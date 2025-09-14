#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Key Validation Module

Provides API key validation for protecting endpoints.
If API_KEY environment variable is set, only requests with matching API key are allowed.
If API_KEY is not set, all requests are allowed (backward compatibility).
"""

import os
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

from .logging import logger

# API key can be provided via header or query parameter
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


def get_required_api_key() -> Optional[str]:
    """
    Get the required API key from environment.
    Reads dynamically to support runtime changes.
    Treats empty string as None (no API key required).
    """
    api_key = os.getenv("API_KEY")
    return api_key if api_key else None


async def get_api_key(
    api_key_from_header: Optional[str] = Security(api_key_header),
    api_key_from_query: Optional[str] = Security(api_key_query),
) -> Optional[str]:
    """
    Validate API key from header or query parameter.
    
    If API_KEY env var is not set, allows all requests.
    If API_KEY is set, validates that the provided key matches.
    
    Args:
        api_key_from_header: API key from X-API-Key header
        api_key_from_query: API key from query parameter
    
    Returns:
        The validated API key or None if validation is disabled
    
    Raises:
        HTTPException: If API key validation fails
    """
    # Get required API key dynamically
    required_api_key = get_required_api_key()
    
    # If no API key is configured, allow all requests
    if not required_api_key:
        logger.debug("API key validation disabled (API_KEY not set)")
        return None
    
    # Get the provided API key from either source
    provided_key = api_key_from_header or api_key_from_query
    
    # Check if API key was provided
    if not provided_key:
        logger.warning("API key required but not provided in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Please provide via X-API-Key header or api_key query parameter",
        )
    
    # Validate the API key
    if provided_key != required_api_key:
        logger.warning(f"Invalid API key provided: {provided_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    logger.debug("API key validation successful")
    return provided_key


def is_api_key_required() -> bool:
    """Check if API key validation is enabled."""
    return bool(get_required_api_key())