#!/usr/bin/env bash
#
# dev-setup.sh — install the prerequisites the studio generation skills need.
#
# This is mainly for the LOCAL half of studio: the skills under
# studio/.claude/skills/ that run inside Claude on your machine.
#
# It is not *only* that half, and the difference matters. CI builds the deployed
# half, but a person or an agent working on it locally still needs the parts CI
# gets for free: the per-machine dev.env (step 3) and frontend/node_modules (step 4).
#
# The only hard requirement is `uv`. The pipeline itself is one package
# (studio/pipeline) with one dependency set, exposing one command: `studio`.
# This installs uv if missing, syncs that package, and puts its console script
# on PATH for the session.
#
# Safe to run repeatedly: every step checks before it acts (idempotent) and runs
# non-interactively. The repo's SessionStart hook calls it on every session.

set -euo pipefail

# For DEV_ENV_FILE and the env-file helpers only; its `die` is never reached
# from here, and the log functions below replace its.
# shellcheck source=dev-aws-common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dev-aws-common.sh"

log() { printf '\033[36m[studio-setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[studio-setup]\033[0m %s\n' "$*"; }

# Resolve studio/ so this works no matter where it is invoked from. Note this is
# studio/, not the repo root: the skills resolve their own paths relative to it
# (studio/infra/README.md), so studio/ is what they treat as root.
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
#    One package with one dependency set, exposing one command — so setup is a
#    single sync, and the skills say `studio runs list` rather than naming a file.
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
# 3. Write ~/.config/andreas-services/studio/dev.env, from THIS MACHINE'S DEV STACK.
#
#    One file for everything local — the frontend's VITE_* values, the dev
#    account, the provider tokens — outside the repo, so it survives `git
#    clean` and a fresh worktree, and holds secrets where no `git add -f`
#    reaches them. `dev-up.sh` exports the VITE_* prefix before Vite starts
#    and reads the tokens for the API; the pipeline reads it through
#    `env_value`. `studio/.env` and `frontend/.env.local`, which it replaced,
#    are imported once and deleted.
#
#    Nothing here reads `/studio/prod/*`: the values come from this machine's
#    dev stack, which `dev-aws-seed.sh` seeds from a published fixture so it
#    exercises the behaviour that matters without touching prod.
#
#    Running the CLI against production is `studio --profile prod <command>`,
#    deliberately not a flag on this script: this one sets up the LOCAL half.
#    Step 3a below syncs the `dev` profile; `studio profile sync prod` writes
#    the other.
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
# is captured is exactly the four values.
#
# Four of the five: the `dev` profile carries the catalog table.
# `load_dev_stack_outputs` refuses a state missing any of the five.
if dev_stack="$(
  # shellcheck source=dev-aws-common.sh
  source "$STUDIO_DIR/scripts/dev-aws-common.sh"
  load_machine_id false
  load_aws_identity
  load_dev_stack_outputs
  printf '%s\t%s\t%s\t%s\n' "$DEV_POOL_ID" "$DEV_CLIENT_ID" "$DEV_AUTH_DOMAIN" "$DEV_BUCKET"
)" 2>/dev/null; then
  IFS=$'\t' read -r POOL_ID CLIENT_ID AUTH_DOMAIN MEDIA_BUCKET <<<"$dev_stack"

  # Rendered whole, in a fixed layout, rather than upserted key by key: upserts
  # append in write order and the result reads like a log. Generated keys are
  # written fresh from the stack; hand-set keys are read back from the current
  # file into their slot; anything unrecognised is carried over at the end.
  previous="$(mktemp)"
  chmod 600 "$previous"
  cat "$DEV_ENV_FILE" > "$previous" 2>/dev/null || true
  # The two files this replaced. Every key the new file lacks is imported —
  # the Replicate token was only ever typed into studio/.env by hand — and the
  # old file removed, because an ignored file nothing reads is the confusion
  # this consolidation exists to end. The stack pins are NOT imported: the
  # `dev` profile carries the bucket and table now (3a), and a pin here would
  # be one more place the answer could come from — and one of them named the
  # PROD bucket for a year. Retired variables are dropped for the same reason.
  import_legacy_env() {
    local legacy="$1" line key
    [ -f "$legacy" ] || return 0
    while IFS= read -r line; do
      [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
      key="${BASH_REMATCH[1]}"
      case "$key" in
        STUDIO_S3_BUCKET|STUDIO_CATALOG_TABLE|XHARNESS_S3_BUCKET|XHARNESS_S3_PREFIX|\
        STUDIO_S3_PREFIX|STUDIO_S3_MEDIA_PREFIX|STUDIO_MAX_WALK_OBJECTS) continue ;;
        REPLICATE_API_TOKEN) [ "${BASH_REMATCH[2]}" = "r8_your_token_here" ] && continue ;;
      esac
      ensure_env "$previous" "$key" "${BASH_REMATCH[2]}"
    done < "$legacy"
    rm -f "$legacy"
    log "imported ${legacy#"$STUDIO_DIR/"} into $DEV_ENV_FILE and removed it"
  }
  import_legacy_env "$STUDIO_DIR/.env"
  import_legacy_env "$STUDIO_DIR/frontend/.env.local"
  written=""
  rendered="$(mktemp)"
  chmod 600 "$rendered"
  exec 3>"$rendered"
  line() { printf '%s\n' "$*" >&3; }
  gen() { line "$1=$2"; written="$written $1"; }
  keep() {
    local key="$1" default="${2-}"
    if grep -Eq "^${key}=" "$previous"; then line "$key=$(read_env "$previous" "$key")"
    elif [ -n "$default" ]; then line "$key=$default"
    else line "#$key="; fi
    written="$written $key"
  }
  line "# Studio local development — the one file. studio/dev.env.sample documents it."
  line "# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ) by dev-setup.sh from dev pool $POOL_ID."
  line "# Which STACK a command targets is not here: that is a profile (studio profile show)."
  line ""
  line "# ---- generated (rewritten on every dev-setup.sh run; do not hand-edit) --------"
  line ""
  line "# Frontend (Vite inlines VITE_*; dev-up.sh exports only this prefix). The DEV"
  line "# Cognito pool and its Managed Login host — local development never signs in"
  line "# against production. VITE_API_URL stays on localhost: dev-up.sh runs the API here."
  gen VITE_API_URL "http://localhost:8000"
  gen VITE_COGNITO_USER_POOL_ID "$POOL_ID"
  gen VITE_COGNITO_CLIENT_ID "$CLIENT_ID"
  gen VITE_COGNITO_DOMAIN "$AUTH_DOMAIN"
  line ""
  line "# ---- yours (kept as-is across reruns) -----------------------------------------"
  line ""
  line "# Dev test account — dev-user.sh writes both; a reserved .test address belongs here."
  keep STUDIO_DEV_USER_EMAIL
  keep STUDIO_DEV_USER_PASSWORD
  line ""
  line "# Provider tokens for the LOCAL pipeline; the deployed half never sees them."
  line "# REPLICATE_API_TOKEN is required for every generation (https://replicate.com/account/api-tokens)."
  line "# Assets are never uploaded to Replicate — only presigned S3 URLs reach a model."
  keep REPLICATE_API_TOKEN
  leftover="$(awk -F= -v written=" $written " '
    /^[A-Za-z_][A-Za-z0-9_]*=/ && index(written, " " $1 " ") == 0 { print }
  ' "$previous" | sort)"
  if [ -n "$leftover" ]; then
    line ""
    line "# ---- not managed by any script; carried over as found ------------------------"
    line "$leftover"
  fi
  exec 3>&-
  rm -f "$previous"
  mkdir -p "$(dirname "$DEV_ENV_FILE")"
  chmod 700 "$(dirname "$DEV_ENV_FILE")"
  mv "$rendered" "$DEV_ENV_FILE"
  log "wrote $DEV_ENV_FILE (dev Cognito pool $POOL_ID, sign-in at $AUTH_DOMAIN)"
  if [ -z "$(read_env "$DEV_ENV_FILE" REPLICATE_API_TOKEN)" ]; then
    warn "REPLICATE_API_TOKEN is not set in $DEV_ENV_FILE — no generation can run until it is."
  fi
  # -------------------------------------------------------------------------
  # 3a. The `dev` PROFILE, which carries WHICH STACK a command targets.
  #
  #     Not a key in dev.env, on purpose. A pin there would cover two of the
  #     five values that select a stack — the other three (the API URL and
  #     both Cognito ids) are exported by `dev-up.sh`, into its own shell. So a
  #     file and a shell could name different environments, and `catalog gc`
  #     read the file's half. Nothing printed either. (`studio/.env` did
  #     exactly this for a year, once with the PROD bucket.)
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

  # -------------------------------------------------------------------------
  # 3b. Push the shared material out to the bucket.
  #
  #     Shared material is what belongs to no character and no project: the pose
  #     angle images under `config/`. They go in through `dev-shared-material.sh` —
  #     which `dev-aws-seed.sh` also sources, so the rules live in one place.
  #
  #     The angle images are a SYNC: studio/config/ is the source of truth and the
  #     library holds a copy, because a model may only be handed a presigned URL
  #     of a stored object, never bytes from disk. So they have to exist in the
  #     bucket before `studio character turnaround` can use them. They are ordinary
  #     nodes, so the push goes through `studio config sync` rather than writing
  #     objects directly.
  #
  #     The phrasebook is `TERM#` rows, not a document, so there is nothing
  #     else to push.
  # -------------------------------------------------------------------------
  # shellcheck source=dev-shared-material.sh
  source "$STUDIO_DIR/scripts/dev-shared-material.sh"
  if [ -n "$MEDIA_BUCKET" ]; then
    if push_pose_plates "$STUDIO_DIR" "$MEDIA_BUCKET"; then
      log "angle images are in the library (or you are not signed in yet)"
    else
      warn "could not push studio/config/ into the library — a turnaround"
      warn "  will report missing angle images. Try: studio login && studio config sync --apply"
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
  warn "  Nothing here points at production."
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
  warn "optional tool missing: ffmpeg — for hand checks only (brew install ffmpeg)."
  warn "  studio does not need it: stitching a scene, pulling a frame and building"
  warn "  a contact sheet are render jobs done by the service, and the local"
  warn "  consumer dev-up.sh runs uses the backend's own imageio-ffmpeg."
fi

log "done."
