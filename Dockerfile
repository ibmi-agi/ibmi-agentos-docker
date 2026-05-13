# ===========================================================================
# IBM i AgentOS — slim runtime image (~500 MB target, down from ~1.5 GB)
# ===========================================================================
#
# Three build stages:
#   1. node-builder   — globally install @ibm/ibmi-cli, prune devDeps
#   2. py-builder     — uv pip install into /opt/venv, then strip caches
#   3. runtime        — python:3.12-slim + COPY-only the venv and the CLI
#
# Override the bundled ibmi CLI version:
#   docker compose build --build-arg IBMI_CLI_VERSION=0.5.2
# ===========================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Node builder for the bundled IBM i CLI
# ---------------------------------------------------------------------------
FROM node:20-slim AS node-builder
ARG IBMI_CLI_VERSION=0.5.1
RUN npm install -g --omit=dev "@ibm/ibmi-cli@${IBMI_CLI_VERSION}" \
    && cd /usr/local/lib/node_modules/@ibm/ibmi-cli \
    && (npm prune --omit=dev || true) \
    && find . \( -name '*.md' -o -name '*.markdown' -o -name '*.ts' \
                 -o -name '*.map' -o -name 'LICENSE*' -o -name 'CHANGELOG*' \
                 -o -name '.eslintrc*' -o -name '.prettierrc*' \
                 -o -name 'tsconfig*' -o -name 'jest.config*' \) -delete \
    && find . -type d \( -name 'test' -o -name 'tests' -o -name '__tests__' \
                          -o -name 'docs' -o -name 'examples' \) \
        -exec rm -rf {} + 2>/dev/null || true \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
              /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

# ---------------------------------------------------------------------------
# Stage 2 — Python builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS py-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && UV_NO_CACHE=1 uv pip install \
        --python /opt/venv/bin/python \
        --no-cache \
        -r requirements.txt \
    && find /opt/venv -type d -name '__pycache__' -exec rm -rf {} + \
    && find /opt/venv -type d -name 'tests' -exec rm -rf {} + \
    && find /opt/venv -type d -name 'test' -exec rm -rf {} + \
    && find /opt/venv -name '*.pyc' -delete \
    && find /opt/venv -name '*.pyo' -delete \
    && /opt/venv/bin/python -m pip uninstall -y pip setuptools wheel 2>/dev/null || true \
    && rm -rf /root/.cache

# ---------------------------------------------------------------------------
# Stage 3 — Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Curl is occasionally useful for health checks; nothing else needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python venv (~270 MB) — already pruned in the builder
COPY --from=py-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# IBM i CLI (~80 MB after pruning)
COPY --from=node-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=node-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/@ibm/ibmi-cli/dist/index.js /usr/local/bin/ibmi

WORKDIR /app
COPY . .
RUN chmod +x /app/scripts/entrypoint.sh

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
