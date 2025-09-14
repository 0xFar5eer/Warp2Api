#!/usr/bin/env python3
"""
Test script to verify the server can handle concurrent connections.
Tests both the Protobuf API (port 4009) and OpenAI API (port 4010).
"""

import asyncio
import aiohttp
import time
import json
from typing import List, Tuple
import sys

# Configuration
PROTOBUF_URL = "http://localhost:4009"
OPENAI_URL = "http://localhost:4010"
CONCURRENT_REQUESTS = 20  # Number of concurrent requests to test
TOTAL_REQUESTS = 100  # Total number of requests to send


async def test_protobuf_endpoint(session: aiohttp.ClientSession, request_id: int) -> Tuple[int, float]:
    """Test a single request to the Protobuf API."""
    start_time = time.time()
    try:
        # Test the healthz endpoint (simple and fast)
        async with session.get(f"{PROTOBUF_URL}/healthz") as response:
            elapsed = time.time() - start_time
            return response.status, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"Request {request_id} failed: {e}")
        return 0, elapsed


async def test_openai_endpoint(session: aiohttp.ClientSession, request_id: int) -> Tuple[int, float]:
    """Test a single request to the OpenAI API."""
    start_time = time.time()
    try:
        # Test the models endpoint
        async with session.get(f"{OPENAI_URL}/v1/models") as response:
            elapsed = time.time() - start_time
            return response.status, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"Request {request_id} failed: {e}")
        return 0, elapsed


async def test_concurrent_load(test_func, url_type: str):
    """Test concurrent load on an endpoint."""
    print(f"\n{'='*60}")
    print(f"Testing {url_type} with {CONCURRENT_REQUESTS} concurrent connections")
    print(f"{'='*60}")
    
    # Create session with connection pool
    connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS, limit_per_host=CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Warm up with a single request
        print("Warming up...")
        await test_func(session, 0)
        
        # Test concurrent requests
        print(f"Sending {TOTAL_REQUESTS} requests with {CONCURRENT_REQUESTS} concurrent...")
        
        all_results = []
        start_time = time.time()
        
        # Process requests in batches
        for batch_start in range(0, TOTAL_REQUESTS, CONCURRENT_REQUESTS):
            batch_end = min(batch_start + CONCURRENT_REQUESTS, TOTAL_REQUESTS)
            batch_tasks = [
                test_func(session, i) 
                for i in range(batch_start, batch_end)
            ]
            
            # Execute batch concurrently
            batch_results = await asyncio.gather(*batch_tasks)
            all_results.extend(batch_results)
            
            # Small delay between batches to prevent overwhelming
            if batch_end < TOTAL_REQUESTS:
                await asyncio.sleep(0.1)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful = sum(1 for status, _ in all_results if status == 200)
        failed = sum(1 for status, _ in all_results if status == 0)
        other_errors = sum(1 for status, _ in all_results if status not in [200, 0])
        
        response_times = [elapsed for _, elapsed in all_results if elapsed > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        min_response_time = min(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        
        # Print results
        print(f"\n📊 Results for {url_type}:")
        print(f"  Total Requests: {TOTAL_REQUESTS}")
        print(f"  Successful (200): {successful}")
        print(f"  Failed (connection error): {failed}")
        print(f"  Other HTTP errors: {other_errors}")
        print(f"  Success Rate: {(successful/TOTAL_REQUESTS)*100:.1f}%")
        print(f"\n⏱️  Performance:")
        print(f"  Total Time: {total_time:.2f} seconds")
        print(f"  Requests/second: {TOTAL_REQUESTS/total_time:.1f}")
        print(f"  Avg Response Time: {avg_response_time*1000:.1f}ms")
        print(f"  Min Response Time: {min_response_time*1000:.1f}ms")
        print(f"  Max Response Time: {max_response_time*1000:.1f}ms")
        
        # Test verdict
        if successful >= TOTAL_REQUESTS * 0.95:  # 95% success rate
            print(f"\n✅ {url_type} PASSED: Can handle {CONCURRENT_REQUESTS} concurrent connections!")
            return True
        else:
            print(f"\n❌ {url_type} FAILED: Could not handle {CONCURRENT_REQUESTS} concurrent connections reliably")
            return False


async def stress_test_complex_endpoint():
    """Test a more complex endpoint with actual data processing."""
    print(f"\n{'='*60}")
    print(f"Stress testing complex endpoint with {CONCURRENT_REQUESTS} concurrent connections")
    print(f"{'='*60}")
    
    connector = aiohttp.TCPConnector(limit=CONCURRENT_REQUESTS, limit_per_host=CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        
        async def complex_request(request_id: int) -> Tuple[int, float]:
            """Send a complex request that requires actual processing."""
            start_time = time.time()
            try:
                # Test the encode endpoint with actual data
                data = {
                    "json_data": {
                        "input": {
                            "input_type": "text_input",
                            "text_input": {
                                "input_text": f"Test request {request_id}"
                            }
                        },
                        "settings": {
                            "model_config": {
                                "base": "test-model"
                            }
                        }
                    }
                }
                
                async with session.post(
                    f"{PROTOBUF_URL}/api/encode",
                    json=data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    elapsed = time.time() - start_time
                    return response.status, elapsed
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"Complex request {request_id} failed: {e}")
                return 0, elapsed
        
        print("Testing complex endpoint processing...")
        
        all_results = []
        start_time = time.time()
        
        # Send 50 complex requests with concurrency
        for batch_start in range(0, 50, CONCURRENT_REQUESTS):
            batch_end = min(batch_start + CONCURRENT_REQUESTS, 50)
            batch_tasks = [
                complex_request(i) 
                for i in range(batch_start, batch_end)
            ]
            
            batch_results = await asyncio.gather(*batch_tasks)
            all_results.extend(batch_results)
            
            if batch_end < 50:
                await asyncio.sleep(0.2)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful = sum(1 for status, _ in all_results if status in [200, 400])  # 400 is expected for test data
        response_times = [elapsed for _, elapsed in all_results if elapsed > 0]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        print(f"\n📊 Complex Endpoint Results:")
        print(f"  Total Requests: {len(all_results)}")
        print(f"  Successful: {successful}")
        print(f"  Success Rate: {(successful/len(all_results))*100:.1f}%")
        print(f"  Avg Response Time: {avg_response_time*1000:.1f}ms")
        print(f"  Requests/second: {len(all_results)/total_time:.1f}")
        
        if successful >= len(all_results) * 0.90:  # 90% success rate for complex operations
            print(f"\n✅ Complex endpoint PASSED concurrent load test!")
            return True
        else:
            print(f"\n❌ Complex endpoint FAILED concurrent load test")
            return False


async def main():
    """Main test function."""
    print("🚀 Starting Concurrent Connection Test")
    print(f"   Testing with {CONCURRENT_REQUESTS} concurrent connections")
    print(f"   Total requests per test: {TOTAL_REQUESTS}")
    
    # Check if servers are running
    print("\n🔍 Checking server availability...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PROTOBUF_URL}/healthz") as resp:
                if resp.status != 200:
                    print(f"❌ Protobuf server not healthy (status: {resp.status})")
                    return 1
                print(f"✅ Protobuf server is running on port 4009")
            
            async with session.get(f"{OPENAI_URL}/healthz") as resp:
                if resp.status != 200:
                    print(f"❌ OpenAI server not healthy (status: {resp.status})")
                    return 1
                print(f"✅ OpenAI server is running on port 4010")
    except Exception as e:
        print(f"❌ Servers not available: {e}")
        print("Please ensure the servers are running (use ./start.sh or docker-compose up)")
        return 1
    
    # Run tests
    results = []
    
    # Test Protobuf API
    result = await test_concurrent_load(test_protobuf_endpoint, "Protobuf API (port 4009)")
    results.append(("Protobuf API", result))
    
    # Test OpenAI API
    result = await test_concurrent_load(test_openai_endpoint, "OpenAI API (port 4010)")
    results.append(("OpenAI API", result))
    
    # Test complex endpoint
    result = await stress_test_complex_endpoint()
    results.append(("Complex Endpoint", result))
    
    # Summary
    print(f"\n{'='*60}")
    print("📋 TEST SUMMARY")
    print(f"{'='*60}")
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print(f"\n🎉 All tests passed! The server can handle {CONCURRENT_REQUESTS}+ concurrent connections.")
        return 0
    else:
        print(f"\n⚠️  Some tests failed. The server may need optimization for high concurrency.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)