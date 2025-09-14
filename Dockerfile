FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS warp2api_proxy
WORKDIR /app
ENV WARP_LOG_LEVEL=info
ENV WARP_ACCESS_LOG=true
ENV OPENAI_LOG_LEVEL=info
ENV OPENAI_ACCESS_LOG=true
# HTTP Proxy support for anonymous account creation
ENV HTTP_PROXY=

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/healthz && curl -f http://localhost:8010/healthz || exit 1

CMD ["uv", "run", "./start.py"]