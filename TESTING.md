# Testing with Warp Intercept Server

This guide explains how to test the OpenAI-compatible API with the warp intercept server.

## Architecture

The system now works with a simplified architecture:

```
OpenAI Client → OpenAI API Server (localhost:8010) → Bridge Server (localhost:8000) → Warp Intercept Server → Warp AI Service
```

### Key Changes

1. **Dummy Authentication**: The code uses dummy bearer tokens (`dummy_bearer_token_replace_by_intercept`)
2. **No SSL Verification**: SSL verification is disabled for `app.warp.dev` connections
3. **No Anonymous Token Management**: All token acquisition and refresh logic has been removed
4. **Intercept Server**: The warp intercept server replaces dummy values with real credentials

## Prerequisites

1. **Warp Intercept Server**: Must be running and configured to intercept `app.warp.dev` requests
2. **OpenAI Python SDK**: Install with `pip install openai pytest`

## Running Tests

### Quick Test

Test basic functionality:

```bash
python test_openai_quick.py
```

This runs 4 essential tests:
- Health check
- Model listing
- Simple chat completion
- Streaming chat

### Full Integration Tests

Run comprehensive tests:

```bash
# Run all tests
python test_openai_integration.py

# Or use pytest
pytest test_openai_integration.py -v

# Run specific test
pytest test_openai_integration.py::test_simple_chat_completion -v
```

Tests include:
- Health checks
- Model listing
- Simple chat completions
- Streaming responses
- System messages
- Multi-turn conversations
- Async operations
- Error handling
- Different model selections

## Configuration

### Environment Variables

```bash
# API endpoint (default: http://localhost:8010/v1)
export OPENAI_API_BASE="http://localhost:8010/v1"

# No need to set real API keys - dummy values are used
```

### Warp Intercept Server Requirements

The intercept server must:

1. Intercept connections to `app.warp.dev`
2. Replace dummy bearer token with valid JWT
3. Add real client version and OS headers
4. Handle SSL/TLS termination
5. Forward requests to actual Warp API

## Expected Behavior

### Successful Request Flow

1. Client sends request with dummy bearer token
2. Request goes to OpenAI API server (localhost:8010)
3. Server converts to protobuf and forwards to bridge (localhost:8000)
4. Bridge sends to `app.warp.dev` with dummy auth
5. Intercept server replaces dummy auth with real credentials
6. Real Warp API processes request
7. Response flows back through the chain

### Dummy Values Used

- **Bearer Token**: `dummy_bearer_token_replace_by_intercept`
- **Client Version**: `v0.2025.09.24.08.11.stable_00` (will be replaced)
- **OS Info**: Windows 11 (will be replaced)

## Test Output

Successful test output example:

```
============================================================
OPENAI API INTEGRATION TESTS
============================================================
API Base URL: http://localhost:8010/v1

📋 Running: Health Check
------------------------------------------------------------
✅ Health check passed: {'status': 'ok', 'service': '...'}
✅ Health Check PASSED

📋 Running: Simple Chat Completion
------------------------------------------------------------
✅ Chat completion response: Hello from OpenAI API test!
✅ Simple Chat Completion PASSED

...

============================================================
RESULTS: 8 passed, 0 failed
============================================================
```

## Debugging

### Enable Verbose Logging

Check server logs in `warp_server.log` and OpenAI server logs.

### Common Issues

1. **Connection Refused**
   - Ensure servers are running: `./start.sh` or manual startup
   - Check ports 8000 and 8010 are available

2. **SSL Errors**
   - Verify intercept server is properly configured
   - Check SSL verification is disabled in client code

3. **Authentication Errors**
   - Verify intercept server is replacing dummy tokens
   - Check intercept server has valid credentials

4. **Timeout Errors**
   - Increase timeout in test code
   - Check intercept server is forwarding requests

### Manual Testing with cURL

Test bridge server directly:

```bash
curl http://localhost:8000/healthz
```

Test OpenAI API server:

```bash
curl http://localhost:8010/healthz

curl http://localhost:8010/v1/models \
  -H "Authorization: Bearer dummy_key"
```

Test with OpenAI CLI:

```bash
export OPENAI_API_BASE="http://localhost:8010/v1"
export OPENAI_API_KEY="dummy_key"

openai api chat.completions.create \
  -m claude-4-sonnet \
  -g user "Hello"
```

## Performance Testing

For performance testing:

```bash
# Test with concurrent requests
python test_concurrent_connections.py

# Monitor performance
python test_performance.py
```

## Integration with CI/CD

Add to your CI pipeline:

```yaml
- name: Run OpenAI API Tests
  run: |
    # Start servers
    ./start.sh &
    sleep 10
    
    # Run tests
    python test_openai_quick.py
    
    # Cleanup
    docker-compose down
```

## Next Steps

1. Configure your warp intercept server
2. Start the API servers: `./start.sh`
3. Run quick test: `python test_openai_quick.py`
4. Run full tests: `python test_openai_integration.py`
5. Integrate with your application

## Support

For issues:
1. Check server logs in `warp_server.log`
2. Verify intercept server is running and configured
3. Test with `test_openai_quick.py` first
4. Review API documentation in `WARP.md`
