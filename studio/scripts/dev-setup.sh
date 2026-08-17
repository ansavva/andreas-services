#!/usr/bin/env bash
#
# dev-setup.sh — install the prerequisites the studio generation skills need.
#
# This is for the LOCAL half of studio: the skills under studio/.claude/skills/
# that run inside Claude on your machine. The deployed half (backend/, frontend/)
# is built by CI and needs nothing from here.
#
# The only hard requirement is `uv`: every skill script declares its own Python
# version and dependencies with PEP 723 inline metadata, so `uv run` builds and
# caches an isolated env per script — there is no shared venv or requirements.txt
# to install. This installs uv (if missing) and warms the dependency caches so
# the first real run is fast.
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
# 2. Pre-warm dependency caches for the entry-point scripts (best-effort).
#    `--help` exits 0 without doing any work, but forces uv to resolve and cache
#    each script's declared dependencies. Only entry points are listed — the
#    library modules they import share the same resolved env.
# ---------------------------------------------------------------------------
prewarm() {
  local name="$1" script="$2"
  if [ -f "$script" ]; then
    log "warming '$name' dependency cache..."
    uv run --script "$script" --help >/dev/null 2>&1 \
      || warn "could not pre-warm '$name' (will resolve on first use)"
  else
    warn "skipping '$name' — $script not found"
  fi
}

SKILLS="$STUDIO_DIR/.claude/skills"

prewarm studio        "$SKILLS/studio-core/scripts/studio.py"
prewarm runs          "$SKILLS/studio-s3/scripts/runs.py"
prewarm s3-convert    "$SKILLS/studio-s3/scripts/s3_convert.py"
prewarm build-prompt  "$SKILLS/studio-prompt/scripts/build_prompt.py"
prewarm character     "$SKILLS/studio-character/scripts/character.py"
prewarm curate        "$SKILLS/studio-character/scripts/curate.py"

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
