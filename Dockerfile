FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS warp2api_proxy
WORKDIR /app
ENV WARP_LOG_LEVEL=info
ENV WARP_ACCESS_LOG=true
ENV OPENAI_LOG_LEVEL=info
ENV OPENAI_ACCESS_LOG=true
# HTTP Proxy support for anonymous account creation
ENV HTTP_PROXY=

# Install curl for healthcheck and dnsmasq for DNS caching
RUN apt-get update && apt-get install -y \
    curl \
    dnsmasq \
    && rm -rf /var/lib/apt/lists/*

# Configure dnsmasq for DNS caching with Google DNS
RUN echo "# DNS Cache Configuration" > /etc/dnsmasq.conf && \
    echo "server=8.8.8.8" >> /etc/dnsmasq.conf && \
    echo "server=8.8.4.4" >> /etc/dnsmasq.conf && \
    echo "cache-size=10000" >> /etc/dnsmasq.conf && \
    echo "neg-ttl=3600" >> /etc/dnsmasq.conf && \
    echo "local-ttl=300" >> /etc/dnsmasq.conf && \
    echo "no-resolv" >> /etc/dnsmasq.conf && \
    echo "no-poll" >> /etc/dnsmasq.conf && \
    echo "interface=lo" >> /etc/dnsmasq.conf && \
    echo "bind-interfaces" >> /etc/dnsmasq.conf && \
    echo "listen-address=127.0.0.1" >> /etc/dnsmasq.conf

# Note: resolv.conf will be configured at runtime via entrypoint script

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/healthz && curl -f http://localhost:8010/healthz || exit 1

# Create a startup script to ensure dnsmasq runs before the main application
RUN echo '#!/bin/bash' > /app/docker-entrypoint.sh && \
    echo 'echo "Starting dnsmasq for DNS caching..."' >> /app/docker-entrypoint.sh && \
    echo 'dnsmasq' >> /app/docker-entrypoint.sh && \
    echo 'echo "nameserver 127.0.0.1" > /etc/resolv.conf' >> /app/docker-entrypoint.sh && \
    echo 'echo "nameserver 8.8.8.8" >> /etc/resolv.conf' >> /app/docker-entrypoint.sh && \
    echo 'echo "nameserver 8.8.4.4" >> /etc/resolv.conf' >> /app/docker-entrypoint.sh && \
    echo 'echo "DNS caching started successfully"' >> /app/docker-entrypoint.sh && \
    echo 'exec uv run ./start.py' >> /app/docker-entrypoint.sh && \
    chmod +x /app/docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"]