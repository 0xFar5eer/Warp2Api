# Warp Anonymous Authentication - Technical Implementation Guide

## Overview

This document provides the **accurate technical implementation** of Warp's anonymous authentication system, based on the actual codebase. The anonymous authentication allows applications to access Warp AI services without user account creation through a streamlined 3-phase flow.

## Architecture Overview

### System Components

1. **Warp GraphQL API** - Anonymous user creation endpoint
2. **Google Identity Toolkit** - ID token to refresh token exchange  
3. **Warp Proxy Token Service** - Refresh token to access token conversion
4. **Usage Monitoring** - GraphQL endpoint for quota tracking (separate from auth flow)

### Authentication Flow

```
Client Application
       ↓
1. Create Anonymous User (GraphQL) → ID Token
       ↓
2. Exchange ID Token (Google Identity Toolkit) → Refresh Token  
       ↓
3. Get Access Token (Warp Proxy) → JWT Access Token
       ↓
4. Use Access Token for API calls
```

## Phase-by-Phase Implementation

### Phase 1: Anonymous User Creation

**Endpoint:** `https://app.warp.dev/graphql/v2?op=CreateAnonymousUser`  
**Method:** POST  
**Data Format:** JSON (GraphQL)  
**Purpose:** Create anonymous Firebase user and obtain ID token

**Python Implementation:**

```python
import httpx
import asyncio

async def create_anonymous_user():
    """Phase 1: Create anonymous user via GraphQL"""
    url = "https://app.warp.dev/graphql/v2?op=CreateAnonymousUser"
    
    headers = {
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, br",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows",
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)"
    }
    
    # GraphQL mutation query
    query = """mutation CreateAnonymousUser($input: CreateAnonymousUserInput!, $requestContext: RequestContext!) {
  createAnonymousUser(input: $input, requestContext: $requestContext) {
    __typename
    ... on CreateAnonymousUserOutput {
      expiresAt
      anonymousUserType
      firebaseUid
      idToken
      isInviteValid
      responseContext { serverVersion }
    }
    ... on UserFacingError {
      error { __typename message }
      responseContext { serverVersion }
    }
  }
}"""
    
    variables = {
        "input": {
            "anonymousUserType": "NATIVE_CLIENT_ANONYMOUS_USER_FEATURE_GATED",
            "expirationType": "NO_EXPIRATION",
            "referralCode": None
        },
        "requestContext": {
            "clientContext": {
                "version": "v0.2025.08.06.08.12.stable_02"
            },
            "osContext": {
                "category": "Windows",
                "linuxKernelVersion": None,
                "name": "Windows",
                "version": "11 (26100)"
            }
        }
    }
    
    payload = {
        "query": query,
        "variables": variables,
        "operationName": "CreateAnonymousUser"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            print(f"Request failed: {e}")
            raise

# Usage example
async def main():
    result = await create_anonymous_user()
    print("Response:")
    print(result)
    
    # Extract ID token
    id_token = result["data"]["createAnonymousUser"]["idToken"]
    print(f"\nID Token: {id_token[:50]}...")

# Run the example
# asyncio.run(main())
```

**Success Response (200 OK):**
```json
{
  "data": {
    "createAnonymousUser": {
      "__typename": "CreateAnonymousUserOutput",
      "expiresAt": "2025-12-31T23:59:59Z",
      "anonymousUserType": "NATIVE_CLIENT_ANONYMOUS_USER_FEATURE_GATED",
      "firebaseUid": "anon_abc123def456",
      "idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjY4M...",
      "isInviteValid": true,
      "responseContext": {
        "serverVersion": "v2025.01.18"
      }
    }
  }
}
```

**Error Response Example:**
```json
{
  "data": {
    "createAnonymousUser": {
      "__typename": "UserFacingError",
      "error": {
        "__typename": "RateLimitError",
        "message": "Too many anonymous user creation requests"
      },
      "responseContext": {
        "serverVersion": "v2025.01.18"
      }
    }
  }
}
```

**Critical Value to Extract:**
- `data.createAnonymousUser.idToken` - Required for Phase 2

---

### Phase 2: Refresh Token Exchange

**Endpoint:** `https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={API_KEY}`  
**Method:** POST  
**Data Format:** Form data (application/x-www-form-urlencoded)  
**Purpose:** Exchange ID token for long-lived refresh token via Google Identity Toolkit

**Python Implementation:**

```python
import httpx
import asyncio

async def exchange_id_token_for_refresh_token(id_token: str):
    """Phase 2: Exchange ID token for refresh token via Google Identity Toolkit"""
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
    api_key = "AIzaSyBdy3O3S9hrdayLJxJ7mriBR4qgUaUygAs"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, br",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows",
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)"
    }
    
    # Form data payload
    form_data = {
        "returnSecureToken": "true",
        "token": id_token
    }
    
    params = {"key": api_key}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url, 
                headers=headers, 
                data=form_data,  # Note: using 'data' for form encoding
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            print(f"Request failed: {e}")
            raise

# Usage example
async def main():
    # Assuming you have an ID token from Phase 1
    id_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6IjY4M..."  # From Phase 1
    
    result = await exchange_id_token_for_refresh_token(id_token)
    print("Response:")
    print(result)
    
    # Extract refresh token
    refresh_token = result["refreshToken"]
    print(f"\nRefresh Token: {refresh_token[:50]}...")
    
    # Extract other useful fields
    local_id = result["localId"]
    expires_in = result["expiresIn"]
    print(f"Local ID: {local_id}")
    print(f"Token expires in: {expires_in} seconds")

# Run the example
# asyncio.run(main())
```

**Success Response (200 OK):**
```json
{
  "kind": "identitytoolkit#SigninRequest",
  "localId": "anon_abc123def456",
  "email": "",
  "displayName": "",
  "idToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjY4M...",
  "registered": false,
  "refreshToken": "AMf-vBxSRmdhveGGBYM69p05kDhIn1i7wscALEmC9fYDRpHzjER9dL7kk-kHPYwvY9ROkmy50qGTcIiJZ4Am86hPXkpVPL90HJmAf5fZ7PejypdbcK4wso8Kf3axiSWtIROhOcn9NzGaSvl;WqRMNOpHGgBrYn4I8krW57R8_ws8u7XcSw8u0DiL9HrpMm0LtwsCh81k_6bb2CWOEb1lIx3HWSBTePFWsQ",
  "expiresIn": "3600",
  "isNewUser": true
}
```

**Error Response Example:**
```json
{
  "error": {
    "code": 400,
    "message": "INVALID_CUSTOM_TOKEN",
    "errors": [{
      "message": "INVALID_CUSTOM_TOKEN",
      "domain": "global",
      "reason": "invalid"
    }]
  }
}
```

**Critical Values to Extract:**
- `refreshToken` - **ESSENTIAL**: Long-term credential for Phase 3
- `idToken` - Short-term token (not needed for Phase 3 in this implementation)
- `localId` - Anonymous user identifier

---

### Phase 3: Warp Access Token Generation

**Endpoint:** `https://app.warp.dev/proxy/token?key=AIzaSyBdy3O3S9hrdayLJxJ7mriBR4qgUaUygAs`  
**Method:** POST  
**Data Format:** Form data (application/x-www-form-urlencoded)  
**Purpose:** Convert refresh token to Warp JWT access token

**Python Implementation:**

```python
import httpx
import asyncio

async def get_warp_access_token(refresh_token: str):
    """Phase 3: Convert refresh token to Warp JWT access token"""
    url = "https://app.warp.dev/proxy/token"
    api_key = "AIzaSyBdy3O3S9hrdayLJxJ7mriBR4qgUaUygAs"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, br",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows",
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)"
    }
    
    # Form data payload
    payload = f"grant_type=refresh_token&refresh_token={refresh_token}"
    
    params = {"key": api_key}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                url,
                headers=headers,
                content=payload.encode('utf-8'),  # Note: using 'content' for raw form data
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            print(f"Request failed: {e}")
            raise

# Usage example
async def main():
    # Assuming you have a refresh token from Phase 2
    refresh_token = "AMf-vBxSRmdhveGGBYM69p05kDhIn1i7wscALEmC9fYD..."  # From Phase 2
    
    result = await get_warp_access_token(refresh_token)
    print("Response:")
    print(result)
    
    # Extract access token
    access_token = result["access_token"]
    token_type = result["token_type"]
    expires_in = result["expires_in"]
    
    print(f"\nAccess Token: {access_token[:50]}...")
    print(f"Token Type: {token_type}")
    print(f"Expires in: {expires_in} seconds")
    
    # Check for refresh token rotation
    new_refresh_token = result.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        print(f"\n⚠️  Refresh token rotated!")
        print(f"New refresh token: {new_refresh_token[:50]}...")
    
    return access_token

# Run the example
# asyncio.run(main())
```

**Success Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IjEyMzQ1Njc4OTAifQ...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "AMf-vBxSRmdhveGGBYM69p05kDhIn1i7wscALEmC9fYDRpHzjER9dL7kk-kHPYwvY9ROkmy50qGTcIiJZ4Am86hPXkpVPL90HJmAf5fZ7PejypdbcK4wso8Kf3axiSWtIROhOcn9NzGaSvl;WqRMNOpHGgBrYn4I8krW57R8_ws8u7XcSw8u0DiL9HrpMm0LtwsCh81k_6bb2CWOEb1lIx3HWSBTePFWsQ",
  "scope": "warp:ai:completions warp:ai:embeddings warp:usage:read"
}
```

**Error Response Examples:**

*Invalid Refresh Token (401 Unauthorized):*
```json
{
  "error": "invalid_grant",
  "error_description": "The provided authorization grant is invalid, expired, revoked, does not match the redirection URI used in the authorization request, or was issued to another client."
}
```

*Rate Limit Exceeded (429 Too Many Requests):*
```json
{
  "error": "rate_limit_exceeded",
  "error_description": "Too many token refresh requests",
  "retry_after": 60
}
```

**Critical Values to Extract:**
- `access_token` - **ESSENTIAL**: Primary Warp API JWT credential
- `refresh_token` - May be rotated; update stored value if different
- `expires_in` - Token lifetime in seconds (typically 3600 = 1 hour)

---

## Advanced Token Management

### Token Refresh Strategy

The Warp API implements intelligent token refresh with rotation support and environment persistence.

#### Automatic Token Refresh

```python
async def get_valid_jwt() -> str:
    """Get a valid JWT token, automatically refreshing if needed"""
    from dotenv import load_dotenv as _load
    _load(override=True)
    jwt = os.getenv("WARP_JWT")
    
    if not jwt:
        logger.info("No JWT token found, attempting to refresh...")
        if await check_and_refresh_token():
            _load(override=True)
            jwt = os.getenv("WARP_JWT")
        if not jwt:
            raise RuntimeError("WARP_JWT is not set and refresh failed")
    
    if is_token_expired(jwt, buffer_minutes=2):
        logger.info("JWT token is expired or expiring soon, attempting to refresh...")
        if await check_and_refresh_token():
            _load(override=True)
            jwt = os.getenv("WARP_JWT")
            if not jwt or is_token_expired(jwt, buffer_minutes=0):
                logger.warning("Warning: New token has short expiry but proceeding anyway")
        else:
            logger.warning("Warning: JWT token refresh failed, trying to use existing token")
    return jwt
```

#### Token Expiration Checking

```python
def is_token_expired(token: str, buffer_minutes: int = 5) -> bool:
    """Check if JWT token is expired or expiring within buffer time"""
    payload = decode_jwt_payload(token)
    if not payload or 'exp' not in payload:
        return True
    expiry_time = payload['exp']
    current_time = time.time()
    buffer_time = buffer_minutes * 60
    return (expiry_time - current_time) <= buffer_time

def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without signature verification"""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
        return payload
    except Exception as e:
        logger.debug(f"Error decoding JWT: {e}")
        return {}
```

#### Refresh Token Management

**Refresh Token Rotation Handling:**
```python
async def refresh_jwt_token() -> dict:
    """Refresh JWT using stored refresh token with rotation support"""
    logger.info("Refreshing JWT token...")
    
    # Get current refresh token from environment
    env_refresh = os.getenv("WARP_REFRESH_TOKEN")
    current_refresh_token = env_refresh
    
    if env_refresh:
        payload = f"grant_type=refresh_token&refresh_token={env_refresh}".encode("utf-8")
    else:
        # Fallback to base64 encoded token
        payload = base64.b64decode(REFRESH_TOKEN_B64)
        # Extract refresh token for rotation comparison
        try:
            payload_str = payload.decode("utf-8")
            for part in payload_str.split("&"):
                if part.startswith("refresh_token="):
                    current_refresh_token = part.split("=", 1)[1]
                    break
        except Exception:
            current_refresh_token = None
    
    headers = {
        "x-warp-client-version": CLIENT_VERSION,
        "x-warp-os-category": OS_CATEGORY,
        "x-warp-os-name": OS_NAME,
        "x-warp-os-version": OS_VERSION,
        "content-type": "application/x-www-form-urlencoded",
        "accept": "*/*",
        "accept-encoding": "gzip, br",
        "content-length": str(len(payload))
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(REFRESH_URL, headers=headers, content=payload)
            if response.status_code == 200:
                token_data = response.json()
                logger.info("Token refresh successful")
                
                # Handle refresh token rotation
                new_refresh_token = token_data.get("refreshToken") or token_data.get("refresh_token")
                if new_refresh_token and current_refresh_token and new_refresh_token != current_refresh_token:
                    logger.info("Refresh token rotated, updating stored token")
                    if update_env_refresh_token(new_refresh_token):
                        logger.info("Successfully updated rotated refresh token")
                    else:
                        logger.warning("Failed to update rotated refresh token - this may cause future refresh failures")
                elif new_refresh_token and not current_refresh_token:
                    logger.info("Received new refresh token, saving for future use")
                    update_env_refresh_token(new_refresh_token)
                
                return token_data
            else:
                logger.error(f"Token refresh failed: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return {}
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        return {}
```

**Environment File Management:**
```python
def update_env_file(new_jwt: str) -> bool:
    """Update .env file with new JWT access token"""
    env_path = Path(".env")
    try:
        set_key(str(env_path), "WARP_JWT", new_jwt)
        logger.info("Updated .env file with new JWT token")
        return True
    except Exception as e:
        logger.error(f"Error updating .env file: {e}")
        return False

def update_env_refresh_token(refresh_token: str) -> bool:
    """Update .env file with new refresh token"""
    env_path = Path(".env")
    try:
        set_key(str(env_path), "WARP_REFRESH_TOKEN", refresh_token)
        logger.info("Updated .env with WARP_REFRESH_TOKEN")
        return True
    except Exception as e:
        logger.error(f"Error updating .env WARP_REFRESH_TOKEN: {e}")
        return False
```

#### Token Refresh Best Practices

1. **Proactive Refresh:** Check tokens 2-15 minutes before expiration
2. **Rotation Handling:** Always check if refresh token changed and update storage
3. **Error Recovery:** Fallback to complete re-authentication if refresh fails
4. **Environment Persistence:** Store tokens in `.env` file for session continuity
5. **Thread Safety:** Use locks in multi-threaded environments

#### Refresh Timing Strategy

```python
# Buffer times for different scenarios
PROACTIVE_REFRESH_BUFFER = 15  # minutes - for background refresh
API_CALL_BUFFER = 2           # minutes - for API request validation
EXPIRATION_CHECK_BUFFER = 5   # minutes - for general expiration checks

# Usage examples:
if is_token_expired(token, buffer_minutes=PROACTIVE_REFRESH_BUFFER):
    # Start background refresh process
    asyncio.create_task(refresh_jwt_token())

if is_token_expired(token, buffer_minutes=API_CALL_BUFFER):
    # Refresh before making API call
    await check_and_refresh_token()
```

### Complete Usage Limits Implementation

```python
async def query_usage_limits(access_token: str) -> dict:
    """Query the Warp GraphQL API to get comprehensive usage limit information."""
    
    url = "https://app.warp.dev/graphql/v2?op=GetRequestLimitInfo"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows", 
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "x-warp-manager-request": "true"
    }
    
    # Complete GraphQL query with error handling
    query = """query GetRequestLimitInfo($requestContext: RequestContext!) {
  user(requestContext: $requestContext) {
    __typename
    ... on UserOutput {
      user {
        requestLimitInfo {
          isUnlimited
          nextRefreshTime
          requestLimit
          requestsUsedSinceLastRefresh
          requestLimitRefreshDuration
          isUnlimitedAutosuggestions
          acceptedAutosuggestionsLimit
          acceptedAutosuggestionsSinceLastRefresh
          isUnlimitedVoice
          voiceRequestLimit
          voiceRequestsUsedSinceLastRefresh
          voiceTokenLimit
          voiceTokensUsedSinceLastRefresh
          isUnlimitedCodebaseIndices
          maxCodebaseIndices
          maxFilesPerRepo
          embeddingGenerationBatchSize
        }
      }
    }
    ... on UserFacingError {
      error {
        __typename
        ... on SharedObjectsLimitExceeded {
          limit
          objectType
          message
        }
        ... on PersonalObjectsLimitExceeded {
          limit
          objectType
          message
        }
        ... on AccountDelinquencyError {
          message
        }
        ... on GenericStringObjectUniqueKeyConflict {
          message
        }
      }
      responseContext {
        serverVersion
      }
    }
  }
}"""
    
    payload = {
        "query": query,
        "variables": {
            "requestContext": {
                "clientContext": {
                    "version": "v0.2025.08.06.08.12.stable_02"
                },
                "osContext": {
                    "category": "Windows",
                    "linuxKernelVersion": None,
                    "name": "Windows", 
                    "version": "11 (26100)"
                }
            }
        },
        "operationName": "GetRequestLimitInfo"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
```

### Usage Limits Response Processing

```python
def process_usage_limits(response_data: dict) -> dict:
    """Process and extract usage limits from GraphQL response"""
    
    # Handle GraphQL errors
    if "errors" in response_data:
        raise RuntimeError(f"GraphQL Errors: {response_data['errors']}")
    
    user_data = response_data.get("data", {}).get("user", {})
    
    # Handle UserFacingError responses
    if user_data.get("__typename") == "UserFacingError":
        error = user_data.get("error", {})
        error_type = error.get("__typename", "Unknown")
        error_message = error.get("message", "No message")
        raise RuntimeError(f"User Error: {error_type} - {error_message}")
    
    # Validate UserOutput response
    if user_data.get("__typename") != "UserOutput":
        raise RuntimeError(f"Unexpected response type: {user_data.get('__typename')}")
    
    limit_info = user_data.get("user", {}).get("requestLimitInfo", {})
    
    if not limit_info:
        raise RuntimeError("No request limit information available")
    
    return limit_info

def calculate_usage_metrics(limit_info: dict) -> dict:
    """Calculate usage metrics and percentages"""
    metrics = {}
    
    # AI Requests
    ai_limit = limit_info.get('requestLimit', 0)
    ai_used = limit_info.get('requestsUsedSinceLastRefresh', 0)
    metrics['ai_requests'] = {
        'limit': ai_limit,
        'used': ai_used,
        'remaining': max(0, ai_limit - ai_used),
        'usage_percent': (ai_used / ai_limit * 100) if ai_limit > 0 else 0,
        'unlimited': limit_info.get('isUnlimited', False)
    }
    
    # Autosuggestions
    auto_limit = limit_info.get('acceptedAutosuggestionsLimit', 0)
    auto_used = limit_info.get('acceptedAutosuggestionsSinceLastRefresh', 0)
    metrics['autosuggestions'] = {
        'limit': auto_limit,
        'used': auto_used,
        'remaining': max(0, auto_limit - auto_used),
        'usage_percent': (auto_used / auto_limit * 100) if auto_limit > 0 else 0,
        'unlimited': limit_info.get('isUnlimitedAutosuggestions', False)
    }
    
    # Voice Requests
    voice_req_limit = limit_info.get('voiceRequestLimit', 0)
    voice_req_used = limit_info.get('voiceRequestsUsedSinceLastRefresh', 0)
    metrics['voice_requests'] = {
        'limit': voice_req_limit,
        'used': voice_req_used,
        'remaining': max(0, voice_req_limit - voice_req_used),
        'usage_percent': (voice_req_used / voice_req_limit * 100) if voice_req_limit > 0 else 0,
        'unlimited': limit_info.get('isUnlimitedVoice', False)
    }
    
    # Voice Tokens
    voice_token_limit = limit_info.get('voiceTokenLimit', 0)
    voice_token_used = limit_info.get('voiceTokensUsedSinceLastRefresh', 0)
    metrics['voice_tokens'] = {
        'limit': voice_token_limit,
        'used': voice_token_used,
        'remaining': max(0, voice_token_limit - voice_token_used),
        'usage_percent': (voice_token_used / voice_token_limit * 100) if voice_token_limit > 0 else 0
    }
    
    # Codebase Indices
    metrics['codebase'] = {
        'max_indices': limit_info.get('maxCodebaseIndices', 0),
        'max_files_per_repo': limit_info.get('maxFilesPerRepo', 0),
        'embedding_batch_size': limit_info.get('embeddingGenerationBatchSize', 0),
        'unlimited': limit_info.get('isUnlimitedCodebaseIndices', False)
    }
    
    # Quota refresh information
    next_refresh = limit_info.get('nextRefreshTime')
    if next_refresh:
        try:
            from datetime import datetime
            if isinstance(next_refresh, str):
                next_refresh_dt = datetime.fromisoformat(next_refresh.replace('Z', '+00:00'))
            else:
                next_refresh_dt = datetime.fromtimestamp(next_refresh / 1000)
            
            time_until_refresh = next_refresh_dt - datetime.now(next_refresh_dt.tzinfo)
            metrics['quota_refresh'] = {
                'next_refresh_time': next_refresh_dt.isoformat(),
                'time_until_refresh_seconds': int(time_until_refresh.total_seconds()),
                'refresh_duration': limit_info.get('requestLimitRefreshDuration', 'UNKNOWN')
            }
        except Exception as e:
            metrics['quota_refresh'] = {
                'next_refresh_time': str(next_refresh),
                'time_until_refresh_seconds': None,
                'refresh_duration': limit_info.get('requestLimitRefreshDuration', 'UNKNOWN'),
                'parse_error': str(e)
            }
    
    return metrics
```

### Usage Monitoring with Alerts

```python
class UsageMonitor:
    def __init__(self, warning_threshold: float = 80.0, critical_threshold: float = 95.0):
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def check_usage_status(self, access_token: str) -> dict:
        """Check usage status and return alerts if needed"""
        response_data = await query_usage_limits(access_token)
        limit_info = process_usage_limits(response_data)
        metrics = calculate_usage_metrics(limit_info)
        
        alerts = []
        
        # Check each metric for threshold violations
        for metric_name, metric_data in metrics.items():
            if isinstance(metric_data, dict) and 'usage_percent' in metric_data:
                usage_percent = metric_data['usage_percent']
                
                if usage_percent >= self.critical_threshold:
                    alerts.append({
                        'level': 'CRITICAL',
                        'metric': metric_name,
                        'usage_percent': usage_percent,
                        'remaining': metric_data.get('remaining', 0),
                        'message': f"{metric_name} usage is critically high: {usage_percent:.1f}%"
                    })
                elif usage_percent >= self.warning_threshold:
                    alerts.append({
                        'level': 'WARNING',
                        'metric': metric_name,
                        'usage_percent': usage_percent,
                        'remaining': metric_data.get('remaining', 0),
                        'message': f"{metric_name} usage is high: {usage_percent:.1f}%"
                    })
        
        return {
            'metrics': metrics,
            'alerts': alerts,
            'overall_status': 'CRITICAL' if any(a['level'] == 'CRITICAL' for a in alerts) else 
                             'WARNING' if any(a['level'] == 'WARNING' for a in alerts) else 'OK'
        }
    
    def should_throttle_requests(self, usage_status: dict) -> bool:
        """Determine if requests should be throttled based on usage"""
        ai_usage = usage_status['metrics'].get('ai_requests', {})
        return ai_usage.get('usage_percent', 0) > self.critical_threshold

# Usage example
monitor = UsageMonitor(warning_threshold=75.0, critical_threshold=90.0)
usage_status = await monitor.check_usage_status(access_token)

if monitor.should_throttle_requests(usage_status):
    logger.warning("Throttling API requests due to high usage")
    # Implement throttling logic

for alert in usage_status['alerts']:
    logger.log(logging.WARNING if alert['level'] == 'WARNING' else logging.ERROR, alert['message'])
```

### Quota Management Strategies

```python
class QuotaManager:
    def __init__(self, usage_monitor: UsageMonitor):
        self.usage_monitor = usage_monitor
        self.last_check = None
        self.cache_duration = 300  # 5 minutes cache
        self._cached_status = None
    
    async def get_cached_usage_status(self, access_token: str) -> dict:
        """Get usage status with caching to avoid excessive API calls"""
        now = time.time()
        
        if (self._cached_status is None or 
            self.last_check is None or 
            now - self.last_check > self.cache_duration):
            
            self._cached_status = await self.usage_monitor.check_usage_status(access_token)
            self.last_check = now
        
        return self._cached_status
    
    async def can_make_request(self, access_token: str, request_type: str = 'ai_requests') -> bool:
        """Check if a request can be made without exceeding quota"""
        status = await self.get_cached_usage_status(access_token)
        metric = status['metrics'].get(request_type, {})
        
        if metric.get('unlimited', False):
            return True
        
        remaining = metric.get('remaining', 0)
        return remaining > 0
    
    async def estimate_requests_until_quota_reset(self, access_token: str) -> dict:
        """Estimate time and requests until quota reset"""
        status = await self.get_cached_usage_status(access_token)
        quota_info = status['metrics'].get('quota_refresh', {})
        
        time_until_reset = quota_info.get('time_until_refresh_seconds', 0)
        
        estimates = {}
        for metric_name, metric_data in status['metrics'].items():
            if isinstance(metric_data, dict) and 'remaining' in metric_data:
                remaining = metric_data.get('remaining', 0)
                estimates[metric_name] = {
                    'remaining_requests': remaining,
                    'time_until_reset_seconds': time_until_reset,
                    'time_until_reset_hours': time_until_reset / 3600,
                    'can_continue': remaining > 0
                }
        
        return estimates
```

---

## Usage Monitoring and Quota Management

### Getting Usage Limits (Separate from Auth Flow)

**Endpoint:** `https://app.warp.dev/graphql/v2?op=GetRequestLimitInfo`  
**Method:** POST  
**Data Format:** JSON (GraphQL)  
**Purpose:** Query current usage limits and consumption
**Authentication:** Requires Bearer token from Phase 3

**Python Implementation:**

```python
import httpx
import asyncio
from datetime import datetime

async def get_usage_limits(access_token: str):
    """Query usage limits and consumption for anonymous users"""
    url = "https://app.warp.dev/graphql/v2?op=GetRequestLimitInfo"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, br",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows",
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)",
        "x-warp-manager-request": "true"
    }
    
    # GraphQL query for usage limits
    query = """query GetRequestLimitInfo($requestContext: RequestContext!) {
  user(requestContext: $requestContext) {
    __typename
    ... on UserOutput {
      user {
        requestLimitInfo {
          isUnlimited
          nextRefreshTime
          requestLimit
          requestsUsedSinceLastRefresh
          requestLimitRefreshDuration
          isUnlimitedAutosuggestions
          acceptedAutosuggestionsLimit
          acceptedAutosuggestionsSinceLastRefresh
          isUnlimitedVoice
          voiceRequestLimit
          voiceRequestsUsedSinceLastRefresh
          voiceTokenLimit
          voiceTokensUsedSinceLastRefresh
          isUnlimitedCodebaseIndices
          maxCodebaseIndices
          maxFilesPerRepo
          embeddingGenerationBatchSize
        }
      }
    }
    ... on UserFacingError {
      error {
        __typename
        message
      }
      responseContext {
        serverVersion
      }
    }
  }
}"""
    
    payload = {
        "query": query,
        "variables": {
            "requestContext": {
                "clientContext": {
                    "version": "v0.2025.08.06.08.12.stable_02"
                },
                "osContext": {
                    "category": "Windows",
                    "linuxKernelVersion": None,
                    "name": "Windows",
                    "version": "11 (26100)"
                }
            }
        },
        "operationName": "GetRequestLimitInfo"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            print(f"Request failed: {e}")
            raise

def format_usage_info(response_data: dict) -> dict:
    """Process and format usage limits data"""
    # Handle GraphQL errors
    if "errors" in response_data:
        raise RuntimeError(f"GraphQL Errors: {response_data['errors']}")
    
    user_data = response_data.get("data", {}).get("user", {})
    
    # Handle UserFacingError responses
    if user_data.get("__typename") == "UserFacingError":
        error = user_data.get("error", {})
        raise RuntimeError(f"User Error: {error.get('message', 'Unknown error')}")
    
    # Extract usage limits
    limit_info = user_data.get("user", {}).get("requestLimitInfo", {})
    
    if not limit_info:
        raise RuntimeError("No request limit information available")
    
    # Calculate usage percentages
    def calc_usage_percent(used, limit):
        return (used / limit * 100) if limit > 0 else 0
    
    ai_used = limit_info.get('requestsUsedSinceLastRefresh', 0)
    ai_limit = limit_info.get('requestLimit', 0)
    
    auto_used = limit_info.get('acceptedAutosuggestionsSinceLastRefresh', 0)
    auto_limit = limit_info.get('acceptedAutosuggestionsLimit', 0)
    
    voice_req_used = limit_info.get('voiceRequestsUsedSinceLastRefresh', 0)
    voice_req_limit = limit_info.get('voiceRequestLimit', 0)
    
    voice_token_used = limit_info.get('voiceTokensUsedSinceLastRefresh', 0)
    voice_token_limit = limit_info.get('voiceTokenLimit', 0)
    
    # Format next refresh time
    next_refresh = limit_info.get('nextRefreshTime')
    next_refresh_formatted = "Unknown"
    if next_refresh:
        try:
            next_refresh_dt = datetime.fromisoformat(next_refresh.replace('Z', '+00:00'))
            next_refresh_formatted = next_refresh_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            next_refresh_formatted = str(next_refresh)
    
    return {
        'ai_requests': {
            'used': ai_used,
            'limit': ai_limit,
            'remaining': max(0, ai_limit - ai_used),
            'usage_percent': calc_usage_percent(ai_used, ai_limit),
            'unlimited': limit_info.get('isUnlimited', False)
        },
        'autosuggestions': {
            'used': auto_used,
            'limit': auto_limit,
            'remaining': max(0, auto_limit - auto_used),
            'usage_percent': calc_usage_percent(auto_used, auto_limit),
            'unlimited': limit_info.get('isUnlimitedAutosuggestions', False)
        },
        'voice_requests': {
            'used': voice_req_used,
            'limit': voice_req_limit,
            'remaining': max(0, voice_req_limit - voice_req_used),
            'usage_percent': calc_usage_percent(voice_req_used, voice_req_limit),
            'unlimited': limit_info.get('isUnlimitedVoice', False)
        },
        'voice_tokens': {
            'used': voice_token_used,
            'limit': voice_token_limit,
            'remaining': max(0, voice_token_limit - voice_token_used),
            'usage_percent': calc_usage_percent(voice_token_used, voice_token_limit)
        },
        'codebase': {
            'max_indices': limit_info.get('maxCodebaseIndices', 0),
            'max_files_per_repo': limit_info.get('maxFilesPerRepo', 0),
            'embedding_batch_size': limit_info.get('embeddingGenerationBatchSize', 0),
            'unlimited': limit_info.get('isUnlimitedCodebaseIndices', False)
        },
        'quota_info': {
            'next_refresh_time': next_refresh_formatted,
            'refresh_duration': limit_info.get('requestLimitRefreshDuration', 'UNKNOWN')
        }
    }

# Usage example
async def main():
    # Assuming you have an access token from Phase 3
    access_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6..."  # From Phase 3
    
    raw_response = await get_usage_limits(access_token)
    print("Raw Response:")
    print(raw_response)
    
    # Process and format the data
    usage_data = format_usage_info(raw_response)
    
    print("\n📊 Formatted Usage Information:")
    print(f"\n🤖 AI Requests:")
    print(f"  Used: {usage_data['ai_requests']['used']}/{usage_data['ai_requests']['limit']}")
    print(f"  Remaining: {usage_data['ai_requests']['remaining']}")
    print(f"  Usage: {usage_data['ai_requests']['usage_percent']:.1f}%")
    
    print(f"\n💡 Autosuggestions:")
    print(f"  Used: {usage_data['autosuggestions']['used']}/{usage_data['autosuggestions']['limit']}")
    print(f"  Remaining: {usage_data['autosuggestions']['remaining']}")
    print(f"  Usage: {usage_data['autosuggestions']['usage_percent']:.1f}%")
    
    print(f"\n🎤 Voice Features:")
    print(f"  Requests: {usage_data['voice_requests']['used']}/{usage_data['voice_requests']['limit']}")
    print(f"  Tokens: {usage_data['voice_tokens']['used']}/{usage_data['voice_tokens']['limit']}")
    
    print(f"\n📅 Quota Information:")
    print(f"  Next Reset: {usage_data['quota_info']['next_refresh_time']}")
    print(f"  Reset Schedule: {usage_data['quota_info']['refresh_duration']}")
    
    # Alert on high usage
    for feature, data in usage_data.items():
        if isinstance(data, dict) and 'usage_percent' in data:
            if data['usage_percent'] > 80:
                print(f"\n⚠️  WARNING: {feature} usage is high ({data['usage_percent']:.1f}%)")

# Run the example
# asyncio.run(main())
```

**Success Response (200 OK):**
```json
{
  "data": {
    "user": {
      "__typename": "UserOutput",
      "user": {
        "requestLimitInfo": {
          "isUnlimited": false,
          "nextRefreshTime": "2025-02-01T00:00:00Z",
          "requestLimit": 150,
          "requestsUsedSinceLastRefresh": 0,
          "requestLimitRefreshDuration": "MONTHLY",
          "isUnlimitedAutosuggestions": false,
          "acceptedAutosuggestionsLimit": 50,
          "acceptedAutosuggestionsSinceLastRefresh": 0,
          "isUnlimitedVoice": false,
          "voiceRequestLimit": 10000,
          "voiceRequestsUsedSinceLastRefresh": 0,
          "voiceTokenLimit": 30000,
          "voiceTokensUsedSinceLastRefresh": 0,
          "isUnlimitedCodebaseIndices": false,
          "maxCodebaseIndices": 3,
          "maxFilesPerRepo": 5000,
          "embeddingGenerationBatchSize": 100
        }
      }
    }
  }
}
```

---

## Implementation Details

### Complete Flow Implementation

**Complete 3-Phase Flow Implementation:**

```python
import httpx
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv, set_key

async def complete_anonymous_authentication_flow():
    """Complete 3-phase anonymous authentication flow with all phases"""
    
    print("🚀 Starting Warp Anonymous Authentication Flow...")
    print("=" * 60)
    
    try:
        # Phase 1: Create Anonymous User
        print("\n📍 Phase 1: Creating anonymous user...")
        id_token = await create_anonymous_user_phase1()
        print(f"✅ Phase 1 complete - ID Token: {id_token[:30]}...")
        
        # Phase 2: Exchange for Refresh Token  
        print("\n📍 Phase 2: Exchanging for refresh token...")
        refresh_token = await exchange_for_refresh_token_phase2(id_token)
        print(f"✅ Phase 2 complete - Refresh Token: {refresh_token[:30]}...")
        
        # Phase 3: Get Access Token
        print("\n📍 Phase 3: Getting access token...")
        access_token = await get_access_token_phase3(refresh_token)
        print(f"✅ Phase 3 complete - Access Token: {access_token[:30]}...")
        
        # Save tokens to .env file
        save_tokens_to_env(access_token, refresh_token)
        print("\n💾 Tokens saved to .env file")
        
        # Test the access token by getting usage limits
        print("\n📊 Testing access token with usage limits query...")
        await test_access_token(access_token)
        
        return access_token
        
    except Exception as e:
        print(f"\n❌ Authentication flow failed: {e}")
        raise

async def create_anonymous_user_phase1():
    """Phase 1: Create anonymous user via GraphQL"""
    url = "https://app.warp.dev/graphql/v2?op=CreateAnonymousUser"
    
    headers = {
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, br",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows",
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)"
    }
    
    query = """mutation CreateAnonymousUser($input: CreateAnonymousUserInput!, $requestContext: RequestContext!) {
  createAnonymousUser(input: $input, requestContext: $requestContext) {
    __typename
    ... on CreateAnonymousUserOutput {
      expiresAt
      anonymousUserType
      firebaseUid
      idToken
      isInviteValid
      responseContext { serverVersion }
    }
    ... on UserFacingError {
      error { __typename message }
      responseContext { serverVersion }
    }
  }
}"""
    
    payload = {
        "query": query,
        "variables": {
            "input": {
                "anonymousUserType": "NATIVE_CLIENT_ANONYMOUS_USER_FEATURE_GATED",
                "expirationType": "NO_EXPIRATION",
                "referralCode": None
            },
            "requestContext": {
                "clientContext": {"version": "v0.2025.08.06.08.12.stable_02"},
                "osContext": {
                    "category": "Windows",
                    "linuxKernelVersion": None,
                    "name": "Windows",
                    "version": "11 (26100)"
                }
            }
        },
        "operationName": "CreateAnonymousUser"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Handle errors
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        
        create_user_data = data["data"]["createAnonymousUser"]
        if create_user_data.get("__typename") == "UserFacingError":
            error = create_user_data.get("error", {})
            raise RuntimeError(f"User creation error: {error.get('message', 'Unknown')}")
        
        return create_user_data["idToken"]

async def exchange_for_refresh_token_phase2(id_token: str):
    """Phase 2: Exchange ID token for refresh token"""
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip, br",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows",
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)"
    }
    
    form_data = {
        "returnSecureToken": "true",
        "token": id_token
    }
    
    params = {"key": "AIzaSyBdy3O3S9hrdayLJxJ7mriBR4qgUaUygAs"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, data=form_data, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            raise RuntimeError(f"Identity Toolkit error: {data['error']}")
        
        return data["refreshToken"]

async def get_access_token_phase3(refresh_token: str):
    """Phase 3: Convert refresh token to access token"""
    url = "https://app.warp.dev/proxy/token"
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, br",
        "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
        "x-warp-os-category": "Windows",
        "x-warp-os-name": "Windows",
        "x-warp-os-version": "11 (26100)"
    }
    
    payload = f"grant_type=refresh_token&refresh_token={refresh_token}"
    params = {"key": "AIzaSyBdy3O3S9hrdayLJxJ7mriBR4qgUaUygAs"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url, 
            headers=headers, 
            content=payload.encode('utf-8'),
            params=params
        )
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            raise RuntimeError(f"Access token error: {data['error']}")
        
        return data["access_token"]

def save_tokens_to_env(access_token: str, refresh_token: str):
    """Save tokens to .env file for persistence"""
    env_path = Path(".env")
    try:
        set_key(str(env_path), "WARP_JWT", access_token)
        set_key(str(env_path), "WARP_REFRESH_TOKEN", refresh_token)
        print("Tokens saved to .env file")
    except Exception as e:
        print(f"Warning: Could not save to .env file: {e}")

async def test_access_token(access_token: str):
    """Test the access token by querying usage limits"""
    try:
        from datetime import datetime
        
        # Quick usage limits test
        url = "https://app.warp.dev/graphql/v2?op=GetRequestLimitInfo"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "x-warp-client-version": "v0.2025.08.06.08.12.stable_02",
            "x-warp-manager-request": "true"
        }
        
        query = """query GetRequestLimitInfo($requestContext: RequestContext!) {
  user(requestContext: $requestContext) {
    __typename
    ... on UserOutput {
      user {
        requestLimitInfo {
          requestLimit
          requestsUsedSinceLastRefresh
          nextRefreshTime
        }
      }
    }
  }
}"""
        
        payload = {
            "query": query,
            "variables": {
                "requestContext": {
                    "clientContext": {"version": "v0.2025.08.06.08.12.stable_02"},
                    "osContext": {"category": "Windows", "name": "Windows", "version": "11 (26100)"}
                }
            },
            "operationName": "GetRequestLimitInfo"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if "errors" not in data:
                limit_info = data["data"]["user"]["user"]["requestLimitInfo"]
                used = limit_info["requestsUsedSinceLastRefresh"]
                limit = limit_info["requestLimit"]
                remaining = limit - used
                
                print(f"✅ Access token is valid!")
                print(f"   📊 AI Requests: {used}/{limit} (remaining: {remaining})")
                
                next_refresh = limit_info.get("nextRefreshTime")
                if next_refresh:
                    try:
                        refresh_dt = datetime.fromisoformat(next_refresh.replace('Z', '+00:00'))
                        print(f"   📅 Next quota reset: {refresh_dt.strftime('%Y-%m-%d %H:%M UTC')}")
                    except:
                        pass
            else:
                print(f"⚠️  Access token test returned errors: {data['errors']}")
                
    except Exception as e:
        print(f"⚠️  Could not test access token: {e}")

# Main execution example
async def main():
    """Complete demonstration of the anonymous authentication flow"""
    try:
        # Run the complete authentication flow
        access_token = await complete_anonymous_authentication_flow()
        
        print("\n🎉 Authentication successful!")
        print(f"Your access token is ready to use: {access_token[:30]}...")
        print("\nYou can now make API calls to Warp services using this token.")
        print("\nExample usage:")
        print('headers = {"Authorization": f"Bearer {access_token}"}')
        
        return access_token
        
    except Exception as e:
        print(f"\n💥 Authentication failed: {e}")
        raise

if __name__ == "__main__":
    # Uncomment to run the complete flow
    # asyncio.run(main())
    
    # Or run individual phases for testing
    pass
```

### Token Management

**Access Token (JWT):**
- **Lifetime:** ~1 hour (3600 seconds)
- **Usage:** Bearer token for all Warp API calls
- **Format:** Standard JWT with Warp-specific claims
- **Refresh:** Use refresh token before expiration

**Refresh Token:**
- **Lifetime:** Long-lived (weeks to months)
- **Usage:** Only for obtaining new access tokens
- **Rotation:** May change during refresh operations
- **Storage:** Must be securely persisted

### Error Handling

**Phase 1 Errors:**
- GraphQL errors returned in `data.createAnonymousUser.__typename: "UserFacingError"`
- HTTP errors (rate limiting, server errors)

**Phase 2 Errors:**
- Google Identity Toolkit standard errors
- Invalid tokens, expired credentials

**Phase 3 Errors:**
- OAuth2-style errors (`invalid_grant`, `rate_limit_exceeded`)
- Network timeouts, server errors

### Security Considerations

1. **Never log refresh tokens** - They are long-lived credentials
2. **Use HTTPS only** - All communications must be encrypted
3. **Rotate refresh tokens** - Update stored tokens when they change
4. **Implement retry logic** - With exponential backoff for failures
5. **Monitor quotas** - Track usage to avoid limit violations

### Anonymous Account Limits

- **Monthly AI Requests:** 150
- **Autosuggestions:** 50 per month
- **Voice Requests:** 10,000 per month
- **Voice Tokens:** 30,000 per month
- **Codebase Indices:** 3 maximum concurrent
- **Files per Repository:** 5,000 maximum

---

## Key Differences from Previous Documentation

1. **Only 3 phases** in authentication flow (not 5)
2. **Phase 2 uses form data**, not JSON
3. **Phase 3 uses form data**, not JSON, with different endpoint
4. **Usage monitoring is separate** from authentication flow
5. **Correct GraphQL queries** with proper variable structures
6. **Accurate response formats** based on actual implementation
7. **Proper error handling** patterns for each phase

## Complete Integration Example

### Production-Ready Implementation

```python
import asyncio
import logging
import time
from typing import Optional, Dict, Any
from pathlib import Path
import httpx
from dotenv import load_dotenv, set_key

class WarpAuthManager:
    """Complete Warp Anonymous Authentication Manager"""
    
    def __init__(self, 
                 client_version: str = "v0.2025.08.06.08.12.stable_02",
                 os_category: str = "Windows",
                 os_name: str = "Windows",
                 os_version: str = "11 (26100)"):
        self.client_version = client_version
        self.os_category = os_category
        self.os_name = os_name
        self.os_version = os_version
        self.refresh_url = "https://app.warp.dev/proxy/token?key=AIzaSyBdy3O3S9hrdayLJxJ7mriBR4qgUaUygAs"
        
        # Initialize usage monitoring
        self.usage_monitor = UsageMonitor(warning_threshold=75.0, critical_threshold=90.0)
        self.quota_manager = QuotaManager(self.usage_monitor)
        
        # Load environment variables
        load_dotenv()
    
    async def get_valid_token(self) -> str:
        """Get a valid access token, handling all refresh logic"""
        jwt = os.getenv("WARP_JWT")
        
        # No token - try to refresh or acquire new anonymous token
        if not jwt:
            logging.info("No JWT token found, acquiring anonymous token...")
            return await self.acquire_anonymous_token()
        
        # Token exists but might be expired
        if self.is_token_expired(jwt, buffer_minutes=2):
            logging.info("JWT token is expired or expiring soon, refreshing...")
            try:
                return await self.refresh_token()
            except Exception as e:
                logging.warning(f"Token refresh failed: {e}. Acquiring new anonymous token...")
                return await self.acquire_anonymous_token()
        
        return jwt
    
    async def acquire_anonymous_token(self) -> str:
        """Complete 3-phase anonymous authentication flow"""
        logging.info("Starting anonymous authentication flow...")
        
        try:
            # Phase 1: Create Anonymous User
            id_token = await self._create_anonymous_user()
            logging.info("Phase 1 completed: Anonymous user created")
            
            # Phase 2: Exchange for Refresh Token
            refresh_token = await self._exchange_for_refresh_token(id_token)
            logging.info("Phase 2 completed: Refresh token acquired")
            
            # Phase 3: Get Access Token
            access_token = await self._get_access_token(refresh_token)
            logging.info("Phase 3 completed: Access token acquired")
            
            # Store tokens
            self._save_tokens(access_token, refresh_token)
            
            return access_token
            
        except Exception as e:
            logging.error(f"Anonymous authentication failed: {e}")
            raise
    
    async def _create_anonymous_user(self) -> str:
        """Phase 1: Create anonymous user via GraphQL"""
        url = "https://app.warp.dev/graphql/v2?op=CreateAnonymousUser"
        
        headers = {
            "accept-encoding": "gzip, br",
            "content-type": "application/json",
            "x-warp-client-version": self.client_version,
            "x-warp-os-category": self.os_category,
            "x-warp-os-name": self.os_name,
            "x-warp-os-version": self.os_version,
        }
        
        query = """mutation CreateAnonymousUser($input: CreateAnonymousUserInput!, $requestContext: RequestContext!) {
  createAnonymousUser(input: $input, requestContext: $requestContext) {
    __typename
    ... on CreateAnonymousUserOutput {
      expiresAt
      anonymousUserType
      firebaseUid
      idToken
      isInviteValid
      responseContext { serverVersion }
    }
    ... on UserFacingError {
      error { __typename message }
      responseContext { serverVersion }
    }
  }
}"""
        
        variables = {
            "input": {
                "anonymousUserType": "NATIVE_CLIENT_ANONYMOUS_USER_FEATURE_GATED",
                "expirationType": "NO_EXPIRATION",
                "referralCode": None
            },
            "requestContext": {
                "clientContext": {"version": self.client_version},
                "osContext": {
                    "category": self.os_category,
                    "linuxKernelVersion": None,
                    "name": self.os_name,
                    "version": self.os_version,
                }
            }
        }
        
        body = {"query": query, "variables": variables, "operationName": "CreateAnonymousUser"}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            
            # Handle GraphQL response
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            
            create_user_data = data.get("data", {}).get("createAnonymousUser", {})
            
            if create_user_data.get("__typename") == "UserFacingError":
                error = create_user_data.get("error", {})
                raise RuntimeError(f"User creation error: {error.get('message', 'Unknown error')}")
            
            id_token = create_user_data.get("idToken")
            if not id_token:
                raise RuntimeError(f"No idToken in response: {data}")
            
            return id_token
    
    async def _exchange_for_refresh_token(self, id_token: str) -> str:
        """Phase 2: Exchange ID token for refresh token"""
        url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=AIzaSyBdy3O3S9hrdayLJxJ7mriBR4qgUaUygAs"
        
        headers = {
            "accept-encoding": "gzip, br",
            "content-type": "application/x-www-form-urlencoded",
            "x-warp-client-version": self.client_version,
            "x-warp-os-category": self.os_category,
            "x-warp-os-name": self.os_name,
            "x-warp-os-version": self.os_version,
        }
        
        form_data = {
            "returnSecureToken": "true",
            "token": id_token,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, data=form_data)
            response.raise_for_status()
            data = response.json()
            
            refresh_token = data.get("refreshToken")
            if not refresh_token:
                raise RuntimeError(f"No refreshToken in response: {data}")
            
            return refresh_token
    
    async def _get_access_token(self, refresh_token: str) -> str:
        """Phase 3: Convert refresh token to access token"""
        payload = f"grant_type=refresh_token&refresh_token={refresh_token}".encode("utf-8")
        
        headers = {
            "x-warp-client-version": self.client_version,
            "x-warp-os-category": self.os_category,
            "x-warp-os-name": self.os_name,
            "x-warp-os-version": self.os_version,
            "content-type": "application/x-www-form-urlencoded",
            "accept": "*/*",
            "accept-encoding": "gzip, br",
            "content-length": str(len(payload))
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.refresh_url, headers=headers, content=payload)
            response.raise_for_status()
            data = response.json()
            
            access_token = data.get("access_token")
            if not access_token:
                raise RuntimeError(f"No access_token in response: {data}")
            
            return access_token
    
    def _save_tokens(self, access_token: str, refresh_token: str):
        """Save tokens to environment file"""
        env_path = Path(".env")
        try:
            set_key(str(env_path), "WARP_JWT", access_token)
            set_key(str(env_path), "WARP_REFRESH_TOKEN", refresh_token)
            logging.info("Tokens saved to .env file")
        except Exception as e:
            logging.error(f"Error saving tokens: {e}")
    
    async def refresh_token(self) -> str:
        """Refresh access token using stored refresh token"""
        refresh_token = os.getenv("WARP_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError("No refresh token available")
        
        access_token = await self._get_access_token(refresh_token)
        
        # Update stored access token
        env_path = Path(".env")
        set_key(str(env_path), "WARP_JWT", access_token)
        
        return access_token
    
    def is_token_expired(self, token: str, buffer_minutes: int = 5) -> bool:
        """Check if JWT token is expired or expiring within buffer time"""
        try:
            import base64
            import json
            
            parts = token.split('.')
            if len(parts) != 3:
                return True
            
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += '=' * padding
            
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(payload_bytes.decode('utf-8'))
            
            if 'exp' not in payload:
                return True
            
            expiry_time = payload['exp']
            current_time = time.time()
            buffer_time = buffer_minutes * 60
            
            return (expiry_time - current_time) <= buffer_time
            
        except Exception:
            return True
    
    async def check_usage_before_request(self, request_type: str = 'ai_requests') -> bool:
        """Check if request can be made without exceeding quota"""
        try:
            access_token = await self.get_valid_token()
            return await self.quota_manager.can_make_request(access_token, request_type)
        except Exception as e:
            logging.error(f"Error checking usage: {e}")
            return False
    
    async def get_usage_status(self) -> Dict[str, Any]:
        """Get comprehensive usage status"""
        access_token = await self.get_valid_token()
        return await self.quota_manager.get_cached_usage_status(access_token)

# Usage example
async def main():
    auth_manager = WarpAuthManager()
    
    try:
        # Get valid token (handles all refresh logic)
        token = await auth_manager.get_valid_token()
        print(f"Got token: {token[:20]}...")
        
        # Check usage before making requests
        if await auth_manager.check_usage_before_request('ai_requests'):
            print("✅ Can make AI requests")
            # Make your API calls here
        else:
            print("❌ AI request quota exceeded")
        
        # Get detailed usage status
        usage_status = await auth_manager.get_usage_status()
        print(f"Overall status: {usage_status['overall_status']}")
        
        # Handle alerts
        for alert in usage_status.get('alerts', []):
            print(f"{alert['level']}: {alert['message']}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Best Practices Summary

### Token Management
1. **Proactive Refresh**: Check token expiry 2-15 minutes before actual expiration
2. **Graceful Degradation**: Fallback to re-authentication if refresh fails
3. **Secure Storage**: Store refresh tokens securely, never log them
4. **Rotation Handling**: Always check for and handle refresh token rotation
5. **Environment Persistence**: Use `.env` files for development, secure vaults for production

### Usage Monitoring
1. **Caching**: Cache usage data for 5-10 minutes to avoid excessive API calls
2. **Threshold Alerts**: Set warning (75-80%) and critical (90-95%) thresholds
3. **Request Throttling**: Implement throttling when approaching quota limits
4. **Quota Planning**: Monitor time until reset for usage planning

### Error Handling
1. **Retry Logic**: Implement exponential backoff for transient failures
2. **Circuit Breakers**: Stop making requests after consecutive failures
3. **Fallback Strategies**: Have backup plans when authentication fails
4. **Monitoring**: Log all authentication events for debugging

### Security
1. **HTTPS Only**: All communication must use HTTPS
2. **Token Scope**: Use tokens only for intended purposes
3. **Audit Logging**: Log authentication events (not token values)
4. **Regular Rotation**: Regularly acquire fresh anonymous tokens

### Production Considerations
1. **Configuration**: Externalize all endpoints and settings
2. **Load Balancing**: Handle multiple concurrent token refreshes
3. **Health Checks**: Monitor authentication system health
4. **Graceful Shutdown**: Handle in-flight requests during shutdown

This documentation reflects the **actual implementation** in the Warp2Api codebase and provides a complete, production-ready integration guide for the Warp Anonymous Authentication system.
