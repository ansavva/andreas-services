#!/usr/bin/env bash
# Provision this machine's isolated studio development resources in AWS.
#
# Port of humbugg/scripts/dev-aws-setup.sh, argument for argument, so the
# mechanism is learned once and applies to both services. What studio does not
# do here is write local env files: humbugg's version ends by populating
# backend/.env and the two frontends' .env.local, while studio's dev-setup.sh
# still reads its values from SSM and points local at prod. Teaching it to point
# at this stack instead is its own change; until then this script provisions the
# resources and prints them.
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
# --check is read-only, so it must not mint a machine ID as a side effect: a
# check on a machine that has never been set up should say so, not quietly
# create the identity the next run would have created anyway.
if [[ "$CHECK_ONLY" -eq 1 ]]; then
  load_machine_id false
else
  load_machine_id true
fi
load_aws_identity

log "AWS account: $AWS_ACCOUNT_ID"
log "AWS principal: $AWS_PRINCIPAL_ARN"
# Logged because it is not cosmetic here: the media bucket's name carries the
# region, so the same machine pointed at a second region gets a second stack.
log "AWS region: $AWS_REGION_VALUE"
log "Machine ID: $MACHINE_ID"
log "Resource prefix: $RESOURCE_PREFIX"
log "Terraform state: s3://andreas-services-terraform-state/$STATE_KEY"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  # `load_dev_stack_outputs` reads the state object straight out of S3 rather
  # than running `terraform init` and `terraform output`: a check should not
  # reconfigure the backend or download providers to answer a yes/no question,
  # and this way it works from a cold checkout with no .terraform directory.
  # `dev-user.sh` and `dev-token.sh` share it, so a stack is located one way.
  load_dev_stack_outputs
  pool_id="$DEV_POOL_ID"
  bucket="$DEV_BUCKET"
  table="$DEV_TABLE"
  # The state can describe resources that no longer exist — a hand-deleted
  # bucket, a pool removed from the console — so each one is reached for rather
  # than trusted. This is the check that tells a developer their stack is ready
  # before they point the integration suite at it.
  aws_dev s3api head-bucket --bucket "$bucket" >/dev/null ||
    die "Development media bucket '$bucket' is unavailable."
  aws_dev cognito-idp describe-user-pool --user-pool-id "$pool_id" >/dev/null ||
    die "Development Cognito pool '$pool_id' is unavailable."
  aws_dev dynamodb describe-table --table-name "$table" >/dev/null ||
    die "Development catalog table '$table' is unavailable."
  ok "Per-machine AWS development resources are ready."
  exit 0
fi

# terraform_init exports real credentials into the environment before it runs.
# `aws login` writes a cache only the AWS CLI reads, so without that export
# `init` and `state list` succeed while `plan` and `apply` fail with an IMDS
# error that reads like an expired session and is not. See "Running Terraform
# locally?" in the root CLAUDE.md.
terraform_init
# No -auto-approve unless --yes: plain `apply` prints the plan and waits for a
# typed "yes", which is the plan-then-confirm step. -input=false only silences
# prompts for missing variables — every variable is supplied in TF_VARS — and
# leaves the approval prompt in place.
apply_args=(apply -input=false "${TF_VARS[@]}")
[[ "$AUTO_APPROVE" -eq 1 ]] && apply_args+=(-auto-approve)
terraform -chdir="$TF_DIR" "${apply_args[@]}"

outputs="$(terraform_output_json)"
pool_id="$(jq -r '.cognito_user_pool_id.value' <<<"$outputs")"
client_id="$(jq -r '.cognito_user_pool_client_id.value' <<<"$outputs")"
bucket="$(jq -r '.media_bucket_name.value' <<<"$outputs")"
table="$(jq -r '.catalog_table_name.value' <<<"$outputs")"

ok "AWS development resources are ready."
printf '\n  Cognito user pool:   %s\n  Cognito app client:  %s\n  Media bucket:        s3://%s/\n  Catalog table:       %s\n' \
  "$pool_id" "$client_id" "$bucket" "$table"
printf '\nConfirm the stack at any time with:\n  ./studio/scripts/dev-aws-setup.sh --check %s\n' "$(aws_profile_flag)"
# The bucket and table are empty and the pool has no accounts. Say so, because
# an empty stack looks identical to a broken one from the app.
printf '\nThe bucket, table and pool are empty. Nothing has been seeded into them,\nand dev-setup.sh still writes prod values into the local env files.\n'
printf '\nGive the pool its one test account with:\n  ./studio/scripts/dev-user.sh\n'
