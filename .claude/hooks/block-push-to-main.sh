#!/usr/bin/env bash
#
# Refuse any `git push` that would write to the trunk branch.
#
# GitHub branch protection is the authoritative gate — it applies to everyone and
# to the web UI. This hook exists because that gate reports failure only after a
# push has been attempted, and because `enforce_admins` is deliberately off so a
# human can override in an emergency. An agent should never be the one taking
# that override, so this stops the attempt before it leaves the machine.
#
# Blocks:  git push origin main / HEAD:main / +main / --force main / :main …
# Allows:  pushes to any other branch, and anything that isn't a git push.
#
# Exit 2 with a message on stderr is how a PreToolUse hook denies a tool call.
set -uo pipefail

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)

# Not a push — nothing to do.
printf '%s' "$CMD" | grep -qE '(^|[;&|]|&&)[[:space:]]*git[[:space:]]+push' || exit 0

TRUNK='main'

# A push targets trunk if trunk appears as a refspec argument: bare (`main`),
# as the destination of a colon pair (`HEAD:main`, `:main`), or force-prefixed
# (`+main`). Matching on word boundaries keeps `claude/main-thing` from tripping
# it, which a naive substring check would not.
TARGETS_TRUNK=0
printf '%s' "$CMD" | grep -qE "(^|[[:space:]:+])${TRUNK}([[:space:]]|$)" && TARGETS_TRUNK=1

# A bare `git push` names no refspec, so it pushes the CURRENT branch. Checked
# out on trunk, that writes to trunk without the word ever appearing in the
# command — the hole a refspec-only check leaves open.
if [ "$TARGETS_TRUNK" -eq 0 ]; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  [ "$BRANCH" = "$TRUNK" ] && TARGETS_TRUNK=1
fi

if [ "$TARGETS_TRUNK" -eq 1 ]; then
  cat >&2 <<EOF
BLOCKED: this command pushes to '${TRUNK}'.

Nothing lands on ${TRUNK} except through a pull request. ${TRUNK} is branch
protected on GitHub, so this push would be rejected anyway — this hook just
fails it here, before the attempt.

Open a branch and a PR instead:
  git checkout -b claude/<feature-name>
  git push -u origin claude/<feature-name>
  gh pr create --base ${TRUNK}

For a stack, use 'gh stack submit --auto' rather than pushing branches by hand.
EOF
  exit 2
fi

exit 0
