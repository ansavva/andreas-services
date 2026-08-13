#!/usr/bin/env bash
#
# ONE-TIME. Delete this script once prod is green.
#
# Clears the three resources #227's half-applied rename left stuck, so that
# `Website · Deploy · Prod` can converge. Nothing here belongs in the pipeline:
# it exists because an apply died partway, not because a deploy ever needs it.
#
# Why Terraform cannot do this itself
# -----------------------------------
# Terraform applies the destroy half of a replacement against PRIOR STATE, not
# against the new configuration — the destroy node receives the old object with
# Config null. So the force_delete/force_destroy this PR adds are read from
# state (false) and ignored, and the destroys keep failing:
#
#   deleting S3 Bucket (andreas-services-website-assets-production): BucketNotEmpty
#   ECR Repository (website-frontend) not empty, consider using force_delete
#   creating ECR Repository (website-prod-api): RepositoryAlreadyExists
#
# Measured, not assumed: renaming a bucket and setting force_destroy=true in one
# apply fails with BucketNotEmpty; setting force_destroy=true first and renaming
# second succeeds. The flags in this PR protect the NEXT rename.
#
# What this leaves behind, deliberately
# -------------------------------------
# website-api and website-frontend stay in AWS, untracked. That is the safe
# direction: website-api still backs the live website-api Lambda until the apply
# replaces it with website-prod-api. Delete both once the deploy is green — the
# last section prints the commands.
#
#   ./website/scripts/reconcile-prod-rename.sh --dry-run
#   ./website/scripts/reconcile-prod-rename.sh
#
set -euo pipefail

CHDIR="website/infra/envs/prod"
OLD_ASSETS_BUCKET="andreas-services-website-assets-production"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

run() {
  if (( DRY_RUN )); then
    printf 'would run: %s\n' "$*"
  else
    printf '+ %s\n' "$*"
    "$@"
  fi
}

if [[ ! -d "${CHDIR}" ]]; then
  echo "Run this from the repository root." >&2
  exit 1
fi

# Fail here rather than three commands in. `terraform state rm` can succeed off
# the backend while the very next `terraform import` dies calling ECR, which is
# exactly how the first run of this script stranded api[0]: removed from state,
# never re-imported, and the deploy then tried to create a repository that
# already existed.
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials are not valid. Run 'aws login', then run this again." >&2
  exit 1
fi

if (( ! DRY_RUN )); then
  read -r -p 'This edits live prod Terraform state. Type "reconcile" to continue: ' reply
  [[ "${reply}" == "reconcile" ]] || { echo "Aborted."; exit 1; }
fi

terraform -chdir="${CHDIR}" init -input=false >/dev/null

# One authoritative read of the state. Under `set -e` an unreachable backend
# aborts here, loudly. That matters more than it looks: the per-address
# `state show 2>/dev/null` this replaced could not tell "the address is absent"
# from "I could not reach S3", and the resume branch below acts on exactly that
# difference — it would have read a credentials failure as "already removed,
# import it" and imported over a healthy state.
STATE_LIST="$(terraform -chdir="${CHDIR}" state list)"

state_has() { grep -qxF "$1" <<<"${STATE_LIST}"; }

state_holds() { # address -> prints the name/bucket recorded at that address
  terraform -chdir="${CHDIR}" state show "$1" |
    awk '$1=="name"||$1=="bucket"{print $3; exit}' | tr -d '"'
}

# 1. website-api -> website-prod-api.
#    The old build-and-push created website-prod-api with the AWS CLI before
#    Terraform could, so the create half collides with a repository that already
#    exists. Forget the old repository at this address and adopt the new one;
#    the plan then has no ECR work left to do.
#    Branch on what the address holds NOW rather than assuming a clean start.
#    The empty case is not hypothetical: it is where a run that died between the
#    state rm and the import leaves things, and treating it as "nothing to do"
#    is what let the first attempt report success on a re-run while the deploy
#    stayed broken.
api_addr='module.compute.aws_ecr_repository.api[0]'
api_holds=""
state_has "${api_addr}" && api_holds="$(state_holds "${api_addr}")"
case "${api_holds}" in
  website-prod-api)
    echo "skip: api[0] already holds website-prod-api"
    ;;
  website-api)
    run terraform -chdir="${CHDIR}" state rm 'module.compute.aws_ecr_repository.api[0]'
    run terraform -chdir="${CHDIR}" import -input=false \
      'module.compute.aws_ecr_repository.api[0]' website-prod-api
    ;;
  "")
    if aws ecr describe-repositories --repository-names website-prod-api >/dev/null 2>&1; then
      echo "api[0] is empty and website-prod-api exists — resuming the import"
      run terraform -chdir="${CHDIR}" import -input=false \
        'module.compute.aws_ecr_repository.api[0]' website-prod-api
    else
      echo "skip: website-prod-api does not exist, Terraform will create it"
    fi
    ;;
  *)
    echo "api[0] holds an unexpected repository (${api_holds}); stopping." >&2
    exit 1
    ;;
esac

# 2. aws_ecr_repository.frontend[0] is an address the configuration no longer
#    has — #227 renamed it to .www, which already applied. Terraform wants to
#    destroy website-frontend and cannot: 13 images, force_delete false in
#    state, and no configuration left to carry a new value. Forgetting it is the
#    only move that converges.
if state_has 'module.compute.aws_ecr_repository.frontend[0]'; then
  run terraform -chdir="${CHDIR}" state rm 'module.compute.aws_ecr_repository.frontend[0]'
else
  echo "skip: frontend[0] already out of state"
fi

# 3. The assets bucket rename cannot delete a bucket holding 20 objects. Empty
#    it so the destroy succeeds and Terraform stays authoritative — the
#    alternative, forgetting it, would strand the bucket policy and public
#    access block that the failed apply already deleted from it.
#
#    Emptying costs nothing: every object is a hashed client asset that
#    deploy-frontend-assets re-syncs into the new bucket in the same run, and
#    CloudFront serves them immutable so edge copies keep answering meanwhile.
if aws s3 ls "s3://${OLD_ASSETS_BUCKET}" >/dev/null 2>&1; then
  run aws s3 rm "s3://${OLD_ASSETS_BUCKET}" --recursive
else
  echo "skip: ${OLD_ASSETS_BUCKET} is gone"
fi

cat <<'EOF'

Done. Now merge the PR and re-run "Website · Deploy · Prod".

Once it is green, delete the two repositories this deliberately left behind and
then delete this script:

  aws ecr delete-repository --repository-name website-api --force
  aws ecr delete-repository --repository-name website-frontend --force
EOF
