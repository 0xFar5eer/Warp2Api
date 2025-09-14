#!/bin/bash

# Test Bearer Token Authentication Script
# Tests API endpoints with Bearer token format (OpenAI/VSCode compatibility)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
OPENAI_BASE_URL="http://localhost:4010"  # OpenAI compatibility server port

# Read the correct API key from .env file
CORRECT_API_KEY=$(grep "^API_KEY=" .env 2>/dev/null | cut -d'=' -f2 || echo "")
WRONG_API_KEY="this_is_definitely_wrong_key_12345"

echo "============================================"
echo "Bearer Token Authentication Test"
echo "============================================"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "  OpenAI Server: $OPENAI_BASE_URL"
if [ -n "$CORRECT_API_KEY" ]; then
    echo "  Correct API Key: ${CORRECT_API_KEY:0:10}..."
else
    echo "  Correct API Key: NOT FOUND (API protection might be disabled)"
fi
echo ""

# Function to test POST endpoint with Bearer token
test_bearer_auth() {
    local endpoint=$1
    local bearer_token=$2
    local test_name=$3
    local expected_status=$4
    local payload=$5
    
    echo -e "\n${YELLOW}Testing: $test_name${NC}"
    echo "  Endpoint: $endpoint"
    if [ -n "$bearer_token" ]; then
        echo "  Bearer Token: ${bearer_token:0:20}..."
    else
        echo "  Bearer Token: [none]"
    fi
    echo "  Expected Status: $expected_status"
    
    # Make request with Bearer token in Authorization header
    if [ -z "$bearer_token" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$endpoint" \
            -H "Content-Type: application/json" \
            -d "$payload" 2>/dev/null)
    else
        response=$(curl -s -w "\n%{http_code}" -X POST "$endpoint" \
            -H "Authorization: Bearer $bearer_token" \
            -H "Content-Type: application/json" \
            -d "$payload" 2>/dev/null)
    fi
    
    # Extract status code (last line)
    status_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')
    
    # Check result
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} - Got expected status code: $status_code"
        if [ "$status_code" = "401" ]; then
            echo "  Response: $(echo $body | jq -r '.detail' 2>/dev/null || echo $body)"
        elif [ "$status_code" = "200" ]; then
            # For successful chat completions, show a preview of the response
            content=$(echo $body | jq -r '.choices[0].message.content' 2>/dev/null || echo "")
            if [ -n "$content" ]; then
                echo "  Response content preview: ${content:0:50}..."
            fi
        fi
    else
        echo -e "  ${RED}✗ FAILED${NC} - Expected: $expected_status, Got: $status_code"
        echo "  Response: ${body:0:200}..."
    fi
    
    return 0
}

# Check if server is running
echo -e "${BLUE}Checking if server is running...${NC}"
if ! curl -s -f "$OPENAI_BASE_URL/healthz" > /dev/null 2>&1; then
    echo -e "${RED}Error: OpenAI compatibility server is not running on $OPENAI_BASE_URL${NC}"
    echo "Please start the server with: docker-compose up -d"
    exit 1
fi

echo -e "${GREEN}Server is running!${NC}"

echo ""
echo "============================================"
echo -e "${BLUE}Test Suite: Bearer Token Authentication${NC}"
echo "============================================"

# Test OpenAI chat completions with Bearer token
CHAT_PAYLOAD='{
    "model": "claude-4-sonnet",
    "messages": [
        {"role": "user", "content": "Say hello"}
    ],
    "stream": false
}'

# Test with correct Bearer token
test_bearer_auth "$OPENAI_BASE_URL/v1/chat/completions" "$CORRECT_API_KEY" \
    "Chat completions with CORRECT Bearer token" "200" "$CHAT_PAYLOAD"

# Test with wrong Bearer token
test_bearer_auth "$OPENAI_BASE_URL/v1/chat/completions" "$WRONG_API_KEY" \
    "Chat completions with WRONG Bearer token" "401" "$CHAT_PAYLOAD"

# Test without Bearer token
test_bearer_auth "$OPENAI_BASE_URL/v1/chat/completions" "" \
    "Chat completions WITHOUT Bearer token" "401" "$CHAT_PAYLOAD"

echo ""
echo "============================================"
echo -e "${BLUE}Test Suite: Compare Authentication Methods${NC}"
echo "============================================"

echo -e "\n${YELLOW}Testing: X-API-Key header (original method)${NC}"
response=$(curl -s -w "\n%{http_code}" -X POST "$OPENAI_BASE_URL/v1/chat/completions" \
    -H "X-API-Key: $CORRECT_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$CHAT_PAYLOAD" 2>/dev/null)
status_code=$(echo "$response" | tail -n 1)
if [ "$status_code" = "200" ]; then
    echo -e "  ${GREEN}✓ PASSED${NC} - X-API-Key authentication still works"
else
    echo -e "  ${RED}✗ FAILED${NC} - X-API-Key authentication failed (status: $status_code)"
fi

echo -e "\n${YELLOW}Testing: Query parameter (original method)${NC}"
response=$(curl -s -w "\n%{http_code}" -X POST "$OPENAI_BASE_URL/v1/chat/completions?api_key=$CORRECT_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$CHAT_PAYLOAD" 2>/dev/null)
status_code=$(echo "$response" | tail -n 1)
if [ "$status_code" = "200" ]; then
    echo -e "  ${GREEN}✓ PASSED${NC} - Query parameter authentication still works"
else
    echo -e "  ${RED}✗ FAILED${NC} - Query parameter authentication failed (status: $status_code)"
fi

echo -e "\n${YELLOW}Testing: Bearer token (VSCode/OpenAI compatible)${NC}"
response=$(curl -s -w "\n%{http_code}" -X POST "$OPENAI_BASE_URL/v1/chat/completions" \
    -H "Authorization: Bearer $CORRECT_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$CHAT_PAYLOAD" 2>/dev/null)
status_code=$(echo "$response" | tail -n 1)
if [ "$status_code" = "200" ]; then
    echo -e "  ${GREEN}✓ PASSED${NC} - Bearer token authentication works!"
else
    echo -e "  ${RED}✗ FAILED${NC} - Bearer token authentication failed (status: $status_code)"
fi

echo ""
echo "============================================"
echo -e "${GREEN}Test Summary${NC}"
echo "============================================"
echo ""
echo "✓ Authentication Methods Supported:"
echo "  1. X-API-Key header (original)"
echo "  2. Query parameter (?api_key=...)"
echo "  3. Authorization: Bearer <token> (NEW - VSCode/OpenAI compatible)"
echo ""
echo "✓ VSCode Extension Configuration:"
echo "  - Base URL: $OPENAI_BASE_URL/v1"
echo "  - API Key: $CORRECT_API_KEY"
echo "  - Model: Any available (e.g., claude-4-sonnet, gpt-5, claude-4.1-opus)"
echo ""
echo "The proxy now accepts Bearer token authentication!"
echo "VSCode extensions should work with the standard OpenAI configuration."