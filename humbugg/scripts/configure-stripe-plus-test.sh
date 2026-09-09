#!/usr/bin/env bash
# Kept for anyone still typing the old name. See configure-stripe-plus.sh.
exec "$(dirname "${BASH_SOURCE[0]}")/configure-stripe-plus.sh" --mode test "$@"
