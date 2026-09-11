#!/usr/bin/env bash
# Destroy this machine's isolated classroom development resources in AWS.
#
# Port of studio/scripts/dev-aws-destroy.sh, argument for argument.
#
# **The machine id is deliberately retained.** Destroying the stack does not
# retire the identity that named it, so a later `dev-aws-setup.sh` re-provisions
# the same resource names against the same state key. Deleting the id would
# strand the state object and mint a second stack beside the first.
#
# **This works where prod's does not**, and for a reason worth keeping in view:
# every page in the pool is keyed by a Cognito `sub`, so destroying prod's pool
# would orphan every page ever written. Here the pool holds one test account and
# the table holds pages that same account typed, so both are disposable.
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
# `false`: destroying on a machine that was never set up should say so, not mint
# an identity and then find nothing to destroy under it.
load_machine_id false
load_aws_identity
terraform_init

# The state must belong to this machine. Without this a mistyped machine id
# points terraform at somebody else's stack and destroys it — the one mistake
# here that cannot be undone by re-running setup.
state_resources="$(terraform -chdir="$TF_DIR" state list)"
if [[ -n "$state_resources" ]]; then
  output_machine_id="$(terraform -chdir="$TF_DIR" output -raw machine_id)"
  [[ "$output_machine_id" == "$MACHINE_ID" ]] ||
    die "Terraform state belongs to machine '$output_machine_id', not '$MACHINE_ID'."
else
  ok "Nothing to destroy: this machine has no stack in Terraform state."
  exit 0
fi

warn "This destroys only resources for machine $MACHINE_ID in account $AWS_ACCOUNT_ID."
warn "The pages table and every page in it go with them, and so does the pool."
destroy_args=(destroy -input=false "${TF_VARS[@]}")
[[ "$AUTO_APPROVE" -eq 1 ]] && destroy_args+=(-auto-approve)
terraform -chdir="$TF_DIR" "${destroy_args[@]}"

ok "This machine's classroom development resources were destroyed."
printf '\nThe machine id was kept, so setup rebuilds the same names:\n  %s\n' "$MACHINE_ID"
printf '  ./classroom/scripts/dev-aws-setup.sh\n'
