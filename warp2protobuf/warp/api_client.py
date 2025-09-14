#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Warp API client module

Handles communication with Warp API, including protobuf data sending and SSE response parsing.
"""
import httpx
import os
import base64
import binascii
from typing import Optional, Any, Dict
from urllib.parse import urlparse
import socket

from ..core.logging import logger
from ..core.protobuf_utils import protobuf_to_dict
from ..core.auth import get_valid_jwt, acquire_anonymous_access_token
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


async def send_protobuf_to_warp_api(
    protobuf_bytes: bytes, show_all_events: bool = True
) -> tuple[str, Optional[str], Optional[str]]:
    """Send protobuf data to Warp API and get response"""
    try:
        logger.info(f"Sending {len(protobuf_bytes)} bytes to Warp API")
        logger.info(f"Packet first 32 bytes (hex): {protobuf_bytes[:32].hex()}")
        
        warp_url = CONFIG_WARP_URL
        
        logger.info(f"Sending request to: {warp_url}")
        
        conversation_id = None
        task_id = None
        complete_response = []
        all_events = []
        event_count = 0
        
        verify_opt = True
        insecure_env = os.getenv("WARP_INSECURE_TLS", "").lower()
        if insecure_env in ("1", "true", "yes"):
            verify_opt = False
            logger.warning("TLS verification disabled via WARP_INSECURE_TLS for Warp API client")

        # Only use proxy for actual Warp API URLs, not for localhost
        use_proxy = not any(x in warp_url.lower() for x in ['localhost', '127.0.0.1', '0.0.0.0'])
        # Set timeout with longer read timeout for SSE streaming
        # Connect timeout: 10s, Read timeout: 300s (5 minutes) for streaming
        async with httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
            verify=verify_opt,
            trust_env=use_proxy
        ) as client:
            # Try at most twice: if first attempt fails with quota 429, acquire anonymous token and retry once
            for attempt in range(2):
                jwt = await get_valid_jwt() if attempt == 0 else jwt  # keep existing unless refreshed explicitly
                headers = {
                    "accept": "text/event-stream",
                    "content-type": "application/x-protobuf", 
                    "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
                    "x-warp-os-category": "Windows",
                    "x-warp-os-name": "Windows", 
                    "x-warp-os-version": "11 (26100)",
                    "authorization": f"Bearer {jwt}",
                    "content-length": str(len(protobuf_bytes)),
                }
                
                async with client.stream("POST", warp_url, headers=headers, content=protobuf_bytes) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        error_content = error_text.decode('utf-8') if error_text else "No error content"
                        # Detect quota exhaustion error and try to acquire anonymous token on first failure
                        if response.status_code == 429 and attempt == 0 and (
                            ("No remaining quota" in error_content) or ("No AI requests remaining" in error_content)
                        ):
                            logger.warning("WARP API returned 429 (quota exhausted). Attempting to acquire anonymous token and retry once...")
                            try:
                                new_jwt = await acquire_anonymous_access_token()
                            except Exception:
                                new_jwt = None
                            if new_jwt:
                                jwt = new_jwt
                                # Break out of current response and proceed to next attempt
                                continue
                            else:
                                logger.error("Anonymous token acquisition failed, cannot retry.")
                                logger.error(f"WARP API HTTP ERROR {response.status_code}: {error_content}")
                                return f"❌ Warp API Error (HTTP {response.status_code}): {error_content}", None, None
                        # Other errors or second failure
                        logger.error(f"WARP API HTTP ERROR {response.status_code}: {error_content}")
                        return f"❌ Warp API Error (HTTP {response.status_code}): {error_content}", None, None
                    
                    logger.info(f"✅ Received HTTP {response.status_code} response")
                    logger.info("Starting to process SSE event stream...")
                    
                    import re as _re
                    def _parse_payload_bytes(data_str: str):
                        s = _re.sub(r"\s+", "", data_str or "")
                        if not s:
                            return None
                        if _re.fullmatch(r"[0-9a-fA-F]+", s or ""):
                            try:
                                return bytes.fromhex(s)
                            except Exception:
                                pass
                        pad = "=" * ((4 - (len(s) % 4)) % 4)
                        try:
                            import base64 as _b64
                            return _b64.urlsafe_b64decode(s + pad)
                        except Exception:
                            try:
                                return _b64.b64decode(s + pad)
                            except Exception:
                                return None
                    
                    current_data = ""
                    
                    async for line in response.aiter_lines():
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
                                logger.debug("Skipping unparseable SSE data block (not hex/base64 or incomplete)")
                                continue
                            try:
                                event_data = protobuf_to_dict(raw_bytes, "warp.multi_agent.v1.ResponseEvent")
                            except Exception as parse_error:
                                logger.debug(f"Failed to parse event, skipping: {str(parse_error)[:100]}")
                                continue
                            event_count += 1
                            
                            def _get(d: Dict[str, Any], *names: str) -> Any:
                                for n in names:
                                    if isinstance(d, dict) and n in d:
                                        return d[n]
                                return None
                            
                            event_type = _get_event_type(event_data)
                            if show_all_events:
                                all_events.append({"event_number": event_count, "event_type": event_type, "raw_data": event_data})
                            logger.info(f"🔄 Event #{event_count}: {event_type}")
                            if show_all_events:
                                logger.info(f"   📋 Event data: {str(event_data)}...")
                            
                            if "init" in event_data:
                                init_data = event_data["init"]
                                conversation_id = init_data.get("conversation_id", conversation_id)
                                task_id = init_data.get("task_id", task_id)
                                logger.info(f"Session initialized: {conversation_id}")
                                client_actions = _get(event_data, "client_actions", "clientActions")
                                if isinstance(client_actions, dict):
                                    actions = _get(client_actions, "actions", "Actions") or []
                                    for i, action in enumerate(actions):
                                        logger.info(f"   🎯 Action #{i+1}: {list(action.keys())}")
                                        append_data = _get(action, "append_to_message_content", "appendToMessageContent")
                                        if isinstance(append_data, dict):
                                            message = append_data.get("message", {})
                                            agent_output = _get(message, "agent_output", "agentOutput") or {}
                                            text_content = agent_output.get("text", "")
                                            if text_content:
                                                complete_response.append(text_content)
                                                logger.info(f"   📝 Text Fragment: {text_content[:100]}...")
                                        messages_data = _get(action, "add_messages_to_task", "addMessagesToTask")
                                        if isinstance(messages_data, dict):
                                            messages = messages_data.get("messages", [])
                                            task_id = messages_data.get("task_id", messages_data.get("taskId", task_id))
                                            for j, message in enumerate(messages):
                                                logger.info(f"   📨 Message #{j+1}: {list(message.keys())}")
                                                if _get(message, "agent_output", "agentOutput") is not None:
                                                    agent_output = _get(message, "agent_output", "agentOutput") or {}
                                                    text_content = agent_output.get("text", "")
                                                    if text_content:
                                                        complete_response.append(text_content)
                                                        logger.info(f"   📝 Complete Message: {text_content[:100]}...")
                    
                full_response = "".join(complete_response)
                logger.info("="*60)
                logger.info("📊 SSE STREAM SUMMARY")
                logger.info("="*60)
                logger.info(f"📈 Total Events Processed: {event_count}")
                logger.info(f"🆔 Conversation ID: {conversation_id}")
                logger.info(f"🆔 Task ID: {task_id}")
                logger.info(f"📝 Response Length: {len(full_response)} characters")
                logger.info("="*60)
                if full_response:
                    logger.info(f"✅ Stream processing completed successfully")
                    return full_response, conversation_id, task_id
                else:
                    logger.warning("⚠️ No text content received in response")
                    return "Warning: No response content received", conversation_id, task_id
    except Exception as e:
        import traceback
        logger.error("="*60)
        logger.error("WARP API CLIENT EXCEPTION")
        logger.error("="*60)
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error(f"Exception Message: {str(e)}")
        logger.error(f"Request URL: {warp_url if 'warp_url' in locals() else 'Unknown'}")
        logger.error(f"Request Size: {len(protobuf_bytes) if 'protobuf_bytes' in locals() else 'Unknown'}")
        logger.error("Python Traceback:")
        logger.error(traceback.format_exc())
        logger.error("="*60)
        raise


async def send_protobuf_to_warp_api_parsed(protobuf_bytes: bytes) -> tuple[str, Optional[str], Optional[str], list]:
    """Send protobuf data to Warp API and get parsed SSE event data"""
    try:
        logger.info(f"Sending {len(protobuf_bytes)} bytes to Warp API (parse mode)")
        logger.info(f"Packet first 32 bytes (hex): {protobuf_bytes[:32].hex()}")
        
        warp_url = CONFIG_WARP_URL
        
        logger.info(f"Sending request to: {warp_url}")
        
        conversation_id = None
        task_id = None
        complete_response = []
        parsed_events = []
        event_count = 0
        
        verify_opt = True
        insecure_env = os.getenv("WARP_INSECURE_TLS", "").lower()
        if insecure_env in ("1", "true", "yes"):
            verify_opt = False
            logger.warning("TLS verification disabled via WARP_INSECURE_TLS for Warp API client")

        # Only use proxy for actual Warp API URLs, not for localhost
        use_proxy = not any(x in warp_url.lower() for x in ['localhost', '127.0.0.1', '0.0.0.0'])
        # Set timeout with longer read timeout for SSE streaming
        # Connect timeout: 10s, Read timeout: 300s (5 minutes) for streaming
        async with httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
            verify=verify_opt,
            trust_env=use_proxy
        ) as client:
            # Try at most twice: if first attempt fails with quota 429, acquire anonymous token and retry once
            for attempt in range(2):
                jwt = await get_valid_jwt() if attempt == 0 else jwt  # keep existing unless refreshed explicitly
                headers = {
                    "accept": "text/event-stream",
                    "content-type": "application/x-protobuf", 
                    "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
                    "x-warp-os-category": "Windows",
                    "x-warp-os-name": "Windows", 
                    "x-warp-os-version": "11 (26100)",
                    "authorization": f"Bearer {jwt}",
                    "content-length": str(len(protobuf_bytes)),
                }
                
                async with client.stream("POST", warp_url, headers=headers, content=protobuf_bytes) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        error_content = error_text.decode('utf-8') if error_text else "No error content"
                        # Detect quota exhaustion error and try to acquire anonymous token on first failure
                        if response.status_code == 429 and attempt == 0 and (
                            ("No remaining quota" in error_content) or ("No AI requests remaining" in error_content)
                        ):
                            logger.warning("WARP API returned 429 (quota exhausted, parse mode). Attempting to acquire anonymous token and retry once...")
                            try:
                                new_jwt = await acquire_anonymous_access_token()
                            except Exception:
                                new_jwt = None
                            if new_jwt:
                                jwt = new_jwt
                                # Break out of current response and proceed to next attempt
                                continue
                            else:
                                logger.error("Anonymous token acquisition failed, cannot retry (parse mode).")
                                logger.error(f"WARP API HTTP ERROR (parse mode) {response.status_code}: {error_content}")
                                return f"❌ Warp API Error (HTTP {response.status_code}): {error_content}", None, None, []
                        # Other errors or second failure
                        logger.error(f"WARP API HTTP ERROR (parse mode) {response.status_code}: {error_content}")
                        return f"❌ Warp API Error (HTTP {response.status_code}): {error_content}", None, None, []
                    
                    logger.info(f"✅ Received HTTP {response.status_code} response (parse mode)")
                    logger.info("Starting to process SSE event stream...")
                    
                    import re as _re2
                    def _parse_payload_bytes2(data_str: str):
                        s = _re2.sub(r"\s+", "", data_str or "")
                        if not s:
                            return None
                        if _re2.fullmatch(r"[0-9a-fA-F]+", s or ""):
                            try:
                                return bytes.fromhex(s)
                            except Exception:
                                pass
                        pad = "=" * ((4 - (len(s) % 4)) % 4)
                        try:
                            import base64 as _b642
                            return _b642.urlsafe_b64decode(s + pad)
                        except Exception:
                            try:
                                return _b642.b64decode(s + pad)
                            except Exception:
                                return None
                    
                    current_data = ""
                    
                    async for line in response.aiter_lines():
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
                            raw_bytes = _parse_payload_bytes2(current_data)
                            current_data = ""
                            if raw_bytes is None:
                                logger.debug("Skipping unparseable SSE data block (not hex/base64 or incomplete)")
                                continue
                            try:
                                event_data = protobuf_to_dict(raw_bytes, "warp.multi_agent.v1.ResponseEvent")
                                event_count += 1
                                event_type = _get_event_type(event_data)
                                parsed_event = {"event_number": event_count, "event_type": event_type, "parsed_data": event_data}
                                parsed_events.append(parsed_event)
                                logger.info(f"🔄 Event #{event_count}: {event_type}")
                                logger.debug(f"   📋 Event data: {str(event_data)}...")
                                
                                def _get(d: Dict[str, Any], *names: str) -> Any:
                                    for n in names:
                                        if isinstance(d, dict) and n in d:
                                            return d[n]
                                    return None
                                
                                if "init" in event_data:
                                    init_data = event_data["init"]
                                    conversation_id = init_data.get("conversation_id", conversation_id)
                                    task_id = init_data.get("task_id", task_id)
                                    logger.info(f"Session initialized: {conversation_id}")
                                
                                client_actions = _get(event_data, "client_actions", "clientActions")
                                if isinstance(client_actions, dict):
                                    actions = _get(client_actions, "actions", "Actions") or []
                                    for i, action in enumerate(actions):
                                        logger.info(f"   🎯 Action #{i+1}: {list(action.keys())}")
                                        append_data = _get(action, "append_to_message_content", "appendToMessageContent")
                                        if isinstance(append_data, dict):
                                            message = append_data.get("message", {})
                                            agent_output = _get(message, "agent_output", "agentOutput") or {}
                                            text_content = agent_output.get("text", "")
                                            if text_content:
                                                complete_response.append(text_content)
                                                logger.info(f"   📝 Text Fragment: {text_content[:100]}...")
                                        messages_data = _get(action, "add_messages_to_task", "addMessagesToTask")
                                        if isinstance(messages_data, dict):
                                            messages = messages_data.get("messages", [])
                                            task_id = messages_data.get("task_id", messages_data.get("taskId", task_id))
                                            for j, message in enumerate(messages):
                                                logger.info(f"   📨 Message #{j+1}: {list(message.keys())}")
                                                if _get(message, "agent_output", "agentOutput") is not None:
                                                    agent_output = _get(message, "agent_output", "agentOutput") or {}
                                                    text_content = agent_output.get("text", "")
                                                    if text_content:
                                                        complete_response.append(text_content)
                                                        logger.info(f"   📝 Complete Message: {text_content[:100]}...")
                            except Exception as parse_err:
                                logger.debug(f"Failed to parse event, skipping: {str(parse_err)[:100]}")
                                continue
                full_response = "".join(complete_response)
                logger.info("="*60)
                logger.info("📊 SSE STREAM SUMMARY (parse mode)")
                logger.info("="*60)
                logger.info(f"📈 Total Events Processed: {event_count}")
                logger.info(f"🆔 Conversation ID: {conversation_id}")
                logger.info(f"🆔 Task ID: {task_id}")
                logger.info(f"📝 Response Length: {len(full_response)} characters")
                logger.info(f"🎯 Parsed Events Count: {len(parsed_events)}")
                logger.info("="*60)
                
                logger.info(f"✅ Stream processing completed successfully (parse mode)")
                return full_response, conversation_id, task_id, parsed_events
                
    except Exception as e:
        import traceback
        logger.error("="*60)
        logger.error("WARP API CLIENT EXCEPTION (parse mode)")
        logger.error("="*60)
        logger.error(f"Exception Type: {type(e).__name__}")
        logger.error(f"Exception Message: {str(e)}")
        logger.error(f"Request URL: {warp_url if 'warp_url' in locals() else 'Unknown'}")
        logger.error(f"Request Size: {len(protobuf_bytes) if 'protobuf_bytes' in locals() else 'Unknown'}")
        logger.error("Python Traceback:")
        logger.error(traceback.format_exc())
        logger.error("="*60)
        raise