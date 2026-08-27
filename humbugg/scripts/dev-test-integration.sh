#!/usr/bin/env bash
# Runs the backend integration tier against this machine's dev stack.
#
# This is the ONLY place HUMBUGG_INTEGRATION=1 is exported. The tests live in
# humbugg/backend/Humbugg.Api.IntegrationTests/ and self-skip without the flag,
# so `dotnet test Humbugg.slnx` (and CI) stays green without credentials while
# this script is the sanctioned way to actually run them.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"

# Preflight 1: the per-machine env file the tests read their table names from.
if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  echo "error: $BACKEND_DIR/.env not found." >&2
  echo "The integration tier runs against the per-machine dev stack." >&2
  echo "Provision it and write the env file with: humbugg/scripts/dev-aws-setup.sh" >&2
  exit 1
fi

# Preflight 2: working AWS credentials. The tests use the ambient default chain,
# exactly like the AWS CLI, so if this fails the tests would too — say so first.
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "error: aws sts get-caller-identity failed — no working AWS credentials." >&2
  echo "The integration tier talks to real dev-stack DynamoDB tables." >&2
  exit 1
fi

export HUMBUGG_INTEGRATION=1
exec dotnet test "$BACKEND_DIR/Humbugg.Api.IntegrationTests/Humbugg.Api.IntegrationTests.csproj" "$@"
