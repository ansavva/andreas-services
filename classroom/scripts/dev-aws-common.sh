#!/usr/bin/env bash
#
# Shared helpers for the classroom dev-AWS scripts. Sourced, never run directly.
#
# This is a port of studio/scripts/dev-aws-common.sh, kept deliberately
# identical so the mechanism is learned once and applies to every service that
# has one. The differences are the service name, the paths derived from it, and
# what a stack is made of: classroom's is a Cognito pool and one DynamoDB table,
# with no bucket and no queues.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLASSROOM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TF_DIR="$CLASSROOM_DIR/infra/envs/dev"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/classroom"
MACHINE_ID_FILE="$CONFIG_DIR/machine-id"

AWS_PROFILE_VALUE="${AWS_PROFILE:-default}"
AWS_REGION_VALUE="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

# The `--profile` fragment every AWS call actually uses, decided once by
# `resolve_aws_profile`. An empty array means "pass no --profile at all and let
# the CLI resolve credentials the way it normally would".
AWS_PROFILE_ARGS=()
AWS_PROFILE_RESOLVED=0

# **One file holds every local development value: `$DEV_ENV_FILE`.** The
# frontend's inlined `VITE_*` values, the dev test account, and any secret the
# local half needs. It used to be two — `frontend/.env.local` for Vite and this
# file for the account — and knowing which key went where was the job. Now the
# readers come to the file: `dev-up.sh` exports the `VITE_*` prefix before Vite
# starts, and the scripts read it directly.
#
# It sits outside the repo. Ignored files still vanish on `git clean -fdx` and
# never exist in a fresh worktree; this one is per machine, shared by every
# checkout on it, and holds a password. `CLASSROOM_DEV_ENV_FILE` overrides the
# location, and every reader honours it.
#
# `dev-setup.sh` writes the generated keys; a hand-set key is left alone by
# every script that touches the file, because `upsert_env` rewrites only the
# key it is given.
DEV_ENV_FILE="${CLASSROOM_DEV_ENV_FILE:-$CONFIG_DIR/dev.env}"
export CLASSROOM_DEV_ENV_FILE="$DEV_ENV_FILE"

# Rewrite exactly one key, creating the file (mode 600) if needed. Comments
# and every other key survive. A commented placeholder (`#KEY=`, which
# dev-setup.sh renders for a hand-set key that has no value yet) is taken as
# the key's slot, so the value lands in its section rather than at the end.
upsert_env() {
  local file="$1" key="$2" value="$3" temp
  mkdir -p "$(dirname "$file")"
  chmod 700 "$(dirname "$file")"
  touch "$file"
  temp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^#?" key "=" {
      if (!found) print key "=" value
      found = 1
      next
    }
    { print }
    END { if (!found) print key "=" value }
  ' "$file" > "$temp"
  chmod 600 "$temp"
  mv "$temp" "$file"
}

# Set a key only when the file has no line for it — a default the user may
# have already replaced.
ensure_env() {
  local file="$1" key="$2" value="$3"
  [[ -f "$file" ]] && grep -Eq "^${key}=" "$file" && return 0
  upsert_env "$file" "$key" "$value"
}

remove_env() {
  local file="$1" key="$2" temp
  [[ -f "$file" ]] || return 0
  temp="$(mktemp)"
  awk -v key="$key" '$0 !~ "^" key "=" { print }' "$file" > "$temp"
  chmod 600 "$temp"
  mv "$temp" "$file"
}

# The value of one key, empty when absent. Never `source` the file: it holds
# URLs and secrets whose characters are not all shell-safe.
read_env() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  awk -v key="$key" -F= '$1 == key { sub("^" key "=", ""); print; exit }' "$file"
}

# Export every key beginning with a prefix into this process. Vite inlines only
# `VITE_*`, and leaves a variable already in the environment alone, so this is
# how the frontend's values reach it without the bundler being handed a secret.
export_env_prefix() {
  local file="$1" prefix="$2" line key value
  [[ -f "$file" ]] || return 0
  while IFS= read -r line; do
    [[ "$line" =~ ^(${prefix}[A-Za-z0-9_]*)=(.*)$ ]] || continue
    key="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    export "$key=$value"
  done < "$file"
}

require_dev_env() {
  [[ -f "$DEV_ENV_FILE" ]] ||
    die "Missing $DEV_ENV_FILE. Run ./classroom/scripts/dev-setup.sh first."
}

# The dev stack's one account lives in the same file. **Neither half of it is
# committed.** Both `dev-user.sh` and `dev-token.sh` read the address from this
# one file, so the account created and the account signed in as cannot drift
# apart. A reserved `.test` address (RFC 2606) is what belongs in it, because
# it can never be a real mailbox; nothing enforces that, because the value is
# the developer's.

load_dev_user_email() {
  # Environment first, then the config file, and no default anywhere. Mirrors
  # `load_dev_user_password` below, deliberately: the two halves of one account
  # should not come from two kinds of place.
  [[ -n "${CLASSROOM_DEV_USER_EMAIL:-}" ]] ||
    CLASSROOM_DEV_USER_EMAIL="$(read_env "$DEV_ENV_FILE" CLASSROOM_DEV_USER_EMAIL)"
  [[ -n "${CLASSROOM_DEV_USER_EMAIL:-}" ]] || die \
    "CLASSROOM_DEV_USER_EMAIL is not set and $DEV_ENV_FILE provides none. Add a
  CLASSROOM_DEV_USER_EMAIL= line to that file. An address in the reserved .test
  TLD is what belongs there: it can never be a real mailbox, so Cognito cannot
  mail a stranger on a typo."
  export CLASSROOM_DEV_USER_EMAIL
}

# **Progress goes to stderr, all of it.** `dev-token.sh`'s stdout is a data
# channel — the whole point of it is `Bearer $(dev-token.sh)` — so a log line on
# stdout would be glued to the front of the token. Every script here is safe to
# capture: stdout carries the answer, stderr carries the narration.
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
  # variables — CI, a container, a Claude cloud session — every call here fails
  # `NoCredentials` while a bare `aws sts get-caller-identity` two lines earlier
  # succeeds, because `~/.aws/config` has a `[default]` section holding settings
  # but no keys. The error names credentials, so it reads as an expired session
  # and invites a re-authentication that cannot fix it.
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
  # **`CLASSROOM_DEV_MACHINE_ID` targets a stack this machine did not create**,
  # and persists it so every later command agrees. Two cases need it and neither
  # is exotic: an ephemeral environment, where a generated id dies with the
  # container and leaves the stack running, billing, and its state key
  # unguessable; and a second machine reaching an existing stack on purpose.
  if [[ -n "${CLASSROOM_DEV_MACHINE_ID:-}" ]]; then
    [[ "$CLASSROOM_DEV_MACHINE_ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] ||
      die "CLASSROOM_DEV_MACHINE_ID is not a lowercase UUID."
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
    printf '%s\n' "$CLASSROOM_DEV_MACHINE_ID" > "$MACHINE_ID_FILE"
    chmod 600 "$MACHINE_ID_FILE"
  fi
  if [[ ! -f "$MACHINE_ID_FILE" ]]; then
    [[ "$create_if_missing" == "true" ]] ||
      die "No machine ID exists. Run ./classroom/scripts/dev-aws-setup.sh first."
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
  RESOURCE_PREFIX="classroom-dev-$MACHINE_SHORT_ID"
  STATE_KEY="classroom/dev/$AWS_ACCOUNT_ID/$MACHINE_ID/terraform.tfstate"
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
  # Make the selected profile resolve its current session before exporting
  # credentials. With a long-lived access key this is redundancy rather than the
  # fix it once was; it still does the right thing for an SSO or
  # credential_process profile. See "Environment access" in the root CLAUDE.md.
  resolve_aws_profile
  aws_dev_probe sts get-caller-identity >/dev/null ||
    die "AWS credentials are not currently valid. Sign in to AWS and try again."
  if [[ ${#AWS_PROFILE_ARGS[@]} -gt 0 ]]; then
    credentials="$(aws configure export-credentials \
      "${AWS_PROFILE_ARGS[@]}" --format process)"
  else
    credentials="$(env -u AWS_PROFILE aws configure export-credentials --format process)"
  fi || die "AWS CLI could not export temporary credentials."
  AWS_ACCESS_KEY_ID="$(jq -r '.AccessKeyId' <<<"$credentials")"; export AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY="$(jq -r '.SecretAccessKey' <<<"$credentials")"; export AWS_SECRET_ACCESS_KEY
  AWS_SESSION_TOKEN="$(jq -r '.SessionToken // empty' <<<"$credentials")"; export AWS_SESSION_TOKEN
  AWS_CREDENTIAL_EXPIRATION="$(jq -r '.Expiration // empty' <<<"$credentials")"; export AWS_CREDENTIAL_EXPIRATION
  env -u AWS_PROFILE aws --no-cli-pager --region "$AWS_REGION_VALUE" \
    sts get-caller-identity >/dev/null ||
    die "AWS CLI exported invalid or expired credentials. Sign in to AWS and try again."
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
    die "Terraform state is missing. Run ./classroom/scripts/dev-aws-setup.sh $(aws_profile_flag)."
  [[ "$(jq -r '.outputs.machine_id.value // empty' <<<"$state_json")" == "$MACHINE_ID" ]] ||
    die "Terraform state does not match this machine ID."
  DEV_POOL_ID="$(jq -r '.outputs.cognito_user_pool_id.value // empty' <<<"$state_json")"
  DEV_CLIENT_ID="$(jq -r '.outputs.cognito_client_id.value // empty' <<<"$state_json")"
  # `<prefix>.auth.<region>.amazoncognito.com` — this stack's Managed Login
  # host, which the SPA redirects to. An empty one is a stack applied without a
  # domain, and the local app cannot sign in at all against it, so failing here
  # beats a blank sign-in button later.
  DEV_AUTH_DOMAIN="$(jq -r '.outputs.cognito_domain.value // empty' <<<"$state_json")"
  DEV_TABLE="$(jq -r '.outputs.pages_table_name.value // empty' <<<"$state_json")"
  # Where a lesson's uploaded files live. In prod CloudFront serves these from a
  # separate host; locally `dev-up.sh` serves them off the API's own port, which
  # is still a different ORIGIN from the SPA's — an origin includes its port —
  # so the isolation the design depends on holds here too.
  DEV_LESSONS_BUCKET="$(jq -r '.outputs.lessons_bucket_name.value // empty' <<<"$state_json")"
  # The origin registered on the app client, so `dev-up.sh` serves the SPA at the
  # one address Cognito will redirect back to. Optional: a stack applied before
  # this output landed has none, and the default is what that stack registered.
  DEV_SPA_ORIGIN="$(jq -r '.outputs.spa_origin.value // empty' <<<"$state_json")"
  [[ -n "$DEV_SPA_ORIGIN" ]] || DEV_SPA_ORIGIN="http://localhost:5174"
  [[ -n "$DEV_POOL_ID" && -n "$DEV_CLIENT_ID" && -n "$DEV_AUTH_DOMAIN" && -n "$DEV_TABLE" && -n "$DEV_LESSONS_BUCKET" ]] ||
    die "Terraform state is missing required development outputs. Re-run ./classroom/scripts/dev-aws-setup.sh."
}

load_dev_user_password() {
  # Order: an exported value wins, then the file, then a prompt. Never a
  # default — see the constant above.
  #
  # Nothing in this function, or in any caller, echoes the value. The prompt is
  # `read -s`, the errors name the *variable* and never its contents, and no
  # caller interpolates it into a log line, a command echo or a URL. That is a
  # rule and not a nicety: `dev-user.sh` passes it to
  # `admin-set-user-password`, which puts it in this shell's history if a caller
  # ever inlines it.
  local prompt_allowed="${1:-true}"
  local generate="${2:-false}"
  [[ -n "${CLASSROOM_DEV_USER_PASSWORD:-}" ]] ||
    CLASSROOM_DEV_USER_PASSWORD="$(read_env "$DEV_ENV_FILE" CLASSROOM_DEV_USER_PASSWORD)"
  if [[ -z "${CLASSROOM_DEV_USER_PASSWORD:-}" && "$generate" == "true" ]]; then
    # 24 hex characters plus a fixed upper/lower/digit tail, because the pool
    # requires all three classes and `openssl rand -hex` alone can produce a
    # string with no uppercase. Written before it is used, so a re-run against
    # an existing stack converges the same password rather than minting a second
    # one nothing has recorded.
    require_command openssl
    # **Rewritten key by key, not overwritten.** Truncating the file would
    # delete the whole stack's configuration along with the account's own address.
    CLASSROOM_DEV_USER_PASSWORD="$(openssl rand -hex 12)Aa1"
    upsert_env "$DEV_ENV_FILE" CLASSROOM_DEV_USER_PASSWORD "$CLASSROOM_DEV_USER_PASSWORD"
    ok "Generated the dev account password into $DEV_ENV_FILE (not printed)."
  fi
  if [[ -z "${CLASSROOM_DEV_USER_PASSWORD:-}" ]]; then
    [[ "$prompt_allowed" == "true" ]] ||
      die "CLASSROOM_DEV_USER_PASSWORD is not set and $DEV_ENV_FILE provides none."
    printf 'Password for %s (not echoed): ' "${CLASSROOM_DEV_USER_EMAIL:-the dev account}" >&2
    read -rs CLASSROOM_DEV_USER_PASSWORD
    printf '\n' >&2
  fi
  [[ -n "${CLASSROOM_DEV_USER_PASSWORD:-}" ]] ||
    die "CLASSROOM_DEV_USER_PASSWORD is empty."
  export CLASSROOM_DEV_USER_PASSWORD
}
