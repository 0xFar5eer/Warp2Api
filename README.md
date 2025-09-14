# Warp2Api

A Python-based bridge service that provides OpenAI Chat Completions API compatibility for Warp AI services, enabling seamless integration with OpenAI-compatible applications by leveraging Warp's protobuf infrastructure.

## 🐳 Docker Compose Quick Start (Recommended)

The easiest way to run Warp2Api is using Docker Compose:

### 1. **Configure Environment Variables**

Copy the example environment file and configure your settings:
```bash
cp .env.example .env
```

Edit the `.env` file and configure your proxy settings if you're using a rotating IP proxy service:
- The proxy credentials are used internally by the Docker container
- These settings enable IP rotation for each request
- Your proxy configuration remains private and is never exposed

### 2. **Start the Service**

```bash
docker compose up -d
```

This will start both servers:
- Protobuf Bridge Server: `http://localhost:4009`
- OpenAI Compatible API: `http://localhost:4010/v1`

### 3. **Configure Your Client (VSCode Kilocode Extension Example)**

In VSCode with the Kilocode extension:
1. Go to extension settings
2. Choose "OpenAI Compatible" mode
3. Configure:
   - **Base URL**: `http://localhost:4010/v1`
   - **API Key**: `dummy` (any value works - not validated)
   - **Model**: Choose `claude-4.1-opus` or any available model

### 4. **Verify the Service**

Check if the service is running:
```bash
curl http://localhost:4010/healthz
```

Stop the service:
```bash
docker compose down
```

---

## 🚀 Features

- **OpenAI API Compatibility**: Full support for OpenAI Chat Completions API format
- **Warp Integration**: Seamless bridging with Warp AI services using protobuf communication
- **Dual Server Architecture**:
  - Protobuf encoding/decoding server for Warp communication
  - OpenAI-compatible API server for client applications
- **JWT Authentication**: Automatic token management and refresh for Warp services
- **Streaming Support**: Real-time streaming responses compatible with OpenAI SSE format
- **WebSocket Monitoring**: Built-in monitoring and debugging capabilities
- **Message Reordering**: Intelligent message handling for Anthropic-style conversations

## 📋 System Requirements

- Python 3.13+
- Access to Warp AI services (JWT token required)

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Warp2Api
   ```

2. **Install dependencies using uv (recommended):**
   ```bash
   uv sync
   ```

   Or using pip:
   ```bash
   pip install -e .
   ```

3. **Configure anonymous JWT TOKEN:**
   You can skip this step - the program will automatically request an anonymous JWT TOKEN

   Alternatively, you can create a `.env` file with your Warp credentials to use your own subscription quota, though this is not recommended:
   ```env
   WARP_JWT=your_jwt_token_here
   WARP_REFRESH_TOKEN=your_refresh_token_here
   ```

## 🎯 Usage

### Quick Start

1. **Start the Protobuf Bridge Server:**
   ```bash
   python server.py
   ```
   Default address: `http://localhost:8000`

2. **Start the OpenAI Compatible API Server:**
   ```bash
   python openai_compat.py
   ```
   Default address: `http://localhost:8010`

### Using the API

Once both servers are running, you can use any OpenAI-compatible client:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8010/v1",
    api_key="dummy"  # Not required, but some clients need it
)

response = client.chat.completions.create(
    model="claude-3-sonnet",  # Model name will be passed through
    messages=[
        {"role": "user", "content": "Hello, how are you?"}
    ],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Available Endpoints

#### Protobuf Bridge Server (`http://localhost:8000`)
- `GET /healthz` - Health check
- `POST /encode` - Encode JSON to protobuf
- `POST /decode` - Decode protobuf to JSON
- `WebSocket /ws` - Real-time monitoring

#### OpenAI API Server (`http://localhost:8010`)
- `GET /` - Service status
- `GET /healthz` - Health check
- `POST /v1/chat/completions` - OpenAI Chat Completions compatible endpoint

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Client App     │───▶│  OpenAI API     │───▶│   Protobuf      │
│  (OpenAI SDK)   │    │     Server      │    │  Bridge Server  │
└─────────────────┘    │  (Port 8010)    │    │  (Port 8000)    │
                       └─────────────────┘    └─────────────────┘
                                                       │
                                                       ▼
                                              ┌─────────────────┐
                                              │    Warp AI      │
                                              │    Service      │
                                              └─────────────────┘
```

### Core Components

- **`protobuf2openai/`**: OpenAI API compatibility layer
  - Message format conversion
  - Streaming response handling
  - Error mapping and validation

- **`warp2protobuf/`**: Warp protobuf communication layer
  - JWT authentication management
  - Protobuf encoding/decoding
  - WebSocket monitoring
  - Request routing and validation

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `WARP_JWT` | Warp authentication JWT token | Required |
| `WARP_REFRESH_TOKEN` | JWT refresh token | Required |
| `HOST` | Server host address | `127.0.0.1` |
| `PORT` | OpenAI API server port | `8010` |
| `BRIDGE_BASE_URL` | Protobuf bridge server URL | `http://localhost:8000` |

### Project Scripts

Defined in `pyproject.toml`:

```bash
# Start protobuf bridge server
warp-server

# Start OpenAI API server
warp-test
```

## 🔐 Authentication

The service automatically handles Warp authentication:

1. **JWT Management**: Automatic token validation and refresh
2. **Anonymous Access**: Falls back to anonymous tokens when needed
3. **Token Persistence**: Secure token storage and reuse

## 🧪 Development

### Project Structure

```
Warp2Api/
├── protobuf2openai/          # OpenAI API compatibility layer
│   ├── app.py               # FastAPI application
│   ├── router.py            # API routes
│   ├── models.py            # Pydantic models
│   ├── bridge.py            # Bridge initialization
│   └── sse_transform.py     # Server-sent events
├── warp2protobuf/           # Warp protobuf layer
│   ├── api/                 # API routes
│   ├── core/                # Core functionality
│   │   ├── auth.py          # Authentication
│   │   ├── protobuf_utils.py # Protobuf utilities
│   │   └── logging.py       # Logging setup
│   ├── config/              # Configuration
│   └── warp/                # Warp-specific code
├── server.py                # Protobuf bridge server
├── openai_compat.py         # OpenAI API server
└── pyproject.toml           # Project configuration
```

### Dependencies

Main dependencies include:
- **FastAPI**: Modern, fast web framework
- **Uvicorn**: ASGI server implementation
- **HTTPx**: Async HTTP client with HTTP/2 support
- **Protobuf**: Protocol buffer support
- **WebSockets**: WebSocket communication
- **OpenAI**: For type compatibility

## 🐛 Troubleshooting

### Common Issues

1. **JWT Token Expiration**
   - The service automatically refreshes tokens
   - Check logs for authentication errors
   - Verify that `WARP_REFRESH_TOKEN` is valid

2. **Bridge Server Not Ready**
   - Ensure the protobuf bridge server is running first
   - Check `BRIDGE_BASE_URL` configuration
   - Verify port availability

3. **Connection Errors**
   - Check network connectivity to Warp services
   - Verify firewall settings
   - Check proxy configuration if applicable

### Logging

Both servers provide detailed logging:
- Authentication status and token refresh
- Request/response handling
- Error details and stack traces
- Performance metrics

## 📄 License

This project is configured for internal use. Please contact the project maintainers for licensing terms.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review server logs for error details
3. Create an issue with reproduction steps