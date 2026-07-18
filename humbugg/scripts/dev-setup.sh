#!/usr/bin/env bash
#
# Humbugg service toolchain bootstrap (.NET SDK for the ASP.NET Core backend).
#
# Humbugg's backend is ASP.NET Core 10 (C# 14); global.json pins the SDK to
# 10.0.302 with rollForward=latestFeature. Homebrew's `dotnet` formula currently
# ships exactly 10.0.302, so this installs it via brew on both platforms (matching
# scripts/dev-setup.sh). Run scripts/dev-setup.sh first for the shared tools and,
# on Linux, to bootstrap Homebrew itself.
#
# On Linux, Homebrew refuses to run as root, so brew is invoked as the non-root
# `ubuntu` user against /home/linuxbrew/.linuxbrew (see scripts/dev-setup.sh).
#
# IDEMPOTENT: if a .NET SDK satisfying the pinned major.minor band is already on
# PATH, the script does nothing.
#
# Usage:
#   ./humbugg/scripts/dev-setup.sh            # install if missing
#   ./humbugg/scripts/dev-setup.sh --check    # report only
#
set -euo pipefail

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

DOTNET_MAJOR_MINOR="10.0"

log()  { printf '\033[1;34m[humbugg-setup]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }

# `uname -s` is the kernel name: reliably "Darwin" on every macOS release (it
# does NOT track the macOS marketing version) and "Linux" on Linux. Match with a
# glob and treat anything else as unsupported rather than assuming Linux.
OS="$(uname -s)"
case "$OS" in
  Darwin*) PLATFORM="macos" ;;
  Linux*)  PLATFORM="linux" ;;
  *) printf 'Unsupported OS: %s (this repo supports macOS and Linux only).\n' "$OS" >&2; exit 1 ;;
esac
have() { command -v "$1" >/dev/null 2>&1; }
if [[ "$(id -u)" -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

LINUXBREW_PREFIX="/home/linuxbrew/.linuxbrew"
LINUX_BREW_USER="ubuntu"
BREW_ENV=(HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1)

# Make brew-installed tools visible on Linux even in a fresh shell.
[[ "$PLATFORM" == "linux" && -x "$LINUXBREW_PREFIX/bin/brew" ]] && eval "$("$LINUXBREW_PREFIX/bin/brew" shellenv)"

brew_run() {
  if [[ "$PLATFORM" == "macos" ]]; then
    env "${BREW_ENV[@]}" brew "$@"
  else
    $SUDO -u "$LINUX_BREW_USER" env "${BREW_ENV[@]}" "$LINUXBREW_PREFIX/bin/brew" "$@"
  fi
}

# Does an installed dotnet already provide a 10.0.x SDK?
dotnet_ok() {
  have dotnet || return 1
  dotnet --list-sdks 2>/dev/null | grep -q "^${DOTNET_MAJOR_MINOR}\."
}

if dotnet_ok; then
  ok ".NET SDK ${DOTNET_MAJOR_MINOR}.x already present: $(dotnet --list-sdks | grep "^${DOTNET_MAJOR_MINOR}\." | head -1)"
  exit 0
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  warn ".NET SDK ${DOTNET_MAJOR_MINOR}.x is MISSING (would: brew install dotnet)"
  exit 0
fi

if [[ "$PLATFORM" == "linux" && ! -x "$LINUXBREW_PREFIX/bin/brew" ]]; then
  warn "Homebrew not found. Run ./scripts/dev-setup.sh first (bootstraps Homebrew on Linux)."
  exit 1
fi
if [[ "$PLATFORM" == "macos" ]] && ! have brew; then
  warn "Homebrew not found. Run ./scripts/dev-setup.sh first."
  exit 1
fi

log "installing .NET SDK via Homebrew (brew dotnet == ${DOTNET_MAJOR_MINOR}.302) ..."
brew_run install dotnet

# Re-expose PATH in case brew was just used for the first time.
[[ "$PLATFORM" == "linux" && -x "$LINUXBREW_PREFIX/bin/brew" ]] && eval "$("$LINUXBREW_PREFIX/bin/brew" shellenv)"

if dotnet_ok; then
  ok ".NET SDK ready: $(dotnet --list-sdks | grep "^${DOTNET_MAJOR_MINOR}\." | head -1)"
else
  warn ".NET install completed but no ${DOTNET_MAJOR_MINOR}.x SDK detected on PATH."
  warn "Ensure the Homebrew prefix is on PATH: eval \"\$($LINUXBREW_PREFIX/bin/brew shellenv)\""
  exit 1
fi
