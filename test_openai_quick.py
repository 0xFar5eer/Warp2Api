#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick test for OpenAI API compatibility

Simple test to verify the API is working with warp intercept server.
"""
import os
from openai import OpenAI

# Configuration
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:8010/v1")
OPENAI_API_KEY = "dummy_key_will_be_replaced_by_intercept"

def main():
    print("=" * 60)
    print("QUICK OPENAI API TEST")
    print("=" * 60)
    print(f"API Base: {OPENAI_API_BASE}")
    print(f"Using dummy API key (will be replaced by intercept server)")
    print()
    
    # Initialize client
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    # Test 1: Health check
    print("📋 Test 1: Health Check")
    import requests
    try:
        response = requests.get(f"{OPENAI_API_BASE.replace('/v1', '')}/healthz")
        if response.status_code == 200:
            print("✅ Server is healthy")
        else:
            print(f"❌ Server returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return False
    
    # Test 2: List models
    print("\n📋 Test 2: List Models")
    try:
        models = client.models.list()
        print(f"✅ Found {len(models.data)} models")
        print(f"   First model: {models.data[0].id if models.data else 'None'}")
    except Exception as e:
        print(f"❌ Failed to list models: {e}")
        return False
    
    # Test 3: Simple chat
    print("\n📋 Test 3: Simple Chat Completion")
    try:
        response = client.chat.completions.create(
            model="claude-4-sonnet",
            messages=[
                {"role": "user", "content": "Say 'Test successful!' in one sentence"}
            ],
            max_tokens=50,
            stream=False
        )
        
        content = response.choices[0].message.content
        print(f"✅ Response: {content}")
    except Exception as e:
        print(f"❌ Chat completion failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 4: Streaming
    print("\n📋 Test 4: Streaming Chat")
    try:
        stream = client.chat.completions.create(
            model="claude-4-sonnet",
            messages=[
                {"role": "user", "content": "Count to 3"}
            ],
            max_tokens=50,
            stream=True
        )
        
        print("Response: ", end="", flush=True)
        chunks = []
        for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    print(delta.content, end="", flush=True)
                    chunks.append(delta.content)
        
        print()
        if chunks:
            print(f"✅ Streaming works ({len(chunks)} chunks)")
        else:
            print("❌ No chunks received")
            return False
    except Exception as e:
        print(f"\n❌ Streaming failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 60)
    print("🎉 ALL QUICK TESTS PASSED!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
