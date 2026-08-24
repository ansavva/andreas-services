#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUMBUGG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$HUMBUGG_DIR/infra/envs/dev"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/humbugg"
MACHINE_ID_FILE="$CONFIG_DIR/machine-id"

AWS_PROFILE_VALUE="${AWS_PROFILE:-default}"
AWS_REGION_VALUE="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

log()  { printf '\033[1;34m[dev-aws]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command '$1' is not installed."
}

aws_dev() {
  aws --no-cli-pager --profile "$AWS_PROFILE_VALUE" --region "$AWS_REGION_VALUE" "$@"
}

load_machine_id() {
  local create_if_missing="${1:-false}"
  if [[ ! -f "$MACHINE_ID_FILE" ]]; then
    [[ "$create_if_missing" == "true" ]] ||
      die "No machine ID exists. Run ./humbugg/scripts/dev-aws-setup.sh first."
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
    if command -v uuidgen >/dev/null 2>&1; then
      uuidgen | tr '[:upper:]' '[:lower:]' > "$MACHINE_ID_FILE"
    elif command -v openssl >/dev/null 2>&1; then
      local hex
      hex="$(openssl rand -hex 16)"
      printf '%s-%s-%s-%s-%s\n' \
        "${hex:0:8}" "${hex:8:4}" "${hex:12:4}" "${hex:16:4}" "${hex:20:12}" \
        > "$MACHINE_ID_FILE"
    else
      die "Either uuidgen or openssl is required to generate the machine ID."
    fi
    chmod 600 "$MACHINE_ID_FILE"
    ok "Generated machine ID at $MACHINE_ID_FILE."
  fi

  MACHINE_ID="$(tr -d '[:space:]' < "$MACHINE_ID_FILE" | tr '[:upper:]' '[:lower:]')"
  [[ "$MACHINE_ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] ||
    die "Invalid machine ID in $MACHINE_ID_FILE."
  MACHINE_SHORT_ID="$(printf '%s' "$MACHINE_ID" | tr -d '-' | cut -c1-12)"
}

load_aws_identity() {
  local identity
  identity="$(aws_dev sts get-caller-identity --output json)" ||
    die "Could not authenticate with AWS profile '$AWS_PROFILE_VALUE'."
  AWS_ACCOUNT_ID="$(jq -r '.Account' <<<"$identity")"
  AWS_PRINCIPAL_ARN="$(jq -r '.Arn' <<<"$identity")"
  [[ "$AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || die "AWS returned an invalid account ID."
  MACHINE_NAME="$(hostname -s 2>/dev/null || hostname)"
  RESOURCE_PREFIX="humbugg-dev-$MACHINE_SHORT_ID"
  STATE_KEY="humbugg/dev/$AWS_ACCOUNT_ID/$MACHINE_ID/terraform.tfstate"
}

set_terraform_vars() {
  TF_VARS=(
    "-var=aws_region=$AWS_REGION_VALUE"
    "-var=aws_account_id=$AWS_ACCOUNT_ID"
    "-var=aws_principal_arn=$AWS_PRINCIPAL_ARN"
    "-var=machine_id=$MACHINE_ID"
    "-var=machine_short_id=$MACHINE_SHORT_ID"
    "-var=machine_name=$MACHINE_NAME"
  )
}

export_temporary_aws_credentials() {
  local credentials
  # Make the selected profile resolve its current session before exporting credentials. This lets
  # SSO/credential-process profiles refresh their cached role credentials instead of copying a stale
  # set into the long-running backend container.
  aws_dev sts get-caller-identity >/dev/null ||
    die "AWS profile '$AWS_PROFILE_VALUE' does not currently have a valid session. Sign in to AWS and try again."
  credentials="$(aws configure export-credentials --profile "$AWS_PROFILE_VALUE" --format process)" ||
    die "AWS CLI could not export temporary credentials for profile '$AWS_PROFILE_VALUE'."
  export AWS_ACCESS_KEY_ID="$(jq -r '.AccessKeyId' <<<"$credentials")"
  export AWS_SECRET_ACCESS_KEY="$(jq -r '.SecretAccessKey' <<<"$credentials")"
  export AWS_SESSION_TOKEN="$(jq -r '.SessionToken // empty' <<<"$credentials")"
  export AWS_CREDENTIAL_EXPIRATION="$(jq -r '.Expiration // empty' <<<"$credentials")"
  aws --no-cli-pager --region "$AWS_REGION_VALUE" sts get-caller-identity >/dev/null ||
    die "AWS CLI exported invalid or expired credentials for profile '$AWS_PROFILE_VALUE'. Sign in to AWS and try again."
  if [[ -n "$AWS_CREDENTIAL_EXPIRATION" ]]; then
    log "AWS credentials refreshed; they expire at $AWS_CREDENTIAL_EXPIRATION."
  else
    log "AWS credentials refreshed."
  fi
}

terraform_init() {
  export AWS_REGION="$AWS_REGION_VALUE"
  export_temporary_aws_credentials
  terraform -chdir="$TF_DIR" init -reconfigure -input=false \
    -backend-config="key=$STATE_KEY"
  set_terraform_vars
}

terraform_output_json() {
  terraform -chdir="$TF_DIR" output -json
}

# The dev stack's test account, and the file its password lives in. Mirrors
# studio's `dev-aws-common.sh` deliberately: the two services had no shared
# convention for this and studio's is the one that already works.
#
# **The address is committed and the password never can be.** `.test` is a
# reserved TLD (RFC 2606), so this can never be a real mailbox and Cognito can
# never mail a stranger on a typo — which is what makes hard-coding it safe.
# Humbugg's pool allows self-signup, so this account is a convenience rather
# than the only way in; what it buys is a *known* account, identical on every
# machine, that a test or a scripted sign-in can rely on.
#
# The password file sits outside the repo on purpose. A default here would be a
# credential in a git history.
HUMBUGG_DEV_USER_EMAIL="dev@humbugg.test"
DEV_ENV_FILE="$CONFIG_DIR/dev.env"

load_dev_user_password() {
  # Never echoed, and never interpolated into a log line or a command echo.
  local prompt_allowed="${1:-true}"
  local generate="${2:-false}"
  if [[ -z "${HUMBUGG_DEV_USER_PASSWORD:-}" && -f "$DEV_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
  fi
  if [[ -z "${HUMBUGG_DEV_USER_PASSWORD:-}" && "$generate" == "true" ]]; then
    # 24 hex characters plus a fixed upper/lower/digit tail, because the pool
    # requires all three classes and `openssl rand -hex` alone can produce a
    # string with no uppercase. 24 hex + 3 clears the 12-character floor with
    # room to spare. Written before it is used, so a re-run against an existing
    # stack converges the same password rather than minting a second one
    # nothing has recorded.
    require_command openssl
    umask 077
    mkdir -p "$CONFIG_DIR"
    printf 'HUMBUGG_DEV_USER_PASSWORD=%s\n' "$(openssl rand -hex 12)Aa1" > "$DEV_ENV_FILE"
    chmod 600 "$DEV_ENV_FILE"
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
    ok "Generated the dev account password into $DEV_ENV_FILE (not printed)."
  fi
  if [[ -z "${HUMBUGG_DEV_USER_PASSWORD:-}" ]]; then
    [[ "$prompt_allowed" == "true" ]] ||
      die "HUMBUGG_DEV_USER_PASSWORD is not set and $DEV_ENV_FILE provides none."
    printf 'Password for %s (not echoed): ' "$HUMBUGG_DEV_USER_EMAIL" >&2
    read -rs HUMBUGG_DEV_USER_PASSWORD
    printf '\n' >&2
  fi
}
