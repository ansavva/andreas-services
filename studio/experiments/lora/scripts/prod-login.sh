#!/usr/bin/env bash
# Sign the studio CLI into PRODUCTION, for pulling a character's references
# into the LoRA lab. The sanctioned pieces, in one place:
#
#   - pool + client ids: SSM, same parameters create-user.sh reads
#     (needs `aws login` — the AWS CLI half, no export required for SSM reads
#     via the CLI)
#   - credentials: ~/.config/andreas-services/studio/prod.env
#     (STUDIO_PROD_USER_EMAIL / STUDIO_PROD_USER_PASSWORD)
#   - API URL: the CLI's default IS prod, so nothing to set
#
# The token cache (~/.config/andreas-services/studio/credentials) is
# single-slot: this login displaces a dev-stack session. `studio login`
# against the dev pool afterwards puts it back.
set -euo pipefail

# `studio` is the pipeline venv's console script; dev-setup.sh puts it on PATH
# only inside Claude sessions, so resolve it here for a plain terminal.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if command -v studio >/dev/null 2>&1; then
  studio() { command studio "$@"; }
else
  STUDIO_BIN="$STUDIO_DIR/pipeline/.venv/bin/studio"
  [ -x "$STUDIO_BIN" ] || { echo "no studio CLI at $STUDIO_BIN — run studio/scripts/dev-setup.sh once" >&2; exit 1; }
  studio() { "$STUDIO_BIN" "$@"; }
fi

REGION="${AWS_REGION:-us-east-1}"
PROD_ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/studio/prod.env"

[ -f "$PROD_ENV_FILE" ] || { echo "missing $PROD_ENV_FILE" >&2; exit 1; }
# shellcheck source=/dev/null
. "$PROD_ENV_FILE"
: "${STUDIO_PROD_USER_EMAIL:?not set in $PROD_ENV_FILE}"
: "${STUDIO_PROD_USER_PASSWORD:?not set in $PROD_ENV_FILE}"

pool_id=$(aws ssm get-parameter --name /studio/prod/cognito-user-pool-id \
  --query Parameter.Value --output text --region "$REGION")
client_id=$(aws ssm get-parameter --name /studio/prod/cognito-client-id \
  --query Parameter.Value --output text --region "$REGION")

STUDIO_COGNITO_USER_POOL_ID="$pool_id" \
STUDIO_COGNITO_CLIENT_ID="$client_id" \
STUDIO_API_URL="https://studio-api.andreas.services" \
STUDIO_PASSWORD="$STUDIO_PROD_USER_PASSWORD" \
  studio login --email "$STUDIO_PROD_USER_EMAIL"

studio whoami
