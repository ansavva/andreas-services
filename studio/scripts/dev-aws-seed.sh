#!/usr/bin/env bash
#
# Load the published dev fixture into this machine's stack.
#
# **This was a thousand lines and is now a wrapper.** The work moved to `studio
# dev-seed load` (`pipeline/…/maintenance/dev_seed.py`), which sits beside
# `publish` so the two halves of a fixture share one set of derivations and one
# validator. What forced the move was arithmetic rather than taste:
#
#     download + upload, one `aws` process per object   71s
#     server-side copy, one `aws` process per object    23s
#     server-side copy, one Python process               0.5s
#     59 node writes as one transaction each             2.5s
#     59 node writes via batch_write_item                0.1s
#
# Seeding is about 0.6 seconds of work against S3 and DynamoDB. The shell
# version spent the other seventy seconds pulling 12.4 MB out of S3 and pushing
# it straight back, and paying ~0.4s of interpreter startup per object — the
# irony being that it reimplemented uuid5 in bash specifically so that it would
# "never need Python". The derivations are pinned against the values this script
# produced, so a stack seeded by either is the same stack, id for id.
#
# What is left here is the part that cannot move: the angle images go in through
# the API rather than through boto3, so they need a signed-in CLI and a library
# that already exists — which is why this runs after the load and not before it.
# That ordering is itself a bug this script once had.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"
# shellcheck source=./dev-shared-material.sh
source "$SCRIPT_DIR/dev-shared-material.sh"

main() {
  load_dev_user_email
  studio dev-seed load "$@"

  # Tolerant of failure on purpose: a developer who has not signed in gets a
  # warning and a seeded stack, not a dead script. `dev-setup.sh` pushes the
  # same angle images at session start and is the other way they arrive.
  push_pose_plates "$SCRIPT_DIR/.." "" &&
    ok "Angle images are in the library." ||
    warn "Could not push studio/config/; a turnaround will report missing angle images."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
