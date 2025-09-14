#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Warp Protobuf Encoding/Decoding Server Startup File

Pure protobuf encoding/decoding server, providing JSON<->Protobuf conversion, WebSocket monitoring, and static file serving.
"""

from typing import Dict, Optional, Tuple
import base64
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi import Query, HTTPException
from fastapi.responses import Response

# Added: Type imports
from typing import Any

from warp2protobuf.api.protobuf_routes import app as protobuf_app
from warp2protobuf.core.logging import logger, set_log_file
from warp2protobuf.api.protobuf_routes import EncodeRequest, _encode_smd_inplace
from warp2protobuf.core.protobuf_utils import dict_to_protobuf_bytes
from warp2protobuf.core.schema_sanitizer import sanitize_mcp_input_schema_in_packet
from warp2protobuf.core.auth import acquire_anonymous_access_token
from warp2protobuf.config.models import get_all_unique_models


# ============= Tools: input_schema cleaning and validation =============


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def _deep_clean(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in value.items():
            vv = _deep_clean(v)
            if _is_empty_value(vv):
                continue
            cleaned[k] = vv
        return cleaned
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            ii = _deep_clean(item)
            if _is_empty_value(ii):
                continue
            cleaned_list.append(ii)
        return cleaned_list
    if isinstance(value, str):
        return value.strip()
    return value


def _infer_type_for_property(prop_name: str) -> str:
    name = prop_name.lower()
    if name in ("url", "uri", "href", "link"):
        return "string"
    if name in ("headers", "options", "params", "payload", "data"):
        return "object"
    return "string"


def _ensure_property_schema(name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    prop = dict(schema) if isinstance(schema, dict) else {}
    prop = _deep_clean(prop)

    # Required: type & description
    if (
        "type" not in prop
        or not isinstance(prop.get("type"), str)
        or not prop["type"].strip()
    ):
        prop["type"] = _infer_type_for_property(name)
    if (
        "description" not in prop
        or not isinstance(prop.get("description"), str)
        or not prop["description"].strip()
    ):
        prop["description"] = f"{name} parameter"

    # Special handling for headers: must be an object, and its properties cannot be empty
    if name.lower() == "headers":
        prop["type"] = "object"
        headers_props = prop.get("properties")
        if not isinstance(headers_props, dict):
            headers_props = {}
        headers_props = _deep_clean(headers_props)
        if not headers_props:
            headers_props = {
                "user-agent": {
                    "type": "string",
                    "description": "User-Agent header for the request",
                }
            }
        else:
            # Clean and ensure each header's sub-property has type/description
            fixed_headers: Dict[str, Any] = {}
            for hk, hv in headers_props.items():
                sub = _deep_clean(hv if isinstance(hv, dict) else {})
                if (
                    "type" not in sub
                    or not isinstance(sub.get("type"), str)
                    or not sub["type"].strip()
                ):
                    sub["type"] = "string"
                if (
                    "description" not in sub
                    or not isinstance(sub.get("description"), str)
                    or not sub["description"].strip()
                ):
                    sub["description"] = f"{hk} header"
                fixed_headers[hk] = sub
            headers_props = fixed_headers
        prop["properties"] = headers_props
        # Handle empty required arrays
        if isinstance(prop.get("required"), list):
            req = [
                r for r in prop["required"] if isinstance(r, str) and r in headers_props
            ]
            if req:
                prop["required"] = req
            else:
                prop.pop("required", None)
        # If additionalProperties is empty dict, delete it; keep explicit True/False
        if (
            isinstance(prop.get("additionalProperties"), dict)
            and len(prop["additionalProperties"]) == 0
        ):
            prop.pop("additionalProperties", None)

    return prop


def _sanitize_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    s = _deep_clean(schema if isinstance(schema, dict) else {})

    # If properties exist, top level should be object
    if "properties" in s and not isinstance(s.get("type"), str):
        s["type"] = "object"

    # Fix $schema
    if "$schema" in s and not isinstance(s["$schema"], str):
        s.pop("$schema", None)
    if "$schema" not in s:
        s["$schema"] = "http://json-schema.org/draft-07/schema#"

    properties = s.get("properties")
    if isinstance(properties, dict):
        fixed_props: Dict[str, Any] = {}
        for name, subschema in properties.items():
            fixed_props[name] = _ensure_property_schema(
                name, subschema if isinstance(subschema, dict) else {}
            )
        s["properties"] = fixed_props

    # required: remove non-existent properties, and don't allow empty lists
    if isinstance(s.get("required"), list):
        if isinstance(properties, dict):
            req = [r for r in s["required"] if isinstance(r, str) and r in properties]
        else:
            req = []
        if req:
            s["required"] = req
        else:
            s.pop("required", None)

    # additionalProperties: empty dict is considered invalid, delete it
    if (
        isinstance(s.get("additionalProperties"), dict)
        and len(s["additionalProperties"]) == 0
    ):
        s.pop("additionalProperties", None)

    return s


class _InputSchemaSanitizerMiddleware:  # deprecated; use sanitize_mcp_input_schema_in_packet in handlers
    pass


# ============= Application Creation =============


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Execute on startup
    await startup_tasks()
    yield
    # Execute on shutdown (if needed)
    pass


def create_app() -> FastAPI:
    """Create FastAPI application"""
    # Redirect server logs to dedicated file
    try:
        set_log_file("warp_server.log")
    except Exception:
        pass

    # Use protobuf routing application as main app, and add lifespan handler
    app = FastAPI(lifespan=lifespan)

    # Include protobuf routes into main application
    app.mount("/", protobuf_app)

    # Mount input schema cleaning middleware (override Warp related endpoints)

    # Check static files directory
    static_dir = Path("static")
    if static_dir.exists():
        # Mount static file service
        app.mount("/static", StaticFiles(directory="static"), name="static")
        logger.info("✅ Static file service enabled: /static")

        # Add root path redirect to frontend interface
        @app.get("/gui", response_class=HTMLResponse)
        async def serve_gui():
            """Serve frontend GUI interface"""
            index_file = static_dir / "index.html"
            if index_file.exists():
                return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
            else:
                return HTMLResponse(
                    content="""
                <html>
                    <body>
                        <h1>Frontend interface file not found</h1>
                        <p>Please ensure static/index.html file exists</p>
                    </body>
                </html>
                """
                )
    else:
        logger.warning("Static files directory does not exist, GUI interface will not be available")

        @app.get("/gui", response_class=HTMLResponse)
        async def no_gui():
            return HTMLResponse(
                content="""
            <html>
                <body>
                    <h1>GUI interface not installed</h1>
                    <p>Static file directory 'static' does not exist</p>
                    <p>Please create frontend interface files</p>
                </body>
            </html>
            """
            )

    # ============= New interface: Return protobuf-encoded AI request bytes =============
    @app.post("/api/warp/encode_raw")
    async def encode_ai_request_raw(
        request: EncodeRequest,
        output: str = Query(
            "raw",
            description="Output format: raw (default, returns application/x-protobuf bytes) or base64",
            regex=r"^(raw|base64)$",
        ),
    ):
        try:
            # Get actual data and validate
            actual_data = request.get_data()
            if not actual_data:
                raise HTTPException(400, "Data packet cannot be empty")

            # Before encoding, perform safety cleaning on mcp_context.tools[*].input_schema
            if isinstance(actual_data, dict):
                wrapped = {"json_data": actual_data}
                wrapped = sanitize_mcp_input_schema_in_packet(wrapped)
                actual_data = wrapped.get("json_data", actual_data)

            # Encode server_message_data object (if any) to Base64URL string
            actual_data = _encode_smd_inplace(actual_data)

            # Encode to protobuf bytes
            protobuf_bytes = dict_to_protobuf_bytes(actual_data, request.message_type)
            logger.info(f"✅ AI request encoded to protobuf successfully: {len(protobuf_bytes)} bytes")

            if output == "raw":
                # Return binary protobuf content directly
                return Response(
                    content=protobuf_bytes,
                    media_type="application/x-protobuf",
                    headers={"Content-Length": str(len(protobuf_bytes))},
                )
            else:
                # Return base64 text for easy transmission/debugging in JSON
                import base64

                return {
                    "protobuf_base64": base64.b64encode(protobuf_bytes).decode("utf-8"),
                    "size": len(protobuf_bytes),
                    "message_type": request.message_type,
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ AI request encoding failed: {e}")
            raise HTTPException(500, f"Encoding failed: {str(e)}")

    # ============= OpenAI compatible: Model list interface =============
    @app.get("/v1/models")
    async def list_models():
        """OpenAI-compatible endpoint that lists available models."""
        try:
            models = get_all_unique_models()
            return {"object": "list", "data": models}
        except Exception as e:
            logger.error(f"❌ Failed to get model list: {e}")
            raise HTTPException(500, f"Failed to get model list: {str(e)}")

    return app


############################################################
# server_message_data deep encoding/decoding tools
############################################################

# Description:
# According to packet capture and analysis, server_message_data is a Base64URL encoded proto3 message:
#   - Field 1: string (usually 36 byte UUID)
#   - Field 3: google.protobuf.Timestamp (field 1=seconds, field 2=nanos)
# May appear as: Timestamp only, UUID only, or UUID + Timestamp.

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None  # type: ignore


def _b64url_decode_padded(s: str) -> bytes:
    t = s.replace("-", "+").replace("_", "/")
    pad = (-len(t)) % 4
    if pad:
        t += "=" * pad
    return base64.b64decode(t)


def _b64url_encode_nopad(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _read_varint(buf: bytes, i: int) -> Tuple[int, int]:
    shift = 0
    val = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, i
        shift += 7
        if shift > 63:
            break
    raise ValueError("invalid varint")


def _write_varint(v: int) -> bytes:
    out = bytearray()
    vv = int(v)
    while True:
        to_write = vv & 0x7F
        vv >>= 7
        if vv:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            break
    return bytes(out)


def _make_key(field_no: int, wire_type: int) -> bytes:
    return _write_varint((field_no << 3) | wire_type)


def _decode_timestamp(buf: bytes) -> Tuple[Optional[int], Optional[int]]:
    # google.protobuf.Timestamp: field 1 = seconds (int64 varint), field 2 = nanos (int32 varint)
    i = 0
    seconds: Optional[int] = None
    nanos: Optional[int] = None
    while i < len(buf):
        key, i = _read_varint(buf, i)
        field_no = key >> 3
        wt = key & 0x07
        if wt == 0:  # varint
            val, i = _read_varint(buf, i)
            if field_no == 1:
                seconds = int(val)
            elif field_no == 2:
                nanos = int(val)
        elif wt == 2:  # length-delimited (not expected inside Timestamp)
            ln, i2 = _read_varint(buf, i)
            i = i2 + ln
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
        else:
            break
    return seconds, nanos


def _encode_timestamp(seconds: Optional[int], nanos: Optional[int]) -> bytes:
    parts = bytearray()
    if seconds is not None:
        parts += _make_key(1, 0)  # field 1, varint
        parts += _write_varint(int(seconds))
    if nanos is not None:
        parts += _make_key(2, 0)  # field 2, varint
        parts += _write_varint(int(nanos))
    return bytes(parts)


def decode_server_message_data(b64url: str) -> Dict:
    """Decode Base64URL server_message_data, return structured information."""
    try:
        raw = _b64url_decode_padded(b64url)
    except Exception as e:
        return {"error": f"base64url decode failed: {e}", "raw_b64url": b64url}

    i = 0
    uuid: Optional[str] = None
    seconds: Optional[int] = None
    nanos: Optional[int] = None

    while i < len(raw):
        key, i = _read_varint(raw, i)
        field_no = key >> 3
        wt = key & 0x07
        if wt == 2:  # length-delimited
            ln, i2 = _read_varint(raw, i)
            i = i2
            data = raw[i : i + ln]
            i += ln
            if field_no == 1:  # uuid string
                try:
                    uuid = data.decode("utf-8")
                except Exception:
                    uuid = None
            elif field_no == 3:  # google.protobuf.Timestamp
                seconds, nanos = _decode_timestamp(data)
        elif wt == 0:  # varint -> not expected, skip
            _, i = _read_varint(raw, i)
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
        else:
            break

    out: Dict[str, Any] = {}
    if uuid is not None:
        out["uuid"] = uuid
    if seconds is not None:
        out["seconds"] = seconds
    if nanos is not None:
        out["nanos"] = nanos
    return out


def encode_server_message_data(
    uuid: Optional[str] = None,
    seconds: Optional[int] = None,
    nanos: Optional[int] = None,
) -> str:
    """Encode uuid/seconds/nanos combination as Base64URL string."""
    parts = bytearray()
    if uuid:
        b = uuid.encode("utf-8")
        parts += _make_key(1, 2)  # field 1, length-delimited
        parts += _write_varint(len(b))
        parts += b

    if seconds is not None or nanos is not None:
        ts = _encode_timestamp(seconds, nanos)
        parts += _make_key(3, 2)  # field 3, length-delimited
        parts += _write_varint(len(ts))
        parts += ts

    return _b64url_encode_nopad(bytes(parts))


async def startup_tasks():
    """Tasks to execute on startup"""
    logger.info("=" * 60)
    logger.info("Warp Protobuf Encoding/Decoding Server Starting")
    logger.info("=" * 60)

    # Check protobuf runtime
    try:
        from warp2protobuf.core.protobuf import ensure_proto_runtime

        ensure_proto_runtime()
        logger.info("✅ Protobuf runtime initialized successfully")
    except Exception as e:
        logger.error(f"❌ Protobuf runtime initialization failed: {e}")
        raise

    # Check JWT token
    try:
        from warp2protobuf.core.auth import get_jwt_token, is_token_expired

        token = get_jwt_token()
        if token and not is_token_expired(token):
            logger.info("✅ JWT token is valid")
        elif not token:
            logger.warning("⚠️ JWT token not found, attempting to acquire anonymous access token for quota initialization...")
            try:
                new_token = await acquire_anonymous_access_token()
                if new_token:
                    logger.info("✅ Anonymous access token acquired successfully")
                else:
                    logger.warning("⚠️ Anonymous access token acquisition failed")
            except Exception as e2:
                logger.warning(f"⚠️ Anonymous access token acquisition exception: {e2}")
        else:
            logger.warning("⚠️ JWT token invalid or expired, suggest running: uv run refresh_jwt.py")
    except Exception as e:
        logger.warning(f"⚠️ JWT check failed: {e}")

    # If OpenAI compatibility layer is needed, run src/openai_compat_server.py separately

    # Display available endpoints
    logger.info("-" * 40)
    logger.info("Available API endpoints:")
    logger.info("  GET  /                   - Service information")
    logger.info("  GET  /healthz            - Health check")
    logger.info("  GET  /gui                - Web GUI interface")
    logger.info("  POST /api/encode         - JSON -> Protobuf encoding")
    logger.info("  POST /api/decode         - Protobuf -> JSON decoding")
    logger.info("  POST /api/stream-decode  - Stream protobuf decoding")
    logger.info("  POST /api/warp/send      - JSON -> Protobuf -> Warp API forward")
    logger.info(
        "  POST /api/warp/send_stream - JSON -> Protobuf -> Warp API forward (return parsed events)"
    )
    logger.info(
        "  POST /api/warp/send_stream_sse - JSON -> Protobuf -> Warp API forward (real-time SSE, events parsed)"
    )
    logger.info("  POST /api/warp/graphql/* - GraphQL request forward to Warp API (with auth)")
    logger.info("  GET  /api/schemas        - Protobuf schema information")
    logger.info("  GET  /api/auth/status    - JWT authentication status")
    logger.info("  POST /api/auth/refresh   - Refresh JWT token")
    logger.info("  GET  /api/auth/user_id   - Get current user ID")
    logger.info("  GET  /api/packets/history - Packet history records")
    logger.info("  WS   /ws                 - WebSocket real-time monitoring")
    logger.info("-" * 40)
    logger.info("Test commands:")
    logger.info("  uv run main.py --test basic    - Run basic tests")
    logger.info("  uv run main.py --list          - View all test scenarios")
    logger.info("=" * 60)


def main():
    """Main function"""
    # Create application
    app = create_app()

    # Start server
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info", access_log=True)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server startup failed: {e}")
        raise


if __name__ == "__main__":
    main()
