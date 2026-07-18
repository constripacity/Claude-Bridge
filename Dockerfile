# Claude Bridge — official container image.
#
# Two stages so the final image carries no build toolchain: stage 1 builds a
# wheel, stage 2 installs just that wheel into a slim runtime.
#
#   docker build -t claude-bridge .
# Network mode fails closed: declare the Host value clients use and require a
# Bearer token. With retention + audit:
#   export CLAUDE_BRIDGE_AUTH_TOKEN="$(openssl rand -hex 32)"
#   docker run -p 8765:8765 -v claude-bridge-data:/data \
#     -e CLAUDE_BRIDGE_AUTH_TOKEN \
#     -e CLAUDE_BRIDGE_TRUSTED_HOSTS=100.100.20.30 \
#     claude-bridge --host 0.0.0.0 --port 8765 \
#       --retention-days 30 --audit-log

FROM python:3.12-slim AS build
WORKDIR /src
COPY . .
RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /dist

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.source="https://github.com/constripacity/Claude-Bridge" \
      org.opencontainers.image.title="Claude Bridge" \
      org.opencontainers.image.description="Local-first, cross-machine MCP relay for independent coding agents." \
      org.opencontainers.image.licenses="MIT"

# Run unprivileged. /data holds the SQLite store and is the documented volume.
RUN useradd --create-home --uid 10001 bridge \
    && mkdir -p /data \
    && chown bridge:bridge /data
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

USER bridge
WORKDIR /home/bridge
ENV CLAUDE_BRIDGE_DB=/data/claude-bridge.db \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8765

# Healthcheck hits the unauthenticated /status endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/status', timeout=2).status==200 else 1)"

# The container listens on its network interface, but startup fails until the
# operator supplies CLAUDE_BRIDGE_TRUSTED_HOSTS and authentication (or the
# explicit --allow-unauthenticated-network escape hatch). No wildcard Host or
# unauthenticated policy is baked into the image.
ENTRYPOINT ["claude-bridge"]
CMD ["--host", "0.0.0.0", "--port", "8765"]
