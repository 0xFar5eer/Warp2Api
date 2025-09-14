FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS warp2api_proxy
WORKDIR /app
ENV WARP_LOG_LEVEL=info
ENV WARP_ACCESS_LOG=true
ENV OPENAI_LOG_LEVEL=info
ENV OPENAI_ACCESS_LOG=true
# HTTP Proxy support for anonymous account creation
ENV HTTP_PROXY=
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .
CMD ["uv", "run", "./start.py"]