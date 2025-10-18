#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Protobuf Encoding/Decoding API Routes

Provides pure protobuf packet encoding/decoding services, including JWT management and WebSocket support.
"""
import json
import base64
import asyncio
import httpx
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.logging import logger
from ..core.protobuf_utils import protobuf_to_dict, dict_to_protobuf_bytes
from ..core.auth import get_jwt_token, get_valid_jwt
from ..core.stream_processor import get_stream_processor, set_websocket_manager
from ..core.api_key_validation import get_api_key
from ..config.models import get_all_unique_models
from ..config.settings import CLIENT_VERSION, OS_CATEGORY, OS_NAME, OS_VERSION, WARP_URL as CONFIG_WARP_URL
from ..core.server_message_data import decode_server_message_data, encode_server_message_data


def _encode_smd_inplace(obj: Any) -> Any:
    if isinstance(obj, dict):
        new_d = {}
        for k, v in obj.items():
            if k in ("server_message_data", "serverMessageData") and isinstance(v, dict):
                try:
                    b64 = encode_server_message_data(
                        uuid=v.get("uuid"),
                        seconds=v.get("seconds"),
                        nanos=v.get("nanos"),
                    )
                    new_d[k] = b64
                except Exception:
                    new_d[k] = v
            else:
                new_d[k] = _encode_smd_inplace(v)
        return new_d
    elif isinstance(obj, list):
        return [_encode_smd_inplace(x) for x in obj]
    else:
        return obj


def _decode_smd_inplace(obj: Any) -> Any:
    if isinstance(obj, dict):
        new_d = {}
        for k, v in obj.items():
            if k in ("server_message_data", "serverMessageData") and isinstance(v, str):
                try:
                    dec = decode_server_message_data(v)
                    new_d[k] = dec
                except Exception:
                    new_d[k] = v
            else:
                new_d[k] = _decode_smd_inplace(v)
        return new_d
    elif isinstance(obj, list):
        return [_decode_smd_inplace(x) for x in obj]
    else:
        return obj
from ..core.schema_sanitizer import sanitize_mcp_input_schema_in_packet


class EncodeRequest(BaseModel):
    json_data: Optional[Dict[str, Any]] = None
    message_type: str = "warp.multi_agent.v1.Request"
    
    task_context: Optional[Dict[str, Any]] = None
    input: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    mcp_context: Optional[Dict[str, Any]] = None
    existing_suggestions: Optional[Dict[str, Any]] = None
    client_version: Optional[str] = None
    os_category: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    
    class Config:
        extra = "allow"
    
    def get_data(self) -> Dict[str, Any]:
        if self.json_data is not None:
            return self.json_data
        else:
            data: Dict[str, Any] = {}
            if self.task_context is not None:
                data["task_context"] = self.task_context
            if self.input is not None:
                data["input"] = self.input
            if self.settings is not None:
                data["settings"] = self.settings
            if self.metadata is not None:
                data["metadata"] = self.metadata
            if self.mcp_context is not None:
                data["mcp_context"] = self.mcp_context
            if self.existing_suggestions is not None:
                data["existing_suggestions"] = self.existing_suggestions
            if self.client_version is not None:
                data["client_version"] = self.client_version
            if self.os_category is not None:
                data["os_category"] = self.os_category
            if self.os_name is not None:
                data["os_name"] = self.os_name
            if self.os_version is not None:
                data["os_version"] = self.os_version
            
            skip_keys = {
                "json_data", "message_type", "task_context", "input", "settings", "metadata",
                "mcp_context", "existing_suggestions", "client_version", "os_category", "os_name", "os_version"
            }
            try:
                for k, v in self.__dict__.items():
                    if v is None:
                        continue
                    if k in skip_keys:
                        continue
                    if k not in data:
                        data[k] = v
            except Exception:
                pass
            return data


class DecodeRequest(BaseModel):
    protobuf_bytes: str
    message_type: str = "warp.multi_agent.v1.Request"


class StreamDecodeRequest(BaseModel):
    protobuf_chunks: List[str]
    message_type: str = "warp.multi_agent.v1.Response"


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.packet_history: List[Dict] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connection established, current connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket connection closed, current connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict):
        if not self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)
    
    async def log_packet(self, packet_type: str, data: Dict, size: int):
        packet_info = {
            "timestamp": datetime.now().isoformat(),
            "type": packet_type,
            "size": size,
            "data_preview": str(data)[:200] + "..." if len(str(data)) > 200 else str(data),
            "full_data": data
        }
        
        self.packet_history.append(packet_info)
        if len(self.packet_history) > 100:
            self.packet_history = self.packet_history[-100:]
        
        await self.broadcast({"event": "packet_captured", "packet": packet_info})


manager = ConnectionManager()
set_websocket_manager(manager)

app = FastAPI(title="Warp Protobuf Encoding/Decoding Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Warp Protobuf Encoding/Decoding Server", "version": "1.0.0"}


@app.get("/healthz")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/api/encode")
async def encode_json_to_protobuf(
    request: EncodeRequest,
    api_key: Optional[str] = Depends(get_api_key)
):
    try:
        logger.info(f"Received encoding request, message type: {request.message_type}")
        actual_data = request.get_data()
        if not actual_data:
            raise HTTPException(400, "Data packet cannot be empty")
        wrapped = {"json_data": actual_data}
        wrapped = sanitize_mcp_input_schema_in_packet(wrapped)
        actual_data = wrapped.get("json_data", actual_data)
        actual_data = _encode_smd_inplace(actual_data)
        protobuf_bytes = dict_to_protobuf_bytes(actual_data, request.message_type)
        try:
            await manager.log_packet("encode", actual_data, len(protobuf_bytes))
        except Exception as log_error:
            logger.warning(f"Failed to record data packet: {log_error}")
        result = {
            "protobuf_bytes": base64.b64encode(protobuf_bytes).decode('utf-8'),
            "size": len(protobuf_bytes),
            "message_type": request.message_type
        }
        logger.info(f"✅ JSON encoded to protobuf successfully: {len(protobuf_bytes)} bytes")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ JSON encoding failed: {e}")
        raise HTTPException(500, f"Encoding failed: {str(e)}")


@app.post("/api/decode")
async def decode_protobuf_to_json(
    request: DecodeRequest,
    api_key: Optional[str] = Depends(get_api_key)
):
    try:
        logger.info(f"Received decoding request, message type: {request.message_type}")
        if not request.protobuf_bytes or not request.protobuf_bytes.strip():
            raise HTTPException(400, "Protobuf data cannot be empty")
        try:
            protobuf_bytes = base64.b64decode(request.protobuf_bytes)
        except Exception as decode_error:
            logger.error(f"Base64 decoding failed: {decode_error}")
            raise HTTPException(400, f"Base64 decoding failed: {str(decode_error)}")
        if not protobuf_bytes:
            raise HTTPException(400, "Decoded protobuf data is empty")
        json_data = protobuf_to_dict(protobuf_bytes, request.message_type)
        try:
            await manager.log_packet("decode", json_data, len(protobuf_bytes))
        except Exception as log_error:
            logger.warning(f"Failed to record data packet: {log_error}")
        result = {"json_data": json_data, "size": len(protobuf_bytes), "message_type": request.message_type}
        logger.info(f"✅ Protobuf decoded to JSON successfully: {len(protobuf_bytes)} bytes")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Protobuf decoding failed: {e}")
        raise HTTPException(500, f"Decoding failed: {e}")


@app.post("/api/stream-decode")
async def decode_stream_protobuf(
    request: StreamDecodeRequest,
    api_key: Optional[str] = Depends(get_api_key)
):
    try:
        logger.info(f"Received streaming decode request, chunk count: {len(request.protobuf_chunks)}")
        results = []
        total_size = 0
        for i, chunk_b64 in enumerate(request.protobuf_chunks):
            try:
                chunk_bytes = base64.b64decode(chunk_b64)
                chunk_json = protobuf_to_dict(chunk_bytes, request.message_type)
                chunk_result = {"chunk_index": i, "json_data": chunk_json, "size": len(chunk_bytes)}
                results.append(chunk_result)
                total_size += len(chunk_bytes)
                await manager.log_packet(f"stream_decode_chunk_{i}", chunk_json, len(chunk_bytes))
            except Exception as e:
                logger.warning(f"Chunk {i} decoding failed: {e}")
                results.append({"chunk_index": i, "error": str(e), "size": 0})
        try:
            all_bytes = b''.join([base64.b64decode(chunk) for chunk in request.protobuf_chunks])
            complete_json = protobuf_to_dict(all_bytes, request.message_type)
            await manager.log_packet("stream_decode_complete", complete_json, len(all_bytes))
            complete_result = {"json_data": complete_json, "size": len(all_bytes)}
        except Exception as e:
            complete_result = {"error": f"Unable to concatenate complete message: {e}", "size": total_size}
        result = {"chunks": results, "complete": complete_result, "total_chunks": len(request.protobuf_chunks), "total_size": total_size, "message_type": request.message_type}
        logger.info(f"✅ Streaming protobuf decode completed: {len(request.protobuf_chunks)} chunks, total size {total_size} bytes")
        return result
    except Exception as e:
        logger.error(f"❌ Streaming protobuf decode failed: {e}")
        raise HTTPException(500, f"Streaming decode failed: {e}")


@app.get("/api/schemas")
async def get_protobuf_schemas(api_key: Optional[str] = Depends(get_api_key)):
    try:
        from ..core.protobuf import ensure_proto_runtime, ALL_MSGS, msg_cls
        ensure_proto_runtime()
        schemas = []
        for msg_name in ALL_MSGS:
            try:
                MessageClass = msg_cls(msg_name)
                descriptor = MessageClass.DESCRIPTOR
                fields = []
                for field in descriptor.fields:
                    fields.append({"name": field.name, "type": field.type, "label": getattr(field, 'label', None), "number": field.number})
                schemas.append({"name": msg_name, "full_name": descriptor.full_name, "field_count": len(fields), "fields": fields[:10]})
            except Exception as e:
                logger.warning(f"Failed to get schema {msg_name} info: {e}")
        result = {"schemas": schemas, "total_count": len(schemas), "message": f"Found {len(schemas)} protobuf message types"}
        logger.info(f"✅ Returned {len(schemas)} protobuf schemas")
        return result
    except Exception as e:
        logger.error(f"❌ Failed to get protobuf schemas: {e}")
        raise HTTPException(500, f"Failed to get schemas: {e}")


# Auth endpoints removed - using dummy bearer token with intercept server
# No token management needed as intercept server handles authentication


@app.get("/api/packets/history")
async def get_packet_history(limit: int = 50, api_key: Optional[str] = Depends(get_api_key)):
    try:
        history = manager.packet_history[-limit:] if len(manager.packet_history) > limit else manager.packet_history
        return {"packets": history, "total_count": len(manager.packet_history), "returned_count": len(history)}
    except Exception as e:
        logger.error(f"❌ Failed to get packet history: {e}")
        raise HTTPException(500, f"Failed to get history: {e}")


@app.post("/api/warp/send")
async def send_to_warp_api(
    request: EncodeRequest,
    show_all_events: bool = Query(True, description="Show detailed SSE event breakdown"),
    api_key: Optional[str] = Depends(get_api_key)
):
    try:
        logger.info(f"Received Warp API send request, message type: {request.message_type}")
        actual_data = request.get_data()
        if not actual_data:
            raise HTTPException(400, "Data packet cannot be empty")
        wrapped = {"json_data": actual_data}
        wrapped = sanitize_mcp_input_schema_in_packet(wrapped)
        actual_data = wrapped.get("json_data", actual_data)
        actual_data = _encode_smd_inplace(actual_data)
        protobuf_bytes = dict_to_protobuf_bytes(actual_data, request.message_type)
        logger.info(f"✅ JSON encoded to protobuf successfully: {len(protobuf_bytes)} bytes")
        from ..warp.api_client_requests import send_protobuf_to_warp_api
        response_text, conversation_id, task_id = await send_protobuf_to_warp_api(protobuf_bytes, show_all_events=show_all_events)
        await manager.log_packet("warp_request", actual_data, len(protobuf_bytes))
        await manager.log_packet("warp_response", {"response": response_text, "conversation_id": conversation_id, "task_id": task_id}, len(response_text.encode()))
        result = {"response": response_text, "conversation_id": conversation_id, "task_id": task_id, "request_size": len(protobuf_bytes), "response_size": len(response_text), "message_type": request.message_type}
        logger.info(f"✅ Warp API call successful, response length: {len(response_text)} characters")
        return result
    except Exception as e:
        import traceback
        error_details = {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc(), "request_info": {"message_type": request.message_type, "json_size": len(str(actual_data)), "has_tools": "mcp_context" in actual_data, "has_history": "task_context" in actual_data}}
        logger.error(f"❌ Warp API call failed: {e}")
        logger.error(f"Error details: {error_details}")
        try:
            await manager.log_packet("warp_error", error_details, 0)
        except Exception as log_error:
            logger.warning(f"Failed to record error: {log_error}")
        raise HTTPException(500, detail=error_details)


@app.post("/api/warp/send_stream")
async def send_to_warp_api_parsed(
    request: EncodeRequest,
    api_key: Optional[str] = Depends(get_api_key)
):
    try:
        logger.info(f"Received Warp API parse send request, message type: {request.message_type}")
        actual_data = request.get_data()
        if not actual_data:
            raise HTTPException(400, "Data packet cannot be empty")
        wrapped = {"json_data": actual_data}
        wrapped = sanitize_mcp_input_schema_in_packet(wrapped)
        actual_data = wrapped.get("json_data", actual_data)
        actual_data = _encode_smd_inplace(actual_data)
        protobuf_bytes = dict_to_protobuf_bytes(actual_data, request.message_type)
        logger.info(f"✅ JSON encoded to protobuf successfully: {len(protobuf_bytes)} bytes")
        from ..warp.api_client_requests import send_protobuf_to_warp_api_parsed
        response_text, conversation_id, task_id, parsed_events = await send_protobuf_to_warp_api_parsed(protobuf_bytes)
        parsed_events = _decode_smd_inplace(parsed_events)
        await manager.log_packet("warp_request_parsed", actual_data, len(protobuf_bytes))
        response_data = {"response": response_text, "conversation_id": conversation_id, "task_id": task_id, "parsed_events": parsed_events}
        await manager.log_packet("warp_response_parsed", response_data, len(str(response_data)))
        result = {"response": response_text, "conversation_id": conversation_id, "task_id": task_id, "request_size": len(protobuf_bytes), "response_size": len(response_text), "message_type": request.message_type, "parsed_events": parsed_events, "events_count": len(parsed_events), "events_summary": {}}
        if parsed_events:
            event_type_counts = {}
            for event in parsed_events:
                event_type = event.get("event_type", "UNKNOWN")
                event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            result["events_summary"] = event_type_counts
        logger.info(f"✅ Warp API parse call successful, response length: {len(response_text)} characters, event count: {len(parsed_events)}")
        return result
    except Exception as e:
        import traceback
        error_details = {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc(), "request_info": {"message_type": request.message_type, "json_size": len(str(actual_data)) if 'actual_data' in locals() else 0, "has_tools": "mcp_context" in (actual_data or {}), "has_history": "task_context" in (actual_data or {})}}
        logger.error(f"❌ Warp API parse call failed: {e}")
        logger.error(f"Error details: {error_details}")
        try:
            await manager.log_packet("warp_error_parsed", error_details, 0)
        except Exception as log_error:
            logger.warning(f"Failed to record error: {log_error}")
        raise HTTPException(500, detail=error_details)


@app.post("/api/warp/send_stream_sse")
async def send_to_warp_api_stream_sse(
    request: EncodeRequest,
    api_key: Optional[str] = Depends(get_api_key)
):
    from fastapi.responses import StreamingResponse
    import os as _os
    import re as _re
    try:
        actual_data = request.get_data()
        if not actual_data:
            raise HTTPException(400, "Data packet cannot be empty")
        wrapped = {"json_data": actual_data}
        wrapped = sanitize_mcp_input_schema_in_packet(wrapped)
        actual_data = wrapped.get("json_data", actual_data)
        actual_data = _encode_smd_inplace(actual_data)
        protobuf_bytes = dict_to_protobuf_bytes(actual_data, request.message_type)
        from ..warp.api_client_requests import send_protobuf_to_warp_api_stream
        
        async def _agen():
            async for event in send_protobuf_to_warp_api_stream(protobuf_bytes):
                if "error" in event:
                    logger.error(f"Warp API error: {event}")
                    yield f"data: {{\"error\": \"{event.get('error')}\"}}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                try:
                    chunk = json.dumps(event, ensure_ascii=False)
                    yield f"data: {chunk}\n\n"
                except Exception as e:
                    logger.error(f"Failed to serialize event: {e}")
                    continue
            yield "data: [DONE]\n\n"
        return StreamingResponse(_agen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()}
        logger.error(f"Warp SSE forwarding endpoint error: {e}")
        raise HTTPException(500, detail=error_details)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json({"event": "connected", "message": "WebSocket connection established", "timestamp": datetime.now().isoformat()})
        recent_packets = manager.packet_history[-10:]
        for packet in recent_packets:
            await websocket.send_json({"event": "packet_history", "packet": packet})
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 