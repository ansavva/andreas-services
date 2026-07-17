#!/usr/bin/env bash
#
# Humbugg service toolchain bootstrap (.NET SDK for the ASP.NET Core backend).
#
# Humbugg's backend is ASP.NET Core 10 (C# 14); global.json pins the SDK to
# 10.0.302 with rollForward=latestFeature. This installs a compatible .NET SDK.
# Run scripts/dev-setup.sh first for the shared tools (Node, Terraform, etc.).
#
# Supported targets:
#   - macOS  -> Homebrew (`brew install dotnet-sdk`)
#   - Ubuntu -> Microsoft's dotnet-install.sh (channel 10.0), no apt pinning
#
# IDEMPOTENT: if a .NET SDK satisfying the pinned feature band is already on
# PATH, the script does nothing.
#
# Usage:
#   ./humbugg/scripts/dev-setup.sh            # install if missing
#   ./humbugg/scripts/dev-setup.sh --check    # report only
#
set -euo pipefail

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

DOTNET_CHANNEL="10.0"
DOTNET_MAJOR_MINOR="10.0"

log()  { printf '\033[1;34m[humbugg-setup]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }

OS="$(uname -s)"
have() { command -v "$1" >/dev/null 2>&1; }
if [[ "$(id -u)" -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

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
  warn ".NET SDK ${DOTNET_MAJOR_MINOR}.x is MISSING (would install channel ${DOTNET_CHANNEL})"
  exit 0
fi

case "$OS" in
  Darwin)
    if ! have brew; then
      warn "Homebrew required. Run scripts/dev-setup.sh first (installs Homebrew)."
      exit 1
    fi
    log "installing .NET SDK via Homebrew ..."
    # dotnet-sdk tracks the latest SDK; global.json rollForward=latestFeature
    # accepts it as long as the major.minor band matches.
    brew install --cask dotnet-sdk || brew install dotnet-sdk
    ;;

  Linux)
    log "installing .NET SDK channel ${DOTNET_CHANNEL} via dotnet-install.sh ..."
    tmp="$(mktemp -d)"
    curl -fsSL https://dot.net/v1/dotnet-install.sh -o "$tmp/dotnet-install.sh"
    chmod +x "$tmp/dotnet-install.sh"
    # Install system-wide so subagents and CI share one SDK.
    export DOTNET_INSTALL_DIR="/usr/local/share/dotnet"
    $SUDO mkdir -p "$DOTNET_INSTALL_DIR"
    $SUDO "$tmp/dotnet-install.sh" --channel "$DOTNET_CHANNEL" --install-dir "$DOTNET_INSTALL_DIR"
    # Expose dotnet on PATH for future shells and the current one.
    if [[ ! -e /usr/local/bin/dotnet ]]; then
      $SUDO ln -sf "$DOTNET_INSTALL_DIR/dotnet" /usr/local/bin/dotnet
    fi
    export PATH="$DOTNET_INSTALL_DIR:$PATH"
    rm -rf "$tmp"
    ;;

  *)
    warn "Unsupported OS '$OS'."
    exit 1
    ;;
esac

if dotnet_ok; then
  ok ".NET SDK ready: $(dotnet --list-sdks | grep "^${DOTNET_MAJOR_MINOR}\." | head -1)"
else
  warn ".NET install completed but no ${DOTNET_MAJOR_MINOR}.x SDK detected on PATH. Check DOTNET_INSTALL_DIR / PATH."
  exit 1
fi
