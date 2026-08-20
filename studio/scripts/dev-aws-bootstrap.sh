#!/usr/bin/env bash
# Provision a studio dev stack, give it its test account, and prove a real
# Cognito token can be minted against it. One command, from a cold checkout.
#
# **This exists because the pieces it chains cannot be run from the machine that
# wrote them.** `dev-aws-setup.sh`, `dev-user.sh` and `dev-token.sh` all need a
# live AWS session, and #289's integration tests need a provisioned stack to
# point at. This is the entry point for an environment that has credentials.
#
# ── What it creates, and what that costs ────────────────────────────────────
#
# A Cognito user pool, an S3 bucket and a DynamoDB table, all named
# `studio-dev-<short12>-*`, in the same account as prod. Pennies a month while
# empty. **There is no teardown script yet** — `dev-aws-destroy.sh` is #286 —
# so removing this is `terraform destroy` with the same machine id, and the
# `--report` output tells you exactly how.
#
# ── The machine id, and why it is pinned ────────────────────────────────────
#
# The stack is keyed to a UUID that `dev-aws-common.sh` keeps at
# `~/.config/andreas-services/studio/machine-id`. On an ephemeral environment
# that file dies with the container and the stack becomes unreachable: still
# running, still billing, and its Terraform state key unguessable.
#
# So the id is an input here, not a side effect. Pass `--machine-id`, or set
# `STUDIO_DEV_MACHINE_ID`. If you pass neither, one is generated and printed in
# a box you must save — that is the only chance to record it.
#
# ── The password never leaves this machine ──────────────────────────────────
#
# The dev account's password is generated here, written to
# `~/.config/andreas-services/studio/dev.env` (mode 600, outside the repo), and
# never printed, never logged, never put in argv. The report says whether a
# token was obtained, not what it was.
#
# Usage:
#   ./studio/scripts/dev-aws-bootstrap.sh --check         # tooling + identity only, no writes
#   ./studio/scripts/dev-aws-bootstrap.sh --machine-id UUID
#   ./studio/scripts/dev-aws-bootstrap.sh                 # generates and prints an id
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

CHECK_ONLY=0
MACHINE_ID_INPUT="${STUDIO_DEV_MACHINE_ID:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --machine-id) [[ $# -ge 2 ]] || die "--machine-id requires a value."; MACHINE_ID_INPUT="$2"; shift ;;
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --check) CHECK_ONLY=1 ;;
    --help|-h)
      printf 'Usage: %s [--machine-id UUID] [--profile NAME] [--region REGION] [--check]\n' "$0"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

# ── 1. Report the environment before doing anything to it ───────────────────
#
# A missing tool should be one clear line at the start, not a failure four
# minutes into a Terraform apply. `--check` stops here, which is what makes it
# safe to run first on an environment nobody has characterised.

log "Checking tooling."
missing=()
for command in aws jq terraform uv; do
  command -v "$command" >/dev/null 2>&1 || missing+=("$command")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  die "Missing: ${missing[*]}. Install them, or run --check to see the rest of the report."
fi
ok "aws, jq, terraform, uv all present."

load_aws_identity
log "AWS account:   $AWS_ACCOUNT_ID"
log "AWS principal: $AWS_PRINCIPAL_ARN"
log "AWS region:    $AWS_REGION_VALUE"
[[ "$AWS_ACCOUNT_ID" == "704202188703" ]] ||
  warn "This is not the andreas.services account. Continuing, but nothing here will match prod."

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  ok "Environment can run this script. Re-run without --check to provision."
  exit 0
fi

# ── 2. Pin the machine id ───────────────────────────────────────────────────

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
if [[ -n "$MACHINE_ID_INPUT" ]]; then
  [[ "$MACHINE_ID_INPUT" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] ||
    die "--machine-id must be a lowercase UUID."
  printf '%s\n' "$MACHINE_ID_INPUT" > "$MACHINE_ID_FILE"
  chmod 600 "$MACHINE_ID_FILE"
  log "Using the machine id you supplied."
elif [[ -f "$MACHINE_ID_FILE" ]]; then
  log "Reusing the machine id already on this machine."
else
  # `load_machine_id true` generates one, but generating it *here* is what lets
  # the box below print it before anything is built on top of it.
  load_machine_id true >/dev/null
fi
load_machine_id false

printf '\n╔══════════════════════════════════════════════════════════════════╗\n'
printf '║  SAVE THIS. It is the only handle on the stack about to exist.   ║\n'
printf '║                                                                  ║\n'
printf '║    machine id: %-50s║\n' "$MACHINE_ID"
printf '║                                                                  ║\n'
printf '║  Re-run or tear down from anywhere with:                         ║\n'
printf '║    --machine-id <the value above>                                ║\n'
printf '╚══════════════════════════════════════════════════════════════════╝\n\n'

# ── 3. The dev account password, generated and kept off the wire ────────────
#
# Written before the pool exists so a re-run against an existing stack converges
# the same password rather than minting a second one nothing has recorded.

if [[ ! -f "$DEV_ENV_FILE" ]] || ! grep -q "STUDIO_DEV_USER_PASSWORD=" "$DEV_ENV_FILE" 2>/dev/null; then
  # 24 hex characters plus a fixed upper/lower/digit tail, because the pool
  # requires all three classes and `openssl rand -hex` alone can produce a
  # string with no uppercase.
  generated="$(openssl rand -hex 12)Aa1"
  umask 077
  printf 'STUDIO_DEV_USER_PASSWORD=%s\n' "$generated" > "$DEV_ENV_FILE"
  unset generated
  chmod 600 "$DEV_ENV_FILE"
  ok "Generated the dev account password into $DEV_ENV_FILE (not printed)."
else
  log "Reusing the password already in $DEV_ENV_FILE."
fi

# ── 4. Provision, seed the account, prove a token ───────────────────────────

log "Provisioning the dev stack. This is a real terraform apply and takes a few minutes."
"$SCRIPT_DIR/dev-aws-setup.sh" --yes --profile "$AWS_PROFILE_VALUE" --region "$AWS_REGION_VALUE"

log "Converging the dev test account."
"$SCRIPT_DIR/dev-user.sh" --profile "$AWS_PROFILE_VALUE" --region "$AWS_REGION_VALUE"

log "Minting an ID token by SRP — the step that has never been proven end to end."
token="$("$SCRIPT_DIR/dev-token.sh" --no-prompt --profile "$AWS_PROFILE_VALUE" --region "$AWS_REGION_VALUE")"

# The claims, never the token. A JWT payload is base64url with the padding
# stripped, so it is re-added before decoding.
payload="$(printf '%s' "$token" | cut -d. -f2)"
case $(( ${#payload} % 4 )) in 2) payload="${payload}==";; 3) payload="${payload}=";; esac
claims="$(printf '%s' "$payload" | tr '_-' '/+' | base64 -d 2>/dev/null || true)"
unset token payload

printf '\n'
ok "A REAL DEV-POOL ID TOKEN WAS OBTAINED. Claims below; the token itself is not printed."
printf '%s' "$claims" | jq '{token_use, aud, iss, email, sub_present: (.sub != null), exp}' 2>/dev/null ||
  warn "Token obtained but its claims could not be decoded — jq or base64 differs here."

load_dev_stack_outputs
printf '\nStack:\n  pool     %s\n  client   %s\n  bucket   s3://%s/\n  table    %s\n' \
  "$DEV_POOL_ID" "$DEV_CLIENT_ID" "$DEV_BUCKET" "$DEV_TABLE"
printf '\nTear down later with:\n  ./studio/scripts/dev-aws-bootstrap.sh --machine-id %s --check\n' "$MACHINE_ID"
printf '  terraform -chdir=studio/infra/envs/dev destroy \\\n'
printf '    -backend-config="key=%s"\n' "$STATE_KEY"
printf '\nPaste the block above back into the session. It contains no secrets.\n'
