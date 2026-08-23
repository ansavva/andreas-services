#!/usr/bin/env bash
#
# The two pushes of SHARED MATERIAL into a media bucket. Sourced, never run.
#
# Shared material is what belongs to no character and no project: the
# `config/pose/` plates. `studio/config/` is the source of truth and the library
# holds a copy, because a model may only be handed a presigned URL of a stored
# object.
#
# **This no longer writes to the bucket, and that is the whole of the change.**
# It used to `aws s3 sync` the plates in as bare objects, which was correct while
# they were addressed by raw key and had no catalog record by design. They are
# ordinary nodes now — `check_plates` resolves each one as a name path before a
# shoot spends anything — so an object with no row is a plate the shoot cannot
# see, and the refusal it prints names this very script. Rows are the API's to
# write, so the push goes through `studio config sync` and this is a wrapper
# around it.
#
# `phrasebook/wording.yaml` used to be seeded here too and is not: the phrasebook
# is `TERM#` rows, so there is no document to put anywhere and `studio phrasebook
# add` works against a library that has never held one.
#
# It exists because two scripts need it. `dev-setup.sh` runs from the
# SessionStart hook; `dev-aws-seed.sh` pushes as step 2 of filling a fresh stack.
#
# It prints nothing. Each caller logs in its own voice, so this reports by exit
# status alone.

# The `studio` invocation the push runs through, overridable before sourcing so a
# caller that has not put the CLI on PATH can name it.
if [[ -z "${SHARED_MATERIAL_STUDIO+x}" ]]; then
  SHARED_MATERIAL_STUDIO=(studio)
fi

push_pose_plates() {
  # push_pose_plates <studio_dir> <bucket>  ->  0 pushed or nothing to do, 1 failed
  #
  # `<bucket>` is accepted and unused. The CLI holds no bucket name — it talks to
  # the API, which owns that decision — and the parameter stays so both callers
  # keep their existing call sites and neither grows a second idea of where the
  # library is.
  #
  # Idempotent and additive: `config sync` uploads only the plates with no node
  # and never deletes, for the reason the `--delete` refusal gave before it —
  # anything else under `config/` was put there by something this does not know
  # about.
  #
  # A missing sign-in is NOT a failure here. `dev-setup.sh` runs from the
  # SessionStart hook and has never required one; `config sync` says it skipped
  # and exits 0, so a session starts either way and the first shoot is what
  # names the real problem.
  local studio_dir="$1"
  [[ -d "$studio_dir/config" ]] || return 0
  command -v "${SHARED_MATERIAL_STUDIO[0]}" >/dev/null 2>&1 || return 0
  "${SHARED_MATERIAL_STUDIO[@]}" config sync --apply --quiet
}
