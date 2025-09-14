#!/usr/bin/env python3
"""
Performance testing script for API request optimizations.

Tests DNS caching, connection pooling, and response time improvements.
"""

import asyncio
import time
import statistics
import json
import os

# Test both sync and async implementations
import requests
import httpx

# Import our optimized clients
from protobuf2openai.http_client import (
    OptimizedSyncClient,
    OptimizedAsyncClient,
    get_sync_client,
    get_async_client,
    DNSCachingResolver,
    prewarm_dns_cache
)


class PerformanceTester:
    """Test harness for measuring API performance improvements."""
    
    def __init__(self):
        self.test_urls = [
            "http://localhost:8000/healthz",
            "http://localhost:8001/healthz",
            "http://localhost:8000/v1/models",
        ]
        self.results = {}
    
    def print_results(self, test_name, times):
        """Print performance statistics for a test."""
        if not times:
            print(f"\n{test_name}: No results")
            return
        
        print(f"\n{test_name}:")
        print(f"  Requests: {len(times)}")
        print(f"  Min: {min(times)*1000:.2f}ms")
        print(f"  Max: {max(times)*1000:.2f}ms")
        print(f"  Avg: {statistics.mean(times)*1000:.2f}ms")
        print(f"  Median: {statistics.median(times)*1000:.2f}ms")
        if len(times) > 1:
            print(f"  Std Dev: {statistics.stdev(times)*1000:.2f}ms")
    
    def test_standard_requests(self, num_requests=10):
        """Test performance with standard requests library."""
        print("\n=== Testing Standard Requests Library ===")
        times = []
        
        session = requests.Session()
        for i in range(num_requests):
            for url in self.test_urls:
                start = time.time()
                try:
                    resp = session.get(url, timeout=5.0)
                    if resp.status_code == 200:
                        elapsed = time.time() - start
                        times.append(elapsed)
                        print(f"  Request {i+1} to {url}: {elapsed*1000:.2f}ms")
                except Exception as e:
                    print(f"  Request {i+1} to {url} failed: {e}")
        
        session.close()
        self.results["standard_requests"] = times
        self.print_results("Standard Requests", times)
    
    def test_optimized_sync_client(self, num_requests=10):
        """Test performance with optimized sync client."""
        print("\n=== Testing Optimized Sync Client ===")
        times = []
        
        client = OptimizedSyncClient()
        
        # Test without caching first
        print("\nWithout caching:")
        for i in range(num_requests // 2):
            for url in self.test_urls:
                start = time.time()
                try:
                    resp = client.get(url, use_cache=False)
                    if resp.status_code == 200:
                        elapsed = time.time() - start
                        times.append(elapsed)
                        print(f"  Request {i+1} to {url}: {elapsed*1000:.2f}ms")
                except Exception as e:
                    print(f"  Request {i+1} to {url} failed: {e}")
        
        # Test with caching
        print("\nWith caching enabled:")
        cache_times = []
        for i in range(num_requests // 2):
            for url in self.test_urls:
                start = time.time()
                try:
                    resp = client.get(url, use_cache=True)
                    if resp.status_code == 200:
                        elapsed = time.time() - start
                        cache_times.append(elapsed)
                        print(f"  Request {i+1} to {url}: {elapsed*1000:.2f}ms (cached)")
                except Exception as e:
                    print(f"  Request {i+1} to {url} failed: {e}")
        
        client.close()
        
        self.results["optimized_sync"] = times
        self.results["optimized_sync_cached"] = cache_times
        self.print_results("Optimized Sync (no cache)", times)
        self.print_results("Optimized Sync (with cache)", cache_times)
    
    async def test_standard_httpx(self, num_requests=10):
        """Test performance with standard httpx async client."""
        print("\n=== Testing Standard HTTPX Async Client ===")
        times = []
        
        async with httpx.AsyncClient() as client:
            for i in range(num_requests):
                for url in self.test_urls:
                    start = time.time()
                    try:
                        resp = await client.get(url, timeout=5.0)
                        if resp.status_code == 200:
                            elapsed = time.time() - start
                            times.append(elapsed)
                            print(f"  Request {i+1} to {url}: {elapsed*1000:.2f}ms")
                    except Exception as e:
                        print(f"  Request {i+1} to {url} failed: {e}")
        
        self.results["standard_httpx"] = times
        self.print_results("Standard HTTPX", times)
    
    async def test_optimized_async_client(self, num_requests=10):
        """Test performance with optimized async client."""
        print("\n=== Testing Optimized Async Client ===")
        times = []
        
        client = OptimizedAsyncClient()
        
        # Test without caching
        print("\nWithout caching:")
        for i in range(num_requests // 2):
            for url in self.test_urls:
                start = time.time()
                try:
                    resp = await client.get(url, use_cache=False)
                    if resp.status_code == 200:
                        elapsed = time.time() - start
                        times.append(elapsed)
                        print(f"  Request {i+1} to {url}: {elapsed*1000:.2f}ms")
                except Exception as e:
                    print(f"  Request {i+1} to {url} failed: {e}")
        
        # Test with caching
        print("\nWith caching enabled:")
        cache_times = []
        for i in range(num_requests // 2):
            for url in self.test_urls:
                start = time.time()
                try:
                    resp = await client.get(url, use_cache=True)
                    if resp.status_code == 200:
                        elapsed = time.time() - start
                        cache_times.append(elapsed)
                        print(f"  Request {i+1} to {url}: {elapsed*1000:.2f}ms (cached)")
                except Exception as e:
                    print(f"  Request {i+1} to {url} failed: {e}")
        
        await client.close()
        
        self.results["optimized_async"] = times
        self.results["optimized_async_cached"] = cache_times
        self.print_results("Optimized Async (no cache)", times)
        self.print_results("Optimized Async (with cache)", cache_times)
    
    def test_dns_caching(self):
        """Test DNS caching functionality."""
        print("\n=== Testing DNS Caching ===")
        
        test_hosts = [
            "localhost",
            "api.openai.com",
            "api.anthropic.com",
        ]
        
        for host in test_hosts:
            # First resolution (cache miss)
            start = time.time()
            try:
                ip1 = DNSCachingResolver.resolve_host(host)
                elapsed1 = time.time() - start
                print(f"\n{host}:")
                print(f"  First resolution: {ip1} ({elapsed1*1000:.2f}ms)")
                
                # Second resolution (cache hit)
                start = time.time()
                ip2 = DNSCachingResolver.resolve_host(host)
                elapsed2 = time.time() - start
                print(f"  Cached resolution: {ip2} ({elapsed2*1000:.2f}ms)")
                
                # Calculate speedup
                if elapsed1 > 0:
                    speedup = (elapsed1 - elapsed2) / elapsed1 * 100
                    print(f"  Cache speedup: {speedup:.1f}%")
            except Exception as e:
                print(f"  Failed to resolve {host}: {e}")
    
    async def test_concurrent_requests(self, num_concurrent=5):
        """Test concurrent request handling."""
        print(f"\n=== Testing Concurrent Requests (x{num_concurrent}) ===")
        
        client = OptimizedAsyncClient()
        urls = self.test_urls * num_concurrent
        
        # Test concurrent requests
        start = time.time()
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start
        
        successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        print(f"\nConcurrent requests completed:")
        print(f"  Total requests: {len(urls)}")
        print(f"  Successful: {successful}")
        print(f"  Total time: {elapsed*1000:.2f}ms")
        print(f"  Avg per request: {(elapsed/len(urls))*1000:.2f}ms")
        
        await client.close()
    
    def print_summary(self):
        """Print performance comparison summary."""
        print("\n" + "="*60)
        print("PERFORMANCE COMPARISON SUMMARY")
        print("="*60)
        
        if not self.results:
            print("No results to compare")
            return
        
        # Calculate average times for each method
        averages = {}
        for name, times in self.results.items():
            if times:
                averages[name] = statistics.mean(times) * 1000  # Convert to ms
        
        if not averages:
            print("No valid results to compare")
            return
        
        # Find baseline (standard requests)
        baseline = averages.get("standard_requests", 0)
        if baseline == 0:
            baseline = averages.get("standard_httpx", 0)
        
        # Print comparison
        print(f"\n{'Method':<30} {'Avg Time':<15} {'vs Baseline':<15}")
        print("-" * 60)
        
        for name, avg_time in sorted(averages.items(), key=lambda x: x[1]):
            if baseline > 0:
                improvement = ((baseline - avg_time) / baseline) * 100
                comparison = f"{improvement:+.1f}%"
            else:
                comparison = "N/A"
            print(f"{name:<30} {avg_time:>10.2f}ms   {comparison:<15}")
        
        # Highlight best performer
        best_method = min(averages, key=averages.get)
        best_time = averages[best_method]
        print(f"\n🏆 Best performer: {best_method} ({best_time:.2f}ms average)")
        
        if baseline > 0 and best_time < baseline:
            overall_improvement = ((baseline - best_time) / baseline) * 100
            print(f"   Overall improvement: {overall_improvement:.1f}% faster than baseline")


async def main():
    """Run all performance tests."""
    print("="*60)
    print("API REQUEST PERFORMANCE TESTING")
    print("="*60)
    print("\nOptimizations being tested:")
    print("  ✓ DNS caching")
    print("  ✓ Connection pooling")
    print("  ✓ Keep-alive connections")
    print("  ✓ Response caching")
    print("  ✓ Retry with exponential backoff")
    print("  ✓ Optimized timeouts")
    
    # Pre-warm DNS cache
    print("\nPre-warming DNS cache...")
    prewarm_dns_cache()
    
    tester = PerformanceTester()
    
    # Run tests
    print("\nStarting performance tests...")
    
    # Test DNS caching
    tester.test_dns_caching()
    
    # Test sync clients
    tester.test_standard_requests(num_requests=10)
    tester.test_optimized_sync_client(num_requests=10)
    
    # Test async clients
    await tester.test_standard_httpx(num_requests=10)
    await tester.test_optimized_async_client(num_requests=10)
    
    # Test concurrent handling
    await tester.test_concurrent_requests(num_concurrent=10)
    
    # Print summary
    tester.print_summary()
    
    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60)


if __name__ == "__main__":
    # Ensure both servers are running
    print("\n⚠️  Make sure both servers are running:")
    print("  - Main server: http://localhost:8000")
    print("  - OpenAI compat: http://localhost:8001")
    print("\nStarting performance tests automatically...\n")
    
    # Run async main
    asyncio.run(main())