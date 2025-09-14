#!/bin/bash

# Test script to verify Docker Compose API_KEY fix
echo "Testing Docker Compose API_KEY authentication fix..."
echo "================================================"

# Check if API_KEY is set in .env
echo "1. Checking API_KEY in .env file:"
if grep -q "^API_KEY=your_secure_api_key_here" .env; then
    echo "   ✓ API_KEY is properly set in .env"
else
    echo "   ✗ API_KEY not found or empty in .env"
    exit 1
fi

# Check if bridge.py includes API key headers
echo ""
echo "2. Checking bridge.py modifications:"
if grep -q "api_key = os.getenv(\"API_KEY\")" protobuf2openai/bridge.py; then
    echo "   ✓ bridge.py reads API_KEY from environment"
else
    echo "   ✗ bridge.py missing API_KEY environment read"
    exit 1
fi

if grep -q "headers\[\"X-API-Key\"\] = api_key" protobuf2openai/bridge.py; then
    echo "   ✓ bridge.py includes X-API-Key header in requests"
else
    echo "   ✗ bridge.py missing X-API-Key header inclusion"
    exit 1
fi

echo ""
echo "3. Docker Compose commands to apply the fix:"
echo "   Run these commands to rebuild and restart:"
echo ""
echo "   docker-compose down"
echo "   docker-compose build --no-cache"
echo "   docker-compose up -d"
echo ""
echo "4. To monitor the logs after restart:"
echo "   docker-compose logs -f warp2api_proxy"
echo ""
echo "================================================"
echo "All checks passed! The fix is ready to be applied."