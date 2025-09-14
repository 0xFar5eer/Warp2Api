#!/usr/bin/env python3
"""
Test script to verify that proxy configuration is working correctly.
Tests that localhost connections bypass the proxy while external URLs use it.
"""

import asyncio
import os
import httpx
import requests
from protobuf2openai.proxy_utils import should_bypass_proxy, get_requests_proxies, get_httpx_trust_env


async def test_proxy_bypass():
    """Test that localhost URLs properly bypass proxy"""
    print("=" * 60)
    print("PROXY BYPASS TESTING")
    print("=" * 60)
    
    # Test URLs
    test_urls = [
        "http://localhost:8000/healthz",
        "http://127.0.0.1:8000/healthz",
        "http://0.0.0.0:8000/healthz",
        "http://host.docker.internal:8000/healthz",
        "https://app.warp.dev/graphql",
        "https://identitytoolkit.googleapis.com/v1/accounts",
    ]
    
    print("\n1. Testing should_bypass_proxy function:")
    print("-" * 40)
    for url in test_urls:
        bypass = should_bypass_proxy(url)
        print(f"  {url[:50]:<50} -> {'BYPASS' if bypass else 'USE PROXY'}")
    
    print("\n2. Testing requests proxy configuration:")
    print("-" * 40)
    for url in test_urls:
        proxies = get_requests_proxies(url)
        if proxies:
            print(f"  {url[:50]:<50} -> Proxy disabled")
        else:
            print(f"  {url[:50]:<50} -> Will use environment proxy")
    
    print("\n3. Testing httpx trust_env configuration:")
    print("-" * 40)
    for url in test_urls:
        trust_env = get_httpx_trust_env(url)
        print(f"  {url[:50]:<50} -> trust_env={trust_env}")
    
    print("\n4. Environment variables:")
    print("-" * 40)
    print(f"  HTTP_PROXY: {os.getenv('HTTP_PROXY', 'Not set')}")
    print(f"  NO_PROXY: {os.getenv('NO_PROXY', 'Not set')}")
    
    print("\n5. Testing actual HTTP connections:")
    print("-" * 40)
    
    # Test with httpx
    print("\n  Testing httpx connections:")
    for url in ["http://localhost:8000/healthz", "http://127.0.0.1:8000/healthz"]:
        try:
            async with httpx.AsyncClient(trust_env=get_httpx_trust_env(url), timeout=2.0) as client:
                response = await client.get(url)
                print(f"    {url} -> Status {response.status_code}")
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "Forbidden" in error_msg:
                print(f"    {url} -> ❌ PROXY ERROR (403 Forbidden)")
            else:
                print(f"    {url} -> Connection failed: {error_msg[:50]}")
    
    # Test with requests
    print("\n  Testing requests connections:")
    for url in ["http://localhost:8000/healthz", "http://127.0.0.1:8000/healthz"]:
        try:
            proxies = get_requests_proxies(url)
            response = requests.get(url, proxies=proxies, timeout=2.0)
            print(f"    {url} -> Status {response.status_code}")
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "Forbidden" in error_msg:
                print(f"    {url} -> ❌ PROXY ERROR (403 Forbidden)")
            else:
                print(f"    {url} -> Connection failed: {error_msg[:50]}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\nSummary:")
    print("- Localhost URLs should show 'BYPASS' and 'Proxy disabled'")
    print("- External URLs should show 'USE PROXY' and 'Will use environment proxy'")
    print("- If you see '403 Forbidden' errors, the proxy is incorrectly being used for localhost")
    print("- Connection failures are expected if servers aren't running")


if __name__ == "__main__":
    # Set test environment variables
    # Load proxy from environment variables or construct from components
    if not os.getenv("HTTP_PROXY"):
        user = os.getenv("PROXY_USER", "")
        password = os.getenv("PROXY_PASS", "")
        host = os.getenv("PROXY_HOST", "")
        port = os.getenv("PROXY_PORT", "")
        
        if all([user, password, host, port]):
            os.environ["HTTP_PROXY"] = f"http://{user}:{password}@{host}:{port}"
        else:
            print("Warning: HTTP_PROXY not configured and proxy components not found in environment")
    if not os.getenv("NO_PROXY"):
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,0.0.0.0,host.docker.internal,::1"
    
    asyncio.run(test_proxy_bypass())