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
# 3. Write the env files, from the REAL prod values.
#
#    LOCAL POINTS AT PROD, DELIBERATELY. There is no dev environment for studio
#    and there is not going to be one: the whole service is a view onto one
#    media bucket, and a second bucket with nothing in it would exercise none of
#    the behaviour that matters. So the CLI and the local app both read and
#    write the live bucket and authenticate against the live Cognito pool.
#
#    That is a real trade, taken on purpose. What makes it survivable:
#    versioning is on, the API role cannot delete a version, and every
#    destructive command confirms. What it means in practice: a `delete` you run
#    locally is a delete in production. Read `docs/PIPELINE.md` before running
#    one.
#
#    The values come from SSM, written by the deploy workflow from Terraform's
#    outputs — so they cannot drift from what is actually deployed.
# ---------------------------------------------------------------------------
ssm() { aws ssm get-parameter --name "$1" --query Parameter.Value --output text 2>/dev/null; }

if aws sts get-caller-identity >/dev/null 2>&1; then
  POOL_ID="$(ssm /studio/prod/cognito-user-pool-id)"
  CLIENT_ID="$(ssm /studio/prod/cognito-client-id)"
  MEDIA_BUCKET="$(ssm /studio/prod/media-bucket)"

  # The app. VITE_API_URL stays on localhost: `dev-up.sh` runs the Flask API
  # locally against the same prod bucket, which is the point of the setup.
  ENV_LOCAL="$STUDIO_DIR/frontend/.env.local"
  if [ -n "$POOL_ID" ] && [ -n "$CLIENT_ID" ]; then
    cat > "$ENV_LOCAL" <<EOF
# Generated by studio/scripts/dev-setup.sh from SSM. Do not edit by hand —
# re-run the script instead. Git-ignored.
#
# These are the PROD Cognito pool and client: local development signs in
# against the real user pool. See the note in dev-setup.sh.
VITE_API_URL=http://localhost:8000
VITE_AWS_REGION=${AWS_REGION:-us-east-1}
VITE_COGNITO_USER_POOL_ID=$POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
EOF
    log "wrote frontend/.env.local (prod Cognito pool $POOL_ID)"
  else
    warn "could not read the Cognito values from SSM — the app will show"
    warn "  'Auth is not configured'. Has studio been deployed?"
  fi

  # The pipeline. Only the bucket is derived; REPLICATE_API_TOKEN is a secret
  # that lives nowhere but this file, so an existing one is never overwritten.
  if [ ! -f "$STUDIO_DIR/.env" ]; then
    cp "$STUDIO_DIR/.env.example" "$STUDIO_DIR/.env"
    warn "created studio/.env from the example — add your REPLICATE_API_TOKEN."
  fi
  # A .env written before the bucket rename pins XHARNESS_S3_BUCKET, which
  # nothing reads any more. Say so rather than leaving a line that looks like
  # configuration and is not — it names the archive bucket, so believing it
  # means believing writes are going somewhere they are not.
  if grep -q "^XHARNESS_S3_" "$STUDIO_DIR/.env"; then
    warn "studio/.env still sets XHARNESS_S3_* — dead since the bucket rename."
    warn "  The variables are STUDIO_S3_* now. Delete the old lines."
  fi
  if [ -n "$MEDIA_BUCKET" ] && ! grep -q "^STUDIO_S3_BUCKET=" "$STUDIO_DIR/.env"; then
    printf '\n# The media bucket, read from SSM by dev-setup.sh.\nSTUDIO_S3_BUCKET=%s\n' \
      "$MEDIA_BUCKET" >> "$STUDIO_DIR/.env"
    log "pinned STUDIO_S3_BUCKET=$MEDIA_BUCKET in studio/.env"
  fi
  # -------------------------------------------------------------------------
  # 3b. Copy the shared config assets out to the bucket.
  #
  #     studio/config/ is the SOURCE OF TRUTH for the pose plates a reference
  #     shoot binds; S3 holds a copy because a model may only be handed a
  #     presigned URL of an S3 object, never bytes from disk. So the plates have
  #     to exist in the bucket before `studio character shoot` can use them.
  #
  #     --size-only because S3 mtimes always differ from local ones, which would
  #     re-upload every plate on every session — and this script runs from the
  #     SessionStart hook each time.
  #
  #     NEVER --delete. This writes to the prod bucket (studio has one
  #     environment, deliberately), and --delete would remove anything under
  #     config/ that is not in this checkout.
  # -------------------------------------------------------------------------
  if [ -n "$MEDIA_BUCKET" ] && [ -d "$STUDIO_DIR/config" ]; then
    if aws s3 sync "$STUDIO_DIR/config/" "s3://$MEDIA_BUCKET/config/" --size-only \
         --only-show-errors; then
      log "synced studio/config/ -> s3://$MEDIA_BUCKET/config/"
    else
      warn "could not sync studio/config/ to s3://$MEDIA_BUCKET/config/ — the pose"
      warn "  plates a reference shoot needs may be missing from the bucket."
    fi
  fi
else
  warn "not signed in to AWS — skipping env files. Run 'aws login', then re-run"
  warn "  studio/scripts/dev-setup.sh to write them."
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
