#!/usr/bin/env bash
# Generate RSA keypair for MCP server per-user authentication (MCP_AUTH_MODE=ibmi).
#
# Creates secrets/private.pem and secrets/public.pem.
# The secrets/ directory is gitignored — never commit these files.
#
# Usage:
#   ./scripts/generate_mcp_keys.sh
#   ./scripts/generate_mcp_keys.sh 4096   # Use 4096-bit key (default: 2048)

set -euo pipefail

KEY_BITS="${1:-2048}"
SECRETS_DIR="$(cd "$(dirname "$0")/.." && pwd)/secrets"

mkdir -p "$SECRETS_DIR"

echo "Generating ${KEY_BITS}-bit RSA keypair in ${SECRETS_DIR}/ ..."

# Generate private key
openssl genpkey -algorithm RSA \
    -out "$SECRETS_DIR/private.pem" \
    -pkeyopt "rsa_keygen_bits:${KEY_BITS}" 2>/dev/null

# Extract public key
openssl rsa -pubout \
    -in "$SECRETS_DIR/private.pem" \
    -out "$SECRETS_DIR/public.pem" 2>/dev/null

# Set restrictive permissions
chmod 600 "$SECRETS_DIR/private.pem"
chmod 644 "$SECRETS_DIR/public.pem"
chmod 700 "$SECRETS_DIR"

echo "Done."
echo "  Private key: $SECRETS_DIR/private.pem (600)"
echo "  Public key:  $SECRETS_DIR/public.pem  (644)"
echo ""
echo "Add to .env:"
echo "  MCP_AUTH_MODE=ibmi"
echo "  IBMI_HTTP_AUTH_ENABLED=true"
echo "  IBMI_AUTH_KEY_ID=ibmi-agentos"
