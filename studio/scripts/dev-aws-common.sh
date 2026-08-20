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

# The dev stack's one account, and the file its password lives in.
#
# **The address is committed and the password never can be.** `.test` is a
# reserved TLD (RFC 2606), so this can never be a real mailbox and Cognito can
# never mail a stranger on a typo — which is what makes hard-coding it safe and
# what makes it worth hard-coding: `dev-user.sh` creates exactly the account
# `dev-token.sh` signs in as, and one constant is how those cannot drift onto
# two different people.
#
# The password file sits outside the repo on purpose. A default here would be a
# credential in a git history, and there is no value that would be safe to put
# in one.
STUDIO_DEV_USER_EMAIL="dev@studio.test"
DEV_ENV_FILE="$CONFIG_DIR/dev.env"

# Progress goes to stderr, like warn/die. It is still on the terminal, but it is
# no longer mixed into a script's *value*: `dev-token.sh` emits a JWT on stdout
# and nothing else, so `dev-aws-bootstrap.sh` can capture it. While these logged
# to stdout, that capture picked up "Signing in as ..." and a pair of ANSI colour
# escapes ahead of the token, and the bootstrap's claims decode fell over on it
# and reported "jq or base64 differs here" — a real token, an unreadable report.
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
  # session and invites an `aws login` that cannot fix it.
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
  [[ -n "${MACHINE_ID:-}" ]] && derive_machine_scoped_names
  return 0
}

derive_machine_scoped_names() {
  # Split out of `load_aws_identity` because the machine id is not always known
  # at the moment the AWS identity is.
  #
  # `dev-aws-bootstrap.sh` characterises the environment *before* pinning an id
  # — deliberately, since `--check` must not write one to disk — so folding
  # these two derivations into the identity call made that script fail with
  # `MACHINE_SHORT_ID: unbound variable` on precisely the cold checkout it
  # exists to serve. It went unseen because the credential error above fired
  # first and hid it.
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
  # set into the long-running backend container. It is also what makes `terraform apply` work at
  # all: `aws login` writes a cache only the AWS CLI reads, so the S3 backend resolves it while the
  # AWS provider does not. See "Running Terraform locally?" in the root CLAUDE.md.
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
  DEV_BUCKET="$(jq -r '.outputs.media_bucket_name.value // empty' <<<"$state_json")"
  DEV_TABLE="$(jq -r '.outputs.catalog_table_name.value // empty' <<<"$state_json")"
  [[ -n "$DEV_POOL_ID" && -n "$DEV_CLIENT_ID" && -n "$DEV_BUCKET" && -n "$DEV_TABLE" ]] ||
    die "Terraform state is missing required development outputs."
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
  if [[ -z "${STUDIO_DEV_USER_PASSWORD:-}" && -f "$DEV_ENV_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$DEV_ENV_FILE"
  fi
  if [[ -z "${STUDIO_DEV_USER_PASSWORD:-}" ]]; then
    [[ "$prompt_allowed" == "true" ]] ||
      die "STUDIO_DEV_USER_PASSWORD is not set and $DEV_ENV_FILE provides none."
    printf 'Password for %s (not echoed): ' "$STUDIO_DEV_USER_EMAIL" >&2
    read -rs STUDIO_DEV_USER_PASSWORD
    printf '\n' >&2
  fi
  [[ -n "${STUDIO_DEV_USER_PASSWORD:-}" ]] ||
    die "STUDIO_DEV_USER_PASSWORD is empty."
  export STUDIO_DEV_USER_PASSWORD
}
