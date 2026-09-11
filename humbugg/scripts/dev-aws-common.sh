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

# **One file holds every local development value: `$DEV_ENV_FILE`.** The
# machine-scoped backend config (table names, pool, bucket), the two frontends'
# inlined values (`EXPO_PUBLIC_*`, `VITE_*`), the Stripe test keys and the CLI's
# webhook signing secret, and the dev test account. It used to be four files —
# `backend/.env`, `app/.env.local`, `marketing/.env.local` and this one — each
# with a different reader, and knowing which key went where was the job. Now
# the readers come to the file: Docker Compose takes it as `env_file`, the two
# dev-up scripts export the prefix their bundler inlines, and the test tiers
# parse it directly.
#
# It sits outside the repo. Ignored files still vanish on `git clean -fdx` and
# never exist in a fresh worktree; this one is per machine, shared by every
# checkout on it, and holds a password.
#
# `dev-aws-setup.sh` writes the generated keys; a hand-set key (a Stripe secret,
# a plan limit) is left alone by every script that touches the file, because
# `upsert_env` rewrites only the key it is given.
#
# `HUMBUGG_DEV_ENV_FILE` overrides the location, and every reader honours it —
# these scripts, backend/docker-compose.yml (which needs an absolute path,
# because Compose resolves relative ones against the compose file and does not
# expand `~`), the integration fixture and the e2e session helper. Exported so
# every script that drives Compose — up, logs, reset — has it.
DEV_ENV_FILE="${HUMBUGG_DEV_ENV_FILE:-$CONFIG_DIR/dev.env}"
export HUMBUGG_DEV_ENV_FILE="$DEV_ENV_FILE"

# Rewrite exactly one key, creating the file (mode 600) if needed. Comments
# and every other key survive. A commented placeholder (`#KEY=`, which
# dev-aws-setup.sh renders for a hand-set key that has no value yet) is taken
# as the key's slot, so the value lands in its section rather than at the end.
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

# Export every key beginning with a prefix into this process. The bundlers
# inline only their own prefix, and both leave a variable already in the
# environment alone, so this is how `EXPO_PUBLIC_*` reaches Metro and `VITE_*`
# reaches Vite without either being handed the Stripe secret key.
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
    die "Missing $DEV_ENV_FILE. Run ./humbugg/scripts/dev-aws-setup.sh first."
}

# The dev stack's test account lives in the same file, under
# `HUMBUGG_DEV_USER_EMAIL` and `HUMBUGG_DEV_USER_PASSWORD`. Mirrors studio's
# `dev-aws-common.sh` deliberately: the two services had no shared convention
# for this and studio's is the one that already works.
#
# **The password is never committed; the addresses are.** `seeds/dev.json`
# names every person a dev stack holds, all at `.test` — a reserved TLD (RFC
# 2606) that can never be a real mailbox, so Cognito can never mail a stranger
# on a typo and nothing is mailed anyway. `HUMBUGG_DEV_USER_EMAIL` should be
# one of them: it is who the e2e helper signs in as, not who exists.
# `HUMBUGG_DEV_USER_PASSWORD` is the ONE password every seeded account shares,
# outside the repo because a password in a git history is a credential.
# Humbugg's pool allows self-signup, so this is a convenience and never the
# only way in.

load_dev_user_email() {
  # Environment first, then the config file, and no default anywhere.
  [[ -n "${HUMBUGG_DEV_USER_EMAIL:-}" ]] ||
    HUMBUGG_DEV_USER_EMAIL="$(read_env "$DEV_ENV_FILE" HUMBUGG_DEV_USER_EMAIL)"
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
  [[ -n "${HUMBUGG_DEV_USER_PASSWORD:-}" ]] ||
    HUMBUGG_DEV_USER_PASSWORD="$(read_env "$DEV_ENV_FILE" HUMBUGG_DEV_USER_PASSWORD)"
  if [[ -z "${HUMBUGG_DEV_USER_PASSWORD:-}" && "$generate" == "true" ]]; then
    # 24 hex characters plus a fixed upper/lower/digit tail, because the pool
    # requires all three classes and `openssl rand -hex` alone can produce a
    # string with no uppercase. 24 hex + 3 clears the 12-character floor with
    # room to spare. Written before it is used, so a re-run against an existing
    # stack converges the same password rather than minting a second one
    # nothing has recorded.
    require_command openssl
    # **Rewritten key by key, not overwritten.** An earlier version truncated
    # the file, which by now would delete the whole dev stack's configuration
    # along with the account's own address.
    HUMBUGG_DEV_USER_PASSWORD="$(openssl rand -hex 12)Aa1"
    upsert_env "$DEV_ENV_FILE" HUMBUGG_DEV_USER_PASSWORD "$HUMBUGG_DEV_USER_PASSWORD"
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

# ── Pool accounts ───────────────────────────────────────────────────────────────
# Create-or-converge one account in a dev pool. Shared by `dev-user.sh` (the one
# account `HUMBUGG_DEV_USER_EMAIL` names) and `dev-aws-seed.sh` (every person in
# `seeds/dev.json`), so the two cannot disagree about what "an account that can
# sign in" means: it exists, its email is verified, nothing was mailed, and its
# password is PERMANENT — `admin-create-user` alone leaves FORCE_CHANGE_PASSWORD,
# which Managed Login answers with a "set a new password" challenge and a
# headless SRP sign-in cannot get past.
#
# The password goes through `--cli-input-json` from a mode-0600 temp file rather
# than `--password`, so it never appears in this process's argv — not in `ps`,
# not in a shell history that captured the line.
pool_user_exists() {
  aws_dev cognito-idp admin-get-user --user-pool-id "$1" --username "$2" >/dev/null 2>&1
}

ensure_pool_user() {
  local pool_id="$1" email="$2" password="$3"
  if pool_user_exists "$pool_id" "$email"; then
    log "Account exists; converging its password: $email"
  else
    # SUPPRESS because the password is set below, and because `.test` is
    # unroutable — an invite would bounce into Cognito's own bounce accounting
    # rather than reach anyone.
    aws_dev cognito-idp admin-create-user \
      --user-pool-id "$pool_id" \
      --username "$email" \
      --user-attributes Name=email,Value="$email" Name=email_verified,Value=true \
      --message-action SUPPRESS >/dev/null
    log "Account created: $email"
  fi
  local payload
  payload="$(umask 077 && mktemp "${TMPDIR:-/tmp}/humbugg-dev-user.XXXXXX")"
  jq -n --arg pool "$pool_id" --arg user "$email" --arg password "$password" \
    '{UserPoolId: $pool, Username: $user, Password: $password, Permanent: true}' >"$payload"
  aws_dev cognito-idp admin-set-user-password --cli-input-json "file://$payload"
  local status=$?
  rm -f "$payload"
  [[ $status -eq 0 ]] ||
    die "admin-set-user-password failed for $email. If it rejected the password, the AWS error above names the rule it broke — the policy differs per pool."
}

# ── This machine's Stripe webhook endpoint ──────────────────────────────────────
# The Terraform side of the webhook relay (`infra/modules/webhook_relay`) is a
# gateway and a queue; the Stripe side is a webhook endpoint pointing at that
# gateway, and this is what creates and removes it. Not Terraform, deliberately:
# the Stripe provider would be a second provider and a second credential for
# one resource, and the `whsec_` Stripe hands back at creation — and only at
# creation — has to land in dev.env regardless.
#
# The Stripe CLI is the client, with the key in STRIPE_API_KEY for the one call
# rather than on `--api-key`, so it is never in argv. The key is dev.env's
# HUMBUGG_STRIPE_SECRET_KEY: whichever sandbox the backend charges against is
# the sandbox the endpoint must live in, or the events would never arrive.
STRIPE_WEBHOOK_EVENTS=(
  checkout.session.completed
  checkout.session.async_payment_succeeded
  checkout.session.async_payment_failed
  checkout.session.expired
  charge.succeeded
  charge.refunded
)

# `stripe_dev <args>`: the CLI against dev.env's test key. Fails when Stripe is
# not configured for test mode, so callers check `stripe_dev_configured` first.
stripe_dev_configured() {
  [[ "$(read_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_MODE)" == "test" ]] &&
    [[ "$(read_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_SECRET_KEY)" == sk_test_* ]]
}

stripe_dev() {
  STRIPE_API_KEY="$(read_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_SECRET_KEY)" \
    stripe "$@"
}

# Ensure exactly one Stripe endpoint points at this machine's relay URL, and that
# dev.env holds its id and secret. Converges:
#   * the recorded endpoint exists at this URL → nothing to do (the secret in
#     dev.env is the one Stripe issued for it);
#   * it is missing, or points elsewhere (the gateway was recreated) → delete
#     it and any other endpoint at this URL — their secrets are unknowable —
#     and create a fresh one, recording id and secret.
ensure_stripe_webhook_endpoint() {
  local url="$1" recorded current id secret others
  require_command stripe
  recorded="$(read_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_WEBHOOK_ENDPOINT_ID)"
  if [[ -n "$recorded" ]]; then
    if current="$(stripe_dev webhook_endpoints retrieve "$recorded" 2>/dev/null)" &&
       [[ "$(jq -r '.url' <<<"$current")" == "$url" && "$(jq -r '.status' <<<"$current")" == "enabled" ]] &&
       [[ "$(read_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_WEBHOOK_SECRET)" == whsec_* ]]; then
      ok "Stripe webhook endpoint $recorded already points at this machine's relay."
      return 0
    fi
    log "Recorded Stripe endpoint $recorded is gone or stale; replacing it."
    stripe_dev webhook_endpoints delete "$recorded" --confirm >/dev/null 2>&1 || true
  fi
  # Any other endpoint at this URL is one whose id dev.env lost. Its secret
  # cannot be read back, so it is useless; remove it rather than leave Stripe
  # delivering to two endpoints for one machine.
  others="$(stripe_dev webhook_endpoints list --limit 100 | jq -r --arg url "$url" '.data[] | select(.url == $url) | .id')"
  for id in $others; do
    log "Removing an orphaned Stripe endpoint at this URL: $id"
    stripe_dev webhook_endpoints delete "$id" --confirm >/dev/null
  done

  local args=(webhook_endpoints create --url "$url" --description "humbugg dev $MACHINE_SHORT_ID")
  for event in "${STRIPE_WEBHOOK_EVENTS[@]}"; do args+=(--enabled-events "$event"); done
  current="$(stripe_dev "${args[@]}")" || die "Stripe refused to create the webhook endpoint. Is HUMBUGG_STRIPE_SECRET_KEY a working test key?"
  id="$(jq -r '.id' <<<"$current")"
  secret="$(jq -r '.secret' <<<"$current")"
  [[ "$id" == we_* && "$secret" == whsec_* ]] || die "Stripe returned an unexpected webhook endpoint: $(jq -c 'del(.secret)' <<<"$current")"
  upsert_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_WEBHOOK_ENDPOINT_ID "$id"
  upsert_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_WEBHOOK_SECRET "$secret"
  ok "Registered Stripe webhook endpoint $id → $url (secret written to $DEV_ENV_FILE, not printed)."
}

# Remove this machine's endpoint from Stripe and its record from dev.env. Safe
# to call when there is none.
delete_stripe_webhook_endpoint() {
  local recorded
  recorded="$(read_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_WEBHOOK_ENDPOINT_ID)"
  if [[ -n "$recorded" ]] && stripe_dev_configured && command -v stripe >/dev/null 2>&1; then
    if stripe_dev webhook_endpoints delete "$recorded" --confirm >/dev/null 2>&1; then
      ok "Deleted Stripe webhook endpoint $recorded."
    else
      warn "Could not delete Stripe webhook endpoint $recorded; remove it in the Stripe dashboard."
    fi
  fi
  remove_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_WEBHOOK_ENDPOINT_ID
  remove_env "$DEV_ENV_FILE" HUMBUGG_STRIPE_WEBHOOK_SECRET
}
