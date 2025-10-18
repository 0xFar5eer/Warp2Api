#!/usr/bin/env python3
"""Test intercept server response to understand the protocol issue"""
import requests

# Disable SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://app.warp.dev/ai/multi-agent"
headers = {
    "accept": "text/event-stream",
    "content-type": "application/x-protobuf",
    "authorization": "Bearer dummy-token-will-be-replaced",
    "x-warp-client-version": "v0.2025.09.24.08.11.stable_00",
    "x-warp-os-category": "Windows",
    "x-warp-os-name": "Windows",
    "x-warp-os-version": "11 (26100)",
}

# Minimal protobuf data (invalid but just for testing connection)
data = b"\x00" * 100

print(f"Testing intercept server at: {url}")
print(f"Request headers: {headers}")
print(f"Data size: {len(data)} bytes")
print()

try:
    response = requests.post(
        url,
        headers=headers,
        data=data,
        verify=False,
        stream=True,
        timeout=10
    )
    print(f"✅ Response status: {response.status_code}")
    print(f"Response headers:")
    for key, value in response.headers.items():
        print(f"  {key}: {value}")
    print()
    
    if response.status_code == 200:
        print("Response content (first 500 bytes):")
        print(response.content[:500])
    else:
        print("Error response:")
        print(response.text[:500])
        
except Exception as e:
    print(f"❌ Request failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
