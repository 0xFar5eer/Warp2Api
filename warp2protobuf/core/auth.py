#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dummy Authentication for Warp API

Provides dummy bearer token for use with Warp intercept server.
The intercept server will replace dummy values with correct authentication.
"""
import os
from .logging import logger

# Dummy bearer token - will be replaced by warp intercept server
DUMMY_BEARER_TOKEN = "dummy_bearer_token_replace_by_intercept"


async def get_valid_jwt() -> str:
    """Return dummy JWT token.
    
    The warp intercept server will replace this with a valid token.
    """
    return DUMMY_BEARER_TOKEN


def get_jwt_token() -> str:
    """Return dummy JWT token.
    
    The warp intercept server will replace this with a valid token.
    """
    return DUMMY_BEARER_TOKEN


