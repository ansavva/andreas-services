#!/usr/bin/env bash
#
# dev-aws-seed.sh — fill this machine's dev stack from the published fixture.
#
# A freshly provisioned stack is empty: `dev-aws-setup.sh` creates the bucket,
# the table and the pool and puts nothing in them. This downloads the fixture
# published to the shared seed bucket and loads it, so `dev-up.sh` shows a
# library that looks like the product instead of a blank page.
#
#   ./studio/scripts/dev-aws-seed.sh --dry-run     # what it would load
#   ./studio/scripts/dev-aws-seed.sh
#
# ── THIS SCRIPT MUST NEVER BE ABLE TO SPEND MONEY ──────────────────────────
#
# **It does not generate. It calls no model provider. It requires no API
# token.** Building the fixture is the `--publish` step in #284 — run rarely, by
# a human, under hard rule #2's approval gate — and this only ever downloads
# what that produced. Generating per machine would re-bill on every setup.
#
# That property is pinned by a test rather than by this comment:
# `pipeline/tests/test_dev_scripts.py` greps this file's executable lines. The
# test says what it does and does not catch; read it before adding a command
# here that runs anything.
#
# It also destroys nothing. Emptying a dev stack is `dev-aws-reset.sh`, and a
# re-seed over a populated stack converges rather than duplicating — see
# "Idempotent" below.
#
# ── WHAT IT READS ──────────────────────────────────────────────────────────
#
#   s3://studio-dev-seed-us-east-1/          shared, versioned, read-only here
#     v1/catalog.json                        the node tree
#     v1/manifest.json                       object count, total bytes, checksums
#     v1/media/…                             the fixture bytes
#
# `v1/` is a version prefix, so re-seeding to a known revision is a `v2/`
# change rather than a mutation. Override the bucket with `--seed-bucket` or
# `STUDIO_DEV_SEED_BUCKET`, and the prefix with `--fixture-version`.
#
# **NEITHER THE BUCKET NOR THE FIXTURE EXISTS YET.** They are #284, which is
# human-gated because it generates media. Until it lands, every run of this
# script stops at the first read and says so. That is the expected outcome
# today, not a fault in your stack.
#
# ── THE CONTRACT WITH #284 ─────────────────────────────────────────────────
#
# `catalog.json` and `manifest.json` are authoritative in git and copied into
# the bucket for this to read. This script is a loader and validates them
# rather than repairing them: anything malformed is reported and nothing is
# written.
#
#   catalog.json
#     {
#       "version": 1,
#       "library_name": "Studio",
#       "nodes": [
#         {"path": "projects", "kind": "folder",
#          "created_at": "2026-08-19T09:12:44.000000+00:00"},
#         {"path": "projects/<project>/runs/<runref>/request.json",
#          "kind": "file", "source": "v1/media/request.json",
#          "content_type": "application/json",
#          "created_at": "2026-08-19T09:12:44.000001+00:00"}
#       ]
#     }
#
# `path` is the slash-joined chain of NAMES from the library root, and it is how
# a node's parent is expressed — the same encoding `catalog_seed.py` uses, so
# there is one scheme here and not a second one. Every ancestor folder must
# appear as its own node; the loader will not invent one, because a fixture is
# reviewed in git and a silently-invented folder is a shape nobody chose.
#
# `created_at` is required and carries the ordering the app's reel and
# `by-recent` index read. It is copied from the dev stack the fixture was
# promoted from, so the fixture sorts the way the material it came from did.
# **Nothing here reads a clock**, for the reason `catalog_seed.py` does not:
# every id and every stamp has to be a pure function of the inputs or a re-run
# cannot recognise what the last one wrote.
#
#   manifest.json
#     {"version": "v1", "object_count": 7, "total_bytes": 214803,
#      "objects": {"v1/media/request.json": {"size": 61, "sha256": "<hex>"}}}
#
# Every file node's `source` must appear in `objects` and every entry in
# `objects` must be claimed by exactly one node. That cross-check is the first
# thing this script does, and it is what makes the two documents one fixture
# rather than two lists that drift.
#
# ── IDS, AND WHY A RE-RUN CONVERGES ────────────────────────────────────────
#
# Ids are derived, never drawn: `uuid5` over `s3://<dev bucket>/<path>`, exactly
# as `catalog_seed.py` derives them. So the same fixture on the same stack
# always produces the same library id, the same node ids and therefore the same
# `blobs/<node_id>` keys — re-running rewrites the same objects and skips the
# rows that are already there, rather than creating a second tree beside the
# first. Two machines derive different ids, because the bucket name is in the
# derivation, and that is correct: they are different libraries.
#
# ── WHAT IT WRITES, IN ORDER ───────────────────────────────────────────────
#
#   1. the fixture bytes  -> s3://<dev bucket>/blobs/<node_id>
#   2. shared material    -> config/ and phrasebook/wording.yaml
#                            (dev-shared-material.sh, shared with dev-setup.sh)
#   3. the catalog        -> the library, its root node, the owner's membership
#                            row, and two items per node
#   4. verify             -> re-read from the dev bucket and check the count,
#                            the byte total and every checksum against the
#                            manifest
#
# Step 3 writes a node as ONE TransactWriteItems of two items — the `META`
# record and the `NAME#` listing item — because a node that exists under one key
# and not the other either cannot be listed or cannot be opened. The root is the
# exception at one item: it has no parent and no name, so there is nothing for a
# `NAME#` item to pair. See infra/README.md.
#
# The owner is this machine's dev account (`dev-user.sh`), and the `sub` comes
# from the DEV pool. No production credential is used at any point: a developer
# with their own dev stack and read access to the seed bucket can run this.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=dev-aws-common.sh
source "$SCRIPT_DIR/dev-aws-common.sh"

# The shared-material pushes run through the same `--profile` decision every
# other call here does, rather than a bare `aws`.
SHARED_MATERIAL_AWS=(aws_dev)
# shellcheck source=dev-shared-material.sh
source "$SCRIPT_DIR/dev-shared-material.sh"

SEED_BUCKET="${STUDIO_DEV_SEED_BUCKET:-studio-dev-seed-us-east-1}"
FIXTURE_VERSION="v1"
DRY_RUN=0

# ── pure helpers ────────────────────────────────────────────────────────────
#
# These read nothing and write nothing, which is what lets the test suite source
# this file and exercise them without touching AWS. That is also why the body
# below is behind a `main` guarded on BASH_SOURCE rather than run top to bottom
# like its siblings.

uuid5_url() {
  # uuid5 in the URL namespace: SHA-1 over the namespace's sixteen bytes
  # followed by the name, with the version and variant bits forced.
  #
  # Reimplemented here rather than shelled out to Python because this script
  # must not depend on the pipeline's environment being installed — and because
  # a `python` invocation in a setup script is exactly what the money test
  # forbids. `test_dev_scripts.py` checks it against `uuid.uuid5` so the two
  # derivations cannot drift.
  local name="$1" digest version variant
  digest="$(
    {
      printf '\x6b\xa7\xb8\x11\x9d\xad\x11\xd1\x80\xb4\x00\xc0\x4f\xd4\x30\xc8'
      printf '%s' "$name"
    } | openssl dgst -sha1 | sed 's/^.*= *//' | tr -d '[:space:]'
  )"
  [[ "${#digest}" -eq 40 ]] || die "openssl returned no SHA-1 digest."
  version="$(printf '%02x' "$(( (0x${digest:12:2} & 0x0f) | 0x50 ))")"
  variant="$(printf '%02x' "$(( (0x${digest:16:2} & 0x3f) | 0x80 ))")"
  printf '%s-%s-%s%s-%s%s-%s' \
    "${digest:0:8}" "${digest:8:4}" "$version" "${digest:14:2}" \
    "$variant" "${digest:18:2}" "${digest:20:12}"
}

derive_library_id() {
  # derive_library_id <bucket>. One bucket, one library; the bucket names it.
  printf 'lib-%s' "$(uuid5_url "s3://$1")"
}

derive_node_id() {
  # derive_node_id <bucket> <path>. `""` is the library root.
  printf 'node-%s' "$(uuid5_url "s3://$1/$2")"
}

materialised() {
  # materialised <bucket> <parent path> — the `path` attribute for a node
  # sitting directly inside that parent: ancestor ids, root first,
  # slash-delimited. The root's own path is `/`, so a node at the library root
  # gets `/<root id>/`. `parent_id` stays authoritative; this is the derived
  # index that makes a subtree one `begins_with` query.
  local bucket="$1" prefix="$2" out accumulated part
  out="/$(derive_node_id "$bucket" "")/"
  if [[ -n "$prefix" ]]; then
    accumulated=""
    while IFS= read -r part; do
      accumulated="${accumulated:+$accumulated/}$part"
      out+="$(derive_node_id "$bucket" "$accumulated")/"
    done < <(printf '%s\n' "$prefix" | tr '/' '\n')
  fi
  printf '%s' "$out"
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

fixture_problems() {
  # fixture_problems <catalog json> <manifest json> — every reason the fixture
  # cannot be loaded, one per line, or nothing.
  #
  # All of them at once rather than the first: a fixture is fixed by editing it
  # in git and re-publishing, so a list is one round trip and a first-failure is
  # as many round trips as there are mistakes. Same reason `catalog_seed.plan`
  # collects `unmapped` instead of raising.
  jq -r -n --argjson catalog "$1" --argjson manifest "$2" '
    def segments: split("/");
    def parent: segments[:-1] | join("/");
    def name: segments[-1];

    ($catalog.nodes // []) as $nodes
    | ($nodes | map(select(.kind == "folder") | .path)) as $folders
    | ($nodes | map(.path)) as $paths
    | ($manifest.objects // {}) as $objects
    | [
        (if ($catalog | has("nodes") | not) then "catalog.json has no `nodes`" else empty end),
        (if ($nodes | length) == 0 then "catalog.json lists no nodes" else empty end),
        (if ($manifest | has("objects") | not) then "manifest.json has no `objects`" else empty end),

        ($paths | group_by(.) | map(select(length > 1) | .[0])[]
          | "duplicate path: \(.)"),

        ($nodes[]
          | select((.path // "") == "")
          | "a node has no `path`"),

        # The same rejections `catalog_seed.clean_name` makes, which are in turn
        # a copy of the API validator: an empty segment, `.` or `..`, a control
        # character, or a name over 255 bytes.
        ($nodes[] | select(.path != null)
          | . as $n
          | ($n.path | segments)[]
          | select(. == "" or . == "." or . == ".."
                   or test("[[:cntrl:]]") or (utf8bytelength > 255))
          | "unusable name in path \($n.path | tojson)"),

        ($nodes[] | select(.path != null and (.kind | IN("file", "folder") | not))
          | "\(.path): kind must be `file` or `folder`, not \(.kind | tojson)"),

        ($nodes[] | select(.path != null and ((.created_at // "") == ""))
          | "\(.path): no `created_at` — the fixture carries the ordering"),

        ($nodes[] | select(.path != null and (.path | parent) != "" and ((.path | parent) as $p | $folders | index($p) | not))
          | "\(.path): its parent folder is not a node in catalog.json"),

        ($nodes[] | select(.kind == "file" and ((.source // "") == ""))
          | "\(.path): a file node needs a `source` key in the seed bucket"),

        ($nodes[] | select(.kind == "file" and ((.content_type // "") == ""))
          | "\(.path): a file node needs a `content_type`"),

        ($nodes[] | select(.kind == "folder" and (.source != null))
          | "\(.path): a folder node may not carry a `source`"),

        ($nodes[] | select(.kind == "file" and .source != null and ($objects[.source] == null))
          | "\(.path): source \(.source) is not in manifest.json"),

        ($nodes | map(select(.kind == "file") | .source) | group_by(.)
          | map(select(length > 1) | .[0])[]
          | "source claimed by more than one node: \(.)"),

        ($objects | keys[] as $key
          | select([$nodes[] | select(.kind == "file") | .source] | index($key) | not)
          | "manifest object claimed by no node: \($key)"),

        (($manifest.object_count // -1) as $declared
          | ($objects | length) as $actual
          | select($declared != $actual)
          | "manifest object_count is \($declared) but it lists \($actual)"),

        (($manifest.total_bytes // -1) as $declared
          | ([$objects[].size] | add // 0) as $actual
          | select($declared != $actual)
          | "manifest total_bytes is \($declared) but its sizes add to \($actual)")
      ][]
  '
}

# The two jq definitions both item builders need.
#
# `ddb` is the marshalling `adapters/ddb.py::to_item` does on the other side:
# DynamoDB's low-level API takes typed attribute maps, and `{"S": …}` / `{"N":
# …}` spelled out at each call site is where a `size` silently becomes a string.
# Nulls are DROPPED rather than written as NULL — a folder has no `blob_key`,
# "the attribute is absent" is what the schema means by that, and an absent
# attribute is also what `attribute_not_exists` tests.
DDB_JQ_DEFS='
  def ddb: with_entries(select(.value != null))
    | with_entries(.value |= (if type == "number" then {N: (. | tostring)} else {S: .} end));
  def put($item): {Put: {TableName: $table, Item: ($item | ddb),
                         ConditionExpression: "attribute_not_exists(pk)"}};
'

library_items() {
  # library_items <table> <lib id> <root id> <library name> <owner sub> <created at>
  #
  # The library, the owner's membership and the root node — one transaction,
  # because a library whose root row is missing is not half-created but broken:
  # every write at the library root reads the parent's `path` first.
  #
  # **The root is ONE item, not two.** It is the only node with neither a
  # `parent_id` nor a `name`; both absences say the same thing, and a `NAME#`
  # item exists to pair a name with a parent. Its display name is the library's.
  jq -c -n --arg table "$1" --arg lib "$2" --arg root "$3" \
    --arg name "$4" --arg sub "$5" --arg born "$6" \
    "$DDB_JQ_DEFS"'
    [ put({pk: "LIB#\($lib)", sk: "META", name: $name, root_node: $root,
           created_at: $born}),
      put({pk: "USER#\($sub)", sk: "LIB#\($lib)", role: "owner",
           created_at: $born}),
      put({pk: "NODE#\($root)", sk: "META", node_id: $root, lib: $lib,
           kind: "folder", path: "/", created_at: $born, updated_at: $born}) ]'
}

node_items() {
  # node_items <table> <lib id> <node id> <parent id> <name> <kind>
  #            <materialised path> <created at> <content type> <size>
  #
  # Two items, one transaction, per node. That is the price of getting
  # list-by-parent and unique-name-per-folder out of one table, and a node that
  # exists under one key and not the other either cannot be listed or cannot be
  # opened.
  #
  # The `NAME#` item is deliberately narrow — `node_id, lib, kind, path,
  # created_at` and nothing else. `size` and `content_type` are mutable, so
  # duplicating them here would put every rename, move and text edit in the
  # business of keeping two copies in step.
  jq -c -n --arg table "$1" --arg lib "$2" --arg node "$3" --arg parent "$4" \
    --arg name "$5" --arg kind "$6" --arg path "$7" --arg created "$8" \
    --arg content_type "$9" --argjson size "${10}" \
    "$DDB_JQ_DEFS"'
    ($kind == "file") as $is_file
    | [ put({pk: "NODE#\($node)", sk: "META", node_id: $node, parent_id: $parent,
             lib: $lib, name: $name, kind: $kind, path: $path,
             created_at: $created, updated_at: $created,
             blob_key: (if $is_file then "blobs/\($node)" else null end),
             size: (if $is_file then $size else null end),
             content_type: (if $is_file then $content_type else null end)}),
        put({pk: "NODE#\($parent)", sk: "NAME#\($name)", node_id: $node,
             lib: $lib, kind: $kind, path: $path, created_at: $created}) ]'
}

ddb_transaction() {
  # ddb_transaction <table> <items json>  ->  0 written, 2 already there
  #
  # A refused `attribute_not_exists(pk)` is not an error here; it is "already
  # seeded", and it is the whole of this script's idempotency. Anything else —
  # a throttle, a missing table, a validation failure — still stops the run.
  #
  # **The distinction is read out of the CLI's error text**, which is a string
  # match and the least durable line in this file. The pre-check in `seed_node`
  # is what normally keeps a re-run off this path at all; this is the guard for
  # the case where a row appeared between the check and the write.
  local table="$1" items="$2" error reasons residue
  if error="$(aws_dev dynamodb transact-write-items --transact-items "$items" 2>&1)"; then
    return 0
  fi
  reasons="$(sed -n 's/.*\[\([^]]*\)\].*/\1/p' <<<"$error")"
  residue="${reasons//ConditionalCheckFailed/}"
  residue="${residue//None/}"
  residue="${residue//,/}"
  residue="${residue// /}"
  if [[ -n "$reasons" && -z "$residue" ]]; then
    return 2
  fi
  die "Writing to $table failed: $error"
}

usage() {
  printf 'Usage: %s [--profile NAME] [--region REGION] [--seed-bucket NAME]\n' "$0"
  printf '       %*s [--fixture-version v1] [--dry-run]\n' "${#0}" ''
}

# ── the run ─────────────────────────────────────────────────────────────────

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile) [[ $# -ge 2 ]] || die "--profile requires a value."; AWS_PROFILE_VALUE="$2"; shift ;;
      --region) [[ $# -ge 2 ]] || die "--region requires a value."; AWS_REGION_VALUE="$2"; shift ;;
      --seed-bucket) [[ $# -ge 2 ]] || die "--seed-bucket requires a value."; SEED_BUCKET="$2"; shift ;;
      --fixture-version) [[ $# -ge 2 ]] || die "--fixture-version requires a value."; FIXTURE_VERSION="$2"; shift ;;
      --dry-run) DRY_RUN=1 ;;
      --help|-h) usage; exit 0 ;;
      *) die "Unknown option: $1" ;;
    esac
    shift
  done

  for command in aws jq openssl; do require_command "$command"; done
  command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1 ||
    die "Either sha256sum or shasum is required to verify the fixture."

  load_machine_id false
  load_aws_identity
  load_dev_stack_outputs

  local bucket="$DEV_BUCKET" table="$DEV_TABLE" pool="$DEV_POOL_ID"

  # The same guards `dev-aws-reset.sh` runs, and for the same reason: this
  # writes, and a write aimed at the wrong stack is not fixed by re-running.
  # `prod` first and separately — every other check compares against a value
  # derived from this machine's id, so they all fail together if the id is
  # wrong, but a name carrying `prod` means something none of them anticipates.
  local name
  for name in "$bucket" "$table"; do
    [[ "$name" != *prod* ]] || die "Refusing: '$name' names a production resource."
  done
  [[ "$bucket" == "$RESOURCE_PREFIX-media-$AWS_REGION_VALUE" ]] ||
    die "Refusing: unexpected S3 bucket '$bucket'."
  [[ "$table" == "$RESOURCE_PREFIX-catalog" ]] ||
    die "Refusing: unexpected DynamoDB table '$table'."

  log "Dev stack:   s3://$bucket/  +  $table"
  log "Fixture:     s3://$SEED_BUCKET/$FIXTURE_VERSION/"

  # The owner of the library. From the DEV pool, never prod.
  local owner_sub
  owner_sub="$(aws_dev cognito-idp admin-get-user \
    --user-pool-id "$pool" --username "$STUDIO_DEV_USER_EMAIL" \
    --query 'UserAttributes[?Name==`sub`].Value | [0]' --output text 2>/dev/null || true)"
  [[ -n "$owner_sub" && "$owner_sub" != "None" ]] ||
    die "No '$STUDIO_DEV_USER_EMAIL' in $pool, so the library would have no member. Run ./studio/scripts/dev-user.sh first."

  # ── the fixture documents ────────────────────────────────────────────────
  #
  # Read first, and the failure here is the one every run hits today. Say what
  # is missing and whose job it is, rather than letting a NoSuchBucket from the
  # AWS CLI read as a broken dev stack.
  local catalog_json manifest_json
  catalog_json="$(aws_dev s3 cp "s3://$SEED_BUCKET/$FIXTURE_VERSION/catalog.json" - 2>/dev/null)" || {
    warn "Could not read s3://$SEED_BUCKET/$FIXTURE_VERSION/catalog.json."
    warn "  The seed bucket and the fixture in it are #284, which has not landed:"
    warn "  the bucket does not exist yet and nothing has been published to it."
    warn "  Nothing is wrong with your stack — there is simply nothing to load."
    die "No fixture to seed from."
  }
  manifest_json="$(aws_dev s3 cp "s3://$SEED_BUCKET/$FIXTURE_VERSION/manifest.json" - 2>/dev/null)" ||
    die "s3://$SEED_BUCKET/$FIXTURE_VERSION/catalog.json exists but manifest.json does not. The fixture is incomplete; see #284."

  jq -e . >/dev/null 2>&1 <<<"$catalog_json" || die "catalog.json is not valid JSON."
  jq -e . >/dev/null 2>&1 <<<"$manifest_json" || die "manifest.json is not valid JSON."

  local problems
  problems="$(fixture_problems "$catalog_json" "$manifest_json")"
  if [[ -n "$problems" ]]; then
    warn "The fixture is not loadable:"
    while IFS= read -r problem; do warn "  $problem"; done <<<"$problems"
    die "Fix the fixture in git and re-publish it (#284). Nothing was written."
  fi

  local library_id root_id library_name born
  library_id="$(derive_library_id "$bucket")"
  root_id="$(derive_node_id "$bucket" "")"
  library_name="$(jq -r '.library_name // "Studio"' <<<"$catalog_json")"
  # The root's stamp is the oldest thing in the fixture, for the reason nothing
  # here reads a clock: the phases have to agree on a re-run.
  born="$(jq -r '[.nodes[].created_at] | min' <<<"$catalog_json")"

  local node_count file_count
  node_count="$(jq '.nodes | length' <<<"$catalog_json")"
  file_count="$(jq '[.nodes[] | select(.kind == "file")] | length' <<<"$catalog_json")"

  printf '\n  library      %s  (%s)\n' "$library_id" "$library_name"
  printf '  root node    %s  (path "/", no parent)\n' "$root_id"
  printf '  owner        USER#%s\n' "$owner_sub"
  printf '  nodes        %s  (%s file(s); 2 items each, the root 1)\n' "$node_count" "$file_count"
  printf '  objects      %s  (%s bytes)\n\n' \
    "$(jq -r '.object_count' <<<"$manifest_json")" \
    "$(jq -r '.total_bytes' <<<"$manifest_json")"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    jq -r '.nodes[] | "  \(.kind)\t\(.path)"' <<<"$catalog_json" | sort -k2
    ok "Dry run complete; nothing was changed."
    return 0
  fi

  local workdir
  workdir="$(mktemp -d)"
  # shellcheck disable=SC2064  # expand workdir now, not when the trap fires
  trap "rm -rf '$workdir'" EXIT

  # ── 1. the fixture bytes ─────────────────────────────────────────────────
  #
  # Downloaded, checksummed, then uploaded. A server-side copy would be one
  # call instead of two, and would put bytes nobody has verified into the dev
  # bucket — the checksum in the manifest is the only thing that says the
  # fixture is the fixture, so it is checked before anything is written.
  log "Loading $file_count object(s) into s3://$bucket/blobs/ ..."
  local path kind source content_type created_at node_id parent_id parent_prefix
  local expected actual size local_file
  while IFS=$'\t' read -r path kind source content_type created_at; do
    [[ "$kind" == "file" ]] || continue
    node_id="$(derive_node_id "$bucket" "$path")"
    local_file="$workdir/$node_id"
    aws_dev s3 cp "s3://$SEED_BUCKET/$source" "$local_file" --only-show-errors ||
      die "Could not download s3://$SEED_BUCKET/$source, which manifest.json lists."
    expected="$(jq -r --arg k "$source" '.objects[$k].sha256' <<<"$manifest_json")"
    actual="$(sha256_of "$local_file")"
    [[ "$expected" == "$actual" ]] ||
      die "$source does not match its manifest checksum. The fixture is corrupt or has been changed in place; nothing further was written."
    aws_dev s3 cp "$local_file" "s3://$bucket/blobs/$node_id" \
      --content-type "$content_type" --only-show-errors ||
      die "Could not write blobs/$node_id to s3://$bucket/."
  done < <(jq -r '.nodes[] | [.path, .kind, (.source // ""), (.content_type // ""), .created_at] | @tsv' <<<"$catalog_json")
  ok "Fixture bytes loaded."

  # ── 2. the shared material ───────────────────────────────────────────────
  #
  # Pose plates and the phrasebook. Repo-sourced, owned by no library and
  # recorded by no node, so they are not part of the fixture and are pushed the
  # same way `dev-setup.sh` pushes them — one definition, in
  # dev-shared-material.sh.
  local studio_dir="$SCRIPT_DIR/.."
  push_pose_plates "$studio_dir" "$bucket" &&
    ok "Synced studio/config/ -> s3://$bucket/config/" ||
    warn "Could not sync studio/config/; a reference shoot will report missing plates."
  local phrasebook_status=0
  seed_phrasebook "$studio_dir" "$bucket" || phrasebook_status=$?
  case "$phrasebook_status" in
    0) ok "Seeded phrasebook/wording.yaml." ;;
    2) log "phrasebook/wording.yaml is already there; left alone." ;;
    *) warn "Could not seed phrasebook/wording.yaml; 'studio phrasebook add' will fail." ;;
  esac

  # ── 3. the catalog ───────────────────────────────────────────────────────
  log "Writing the catalog to $table ..."
  local items status created=0 skipped=0
  items="$(library_items "$table" "$library_id" "$root_id" "$library_name" \
             "$owner_sub" "$born")"
  ddb_transaction "$table" "$items" && status=0 || status=$?
  [[ "$status" -eq 0 ]] && log "  library, membership and root created" \
    || log "  library, membership and root already there"

  # Nodes in path order, which puts every parent before its children: a
  # parent's path is a proper prefix of its child's, so it always sorts first.
  while IFS=$'\t' read -r path kind source content_type created_at; do
    node_id="$(derive_node_id "$bucket" "$path")"
    # A cheap pre-check, so a re-run reports what it skipped instead of
    # discovering it one cancelled transaction at a time.
    if [[ -n "$(aws_dev dynamodb get-item --table-name "$table" \
                  --key "{\"pk\":{\"S\":\"NODE#$node_id\"},\"sk\":{\"S\":\"META\"}}" \
                  --query 'Item.node_id.S' --output text 2>/dev/null | grep -v '^None$' || true)" ]]; then
      skipped=$((skipped + 1))
      continue
    fi
    parent_prefix="${path%/*}"
    [[ "$parent_prefix" == "$path" ]] && parent_prefix=""
    parent_id="$(derive_node_id "$bucket" "$parent_prefix")"
    size="$(jq -r --arg k "$source" '.objects[$k].size // 0' <<<"$manifest_json")"
    items="$(node_items "$table" "$library_id" "$node_id" "$parent_id" \
               "${path##*/}" "$kind" "$(materialised "$bucket" "$parent_prefix")" \
               "$created_at" "$content_type" "$size")"
    ddb_transaction "$table" "$items" && status=0 || status=$?
    if [[ "$status" -eq 0 ]]; then created=$((created + 1)); else skipped=$((skipped + 1)); fi
  done < <(jq -r '.nodes[] | [.path, .kind, (.source // ""), (.content_type // ""), .created_at] | @tsv' <<<"$catalog_json" | sort)
  ok "Catalog written: $created node(s) created, $skipped already there."

  # ── 4. verify ────────────────────────────────────────────────────────────
  #
  # Against the manifest, and re-read from the DEV bucket rather than from the
  # copies downloaded in step 1 — checking those would only prove the download
  # worked. Counts what the catalog claims, not what the bucket holds: config/
  # and phrasebook/ are in there too and belong to no library.
  log "Verifying against manifest.json ..."
  local verified=0 bytes=0 failures=0
  while IFS=$'\t' read -r path kind source content_type created_at; do
    [[ "$kind" == "file" ]] || continue
    node_id="$(derive_node_id "$bucket" "$path")"
    local_file="$workdir/verify-$node_id"
    if ! aws_dev s3 cp "s3://$bucket/blobs/$node_id" "$local_file" --only-show-errors; then
      warn "  missing: blobs/$node_id  ($path)"
      failures=$((failures + 1))
      continue
    fi
    expected="$(jq -r --arg k "$source" '.objects[$k].sha256' <<<"$manifest_json")"
    actual="$(sha256_of "$local_file")"
    if [[ "$expected" != "$actual" ]]; then
      warn "  checksum: blobs/$node_id  ($path)"
      failures=$((failures + 1))
      continue
    fi
    verified=$((verified + 1))
    bytes=$((bytes + $(jq -r --arg k "$source" '.objects[$k].size' <<<"$manifest_json")))
  done < <(jq -r '.nodes[] | [.path, .kind, (.source // ""), (.content_type // ""), .created_at] | @tsv' <<<"$catalog_json")

  local declared_count declared_bytes
  declared_count="$(jq -r '.object_count' <<<"$manifest_json")"
  declared_bytes="$(jq -r '.total_bytes' <<<"$manifest_json")"
  printf '  objects   %s of %s\n  bytes     %s of %s\n' \
    "$verified" "$declared_count" "$bytes" "$declared_bytes"
  [[ "$failures" -eq 0 && "$verified" -eq "$declared_count" && "$bytes" -eq "$declared_bytes" ]] ||
    die "VERIFY FAILED. The stack is partially seeded; re-run this script — it converges."
  ok "VERIFY PASS."

  printf '\nThe stack is seeded. Start the app with:\n  ./studio/scripts/dev-up.sh\n'
}

# Sourced by the test suite to reach the pure helpers above; run as a script by
# everyone else.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
