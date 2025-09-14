#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to update API_KEY in .env file
update_env_file() {
    local api_key_value="$1"
    if [ -z "$api_key_value" ]; then
        # Set empty API_KEY
        sed -i '' 's/^API_KEY=.*/API_KEY=/' .env
        echo -e "${YELLOW}Updated .env: API_KEY=(empty)${NC}"
    else
        # Set specific API_KEY
        sed -i '' "s/^API_KEY=.*/API_KEY=$api_key_value/" .env
        echo -e "${YELLOW}Updated .env: API_KEY=$api_key_value${NC}"
    fi
}

# Function to wait for services to be healthy
wait_for_services() {
    local max_attempts=60  # 60 seconds maximum wait
    local attempt=0
    
    echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
    
    while [ $attempt -lt $max_attempts ]; do
        # Check health on both ports
        health_4009=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:4009/healthz" 2>/dev/null)
        health_4010=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:4010/healthz" 2>/dev/null)
        
        if [ "$health_4009" == "200" ] && [ "$health_4010" == "200" ]; then
            echo -e "${GREEN}✓ Services are healthy (both ports responding)${NC}"
            return 0
        fi
        
        attempt=$((attempt + 1))
        echo -ne "\rWaiting for services... ($attempt/$max_attempts seconds)"
        sleep 1
    done
    
    echo -e "\n${RED}✗ Services failed to become healthy after $max_attempts seconds${NC}"
    echo -e "${RED}  Port 4009 status: $health_4009${NC}"
    echo -e "${RED}  Port 4010 status: $health_4010${NC}"
    return 1
}

# Function to restart Docker Compose
restart_docker() {
    echo -e "${YELLOW}Restarting Docker Compose...${NC}"
    docker-compose down > /dev/null 2>&1
    docker-compose up -d > /dev/null 2>&1
    
    # Wait for services to be healthy
    if ! wait_for_services; then
        echo -e "${RED}Failed to start services properly. Exiting.${NC}"
        exit 1
    fi
    
    # Additional delay after services are healthy
    echo -e "${YELLOW}Waiting additional 30 seconds for services to fully initialize...${NC}"
    for i in {30..1}; do
        echo -ne "\rWaiting... $i seconds remaining  "
        sleep 1
    done
    echo -e "\n${GREEN}✓ Services ready for testing${NC}"
}

# Function to test API endpoint with authentication
test_api_auth() {
    local port="$1"
    local api_key="$2"
    local expect_auth="$3"  # "allow" or "deny"
    
    # Use protected endpoints that require API key authentication
    local url=""
    local body=""
    if [ "$port" == "4009" ]; then
        # Use /api/encode endpoint which has API key protection
        url="http://localhost:${port}/api/encode"
        body='{"json_data":{}}'
    else
        # Port 4010: Use /v1/chat/completions endpoint which has API key protection
        url="http://localhost:${port}/v1/chat/completions"
        body='{"messages":[{"role":"user","content":"test"}],"model":"test"}'
    fi
    
    # Execute curl and capture status code with POST request
    if [ ! -z "$api_key" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "X-API-Key: $api_key" -H "Content-Type: application/json" -d "$body" "$url" 2>/dev/null)
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "$body" "$url" 2>/dev/null)
    fi
    
    # Check if authentication worked as expected
    if [ "$expect_auth" == "deny" ]; then
        # Should get 401 Unauthorized
        if [ "$response" == "401" ]; then
            echo -e "${GREEN}✓ Port $port: PASSED (Got expected 401 Unauthorized)${NC}"
            return 0
        else
            echo -e "${RED}✗ Port $port: FAILED (Expected 401, got $response)${NC}"
            return 1
        fi
    else
        # Should NOT get 401 (may get other errors like 400/502 due to minimal payload)
        if [ "$response" != "401" ]; then
            echo -e "${GREEN}✓ Port $port: PASSED (Authorized, got $response)${NC}"
            return 0
        else
            echo -e "${RED}✗ Port $port: FAILED (Got unexpected 401 Unauthorized)${NC}"
            return 1
        fi
    fi
}

# Main test execution
echo "========================================="
echo "API Key Authentication Test Suite"
echo "========================================="

passed_tests=0
total_tests=0

# Test 1: Empty API_KEY, no auth required
echo -e "\n${YELLOW}Test 1: Empty API_KEY, no auth required${NC}"
echo "Expected: All requests should be authorized (not return 401)"
update_env_file ""
restart_docker

test_api_auth 4009 "" "allow" && ((passed_tests++))
((total_tests++))
test_api_auth 4010 "" "allow" && ((passed_tests++))
((total_tests++))

# Test 2: Set API_KEY, no key provided
echo -e "\n${YELLOW}Test 2: API_KEY set to 'test_secret_123', no key provided${NC}"
echo "Expected: Requests should fail with 401 Unauthorized"
update_env_file "test_secret_123"
restart_docker

test_api_auth 4009 "" "deny" && ((passed_tests++))
((total_tests++))
test_api_auth 4010 "" "deny" && ((passed_tests++))
((total_tests++))

# Test 3: Set API_KEY, wrong key provided
echo -e "\n${YELLOW}Test 3: API_KEY set, wrong key provided${NC}"
echo "Expected: Requests should fail with 401 Unauthorized"

test_api_auth 4009 "wrong_key" "deny" && ((passed_tests++))
((total_tests++))
test_api_auth 4010 "wrong_key" "deny" && ((passed_tests++))
((total_tests++))

# Test 4: Set API_KEY, correct key provided
echo -e "\n${YELLOW}Test 4: API_KEY set, correct key provided${NC}"
echo "Expected: Requests should be authorized (not return 401)"

test_api_auth 4009 "test_secret_123" "allow" && ((passed_tests++))
((total_tests++))
test_api_auth 4010 "test_secret_123" "allow" && ((passed_tests++))
((total_tests++))

# Test 5: Reset to empty API_KEY
echo -e "\n${YELLOW}Test 5: Reset to empty API_KEY${NC}"
echo "Expected: All requests should be authorized (not return 401)"
update_env_file ""
restart_docker

test_api_auth 4009 "" "allow" && ((passed_tests++))
((total_tests++))
test_api_auth 4010 "" "allow" && ((passed_tests++))
((total_tests++))

# Summary
echo -e "\n========================================="
echo "TEST SUMMARY"
echo "========================================="
echo -e "Results: ${passed_tests}/${total_tests} tests passed"

if [ $passed_tests -eq $total_tests ]; then
    echo -e "${GREEN}✓ All tests passed! API key authentication is working correctly.${NC}"
    echo -e "\n${GREEN}Summary:${NC}"
    echo -e "  • Empty API_KEY allows all requests"
    echo -e "  • Set API_KEY enforces authentication"
    echo -e "  • Wrong API key returns 401 Unauthorized"
    echo -e "  • Correct API key allows access"
    echo -e "  • Configuration changes apply after Docker restart"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please check the output above.${NC}"
    exit 1
fi