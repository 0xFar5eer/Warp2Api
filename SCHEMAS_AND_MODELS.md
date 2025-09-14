# Warp2Api Schemas and Models (No API Token Protection)

## Overview

This document outlines the available schemas and models in the Warp2Api project that can be accessed without API token protection when `API_KEY_REQUIRED` is set to `false` in the environment variables.

## Available AI Models

The project supports multiple AI models across three categories. All models support vision capabilities and have a usage multiplier of 1.

### Agent Mode Models

| Model ID | Display Name | Description | Default |
|----------|-------------|-------------|---------|
| `auto` | auto | Claude 4 Sonnet | ✅ |
| `warp-basic` | lite | Basic model | |
| `gpt-5` | gpt-5 | GPT-5 model | |
| `claude-4-sonnet` | claude 4 sonnet | Claude 4 Sonnet | |
| `claude-4-opus` | claude 4 opus | Claude 4 Opus | |
| `claude-4.1-opus` | claude 4.1 opus | Claude 4.1 Opus | |
| `gpt-4o` | gpt-4o | GPT-4o model | |
| `gpt-4.1` | gpt-4.1 | GPT-4.1 model | |
| `o4-mini` | o4-mini | O4 Mini model | |
| `o3` | o3 | O3 model | |
| `gemini-2.5-pro` | gemini 2.5 pro | Gemini 2.5 Pro | |

### Planning Models

| Model ID | Display Name | Description | Default |
|----------|-------------|-------------|---------|
| `o3` | o3 | O3 model | ✅ |
| `warp-basic` | lite | Basic model | |
| `gpt-5 (high reasoning)` | gpt-5 | High reasoning | |
| `claude-4-opus` | claude 4 opus | Claude 4 Opus | |
| `claude-4.1-opus` | claude 4.1 opus | Claude 4.1 Opus | |
| `gpt-4.1` | gpt-4.1 | GPT-4.1 model | |
| `o4-mini` | o4-mini | O4 Mini model | |

### Coding Models

| Model ID | Display Name | Description | Default |
|----------|-------------|-------------|---------|
| `auto` | auto | Claude 4 Sonnet | ✅ |
| `warp-basic` | lite | Basic model | |
| `gpt-5` | gpt-5 | GPT-5 model | |
| `claude-4-sonnet` | claude 4 sonnet | Claude 4 Sonnet | |
| `claude-4-opus` | claude 4 opus | Claude 4 Opus | |
| `claude-4.1-opus` | claude 4.1 opus | Claude 4.1 Opus | |
| `gpt-4o` | gpt-4o | GPT-4o model | |
| `gpt-4.1` | gpt-4.1 | GPT-4.1 model | |
| `o4-mini` | o4-mini | O4 Mini model | |
| `o3` | o3 | O3 model | |
| `gemini-2.5-pro` | gemini 2.5 pro | Gemini 2.5 Pro | |

## Model Configuration

Models are configured using a simple pattern:

```json
{
  "base": "model-name",    // Base model for general tasks
  "planning": "o3",         // Planning model (defaults to o3)
  "coding": "auto"          // Coding model (defaults to auto)
}
```

The system automatically maps known models and falls back to "auto" for unknown model names.

## Protobuf Schemas

### 1. Request Schema (`proto/request.proto`)

The main request message structure includes:

```protobuf
message Request {
    TaskContext task_context     // Task history and active task
    Input input                   // User inputs and tool results
    Settings settings            // Model configuration
    Metadata metadata            // Conversation ID and logging
    Suggestions existing_suggestions
    MCPContext mcp_context       // MCP tools and resources
}
```

**Key Components:**

- **TaskContext**: Contains task history and active task ID
- **Input**: Supports multiple input types:
  - UserInputs (user queries with attachments)
  - QueryWithCannedResponse (predefined responses)
  - AutoCodeDiffQuery
  - ResumeConversation
  - InitProjectRules
  - ToolCallResult (results from tool executions)

- **Settings**: Model configuration including:
  - Model config (base, planning, coding)
  - Feature flags (rules_enabled, web_context_retrieval_enabled, etc.)
  - Supported tools and capabilities

- **MCPContext**: Model Context Protocol support:
  - Resources (URI, name, description, mime_type)
  - Tools (name, description, input_schema)

### 2. Response Schema (`proto/response.proto`)

Handles streaming responses and events from the Warp API.

### 3. Task Schema (`proto/task.proto`)

Defines task structure and management.

### 4. Attachment Schema (`proto/attachment.proto`)

Manages file attachments and references.

### 5. Citations Schema (`proto/citations.proto`)

Handles citation tracking and references.

### 6. Additional Schemas

- `proto/suggestions.proto` - Suggestion handling
- `proto/options.proto` - Configuration options
- `proto/input_context.proto` - Input context management
- `proto/file_content.proto` - File content handling
- `proto/debug.proto` - Debug information
- `proto/todo.proto` - Todo list management

## Public API Endpoints (No API Key Required)

When `API_KEY_REQUIRED=false`, these endpoints are publicly accessible:

### General Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Server information |
| `/healthz` | GET | Health check status |

### Schema Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/schemas` | GET | List all available protobuf schemas with field information |

### Protobuf Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/encode` | POST | Encode JSON to protobuf bytes |
| `/api/decode` | POST | Decode protobuf bytes to JSON |
| `/api/stream-decode` | POST | Decode streaming protobuf chunks |

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/status` | GET | Check JWT authentication status |
| `/api/auth/refresh` | POST | Refresh JWT token |
| `/api/auth/user_id` | GET | Get current user ID |

### Warp API Integration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/warp/send` | POST | Send request to Warp API |
| `/api/warp/send_stream` | POST | Send request with parsed event stream |
| `/api/warp/send_stream_sse` | POST | Send request with SSE streaming |

### Monitoring

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/packets/history` | GET | View packet history (last 100) |
| `/ws` | WebSocket | Real-time packet monitoring |

## API Key Configuration

The API key requirement is controlled by the `API_KEY_REQUIRED` environment variable:

```bash
# Disable API key protection (public access)
API_KEY_REQUIRED=false

# Enable API key protection (requires X-API-Key header)
API_KEY_REQUIRED=true
API_KEYS=your-api-key-1,your-api-key-2
```

When API key protection is enabled, requests must include:
```
X-API-Key: your-api-key
```

## Request/Response Examples

### Encode JSON to Protobuf

**Request:**
```json
POST /api/encode
{
  "message_type": "warp.multi_agent.v1.Request",
  "input": {
    "user_inputs": {
      "inputs": [{
        "user_query": {
          "query": "Hello, world!"
        }
      }]
    }
  },
  "settings": {
    "model_config": {
      "base": "claude-4-sonnet",
      "planning": "o3",
      "coding": "auto"
    }
  }
}
```

**Response:**
```json
{
  "protobuf_bytes": "base64-encoded-bytes",
  "size": 256,
  "message_type": "warp.multi_agent.v1.Request"
}
```

### Decode Protobuf to JSON

**Request:**
```json
POST /api/decode
{
  "protobuf_bytes": "base64-encoded-bytes",
  "message_type": "warp.multi_agent.v1.Request"
}
```

**Response:**
```json
{
  "json_data": {
    "input": {...},
    "settings": {...}
  },
  "size": 256,
  "message_type": "warp.multi_agent.v1.Request"
}
```

### Get Available Schemas

**Request:**
```
GET /api/schemas
```

**Response:**
```json
{
  "schemas": [
    {
      "name": "warp.multi_agent.v1.Request",
      "full_name": "warp.multi_agent.v1.Request",
      "field_count": 6,
      "fields": [...]
    },
    ...
  ],
  "total_count": 15,
  "message": "Found 15 protobuf message types"
}
```

## WebSocket Real-time Monitoring

Connect to `/ws` for real-time packet monitoring:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.event === 'packet_captured') {
    console.log('New packet:', data.packet);
  }
};
```

## Server Message Data Encoding

The system handles special `server_message_data` fields that contain:
- UUID
- Timestamp (seconds and nanos)

These are automatically encoded/decoded during protobuf operations.

## Environment Variables

Key environment variables for configuration:

```bash
# API Key Protection
API_KEY_REQUIRED=false    # Set to true to enable protection
API_KEYS=key1,key2        # Comma-separated list of valid keys

# JWT Configuration
WARP_JWT=your-jwt-token
WARP_REFRESH_TOKEN=your-refresh-token

# Proxy Configuration (optional)
HTTP_PROXY=http://proxy:port
PROXY_USER=username
PROXY_PASS=password
PROXY_HOST=proxy.example.com
PROXY_PORT=8080

# TLS Configuration
WARP_INSECURE_TLS=false   # Set to true to disable TLS verification
```

## OpenAI Compatibility

The system provides OpenAI-compatible model listings through the [`get_all_unique_models()`](warp2protobuf/config/models.py:288) function, which returns models in OpenAI's format:

```json
{
  "id": "claude-4-sonnet",
  "object": "model",
  "created": 1234567890,
  "owned_by": "warp",
  "display_name": "claude 4 sonnet",
  "description": "Claude 4 Sonnet",
  "vision_supported": true,
  "usage_multiplier": 1,
  "categories": ["agent", "coding"]
}
```

## Security Notes

1. **API Key Protection**: When disabled, all endpoints become publicly accessible. Enable in production environments.

2. **JWT Token Management**: The system automatically refreshes JWT tokens when they expire or are close to expiring.

3. **Anonymous Access**: When quota is exhausted, the system can acquire anonymous access tokens for continued operation.

4. **Proxy Support**: Full proxy support for all HTTP requests with automatic bypass for localhost connections.

5. **TLS Verification**: Can be disabled for development but should be enabled in production.

## Rate Limiting

When the Warp API returns a 429 (quota exhausted) error, the system automatically:
1. Attempts to acquire an anonymous access token
2. Retries the request with the new token
3. Updates the environment with the new credentials

## Conclusion

This system provides a comprehensive interface to the Warp AI API with flexible authentication options. When API key protection is disabled, all features are publicly accessible, making it suitable for development and testing environments. For production use, enable API key protection and configure appropriate security measures.