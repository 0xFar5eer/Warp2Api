#!/usr/bin/env python3
"""Test script to verify proxy configuration is working"""

import asyncio
import os
import sys
sys.path.insert(0, '.')

from warp2protobuf.core.auth import get_proxy_config, refresh_jwt_token, acquire_anonymous_access_token
from warp2protobuf.core.logging import logger

async def test_proxy_config():
    """Test proxy configuration"""
    print("=" * 60)
    print("PROXY CONFIGURATION TEST")
    print("=" * 60)
    
    # Test 1: Check default proxy configuration
    print("\n1. Testing get_proxy_config():")
    config = get_proxy_config()
    print(f"   Proxy configured: {'proxy' in config}")
    if 'proxy' in config:
        proxy_url = config['proxy']
        if '@' in proxy_url:
            parts = proxy_url.split('@')
            print(f"   Proxy URL: [CREDENTIALS]@{parts[-1]}")
        else:
            print(f"   Proxy URL: {proxy_url}")
    
    # Test 2: Check environment variable override
    print("\n2. Testing environment variable override:")
    original_proxy = os.environ.get('HTTP_PROXY')
    os.environ['HTTP_PROXY'] = 'http://test:test@example.com:8080'
    config_override = get_proxy_config()
    print(f"   Override successful: {config_override.get('proxy') == 'http://test:test@example.com:8080'}")
    
    # Restore original
    if original_proxy:
        os.environ['HTTP_PROXY'] = original_proxy
    else:
        os.environ.pop('HTTP_PROXY', None)
    
    # Test 3: Test actual HTTP request with proxy (dry run)
    print("\n3. Testing JWT refresh with proxy (dry run):")
    try:
        # This will attempt to refresh but may fail if no valid refresh token
        # The important part is that it uses the proxy
        result = await refresh_jwt_token()
        if result:
            print("   ✅ JWT refresh completed (token obtained)")
        else:
            print("   ⚠️  JWT refresh failed (expected if no valid refresh token)")
    except Exception as e:
        print(f"   ⚠️  Error during refresh: {str(e)[:100]}")
    
    print("\n" + "=" * 60)
    print("PROXY TEST COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_proxy_config())