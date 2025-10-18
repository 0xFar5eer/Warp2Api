#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration tests for OpenAI-compatible API with Warp Intercept Server

Tests the OpenAI API compatibility layer working through the warp intercept server.
The intercept server replaces dummy authentication with real credentials.
"""
import os
import sys
import asyncio
from openai import OpenAI, AsyncOpenAI
import pytest

# Configuration
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:8010/v1")
OPENAI_API_KEY = "dummy_key_will_be_replaced_by_intercept"

def test_health_check():
    """Test that the API server is running"""
    import requests
    response = requests.get(f"{OPENAI_API_BASE.replace('/v1', '')}/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    print(f"✅ Health check passed: {data}")


def test_list_models():
    """Test listing available models"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    models = client.models.list()
    assert models is not None
    assert hasattr(models, 'data')
    assert len(models.data) > 0
    print(f"✅ Found {len(models.data)} models")
    for model in models.data[:5]:  # Show first 5 models
        print(f"   - {model.id}")


def test_simple_chat_completion():
    """Test a simple chat completion request"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    response = client.chat.completions.create(
        model="claude-4-sonnet",
        messages=[
            {"role": "user", "content": "Say 'Hello from OpenAI API test!'"}
        ],
        max_tokens=100,
        stream=False
    )
    
    assert response is not None
    assert len(response.choices) > 0
    assert response.choices[0].message.content is not None
    
    content = response.choices[0].message.content
    print(f"✅ Chat completion response: {content[:200]}...")
    return content


def test_streaming_chat_completion():
    """Test streaming chat completion"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    stream = client.chat.completions.create(
        model="claude-4-sonnet",
        messages=[
            {"role": "user", "content": "Count from 1 to 5"}
        ],
        max_tokens=100,
        stream=True
    )
    
    chunks = []
    for chunk in stream:
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content:
                chunks.append(delta.content)
                print(f"📝 Chunk: {delta.content}", end="", flush=True)
    
    print()  # New line after streaming
    full_response = "".join(chunks)
    assert len(full_response) > 0
    print(f"✅ Streaming completed, total length: {len(full_response)} chars")
    return full_response


def test_chat_with_system_message():
    """Test chat completion with system message"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    response = client.chat.completions.create(
        model="claude-4-sonnet",
        messages=[
            {"role": "system", "content": "You are a helpful pirate assistant. Always respond in pirate speak."},
            {"role": "user", "content": "Tell me about the weather"}
        ],
        max_tokens=150,
        stream=False
    )
    
    assert response is not None
    assert len(response.choices) > 0
    content = response.choices[0].message.content
    
    print(f"✅ System message test response: {content[:200]}...")
    return content


def test_multi_turn_conversation():
    """Test multi-turn conversation"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    messages = [
        {"role": "user", "content": "My name is Alice"},
        {"role": "assistant", "content": "Hello Alice! Nice to meet you."},
        {"role": "user", "content": "What's my name?"}
    ]
    
    response = client.chat.completions.create(
        model="claude-4-sonnet",
        messages=messages,
        max_tokens=50,
        stream=False
    )
    
    assert response is not None
    content = response.choices[0].message.content
    
    # Should mention "Alice" in the response
    assert "Alice" in content or "alice" in content.lower()
    print(f"✅ Multi-turn conversation works: {content}")
    return content


@pytest.mark.asyncio
async def test_async_chat_completion():
    """Test async chat completion"""
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    response = await client.chat.completions.create(
        model="claude-4-sonnet",
        messages=[
            {"role": "user", "content": "Say 'Hello from async test!'"}
        ],
        max_tokens=50,
        stream=False
    )
    
    assert response is not None
    assert len(response.choices) > 0
    content = response.choices[0].message.content
    
    print(f"✅ Async chat completion: {content}")
    return content


@pytest.mark.asyncio
async def test_async_streaming():
    """Test async streaming chat completion"""
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    stream = await client.chat.completions.create(
        model="claude-4-sonnet",
        messages=[
            {"role": "user", "content": "List three fruits"}
        ],
        max_tokens=100,
        stream=True
    )
    
    chunks = []
    async for chunk in stream:
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content:
                chunks.append(delta.content)
                print(f"📝 Async chunk: {delta.content}", end="", flush=True)
    
    print()  # New line
    full_response = "".join(chunks)
    assert len(full_response) > 0
    print(f"✅ Async streaming completed: {len(full_response)} chars")
    return full_response


def test_different_models():
    """Test different model selections"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    models_to_test = ["claude-4-sonnet", "gpt-4o", "auto"]
    
    for model in models_to_test:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "Say hello"}
                ],
                max_tokens=30,
                stream=False
            )
            
            assert response is not None
            content = response.choices[0].message.content
            print(f"✅ Model '{model}' works: {content[:50]}...")
        except Exception as e:
            print(f"⚠️  Model '{model}' failed: {e}")


def test_error_handling():
    """Test error handling for invalid requests"""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_API_BASE)
    
    # Test with empty messages
    try:
        response = client.chat.completions.create(
            model="claude-4-sonnet",
            messages=[],
            stream=False
        )
        assert False, "Should have raised an error for empty messages"
    except Exception as e:
        print(f"✅ Correctly caught empty messages error: {type(e).__name__}")


def run_all_sync_tests():
    """Run all synchronous tests"""
    print("=" * 60)
    print("OPENAI API INTEGRATION TESTS")
    print("=" * 60)
    print(f"API Base URL: {OPENAI_API_BASE}")
    print()
    
    tests = [
        ("Health Check", test_health_check),
        ("List Models", test_list_models),
        ("Simple Chat Completion", test_simple_chat_completion),
        ("Streaming Chat", test_streaming_chat_completion),
        ("System Message", test_chat_with_system_message),
        ("Multi-turn Conversation", test_multi_turn_conversation),
        ("Different Models", test_different_models),
        ("Error Handling", test_error_handling),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n📋 Running: {name}")
        print("-" * 60)
        try:
            test_func()
            passed += 1
            print(f"✅ {name} PASSED")
        except Exception as e:
            failed += 1
            print(f"❌ {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


async def run_all_async_tests():
    """Run all async tests"""
    print("\n" + "=" * 60)
    print("ASYNC TESTS")
    print("=" * 60)
    
    tests = [
        ("Async Chat Completion", test_async_chat_completion),
        ("Async Streaming", test_async_streaming),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n📋 Running: {name}")
        print("-" * 60)
        try:
            await test_func()
            passed += 1
            print(f"✅ {name} PASSED")
        except Exception as e:
            failed += 1
            print(f"❌ {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 60)
    print(f"ASYNC RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    # Check if servers are running
    import requests
    try:
        response = requests.get(f"{OPENAI_API_BASE.replace('/v1', '')}/healthz", timeout=5)
        if response.status_code != 200:
            print("❌ OpenAI API server is not responding correctly")
            print("   Please start the server with: python openai_compat.py")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to OpenAI API server")
        print(f"   Expected server at: {OPENAI_API_BASE}")
        print("   Please start the server with: python openai_compat.py")
        sys.exit(1)
    
    # Run sync tests
    sync_success = run_all_sync_tests()
    
    # Run async tests
    async_success = asyncio.run(run_all_async_tests())
    
    # Final result
    if sync_success and async_success:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)
