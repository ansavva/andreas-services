#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Install AWS CLI v2 if not present
if ! command -v aws &>/dev/null; then
  echo "Installing AWS CLI v2..." >&2
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli --update
  rm -rf /tmp/awscliv2.zip /tmp/aws
  echo "AWS CLI installed: $(aws --version)" >&2
else
  echo "AWS CLI already present: $(aws --version)" >&2
fi

# Install tflint if not present — the cloud image ships eslint/ruff but not
# tflint, and the PR workflows / pre-commit lint Terraform with it.
if ! command -v tflint &>/dev/null; then
  echo "Installing tflint..." >&2
  curl -fsSL https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash
  echo "tflint installed: $(tflint --version)" >&2
else
  echo "tflint already present: $(tflint --version)" >&2
fi

# Pre-download the tflint ruleset plugins so `tflint` is ready to run.
# Non-critical — never block the session if the plugin registry is unreachable.
tflint --init --config "$CLAUDE_PROJECT_DIR/.tflint.hcl" >&2 || true
