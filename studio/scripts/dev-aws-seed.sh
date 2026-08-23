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
# **NEITHER THE BUCKET NOR THE FIXTURE EXISTS YET.** The bucket is declared
# (`infra/modules/dev_seed`, wired into `envs/prod`) and has never been applied;
# nothing has ever been published into it. Until both happen, every run of this
# script stops at the first read and says so. That is the expected outcome
# today, not a fault in your stack.
#
# It is gated on a human, but NOT because publishing generates media — #284 was
# rewritten and `studio dev-seed publish` is a copy out of a dev stack that
# calls no model and costs nothing. What needs a human is the driving: someone
# has to have run the generations, with placeholder names, and then choose which
# six to eight nodes are worth every machine downloading.
#
# ── THE CONTRACT WITH #284 ─────────────────────────────────────────────────
#
# `catalog.json` and `manifest.json` are authoritative in git and copied into
# the bucket for this to read. This script is a loader and validates them
# rather than repairing them: anything malformed is reported and nothing is
# written.
#
# **This contract was one-sided when it was written here and is not any more.**
# `studio dev-seed publish` is the writer, and `pipeline/tests/test_dev_seed.py`
# feeds its output through `fixture_problems` below — so the two halves cannot
# drift without a red test. Neither side had to move to make them agree.
#
#   catalog.json
#     {
#       "version": 2,
#       "library_name": "Studio",
#       "entities": [
#         {"kind": "character", "slug": "<slug>", "root": "<slug>",
#          "display_name": "<Name>", "fictional": true,
#          "default_set": ["<slug>/reference/face/front.png"],
#          "references": [
#            {"node": "<slug>/reference/face/front.png", "group": "face",
#             "order": 1000, "description": "front, neutral", "tags": ["face"]}
#          ]},
#         {"kind": "project", "slug": "<project>", "root": "<project>",
#          "title": "<Title>", "characters": ["<slug>"]}
#       ],
#       "nodes": [
#         {"path": "<project>", "kind": "folder",
#          "created_at": "2026-08-19T09:12:44.000000+00:00"},
#         {"path": "<project>/runs/<run>/request.json",
#          "kind": "file", "source": "v1/media/request.json",
#          "content_type": "application/json",
#          "created_at": "2026-08-19T09:12:44.000001+00:00"}
#       ]
#     }
#
# `path` is the slash-joined chain of NAMES from the library root, and it is how
# a node's parent is expressed — the same encoding `catalog_migrate.py` uses, so
# there is one scheme here and not a second one. Every ancestor folder must
# appear as its own node; the loader will not invent one, because a fixture is
# reviewed in git and a silently-invented folder is a shape nobody chose.
#
# ── `entities`, AND WHY THE PATHS LOST A LEVEL ─────────────────────────────
#
# **`characters/` and `projects/` are not folders any more.** An entity's root
# folder is a child of the LIBRARY root and is named for its slug, so a path
# that used to read `characters/<slug>/reference/…` now reads
# `<slug>/reference/…`. A version-1 fixture would therefore load a library with
# two folders in it called `characters` and `projects` and no entities at all —
# which is why the version moved to 2 rather than the shape being widened
# quietly.
#
# `entities` is what makes a folder a character or a project. Each entry names
# a `root` — a folder path that must also appear in `nodes` — and the loader
# writes the record, its slug claim and the `entity` back-pointer onto that
# folder, adopting it rather than creating one. A character's `references` are
# `REF#` rows, one per entry, naming the reference image by PATH here and by
# node id in the table; a fixture carries no ids, for the reason below.
#
# It is OPTIONAL, and a fixture with no `entities` still loads: the nodes are
# written and nothing owns them. That is a real state — loose material under the
# library root — and refusing it would make the loader stricter than the model.
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
# as `catalog_migrate.py` derives them. So the same fixture on the same stack
# always produces the same library id, the same node ids and therefore the same
# blob keys — re-running rewrites the same objects and skips the rows that are
# already there, rather than creating a second tree beside the first. Two
# machines derive different ids, because the bucket name is in the derivation,
# and that is correct: they are different libraries.
#
# An ENTITY id is derived too, and deliberately not from its slug:
# `uuid5` over `studio://<kind>/<root node id>`, which is what
# `catalog_migrate.entity_id` does and for the same reason — a slug is mutable
# by design, so deriving from one would fork the derivation the first time
# somebody renamed a character between two runs.
#
# ── THE BLOB KEY CARRIES THE OWNER, AND NO NAME ────────────────────────────
#
#   characters/<char id>/<node id>.<ext>     bytes a character owns
#   projects/<proj id>/<node id>.<ext>       bytes a project owns
#   libraries/<lib id>/<node id>.<ext>       bytes under the library root
#
# It was `blobs/<node_id>`, flat. The prefix buys per-entity cost attribution,
# per-entity lifecycle rules and a bulk delete that is one prefix — and it
# carries **no slug**, which is hard rule #1 applied to a bucket listing rather
# than only to the repo.
#
# The owner is the entity whose `root` is the first segment of the node's path,
# and the key is stamped ONCE, here, at creation. Nothing parses it and nothing
# re-derives it; a node later moved to a different owner keeps the key it was
# stamped with, and `studio catalog reseat` is the out-of-band command that
# rewrites the drift.
#
# ── WHAT IT WRITES, IN ORDER ───────────────────────────────────────────────
#
#   1. the fixture bytes  -> s3://<dev bucket>/<owner kind>/<owner id>/<node id>.<ext>
#   2. shared material    -> config/ and phrasebook/wording.yaml
#                            (dev-shared-material.sh, shared with dev-setup.sh)
#   3. the catalog        -> the library, its root node, the owner's membership
#                            row, two items per node, and — for each entry in
#                            `entities` — a record, a slug claim, the `entity`
#                            pointer onto its root folder, and one `REF#` row
#                            per reference
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
# shellcheck source=dev-shared-material.sh
source "$SCRIPT_DIR/dev-shared-material.sh"

SEED_BUCKET="${STUDIO_DEV_SEED_BUCKET:-studio-dev-seed-us-east-1}"
FIXTURE_VERSION="v1"
DRY_RUN=0

# One node per line, tab-separated, read by all three passes below.
#
# **NO FIELD IS EVER EMPTY — absent is written as `-`, and that is a fix.**
# `read` with `IFS=$'\t'` collapses RUNS of tabs, because tab counts as IFS
# whitespace: `p<TAB>folder<TAB>2026<TAB><TAB><TAB>character<TAB><slug>` parses
# as FIVE fields, and `character` lands in `source`. The row then writes a node
# whose owner is a content type.
#
# The old arrangement dodged this by putting the two fields that can be empty
# (`source`, `content_type`) last, on the rule that only trailing fields may
# safely be empty. That rule stopped being enough the moment `owner_kind` and
# `owner_root` joined the row: they can be empty INDEPENDENTLY — a folder has
# no source, material at the library root has no owner — so there are two
# holes and no ordering puts both of them at the end.
#
# A sentinel has no ordering constraint at all. `-` is safe because every field
# it stands in for is a manifest key, a MIME type or a path segment, and none
# of those may be a bare dash. `node_row_fixup` turns it back into "" the
# moment the row is read.
NODE_ROWS_JQ='. as $c
  | (($c.entities // []) | map({key: .root, value: .kind}) | from_entries) as $owners
  | $c.nodes[]
  | (.path | split("/")[0]) as $top
  | [.path, .kind, .created_at, (.source // "-"), (.content_type // "-"),
     ($owners[$top] // "-"), (if $owners[$top] then $top else "-" end)]
  | @tsv'

# One entity per line: kind, slug, root path. Read by the entity pass, and by
# every node that needs to know who owns its bytes.
ENTITY_ROWS_JQ='(.entities // [])[] | [.kind, .slug, .root] | @tsv'

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

node_row_fixup() {
  # Called immediately after each `read` of a NODE_ROWS_JQ line, on the caller's
  # own variables. A folder node carries neither a `source` nor a
  # `content_type` — the fixture validator rejects one that does — so whatever
  # tab-collapsing left in them is noise.
  #
  # First the sentinel, then the kind rule. `-` means "absent" on the wire (see
  # NODE_ROWS_JQ); the second line then re-blanks what a folder may not carry
  # at all, so a fixture that smuggled a `content_type` onto a folder cannot
  # reach the item builder even though the validator already refused it.
  [[ "$source" != "-" ]] || source=""
  [[ "$content_type" != "-" ]] || content_type=""
  [[ "$owner_kind" != "-" ]] || owner_kind=""
  [[ "$owner_root" != "-" ]] || owner_root=""
  [[ "$kind" == "file" ]] || { source=""; content_type=""; }
}

extension_of() {
  # extension_of <path> -> ".png", or "" when the basename carries none.
  #
  # Decoration for a human reading the S3 console: `content_type` on the row is
  # authoritative and the API sets it on every presigned response. It is on the
  # key because a bucket full of extensionless uuids is unreadable, and for no
  # other reason.
  local base="${1##*/}" ext="${1##*.}"
  [[ "$base" == *.* && -n "$ext" && "$ext" != "$base" ]] || { printf ''; return; }
  printf '.%s' "$ext"
}

derive_entity_id() {
  # derive_entity_id <kind> <root node id>
  #
  # `uuid5` over `studio://<kind>/<root node id>` — the derivation
  # `catalog_migrate.entity_id` uses, so the migrator and this loader cannot
  # disagree about who a folder belongs to.
  #
  # **Not derived from the slug**, deliberately. A slug is mutable by design, so
  # a rename between two runs would fork the derivation and the second run would
  # write a second character beside the first.
  local kind="$1" root="$2" prefix
  case "$kind" in
    character) prefix="char" ;;
    project)   prefix="proj" ;;
    *) die "unknown entity kind ${kind@Q}; expected character or project." ;;
  esac
  printf '%s-%s' "$prefix" "$(uuid5_url "studio://$kind/$root")"
}

blob_key_for() {
  # blob_key_for <bucket> <node id> <path> <owner kind> <owner root path>
  #
  # `<owner_kind>/<owner_id>/<node_id>.<ext>`, stamped once and never parsed.
  # Anything owned by no entity sits under `libraries/<lib id>/`, which is a
  # real state rather than a fallback: material at the library root belongs to
  # nobody in particular.
  local bucket="$1" node_id="$2" path="$3" owner_kind="$4" owner_root="$5"
  local ext owner_id
  ext="$(extension_of "$path")"
  if [[ -z "$owner_kind" ]]; then
    printf 'libraries/%s/%s%s' "$(derive_library_id "$bucket")" "$node_id" "$ext"
    return
  fi
  owner_id="$(derive_entity_id "$owner_kind" "$(derive_node_id "$bucket" "$owner_root")")"
  case "$owner_kind" in
    character) printf 'characters/%s/%s%s' "$owner_id" "$node_id" "$ext" ;;
    project)   printf 'projects/%s/%s%s' "$owner_id" "$node_id" "$ext" ;;
  esac
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

        # `entities` is optional — a fixture of loose material under the library
        # root is a real library — but anything it DOES say has to resolve, or
        # the loader would write a record pointing at a folder that is not
        # there and a `REF#` row naming an image nobody can open.
        (($catalog.entities // [])[]
          | select((.kind | IN("character", "project")) | not)
          | "entity \(.slug | tojson): kind must be `character` or `project`"),

        (($catalog.entities // [])[]
          | select((.slug // "") == "" or ((.slug // "") | test("^[a-z0-9][a-z0-9_-]*$") | not))
          | "entity root \(.root | tojson): slug must be lowercase [a-z0-9_-] starting alphanumeric"),

        (($catalog.entities // []) | map(.slug) | group_by(.) | map(select(length > 1) | .[0])[]
          | "two entities claim the slug: \(.)"),

        # `. as $e` before every cross-reference, and it is not style: inside
        # `$folders | index(.root)` the `.` is $folders, so the unbound spelling
        # asks an ARRAY for its `.root` and jq stops the whole program with
        # "Cannot index array with string". Measured, not guessed.
        (($catalog.entities // [])[] | . as $e
          | select((($e.root // "") == "") or ($folders | index($e.root) | not))
          | "entity \($e.slug | tojson): its root \($e.root | tojson) is not a folder node"),

        # A root has to be a TOP-LEVEL folder, because that is where the owner
        # of a blob key is read from: the first segment of the path on a node.
        # An entity rooted deeper would own bytes the key scheme cannot express.
        # (No apostrophes in here — the whole block is one single-quoted jq
        # program, and one would close it mid-expression.)
        (($catalog.entities // [])[]
          | select((.root // "") != "" and ((.root | test("/"))))
          | "entity \(.slug | tojson): its root must be a folder at the library root, not \(.root | tojson)"),


        (($catalog.entities // [])[] | select(.kind == "character")
          | . as $e | (.references // [])[] | . as $ref
          | select($paths | index($ref.node) | not)
          | "\($e.slug): reference \($ref.node | tojson) is not a node in catalog.json"),

        (($catalog.entities // [])[] | select(.kind == "character")
          | . as $e | (.default_set // [])[] | . as $want
          | select([($e.references // [])[].node] | index($want) | not)
          | "\($e.slug): default_set names \($want | tojson), which is not one of its references"),

        (($catalog.entities // [])[] | select(.kind == "project")
          | . as $e | (.characters // [])[] as $slug
          | select([($catalog.entities // [])[] | select(.kind == "character") | .slug] | index($slug) | not)
          | "\($e.slug): involves \($slug | tojson), which is not a character in this fixture"),

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
#
# `ddb` marshals a list as `{"L": …}` and a map as `{"M": …}` now, because an
# entity row is not flat: a character carries `default_set` (a list of node ids)
# and `profile` (a nested map), and a run carries `bindings`. A node row never
# needed either, which is why this started out handling only strings and
# numbers.
DDB_JQ_DEFS='
  def ddb: with_entries(select(.value != null))
    | with_entries(.value |= (
        if type == "number" then {N: (. | tostring)}
        elif type == "boolean" then {BOOL: .}
        elif type == "array" then {L: (map({S: .}))}
        elif type == "object" then {M: (with_entries(.value |= {S: (. | tostring)}))}
        else {S: .} end));
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
  #
  # **`reel` is the sparse key on `by-recent` (D5), and only the META item
  # carries it.** The index is hashed on `reel` rather than on `lib`, so a row
  # without the attribute is simply not in it — which is the point: a folder,
  # an entity row, a `request.json` and a `NAME#` item have no business in a
  # reel of media, and under the old `lib`-hashed index every one of them
  # landed there and was filtered out in memory, consuming the enumeration cap
  # on the way. Written on image and video FILE nodes and nothing else.
  jq -c -n --arg table "$1" --arg lib "$2" --arg node "$3" --arg parent "$4" \
    --arg name "$5" --arg kind "$6" --arg path "$7" --arg created "$8" \
    --arg content_type "$9" --argjson size "${10}" --arg blob_key "${11}" \
    "$DDB_JQ_DEFS"'
    ($kind == "file") as $is_file
    | ($is_file and ($content_type | test("^(image|video)/"))) as $in_reel
    | [ put({pk: "NODE#\($node)", sk: "META", node_id: $node, parent_id: $parent,
             lib: $lib, name: $name, kind: $kind, path: $path,
             created_at: $created, updated_at: $created,
             blob_key: (if $is_file then $blob_key else null end),
             size: (if $is_file then $size else null end),
             content_type: (if $is_file then $content_type else null end),
             reel: (if $in_reel then $lib else null end)}),
        put({pk: "NODE#\($parent)", sk: "NAME#\($name)", node_id: $node,
             lib: $lib, kind: $kind, path: $path, created_at: $created}) ]'
}

entity_items() {
  # entity_items <table> <lib id> <entity id> <kind> <slug> <root node id>
  #              <created at> <entity json>
  #
  # The record, its slug claim, and the `entity` pointer written back onto the
  # root folder — one transaction, because each is useless without the others.
  # A record with no claim is unlistable and its slug is unprotected; a claim
  # with no record points at nothing; a root folder with no pointer cannot be
  # drawn as a character card and `GET /api/nodes/<id>/owner` cannot walk up to
  # it.
  #
  # **The root folder is ADOPTED, not created.** It is already a node — the node
  # pass wrote it — so this is an `Update` that sets one attribute and leaves
  # its name, its parent, its `path` and its stamps alone. Creating a second
  # folder would give the entity a root nobody browses.
  #
  # The claim is `attribute_not_exists(pk)`, which is how DynamoDB is told a
  # slug is unique in a library: uniqueness is enforceable on a primary key and
  # on nothing else, so it has to be part of one. A GSI would give the listing
  # and enforce nothing — two records with the same slug would both land in it,
  # silently.
  local table="$1" lib="$2" entity="$3" kind="$4" slug="$5" root="$6" born="$7"
  local doc="$8" pk claim_sk
  case "$kind" in
    character) pk="CHAR"; claim_sk="CHARSLUG" ;;
    project)   pk="PROJ"; claim_sk="PROJSLUG" ;;
    *) die "unknown entity kind ${kind@Q}." ;;
  esac
  jq -c -n --arg table "$table" --arg lib "$lib" --arg entity "$entity" \
    --arg pk "$pk" --arg claim_sk "$claim_sk" --arg slug "$slug" \
    --arg root "$root" --arg born "$born" --argjson doc "$doc" \
    "$DDB_JQ_DEFS"'
    [ put(({pk: "\($pk)#\($entity)", sk: "META", lib: $lib, slug: $slug,
            rev: 1, created: $born, updated: $born, root: $root} + $doc)),
      put({pk: "LIB#\($lib)", sk: "\($claim_sk)#\($slug)",
           entity: $entity, created: $born}),
      {Update: {TableName: $table,
                Key: ({pk: "NODE#\($root)", sk: "META"} | ddb),
                UpdateExpression: "SET #entity = :entity",
                ExpressionAttributeNames: {"#entity": "entity"},
                ExpressionAttributeValues: ({":entity": $entity} | ddb),
                ConditionExpression: "attribute_exists(pk)"}} ]'
}

reference_items() {
  # reference_items <table> <lib id> <char id> <created at> <references json>
  #
  # One `REF#` row per reference image, keyed on the NODE ID rather than on the
  # filename. That is what kills filename magic: `order` is an attribute so a
  # reorder is one write and `curate renumber` has nothing to maintain, `group`
  # is an attribute so a regroup moves no object, and the image can be called
  # anything and renamed freely.
  #
  # `order` is gapped by 1000 when the fixture does not say, so an insert
  # between two entries is one write and never touches a neighbour.
  jq -c -n --arg table "$1" --arg lib "$2" --arg char "$3" --arg born "$4" \
    --argjson refs "$5" \
    "$DDB_JQ_DEFS"'
    [ $refs | to_entries[]
      | put({pk: "CHAR#\($char)", sk: "REF#\(.value.node)", lib: $lib,
             group: (.value.group // "unsorted"),
             order: (.value.order // ((.key + 1) * 1000)),
             description: (.value.description // ""),
             tags: (.value.tags // []),
             created: (.value.created // $born)}) ]'
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
  log "Loading $file_count object(s) into s3://$bucket/ ..."
  local path kind created_at source content_type owner_kind owner_root
  local node_id parent_id parent_prefix blob_key
  local expected actual size local_file
  while IFS=$'\t' read -r path kind created_at source content_type owner_kind owner_root; do
    node_row_fixup
    [[ "$kind" == "file" ]] || continue
    node_id="$(derive_node_id "$bucket" "$path")"
    blob_key="$(blob_key_for "$bucket" "$node_id" "$path" "$owner_kind" "$owner_root")"
    local_file="$workdir/$node_id"
    aws_dev s3 cp "s3://$SEED_BUCKET/$source" "$local_file" --only-show-errors ||
      die "Could not download s3://$SEED_BUCKET/$source, which manifest.json lists."
    expected="$(jq -r --arg k "$source" '.objects[$k].sha256' <<<"$manifest_json")"
    actual="$(sha256_of "$local_file")"
    [[ "$expected" == "$actual" ]] ||
      die "$source does not match its manifest checksum. The fixture is corrupt or has been changed in place; nothing further was written."
    aws_dev s3 cp "$local_file" "s3://$bucket/$blob_key" \
      --content-type "$content_type" --only-show-errors ||
      die "Could not write $blob_key to s3://$bucket/."
  done < <(jq -r "$NODE_ROWS_JQ" <<<"$catalog_json")
  ok "Fixture bytes loaded."

  # ── 2. the shared material ───────────────────────────────────────────────
  #
  # The pose plates. Repo-sourced and owned by no entity, so they are not part
  # of the fixture and are pushed the same way `dev-setup.sh` pushes them — one
  # definition, in dev-shared-material.sh. They are nodes now, so this goes
  # through the API and needs a sign-in; the phrasebook is `TERM#` rows and is
  # not seeded at all.
  local studio_dir="$SCRIPT_DIR/.."
  push_pose_plates "$studio_dir" "$bucket" &&
    ok "Pose plates are in the library." ||
    warn "Could not push studio/config/; a reference shoot will report missing plates."

  # ── 3. the catalog ───────────────────────────────────────────────────────
  log "Writing the catalog to $table ..."
  local items status created=0 skipped=0 node_id_lookup
  items="$(library_items "$table" "$library_id" "$root_id" "$library_name" \
             "$owner_sub" "$born")"
  ddb_transaction "$table" "$items" && status=0 || status=$?
  [[ "$status" -eq 0 ]] && log "  library, membership and root created" \
    || log "  library, membership and root already there"

  # A fixture names a reference and a hero by PATH, because it carries no ids —
  # ids are derived per stack, so a published id would be an id from somebody
  # else's stack. This is the one map from the one to the other, built with the
  # same derivation the node pass uses so the two cannot disagree.
  node_id_lookup="$(while IFS=$'\t' read -r path kind created_at source content_type owner_kind owner_root; do
      printf '%s\t%s\n' "$path" "$(derive_node_id "$bucket" "$path")"
    done < <(jq -r "$NODE_ROWS_JQ" <<<"$catalog_json") \
    | jq -R -s 'split("\n") | map(select(length > 0) | split("\t"))
                | map({key: .[0], value: .[1]}) | from_entries')"

  # Nodes in path order, which puts every parent before its children: a
  # parent's path is a proper prefix of its child's, so it always sorts first.
  while IFS=$'\t' read -r path kind created_at source content_type owner_kind owner_root; do
    node_row_fixup
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
               "$created_at" "$content_type" "$size" \
               "$(blob_key_for "$bucket" "$node_id" "$path" "$owner_kind" "$owner_root")")"
    ddb_transaction "$table" "$items" && status=0 || status=$?
    if [[ "$status" -eq 0 ]]; then created=$((created + 1)); else skipped=$((skipped + 1)); fi
  done < <(jq -r "$NODE_ROWS_JQ" <<<"$catalog_json" | sort)
  ok "Catalog written: $created node(s) created, $skipped already there."

  # ── 3b. the entities ─────────────────────────────────────────────────────
  #
  # After the nodes, and that ordering is the safety property: an entity ADOPTS
  # its root folder with a conditional `attribute_exists(pk)` update, so the
  # folder has to be there first. Doing it the other way round would either
  # fail every time or tempt the loader into creating a folder the fixture did
  # not describe.
  local entity_kind entity_slug entity_root entity_root_id entity_id doc refs
  local entities_created=0 entities_skipped=0 refs_created=0
  while IFS=$'\t' read -r entity_kind entity_slug entity_root; do
    [[ -n "$entity_kind" ]] || continue
    entity_root_id="$(derive_node_id "$bucket" "$entity_root")"
    entity_id="$(derive_entity_id "$entity_kind" "$entity_root_id")"
    # The half of the record that differs by kind, built in jq so the fixture
    # can carry a nested `profile` map or a `default_set` list without this
    # script learning either shape. Reference PATHS become node ids here —
    # a fixture carries no ids, because ids are derived per stack.
    doc="$(jq -c --arg kind "$entity_kind" --arg slug "$entity_slug" \
             --arg bucket "$bucket" --argjson lookup "$node_id_lookup" '
        (.entities[] | select(.slug == $slug and .kind == $kind)) as $e
        | if $kind == "character" then
            {display_name: ($e.display_name // $slug),
             fictional: ($e.fictional // true),
             schema_version: ($e.schema_version // 2),
             hero: ($e.hero // null | if . then $lookup[.] else null end),
             default_set: [($e.default_set // [])[] | $lookup[.]],
             profile: ($e.profile // {})}
          else
            {title: ($e.title // ""), description: ($e.description // ""),
             hero: ($e.hero // null | if . then $lookup[.] else null end),
             counts: ($e.counts // {})}
          end' <<<"$catalog_json")"
    items="$(entity_items "$table" "$library_id" "$entity_id" "$entity_kind" \
               "$entity_slug" "$entity_root_id" "$born" "$doc")"
    ddb_transaction "$table" "$items" && status=0 || status=$?
    if [[ "$status" -eq 0 ]]; then
      entities_created=$((entities_created + 1))
    else
      entities_skipped=$((entities_skipped + 1))
      continue
    fi
    [[ "$entity_kind" == "character" ]] || continue
    refs="$(jq -c --arg slug "$entity_slug" --argjson lookup "$node_id_lookup" '
        [ (.entities[] | select(.slug == $slug and .kind == "character")
           | (.references // [])[])
          | . + {node: $lookup[.node]} ]' <<<"$catalog_json")"
    [[ "$(jq 'length' <<<"$refs")" -gt 0 ]] || continue
    items="$(reference_items "$table" "$library_id" "$entity_id" "$born" "$refs")"
    ddb_transaction "$table" "$items" && status=0 || status=$?
    [[ "$status" -eq 0 ]] && refs_created=$((refs_created + $(jq 'length' <<<"$refs")))
  done < <(jq -r "$ENTITY_ROWS_JQ" <<<"$catalog_json")
  if [[ "$entities_created" -gt 0 || "$entities_skipped" -gt 0 ]]; then
    ok "Entities written: $entities_created created ($refs_created reference row(s)), $entities_skipped already there."
  else
    log "The fixture describes no entities; its nodes are loose under the library root."
  fi

  # ── 4. verify ────────────────────────────────────────────────────────────
  #
  # Against the manifest, and re-read from the DEV bucket rather than from the
  # copies downloaded in step 1 — checking those would only prove the download
  # worked. Counts what the catalog claims, not what the bucket holds: config/
  # and phrasebook/ are in there too and belong to no library.
  log "Verifying against manifest.json ..."
  local verified=0 bytes=0 failures=0
  while IFS=$'\t' read -r path kind created_at source content_type owner_kind owner_root; do
    node_row_fixup
    [[ "$kind" == "file" ]] || continue
    node_id="$(derive_node_id "$bucket" "$path")"
    blob_key="$(blob_key_for "$bucket" "$node_id" "$path" "$owner_kind" "$owner_root")"
    local_file="$workdir/verify-$node_id"
    if ! aws_dev s3 cp "s3://$bucket/$blob_key" "$local_file" --only-show-errors; then
      warn "  missing: $blob_key  ($path)"
      failures=$((failures + 1))
      continue
    fi
    expected="$(jq -r --arg k "$source" '.objects[$k].sha256' <<<"$manifest_json")"
    actual="$(sha256_of "$local_file")"
    if [[ "$expected" != "$actual" ]]; then
      warn "  checksum: $blob_key  ($path)"
      failures=$((failures + 1))
      continue
    fi
    verified=$((verified + 1))
    bytes=$((bytes + $(jq -r --arg k "$source" '.objects[$k].size' <<<"$manifest_json")))
  done < <(jq -r "$NODE_ROWS_JQ" <<<"$catalog_json")

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
