#!/usr/bin/env bash
# Empty this machine's studio development data, keeping the stack itself.
#
# Port of humbugg/scripts/dev-aws-reset.sh, with one addition that is not
# cosmetic: **studio's prod bucket holds the only copy of the library**, and this
# service spent its first year pointing local tooling at it. So before deleting
# anything, every name is checked against the one this machine's stack is
# supposed to have, and any name containing `prod` aborts outright. A reset
# aimed at the wrong stack is not recoverable by re-running setup.
#
# `--dry-run` names everything it would remove and removes nothing.
# `--skip-cognito` keeps the accounts, so a reset does not mean signing in again.
#
# **It does not re-seed.** `dev-aws-seed.sh` now exists and is the way back, but
# the fixture it loads is #284 and has not been published — so what you get back
# today is an empty stack either way. Named at the end rather than called: a
# reset and a seed are separate decisions, and chaining them would make
# `--skip-cognito` the only way to reset without re-downloading.
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

for command in aws jq terraform; do require_command "$command"; done
load_machine_id false
load_aws_identity
terraform_init
outputs="$(terraform_output_json)"

output_machine_id="$(jq -r '.machine_id.value' <<<"$outputs")"
[[ "$output_machine_id" == "$MACHINE_ID" ]] ||
  die "Terraform state belongs to machine '$output_machine_id', not '$MACHINE_ID'."

pool_id="$(jq -r '.cognito_user_pool_id.value' <<<"$outputs")"
bucket="$(jq -r '.media_bucket_name.value' <<<"$outputs")"
table="$(jq -r '.catalog_table_name.value' <<<"$outputs")"

# ── The guards, in order of what they would cost to get wrong ───────────────
#
# `prod` first and separately. Every other check compares against a value
# derived from this machine's id, so they all fail together if the id is wrong —
# but a name carrying `prod` means something has gone wrong in a way none of
# them anticipates, and the right response is to stop rather than to reason.
for name in "$bucket" "$table"; do
  [[ "$name" != *prod* ]] || die "Refusing: '$name' names a production resource."
done
[[ "$bucket" == "$RESOURCE_PREFIX-media-$AWS_REGION_VALUE" ]] ||
  die "Refusing: unexpected S3 bucket '$bucket'."
[[ "$table" == "$RESOURCE_PREFIX-catalog" ]] ||
  die "Refusing: unexpected DynamoDB table '$table'."
pool_name="$(aws_dev cognito-idp describe-user-pool --user-pool-id "$pool_id" \
  --query 'UserPool.Name' --output text)"
[[ "$pool_name" == "$RESOURCE_PREFIX-app" ]] ||
  die "Refusing: Cognito pool is named '$pool_name', not '$RESOURCE_PREFIX-app'."

object_count="$(aws_dev s3api list-objects-v2 --bucket "$bucket" --query 'KeyCount' --output text 2>/dev/null || echo 0)"
user_count="$(aws_dev cognito-idp list-users --user-pool-id "$pool_id" --query 'length(Users)' --output text)"

printf '\nThis clears development data owned by:\n'
printf '  AWS account: %s\n' "$AWS_ACCOUNT_ID"
printf '  Machine ID:  %s\n' "$MACHINE_ID"
printf '  S3 bucket:   %s  (%s object(s), first page)\n' "$bucket" "$object_count"
printf '  Table:       %s  (deleted and recreated empty)\n' "$table"
if [[ "$SKIP_COGNITO" -eq 1 ]]; then
  printf '  Cognito:     %s  (kept)\n\n' "$pool_id"
else
  printf '  Cognito:     %s  (%s user(s) removed)\n\n' "$pool_id" "$user_count"
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

log "Emptying s3://$bucket ..."
aws_dev s3 rm "s3://$bucket" --recursive >/dev/null

# Deleted and recreated rather than scanned and deleted row by row: a scan-delete
# is many writes, is not atomic, and leaves the table's own state (indexes,
# throughput) unexamined. Terraform rebuilds it exactly as declared.
log "Deleting $table ..."
aws_dev dynamodb delete-table --table-name "$table" >/dev/null
aws_dev dynamodb wait table-not-exists --table-name "$table"

if [[ "$SKIP_COGNITO" -eq 0 ]]; then
  while IFS= read -r username; do
    [[ -n "$username" ]] || continue
    aws_dev cognito-idp admin-delete-user --user-pool-id "$pool_id" --username "$username"
  done < <(aws_dev cognito-idp list-users --user-pool-id "$pool_id" --output json | jq -r '.Users[].Username')
  ok "Removed $user_count Cognito user(s)."
fi

log "Recreating the empty table through Terraform ..."
terraform -chdir="$TF_DIR" apply -input=false -auto-approve "${TF_VARS[@]}"

ok "This machine's studio development data has been reset."
printf '\nThe stack is EMPTY. Refill it with:\n  ./studio/scripts/dev-aws-seed.sh\n'
printf 'That will report that there is no fixture to load — publishing one is\n'
printf '#284 and has not happened. Until it does, empty is as full as it gets.\n'
if [[ "$SKIP_COGNITO" -eq 0 ]]; then
  printf 'The dev account went with the users; recreate it with:\n'
  printf '  ./studio/scripts/dev-user.sh\n'
fi
