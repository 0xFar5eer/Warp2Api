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

# Function to test API endpoint
test_api() {
    local port="$1"
    local api_key="$2"
    local expected_status="$3"
    
    # Use protected endpoints that require API key authentication
    local url=""
    if [ "$port" == "4009" ]; then
        # Use /api/encode endpoint which has API key protection
        url="http://localhost:${port}/api/encode"
    else
        # Port 4010: Use /v1/chat/completions endpoint which has API key protection
        url="http://localhost:${port}/v1/chat/completions"
    fi
    
    local headers=""
    
    if [ ! -z "$api_key" ]; then
        headers="-H \"X-API-Key: $api_key\""
    fi
    
    # Execute curl and capture status code with POST request and minimal body
    if [ "$port" == "4009" ]; then
        # For /api/encode endpoint
        if [ ! -z "$api_key" ]; then
            response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "X-API-Key: $api_key" -H "Content-Type: application/json" -d '{"json_data":{}}' "$url" 2>/dev/null)
        else
            response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"json_data":{}}' "$url" 2>/dev/null)
        fi
    else
        # For /v1/chat/completions endpoint
        if [ ! -z "$api_key" ]; then
            response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "X-API-Key: $api_key" -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"test"}],"model":"test"}' "$url" 2>/dev/null)
        else
            response=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"test"}],"model":"test"}' "$url" 2>/dev/null)
        fi
    fi
    
    if [ "$response" == "$expected_status" ]; then
        echo -e "${GREEN}✓ Port $port: PASSED (Got expected $response)${NC}"
        return 0
    else
        echo -e "${RED}✗ Port $port: FAILED (Expected $expected_status, got $response)${NC}"
        # Debug: Check if container is seeing the env variable
        echo -e "${YELLOW}  Debug: Checking container environment...${NC}"
        docker-compose exec -T warp2api_proxy sh -c 'echo "    API_KEY in container: \"$API_KEY\""' 2>/dev/null || echo "    Could not check container env"
        return 1
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
echo "Expected: All requests should succeed (200)"
update_env_file ""
restart_docker

test_api 4009 "" 200 && ((passed_tests++))
((total_tests++))
test_api 4010 "" 200 && ((passed_tests++))
((total_tests++))

# Test 2: Set API_KEY, no key provided
echo -e "\n${YELLOW}Test 2: API_KEY set to 'test_secret_123', no key provided${NC}"
echo "Expected: Requests should fail (401)"
update_env_file "test_secret_123"
restart_docker

test_api 4009 "" 401 && ((passed_tests++))
((total_tests++))
test_api 4010 "" 401 && ((passed_tests++))
((total_tests++))

# Test 3: Set API_KEY, wrong key provided
echo -e "\n${YELLOW}Test 3: API_KEY set, wrong key provided${NC}"
echo "Expected: Requests should fail (401)"

test_api 4009 "wrong_key" 401 && ((passed_tests++))
((total_tests++))
test_api 4010 "wrong_key" 401 && ((passed_tests++))
((total_tests++))

# Test 4: Set API_KEY, correct key provided
echo -e "\n${YELLOW}Test 4: API_KEY set, correct key provided${NC}"
echo "Expected: Requests should succeed (200)"

test_api 4009 "test_secret_123" 200 && ((passed_tests++))
((total_tests++))
test_api 4010 "test_secret_123" 200 && ((passed_tests++))
((total_tests++))

# Test 5: Reset to empty API_KEY
echo -e "\n${YELLOW}Test 5: Reset to empty API_KEY${NC}"
echo "Expected: All requests should succeed (200)"
update_env_file ""
restart_docker

test_api 4009 "" 200 && ((passed_tests++))
((total_tests++))
test_api 4010 "" 200 && ((passed_tests++))
((total_tests++))

# Summary
echo -e "\n========================================="
echo "TEST SUMMARY"
echo "========================================="
echo -e "Results: ${passed_tests}/${total_tests} tests passed"

if [ $passed_tests -eq $total_tests ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please check the output above.${NC}"
    exit 1
fi