from __future__ import annotations
import asyncio
import os
import threading
import time
import httpx
from protobuf2openai.app import app as openai_server  # FastAPI app
from server import create_app, startup_tasks
import uvicorn


async def wait_for_protobuf_server(max_retries=30, delay=0.5):
    """Wait for the protobuf server to be ready"""
    import logging
    logger = logging.getLogger("startup")
    
    for attempt in range(max_retries):
        try:
            # Don't use proxy for localhost connections
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                response = await client.get("http://localhost:8000/healthz")
                if response.status_code == 200:
                    logger.info(f"✅ Protobuf server is ready after {attempt + 1} attempts")
                    return True
        except Exception:
            pass
        
        if attempt < max_retries - 1:
            await asyncio.sleep(delay)
    
    logger.error(f"❌ Protobuf server failed to start after {max_retries} attempts")
    return False


async def main():
    # Start warp server in background thread
    warp_app = create_app()
    await startup_tasks()
    
    # Start the warp server background thread
    warp_thread = threading.Thread(
        target=uvicorn.run,
        args=(warp_app,),
        kwargs={"host": "0.0.0.0", "port": 8000, "log_level": "info", "access_log": True},
        daemon=True
    )
    warp_thread.start()
    
    # Wait for protobuf server to be ready
    await wait_for_protobuf_server()
    
    try:
        from warp2protobuf.core.auth import refresh_jwt_if_needed as _refresh_jwt
        await _refresh_jwt()
    except Exception:
        pass
    

if __name__ == "__main__":
    asyncio.run(main())
    uvicorn.run(
        openai_server,
        host=os.getenv("HOST", "0.0.0.0"),  # Changed to 0.0.0.0 to match container setup
        port=int(os.getenv("PORT", "8010")),
        log_level="info",
    )