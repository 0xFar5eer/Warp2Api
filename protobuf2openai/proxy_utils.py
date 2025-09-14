"""Proxy configuration utilities for HTTP clients."""

import os
from typing import Dict, Optional
from urllib.parse import urlparse


def should_bypass_proxy(url: str) -> bool:
    """
    Determine if a URL should bypass proxy settings.
    
    Args:
        url: The target URL to check
        
    Returns:
        True if proxy should be bypassed, False otherwise
    """
    # Parse the URL to get hostname
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
    except Exception:
        hostname = url.lower()
    
    # List of hostnames that should never use proxy
    no_proxy_hosts = [
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
        'host.docker.internal',  # Docker internal hostname
        '::1',  # IPv6 localhost
    ]
    
    # Check if hostname matches any no-proxy host
    for no_proxy_host in no_proxy_hosts:
        if no_proxy_host in hostname.lower():
            return True
    
    # Check NO_PROXY environment variable
    no_proxy_env = os.getenv('NO_PROXY', os.getenv('no_proxy', ''))
    if no_proxy_env:
        no_proxy_list = [h.strip().lower() for h in no_proxy_env.split(',')]
        hostname_lower = hostname.lower()
        for no_proxy_pattern in no_proxy_list:
            if no_proxy_pattern and (
                hostname_lower == no_proxy_pattern or
                hostname_lower.endswith('.' + no_proxy_pattern) or
                no_proxy_pattern.startswith('.') and hostname_lower.endswith(no_proxy_pattern)
            ):
                return True
    
    return False


def get_requests_proxies(url: str) -> Optional[Dict[str, Optional[str]]]:
    """
    Get proxy configuration for requests library.
    
    Args:
        url: The target URL to check
        
    Returns:
        Dictionary with proxy settings or None to bypass proxy
    """
    if should_bypass_proxy(url):
        # Explicitly disable proxy for this URL
        return {'http': None, 'https': None}
    
    # Return None to let requests use environment proxy settings
    return None


def get_httpx_trust_env(url: str) -> bool:
    """
    Determine if httpx should trust environment variables for proxy.
    
    Args:
        url: The target URL to check
        
    Returns:
        False if proxy should be bypassed, True otherwise
    """
    return not should_bypass_proxy(url)


def log_proxy_decision(url: str, logger) -> None:
    """
    Log the proxy decision for debugging.
    
    Args:
        url: The target URL
        logger: Logger instance to use
    """
    if should_bypass_proxy(url):
        logger.debug(f"Bypassing proxy for URL: {url}")
    else:
        proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        if proxy:
            # Mask credentials in proxy URL for logging
            if '@' in proxy:
                parts = proxy.split('@')
                masked_proxy = f"[CREDENTIALS]@{parts[-1]}"
            else:
                masked_proxy = proxy
            logger.debug(f"Using proxy {masked_proxy} for URL: {url}")
        else:
            logger.debug(f"No proxy configured for URL: {url}")