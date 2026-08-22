#!/usr/bin/env bash
#
# The two pushes of SHARED MATERIAL into a media bucket. Sourced, never run.
#
# Shared material is what belongs to no character and no project:
# `config/pose/` and `phrasebook/wording.yaml`. `catalog_seed.py` deliberately
# records no node for either, so neither can be reached by name and neither can
# be created through the API's node routes — they are put in the bucket
# directly, and this file is the only place that happens.
#
# It exists because two scripts need it. `dev-setup.sh` runs from the
# SessionStart hook and pushes on every session; `dev-aws-seed.sh` pushes as
# step 2 of filling a fresh stack. One definition, so the two rules below are
# stated once instead of drifting apart.
#
# **The two pushes are not the same operation, and that is the point.**
#
#   config/pose/            repo-owned. studio/config/ is the source of truth,
#                           the bucket holds a copy, so a re-sync is correct.
#   phrasebook/wording.yaml bucket-owned from the first `studio phrasebook add`.
#                           Copied in ONLY when absent; syncing the repo copy
#                           over it would delete recorded entries.
#
# Neither function prints anything. Each caller logs in its own voice — the two
# have different prefixes — so these report by exit status alone.

# The AWS command each push runs through, overridable before sourcing. Plain
# `aws` by default so `dev-setup.sh` needs no setup; `dev-aws-seed.sh` sets it
# to `aws_dev`, which carries the --profile and --region decision
# `dev-aws-common.sh` already made for that run.
if [[ -z "${SHARED_MATERIAL_AWS+x}" ]]; then
  SHARED_MATERIAL_AWS=(aws)
fi

push_pose_plates() {
  # push_pose_plates <studio_dir> <bucket>  ->  0 synced, 1 failed
  #
  # --size-only because S3 mtimes always differ from local ones, which would
  # re-upload every plate on every session — and the caller runs on every
  # session.
  #
  # NEVER --delete. It would remove anything under config/ that is not in this
  # checkout, including whatever a later fixture puts there. This used to write
  # to the PROD bucket, which made --delete unthinkable; it now writes to this
  # machine's dev bucket, which makes it merely wrong.
  local studio_dir="$1" bucket="$2"
  [[ -d "$studio_dir/config" ]] || return 0
  "${SHARED_MATERIAL_AWS[@]}" s3 sync "$studio_dir/config/" "s3://$bucket/config/" \
    --size-only --only-show-errors
}

seed_phrasebook() {
  # seed_phrasebook <studio_dir> <bucket>  ->  0 copied, 2 already there, 1 failed
  #
  # `PATCH /api/text` requires the key to name an object that already exists —
  # the route overwrites and never invents, because there is no upload route for
  # a keyed object with no node. So `studio phrasebook add` fails permanently
  # against a stack that has never held a wording.yaml (#425), and this is what
  # puts the first one there.
  #
  # A HEAD that fails for a reason other than 404 — no permission, no bucket —
  # is treated as absent and falls through to the copy, which then fails on the
  # same cause and reports it. Distinguishing the two here would only move the
  # message.
  local studio_dir="$1" bucket="$2"
  local source="$studio_dir/phrasebook/wording.yaml"
  [[ -f "$source" ]] || return 1
  if "${SHARED_MATERIAL_AWS[@]}" s3api head-object \
       --bucket "$bucket" --key phrasebook/wording.yaml >/dev/null 2>&1; then
    return 2
  fi
  "${SHARED_MATERIAL_AWS[@]}" s3 cp "$source" "s3://$bucket/phrasebook/wording.yaml" \
    --only-show-errors
}
