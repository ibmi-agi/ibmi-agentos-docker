# ===========================================================================
# IBM i AgentOS — slim runtime image (~500 MB target, down from ~1.5 GB)
# ===========================================================================
#
# Two build stages:
#   1. py-builder     — uv pip install into /opt/venv, then strip caches
#   2. runtime        — python:3.12-slim + COPY-only the venv
# ===========================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Python builder
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
# Stage 2 — Runtime
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

WORKDIR /app
COPY . .
RUN chmod +x /app/scripts/entrypoint.sh

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
