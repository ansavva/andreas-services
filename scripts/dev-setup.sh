#!/usr/bin/env bash
#
# Shared developer / CI toolchain bootstrap for the andreas-services monorepo.
#
# Installs the cross-cutting tools every service needs (Terraform, tflint, AWS
# CLI, Node.js, jq, zip) with Homebrew on BOTH macOS and Linux. Service-specific
# runtimes live in per-service scripts, e.g. humbugg/scripts/dev-setup.sh (.NET).
#
# Homebrew details:
#   - macOS (developer machines): brew runs as the normal user.
#   - Linux (this cloud sandbox / CI): Homebrew refuses to run as root, so it is
#     installed into the default prefix /home/linuxbrew/.linuxbrew owned by the
#     non-root `ubuntu` user, and every `brew` call is run as that user via sudo.
#     The prefix bin is added to PATH (this run + /etc/profile.d) so root and CI
#     agents can execute the installed tools.
#   - terraform and tflint are NOT in homebrew-core; they come from taps
#     (hashicorp/tap, terraform-linters/tap) on every platform.
#
# IDEMPOTENT: every tool is checked with `command -v` before install, so
# re-running is a no-op once the toolchain is present.
#
# Usage:
#   ./scripts/dev-setup.sh            # install everything missing
#   ./scripts/dev-setup.sh --check    # report status only, install nothing
#
set -euo pipefail

CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

NODE_MAJOR_MIN=20           # repo builds on Node 20+

log()  { printf '\033[1;34m[dev-setup]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
skip() { printf '\033[1;36m[skip]\033[0m %s already present: %s\n' "$1" "$2"; }

OS="$(uname -s)"
have() { command -v "$1" >/dev/null 2>&1; }
if [[ "$(id -u)" -eq 0 ]]; then SUDO=""; else SUDO="sudo"; fi

# --- Linux Homebrew (installed & run as the non-root ubuntu user) ----------
LINUXBREW_PREFIX="/home/linuxbrew/.linuxbrew"
LINUX_BREW_USER="ubuntu"
BREW_ENV=(HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ENV_HINTS=1)

# Run a brew command the right way for the platform.
brew_run() {
  if [[ "$OS" == "Darwin" ]]; then
    env "${BREW_ENV[@]}" brew "$@"
  else
    $SUDO -u "$LINUX_BREW_USER" env "${BREW_ENV[@]}" "$LINUXBREW_PREFIX/bin/brew" "$@"
  fi
}

apt_install() { $SUDO apt-get update -y >/dev/null && $SUDO apt-get install -y "$@"; }

ensure_brew() {
  if [[ "$OS" == "Darwin" ]]; then
    if have brew; then return 0; fi
    if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "Homebrew is MISSING (required on macOS)"; return 1; fi
    log "installing Homebrew ..."
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    return 0
  fi

  # ---- Linux ----
  if [[ ! -x "$LINUXBREW_PREFIX/bin/brew" ]]; then
    if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "Homebrew (Linux) is MISSING (would install as user '$LINUX_BREW_USER')"; return 1; fi
    if ! id "$LINUX_BREW_USER" >/dev/null 2>&1; then
      warn "non-root user '$LINUX_BREW_USER' not found; Homebrew cannot run as root."
      return 1
    fi
    log "installing Homebrew prerequisites ..."
    apt_install build-essential procps curl file git >/dev/null 2>&1 || \
      warn "could not apt-get prerequisites (continuing; they may already be present)"
    log "installing Homebrew into $LINUXBREW_PREFIX (owned by $LINUX_BREW_USER) ..."
    $SUDO mkdir -p "$LINUXBREW_PREFIX"
    $SUDO chown -R "$LINUX_BREW_USER:$LINUX_BREW_USER" "$(dirname "$LINUXBREW_PREFIX")"
    $SUDO -u "$LINUX_BREW_USER" git clone --depth=1 https://github.com/Homebrew/brew "$LINUXBREW_PREFIX/Homebrew"
    $SUDO -u "$LINUX_BREW_USER" mkdir -p "$LINUXBREW_PREFIX/bin"
    $SUDO -u "$LINUX_BREW_USER" ln -sf "$LINUXBREW_PREFIX/Homebrew/bin/brew" "$LINUXBREW_PREFIX/bin/brew"
  fi

  # Expose brew + its tools on PATH for this run and for future login shells.
  eval "$("$LINUXBREW_PREFIX/bin/brew" shellenv)"
  local profile="/etc/profile.d/homebrew.sh"
  if [[ "$CHECK_ONLY" -ne 1 && ! -f "$profile" ]]; then
    echo "eval \"\$($LINUXBREW_PREFIX/bin/brew shellenv)\"" | $SUDO tee "$profile" >/dev/null || true
  fi
  return 0
}

# brew_ensure <cli-name> <formula>  (formula may be tap-qualified)
brew_ensure() {
  local cli="$1" formula="$2"
  if have "$cli"; then skip "$cli" "$(command -v "$cli")"; return 0; fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then warn "$cli is MISSING (would: brew install $formula)"; return 0; fi
  log "installing $formula ..."
  brew_run install "$formula"
}

# tflint's AWS ruleset plugin (CI parity). GitHub-release download; best-effort.
install_tflint_aws_plugin_best_effort() {
  [[ "$CHECK_ONLY" -eq 1 ]] && return 0
  local script=".github/scripts/install-tflint-aws-plugin.sh"
  [[ -f "$script" ]] || return 0
  if bash "$script" >/dev/null 2>&1; then
    ok "tflint AWS ruleset plugin installed (full CI parity)"
  else
    warn "tflint AWS plugin not installed (network-restricted?); bundled terraform ruleset still catches unused-declaration errors"
  fi
}

# ---------------------------------------------------------------------------
log "OS detected: $OS  (check-only: $CHECK_ONLY)"

if ! ensure_brew; then
  warn "Homebrew is not available; cannot continue. See messages above."
  exit 1
fi

brew_ensure terraform hashicorp/tap/terraform
brew_ensure tflint    terraform-linters/tap/tflint
install_tflint_aws_plugin_best_effort
brew_ensure aws  awscli
brew_ensure node node
brew_ensure jq   jq
brew_ensure zip  zip

# Node version floor (the OS may already ship a newer/older node than brew's).
if have node; then
  major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  [[ "$major" -ge "$NODE_MAJOR_MIN" ]] || warn "node $(node --version) is below required v${NODE_MAJOR_MIN}"
fi

# Docker is a daemon/GUI concern — check only, never auto-install.
if have docker; then skip docker "$(command -v docker)"; else
  if [[ "$OS" == "Darwin" ]]; then
    warn "docker not found — install Docker Desktop: https://www.docker.com/products/docker-desktop/"
  else
    warn "docker not found — see https://docs.docker.com/engine/install/ubuntu/"
  fi
fi

log "shared toolchain ready. For service runtimes run the per-service script, e.g.:"
log "    ./humbugg/scripts/dev-setup.sh   # .NET SDK for the Humbugg backend"
[[ "$OS" != "Darwin" && "$CHECK_ONLY" -ne 1 ]] && log "Tools are on PATH via /etc/profile.d/homebrew.sh (new shells) or: eval \"\$($LINUXBREW_PREFIX/bin/brew shellenv)\""
ok "done."
