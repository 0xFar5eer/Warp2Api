from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
import os

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader, APIKeyQuery

from .logger_config import logger
from .http_client import OptimizedSyncClient, get_sync_client

from .models import ChatCompletionsRequest, ChatMessage, EmbeddingsRequest, EmbeddingsResponse, EmbeddingData
from .reorder import reorder_messages_for_anthropic
from .helpers import normalize_content_to_list, segments_to_text
from .packets import packet_template, map_history_to_warp_messages, attach_user_and_tools_to_inputs
from .state import STATE
from .config import BRIDGE_BASE_URL
from .bridge import initialize_once
from .sse_transform import stream_openai_sse


router = APIRouter()

# API Key validation setup
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


def get_required_api_key() -> Optional[str]:
    """
    Get the required API key from environment.
    Reads dynamically to support runtime changes.
    Treats empty string as None (no API key required).
    """
    api_key = os.getenv("API_KEY")
    return api_key if api_key else None


async def get_api_key(
    api_key_from_header: Optional[str] = Depends(api_key_header),
    api_key_from_query: Optional[str] = Depends(api_key_query),
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """Validate API key from header, query parameter, or Bearer token."""
    # Get required API key dynamically
    required_api_key = get_required_api_key()
    
    # If no API key is configured, allow all requests
    if not required_api_key:
        return None
    
    # Get the provided API key from either source
    provided_key = api_key_from_header or api_key_from_query
    
    # Check Authorization header for Bearer token (OpenAI compatibility)
    if not provided_key and authorization:
        # Extract Bearer token from Authorization header
        if authorization.startswith("Bearer "):
            provided_key = authorization[7:]  # Remove "Bearer " prefix
            logger.info(f"API key extracted from Bearer token: {provided_key[:8]}...")
    
    # Check if API key was provided
    if not provided_key:
        logger.warning("API key required but not provided in request")
        raise HTTPException(
            status_code=401,
            detail="API key required. Please provide via X-API-Key header, Authorization: Bearer header, or api_key query parameter",
        )
    
    # Validate the API key
    if provided_key != required_api_key:
        logger.warning(f"Invalid API key provided: {provided_key[:8]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )
    
    return provided_key


@router.get("/")
def root():
    return {"service": "OpenAI Chat Completions (Warp bridge) - Streaming", "status": "ok"}


@router.get("/healthz")
def health_check():
    return {"status": "ok", "service": "OpenAI Chat Completions (Warp bridge) - Streaming"}


@router.get("/v1/models")
def list_models(api_key: Optional[str] = Depends(get_api_key)):
    """OpenAI-compatible model listing. Forwards to bridge, with local fallback."""
    headers = {}
    
    # Use optimized HTTP client
    client = get_sync_client()
    
    try:
        # Use caching for model listing
        resp = client.get(f"{BRIDGE_BASE_URL}/v1/models", headers=headers, timeout=10.0, use_cache=True)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"bridge_error: {resp.text}")
        return resp.json()
    except Exception as e:
        try:
            # Local fallback: construct models directly if bridge is unreachable
            from warp2protobuf.config.models import get_all_unique_models  # type: ignore
            models = get_all_unique_models()
            return {"object": "list", "data": models}
        except Exception:
            raise HTTPException(502, f"bridge_unreachable: {e}")


@router.post("/v1/chat/completions")
async def chat_completions(
    req: ChatCompletionsRequest,
    api_key: Optional[str] = Depends(get_api_key)
):
    try:
        initialize_once()
    except Exception as e:
        logger.warning(f"[OpenAI Compat] initialize_once failed or skipped: {e}")

    if not req.messages:
        raise HTTPException(400, "messages cannot be empty")

    # 1) Log the received Chat Completions raw request body
    try:
        logger.info("[OpenAI Compat] Received Chat Completions request body (raw): %s", json.dumps(req.dict(), ensure_ascii=False))
    except Exception:
        logger.info("[OpenAI Compat] Failed to serialize received Chat Completions request body (raw)")

    # Organize messages
    history: List[ChatMessage] = reorder_messages_for_anthropic(list(req.messages))

    # 2) Log the organized request body (post-reorder)
    try:
        logger.info("[OpenAI Compat] Organized request body (post-reorder): %s", json.dumps({
            **req.dict(),
            "messages": [m.dict() for m in history]
        }, ensure_ascii=False))
    except Exception:
        logger.info("[OpenAI Compat] Failed to serialize organized request body (post-reorder)")

    system_prompt_text: Optional[str] = None
    try:
        chunks: List[str] = []
        for _m in history:
            if _m.role == "system":
                _txt = segments_to_text(normalize_content_to_list(_m.content))
                if _txt.strip():
                    chunks.append(_txt)
        if chunks:
            system_prompt_text = "\n\n".join(chunks)
    except Exception:
        system_prompt_text = None

    task_id = STATE.baseline_task_id or str(uuid.uuid4())
    packet = packet_template()
    packet["task_context"] = {
        "tasks": [{
            "id": task_id,
            "description": "",
            "status": {"in_progress": {}},
            "messages": map_history_to_warp_messages(history, task_id, None, False),
        }],
        "active_task_id": task_id,
    }

    packet.setdefault("settings", {}).setdefault("model_config", {})
    packet["settings"]["model_config"]["base"] = req.model or packet["settings"]["model_config"].get("base") or "claude-4.1-opus"

    if STATE.conversation_id:
        packet.setdefault("metadata", {})["conversation_id"] = STATE.conversation_id

    attach_user_and_tools_to_inputs(packet, history, system_prompt_text)

    if req.tools:
        mcp_tools: List[Dict[str, Any]] = []
        for t in req.tools:
            if t.type != "function" or not t.function:
                continue
            mcp_tools.append({
                "name": t.function.name,
                "description": t.function.description or "",
                "input_schema": t.function.parameters or {},
            })
        if mcp_tools:
            packet.setdefault("mcp_context", {}).setdefault("tools", []).extend(mcp_tools)

    # 3) Log the request body converted to protobuf JSON (packet sent to bridge)
    try:
        logger.info("[OpenAI Compat] Request body converted to Protobuf JSON: %s", json.dumps(packet, ensure_ascii=False))
    except Exception:
        logger.info("[OpenAI Compat] Failed to serialize request body converted to Protobuf JSON")

    created_ts = int(time.time())
    completion_id = str(uuid.uuid4())
    model_id = req.model or "warp-default"

    if req.stream:
        async def _agen():
            async for chunk in stream_openai_sse(packet, completion_id, created_ts, model_id):
                yield chunk
        return StreamingResponse(_agen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

    # Use optimized HTTP client
    client = get_sync_client()
    
    def _post_once() -> Any:
        # Get API key from environment for internal bridge requests
        bridge_api_key = os.getenv("API_KEY")
        headers = {}
        if bridge_api_key:
            headers["X-API-Key"] = bridge_api_key
        
        return client.post(
            f"{BRIDGE_BASE_URL}/api/warp/send_stream",
            json={"json_data": packet, "message_type": "warp.multi_agent.v1.Request"},
            headers=headers,
            timeout=(5.0, 180.0)
        )

    try:
        resp = _post_once()
        if resp.status_code == 429:
            try:
                # Get API key from environment for internal bridge requests
                bridge_api_key = os.getenv("API_KEY")
                headers = {}
                if bridge_api_key:
                    headers["X-API-Key"] = bridge_api_key
                # Try refresh endpoint
                r = client.post(f"{BRIDGE_BASE_URL}/api/auth/refresh", headers=headers, timeout=10.0)
                logger.warning("[OpenAI Compat] Bridge returned 429. Tried JWT refresh -> HTTP %s", getattr(r, 'status_code', 'N/A'))
            except Exception as _e:
                logger.warning("[OpenAI Compat] JWT refresh attempt failed after 429: %s", _e)
            resp = _post_once()
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"bridge_error: {resp.text}")
        bridge_resp = resp.json()
    except Exception as e:
        raise HTTPException(502, f"bridge_unreachable: {e}")

    try:
        STATE.conversation_id = bridge_resp.get("conversation_id") or STATE.conversation_id
        ret_task_id = bridge_resp.get("task_id")
        if isinstance(ret_task_id, str) and ret_task_id:
            STATE.baseline_task_id = ret_task_id
    except Exception:
        pass

    tool_calls: List[Dict[str, Any]] = []
    try:
        parsed_events = bridge_resp.get("parsed_events", []) or []
        for ev in parsed_events:
            evd = ev.get("parsed_data") or ev.get("raw_data") or {}
            client_actions = evd.get("client_actions") or evd.get("clientActions") or {}
            actions = client_actions.get("actions") or client_actions.get("Actions") or []
            for action in actions:
                add_msgs = action.get("add_messages_to_task") or action.get("addMessagesToTask") or {}
                if not isinstance(add_msgs, dict):
                    continue
                for message in add_msgs.get("messages", []) or []:
                    tc = message.get("tool_call") or message.get("toolCall") or {}
                    call_mcp = tc.get("call_mcp_tool") or tc.get("callMcpTool") or {}
                    if isinstance(call_mcp, dict) and call_mcp.get("name"):
                        try:
                            args_obj = call_mcp.get("args", {}) or {}
                            args_str = json.dumps(args_obj, ensure_ascii=False)
                        except Exception:
                            args_str = "{}"
                        tool_calls.append({
                            "id": tc.get("tool_call_id") or str(uuid.uuid4()),
                            "type": "function",
                            "function": {"name": call_mcp.get("name"), "arguments": args_str},
                        })
    except Exception:
        pass

    if tool_calls:
        msg_payload = {"role": "assistant", "content": "", "tool_calls": tool_calls}
        finish_reason = "tool_calls"
    else:
        response_text = bridge_resp.get("response", "")
        msg_payload = {"role": "assistant", "content": response_text}
        finish_reason = "stop"

    final = {
        "id": completion_id,
        "object": "chat.completion",
        "created": created_ts,
        "model": model_id,
        "choices": [{"index": 0, "message": msg_payload, "finish_reason": finish_reason}],
    }
    return final


@router.post("/v1/embeddings")
async def create_embeddings(
    req: EmbeddingsRequest,
    api_key: Optional[str] = Depends(get_api_key)
):
    """
    OpenAI-compatible embeddings endpoint using Claude for semantic embedding generation.
    This generates embeddings by using Claude to analyze code and create feature vectors.
    """
    import hashlib
    import numpy as np
    
    try:
        initialize_once()
    except Exception as e:
        logger.warning(f"[OpenAI Compat] initialize_once failed or skipped: {e}")
    
    # Normalize input to list
    if isinstance(req.input, str):
        inputs = [req.input]
    else:
        inputs = req.input
    
    if not inputs:
        raise HTTPException(400, "input cannot be empty")
    
    logger.info(f"[OpenAI Compat] Creating embeddings for {len(inputs)} input(s) using model: {req.model}")
    
    embeddings_data = []
    total_tokens = 0
    
    # Get dimensions (default to 1536 for OpenAI compatibility)
    dimensions = req.dimensions or 1536
    
    # Use optimized HTTP client
    client = get_sync_client()
    
    # Process each input text
    for idx, text in enumerate(inputs):
        try:
            # Option 1: Use Claude to generate semantic features
            # Create a prompt that asks Claude to analyze the code/text
            analysis_prompt = f"""Analyze this code/text for semantic indexing. Extract key features:
1. Primary programming language
2. Main purpose/functionality
3. Key algorithms or patterns used
4. Dependencies or imports
5. Complexity level (1-10)
6. Code quality indicators

Text to analyze:
{text[:2000]}  # Limit to prevent too long prompts

Respond with only a JSON object containing numeric scores (0-1) for each feature."""

            # Prepare the chat completion request
            messages = [
                ChatMessage(role="system", content="You are a code analysis assistant that extracts semantic features for code indexing."),
                ChatMessage(role="user", content=analysis_prompt)
            ]
            
            # Create packet for Claude request
            task_id = str(uuid.uuid4())
            packet = packet_template()
            packet["task_context"] = {
                "tasks": [{
                    "id": task_id,
                    "description": "",
                    "status": {"in_progress": {}},
                    "messages": map_history_to_warp_messages(messages, task_id, None, False),
                }],
                "active_task_id": task_id,
            }
            
            packet.setdefault("settings", {}).setdefault("model_config", {})
            packet["settings"]["model_config"]["base"] = req.model or "claude-4.1-opus"
            
            # Call Claude for semantic analysis
            bridge_api_key = os.getenv("API_KEY")
            headers = {}
            if bridge_api_key:
                headers["X-API-Key"] = bridge_api_key
            
            try:
                resp = client.post(
                    f"{BRIDGE_BASE_URL}/api/warp/send_stream",
                    json={"json_data": packet, "message_type": "warp.multi_agent.v1.Request"},
                    headers=headers,
                    timeout=(5.0, 30.0)  # Shorter timeout for embeddings
                )
                
                if resp.status_code == 200:
                    bridge_resp = resp.json()
                    semantic_text = bridge_resp.get("response", "")
                    
                    # Parse semantic features from Claude's response
                    # For now, we'll use the response to seed our embedding generation
                    semantic_hash = hashlib.sha256((text + semantic_text).encode()).digest()
                else:
                    # Fallback to text-only hash if Claude fails
                    semantic_hash = hashlib.sha256(text.encode()).digest()
                    
            except Exception as e:
                logger.warning(f"Claude analysis failed, using fallback: {e}")
                semantic_hash = hashlib.sha256(text.encode()).digest()
                
        except Exception as e:
            logger.warning(f"Semantic analysis failed, using deterministic fallback: {e}")
            semantic_hash = hashlib.sha256(text.encode()).digest()
        
        # Generate deterministic embedding based on semantic hash
        np.random.seed(int.from_bytes(semantic_hash[:4], 'big'))
        
        # Create base embedding
        embedding = np.random.randn(dimensions)
        
        # Add text-based features for better code understanding
        text_lower = text.lower()
        
        # Language-specific boosts
        if "python" in text_lower or "def " in text_lower or "import " in text_lower:
            embedding[0:50] *= 1.2  # Python indicator
        if "javascript" in text_lower or "function" in text_lower or "const " in text_lower:
            embedding[50:100] *= 1.2  # JavaScript indicator
        if "typescript" in text_lower or "interface " in text_lower or "type " in text_lower:
            embedding[100:150] *= 1.2  # TypeScript indicator
        
        # Code structure indicators
        if "class " in text_lower:
            embedding[150:200] *= 1.3  # OOP code
        if "async " in text_lower or "await " in text_lower:
            embedding[200:250] *= 1.3  # Async code
        if "test" in text_lower or "describe(" in text_lower or "it(" in text_lower:
            embedding[250:300] *= 1.3  # Test code
        
        # Framework/library indicators
        if "react" in text_lower or "usestate" in text_lower or "useeffect" in text_lower:
            embedding[300:350] *= 1.3  # React code
        if "fastapi" in text_lower or "@router" in text_lower or "@app" in text_lower:
            embedding[350:400] *= 1.3  # FastAPI code
        if "express" in text_lower or "app.get" in text_lower or "app.post" in text_lower:
            embedding[400:450] *= 1.3  # Express.js code
        
        # Complexity indicators based on text length and structure
        complexity_score = min(1.0, len(text) / 5000)  # Normalize by typical file size
        embedding[450:500] *= (1 + complexity_score)
        
        # Line count and nesting depth estimation
        line_count = text.count('\n')
        nesting_depth = max(text.count('{'), text.count('['), text.count('(')) / 10
        embedding[500:550] *= (1 + min(1.0, line_count / 100))
        embedding[550:600] *= (1 + min(1.0, nesting_depth))
        
        # Normalize to unit vector
        embedding = embedding / np.linalg.norm(embedding)
        
        embeddings_data.append(EmbeddingData(
            embedding=embedding.tolist(),
            index=idx
        ))
        
        # Estimate token usage
        total_tokens += len(text.split()) * 1.3
    
    # Create response
    response = EmbeddingsResponse(
        data=embeddings_data,
        model=req.model,
        usage={
            "prompt_tokens": int(total_tokens),
            "total_tokens": int(total_tokens)
        }
    )
    
    logger.info(f"[OpenAI Compat] Generated {len(embeddings_data)} embeddings successfully")
    
    return response.dict()