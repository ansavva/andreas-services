#!/usr/bin/env bash
#
# Add an existing studio user to a library, or list who is already in one.
#
# **Deliberately a script and not an API route.** Membership is the whole of
# authorisation in this service — every route checks the caller's rows against
# the library a node says it belongs to — so a route that granted membership
# would be a route that could grant itself access to somebody else's library.
# There is no such route, and there should not be one. Granting access is an
# out-of-band act, like creating the account itself (`create-user.sh`).
#
# **Membership rides on the ID token only through `sub`.** The token carries no
# library and no role, so nothing about it goes stale when a row is written here
# — a user already signed in sees the new library on their next call to
# `GET /api/libraries`, with no refresh and no sign-out. What the user must
# already have is an account in the pool: `sub` is the pool's, and this script
# reads it rather than inventing one.
#
# Safe to run repeatedly. An existing membership is left exactly as it is,
# including its role — this script grants access and never revokes or changes
# it, because "add" quietly demoting an owner is the kind of surprise that costs
# somebody their library.
#
# Required env:
#   STUDIO_EMAIL     the pool account to add (its username)
#   STUDIO_LIBRARY   the library id, `lib-<uuid>`
# Optional:
#   STUDIO_ROLE      owner | member  (default: member)
#   USER_POOL_ID     defaults to the value the deploy workflow wrote to SSM
#   CATALOG_TABLE    same
#   AWS_REGION       defaults to us-east-1
#
# Usage:
#   STUDIO_EMAIL=you@example.com STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh
#   STUDIO_ROLE=owner STUDIO_EMAIL=… STUDIO_LIBRARY=… ./studio/scripts/add-member.sh
#   STUDIO_LIBRARY=lib-… ./studio/scripts/add-member.sh --list
#
# The defaults point at **prod**, like `create-user.sh` and unlike everything
# named `dev-*`. To reach this machine's dev stack, set `USER_POOL_ID` and
# `CATALOG_TABLE` from `dev-aws-setup.sh`'s outputs — there is no flag for it,
# for the reason `studio/CLAUDE.md` gives about not designing one unprompted.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
LIST_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --list) LIST_ONLY=true ;;
    # To the first blank line, which is where the header ends. A line range
    # would go stale the next time a paragraph is added above it.
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

: "${STUDIO_LIBRARY:?STUDIO_LIBRARY is required (the lib-<uuid> to grant access to)}"

# Checked here, before the first AWS call, because a role that is neither of the
# two words is a typo and a typo should not cost three round trips to find out
# about. `member` is the default: the wider grant is the one you have to ask for
# by name.
ROLE="${STUDIO_ROLE:-member}"
if [ "$ROLE" != "owner" ] && [ "$ROLE" != "member" ]; then
  echo "STUDIO_ROLE must be 'owner' or 'member' (got '${ROLE}')." >&2
  exit 2
fi

if [ -z "${USER_POOL_ID:-}" ]; then
  USER_POOL_ID=$(aws ssm get-parameter \
    --name /studio/prod/cognito-user-pool-id \
    --query Parameter.Value --output text --region "$REGION")
fi

if [ -z "${CATALOG_TABLE:-}" ]; then
  CATALOG_TABLE=$(aws ssm get-parameter \
    --name /studio/prod/catalog-table \
    --query Parameter.Value --output text --region "$REGION")
fi

# The library has to exist before anyone is added to it. A membership row
# naming no library is not an error the table can refuse — the two are separate
# items — and what it produces is an entry in `GET /api/libraries` that works,
# cannot be renamed and has an id for a name. `routes/libraries.py` reports it
# rather than hiding it, and this is where it is cheapest to prevent.
#
# Existence is asked of `sk`, which is part of the key and therefore on every
# row, rather than of `name`, which is not: nothing in this service creates a
# library, so the rows are hand-written and one without a name is possible.
# **And "no item" reads as the four characters `None`** — `aws … --output text`
# prints that for a null JMESPath result, so a `grep -q .` on it matches happily
# and every check in this script has to compare against the word.
LIBRARY=$(aws dynamodb get-item \
  --table-name "$CATALOG_TABLE" \
  --key "{\"pk\":{\"S\":\"LIB#${STUDIO_LIBRARY}\"},\"sk\":{\"S\":\"META\"}}" \
  --query Item.sk.S --output text --region "$REGION" 2>/dev/null || true)

if [ -z "$LIBRARY" ] || [ "$LIBRARY" = "None" ]; then
  echo "No library '${STUDIO_LIBRARY}' in ${CATALOG_TABLE}." >&2
  exit 1
fi

# ── Listing ────────────────────────────────────────────────────────────────
#
# Membership is stored under the *user's* partition so that a sign-in reads one
# partition, which leaves "who else is in here" with nothing to query but the
# inverted index — `by-sk`, the same one `catalog.members_of` reads. A scan
# would work and is the wrong habit to leave in a script somebody copies.

if [ "$LIST_ONLY" = true ]; then
  echo "Members of ${STUDIO_LIBRARY}:"
  aws dynamodb query \
    --table-name "$CATALOG_TABLE" \
    --index-name by-sk \
    --key-condition-expression "sk = :sk" \
    --expression-attribute-values "{\":sk\":{\"S\":\"LIB#${STUDIO_LIBRARY}\"}}" \
    --query 'Items[].[pk.S, role.S, created_at.S]' --output text --region "$REGION" |
    while read -r pk role created; do
      sub="${pk#USER#}"
      # A `sub` is opaque and nobody knows theirs. The pool can turn it back
      # into the address the person signs in with, which is the only form of
      # this list worth reading. Best effort: a sub whose account has since
      # been deleted still holds membership, and saying so beats hiding it.
      email=$(aws cognito-idp admin-list-users \
        --user-pool-id "$USER_POOL_ID" \
        --filter "sub = \"${sub}\"" \
        --query 'Users[0].Attributes[?Name==`email`].Value | [0]' \
        --output text --region "$REGION" 2>/dev/null || true)
      # An explicit `if`, not `[ … ] || [ … ] && …`: under `set -e` that
      # compound returns non-zero on the ordinary case — a member whose email
      # resolved — and takes the loop's subshell down with it after the first
      # row.
      if [ -z "$email" ] || [ "$email" = "None" ]; then email="(no pool account)"; fi
      printf '  %-32s %-7s %s  %s\n' "$email" "$role" "$created" "$sub"
    done
  exit 0
fi

# ── Adding ─────────────────────────────────────────────────────────────────

: "${STUDIO_EMAIL:?STUDIO_EMAIL is required}"
# `sub` and not the email. The email is the pool's username and a person can
# change it; `sub` is immutable and is the claim the API reads out of the ID
# token, so it is the only thing a membership row can be keyed on. A user who
# does not exist is refused here rather than granted access that resolves to
# nobody.
SUB=$(aws cognito-idp admin-get-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$STUDIO_EMAIL" \
  --query 'UserAttributes[?Name==`sub`].Value | [0]' \
  --output text --region "$REGION" 2>/dev/null || true)

if [ -z "$SUB" ] || [ "$SUB" = "None" ]; then
  echo "No user '${STUDIO_EMAIL}' in ${USER_POOL_ID}." >&2
  echo "Create it first: STUDIO_EMAIL=${STUDIO_EMAIL} ./studio/scripts/create-user.sh" >&2
  exit 1
fi

EXISTING=$(aws dynamodb get-item \
  --table-name "$CATALOG_TABLE" \
  --key "{\"pk\":{\"S\":\"USER#${SUB}\"},\"sk\":{\"S\":\"LIB#${STUDIO_LIBRARY}\"}}" \
  --query Item.role.S --output text --region "$REGION" 2>/dev/null || true)

if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ]; then
  echo "'${STUDIO_EMAIL}' is already a ${EXISTING} of ${STUDIO_LIBRARY} — leaving it untouched."
  exit 0
fi

# `created_at` is stamped to the second with zero microseconds, unlike every
# timestamp `services.catalog` writes. Microseconds there are what stop two
# nodes created inside one second from colliding in the reel's sort; nothing
# sorts memberships, and BSD `date` has no `%N` to produce them with.
#
# The condition is what makes the read above an optimisation rather than the
# check: two runs at once would both see no row, and only one of them may
# write. A cancelled put means the other one won, which is the same outcome the
# branch above reports.
if aws dynamodb put-item \
  --table-name "$CATALOG_TABLE" \
  --item "{
    \"pk\": {\"S\": \"USER#${SUB}\"},
    \"sk\": {\"S\": \"LIB#${STUDIO_LIBRARY}\"},
    \"role\": {\"S\": \"${ROLE}\"},
    \"created_at\": {\"S\": \"$(date -u +%Y-%m-%dT%H:%M:%S).000000+00:00\"}
  }" \
  --condition-expression "attribute_not_exists(pk)" \
  --region "$REGION" 2>/dev/null; then
  echo "Added '${STUDIO_EMAIL}' to ${STUDIO_LIBRARY} as ${ROLE}."
  echo "They see it on their next GET /api/libraries — no sign-out, no token refresh."
else
  echo "'${STUDIO_EMAIL}' is already a member of ${STUDIO_LIBRARY} — leaving it untouched."
fi
