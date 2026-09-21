#!/usr/bin/env bash
# Reset this machine's AWS-backed Humbugg development data and recreate its tables.
#
# Cognito accounts are NOT touched: the pool is the team's shared one
# (infra/envs/dev-shared) and its users are not this machine's to delete. A
# machine that wants fresh people re-runs dev-aws-seed.sh, which converges.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

AUTO_APPROVE=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
    --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
    --yes|-y) AUTO_APPROVE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    # Accepted and ignored: users were never deleted since the pool became shared.
    --skip-cognito) ;;
    --help|-h)
      printf 'Usage: %s [--profile NAME] [--region REGION] [--yes] [--dry-run]\n' "$0"
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

bucket="$(jq -r '.app_bucket_name.value' <<<"$outputs")"

[[ "$bucket" == "humbugg-dev-$AWS_ACCOUNT_ID-$MACHINE_SHORT_ID-app" ]] ||
  die "Refusing reset: unexpected S3 bucket '$bucket'."

printf '\nThis will clear development data owned by:\n'
printf '  AWS account: %s\n' "$AWS_ACCOUNT_ID"
printf '  Machine ID:  %s\n' "$MACHINE_ID"
printf '  Tables:      %s-*\n' "$RESOURCE_PREFIX"
printf '  S3 bucket:   %s\n' "$bucket"
printf '  Cognito:     untouched (the shared pool)\n\n'

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


log "Recreating the empty DynamoDB tables through Terraform..."
terraform -chdir="$TF_DIR" apply -input=false -auto-approve "${TF_VARS[@]}"

if [[ "$backend_was_running" -eq 1 ]]; then
  docker compose -f "$compose_file" up -d backend >/dev/null
fi
ok "This machine's AWS development data has been reset."
