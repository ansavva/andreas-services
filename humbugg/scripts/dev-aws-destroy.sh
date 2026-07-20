#!/usr/bin/env bash
# Destroy this machine's isolated Humbugg development resources in AWS.
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
load_machine_id false
load_aws_identity
terraform_init

state_resources="$(terraform -chdir="$TF_DIR" state list)"
if [[ -n "$state_resources" ]]; then
  output_machine_id="$(terraform -chdir="$TF_DIR" output -raw machine_id)"
  [[ "$output_machine_id" == "$MACHINE_ID" ]] ||
    die "Terraform state belongs to machine '$output_machine_id', not '$MACHINE_ID'."
fi

warn "This will destroy only resources tagged for machine $MACHINE_ID in account $AWS_ACCOUNT_ID."
destroy_args=(destroy -input=false "${TF_VARS[@]}")
[[ "$AUTO_APPROVE" -eq 1 ]] && destroy_args+=(-auto-approve)
terraform -chdir="$TF_DIR" "${destroy_args[@]}"
ok "This machine's Humbugg development resources were destroyed. The machine ID was retained for safe reuse."
