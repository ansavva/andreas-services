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
# Matching is token-based: the command is parsed with quotes and heredoc bodies
# respected, and only the arguments of a real `git push` invocation are
# inspected. The old version grepped the whole command string, so trunk's name
# appearing in *data* tripped it. Previously-blocked false positives that now
# pass (both hit for real on 2026-08-27 while raising PR #506):
#
#   git commit -m "...primary checkout... main ..." && git push -u origin claude/foo
#   gh pr create --base main --body "then: git commit && git push"
#   git checkout main && git push -u origin claude/foo
#
# Still blocked:
#   git push origin main / HEAD:main / :main / +main / --force main
#   bare `git push` (or `git push origin`, `git push origin HEAD`) on trunk
#
# Exit 2 with a message on stderr is how a PreToolUse hook denies a tool call.
set -uo pipefail

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)

TRUNK='main'

# Fast path: no `git <space> push` substring anywhere, even as data — done.
printf '%s' "$CMD" | grep -qE 'git[[:space:]]+push' || exit 0

legacy_verdict() {
  # Conservative whole-string match (the pre-2026-08-27 behavior). Used only
  # when token parsing is unavailable — it can false-positive on quoted data,
  # but never lets a real trunk push through that the parser would catch.
  if printf '%s' "$CMD" | grep -qE '(^|[;&|])[[:space:]]*git[[:space:]]+push'; then
    if printf '%s' "$CMD" | grep -qE "(^|[[:space:]:+])${TRUNK}([[:space:]]|$)"; then
      echo block
    else
      echo branch
    fi
  else
    echo allow
  fi
}

if command -v python3 >/dev/null 2>&1; then
  VERDICT=$(CMD="$CMD" TRUNK="$TRUNK" python3 - <<'PY'
import os, re, shlex, sys

cmd = os.environ.get("CMD", "")
trunk = os.environ.get("TRUNK", "main")

def out(v):
    print(v)
    sys.exit(0)

def conservative():
    # Mirror of legacy_verdict in the wrapper — for unbalanced quoting only.
    if re.search(r'(^|[;&|])\s*git\s+push', cmd, re.M):
        if re.search(r'(^|[\s:+])' + re.escape(trunk) + r'(\s|$)', cmd, re.M):
            out("block")
        out("branch")
    out("allow")

def heredoc_tags(line):
    # Heredoc openers on one line, honoring quote state so a quoted "<<" stays
    # data. Quote state is per line; a string spanning lines lands in the
    # ValueError fallback below rather than being mis-parsed.
    tags, i, n, q = [], 0, len(line), None
    while i < n:
        c = line[i]
        if q == "'":
            if c == "'":
                q = None
        elif q == '"':
            if c == "\\":
                i += 1
            elif c == '"':
                q = None
        elif c == "'":
            q = "'"
        elif c == '"':
            q = '"'
        elif c == "\\":
            i += 1
        elif c == "<" and line[i + 1:i + 2] == "<":
            if line[i + 2:i + 3] == "<":
                i += 2  # <<< herestring, not a heredoc
            else:
                m = re.match(r'<<-?\s*(["\']?)([A-Za-z0-9_]+)\1', line[i:])
                if m:
                    tags.append(m.group(2))
                    i += m.end() - 1
                else:
                    i += 1
        i += 1
    return tags

# Drop heredoc bodies — stdin data, not commands.
lines = cmd.split("\n")
kept, i = [], 0
while i < len(lines):
    kept.append(lines[i])
    for tag in heredoc_tags(lines[i]):
        i += 1
        while i < len(lines) and lines[i].strip() != tag:
            i += 1
    i += 1
text = "\n".join(kept)

# Join continuations, then make remaining newlines explicit separators so a
# push on its own line still sits at command position after tokenizing.
text = text.replace("\\\n", " ").replace("\n", " ; ")

lex = shlex.shlex(text, posix=True, punctuation_chars=True)
lex.whitespace_split = True
try:
    tokens = list(lex)
except ValueError:
    conservative()

OPS = set("();<>|&")

def is_op(t):
    return bool(t) and all(ch in OPS for ch in t)

# push options that take a separate value argument
VALUE_OPTS = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
# trunk as a push target: bare, +forced, or the destination of a colon refspec.
# `main:other` pushes local main elsewhere and is allowed.
target = re.compile(r'^\+?([^:]*:)?' + re.escape(trunk) + r'$')

verdict = "allow"
i = 0
while i < len(tokens) - 1:
    at_cmd_pos = i == 0 or is_op(tokens[i - 1])
    if not (at_cmd_pos and tokens[i] == "git" and tokens[i + 1] == "push"):
        i += 1
        continue
    j = i + 2
    args = []
    while j < len(tokens) and not is_op(tokens[j]):
        args.append(tokens[j])
        j += 1
    nonopts, skip, opts_done = [], False, False
    for t in args:
        if skip:
            skip = False
        elif not opts_done and t == "--":
            opts_done = True
        elif not opts_done and t in VALUE_OPTS:
            skip = True
        elif not opts_done and t.startswith("-") and t != "-":
            pass
        else:
            nonopts.append(t)
    if any(target.match(t) for t in nonopts):
        out("block")
    # No refspec (or HEAD) pushes the CURRENT branch — the wrapper resolves it.
    if not nonopts[1:] or any(r.lstrip("+") == "HEAD" for r in nonopts[1:]):
        verdict = "branch"
    i = j
out(verdict)
PY
  ) || VERDICT=$(legacy_verdict)
  [ -n "$VERDICT" ] || VERDICT=$(legacy_verdict)
else
  VERDICT=$(legacy_verdict)
fi

# A push with no refspec writes to the CURRENT branch. Checked out on trunk,
# that targets trunk without the word ever appearing in the command.
if [ "$VERDICT" = "branch" ]; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
  if [ "$BRANCH" = "$TRUNK" ]; then VERDICT=block; else VERDICT=allow; fi
fi

[ "$VERDICT" = "block" ] || exit 0

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
