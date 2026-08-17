#!/usr/bin/env bash
#
# dev-setup.sh — install the prerequisites the studio generation skills need.
#
# This is for the LOCAL half of studio: the skills under studio/.claude/skills/
# that run inside Claude on your machine. The deployed half (backend/, frontend/)
# is built by CI and needs nothing from here.
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
# 3. Report optional external tools (never fatal — platform dependent).
# ---------------------------------------------------------------------------
if command -v ffmpeg >/dev/null 2>&1; then
  log "optional tool found: ffmpeg"
else
  warn "optional tool missing: ffmpeg — used to verify rendered frames and to"
  warn "  stitch scenes and movies (brew install ffmpeg). The scene/movie"
  warn "  scripts vendor imageio-ffmpeg, so this is only needed for hand checks."
fi

log "done."
