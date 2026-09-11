#!/usr/bin/env bash
# Provision this machine's isolated Humbugg development resources in AWS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

AUTO_APPROVE=0
CHECK_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --yes|-y) AUTO_APPROVE=1 ;;
    --check) CHECK_ONLY=1 ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--yes] [--check]\n' "$0"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

for command in aws jq terraform; do require_command "$command"; done
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  load_machine_id false
else
  load_machine_id true
fi
load_aws_identity

log "AWS account: $AWS_ACCOUNT_ID"
log "AWS principal: $AWS_PRINCIPAL_ARN"
log "Machine ID: $MACHINE_ID"
log "Resource prefix: $RESOURCE_PREFIX"
log "Terraform state: s3://andreas-services-terraform-state/$STATE_KEY"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  state_json="$(aws_dev s3 cp "s3://andreas-services-terraform-state/$STATE_KEY" -)" ||
    die "Terraform state is missing. Run ./humbugg/scripts/dev-setup.sh --profile $AWS_PROFILE_VALUE."
  [[ "$(jq -r '.outputs.machine_id.value // empty' <<<"$state_json")" == "$MACHINE_ID" ]] ||
    die "Terraform state does not match this machine ID."
  bucket="$(jq -r '.outputs.app_bucket_name.value // empty' <<<"$state_json")"
  pool_id="$(jq -r '.outputs.cognito_user_pool_id.value // empty' <<<"$state_json")"
  [[ -n "$bucket" && -n "$pool_id" ]] || die "Terraform state is missing required development outputs."
  aws_dev s3api head-bucket --bucket "$bucket" >/dev/null || die "Development S3 bucket '$bucket' is unavailable."
  aws_dev cognito-idp describe-user-pool --user-pool-id "$pool_id" >/dev/null ||
    die "Development Cognito pool '$pool_id' is unavailable."
  while IFS= read -r table; do
    aws_dev dynamodb describe-table --table-name "$table" >/dev/null ||
      die "Development DynamoDB table '$table' is unavailable."
  done < <(jq -r '.outputs.table_names.value[]' <<<"$state_json")
  [[ -f "$DEV_ENV_FILE" ]] ||
    die "$DEV_ENV_FILE is missing. Run setup without --check."
  for key in COGNITO_USER_POOL_ID HUMBUGG_GROUPS_TABLE EXPO_PUBLIC_COGNITO_CLIENT_ID VITE_API_BASE_URL; do
    [[ -n "$(read_env "$DEV_ENV_FILE" "$key")" ]] ||
      die "$DEV_ENV_FILE has no $key. Run setup without --check."
  done
  ok "Per-machine AWS resources and $DEV_ENV_FILE are ready."
  exit 0
fi

terraform_init
apply_args=(apply -input=false "${TF_VARS[@]}")
[[ "$AUTO_APPROVE" -eq 1 ]] && apply_args+=(-auto-approve)
terraform -chdir="$TF_DIR" "${apply_args[@]}"

outputs="$(terraform_output_json)"
pool_id="$(jq -r '.cognito_user_pool_id.value' <<<"$outputs")"
client_id="$(jq -r '.cognito_client_id.value' <<<"$outputs")"
auth_domain="$(jq -r '.cognito_auth_domain.value' <<<"$outputs")"
bucket="$(jq -r '.app_bucket_name.value' <<<"$outputs")"

# Everything below lands in the one per-machine file. Generated keys are
# rewritten on every run; keys the developer set by hand (Stripe, plan limits)
# are never touched, and defaults are seeded only where no line exists yet.
env_file="$DEV_ENV_FILE"

# The three in-repo files this replaced. Import any key the new file lacks —
# the Stripe keys were only ever typed into backend/.env by hand — then remove
# them, because an ignored file nothing reads is exactly the confusion this
# consolidation exists to end.
import_legacy_env() {
  local legacy="$1" line key
  [[ -f "$legacy" ]] || return 0
  while IFS= read -r line; do
    [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
    key="${BASH_REMATCH[1]}"
    ensure_env "$env_file" "$key" "${BASH_REMATCH[2]}"
  done < "$legacy"
  rm -f "$legacy"
  ok "Imported $legacy into $env_file and removed it."
}
import_legacy_env "$HUMBUGG_DIR/backend/.env"
import_legacy_env "$HUMBUGG_DIR/app/.env.local"
import_legacy_env "$HUMBUGG_DIR/marketing/.env.local"

# Render the whole file in a fixed layout rather than upserting keys one at a
# time: upserts append in write order, and the result read like a log. Generated
# keys are written fresh from Terraform, hand-set keys are read back out of the
# current file, and anything unrecognised is carried over at the end rather
# than lost. No associative arrays: /bin/bash on macOS is still 3.2.
previous="$(mktemp)"
chmod 600 "$previous"
cat "$env_file" > "$previous" 2>/dev/null || true

# Keys earlier versions wrote and nothing reads now — Amplify's pool id and
# region, the local Cognito endpoints — are dropped rather than carried over.
for key in COGNITO_ENDPOINT_URL COGNITO_ISSUER_URL VITE_COGNITO_USER_POOL_ID VITE_COGNITO_CLIENT_ID \
  VITE_AWS_REGION VITE_COGNITO_ENDPOINT_URL EXPO_PUBLIC_COGNITO_USER_POOL_ID EXPO_PUBLIC_AWS_REGION \
  ASPNETCORE_ENVIRONMENT CORS_ORIGIN APP_BASE_URL; do
  remove_env "$previous" "$key"
done

written=""
rendered="$(mktemp)"
chmod 600 "$rendered"
exec 3>"$rendered"
line() { printf '%s\n' "$*" >&3; }
# A generated key: always the fresh value.
gen() { line "$1=$2"; written="$written $1"; }
# A hand-set key: the file's value if it has one, else the default, else a
# commented placeholder so the slot is visible.
keep() {
  local key="$1" default="${2-}"
  if grep -Eq "^${key}=" "$previous"; then line "$key=$(read_env "$previous" "$key")"
  elif [[ -n "$default" ]]; then line "$key=$default"
  else line "#$key="; fi
  written="$written $key"
}
table() { gen "$1" "$(jq -r ".table_names.value.$2" <<<"$outputs")"; }

line "# Humbugg local development — the one file. humbugg/dev.env.sample documents it."
line "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) by dev-aws-setup.sh for machine $MACHINE_SHORT_ID."
line ""
line "# ---- generated (rewritten on every dev-aws-setup.sh run; do not hand-edit) ----"
line ""
line "# AWS"
gen AWS_PROFILE "$AWS_PROFILE_VALUE"
gen AWS_DEFAULT_REGION "$AWS_REGION_VALUE"
line ""
line "# Cognito"
gen COGNITO_REGION "$AWS_REGION_VALUE"
gen COGNITO_USER_POOL_ID "$pool_id"
gen COGNITO_CLIENT_ID "$client_id"
line ""
line "# Storage. Empty endpoints mean real AWS, not a local emulator."
gen DYNAMODB_ENDPOINT_URL ""
gen S3_ENDPOINT_URL ""
gen HUMBUGG_APP_BUCKET "$bucket"
gen HUMBUGG_AVATAR_BASE_URL "https://$bucket.s3.$AWS_REGION_VALUE.amazonaws.com"
gen HUMBUGG_AVATAR_PRESIGNED_READS "true"
line ""
line "# DynamoDB tables — all twelve required; the backend refuses to start without any one."
table HUMBUGG_PROFILES_TABLE profiles
table HUMBUGG_GROUPS_TABLE groups
table HUMBUGG_GROUPMEMBERS_TABLE groupmembers
table HUMBUGG_WISHES_TABLE wishes
table HUMBUGG_DRAWS_TABLE draws
table HUMBUGG_AUDIT_EVENTS_TABLE audit_events
table HUMBUGG_ANALYTICS_EVENTS_TABLE analytics_events
table HUMBUGG_EMAIL_MESSAGES_TABLE email_messages
table HUMBUGG_BILLING_TABLE billing
table HUMBUGG_INVITATIONS_TABLE invitations
table HUMBUGG_REMINDERS_TABLE reminders
table HUMBUGG_TEMPLATES_TABLE templates
table HUMBUGG_QUESTIONS_TABLE questions
line ""
# The product app holds the auth flow, and reaches the backend cross-origin at
# its dev port rather than through a same-origin proxy. Metro inlines these.
line "# Product app (Metro inlines EXPO_PUBLIC_*; dev-up-app.sh exports only this prefix)."
line "# The domain is the Managed Login HOST — no scheme, no path — a default Cognito"
line "# domain on a dev stack rather than a name Humbugg owns."
gen EXPO_PUBLIC_COGNITO_CLIENT_ID "$client_id"
gen EXPO_PUBLIC_COGNITO_DOMAIN "$auth_domain"
gen EXPO_PUBLIC_API_BASE_URL "http://127.0.0.1:5001/api"
gen EXPO_PUBLIC_WEB_BASE_URL "http://localhost:5176"
line ""
# The marketing site no longer authenticates anyone, so it gets no Cognito
# values — only its own origin and where to send someone who wants to sign in.
# VITE_API_BASE_URL exists only to point the pricing page at the local backend
# (#158); production defaults to api.humbugg.com in site.ts.
line "# Marketing site (Vite inlines VITE_*; dev-up-marketing.sh exports only this prefix)."
gen VITE_APP_BASE_URL "http://localhost:5176"
gen VITE_APP_ORIGIN "http://localhost:8081"
gen VITE_API_BASE_URL "http://127.0.0.1:5001"
line ""
line "# ---- yours (kept as-is across reruns) -----------------------------------------"
line ""
line "# Dev test account — dev-user.sh writes both; a reserved .test address belongs here."
keep HUMBUGG_DEV_USER_EMAIL
keep HUMBUGG_DEV_USER_PASSWORD
line ""
line "# Plans. Unset means the backend defaults (6 / 50 / 10000, \$12 / \$99)."
line "# Lower HUMBUGG_FREE_PARTICIPANT_LIMIT to hit the Free cap with fewer accounts."
keep HUMBUGG_FREE_PARTICIPANT_LIMIT
keep HUMBUGG_PLUS_PARTICIPANT_LIMIT
keep HUMBUGG_WORK_PARTICIPANT_LIMIT
keep HUMBUGG_PLUS_PRICE_CENTS
keep HUMBUGG_WORK_PRICE_CENTS
keep HUMBUGG_WORK_ENABLED false
line ""
line "# Stripe, TEST MODE ONLY (live is blocked, #159). 'disabled' runs without Stripe."
line "# dev-up.sh writes the webhook secret from 'stripe listen'; docs/stripe-setup.md."
keep HUMBUGG_STRIPE_MODE disabled
keep HUMBUGG_PLUS_PRODUCT_ID
keep HUMBUGG_PLUS_PRICE_ID
keep HUMBUGG_WORK_PRODUCT_ID
keep HUMBUGG_WORK_PRICE_ID
keep HUMBUGG_STRIPE_PUBLISHABLE_KEY
keep HUMBUGG_STRIPE_SECRET_KEY
keep HUMBUGG_STRIPE_WEBHOOK_SECRET

# Anything the file held that no section above claims.
leftover="$(awk -F= -v written=" $written " '
  /^[A-Za-z_][A-Za-z0-9_]*=/ && index(written, " " $1 " ") == 0 { print }
' "$previous" | sort)"
if [[ -n "$leftover" ]]; then
  line ""
  line "# ---- not managed by any script; carried over as found ------------------------"
  line "$leftover"
fi
exec 3>&-
rm -f "$previous"
mv "$rendered" "$env_file"

ok "AWS development resources are ready; $env_file is up to date."

# If setup is reapplied while the backend is already running, replace the container so it receives
# the freshly exported credentials. Container environment variables cannot be changed in place.
compose_file="$HUMBUGG_DIR/backend/docker-compose.yml"
if command -v docker >/dev/null 2>&1 &&
  docker compose version >/dev/null 2>&1 &&
  docker compose -f "$compose_file" ps --services --status running 2>/dev/null | grep -qx backend; then
  log "Recreating the running backend with refreshed AWS credentials..."
  export AWS_DEFAULT_REGION="$AWS_REGION_VALUE"
  docker compose -f "$compose_file" up -d --build --force-recreate backend
  ok "The running backend now has refreshed AWS credentials."
fi

printf '\nStart all Humbugg development services with:\n  ./humbugg/scripts/dev-up.sh --profile %s\n\nOr start them individually with:\n  ./humbugg/scripts/dev-up-backend.sh --profile %s\n  ./humbugg/scripts/dev-up-marketing.sh\n  ./humbugg/scripts/dev-up-app.sh\n  ./humbugg/scripts/dev-up-stripe.sh\n\nFollow backend logs with:\n  ./humbugg/scripts/dev-logs-backend.sh\n' "$AWS_PROFILE_VALUE" "$AWS_PROFILE_VALUE"
