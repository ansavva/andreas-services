#!/usr/bin/env bash
#
# Put the smoke account's password into GitHub Actions as an ENVIRONMENT secret
# on `studio-production`, where the smoke job in .github/workflows/studio-prod.yaml
# can see it. One-time setup, and re-run to rotate.
#
#   ./studio/scripts/prod-github-set-secrets.sh              # prompts, without echo
#   ./studio/scripts/prod-github-set-secrets.sh --check      # list what is set, change nothing
#
# ## ONE secret, and only one
#
# The address lives in studio/seeds/smoke.json. It ends in `.test`, a reserved
# TLD (RFC 2606) that can never be a real mailbox, so it is safe to commit and
# belongs next to the library it is seeded into. The `sub` is resolved from the
# pool at seed time rather than pinned, because a pinned one rots the moment the
# pool is replaced. What is left is a password.
#
# ADDING A SECOND SMOKE IDENTITY DOES NOT COME BACK HERE. It is an edit to the
# fixture; the next deploy creates the account with this same password. That is
# the point of keeping the address out of a secret.
#
# ## Why the ENVIRONMENT and not the repository
#
# Same scoping as `AWS_ROLE_ARN` on every studio job today. A repository secret
# is visible to every workflow in the repo, including ones with nothing to do
# with studio; an environment secret is visible only to a job that declares
# `environment: studio-production`. The flip side is the trap worth knowing on
# sight: a job that forgets the `environment:` key — or borrows another
# environment's name — sees the secret as an EMPTY STRING, silently. Both the
# seed step and the suite fail fast and name the variable rather than trying to
# sign in as nobody, but the fix is always to check `environment:` first.
#
# ## Credentials
#
# `gh`, not AWS: this touches GitHub only. The value is read from the
# environment or a no-echo prompt and never from a file in this repo. It is
# piped to `gh secret set` on stdin rather than passed as `--body`, so it never
# becomes an argv entry — argv is readable in `ps` by every other process on
# this machine for as long as the call takes.
#
# ## Idempotence
#
# `gh secret set` is an upsert, so re-running is how you ROTATE: the new value
# replaces the old under the same name, and the next deploy's seed step sets the
# smoke account to it. A rotation therefore converges rather than locking the
# suite out — which is why this prints what it is about to overwrite and asks
# first.
#
set -euo pipefail

REPO="${STUDIO_REPO:-ansavva/andreas-services}"

# Must match `environment:` on the smoke job in studio-prod.yaml, the variable
# the suite reads in backend/tests/smoke/conftest.py, and the placeholder the
# seeder expands in seeds/smoke.json. All four are one contract; renaming any
# without the others makes the job see an empty string.
readonly ENVIRONMENT="studio-production"
readonly SECRETS=(SMOKE_TEST_USER_PASSWORD)

log()  { printf '\033[1;34m[smoke-secrets]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

CHECK_ONLY=0
ASSUME_YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK_ONLY=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
    --help|-h)
      printf 'Usage: %s [--check] [--yes]\n\n' "$0"
      printf '  SMOKE_TEST_USER_PASSWORD  optional — prompted for, without echo, when unset\n'
      printf '  STUDIO_REPO               optional — defaults to %s\n' "$REPO"
      exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
  shift
done

command -v gh >/dev/null || die "gh CLI not installed."
gh auth status >/dev/null 2>&1 || die "Not logged in to GitHub. Run 'gh auth login'."

# Catch a typo'd or not-yet-created environment here, rather than as a
# `gh secret set` failure whose message does not say which of the two is wrong.
gh api "repos/$REPO/environments/$ENVIRONMENT" --silent >/dev/null 2>&1 ||
  die "No '$ENVIRONMENT' environment on $REPO. It is the one every studio job already
       declares; if it is missing, so is AWS_ROLE_ARN and nothing deploys."

existing="$(gh secret list --env "$ENVIRONMENT" --repo "$REPO" --json name --jq '.[].name')"

report() {
  log "Environment secrets on $ENVIRONMENT ($REPO):"
  for name in "${SECRETS[@]}"; do
    if grep -qx "$name" <<<"$existing"; then
      printf '  \033[1;32m✓\033[0m %s\n' "$name"
    else
      printf '  \033[1;31m✗\033[0m %s  (not set)\n' "$name"
    fi
  done
}

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  report
  for name in "${SECRETS[@]}"; do
    grep -qx "$name" <<<"$existing" || exit 1
  done
  ok "The smoke password is set on $ENVIRONMENT."
  exit 0
fi

report

# An existing value is about to be replaced. Say so before doing it — an
# accidental rotation breaks the next deploy's smoke job with a credential
# error nobody expected.
already=()
for name in "${SECRETS[@]}"; do
  grep -qx "$name" <<<"$existing" && already+=("$name")
done
if [[ ${#already[@]} -ne 0 && "$ASSUME_YES" -ne 1 ]]; then
  warn "About to OVERWRITE: ${already[*]}"
  warn "The next deploy's seed step resets the smoke account to the new value, so a"
  warn "rotation here converges rather than locking the suite out."
  read -rp "Continue? [y/N] " reply
  [[ "$reply" == [yY]* ]] || die "Aborted; nothing was changed."
fi

PASSWORD="${SMOKE_TEST_USER_PASSWORD:-}"
if [[ -z "$PASSWORD" ]]; then
  read -rsp "Password for the seeded smoke account (not echoed, not stored): " PASSWORD
  printf '\n'
fi
[[ -n "$PASSWORD" ]] || die "No password given."

# Checked against the pool's own policy here (12+, upper, lower, digit —
# studio/infra/modules/auth/main.tf) so a weak one fails in one line, rather
# than as an InvalidPasswordException inside a seed step on the next deploy.
{
  [[ ${#PASSWORD} -ge 12 ]] &&
    [[ "$PASSWORD" == *[[:lower:]]* ]] &&
    [[ "$PASSWORD" == *[[:upper:]]* ]] &&
    [[ "$PASSWORD" == *[[:digit:]]* ]]
} || die "Password does not meet the pool policy: 12+ characters with at least one
       lower-case letter, one upper-case letter and one digit."

# `printf` (a shell builtin) into gh's stdin: the value never becomes an argv
# entry, so it cannot be read out of `ps` by another user on this machine.
set_secret() {
  local name="$1" value="$2"
  printf '%s' "$value" | gh secret set "$name" --env "$ENVIRONMENT" --repo "$REPO" ||
    die "Failed to set $name. Your token needs write access to $REPO's Actions secrets."
  log "Set $name"
}

set_secret SMOKE_TEST_USER_PASSWORD "$PASSWORD"

existing="$(gh secret list --env "$ENVIRONMENT" --repo "$REPO" --json name --jq '.[].name')"
report
for name in "${SECRETS[@]}"; do
  grep -qx "$name" <<<"$existing" || die "$name is still missing after being set — check $REPO's settings."
done

ok "The smoke password is set on the $ENVIRONMENT environment."
log "Next: merge to main (or dispatch Studio · Deploy · Prod) and watch the 'smoke' job."
