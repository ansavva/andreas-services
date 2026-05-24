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
