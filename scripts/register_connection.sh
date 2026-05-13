#!/usr/bin/env bash
# Register an IBM i system connection with the AgentOS API.
#
# Usage:
#   curl -sL <raw-url>/scripts/register_connection.sh | bash -s -- \
#       --host my-ibmi.com --user MYUSER --password MYPASS --token sk_abc123
#
#   # Or if you have the repo:
#   ./scripts/register_connection.sh --host my-ibmi.com --user MYUSER --token sk_abc123
#
#   # Minimal (prompts for password, uses env vars for token/url):
#   export AGENTOS_API_TOKEN=sk_abc123
#   ./scripts/register_connection.sh --host my-ibmi.com --user MYUSER
#
# Environment variables:
#   AGENTOS_API_URL     Base URL (default: http://localhost:8000)
#   AGENTOS_API_TOKEN   Bearer token (API key)

set -euo pipefail

# Defaults
API_URL="${AGENTOS_API_URL:-http://localhost:8000}"
TOKEN="${AGENTOS_API_TOKEN:-}"
HOST=""
PORT=8076
USER=""
PASSWORD=""
NAME=""
IS_DEFAULT=false
SKIP_TEST=false
JSON_OUTPUT=false

usage() {
    cat <<'EOF'
Usage: register_connection.sh [OPTIONS]

Register an IBM i system connection with the AgentOS API.

Required:
  --host HOST         IBM i hostname or IP
  --user USER         IBM i user profile

Optional:
  --password PASS     IBM i password (prompts if omitted)
  --token TOKEN       API bearer token (or set AGENTOS_API_TOKEN)
  --url URL           API base URL (or set AGENTOS_API_URL, default: http://localhost:8000)
  --port PORT         Mapepire port (default: 8076)
  --name NAME         Connection name (default: USER@HOST)
  --default           Set as the default connection
  --skip-test         Skip connection test after registering
  --json              Output raw JSON
  -h, --help          Show this help
EOF
    exit 0
}

die() { echo "Error: $1" >&2; exit 1; }

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)      HOST="$2"; shift 2 ;;
        --user)      USER="$2"; shift 2 ;;
        --password)  PASSWORD="$2"; shift 2 ;;
        --token)     TOKEN="$2"; shift 2 ;;
        --url)       API_URL="$2"; shift 2 ;;
        --port)      PORT="$2"; shift 2 ;;
        --name)      NAME="$2"; shift 2 ;;
        --default)   IS_DEFAULT=true; shift ;;
        --skip-test) SKIP_TEST=true; shift ;;
        --json)      JSON_OUTPUT=true; shift ;;
        -h|--help)   usage ;;
        *)           die "Unknown option: $1" ;;
    esac
done

# Validate required args
[[ -z "$HOST" ]] && die "Missing --host"
[[ -z "$USER" ]] && die "Missing --user"
[[ -z "$TOKEN" ]] && die "Missing --token (or set AGENTOS_API_TOKEN)"

# Prompt for password if not provided
if [[ -z "$PASSWORD" ]]; then
    if [[ -t 0 ]]; then
        read -rsp "Password for ${USER}@${HOST}: " PASSWORD
        echo
        [[ -z "$PASSWORD" ]] && die "Password is required"
    else
        die "Missing --password (required when not running interactively)"
    fi
fi

# Default connection name
[[ -z "$NAME" ]] && NAME="${USER}@${HOST}"

API_URL="${API_URL%/}"

# --- Register ---

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/auth/connections" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(cat <<ENDJSON
{
  "name": "$NAME",
  "host": "$HOST",
  "port": $PORT,
  "user": "$USER",
  "password": "$PASSWORD",
  "is_default": $IS_DEFAULT
}
ENDJSON
)")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

# Handle "already exists"
if [[ "$HTTP_CODE" == "409" ]]; then
    echo "Connection '${NAME}' already exists. Looking up existing..." >&2
    LIST_RESP=$(curl -s -X GET "${API_URL}/auth/connections" \
        -H "Authorization: Bearer ${TOKEN}")

    # Extract connection ID by name (portable — no jq required)
    if command -v jq &>/dev/null; then
        CONN_ID=$(echo "$LIST_RESP" | jq -r ".[] | select(.name == \"$NAME\") | .id")
        BODY=$(echo "$LIST_RESP" | jq -c ".[] | select(.name == \"$NAME\")")
    else
        # Fallback: grep for the ID near the name
        CONN_ID=$(echo "$LIST_RESP" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        BODY="$LIST_RESP"
    fi

    if [[ -z "$CONN_ID" ]]; then
        die "Could not find existing connection '${NAME}'"
    fi
    echo "Using existing connection: ${CONN_ID}"
    HTTP_CODE="200"
elif [[ "$HTTP_CODE" != "201" ]]; then
    die "Failed to create connection (HTTP ${HTTP_CODE}): ${BODY}"
fi

# Extract connection ID
if command -v jq &>/dev/null; then
    CONN_ID=$(echo "$BODY" | jq -r '.id')
else
    CONN_ID=$(echo "$BODY" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
fi

# --- Test ---

if [[ "$SKIP_TEST" != "true" ]]; then
    echo "Connection registered: ${CONN_ID}"
    echo "Testing connection to ${HOST}..."

    TEST_RESP=$(curl -s -X POST "${API_URL}/auth/connections/${CONN_ID}/test" \
        -H "Authorization: Bearer ${TOKEN}")

    if command -v jq &>/dev/null; then
        SUCCESS=$(echo "$TEST_RESP" | jq -r '.success')
        MESSAGE=$(echo "$TEST_RESP" | jq -r '.message')
    else
        SUCCESS=$(echo "$TEST_RESP" | grep -o '"success":true' | head -1)
        MESSAGE=$(echo "$TEST_RESP" | grep -o '"message":"[^"]*"' | head -1 | cut -d'"' -f4)
        [[ -n "$SUCCESS" ]] && SUCCESS="true" || SUCCESS="false"
    fi

    if [[ "$SUCCESS" == "true" ]]; then
        echo "Connection test: OK"
    else
        echo "Connection test: FAILED — ${MESSAGE}" >&2
        echo "The connection was registered but could not authenticate." >&2
        echo "Check your credentials and ensure the MCP server is configured for auth." >&2
        exit 1
    fi
fi

# --- Output ---

if [[ "$JSON_OUTPUT" == "true" ]]; then
    if command -v jq &>/dev/null; then
        echo "$BODY" | jq .
    else
        echo "$BODY"
    fi
else
    echo ""
    echo "  Connection ID:  ${CONN_ID}"
    echo "  Name:           ${NAME}"
    echo "  Host:           ${HOST}:${PORT}"
    echo "  User:           ${USER}"
    echo "  Default:        ${IS_DEFAULT}"
    echo ""
    echo "Your agents will now use this connection for IBM i access."
fi
