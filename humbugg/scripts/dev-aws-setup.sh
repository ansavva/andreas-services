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
  [[ -f "$HUMBUGG_DIR/backend/.env" && -f "$HUMBUGG_DIR/web/.env.local" && -f "$HUMBUGG_DIR/app/.env.local" ]] ||
    die "Local environment files are missing. Run setup without --check."
  ok "Per-machine AWS resources and local environment files are ready."
  exit 0
fi

terraform_init
apply_args=(apply -input=false "${TF_VARS[@]}")
[[ "$AUTO_APPROVE" -eq 1 ]] && apply_args+=(-auto-approve)
terraform -chdir="$TF_DIR" "${apply_args[@]}"

outputs="$(terraform_output_json)"
pool_id="$(jq -r '.cognito_user_pool_id.value' <<<"$outputs")"
client_id="$(jq -r '.cognito_client_id.value' <<<"$outputs")"
bucket="$(jq -r '.app_bucket_name.value' <<<"$outputs")"

upsert_env() {
  local file="$1" key="$2" value="$3" temp
  mkdir -p "$(dirname "$file")"
  touch "$file"
  temp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    BEGIN { found = 0 }
    $0 ~ "^" key "=" {
      if (!found) print key "=" value
      found = 1
      next
    }
    { print }
    END { if (!found) print key "=" value }
  ' "$file" > "$temp"
  mv "$temp" "$file"
}

remove_env() {
  local file="$1" key="$2" temp
  [[ -f "$file" ]] || return 0
  temp="$(mktemp)"
  awk -v key="$key" '$0 !~ "^" key "=" { print }' "$file" > "$temp"
  mv "$temp" "$file"
}

backend_env="$HUMBUGG_DIR/backend/.env"
upsert_env "$backend_env" AWS_PROFILE "$AWS_PROFILE_VALUE"
upsert_env "$backend_env" AWS_DEFAULT_REGION "$AWS_REGION_VALUE"
upsert_env "$backend_env" COGNITO_REGION "$AWS_REGION_VALUE"
upsert_env "$backend_env" COGNITO_USER_POOL_ID "$pool_id"
upsert_env "$backend_env" COGNITO_CLIENT_ID "$client_id"
upsert_env "$backend_env" DYNAMODB_ENDPOINT_URL ""
upsert_env "$backend_env" S3_ENDPOINT_URL ""
upsert_env "$backend_env" HUMBUGG_APP_BUCKET "$bucket"
upsert_env "$backend_env" HUMBUGG_AVATAR_BASE_URL "https://$bucket.s3.$AWS_REGION_VALUE.amazonaws.com"
upsert_env "$backend_env" HUMBUGG_AVATAR_PRESIGNED_READS "true"
upsert_env "$backend_env" HUMBUGG_PROFILES_TABLE "$(jq -r '.table_names.value.profiles' <<<"$outputs")"
upsert_env "$backend_env" HUMBUGG_GROUPS_TABLE "$(jq -r '.table_names.value.groups' <<<"$outputs")"
upsert_env "$backend_env" HUMBUGG_GROUPMEMBERS_TABLE "$(jq -r '.table_names.value.groupmembers' <<<"$outputs")"
upsert_env "$backend_env" HUMBUGG_DRAWS_TABLE "$(jq -r '.table_names.value.draws' <<<"$outputs")"
upsert_env "$backend_env" HUMBUGG_AUDIT_EVENTS_TABLE "$(jq -r '.table_names.value.audit_events' <<<"$outputs")"
upsert_env "$backend_env" HUMBUGG_ANALYTICS_EVENTS_TABLE "$(jq -r '.table_names.value.analytics_events' <<<"$outputs")"
upsert_env "$backend_env" HUMBUGG_EMAIL_MESSAGES_TABLE "$(jq -r '.table_names.value.email_messages' <<<"$outputs")"
upsert_env "$backend_env" HUMBUGG_BILLING_TABLE "$(jq -r '.table_names.value.billing' <<<"$outputs")"
remove_env "$backend_env" COGNITO_ENDPOINT_URL
remove_env "$backend_env" COGNITO_ISSUER_URL

# Two frontends now, with different prefixes because they run under different
# bundlers: Vite exposes VITE_*, Metro inlines EXPO_PUBLIC_*.
#
# The marketing site no longer authenticates anyone, so it gets no Cognito
# values — only its own origin and where to send someone who wants to sign in.
web_env="$HUMBUGG_DIR/web/.env.local"
upsert_env "$web_env" VITE_APP_BASE_URL "http://localhost:5173"
upsert_env "$web_env" VITE_APP_ORIGIN "http://localhost:8081"
remove_env "$web_env" VITE_COGNITO_USER_POOL_ID
remove_env "$web_env" VITE_COGNITO_CLIENT_ID
remove_env "$web_env" VITE_AWS_REGION
remove_env "$web_env" VITE_COGNITO_ENDPOINT_URL

# The product app holds the auth flow, and reaches the backend cross-origin at
# its dev port rather than through a same-origin proxy.
app_env="$HUMBUGG_DIR/app/.env.local"
upsert_env "$app_env" EXPO_PUBLIC_COGNITO_USER_POOL_ID "$pool_id"
upsert_env "$app_env" EXPO_PUBLIC_COGNITO_CLIENT_ID "$client_id"
upsert_env "$app_env" EXPO_PUBLIC_AWS_REGION "$AWS_REGION_VALUE"
upsert_env "$app_env" EXPO_PUBLIC_API_BASE_URL "http://127.0.0.1:5001/api"

ok "AWS development resources are ready and local env files were updated."

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

printf '\nStart all Humbugg development services with:\n  ./humbugg/scripts/dev-up.sh --profile %s\n\nOr start them individually with:\n  ./humbugg/scripts/dev-up-backend.sh --profile %s\n  ./humbugg/scripts/dev-up-web.sh\n  ./humbugg/scripts/dev-up-app.sh\n  ./humbugg/scripts/dev-up-stripe.sh\n\nFollow backend logs with:\n  ./humbugg/scripts/dev-logs-backend.sh\n' "$AWS_PROFILE_VALUE" "$AWS_PROFILE_VALUE"
