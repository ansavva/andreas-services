#!/usr/bin/env bash
# Empty this machine's classroom development data, keeping the stack itself.
#
# Port of studio/scripts/dev-aws-reset.sh. Before deleting anything, every name
# is checked against the one this machine's stack is supposed to have, and any
# name containing `prod` aborts outright. A reset aimed at the wrong stack takes
# a real teacher's pages with it and is not recoverable by re-running setup.
#
# `--dry-run` names everything it would remove and removes nothing.
# `--skip-cognito` keeps the accounts, so a reset does not mean signing in again
# — and, more to the point, keeps the `sub` that every surviving page is keyed
# by. Resetting the pool without the table would leave pages nobody can open.
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
table="$(jq -r '.pages_table_name.value' <<<"$outputs")"
bucket="$(jq -r '.lessons_bucket_name.value // empty' <<<"$outputs")"

# ── The guards, in order of what they would cost to get wrong ───────────────
#
# `prod` first and separately. Every other check compares against a value
# derived from this machine's id, so they all fail together if the id is wrong —
# but a name carrying `prod` means something has gone wrong in a way none of
# them anticipates, and the right response is to stop rather than to reason.
for name in "$table" "$bucket"; do
  [[ -z "$name" || "$name" != *prod* ]] ||
    die "Refusing: '$name' names a production resource."
done
[[ "$table" == "$RESOURCE_PREFIX-pages" ]] ||
  die "Refusing: unexpected DynamoDB table '$table'."
# A lesson bucket holds the only copy of a teacher's uploaded work, so the name
# is checked as strictly as the table's before anything is deleted from it.
[[ -z "$bucket" || "$bucket" == "$RESOURCE_PREFIX-lessons-$AWS_REGION_VALUE" ]] ||
  die "Refusing: unexpected lesson bucket '$bucket'."
pool_name="$(aws_dev cognito-idp describe-user-pool --user-pool-id "$pool_id" \
  --query 'UserPool.Name' --output text)"
[[ "$pool_name" == "$RESOURCE_PREFIX" ]] ||
  die "Refusing: Cognito pool is named '$pool_name', not '$RESOURCE_PREFIX'."

user_count="$(aws_dev cognito-idp list-users --user-pool-id "$pool_id" --query 'length(Users)' --output text)"

printf '\nThis clears development data owned by:\n'
printf '  AWS account: %s\n' "$AWS_ACCOUNT_ID"
printf '  Machine ID:  %s\n' "$MACHINE_ID"
printf '  Table:       %s  (deleted and recreated empty)\n' "$table"
if [[ -n "$bucket" ]]; then
  object_count="$(aws_dev s3api list-objects-v2 --bucket "$bucket" --query 'KeyCount' --output text 2>/dev/null || echo 0)"
  printf '  Lessons:     s3://%s  (%s object(s), first page)\n' "$bucket" "$object_count"
fi
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

# Deleted and recreated rather than scanned and deleted row by row: a
# scan-delete is many writes, is not atomic, and leaves the table's own state
# (the GSI, the billing mode) unexamined. Terraform rebuilds it as declared.
if [[ -n "$bucket" ]]; then
  log "Emptying s3://$bucket ..."
  # Every version, not just the current one: the bucket is versioned, so
  # `s3 rm --recursive` would leave the old versions behind — still billed, and
  # still restorable, which is not what "reset" means.
  aws_dev s3 rm "s3://$bucket" --recursive >/dev/null
  versions="$(aws_dev s3api list-object-versions --bucket "$bucket" \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null || echo '{}')"
  if [[ "$(jq -r '.Objects // [] | length' <<<"$versions")" != "0" ]]; then
    aws_dev s3api delete-objects --bucket "$bucket" --delete "$versions" >/dev/null
  fi
  markers="$(aws_dev s3api list-object-versions --bucket "$bucket" \
    --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' --output json 2>/dev/null || echo '{}')"
  if [[ "$(jq -r '.Objects // [] | length' <<<"$markers")" != "0" ]]; then
    aws_dev s3api delete-objects --bucket "$bucket" --delete "$markers" >/dev/null
  fi
fi

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

ok "This machine's classroom development data has been reset."
if [[ "$SKIP_COGNITO" -eq 0 ]]; then
  printf '\nThe dev account went with the users. Recreate it with:\n'
  printf '  ./classroom/scripts/dev-user.sh\n'
  printf 'It gets a NEW Cognito sub, so any page written before this reset would\n'
  printf 'have been invisible to it — which is why the table is emptied too.\n'
fi
