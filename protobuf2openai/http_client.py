"""
Optimized HTTP client module with DNS caching, connection pooling, and performance improvements.

This module provides high-performance HTTP client functionality for API requests with:
- DNS caching to reduce lookup times
- Connection pooling and keep-alive
- Retry logic with exponential backoff
- Request/response caching
- Optimized timeout configurations
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import time
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlparse

import httpx
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .logger_config import logger


# DNS Cache configuration
DNS_CACHE_TTL = 300  # 5 minutes
dns_cache: Dict[str, Tuple[str, float]] = {}


class DNSCachingResolver:
    """Custom DNS resolver with caching support."""
    
    @staticmethod
    def resolve_host(hostname: str) -> str:
        """Resolve hostname with caching."""
        current_time = time.time()
        
        # Check cache
        if hostname in dns_cache:
            ip, timestamp = dns_cache[hostname]
            if current_time - timestamp < DNS_CACHE_TTL:
                logger.debug(f"DNS cache hit for {hostname}: {ip}")
                return ip
        
        # Perform DNS lookup
        try:
            ip = socket.gethostbyname(hostname)
            dns_cache[hostname] = (ip, current_time)
            logger.debug(f"DNS resolved {hostname} to {ip}")
            return ip
        except socket.gaierror as e:
            logger.error(f"DNS resolution failed for {hostname}: {e}")
            raise


class OptimizedHTTPAdapter(HTTPAdapter):
    """Custom HTTP adapter with optimized settings."""
    
    def __init__(self, *args, **kwargs):
        # Set connection pool size and retry configuration
        self.max_retries = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        super().__init__(*args, **kwargs)
    
    def init_poolmanager(self, *args, **kwargs):
        """Initialize pool manager with custom settings."""
        kwargs["socket_options"] = [
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
            (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 120),
            (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30),
            (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 8)
        ] if hasattr(socket, "TCP_KEEPIDLE") else []
        return super().init_poolmanager(*args, **kwargs)


class OptimizedSyncClient:
    """Optimized synchronous HTTP client with connection pooling and caching."""
    
    def __init__(self, 
                 pool_connections: int = 10,
                 pool_maxsize: int = 100,
                 max_retries: int = 3,
                 timeout: Tuple[float, float] = (5.0, 180.0)):
        """
        Initialize optimized sync client.
        
        Args:
            pool_connections: Number of connection pools to cache
            pool_maxsize: Maximum number of connections to save in the pool
            max_retries: Maximum number of retries for failed requests
            timeout: Tuple of (connect_timeout, read_timeout)
        """
        self.session = requests.Session()
        self.timeout = timeout
        
        # Configure optimized adapter
        adapter = OptimizedHTTPAdapter(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=max_retries
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set keep-alive headers
        self.session.headers.update({
            "Connection": "keep-alive",
            "Keep-Alive": "timeout=120, max=1000"
        })
        
        # Response cache for GET requests
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._cache_ttl = 60  # 1 minute cache TTL
    
    def _get_cache_key(self, method: str, url: str, **kwargs) -> str:
        """Generate cache key for request."""
        cache_data = {
            "method": method,
            "url": url,
            "headers": kwargs.get("headers", {}),
            "params": kwargs.get("params", {}),
            "json": kwargs.get("json", {})
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        """Check if cached response is still valid."""
        return time.time() - timestamp < self._cache_ttl
    
    def request(self, method: str, url: str, use_cache: bool = False, **kwargs) -> requests.Response:
        """
        Make HTTP request with optimizations.
        
        Args:
            method: HTTP method
            url: Request URL
            use_cache: Whether to use response caching for GET requests
            **kwargs: Additional request parameters
        """
        # Disable SSL verification for app.warp.dev (warp intercept server)
        parsed = urlparse(url)
        if parsed.hostname and 'app.warp.dev' in parsed.hostname:
            kwargs["verify"] = False
            logger.debug(f"SSL verification disabled for warp intercept server: {parsed.hostname}")
        
        # Apply DNS caching
        if parsed.hostname and not any(x in parsed.hostname for x in ['localhost', '127.0.0.1', '0.0.0.0']):
            try:
                ip = DNSCachingResolver.resolve_host(parsed.hostname)
                # Replace hostname with IP in URL
                url = url.replace(parsed.hostname, ip)
                # Add Host header for virtual hosting
                if "headers" not in kwargs:
                    kwargs["headers"] = {}
                kwargs["headers"]["Host"] = parsed.hostname
            except Exception as e:
                logger.debug(f"DNS caching failed, using original URL: {e}")
        
        # Check cache for GET requests
        if use_cache and method.upper() == "GET":
            cache_key = self._get_cache_key(method, url, **kwargs)
            if cache_key in self._cache:
                response, timestamp = self._cache[cache_key]
                if self._is_cache_valid(timestamp):
                    logger.debug(f"Cache hit for {method} {url}")
                    return response
        
        # Set timeout if not provided
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout
        
        # Disable proxy for localhost
        if any(x in url.lower() for x in ['localhost', '127.0.0.1', '0.0.0.0']):
            kwargs["proxies"] = {'http': None, 'https': None}
        
        # Make request
        response = self.session.request(method, url, **kwargs)
        
        # Cache successful GET responses
        if use_cache and method.upper() == "GET" and response.status_code == 200:
            cache_key = self._get_cache_key(method, url, **kwargs)
            self._cache[cache_key] = (response, time.time())
        
        return response
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """Make GET request."""
        return self.request("GET", url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """Make POST request."""
        return self.request("POST", url, **kwargs)
    
    def close(self):
        """Close the session."""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


class OptimizedAsyncClient:
    """Optimized asynchronous HTTP client with connection pooling and caching."""
    
    def __init__(self,
                 max_connections: int = 100,
                 max_keepalive_connections: int = 20,
                 keepalive_expiry: float = 120.0,
                 timeout: httpx.Timeout = None):
        """
        Initialize optimized async client.
        
        Args:
            max_connections: Maximum number of concurrent connections
            max_keepalive_connections: Maximum number of keepalive connections
            keepalive_expiry: Time in seconds to keep idle connections alive
            timeout: HTTPX timeout configuration
        """
        if timeout is None:
            timeout = httpx.Timeout(
                connect=10.0,
                read=300.0,
                write=10.0,
                pool=10.0
            )
        
        # Store configuration for later use
        self.timeout = timeout
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.keepalive_expiry = keepalive_expiry
        
        # Configure connection limits
        self.limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry
        )
        
        # Create client with optimized settings
        # Use HTTP/1.1 to support Transfer-Encoding: chunked for streaming
        self.client = httpx.AsyncClient(
            http2=False,
            timeout=self.timeout,
            limits=self.limits,
            headers={
                "Connection": "keep-alive",
                "Keep-Alive": "timeout=120, max=1000"
            }
        )
        
        # Response cache
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._cache_ttl = 60
    
    def _get_cache_key(self, method: str, url: str, **kwargs) -> str:
        """Generate cache key for request."""
        cache_data = {
            "method": method,
            "url": url,
            "headers": dict(kwargs.get("headers", {})),
            "params": dict(kwargs.get("params", {}))
        }
        if "json" in kwargs:
            cache_data["json"] = kwargs["json"]
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    async def request(self, method: str, url: str, use_cache: bool = False, **kwargs) -> httpx.Response:
        """
        Make async HTTP request with optimizations.
        
        Args:
            method: HTTP method
            url: Request URL
            use_cache: Whether to use response caching for GET requests
            **kwargs: Additional request parameters
        """
        # Disable SSL verification for app.warp.dev (warp intercept server)
        parsed = urlparse(url)
        if parsed.hostname and 'app.warp.dev' in parsed.hostname:
            # Note: httpx async client needs verify=False passed to client init, not request
            logger.debug(f"SSL verification should be disabled for warp intercept server: {parsed.hostname}")
        
        # Apply DNS caching
        if parsed.hostname and not any(x in parsed.hostname for x in ['localhost', '127.0.0.1', '0.0.0.0']):
            try:
                ip = await asyncio.get_event_loop().run_in_executor(
                    None, DNSCachingResolver.resolve_host, parsed.hostname
                )
                # Replace hostname with IP in URL
                url = url.replace(parsed.hostname, ip)
                # Add Host header
                if "headers" not in kwargs:
                    kwargs["headers"] = {}
                kwargs["headers"]["Host"] = parsed.hostname
            except Exception as e:
                logger.debug(f"DNS caching failed, using original URL: {e}")
        
        # Check cache for GET requests
        if use_cache and method.upper() == "GET":
            cache_key = self._get_cache_key(method, url, **kwargs)
            if cache_key in self._cache:
                response, timestamp = self._cache[cache_key]
                if time.time() - timestamp < self._cache_ttl:
                    logger.debug(f"Cache hit for {method} {url}")
                    return response
        
        # Make request with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Create a new client for localhost without proxy
                if any(x in url.lower() for x in ['localhost', '127.0.0.1', '0.0.0.0']):
                    async with httpx.AsyncClient(
                        http2=False,
                        timeout=self.timeout,
                        limits=self.limits,
                        headers=self.client.headers,
                        trust_env=False
                    ) as local_client:
                        response = await local_client.request(method, url, **kwargs)
                else:
                    response = await self.client.request(method, url, **kwargs)
                
                # Cache successful GET responses
                if use_cache and method.upper() == "GET" and response.status_code == 200:
                    cache_key = self._get_cache_key(method, url, **kwargs)
                    self._cache[cache_key] = (response, time.time())
                
                return response
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Make async GET request."""
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Make async POST request."""
        return await self.request("POST", url, **kwargs)
    
    async def stream(self, method: str, url: str, **kwargs):
        """Create streaming request."""
        # Apply DNS caching for streaming requests
        parsed = urlparse(url)
        if parsed.hostname and not any(x in parsed.hostname for x in ['localhost', '127.0.0.1', '0.0.0.0']):
            try:
                ip = await asyncio.get_event_loop().run_in_executor(
                    None, DNSCachingResolver.resolve_host, parsed.hostname
                )
                url = url.replace(parsed.hostname, ip)
                if "headers" not in kwargs:
                    kwargs["headers"] = {}
                kwargs["headers"]["Host"] = parsed.hostname
            except Exception:
                pass
        
        # Create a different client for localhost without proxy
        if any(x in url.lower() for x in ['localhost', '127.0.0.1', '0.0.0.0']):
            # Return a new client configured for localhost
            local_client = httpx.AsyncClient(
                http2=False,
                timeout=self.timeout,
                limits=self.limits,
                headers=self.client.headers,
                trust_env=False
            )
            return local_client.stream(method, url, **kwargs)
        
        return self.client.stream(method, url, **kwargs)
    
    async def close(self):
        """Close the client."""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()


# Global client instances for reuse
_sync_client: Optional[OptimizedSyncClient] = None
_async_client: Optional[OptimizedAsyncClient] = None


def get_sync_client() -> OptimizedSyncClient:
    """Get or create global synchronous client instance."""
    global _sync_client
    if _sync_client is None:
        _sync_client = OptimizedSyncClient()
    return _sync_client


def get_async_client() -> OptimizedAsyncClient:
    """Get or create global asynchronous client instance."""
    global _async_client
    if _async_client is None:
        _async_client = OptimizedAsyncClient()
    return _async_client


def cleanup_clients():
    """Cleanup global client instances."""
    global _sync_client, _async_client
    if _sync_client:
        _sync_client.close()
        _sync_client = None
    if _async_client:
        asyncio.create_task(_async_client.close())
        _async_client = None


# Utility functions for backward compatibility
def make_optimized_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Make an optimized HTTP request using the global sync client.
    
    Args:
        method: HTTP method
        url: Request URL
        **kwargs: Additional request parameters
    
    Returns:
        Response object
    """
    client = get_sync_client()
    return client.request(method, url, **kwargs)


async def make_optimized_async_request(method: str, url: str, **kwargs) -> httpx.Response:
    """
    Make an optimized async HTTP request using the global async client.
    
    Args:
        method: HTTP method
        url: Request URL
        **kwargs: Additional request parameters
    
    Returns:
        Response object
    """
    client = get_async_client()
    return await client.request(method, url, **kwargs)


# Pre-warm DNS cache for common OpenAI/Anthropic endpoints
def prewarm_dns_cache():
    """Pre-warm DNS cache with common API endpoints."""
    common_hosts = [
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com"
    ]
    
    for host in common_hosts:
        try:
            DNSCachingResolver.resolve_host(host)
            logger.info(f"Pre-warmed DNS cache for {host}")
        except Exception as e:
            logger.debug(f"Failed to pre-warm DNS for {host}: {e}")


# Initialize DNS cache on module load
if os.getenv("PREWARM_DNS_CACHE", "true").lower() == "true":
    try:
        prewarm_dns_cache()
    except Exception:
        pass