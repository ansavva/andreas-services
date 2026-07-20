#!/usr/bin/env bash
# Provision this machine's isolated Humbugg development resources in AWS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

AUTO_APPROVE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --yes|-y) AUTO_APPROVE=1 ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--yes]\n' "$0"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

for command in aws jq terraform; do require_command "$command"; done
load_machine_id true
load_aws_identity

log "AWS account: $AWS_ACCOUNT_ID"
log "AWS principal: $AWS_PRINCIPAL_ARN"
log "Machine ID: $MACHINE_ID"
log "Resource prefix: $RESOURCE_PREFIX"
log "Terraform state: s3://andreas-services-terraform-state/$STATE_KEY"

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

frontend_env="$HUMBUGG_DIR/frontend/.env.local"
upsert_env "$frontend_env" VITE_COGNITO_USER_POOL_ID "$pool_id"
upsert_env "$frontend_env" VITE_COGNITO_CLIENT_ID "$client_id"
upsert_env "$frontend_env" VITE_AWS_REGION "$AWS_REGION_VALUE"
upsert_env "$frontend_env" VITE_APP_BASE_URL "http://localhost:5173"
remove_env "$frontend_env" VITE_COGNITO_ENDPOINT_URL

ok "AWS development resources are ready and local env files were updated."
printf '\nStart all Humbugg development services with:\n  ./humbugg/scripts/dev-up.sh --profile %s\n\nOr start them individually with:\n  ./humbugg/scripts/dev-up-backend.sh --profile %s\n  ./humbugg/scripts/dev-up-frontend.sh\n  ./humbugg/scripts/dev-up-stripe.sh\n' "$AWS_PROFILE_VALUE" "$AWS_PROFILE_VALUE"
