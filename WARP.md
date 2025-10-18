# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development Commands

### Quick Start (Recommended)
```bash
# One-command Docker setup (Unix/macOS)
./start.sh

# One-command Docker setup (Windows)  
start.bat
```

### Manual Development Setup
```bash
# Install dependencies
uv sync

# Start protobuf bridge server (Port 8000)
python server.py
# or
uv run warp-server

# Start OpenAI API server (Port 8010)
python openai_compat.py
# or  
uv run warp-test
```

### Docker Commands
```bash
# Force rebuild and start
docker-compose build --no-cache
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Restart services
docker-compose restart
```

### Testing Commands
```bash
# Run specific tests
python test_api_key.py
python test_concurrent_connections.py
python test_embeddings.py
python test_performance.py
python test_kilocode_integration.py

# Health checks
curl http://localhost:4009/healthz  # Bridge server
curl http://localhost:4010/healthz  # OpenAI API server

# Test with authentication
./test_api_auth.sh
./test_bearer_auth.sh
```

### Environment Configuration
```bash
# Create environment file
cp .env.example .env

# Configure API key protection (optional)
API_KEY=your-secure-key  # Leave empty to disable auth

# Configure JWT tokens (optional - auto-generated if not set)
WARP_JWT=your-jwt-token
WARP_REFRESH_TOKEN=your-refresh-token
```

## Architecture Overview

### Dual Server Architecture
The system operates with two complementary FastAPI servers:

1. **Protobuf Bridge Server** (`server.py`, Port 8000/4009)
   - Pure protobuf encoding/decoding
   - WebSocket monitoring (`/ws`)
   - Schema introspection (`/api/schemas`)
   - Warp API integration (`/api/warp/send*`)
   - JWT authentication management

2. **OpenAI Compatible API Server** (`protobuf2openai/app.py`, Port 8010/4010)
   - OpenAI Chat Completions API compatibility
   - Streaming response handling
   - Message reordering for Anthropic-style conversations
   - Model listing and management

### Request Flow
```
Client (OpenAI SDK) → OpenAI API Server → Protobuf Bridge Server → Warp AI Service
```

### Key Components

#### Core Modules
- `protobuf2openai/`: OpenAI compatibility layer
  - `router.py`: API endpoints and request handling
  - `models.py`: Pydantic models for OpenAI API types
  - `bridge.py`: Connection management and initialization
  - `sse_transform.py`: Server-sent events streaming
  - `reorder.py`: Message ordering for Anthropic format
  - `packets.py`: Warp protocol packet construction

#### Protobuf Layer
- `proto/`: Protocol buffer definitions
  - `request.proto`: Main request schema
  - `response.proto`: Response handling
  - `task.proto`, `attachment.proto`, etc.: Supporting schemas

#### Authentication System
- Dual-layer authentication:
  - API key protection (configurable via `API_KEY` env var)
  - JWT token management for Warp services (automatic refresh)
  - Anonymous token fallback when quota exhausted

#### Message Processing Pipeline
1. **Message Reordering**: Converts OpenAI format to Anthropic-style alternating user/assistant
2. **Content Normalization**: Handles text/image content in consistent format
3. **Tool Mapping**: Converts OpenAI function calls to MCP (Model Context Protocol) tools
4. **Protobuf Encoding**: JSON→Protobuf with special handling for `server_message_data`

### Special Data Handling

#### Server Message Data Encoding
The system handles special `server_message_data` fields containing:
- UUID (36-byte identifier)
- Timestamp (seconds + nanoseconds)
- Base64URL encoding/decoding with proper padding

#### Model Configuration
Supports three model categories with automatic mapping:
- **Agent Mode**: `auto` (default), `claude-4-sonnet`, `gpt-4o`, etc.
- **Planning**: `o3` (default), `gpt-5`, `claude-4-opus`, etc.
- **Coding**: `auto` (default), supports all agent models

#### MCP Tool Integration
Converts OpenAI function schemas to MCP format with:
- Input schema sanitization and validation
- Required field inference
- Type coercion for properties

### State Management
- Conversation tracking via `STATE.conversation_id`
- Task continuity with `STATE.baseline_task_id` 
- Tool ID management for consistent references
- Warmup initialization for bridge connectivity

### Error Handling & Resilience
- Automatic JWT token refresh on expiration
- Anonymous token acquisition on quota exhaustion
- Fallback bridge URL support
- Graceful degradation for unreachable services
- Request retry logic with exponential backoff

### Logging Strategy
- Separate log files: `warp_server.log` and OpenAI server logs
- Structured JSON logging for requests/responses
- Request/response payload logging (configurable)
- Error tracking with full stack traces

## Important Implementation Notes

### OpenAI Compatibility
- Full support for streaming and non-streaming responses
- Bearer token authentication (extracts from `Authorization: Bearer token`)
- Model listing endpoint (`/v1/models`) with fallback to local models
- Chat completions endpoint (`/v1/chat/completions`) with tool support

### Docker Considerations
- Multi-stage build optimized for Python 3.13
- Health checks on both ports (4009, 4010)
- DNS configuration for reliable external connections
- Proxy support with localhost bypass
- Volume mounting for persistent logs

### Security Features
- Configurable API key protection (can be disabled for development)
- JWT token automatic refresh and management
- Proxy credential handling (never exposed in logs)
- TLS verification (configurable for development)

### Development Workflow
1. Use `./start.sh` for quick Docker setup with automatic prerequisite checking
2. For active development, run servers manually to see immediate code changes
3. Use WebSocket endpoint `/ws` for real-time request monitoring
4. Check `/api/packets/history` for debugging recent requests
5. Use schema endpoint `/api/schemas` to inspect protobuf definitions

### Performance Optimizations
- HTTP/2 support via httpx
- Connection pooling and keep-alive
- Request caching for health checks and model listings
- Optimized protobuf encoding/decoding
- Uvloop async event loop for better performance