#!/usr/bin/env bash

set -euo pipefail

# TFLint 0.63.1 currently panics while reading the GitHub attestation bundle
# published for this ruleset. Install the exact release archive ourselves and
# pin its SHA-256 instead of disabling plugin verification.
version="0.47.0"
archive="tflint-ruleset-aws_linux_amd64.zip"
expected_sha256="6ba3e665642be9ae61b08ca04f0396fdba33ee9be3b5fdb36d5603208887e17d"
plugin_root="${TFLINT_PLUGIN_DIR:-${HOME}/.tflint.d/plugins}"
plugin_dir="${plugin_root}/github.com/terraform-linters/tflint-ruleset-aws/${version}"
download_dir="$(mktemp -d)"

cleanup() {
  rm -rf "${download_dir}"
}
trap cleanup EXIT

curl \
  --fail \
  --location \
  --connect-timeout 10 \
  --max-time 60 \
  --retry 3 \
  --silent \
  --show-error \
  --output "${download_dir}/${archive}" \
  "https://github.com/terraform-linters/tflint-ruleset-aws/releases/download/v${version}/${archive}"

if command -v sha256sum >/dev/null 2>&1; then
  actual_sha256="$(sha256sum "${download_dir}/${archive}" | awk '{print $1}')"
else
  actual_sha256="$(shasum -a 256 "${download_dir}/${archive}" | awk '{print $1}')"
fi
test "${actual_sha256}" = "${expected_sha256}"
mkdir -p "${plugin_dir}"
unzip -q "${download_dir}/${archive}" -d "${plugin_dir}"
test -x "${plugin_dir}/tflint-ruleset-aws"
