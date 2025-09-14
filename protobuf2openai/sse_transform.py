from __future__ import annotations

import json
import os
import uuid
from typing import Any, AsyncGenerator, Dict

from .logging import logger
from .http_client import OptimizedAsyncClient, get_async_client

from .config import BRIDGE_BASE_URL
from .helpers import _get


async def stream_openai_sse(packet: Dict[str, Any], completion_id: str, created_ts: int, model_id: str) -> AsyncGenerator[str, None]:
    try:
        first = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model_id,
            "choices": [{"index": 0, "delta": {"role": "assistant"}}],
        }
        # Print first converted SSE event (OpenAI format)
        try:
            logger.info("[OpenAI Compat] Converted SSE(emit): %s", json.dumps(first, ensure_ascii=False))
        except Exception:
            pass
        yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"

        # Get API key from environment for internal bridge requests
        api_key = os.getenv("API_KEY")
        headers = {"accept": "text/event-stream"}
        if api_key:
            headers["X-API-Key"] = api_key
        
        # Use optimized async client
        client = get_async_client()
        
        def _do_stream():
            return client.stream(
                "POST",
                f"{BRIDGE_BASE_URL}/api/warp/send_stream_sse",
                headers=headers,
                json={"json_data": packet, "message_type": "warp.multi_agent.v1.Request"},
            )

        # First request with retry logic
        max_retries = 2
        for attempt in range(max_retries):
            response_cm = await _do_stream()
            async with response_cm as response:
                if response.status_code == 429 and attempt == 0:
                    try:
                        # Include API key in refresh request if available
                        refresh_headers = {}
                        if api_key:
                            refresh_headers["X-API-Key"] = api_key
                        r = await client.post(f"{BRIDGE_BASE_URL}/api/auth/refresh", headers=refresh_headers, timeout=10.0)
                        logger.warning("[OpenAI Compat] Bridge returned 429. Tried JWT refresh -> HTTP %s", r.status_code)
                    except Exception as _e:
                        logger.warning("[OpenAI Compat] JWT refresh attempt failed after 429: %s", _e)
                    continue  # Retry with next attempt
                    
                if response.status_code != 200:
                    error_text = await response.aread()
                    error_content = error_text.decode("utf-8") if error_text else ""
                    logger.error(f"[OpenAI Compat] Bridge HTTP error {response.status_code}: {error_content[:300]}")
                    raise RuntimeError(f"bridge error: {error_content}")
                
                current = ""
                tool_calls_emitted = False
                
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        # Print received Protobuf SSE raw event fragment
                        try:
                            logger.info("[OpenAI Compat] Received Protobuf SSE(data): %s", payload)
                        except Exception:
                            pass
                        if payload == "[DONE]":
                            break
                        current += payload
                        continue
                    
                    if (line.strip() == "") and current:
                        try:
                            ev = json.loads(current)
                        except Exception:
                            current = ""
                            continue
                        current = ""
                        event_data = (ev or {}).get("parsed_data") or {}

                        # Print received Protobuf event (parsed)
                        try:
                            logger.info("[OpenAI Compat] Received Protobuf event(parsed): %s", json.dumps(event_data, ensure_ascii=False))
                        except Exception:
                            pass

                        if "init" in event_data:
                            pass

                        client_actions = _get(event_data, "client_actions", "clientActions")
                        if isinstance(client_actions, dict):
                            actions = _get(client_actions, "actions", "Actions") or []
                            for action in actions:
                                append_data = _get(action, "append_to_message_content", "appendToMessageContent")
                                if isinstance(append_data, dict):
                                    message = append_data.get("message", {})
                                    agent_output = _get(message, "agent_output", "agentOutput") or {}
                                    text_content = agent_output.get("text", "")
                                    if text_content:
                                        delta = {
                                            "id": completion_id,
                                            "object": "chat.completion.chunk",
                                            "created": created_ts,
                                            "model": model_id,
                                            "choices": [{"index": 0, "delta": {"content": text_content}}],
                                        }
                                        # Print converted OpenAI SSE event
                                        try:
                                            logger.info("[OpenAI Compat] Converted SSE(emit): %s", json.dumps(delta, ensure_ascii=False))
                                        except Exception:
                                            pass
                                        yield f"data: {json.dumps(delta, ensure_ascii=False)}\n\n"

                                messages_data = _get(action, "add_messages_to_task", "addMessagesToTask")
                                if isinstance(messages_data, dict):
                                    messages = messages_data.get("messages", [])
                                    for message in messages:
                                        tool_call = _get(message, "tool_call", "toolCall") or {}
                                        call_mcp = _get(tool_call, "call_mcp_tool", "callMcpTool") or {}
                                        if isinstance(call_mcp, dict) and call_mcp.get("name"):
                                            try:
                                                args_obj = call_mcp.get("args", {}) or {}
                                                args_str = json.dumps(args_obj, ensure_ascii=False)
                                            except Exception:
                                                args_str = "{}"
                                            tool_call_id = tool_call.get("tool_call_id") or str(uuid.uuid4())
                                            delta = {
                                                "id": completion_id,
                                                "object": "chat.completion.chunk",
                                                "created": created_ts,
                                                "model": model_id,
                                                "choices": [{
                                                    "index": 0,
                                                    "delta": {
                                                        "tool_calls": [{
                                                            "index": 0,
                                                            "id": tool_call_id,
                                                            "type": "function",
                                                            "function": {"name": call_mcp.get("name"), "arguments": args_str},
                                                        }]
                                                    }
                                                }],
                                            }
                                            # Print converted OpenAI tool call event
                                            try:
                                                logger.info("[OpenAI Compat] Converted SSE(emit tool_calls): %s", json.dumps(delta, ensure_ascii=False))
                                            except Exception:
                                                pass
                                            yield f"data: {json.dumps(delta, ensure_ascii=False)}\n\n"
                                            tool_calls_emitted = True
                                        else:
                                            agent_output = _get(message, "agent_output", "agentOutput") or {}
                                            text_content = agent_output.get("text", "")
                                            if text_content:
                                                delta = {
                                                    "id": completion_id,
                                                    "object": "chat.completion.chunk",
                                                    "created": created_ts,
                                                    "model": model_id,
                                                    "choices": [{"index": 0, "delta": {"content": text_content}}],
                                                }
                                                try:
                                                    logger.info("[OpenAI Compat] Converted SSE(emit): %s", json.dumps(delta, ensure_ascii=False))
                                                except Exception:
                                                    pass
                                                yield f"data: {json.dumps(delta, ensure_ascii=False)}\n\n"

                        if "finished" in event_data:
                            done_chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model_id,
                                "choices": [{"index": 0, "delta": {}, "finish_reason": ("tool_calls" if tool_calls_emitted else "stop")}],
                            }
                            try:
                                logger.info("[OpenAI Compat] Converted SSE(emit done): %s", json.dumps(done_chunk, ensure_ascii=False))
                            except Exception:
                                pass
                            yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"

                # Print completion marker
                try:
                    logger.info("[OpenAI Compat] Converted SSE(emit): [DONE]")
                except Exception:
                    pass
                yield "data: [DONE]\n\n"
                return  # Success, exit function

    except Exception as e:
        logger.error(f"[OpenAI Compat] Stream processing failed: {e}")
        error_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model_id,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
            "error": {"message": str(e)},
        }
        try:
            logger.info("[OpenAI Compat] Converted SSE(emit error): %s", json.dumps(error_chunk, ensure_ascii=False))
        except Exception:
            pass
        yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"