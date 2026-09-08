#!/usr/bin/env bash
# Provision this machine's isolated classroom development resources in AWS.
#
# Port of studio/scripts/dev-aws-setup.sh, argument for argument. What it
# provisions is a Cognito pool and one DynamoDB table — no bucket, no Lambda, no
# gateway and no CloudFront, because the API and the SPA both run on this
# machine under `dev-up.sh`. See `infra/envs/dev/main.tf`.
#
# It does not write local env files; `dev-setup.sh` owns those, and reads this
# stack's Terraform outputs to do it.
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
log "AWS region: $AWS_REGION_VALUE"
log "Machine ID: $MACHINE_ID"
log "Resource prefix: $RESOURCE_PREFIX"
log "Terraform state: s3://andreas-services-terraform-state/$STATE_KEY"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  # `load_dev_stack_outputs` reads the state object straight out of S3 rather
  # than running `terraform init` and `terraform output`: a check should not
  # reconfigure the backend or download providers to answer a yes/no question,
  # and this way it works from a cold checkout with no .terraform directory.
  load_dev_stack_outputs
  # The state can describe resources that no longer exist — a table dropped from
  # the console, a pool deleted by hand — so each one is reached for rather than
  # trusted.
  aws_dev cognito-idp describe-user-pool --user-pool-id "$DEV_POOL_ID" >/dev/null ||
    die "Development Cognito pool '$DEV_POOL_ID' is unavailable."
  aws_dev dynamodb describe-table --table-name "$DEV_TABLE" >/dev/null ||
    die "Development pages table '$DEV_TABLE' is unavailable."
  ok "Per-machine AWS development resources are ready."
  exit 0
fi

# terraform_init exports real credentials into the environment before it runs.
# Since the move to a long-lived access key in August 2026 the AWS provider
# resolves them on its own, so this is belt-and-braces rather than the fix it
# once was. See "Environment access" in the root CLAUDE.md.
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
client_id="$(jq -r '.cognito_client_id.value' <<<"$outputs")"
auth_domain="$(jq -r '.cognito_domain.value' <<<"$outputs")"
table="$(jq -r '.pages_table_name.value' <<<"$outputs")"

ok "AWS development resources are ready."
printf '\n  Cognito user pool:   %s\n  Cognito app client:  %s\n  Sign-in host:        https://%s\n  Pages table:         %s\n' \
  "$pool_id" "$client_id" "$auth_domain" "$table"
printf '\nConfirm the stack at any time with:\n  ./classroom/scripts/dev-aws-setup.sh --check %s\n' "$(aws_profile_flag)"
# The table is empty and the pool has no accounts. Say so, because an empty
# stack looks identical to a broken one from the app.
printf '\nThe table and the pool are empty. Nothing has been seeded into them.\n'
printf 'There is no seed fixture, and that is deliberate: a page is a teacher\n'
printf 'typing HTML, so the first one takes about ten seconds to make by hand.\n'
# `dev-user.sh` is NOT called from here. It needs a password decision — a
# generated one or a typed one — and a provisioning script should not make that
# quietly. Print the order instead.
printf '\nThen, in order:\n'
printf '  ./classroom/scripts/dev-user.sh   # its one teacher account\n'
printf '  ./classroom/scripts/dev-setup.sh  # write the local env file\n'
printf '  ./classroom/scripts/dev-up.sh     # API on :8001, SPA on :5174\n'
