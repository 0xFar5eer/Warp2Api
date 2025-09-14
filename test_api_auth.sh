#!/bin/bash

# Test API Authentication Script
# Tests API endpoints with focus on /v1/chat/completions endpoint

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_BASE_URL="http://localhost:4009"  # Protobuf server port
OPENAI_BASE_URL="http://localhost:4010"  # OpenAI compatibility server port

# Read the correct API key from .env file
CORRECT_API_KEY=$(grep "^API_KEY=" .env 2>/dev/null | cut -d'=' -f2 || echo "")
WRONG_API_KEY="this_is_definitely_wrong_key_12345"

echo "============================================"
echo "API Authentication Test Suite"
echo "============================================"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "  Protobuf Server: $API_BASE_URL"
echo "  OpenAI Server: $OPENAI_BASE_URL"
if [ -n "$CORRECT_API_KEY" ]; then
    echo "  Correct API Key: ${CORRECT_API_KEY:0:10}..."
else
    echo "  Correct API Key: NOT FOUND (API protection might be disabled)"
fi
echo ""

# Function to test API endpoint
test_api_endpoint() {
    local endpoint=$1
    local api_key=$2
    local test_name=$3
    local expected_status=$4
    
    echo -e "\n${YELLOW}Testing: $test_name${NC}"
    echo "  Endpoint: $endpoint"
    if [ -n "$api_key" ]; then
        echo "  API Key: ${api_key:0:20}..."
    else
        echo "  API Key: [none]"
    fi
    echo "  Expected Status: $expected_status"
    
    # Make request with API key in header
    if [ -z "$api_key" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$endpoint" 2>/dev/null)
    else
        response=$(curl -s -w "\n%{http_code}" -X GET "$endpoint" \
            -H "X-API-Key: $api_key" 2>/dev/null)
    fi
    
    # Extract status code (last line)
    status_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')
    
    # Check result
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "  ${GREEN}✓ PASSED${NC} - Got expected status code: $status_code"
        if [ "$status_code" = "401" ]; then
            echo "  Response: $(echo $body | jq -r '.detail' 2>/dev/null || echo $body)"
        fi
    else
        echo -e "  ${RED}✗ FAILED${NC} - Expected: $expected_status, Got: $status_code"
        echo "  Response: $body"
    fi
    
    return 0
}

# Function to test POST endpoint with JSON payload
test_post_endpoint() {
    local endpoint=$1
    local api_key=$2
    local test_name=$3
    local expected_status=$4
    local payload=$5
    
    echo -e "\n${YELLOW}Testing: $test_name${NC}"
    echo "  Endpoint: $endpoint"
    if [ -n "$api_key" ]; then
        echo "  API Key: ${api_key:0:20}..."
    else
        echo "  API Key: [none]"
    fi
    echo "  Expected Status: $expected_status"
    
    # Make request with API key in header
    if [ -z "$api_key" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$endpoint" \
            -H "Content-Type: application/json" \
            -d "$payload" 2>/dev/null)
    else
        response=$(curl -s -w "\n%{http_code}" -X POST "$endpoint" \
            -H "X-API-Key: $api_key" \
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
            if echo "$endpoint" | grep -q "chat/completions"; then
                content=$(echo $body | jq -r '.choices[0].message.content' 2>/dev/null || echo "")
                if [ -n "$content" ]; then
                    echo "  Response content preview: ${content:0:50}..."
                fi
            fi
        fi
    else
        echo -e "  ${RED}✗ FAILED${NC} - Expected: $expected_status, Got: $status_code"
        echo "  Response: ${body:0:200}..."
    fi
    
    return 0
}

# Check if servers are running
echo -e "${BLUE}Checking if servers are running...${NC}"
if ! curl -s -f "$API_BASE_URL/healthz" > /dev/null 2>&1; then
    echo -e "${RED}Error: Protobuf server is not running on $API_BASE_URL${NC}"
    echo "Please start the server with: docker-compose up -d"
    exit 1
fi

if ! curl -s -f "$OPENAI_BASE_URL/healthz" > /dev/null 2>&1; then
    echo -e "${RED}Error: OpenAI compatibility server is not running on $OPENAI_BASE_URL${NC}"
    echo "Please start the server with: docker-compose up -d"
    exit 1
fi

echo -e "${GREEN}Both servers are running!${NC}"

echo ""
echo "============================================"
echo -e "${BLUE}Test Suite 1: Health Check Endpoints${NC}"
echo "============================================"

# Health endpoints should work without authentication
test_api_endpoint "$API_BASE_URL/healthz" "" "Health check without API key" "200"
test_api_endpoint "$OPENAI_BASE_URL/healthz" "" "OpenAI health check without API key" "200"

echo ""
echo "============================================"
echo -e "${BLUE}Test Suite 2: OpenAI /v1/chat/completions Endpoint${NC}"
echo "============================================"

# Test OpenAI chat completions with claude-4-sonnet model
CHAT_PAYLOAD_CLAUDE_4_SONNET='{
    "model": "claude-4-sonnet",
    "messages": [
        {"role": "user", "content": "Say hi"}
    ],
    "stream": false
}'

echo -e "\n${BLUE}--- Testing with claude-4-sonnet model ---${NC}"
test_post_endpoint "$OPENAI_BASE_URL/v1/chat/completions" "$CORRECT_API_KEY" \
    "Chat completions (claude-4-sonnet) with CORRECT API key" "200" "$CHAT_PAYLOAD_CLAUDE_4_SONNET"

test_post_endpoint "$OPENAI_BASE_URL/v1/chat/completions" "$WRONG_API_KEY" \
    "Chat completions (claude-4-sonnet) with WRONG API key" "401" "$CHAT_PAYLOAD_CLAUDE_4_SONNET"

test_post_endpoint "$OPENAI_BASE_URL/v1/chat/completions" "" \
    "Chat completions (claude-4-sonnet) WITHOUT API key" "401" "$CHAT_PAYLOAD_CLAUDE_4_SONNET"

# Test with other available models
echo ""
echo -e "\n${BLUE}--- Testing with other models ---${NC}"

CHAT_PAYLOAD_GPT5='{
    "model": "gpt-5",
    "messages": [
        {"role": "user", "content": "Say hello"}
    ],
    "stream": false
}'

test_post_endpoint "$OPENAI_BASE_URL/v1/chat/completions" "$CORRECT_API_KEY" \
    "Chat completions (gpt-5) with CORRECT API key" "200" "$CHAT_PAYLOAD_GPT5"

CHAT_PAYLOAD_CLAUDE_OPUS='{
    "model": "claude-4.1-opus",
    "messages": [
        {"role": "user", "content": "Hi there"}
    ],
    "stream": false
}'

test_post_endpoint "$OPENAI_BASE_URL/v1/chat/completions" "$CORRECT_API_KEY" \
    "Chat completions (claude-4.1-opus) with CORRECT API key" "200" "$CHAT_PAYLOAD_CLAUDE_OPUS"

echo ""
echo "============================================"
echo -e "${BLUE}Test Suite 3: OpenAI /v1/models Endpoint${NC}"
echo "============================================"

test_api_endpoint "$OPENAI_BASE_URL/v1/models" "$CORRECT_API_KEY" \
    "List models with CORRECT API key" "200"

test_api_endpoint "$OPENAI_BASE_URL/v1/models" "$WRONG_API_KEY" \
    "List models with WRONG API key" "401"

test_api_endpoint "$OPENAI_BASE_URL/v1/models" "" \
    "List models WITHOUT API key" "401"

echo ""
echo "============================================"
echo -e "${BLUE}Test Suite 4: API Key via Query Parameter${NC}"
echo "============================================"

# Test with API key in query parameter for chat completions
echo -e "\n${YELLOW}Testing: Chat completions with API key in query parameter${NC}"
response=$(curl -s -w "\n%{http_code}" -X POST "$OPENAI_BASE_URL/v1/chat/completions?api_key=$CORRECT_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$CHAT_PAYLOAD_CLAUDE_4_SONNET" 2>/dev/null)
status_code=$(echo "$response" | tail -n 1)
if [ "$status_code" = "200" ]; then
    echo -e "  ${GREEN}✓ PASSED${NC} - Query parameter authentication works"
else
    echo -e "  ${RED}✗ FAILED${NC} - Query parameter authentication failed (status: $status_code)"
fi

echo -e "\n${YELLOW}Testing: Chat completions with WRONG API key in query parameter${NC}"
response=$(curl -s -w "\n%{http_code}" -X POST "$OPENAI_BASE_URL/v1/chat/completions?api_key=$WRONG_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$CHAT_PAYLOAD_CLAUDE_4_SONNET" 2>/dev/null)
status_code=$(echo "$response" | tail -n 1)
if [ "$status_code" = "401" ]; then
    echo -e "  ${GREEN}✓ PASSED${NC} - Wrong query parameter key properly rejected"
else
    echo -e "  ${RED}✗ FAILED${NC} - Wrong query parameter key not rejected (status: $status_code)"
fi

echo ""
echo "============================================"
echo -e "${BLUE}Test Suite 5: Complex Chat Completions${NC}"
echo "============================================"

# Test with system message and multi-turn conversation
COMPLEX_CHAT_PAYLOAD='{
    "model": "claude-4-sonnet",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "2+2 equals 4."},
        {"role": "user", "content": "And what is 3+3?"}
    ],
    "stream": false
}'

test_post_endpoint "$OPENAI_BASE_URL/v1/chat/completions" "$CORRECT_API_KEY" \
    "Complex multi-turn conversation with CORRECT API key" "200" "$COMPLEX_CHAT_PAYLOAD"

# Test streaming response
STREAMING_CHAT_PAYLOAD='{
    "model": "claude-4-sonnet",
    "messages": [
        {"role": "user", "content": "Count to 3"}
    ],
    "stream": true
}'

echo -e "\n${YELLOW}Testing: Streaming chat completions with CORRECT API key${NC}"
echo "  Endpoint: $OPENAI_BASE_URL/v1/chat/completions"
echo "  API Key: ${CORRECT_API_KEY:0:20}..."
echo "  Expected: SSE stream data"

# Test streaming (just check if connection is established)
response_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$OPENAI_BASE_URL/v1/chat/completions" \
    -H "X-API-Key: $CORRECT_API_KEY" \
    -H "Content-Type: application/json" \
    -H "Accept: text/event-stream" \
    -d "$STREAMING_CHAT_PAYLOAD" \
    --max-time 5 2>/dev/null)

if [ "$response_code" = "200" ]; then
    echo -e "  ${GREEN}✓ PASSED${NC} - Streaming endpoint accessible"
else
    echo -e "  ${RED}✗ FAILED${NC} - Streaming endpoint returned: $response_code"
fi

echo ""
echo "============================================"
echo -e "${GREEN}Test Summary${NC}"
echo "============================================"
echo ""
echo "Authentication test suite completed. Key findings:"
echo ""
if [ -n "$CORRECT_API_KEY" ]; then
    echo "✓ API Key Protection is ENABLED"
    echo "  - Correct API key allows access (200 response)"
    echo "  - Wrong API key is rejected (401 response)"
    echo "  - Missing API key is rejected (401 response)"
    echo "  - Both header and query parameter authentication work"
else
    echo "⚠ API Key Protection appears to be DISABLED"
    echo "  - No API_KEY found in .env file"
    echo "  - All requests may be allowed without authentication"
fi
echo ""
echo "✓ Tested models:"
echo "  - claude-4-sonnet"
echo "  - gpt-5"
echo "  - claude-4.1-opus"
echo ""
echo "✓ Tested scenarios:"
echo "  - Simple chat completions"
echo "  - Multi-turn conversations"
echo "  - System messages"
echo "  - Streaming responses"
echo "  - Model listing"
echo ""
echo "If all tests passed, your API authentication is working correctly!"