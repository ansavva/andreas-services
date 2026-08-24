#!/usr/bin/env bash
#
# dev-setup.sh — install the prerequisites the studio generation skills need.
#
# This is mainly for the LOCAL half of studio: the skills under
# studio/.claude/skills/ that run inside Claude on your machine.
#
# It is not *only* that half, and the difference matters. CI builds the deployed
# half, but a person or an agent working on it locally still needs the parts CI
# gets for free: frontend/.env.local (step 3) and frontend/node_modules (step 4).
# This header used to claim the deployed half "needs nothing from here", which
# read as a scope boundary and left those prerequisites owned by no script at
# all — the reason a clean checkout reported `tsc: not found`.
#
# The only hard requirement is `uv`. The pipeline itself is one package
# (studio/pipeline) with one dependency set, exposing one command: `studio`.
# This installs uv if missing, syncs that package, and puts its console script
# on PATH for the session.
#
# Safe to run repeatedly: every step checks before it acts (idempotent) and runs
# non-interactively. The repo's SessionStart hook calls it on every session.

set -euo pipefail

log() { printf '\033[36m[studio-setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[studio-setup]\033[0m %s\n' "$*"; }

# Resolve studio/ so this works no matter where it is invoked from. Note this is
# studio/, not the repo root: the skills resolve their own paths relative to it
# (studio/.env, studio/infra/README.md), so studio/ is what they treat as root.
STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------------------
# 1. Ensure uv is installed (via Homebrew) and on PATH.
# ---------------------------------------------------------------------------
# Make sure a Homebrew install is visible on PATH before we probe for uv —
# brew's bin isn't always exported yet in a bare non-interactive shell.
for brew_prefix in /opt/homebrew /usr/local /home/linuxbrew/.linuxbrew; do
  [ -x "$brew_prefix/bin/brew" ] && export PATH="$brew_prefix/bin:$PATH"
done

if command -v uv >/dev/null 2>&1; then
  log "uv already installed: $(uv --version)"
elif command -v brew >/dev/null 2>&1; then
  log "installing uv via Homebrew..."
  brew install uv
  hash -r 2>/dev/null || true
  log "uv installed: $(uv --version)"
else
  warn "uv is not installed and Homebrew is unavailable."
  warn "Install Homebrew (https://brew.sh) and re-run, or install uv yourself."
  exit 1
fi

# Persist uv's directory on PATH for the rest of a Claude Code session, when
# available. Derive it from where uv actually resolves rather than assuming a
# fixed location, so it works with whatever prefix Homebrew used.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  UV_BIN_DIR="$(dirname "$(command -v uv)")"
  if ! grep -qs "$UV_BIN_DIR" "$CLAUDE_ENV_FILE" 2>/dev/null; then
    echo "export PATH=\"$UV_BIN_DIR:\$PATH\"" >> "$CLAUDE_ENV_FILE"
    log "added uv bin dir to CLAUDE_ENV_FILE"
  fi
fi

# ---------------------------------------------------------------------------
# 2. Install the pipeline and put its `studio` command on PATH.
#
#    The pipeline used to be a set of standalone scripts, each declaring its own
#    dependencies inline and invoked by its path. It is now one package with one
#    dependency set, exposing one command — so setup is a sync rather than a
#    per-script cache warm, and the skills can say `studio runs list` instead of
#    naming a file.
# ---------------------------------------------------------------------------
PIPELINE="$STUDIO_DIR/pipeline"

if [ -f "$PIPELINE/pyproject.toml" ]; then
  log "syncing the pipeline environment..."
  if uv sync --project "$PIPELINE" --quiet; then
    log "pipeline ready: $(uv run --project "$PIPELINE" studio --help 2>/dev/null | head -1)"
  else
    warn "could not sync the pipeline environment — 'studio' will be unavailable."
  fi

  # Expose the console script for the rest of the session, the same way uv is
  # exposed above. Without this a caller has to spell out
  # `uv run --project studio/pipeline studio ...` every time.
  VENV_BIN="$PIPELINE/.venv/bin"
  if [ -d "$VENV_BIN" ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    if ! grep -qs "$VENV_BIN" "$CLAUDE_ENV_FILE" 2>/dev/null; then
      echo "export PATH=\"$VENV_BIN:\$PATH\"" >> "$CLAUDE_ENV_FILE"
      log "added the pipeline's bin dir to CLAUDE_ENV_FILE"
    fi
  fi
else
  warn "no pipeline package at $PIPELINE — skipping."
fi

# ---------------------------------------------------------------------------
# 3. Write the env files, from THIS MACHINE'S DEV STACK.
#
#    This block used to read `/studio/prod/*` from SSM and pin the live bucket
#    and the live Cognito pool into the local env files, under a heading that
#    read "LOCAL POINTS AT PROD, DELIBERATELY". **That is over (#287.)** Studio
#    stops connecting to production from this repo, the way every other service
#    in the monorepo already works. The old reasoning — that a second, empty
#    bucket would exercise none of the behaviour that matters — is answered by
#    seeding the dev stack from a published fixture (#284, #285) rather than by
#    pointing at prod.
#
#    Running the CLI against production is a `studio --profile prod <command>`
#    now, and it is deliberately still not a flag on this script: this one sets
#    up the LOCAL half, and pointing that at prod is what #287 removed. Step 3a
#    below syncs the `dev` profile; `studio profile sync prod` writes the other.
#
#    Values come from the dev stack's Terraform outputs, not SSM: SSM holds what
#    the deploy workflow wrote, and nothing deploys a dev stack.
#
#    **This step is skippable and must stay that way.** The SessionStart hook
#    runs this script on every session, including on a machine that has never
#    provisioned a stack. That is a warning and a pointer, never a failure.
# ---------------------------------------------------------------------------
# A subshell: `dev-aws-common.sh`'s `die` exits, and `set -e` here would take
# the whole session hook down with it. Its `log` output goes to stderr, so what
# is captured is exactly the three values.
#
# Three, not four: the catalog table used to be read here to pin into
# `studio/.env`, and the `dev` profile carries it now. `load_dev_stack_outputs`
# still refuses a state missing any of the four, so nothing is unchecked by
# dropping it — it is simply not this script's to write any more.
if dev_stack="$(
  # shellcheck source=dev-aws-common.sh
  source "$STUDIO_DIR/scripts/dev-aws-common.sh"
  load_machine_id false
  load_aws_identity
  load_dev_stack_outputs
  printf '%s\t%s\t%s\n' "$DEV_POOL_ID" "$DEV_CLIENT_ID" "$DEV_BUCKET"
)" 2>/dev/null; then
  IFS=$'\t' read -r POOL_ID CLIENT_ID MEDIA_BUCKET <<<"$dev_stack"

  # The app. VITE_API_URL stays on localhost: `dev-up.sh` runs the Flask API
  # locally against the same dev stack, which is the point of the setup.
  ENV_LOCAL="$STUDIO_DIR/frontend/.env.local"
  cat > "$ENV_LOCAL" <<EOF
# Generated by studio/scripts/dev-setup.sh from this machine's dev stack.
# Do not edit by hand — re-run the script instead. Git-ignored.
#
# These are the DEV Cognito pool and client. Local development does not sign in
# against production; see the note in dev-setup.sh.
VITE_API_URL=http://localhost:8000
VITE_COGNITO_USER_POOL_ID=$POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
EOF
  log "wrote frontend/.env.local (dev Cognito pool $POOL_ID)"

  # The pipeline. Only the bucket and table are derived; REPLICATE_API_TOKEN is
  # a secret that lives nowhere but this file, so an existing one is never
  # overwritten.
  # Spelled out rather than taken from `dev-aws-common.sh`: that file is sourced
  # in the subshell above, so nothing it sets survives out here.
  STUDIO_DEV_ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/andreas-services/studio/dev.env"

  if [ ! -f "$STUDIO_DIR/.env" ]; then
    cp "$STUDIO_DIR/.env.example" "$STUDIO_DIR/.env"
    warn "created studio/.env from the example."
    warn "  Put REPLICATE_API_TOKEN in $STUDIO_DEV_ENV_FILE, not in that file."
  fi
  # A token inside the working tree is one `git add -f`, one copied directory
  # or one backup tool away from leaving the machine, and `.gitignore` stops
  # none of those. The config dir already holds this machine's dev pool
  # password for exactly that reason; the token predates the decision.
  #
  # Named rather than moved. The file is the developer's, and a setup script
  # that silently relocates a credential is a setup script nobody can predict —
  # the same reasoning as the prod-bucket pin below. `env_value` reads the
  # config dir FIRST, so copying the line across is enough and deleting the old
  # one is tidiness rather than a step.
  #
  # The example's own placeholder starts `r8_` too, so it is excluded by name:
  # a checkout that has copied the template and filled in nothing has no secret
  # to move, and warning about it would train the warning to be ignored.
  if grep -q "^REPLICATE_API_TOKEN=r8_" "$STUDIO_DIR/.env" &&
    ! grep -q "^REPLICATE_API_TOKEN=r8_your_token_here$" "$STUDIO_DIR/.env"; then
    warn "studio/.env holds a REPLICATE_API_TOKEN — a secret inside the repo."
    warn "  Move it to $STUDIO_DEV_ENV_FILE (read first, so the move takes effect at once)."
  fi
  # A .env written before the bucket rename pins XHARNESS_S3_BUCKET, which
  # nothing reads any more. Say so rather than leaving a line that looks like
  # configuration and is not.
  if grep -q "^XHARNESS_S3_" "$STUDIO_DIR/.env"; then
    warn "studio/.env still sets XHARNESS_S3_* — dead since the bucket rename."
    warn "  The variables are STUDIO_S3_* now. Delete the old lines."
  fi
  # Every other variable that has stopped being read, named individually.
  #
  # **Silence is the failure mode this exists to avoid**, and it is the same one
  # the XHARNESS_S3_* rename was designed around: a pinned line looks like
  # configuration, so a person reasons from it, and it has no effect. The
  # variables below were removed by the catalog programme rather than renamed,
  # so there is no successor name to point at — only a line to delete. Keep this
  # list appended to whenever a variable retires; the cost of an extra entry is
  # one grep per session and the cost of a missing one is a wrong diagnosis.
  #
  # STUDIO_S3_PREFIX used to need a message of its own, because "nothing reads
  # it" would have been a lie — the layout migrator did, and only it. That
  # command is deleted, no reader is left, and it joins the list. The WARNING
  # is not what retired; a stale pin in someone's .env is exactly as silent as
  # it ever was, and this is what breaks the silence.
  for dead in STUDIO_S3_PREFIX STUDIO_S3_MEDIA_PREFIX STUDIO_MAX_WALK_OBJECTS; do
    if grep -q "^${dead}=" "$STUDIO_DIR/.env"; then
      warn "studio/.env sets ${dead} — retired, and read by nothing. Delete the line."
    fi
  done
  # -------------------------------------------------------------------------
  # 3a. The `dev` PROFILE, which replaces pinning the stack into studio/.env.
  #
  #     This block used to append STUDIO_S3_BUCKET and STUDIO_CATALOG_TABLE to
  #     that file. Two problems with it, and the second is why it is gone.
  #
  #     A pin is per-CHECKOUT and the stack is per-MACHINE, so a second worktree
  #     had no pins at all and a maintenance command run there addressed
  #     whatever the shell happened to hold. And a pin covers two of the five
  #     values that select a stack — the other three (the API URL and both
  #     Cognito ids) were only ever exported by `dev-up.sh`, into its own shell.
  #     So a `.env` and a shell could name different environments, and
  #     `catalog gc` read the `.env` half. Nothing printed either.
  #
  #     `studio profile sync dev` writes all five into
  #     `~/.config/andreas-services/studio/config`, beside the machine id they
  #     belong to. `studio profile show` prints what is in force.
  #
  #     Through the CLI rather than written from here on purpose: one writer for
  #     that file, and it refuses to save a profile missing any of the five
  #     rather than leaving one that names two stacks at once.
  # -------------------------------------------------------------------------
  if uv run --project "$PIPELINE" studio profile sync dev >/dev/null 2>&1; then
    log "synced the dev profile ($MEDIA_BUCKET)"
  else
    warn "could not sync the dev profile. Run it directly to see why:"
    warn "  uv run --project $PIPELINE studio profile sync dev"
  fi

  # A .env pinned to the PROD bucket predates #287. It still wins whenever no
  # profile is selected, so it still points ordinary commands at production —
  # named loudly rather than rewritten, because the file is the developer's and
  # silently repointing where their commands write is worse than telling them.
  if grep -qE "^STUDIO_S3_BUCKET=.*prod" "$STUDIO_DIR/.env"; then
    warn "studio/.env pins a PROD bucket: $(grep -E '^STUDIO_S3_BUCKET=' "$STUDIO_DIR/.env")"
    warn "  That line beats the dev profile whenever --profile is not given."
    warn "  Delete it — the profile carries the bucket now — or reach prod"
    warn "  deliberately with: studio --profile prod <command>"
  fi
  # Both stack pins are now the profile's job, so a line for either is one more
  # place the answer can come from. Inert while it agrees with the profile and
  # invisible when it does not, which is the shape of every other entry in the
  # dead-variable list above.
  for pinned in STUDIO_S3_BUCKET STUDIO_CATALOG_TABLE; do
    if grep -q "^${pinned}=" "$STUDIO_DIR/.env"; then
      warn "studio/.env pins ${pinned} — the dev profile carries it now."
      warn "  Delete the line; check with: studio profile show"
    fi
  done
  # -------------------------------------------------------------------------
  # 3b. Push the shared material out to the bucket.
  #
  #     Shared material is what belongs to no character and no project, has no
  #     catalog node, and therefore cannot be created through the API: the pose
  #     plates under `config/`, and `phrasebook/wording.yaml`. Both are put in
  #     the bucket directly, by `dev-shared-material.sh` — which `dev-aws-seed.sh`
  #     also sources, so the rules live in one place.
  #
  #     The plates are a SYNC: studio/config/ is the source of truth and S3 holds
  #     a copy, because a model may only be handed a presigned URL of an S3
  #     object, never bytes from disk. So they have to exist in the bucket before
  #     `studio character shoot` can use them.
  #
  #     The phrasebook is a COPY-IF-ABSENT, and the asymmetry is deliberate: the
  #     bucket's copy is the live document the moment anyone runs
  #     `studio phrasebook add`, so syncing the repo copy over it would delete
  #     their entries. Putting the first one there is all this does — and it is
  #     what `add` needs, because `PATCH /api/text` overwrites and never invents
  #     (#425).
  # -------------------------------------------------------------------------
  # shellcheck source=dev-shared-material.sh
  source "$STUDIO_DIR/scripts/dev-shared-material.sh"
  if [ -n "$MEDIA_BUCKET" ]; then
    if push_pose_plates "$STUDIO_DIR" "$MEDIA_BUCKET"; then
      log "pose plates are in the library (or you are not signed in yet)"
    else
      warn "could not push studio/config/ into the library — a reference shoot"
      warn "  will report missing plates. Try: studio login && studio config sync --apply"
    fi
  fi
else
  # Three distinct causes, one message, and that is deliberate: the remedy for
  # all of them starts with the same command, and a script running from a
  # session hook should not make a person diagnose which of the three it hit.
  warn "no dev stack readable — skipping env files."
  warn "  Either this machine has no working AWS credentials, or it has never"
  warn "  provisioned a stack. Check the first with:"
  warn "    aws sts get-caller-identity"
  warn "  then provision with:"
  warn "    ./studio/scripts/dev-aws-setup.sh"
  warn "  Nothing here points at production any more (#287)."
fi

# ---------------------------------------------------------------------------
# 4. Install the frontend's node_modules.
#
#    Nothing else does, and that is what a fresh checkout trips over. `dev-up.sh`
#    goes straight to `npm run dev`, CI does its own `npm ci`, and a laptop that
#    ran `npm install` once by hand looks fine forever — so the gap is invisible
#    on exactly the machines it does not affect. On a clean clone or a cloud
#    agent's worktree the first symptom is `tsc: not found`, because `tsc` is a
#    local devDependency and `node_modules/.bin` is where it lives. So is eslint,
#    and so is vite. There is no global TypeScript to fall back on and there
#    should not be one.
#
#    `@ansavva/design-system` comes from GitHub Packages, which has no anonymous
#    read, so the install needs a `read:packages` token in NODE_AUTH_TOKEN — the
#    committed `frontend/.npmrc` already reads it from there. The monorepo
#    already has one script that resolves such a token from a PAT or from `gh`;
#    studio simply never called it. Use it rather than adding a second mechanism.
#
#    Never fatal: the SessionStart hook runs this file, the pipeline half needs
#    none of it, and a session must not fail to start over a frontend the task
#    may never touch. A warning that names the fix is the useful outcome.
# ---------------------------------------------------------------------------
FRONTEND="$STUDIO_DIR/frontend"
AUTH_SCRIPT="$STUDIO_DIR/../scripts/github-packages-auth.sh"

# Up to date when node_modules' own lockfile is at least as new as the repo's.
# npm writes node_modules/.package-lock.json on every install, so this is the
# cheap check that makes running on every session free.
frontend_is_current() {
  [ -d "$FRONTEND/node_modules" ] &&
    [ -f "$FRONTEND/node_modules/.package-lock.json" ] &&
    [ ! "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]
}

if ! command -v npm >/dev/null 2>&1; then
  warn "npm is missing — skipping frontend deps. The shared installer has it:"
  warn "  ./scripts/dev-setup.sh (repo root)"
elif frontend_is_current; then
  log "frontend node_modules already current"
else
  # `--check` FIRST, and never a bare `--export`. In its ensure and export modes
  # that script falls through to `gh auth refresh --scopes read:packages`, which
  # is INTERACTIVE — it prompts and waits for a browser flow. The SessionStart
  # hook runs this file, so calling it that way hangs the start of every session
  # on any machine without a token. Measured, not feared: it blocked for seven
  # minutes here before being killed.
  #
  # `--check` only inspects env vars, needs no input and exits non-zero quickly.
  # Once it passes, `--export` resolves from that same env var and returns
  # without ever reaching gh. The interactive path stays available to a person,
  # which is where a prompt belongs — it is the remedy printed below.
  # A developer machine usually already has the scope on its `gh` login, but
  # `--check` reads only env vars and would miss it, warning at someone who is
  # perfectly well authenticated. So hand gh's existing token to `--check` as one
  # of the variables it does read. Reading a token is not refreshing one: this
  # never prompts, and `--check` still verifies the token can actually read the
  # package rather than trusting it.
  if [ -z "${GITHUB_PACKAGES_TOKEN:-}" ] && command -v gh >/dev/null 2>&1; then
    gh_existing="$(gh auth token 2>/dev/null || true)"
    [ -n "$gh_existing" ] && export GITHUB_PACKAGES_TOKEN="$gh_existing"
    unset gh_existing
  fi

  if [ -x "$AUTH_SCRIPT" ] && "$AUTH_SCRIPT" --check >/dev/null 2>&1; then
    eval "$("$AUTH_SCRIPT" --export 2>/dev/null || true)"
    log "GitHub Packages read access confirmed"
  fi

  if [ -z "${NODE_AUTH_TOKEN:-}" ]; then
    warn "no read:packages token, so @ansavva/design-system cannot be installed."
    warn "  Fix it with either of these, then re-run this script:"
    warn "    ./scripts/github-packages-auth.sh                      # interactive, via gh"
    warn "    export GITHUB_PACKAGES_TOKEN=<PAT with read:packages>  # CI / cloud agent"
    warn "  Until then 'npm run typecheck', 'npm run lint' and 'npm run dev' all"
    warn "  fail with a missing binary — tsc, eslint and vite are all local."
  else
    log "installing frontend node_modules (npm ci)..."
    # `npm ci` rather than `install`: it is what CI runs, and it refuses to
    # silently rewrite package-lock.json underneath a dev environment.
    if (cd "$FRONTEND" && npm ci --no-audit --no-fund >/dev/null 2>&1); then
      log "frontend node_modules installed"
    else
      warn "npm ci failed in studio/frontend. Re-run it directly to see why:"
      warn "  cd studio/frontend && npm ci"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 5. Report optional external tools (never fatal — platform dependent).
# ---------------------------------------------------------------------------
if command -v ffmpeg >/dev/null 2>&1; then
  log "optional tool found: ffmpeg"
else
  warn "optional tool missing: ffmpeg — used to verify rendered frames and to"
  warn "  stitch scenes and movies (brew install ffmpeg). The scene/movie"
  warn "  scripts vendor imageio-ffmpeg, so this is only needed for hand checks."
fi

log "done."
