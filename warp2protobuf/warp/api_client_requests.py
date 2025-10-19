#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Warp API client using requests library (compatible with intercept server)

This replaces the httpx-based client which has protocol compatibility issues.
"""
import requests
import asyncio
import base64
import urllib3
from typing import Optional, Any, Dict

# Disable SSL warnings for intercept server
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from ..core.logging import logger
from ..core.protobuf_utils import protobuf_to_dict
from ..core.auth import get_valid_jwt
from ..config.settings import WARP_URL as CONFIG_WARP_URL


def _get(d: Dict[str, Any], *names: str) -> Any:
    """Return the first matching key value (camelCase/snake_case tolerant)."""
    for name in names:
        if name in d:
            return d[name]
    return None


def _get_event_type(event_data: dict) -> str:
    """Determine the type of SSE event for logging"""
    if "init" in event_data:
        return "INITIALIZATION"
    client_actions = _get(event_data, "client_actions", "clientActions")
    if isinstance(client_actions, dict):
        actions = _get(client_actions, "actions", "Actions") or []
        if not actions:
            return "CLIENT_ACTIONS_EMPTY"
        
        action_types = []
        for action in actions:
            if _get(action, "create_task", "createTask") is not None:
                action_types.append("CREATE_TASK")
            elif _get(action, "append_to_message_content", "appendToMessageContent") is not None:
                action_types.append("APPEND_CONTENT")
            elif _get(action, "add_messages_to_task", "addMessagesToTask") is not None:
                action_types.append("ADD_MESSAGE")
            elif _get(action, "tool_call", "toolCall") is not None:
                action_types.append("TOOL_CALL")
            elif _get(action, "tool_response", "toolResponse") is not None:
                action_types.append("TOOL_RESPONSE")
            else:
                action_types.append("UNKNOWN_ACTION")
        
        return f"CLIENT_ACTIONS({', '.join(action_types)})"
    elif "finished" in event_data:
        return "FINISHED"
    else:
        return "UNKNOWN_EVENT"


def _parse_sse_stream(response, show_all_events=True):
    """Parse SSE stream from requests response"""
    import re
    
    conversation_id = None
    task_id = None
    complete_response = []
    event_count = 0
    
    def _parse_payload_bytes(data_str: str):
        s = re.sub(r"\s+", "", data_str or "")
        if not s:
            return None
        if re.fullmatch(r"[0-9a-fA-F]+", s or ""):
            try:
                return bytes.fromhex(s)
            except Exception:
                pass
        pad = "=" * ((4 - (len(s) % 4)) % 4)
        try:
            return base64.urlsafe_b64decode(s + pad)
        except Exception:
            try:
                return base64.b64decode(s + pad)
            except Exception:
                return None
    
    current_data = ""
    line_count = 0
    
    logger.info("Starting to iterate over response content...")
    
    # Use iter_content instead of iter_lines for more reliable streaming
    # iter_lines() can fail silently when content-type is missing
    buffer = b""
    for chunk in response.iter_content(chunk_size=8192, decode_unicode=False):
        if not chunk:
            continue
        
        buffer += chunk
        # Process complete lines from buffer
        while b"\n" in buffer:
            line_bytes, buffer = buffer.split(b"\n", 1)
            try:
                line = line_bytes.decode('utf-8').rstrip('\r')
            except UnicodeDecodeError:
                logger.warning(f"Failed to decode line, skipping")
                continue
            
            line_count += 1
            if line_count <= 10:  # Log first 10 lines to see what we're getting
                logger.info(f"📥 Raw line #{line_count}: {repr(line[:200])}")
            
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload:
                    continue
                if payload == "[DONE]":
                    logger.info("Received [DONE] marker, ending processing")
                    break
                current_data += payload
                continue
            
            if (line.strip() == "") and current_data:
                raw_bytes = _parse_payload_bytes(current_data)
                current_data = ""
                if raw_bytes is None:
                    logger.debug("Skipping unparseable SSE data block")
                    continue
                try:
                    event_data = protobuf_to_dict(raw_bytes, "warp.multi_agent.v1.ResponseEvent")
                except Exception as parse_error:
                    logger.debug(f"Failed to parse event: {str(parse_error)[:100]}")
                    continue
                
                event_count += 1
                event_type = _get_event_type(event_data)
                logger.info(f"🔄 Event #{event_count}: {event_type}")
                if show_all_events:
                    logger.debug(f"   📋 Event data: {str(event_data)[:200]}...")
                
                if "init" in event_data:
                    init_data = event_data["init"]
                    conversation_id = init_data.get("conversation_id", conversation_id)
                    task_id = init_data.get("task_id", task_id)
                    logger.info(f"Session initialized: {conversation_id}")
                
                client_actions = _get(event_data, "client_actions", "clientActions")
                if isinstance(client_actions, dict):
                    actions = _get(client_actions, "actions", "Actions") or []
                    for i, action in enumerate(actions):
                        append_data = _get(action, "append_to_message_content", "appendToMessageContent")
                        if isinstance(append_data, dict):
                            message = append_data.get("message", {})
                            agent_output = _get(message, "agent_output", "agentOutput") or {}
                            text_content = agent_output.get("text", "")
                            if text_content:
                                complete_response.append(text_content)
                                logger.info(f"   📝 Text: {text_content[:100]}...")
                        
                        messages_data = _get(action, "add_messages_to_task", "addMessagesToTask")
                        if isinstance(messages_data, dict):
                            messages = messages_data.get("messages", [])
                            task_id = messages_data.get("task_id", messages_data.get("taskId", task_id))
                            for message in messages:
                                if _get(message, "agent_output", "agentOutput") is not None:
                                    agent_output = _get(message, "agent_output", "agentOutput") or {}
                                    text_content = agent_output.get("text", "")
                                    if text_content:
                                        complete_response.append(text_content)
                                        logger.info(f"   📝 Message: {text_content[:100]}...")
    
    logger.info(f"Finished iterating. Total lines processed: {line_count}")
    full_response = "".join(complete_response)
    logger.info("="*60)
    logger.info("📊 SSE STREAM SUMMARY")
    logger.info(f"📈 Total Events: {event_count}")
    logger.info(f"🆔 Conversation ID: {conversation_id}")
    logger.info(f"🆔 Task ID: {task_id}")
    logger.info(f"📝 Response Length: {len(full_response)} characters")
    logger.info("="*60)
    
    return full_response, conversation_id, task_id


async def send_protobuf_to_warp_api(
    protobuf_bytes: bytes, show_all_events: bool = True
) -> tuple[str, Optional[str], Optional[str]]:
    """Send protobuf data to Warp API and get response"""
    def _sync_request():
        logger.info(f"Sending {len(protobuf_bytes)} bytes to Warp API")
        logger.info(f"Packet first 32 bytes (hex): {protobuf_bytes[:32].hex()}") 
        
        warp_url = CONFIG_WARP_URL
        logger.info(f"Sending request to: {warp_url}")
        logger.info("TLS verification disabled for intercept server")
        
        # Get JWT (need to run in new event loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        jwt = loop.run_until_complete(get_valid_jwt())
        loop.close()
        
        headers = {
            "accept": "text/event-stream",
            "content-type": "application/x-protobuf",
            "x-warp-client-version": "v0.2025.09.24.08.11.stable_00",
            "x-warp-os-category": "Windows",
            "x-warp-os-name": "Windows",
            "x-warp-os-version": "11 (26100)",
            "authorization": f"Bearer {jwt}",
        }
        
        response = requests.post(
            warp_url,
            headers=headers,
            data=protobuf_bytes,
            stream=True,
            verify=False,
            timeout=(10.0, 300.0)
        )
        
        if response.status_code != 200:
            error_content = response.text or "No error content"
            logger.error(f"WARP API HTTP ERROR {response.status_code}: {error_content}")
            return f"❌ Warp API Error (HTTP {response.status_code}): {error_content}", None, None
        
        logger.info(f"✅ Received HTTP {response.status_code} response")
        content_type = response.headers.get('content-type', 'NOT SET')
        logger.info(f"Content-Type: {content_type}")
        logger.info(f"Transfer-Encoding: {response.headers.get('transfer-encoding', 'NOT SET')}")
        
        # WORKAROUND: If content-type is missing but we requested text/event-stream,
        # assume the response is SSE. This handles cases where the intercept server
        # doesn't preserve or the Warp API doesn't set the content-type header.
        if content_type == 'NOT SET' and headers.get('accept') == 'text/event-stream':
            logger.warning("⚠️  Content-Type header is missing from response!")
            logger.warning("⚠️  We requested 'text/event-stream' so assuming SSE format")
            logger.warning("⚠️  This is likely a bug in the upstream server or intercept layer")
        
        logger.info("Starting to process SSE event stream...")
        
        try:
            return _parse_sse_stream(response, show_all_events)
        except Exception as e:
            logger.error(f"Failed to parse SSE stream: {e}")
            raise
    
    try:
        # Run sync request in thread pool
        return await asyncio.to_thread(_sync_request)
    except Exception as e:
        import traceback
        logger.error("="*60)
        logger.error("WARP API CLIENT EXCEPTION")
        logger.error(f"Exception: {type(e).__name__}: {str(e)}")
        logger.error(traceback.format_exc())
        logger.error("="*60)
        raise


async def send_protobuf_to_warp_api_parsed(protobuf_bytes: bytes) -> tuple[str, Optional[str], Optional[str], list]:
    """Send protobuf data and return parsed events (same as non-parsed for now)"""
    full_response, conversation_id, task_id = await send_protobuf_to_warp_api(protobuf_bytes, show_all_events=True)
    # For simplicity, return empty parsed_events list - can be enhanced later if needed
    return full_response, conversation_id, task_id, []


async def send_protobuf_to_warp_api_stream(protobuf_bytes: bytes):
    """Send protobuf data and yield SSE events as they arrive"""
    def _sync_stream():
        """Synchronous streaming request handler"""
        import re
        import json
        
        logger.info(f"Streaming {len(protobuf_bytes)} bytes to Warp API")
        
        warp_url = CONFIG_WARP_URL
        logger.info(f"Streaming request to: {warp_url}")
        logger.info("TLS verification disabled for intercept server")
        
        # Get JWT
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        jwt = loop.run_until_complete(get_valid_jwt())
        loop.close()
        
        headers = {
            "accept": "text/event-stream",
            "content-type": "application/x-protobuf",
            "x-warp-client-version": "v0.2025.09.24.08.11.stable_00",
            "x-warp-os-category": "Windows",
            "x-warp-os-name": "Windows",
            "x-warp-os-version": "11 (26100)",
            "authorization": f"Bearer {jwt}",
        }
        
        response = requests.post(
            warp_url,
            headers=headers,
            data=protobuf_bytes,
            stream=True,
            verify=False,
            timeout=(10.0, 300.0)
        )
        
        if response.status_code != 200:
            error_content = response.text or "No error content"
            logger.error(f"WARP API HTTP ERROR {response.status_code}: {error_content}")
            yield {"error": f"HTTP {response.status_code}", "detail": error_content}
            return
        
        logger.info(f"✅ Streaming response received (HTTP {response.status_code})")
        
        def _parse_payload_bytes(data_str: str):
            s = re.sub(r"\s+", "", data_str or "")
            if not s:
                return None
            if re.fullmatch(r"[0-9a-fA-F]+", s or ""):
                try:
                    return bytes.fromhex(s)
                except Exception:
                    pass
            pad = "=" * ((4 - (len(s) % 4)) % 4)
            try:
                return base64.urlsafe_b64decode(s + pad)
            except Exception:
                try:
                    return base64.b64decode(s + pad)
                except Exception:
                    return None
        
        current_data = ""
        event_no = 0
        
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload:
                    continue
                if payload == "[DONE]":
                    logger.info("Received [DONE] marker")
                    break
                current_data += payload
                continue
            
            if (line.strip() == "") and current_data:
                raw_bytes = _parse_payload_bytes(current_data)
                current_data = ""
                if raw_bytes is None:
                    continue
                try:
                    event_data = protobuf_to_dict(raw_bytes, "warp.multi_agent.v1.ResponseEvent")
                except Exception as e:
                    logger.debug(f"Failed to parse event: {e}")
                    continue
                
                event_no += 1
                
                # Determine event type
                event_type = "UNKNOWN_EVENT"
                if isinstance(event_data, dict):
                    if "init" in event_data:
                        event_type = "INITIALIZATION"
                    elif "client_actions" in event_data or "clientActions" in event_data:
                        client_actions = event_data.get("client_actions") or event_data.get("clientActions") or {}
                        actions = client_actions.get("actions") or client_actions.get("Actions") or []
                        event_type = f"CLIENT_ACTIONS({len(actions)})"
                    elif "finished" in event_data:
                        event_type = "FINISHED"
                
                logger.info(f"🔄 SSE Event #{event_no}: {event_type}")
                
                out = {
                    "event_number": event_no,
                    "event_type": event_type,
                    "parsed_data": event_data
                }
                yield out
        
        logger.info(f"📊 Stream complete: {event_no} events forwarded")
    
    # Stream events asynchronously
    for event in await asyncio.to_thread(lambda: list(_sync_stream())):
        yield event
