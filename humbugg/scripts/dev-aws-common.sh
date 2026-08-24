#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HUMBUGG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$HUMBUGG_DIR/infra/envs/dev"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/humbugg"
MACHINE_ID_FILE="$CONFIG_DIR/machine-id"

AWS_PROFILE_VALUE="${AWS_PROFILE:-default}"
AWS_REGION_VALUE="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARGS=()
AWS_PROFILE_RESOLVED=0

log()  { printf '\033[1;34m[dev-aws]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command '$1' is not installed."
}

aws_dev() {
  aws --no-cli-pager ${AWS_PROFILE_ARGS[@]+"${AWS_PROFILE_ARGS[@]}"} \
    --region "$AWS_REGION_VALUE" "$@"
}

resolve_aws_profile() {
  # Decide once whether to name a profile at all. Ported from
  # `studio/scripts/dev-aws-common.sh`, which hit this first.
  #
  # **`--profile default` is not a harmless way of saying "the usual
  # credentials".** Naming a profile makes the CLI resolve *that profile* and
  # stop; it will not fall back to `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
  # in the environment. So on a machine whose credentials arrive as environment
  # variables — CI, a container, a Claude cloud session — every call here failed
  # `NoCredentials` while a bare `aws sts get-caller-identity` two lines earlier
  # succeeded, because `~/.aws/config` had a `[default]` section holding
  # settings but no keys. The error names credentials, so it reads as an expired
  # session and invites a sign-in that cannot fix it.
  #
  # The fallback is deliberately narrow: it triggers only when the named profile
  # resolves *no* credentials and ambient ones *do* work. A profile that
  # authenticates is always used as given, so this can never silently retarget a
  # working profile at a different account.
  [[ "$AWS_PROFILE_RESOLVED" -eq 1 ]] && return 0
  AWS_PROFILE_RESOLVED=1

  if [[ -z "$AWS_PROFILE_VALUE" ]]; then
    AWS_PROFILE_ARGS=()
    return 0
  fi

  AWS_PROFILE_ARGS=(--profile "$AWS_PROFILE_VALUE")
  aws --no-cli-pager --profile "$AWS_PROFILE_VALUE" --region "$AWS_REGION_VALUE" \
    sts get-caller-identity >/dev/null 2>&1 && return 0

  # `env -u AWS_PROFILE` because an exported AWS_PROFILE would steer this probe
  # too, and then it would not be testing ambient credentials at all.
  env -u AWS_PROFILE aws --no-cli-pager --region "$AWS_REGION_VALUE" \
    sts get-caller-identity >/dev/null 2>&1 || return 0

  warn "Profile '$AWS_PROFILE_VALUE' resolves no credentials, but the environment does. Using those."
  AWS_PROFILE_ARGS=()
  AWS_PROFILE_VALUE=""
  # Drop it from the environment as well, not just from our own argv. A stale
  # exported AWS_PROFILE steers every later `aws` call and, more importantly,
  # the Terraform AWS provider — which would then fail the apply for exactly the
  # reason we just decided to route around.
  unset AWS_PROFILE
  return 0
}

aws_profile_flag() {
  # The `--profile X` fragment for user-facing hints, empty when running on
  # ambient credentials so printed commands stay copy-pasteable.
  if [[ ${#AWS_PROFILE_ARGS[@]} -gt 0 ]]; then
    printf -- '--profile %s' "$AWS_PROFILE_VALUE"
  fi
  return 0
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
  resolve_aws_profile
  identity="$(aws_dev sts get-caller-identity --output json)" ||
    die "Could not authenticate with AWS$(
      [[ -n "$AWS_PROFILE_VALUE" ]] && printf " profile '%s'" "$AWS_PROFILE_VALUE"
      true
    ). Put an access key in ~/.aws/credentials or the environment."
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
  # set into the long-running backend container. With the long-lived access key
  # this repo moved to in August 2026 it is a straight copy, but the indirection
  # is kept so an SSO or credential_process profile still works here.
  resolve_aws_profile
  aws_dev sts get-caller-identity >/dev/null ||
    die "AWS credentials are not currently valid. Put an access key in ~/.aws/credentials or the environment."
  if [[ ${#AWS_PROFILE_ARGS[@]} -gt 0 ]]; then
    credentials="$(aws configure export-credentials \
      "${AWS_PROFILE_ARGS[@]}" --format process)"
  else
    credentials="$(env -u AWS_PROFILE aws configure export-credentials --format process)"
  fi || die "AWS CLI could not export credentials."
  export AWS_ACCESS_KEY_ID="$(jq -r '.AccessKeyId' <<<"$credentials")"
  export AWS_SECRET_ACCESS_KEY="$(jq -r '.SecretAccessKey' <<<"$credentials")"
  export AWS_SESSION_TOKEN="$(jq -r '.SessionToken // empty' <<<"$credentials")"
  export AWS_CREDENTIAL_EXPIRATION="$(jq -r '.Expiration // empty' <<<"$credentials")"
  env -u AWS_PROFILE aws --no-cli-pager --region "$AWS_REGION_VALUE" \
    sts get-caller-identity >/dev/null ||
    die "AWS CLI exported invalid credentials. Check ~/.aws/credentials or AWS_ACCESS_KEY_ID."
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

# The dev stack's test account. Mirrors studio's `dev-aws-common.sh`
# deliberately: the two services had no shared convention for this and studio's
# is the one that already works.
#
# **Neither half is committed.** The address was the literal `dev@humbugg.test`
# when this landed, on the reasoning that a reserved `.test` TLD (RFC 2606) can
# never be a real mailbox, so Cognito could never mail a stranger on a typo.
# What the account is for has not changed — a *known* account, identical on
# every machine, that a test or a scripted sign-in can rely on — but "identical
# on every machine" is now a property of the config file rather than of the
# repo. Humbugg's pool allows self-signup, so this is a convenience and never
# the only way in.
#
# Both values sit outside the repo. A default password here would be a
# credential in a git history; the address follows it for consistency, so one
# account is described in one place.
DEV_ENV_FILE="$CONFIG_DIR/dev.env"

load_dev_user_email() {
  # Environment first, then the config file, and no default anywhere.
  if [[ -z "${HUMBUGG_DEV_USER_EMAIL:-}" && -f "$DEV_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
  fi
  [[ -n "${HUMBUGG_DEV_USER_EMAIL:-}" ]] || die \
    "HUMBUGG_DEV_USER_EMAIL is not set and $DEV_ENV_FILE provides none. Add a
  HUMBUGG_DEV_USER_EMAIL= line to that file. An address in the reserved .test TLD
  is what belongs there: it can never be a real mailbox, so Cognito cannot mail
  a stranger on a typo."
  export HUMBUGG_DEV_USER_EMAIL
}

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
    # **Rewritten key by key, not overwritten.** This truncated the file
    # until the address moved into it too, at which point a `--generate-password`
    # run would have silently deleted the account's own name and left the
    # next command asking for an email nobody removed.
    local generated_env
    generated_env="$(mktemp)"
    chmod 600 "$generated_env"
    [[ -f "$DEV_ENV_FILE" ]] &&
      grep -v '^HUMBUGG_DEV_USER_PASSWORD=' "$DEV_ENV_FILE" > "$generated_env" || true
    printf 'HUMBUGG_DEV_USER_PASSWORD=%s\n' "$(openssl rand -hex 12)Aa1" >> "$generated_env"
    mv "$generated_env" "$DEV_ENV_FILE"
    chmod 600 "$DEV_ENV_FILE"
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
    ok "Generated the dev account password into $DEV_ENV_FILE (not printed)."
  fi
  if [[ -z "${HUMBUGG_DEV_USER_PASSWORD:-}" ]]; then
    [[ "$prompt_allowed" == "true" ]] ||
      die "HUMBUGG_DEV_USER_PASSWORD is not set and $DEV_ENV_FILE provides none."
    # Falls back to a description rather than requiring the email to be loaded:
    # this function is reachable on its own, and a prompt is not worth a die.
    printf 'Password for %s (not echoed): ' "${HUMBUGG_DEV_USER_EMAIL:-the dev account}" >&2
    read -rs HUMBUGG_DEV_USER_PASSWORD
    printf '\n' >&2
  fi
}
