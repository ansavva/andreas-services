#!/usr/bin/env bash
#
# Shared developer / CI toolchain bootstrap for the andreas-services monorepo.
#
# Installs the cross-cutting tools every service needs (Terraform, AWS CLI,
# Node.js, jq, zip). Service-specific runtimes live in per-service scripts,
# e.g. humbugg/scripts/dev-setup.sh (.NET SDK).
#
# Supported targets:
#   - macOS (developer machines) -> Homebrew
#   - Ubuntu (this cloud sandbox / CI) -> apt + official vendor installers
#
# The script is IDEMPOTENT: every tool is checked with `command -v` (and a
# version floor where it matters) before anything is installed, so re-running
# it is a no-op once the toolchain is present.
#
# Usage:
#   ./scripts/dev-setup.sh            # install everything missing
#   ./scripts/dev-setup.sh --check    # report status only, install nothing
#
set -euo pipefail

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

# --- versions we pin/floor -------------------------------------------------
TERRAFORM_VERSION="1.9.8"   # matches CI; HashiCorp releases are per-version zips
NODE_MAJOR_MIN=20           # repo builds on Node 20+; sandbox ships 22

# --- pretty logging --------------------------------------------------------
log()  { printf '\033[1;34m[dev-setup]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
skip() { printf '\033[1;36m[skip]\033[0m %s already present: %s\n' "$1" "$2"; }

OS="$(uname -s)"
have() { command -v "$1" >/dev/null 2>&1; }

# SUDO is empty when we are already root (the sandbox runs as root).
if [[ "$(id -u)" -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

APT_UPDATED=0
apt_update_once() {
  [[ "$APT_UPDATED" -eq 1 ]] && return 0
  $SUDO apt-get update -y
  APT_UPDATED=1
}
apt_install() { apt_update_once; $SUDO apt-get install -y "$@"; }

# ---------------------------------------------------------------------------
# macOS (Homebrew)
# ---------------------------------------------------------------------------
ensure_brew() {
  if have brew; then return 0; fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "Homebrew is MISSING (required on macOS)"; return 1; fi
  log "installing Homebrew ..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
}

brew_ensure() {
  # brew_ensure <cli-name> <formula>
  local cli="$1" formula="$2"
  if have "$cli"; then skip "$cli" "$(command -v "$cli")"; return 0; fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "$cli is MISSING (would: brew install $formula)"; return 0; fi
  log "installing $formula ..."
  brew install "$formula"
}

# ---------------------------------------------------------------------------
# Ubuntu (apt + vendor installers)
# ---------------------------------------------------------------------------
install_terraform_linux() {
  if have terraform; then skip terraform "$(command -v terraform)"; return 0; fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "terraform is MISSING (would install $TERRAFORM_VERSION)"; return 0; fi
  log "installing terraform $TERRAFORM_VERSION ..."
  local tmp arch; tmp="$(mktemp -d)"; arch="$(uname -m)"
  case "$arch" in
    x86_64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
  esac
  curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${arch}.zip" -o "$tmp/tf.zip"
  ( cd "$tmp" && unzip -o -q tf.zip )
  $SUDO install -m 0755 "$tmp/terraform" /usr/local/bin/terraform
  rm -rf "$tmp"
  ok "terraform $(terraform version | head -1)"
}

install_node_linux() {
  if have node; then
    local major; major="$(node -p 'process.versions.node.split(".")[0]')"
    if [[ "$major" -ge "$NODE_MAJOR_MIN" ]]; then skip node "$(node --version)"; return 0; fi
    warn "node $(node --version) is below required v${NODE_MAJOR_MIN}; upgrading"
  fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "node >= v${NODE_MAJOR_MIN} is MISSING (would install)"; return 0; fi
  log "installing Node.js ${NODE_MAJOR_MIN}.x ..."
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR_MIN}.x" | $SUDO -E bash -
  apt_install nodejs
}

install_awscli_linux() {
  if have aws; then skip aws "$(command -v aws)"; return 0; fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "aws is MISSING (would install AWS CLI v2)"; return 0; fi
  log "installing AWS CLI v2 ..."
  local tmp; tmp="$(mktemp -d)"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o "$tmp/awscliv2.zip"
  ( cd "$tmp" && unzip -o -q awscliv2.zip && $SUDO ./aws/install --update )
  rm -rf "$tmp"
  ok "aws $(aws --version)"
}

apt_ensure() {
  # apt_ensure <cli-name> <package>
  local cli="$1" pkg="$2"
  if have "$cli"; then skip "$cli" "$(command -v "$cli")"; return 0; fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "$cli is MISSING (would: apt-get install $pkg)"; return 0; fi
  log "installing $pkg ..."
  apt_install "$pkg"
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
log "OS detected: $OS  (check-only: $CHECK_ONLY)"

case "$OS" in
  Darwin)
    ensure_brew || true
    brew_ensure terraform terraform
    brew_ensure aws awscli
    brew_ensure node node
    brew_ensure jq jq
    brew_ensure zip zip
    if have docker; then skip docker "$(command -v docker)"; else
      warn "docker not found — install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    fi
    ;;

  Linux)
    install_terraform_linux
    install_node_linux
    install_awscli_linux
    apt_ensure jq jq
    apt_ensure zip zip
    if have docker; then skip docker "$(command -v docker)"; else
      warn "docker not found — see https://docs.docker.com/engine/install/ubuntu/"
    fi
    ;;

  *)
    warn "Unsupported OS '$OS'. This repo supports macOS (developers) and Ubuntu (CI/sandbox)."
    exit 1
    ;;
esac

log "shared toolchain ready. For service runtimes run the per-service script, e.g.:"
log "    ./humbugg/scripts/dev-setup.sh   # .NET SDK for the Humbugg backend"
ok "done."
