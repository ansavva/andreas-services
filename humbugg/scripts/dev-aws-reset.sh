#!/usr/bin/env bash
# Reset this machine's AWS-backed Humbugg development data and recreate its tables.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

AUTO_APPROVE=0
DRY_RUN=0
SKIP_COGNITO=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --yes|-y) AUTO_APPROVE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --skip-cognito) SKIP_COGNITO=1 ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--yes] [--dry-run] [--skip-cognito]\n' "$0"
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

for command in aws docker jq terraform; do require_command "$command"; done
load_machine_id false
load_aws_identity
terraform_init
outputs="$(terraform_output_json)"
output_machine_id="$(jq -r '.machine_id.value' <<<"$outputs")"
[[ "$output_machine_id" == "$MACHINE_ID" ]] ||
  die "Terraform state belongs to machine '$output_machine_id', not '$MACHINE_ID'."

pool_id="$(jq -r '.cognito_user_pool_id.value' <<<"$outputs")"
bucket="$(jq -r '.app_bucket_name.value' <<<"$outputs")"
expected_pool_name="$RESOURCE_PREFIX-development"

[[ "$bucket" == "humbugg-dev-$AWS_ACCOUNT_ID-$MACHINE_SHORT_ID-app" ]] ||
  die "Refusing reset: unexpected S3 bucket '$bucket'."
pool_name="$(aws_dev cognito-idp describe-user-pool --user-pool-id "$pool_id" --query 'UserPool.Name' --output text)"
[[ "$pool_name" == "$expected_pool_name" ]] ||
  die "Refusing reset: Cognito pool is named '$pool_name', not '$expected_pool_name'."

printf '\nThis will clear development data owned by:\n'
printf '  AWS account: %s\n' "$AWS_ACCOUNT_ID"
printf '  Machine ID:  %s\n' "$MACHINE_ID"
printf '  Tables:      %s-*\n' "$RESOURCE_PREFIX"
printf '  S3 bucket:   %s\n' "$bucket"
if [[ "$SKIP_COGNITO" -eq 1 ]]; then
  printf '  Cognito:     skipped\n\n'
else
  printf '  Cognito:     %s (users only)\n\n' "$pool_id"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  ok "Dry run complete; nothing was changed."
  exit 0
fi
if [[ "$AUTO_APPROVE" -eq 0 ]]; then
  [[ -t 0 ]] || die "Non-interactive reset requires --yes."
  read -r -p "Type RESET to continue: " confirmation
  [[ "$confirmation" == "RESET" ]] || die "Reset canceled."
fi

compose_file="$HUMBUGG_DIR/backend/docker-compose.yml"
backend_was_running=0
if docker compose -f "$compose_file" ps --services --status running 2>/dev/null | grep -qx backend; then
  backend_was_running=1
  docker compose -f "$compose_file" stop backend >/dev/null
fi

tables=()
while IFS= read -r table; do
  [[ "$table" == "$RESOURCE_PREFIX-"* ]] || die "Refusing to delete unexpected table '$table'."
  tables+=("$table")
done < <(jq -r '.table_names.value[]' <<<"$outputs")

for table in "${tables[@]}"; do
  log "Deleting $table..."
  aws_dev dynamodb delete-table --table-name "$table" >/dev/null
done
for table in "${tables[@]}"; do
  aws_dev dynamodb wait table-not-exists --table-name "$table"
done

log "Emptying s3://$bucket..."
aws_dev s3 rm "s3://$bucket" --recursive >/dev/null

if [[ "$SKIP_COGNITO" -eq 0 ]]; then
  users_json="$(aws_dev cognito-idp list-users --user-pool-id "$pool_id" --output json)"
  while IFS= read -r username; do
    [[ -n "$username" ]] || continue
    aws_dev cognito-idp admin-delete-user --user-pool-id "$pool_id" --username "$username"
  done < <(jq -r '.Users[].Username' <<<"$users_json")
  ok "Removed $(jq '.Users | length' <<<"$users_json") Cognito user(s)."
fi

log "Recreating the empty DynamoDB tables through Terraform..."
terraform -chdir="$TF_DIR" apply -input=false -auto-approve "${TF_VARS[@]}"

if [[ "$backend_was_running" -eq 1 ]]; then
  docker compose -f "$compose_file" up -d backend >/dev/null
fi
ok "This machine's AWS development data has been reset."
