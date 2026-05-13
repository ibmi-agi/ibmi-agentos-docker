# ===========================================================================
# AgentOS Template
# ===========================================================================

# ---------------------------------------------------------------------------
# ibmi CLI builder — installs @ibm/ibmi-cli (npm) in a throwaway Node image,
# then we copy just the artifact + Node runtime into the Python stage below.
# Lets the runtime image use the bundled `ibmi` binary when
# IBMI_CLI_MODE=true, with no npm toolchain bloat. Override version via:
#   docker compose build --build-arg IBMI_CLI_VERSION=0.5.2
# ---------------------------------------------------------------------------
FROM node:20-slim AS node-builder
ARG IBMI_CLI_VERSION=0.5.1
RUN npm install -g "@ibm/ibmi-cli@${IBMI_CLI_VERSION}"

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM agnohq/python:3.12

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# ibmi CLI binary (from node-builder stage)
# ---------------------------------------------------------------------------
COPY --from=node-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=node-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/@ibm/ibmi-cli/dist/index.js /usr/local/bin/ibmi

# ---------------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------------
WORKDIR /app
ENV PYTHONPATH=/app
COPY requirements.txt ./
RUN uv pip sync requirements.txt --system
COPY . .

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
RUN chmod +x /app/scripts/entrypoint.sh
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

# ---------------------------------------------------------------------------
# Default command (overridden by compose for dev)
# ---------------------------------------------------------------------------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
