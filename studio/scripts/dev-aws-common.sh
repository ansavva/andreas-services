#!/usr/bin/env bash
#
# Shared helpers for the studio dev-AWS scripts. Sourced, never run directly.
#
# This is a port of humbugg/scripts/dev-aws-common.sh, kept deliberately
# identical so the mechanism is learned once and applies to both services. The
# only differences are the service name and the paths it derives from it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$STUDIO_DIR/infra/envs/dev"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/studio"
MACHINE_ID_FILE="$CONFIG_DIR/machine-id"

AWS_PROFILE_VALUE="${AWS_PROFILE:-default}"
AWS_REGION_VALUE="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

# The `--profile` fragment every AWS call actually uses, decided once by
# `resolve_aws_profile`. An empty array means "pass no --profile at all and let
# the CLI resolve credentials the way it normally would".
AWS_PROFILE_ARGS=()
AWS_PROFILE_RESOLVED=0

# The dev stack's one account. **Neither half of it is committed** — the
# password never could be, and the address no longer is.
#
# It used to be the literal `dev@studio.test`, on the reasoning that a reserved
# `.test` TLD (RFC 2606) can never be a real mailbox, so the address was safe to
# hard-code and worth hard-coding: `dev-user.sh` creates exactly the account
# `dev-token.sh` signs in as, and one constant is how those cannot drift onto
# two different people.
#
# That second half still has to hold, and now it holds through the config file
# rather than through the repo: both scripts read one value from one place, so
# they still cannot drift — the place is just no longer inside a checkout.
# `.test` is still what belongs in it, and nothing here enforces that, because
# the value is now the developer's to choose.
DEV_ENV_FILE="$CONFIG_DIR/dev.env"

load_dev_user_email() {
  # Environment first, then the config file, and no default anywhere. Mirrors
  # `load_dev_user_password` below, deliberately: the two halves of one account
  # should not come from two kinds of place.
  if [[ -z "${STUDIO_DEV_USER_EMAIL:-}" && -f "$DEV_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
  fi
  [[ -n "${STUDIO_DEV_USER_EMAIL:-}" ]] || die \
    "STUDIO_DEV_USER_EMAIL is not set and $DEV_ENV_FILE provides none. Add a
  STUDIO_DEV_USER_EMAIL= line to that file. An address in the reserved .test TLD
  is what belongs there: it can never be a real mailbox, so Cognito cannot mail
  a stranger on a typo."
  export STUDIO_DEV_USER_EMAIL
}

# **Progress goes to stderr, all of it.** `dev-token.sh`'s stdout is a data
# channel — the whole point of it is `Bearer $(dev-token.sh)` — and `log` used to
# write to stdout, so the token came back with a log line glued to the front of
# it. The integration suite caught it on the assertion that the result is a JWT.
#
# Every script here is now safe to capture: stdout carries the answer, stderr
# carries the narration. `warn` and `die` were already right.
log()  { printf '\033[1;34m[dev-aws]\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command '$1' is not installed."
}

aws_dev() {
  aws --no-cli-pager ${AWS_PROFILE_ARGS[@]+"${AWS_PROFILE_ARGS[@]}"} \
    --region "$AWS_REGION_VALUE" "$@"
}

aws_dev_probe() {
  # aws_dev, with any exported AWS_PROFILE stripped so the explicit decision in
  # AWS_PROFILE_ARGS is the only thing selecting credentials.
  env -u AWS_PROFILE aws --no-cli-pager ${AWS_PROFILE_ARGS[@]+"${AWS_PROFILE_ARGS[@]}"} \
    --region "$AWS_REGION_VALUE" "$@"
}

resolve_aws_profile() {
  # Decide once whether to name a profile at all.
  #
  # **`--profile default` is not a harmless way of saying "the usual
  # credentials".** Naming a profile makes the CLI resolve *that profile* and
  # stop; it will not fall back to `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
  # in the environment. So on a machine whose credentials arrive as environment
  # variables — CI, a container, a Claude cloud session — every call here failed
  # `NoCredentials` while a bare `aws sts get-caller-identity` two lines earlier
  # succeeded, because `~/.aws/config` had a `[default]` section holding
  # settings but no keys. The error names credentials, so it reads as an expired
  # session and invites a re-authentication that cannot fix it.
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
  # **`STUDIO_DEV_MACHINE_ID` targets a stack this machine did not create**, and
  # persists it so every later command agrees. Two cases need it and neither is
  # exotic: an ephemeral environment, where a generated id dies with the
  # container and leaves the stack running, billing, and its state key
  # unguessable; and a second machine reaching an existing stack on purpose.
  #
  # It lives here rather than as a flag on one script because every dev-AWS
  # command needs the same answer, and `backend/tests/integration/conftest.py`
  # already reads this variable.
  if [[ -n "${STUDIO_DEV_MACHINE_ID:-}" ]]; then
    [[ "$STUDIO_DEV_MACHINE_ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] ||
      die "STUDIO_DEV_MACHINE_ID is not a lowercase UUID."
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
    printf '%s\n' "$STUDIO_DEV_MACHINE_ID" > "$MACHINE_ID_FILE"
    chmod 600 "$MACHINE_ID_FILE"
  fi
  if [[ ! -f "$MACHINE_ID_FILE" ]]; then
    [[ "$create_if_missing" == "true" ]] ||
      die "No machine ID exists. Run ./studio/scripts/dev-aws-setup.sh first."
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
    ). Sign in, or put credentials in the environment."
  AWS_ACCOUNT_ID="$(jq -r '.Account' <<<"$identity")"
  AWS_PRINCIPAL_ARN="$(jq -r '.Arn' <<<"$identity")"
  [[ "$AWS_ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || die "AWS returned an invalid account ID."
  MACHINE_NAME="$(hostname -s 2>/dev/null || hostname)"
  RESOURCE_PREFIX="studio-dev-$MACHINE_SHORT_ID"
  STATE_KEY="studio/dev/$AWS_ACCOUNT_ID/$MACHINE_ID/terraform.tfstate"
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
  # set into the long-running backend container. It used to be what made `terraform apply` work at
  # all: `aws login` wrote a cache only the AWS CLI read, so the S3 backend resolved it while the
  # AWS provider did not. The long-lived access key this repo moved to in August 2026 is read by
  # both, so this is now redundancy rather than the fix. See "Environment access" in the root
  # CLAUDE.md.
  resolve_aws_profile
  aws_dev_probe sts get-caller-identity >/dev/null ||
    die "AWS credentials are not currently valid. Sign in to AWS and try again."
  if [[ ${#AWS_PROFILE_ARGS[@]} -gt 0 ]]; then
    credentials="$(aws configure export-credentials \
      "${AWS_PROFILE_ARGS[@]}" --format process)"
  else
    credentials="$(env -u AWS_PROFILE aws configure export-credentials --format process)"
  fi || die "AWS CLI could not export temporary credentials."
  export AWS_ACCESS_KEY_ID="$(jq -r '.AccessKeyId' <<<"$credentials")"
  export AWS_SECRET_ACCESS_KEY="$(jq -r '.SecretAccessKey' <<<"$credentials")"
  export AWS_SESSION_TOKEN="$(jq -r '.SessionToken // empty' <<<"$credentials")"
  export AWS_CREDENTIAL_EXPIRATION="$(jq -r '.Expiration // empty' <<<"$credentials")"
  env -u AWS_PROFILE aws --no-cli-pager --region "$AWS_REGION_VALUE" \
    sts get-caller-identity >/dev/null ||
    die "AWS CLI exported invalid or expired credentials. Sign in to AWS and try again."
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

load_dev_stack_outputs() {
  # This machine's stack, read straight out of the Terraform state object in S3
  # rather than through `terraform init` + `terraform output`. A caller that
  # only wants to know a pool id should not reconfigure a backend or download a
  # provider to find out, and this way it works from a cold checkout with no
  # .terraform directory. `dev-aws-setup.sh --check` reads it the same way.
  local state_json
  state_json="$(aws_dev s3 cp "s3://andreas-services-terraform-state/$STATE_KEY" -)" ||
    die "Terraform state is missing. Run ./studio/scripts/dev-aws-setup.sh $(aws_profile_flag)."
  [[ "$(jq -r '.outputs.machine_id.value // empty' <<<"$state_json")" == "$MACHINE_ID" ]] ||
    die "Terraform state does not match this machine ID."
  DEV_POOL_ID="$(jq -r '.outputs.cognito_user_pool_id.value // empty' <<<"$state_json")"
  DEV_CLIENT_ID="$(jq -r '.outputs.cognito_user_pool_client_id.value // empty' <<<"$state_json")"
  # `<prefix>.auth.<region>.amazoncognito.com` — this stack's Managed Login
  # host, which the SPA redirects to. Checked below with the rest: an empty one
  # is a stack applied before #364, and the local app cannot sign in at all
  # against it, so failing here beats a blank sign-in button later.
  DEV_AUTH_DOMAIN="$(jq -r '.outputs.cognito_auth_domain.value // empty' <<<"$state_json")"
  DEV_BUCKET="$(jq -r '.outputs.media_bucket_name.value // empty' <<<"$state_json")"
  DEV_TABLE="$(jq -r '.outputs.catalog_table_name.value // empty' <<<"$state_json")"
  # WHERE REPLICATE CALLS BACK FOR THIS MACHINE, AND THE QUEUE IT LANDS ON.
  #
  # Replicate cannot reach `http://localhost:8000`, so a generation submitted
  # against this stack is reported to a real AWS endpoint that enqueues it, and
  # `dev-up.sh` runs a consumer which drains that queue with the local working
  # tree. See `infra/modules/callbacks`.
  #
  # **Deliberately NOT in the required list below.** A stack applied before this
  # landed has neither, and every other thing a developer does with it still
  # works — so an empty value degrades to "runs are closed by `studio runs
  # reconcile`" rather than refusing to start the app. `dev-up.sh` says so once,
  # in words, and names the re-apply.
  DEV_CALLBACK_URL="$(jq -r '.outputs.callback_base_url.value // empty' <<<"$state_json")"
  DEV_CALLBACK_QUEUE="$(jq -r '.outputs.callback_queue_url.value // empty' <<<"$state_json")"
  [[ -n "$DEV_POOL_ID" && -n "$DEV_CLIENT_ID" && -n "$DEV_AUTH_DOMAIN" && -n "$DEV_BUCKET" && -n "$DEV_TABLE" ]] ||
    die "Terraform state is missing required development outputs. Re-run ./studio/scripts/dev-aws-setup.sh."
}

load_dev_user_password() {
  # Order: an exported value wins, then the file, then a prompt. Never a
  # default — see the constant above.
  #
  # Nothing in this function, or in either caller, echoes the value. The prompt
  # is `read -s`, the errors name the *variable* and never its contents, and no
  # caller interpolates it into a log line, a command echo or a URL. That is a
  # rule and not a nicety: `dev-user.sh` passes it to `admin-set-user-password`,
  # which puts it in this shell's history if a caller ever inlines it.
  local prompt_allowed="${1:-true}"
  local generate="${2:-false}"
  if [[ -z "${STUDIO_DEV_USER_PASSWORD:-}" && -f "$DEV_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
  fi
  if [[ -z "${STUDIO_DEV_USER_PASSWORD:-}" && "$generate" == "true" ]]; then
    # 24 hex characters plus a fixed upper/lower/digit tail, because the pool
    # requires all three classes and `openssl rand -hex` alone can produce a
    # string with no uppercase. Written before it is used, so a re-run against
    # an existing stack converges the same password rather than minting a second
    # one nothing has recorded.
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
      grep -v '^STUDIO_DEV_USER_PASSWORD=' "$DEV_ENV_FILE" > "$generated_env" || true
    printf 'STUDIO_DEV_USER_PASSWORD=%s\n' "$(openssl rand -hex 12)Aa1" >> "$generated_env"
    mv "$generated_env" "$DEV_ENV_FILE"
    chmod 600 "$DEV_ENV_FILE"
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
    ok "Generated the dev account password into $DEV_ENV_FILE (not printed)."
  fi
  if [[ -z "${STUDIO_DEV_USER_PASSWORD:-}" ]]; then
    [[ "$prompt_allowed" == "true" ]] ||
      die "STUDIO_DEV_USER_PASSWORD is not set and $DEV_ENV_FILE provides none."
    # Falls back to a description rather than requiring the email to be loaded:
    # this function is reachable on its own, and a prompt is not worth a die.
    printf 'Password for %s (not echoed): ' "${STUDIO_DEV_USER_EMAIL:-the dev account}" >&2
    read -rs STUDIO_DEV_USER_PASSWORD
    printf '\n' >&2
  fi
  [[ -n "${STUDIO_DEV_USER_PASSWORD:-}" ]] ||
    die "STUDIO_DEV_USER_PASSWORD is empty."
  export STUDIO_DEV_USER_PASSWORD
}
