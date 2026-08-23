"""The dev-stack shell scripts, checked from the suite that actually runs.

`studio/scripts/` belongs to neither half of studio and has no suite of its own,
so it is checked here — the pipeline suite is the one CI runs for the local half,
and `studio-pr.yml`'s path filter names `studio/scripts/**` so a change to a
script runs these.

**Nothing here touches AWS.** Every test either reads a script's source or
sources it and calls a function that reads and writes nothing. The one thing
these cannot do is run `dev-aws-seed.sh` end to end: the fixture it loads is
#284, which is human-gated because it generates media, and the seed bucket does
not exist yet.
"""

import json
import re
import subprocess
import uuid

import pytest

from studio_pipeline import STUDIO_DIR
from studio_pipeline.maintenance import catalog_migrate

SCRIPTS = STUDIO_DIR / "scripts"
SEED = SCRIPTS / "dev-aws-seed.sh"
SHARED = SCRIPTS / "dev-shared-material.sh"

BUCKET = "studio-dev-abc123456789-media-us-east-1"


def _source_and_run(script, snippet: str) -> str:
    """Source a script and run `snippet` against its functions.

    Safe because both scripts define their functions before doing anything:
    `dev-aws-seed.sh` puts its body in `main` behind a `BASH_SOURCE` guard for
    exactly this, and `dev-shared-material.sh` is sourced-only by design.
    """
    result = subprocess.run(
        ["bash", "-c", f'source "{script}"\n{snippet}'],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def _code_lines(path) -> str:
    """A script with its comment lines removed.

    Whole-line comments only. A trailing comment on a command line stays, which
    is the conservative direction: this is used to look for things that must not
    be there, so keeping too much can only produce a false failure.
    """
    return "\n".join(line for line in path.read_text().splitlines()
                     if not line.lstrip().startswith("#"))


# ── the money pin ───────────────────────────────────────────────────────────
#
# #285: "This script must never be able to spend money. It does not generate. It
# does not call Replicate. It requires no REPLICATE_API_TOKEN. … That is a
# property worth pinning with a test rather than a comment: a setup script that
# can bill you is a bad setup script."


def test_dev_aws_seed_cannot_reach_a_model_provider():
    """**The pin, and it is a grep. Read what it does not catch.**

    It scans the executable lines of one file for the names of things that cost
    money to call, and for the interpreters that would let this script hand the
    job to something else.

    WHAT IT CATCHES: someone adding a generation step to this script directly —
    a provider's name, a token, a curl, or a shell-out to Python or to the
    `studio` CLI, which is where every paid call in this repo lives.

    WHAT IT DOES NOT CATCH, and none of these are hypothetical enough to ignore:

    - **Anything reached indirectly.** A command built in a variable, an `eval`,
      or a paid call added to `dev-aws-common.sh` or `dev-shared-material.sh`,
      which this file sources. Text in one file says nothing about what another
      one does.
    - **What a command does at runtime.** This is a scan of source, not an
      execution or a network sandbox. `aws` is allowed here and `aws` can be
      made to cost money.
    - **AWS's own charges.** S3 GETs, PUTs and DynamoDB writes cost fractions of
      a cent, and this script performs all three. The property is "no model
      inference is billed", not "zero spend".

    A network-denied integration run would catch the first two. It would also
    need the fixture, which does not exist yet (#284), so this is what there is.
    """
    code = _code_lines(SEED).lower()

    for token, why in [
        ("replicate", "the model provider — a generation here would bill on every setup"),
        ("openai", "a model provider"),
        ("anthropic", "a model provider"),
        ("api_token", "a provider credential has no business in a setup script"),
        ("api_key", "a provider credential has no business in a setup script"),
        ("curl", "no HTTP call — everything here goes through the AWS CLI"),
        ("wget", "no HTTP call — everything here goes through the AWS CLI"),
        ("uv run", "the pipeline is where the paid commands live"),
        ("python", "the pipeline is where the paid commands live"),
    ]:
        assert token not in code, f"{SEED.name} names {token!r}: {why}"

    # The `studio` CLI at a command position. Not a bare substring: the script
    # legitimately says `./studio/scripts/dev-user.sh` and `$studio_dir`.
    invocation = re.compile(r"(?:^|[;&|]|\$\()\s*studio\s", re.MULTILINE)
    assert not invocation.search(_code_lines(SEED)), (
        f"{SEED.name} invokes the studio CLI; every paid command in this repo is one"
    )


def test_no_dev_aws_script_names_the_provider_token():
    """The whole family, comments included — a token it cannot name it cannot read.

    Wider than the test above and weaker: it is one string. It is here because
    `dev-aws-setup.sh` calls into this family, so the property has to hold for
    more than the one script that would do the spending.
    """
    for script in sorted(SCRIPTS.glob("dev-aws-*.sh")):
        assert "REPLICATE_API_TOKEN" not in script.read_text(), script.name


def test_dev_aws_seed_destroys_nothing():
    """A seed converges a stack. Emptying one is `dev-aws-reset.sh`.

    Same shape of check and the same limits: it reads source, so it catches the
    line someone adds here and not a delete reached through something else.
    """
    code = _code_lines(SEED)
    for token in ("s3 rm", "s3 rb", "delete-object", "delete-table",
                  "delete-item", "admin-delete-user", "delete-user-pool",
                  "terraform destroy", "terraform apply"):
        assert token not in code, f"{SEED.name} runs {token!r}, which a seed must not"


def test_the_pose_plate_sync_can_never_delete():
    """`--delete` would remove whatever a fixture put under `config/`.

    The comment in `dev-shared-material.sh` says never; this is what makes it
    true after someone edits the line.
    """
    assert "--delete" not in _code_lines(SHARED)


# ── the ids, against the Python that derives them the same way ──────────────


@pytest.mark.parametrize("name", [
    "",
    "s3://bucket",
    "s3://bucket/",
    "s3://bucket/projects/subject-a/runs/2026-08-04_21-30-54_wave-porch/request.json",
    "s3://bucket/UPPER.PNG",
    "s3://bucket/ünïcødé — a deliberately awkward name",
])
def test_bash_uuid5_matches_python(name):
    """The seed script reimplements uuid5 in bash; this is why that is allowed.

    It must not shell out to Python — a `python` in a setup script is what the
    money test forbids, and the pipeline's environment may not be installed on a
    machine being provisioned. So the derivation exists twice, and this is what
    stops the two from drifting.
    """
    got = _source_and_run(SEED, f'uuid5_url "{name}"')
    assert got == str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def test_derived_entity_ids_match_the_migrator():
    """**The one derivation that still exists on both sides, so it is the one pinned.**

    This test used to compare the bash loader against `catalog_seed`, which
    derived library ids, node ids and materialised `path` values in Python too.
    That command is gone: the catalog seed inventoried a bucket that had no
    rows, and every library has rows now. The loader is therefore the ONLY
    writer of node rows left, and there is no Python twin to compare it to —
    asserting the schema directly (below) is what replaced that comparison.

    An entity id is different: `catalog_migrate.entity_id` derives one when it
    raises entity rows over an existing library, and the loader derives one when
    it seeds a fixture. Both must land on `uuid5` over
    `studio://<kind>/<root node id>` or a migrated stack and a seeded stack
    would disagree about who owns a folder.

    Note what is NOT in the derivation: the slug. It is mutable by design, so
    deriving from one would fork the derivation the first time a character was
    renamed between two runs.
    """
    for kind in ("character", "project"):
        for root in ("node-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "node-root"):
            assert (_source_and_run(SEED, f'derive_entity_id "{kind}" "{root}"')
                    == catalog_migrate.entity_id(kind, root))


def test_an_unknown_entity_kind_is_refused_rather_than_prefixed():
    """A third kind would silently produce a `-<uuid>` id with no prefix."""
    result = subprocess.run(
        ["bash", "-c", f'source "{SEED}"\nderive_entity_id sculpture node-root'],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "unknown entity kind" in result.stderr


# ── the items, against the schema itself ────────────────────────────────────
#
# **These used to compare the bash items attribute-for-attribute against
# `catalog_seed.meta_item` / `index_item`.** That Python twin is gone with the
# catalog seed, so the comparison would now be against nothing. What replaced it
# is an explicit statement of the schema — which is weaker in one way (two
# writers can no longer be diffed) and stronger in another: the expected item is
# written out here in full, so a reviewer can read what the loader writes
# without holding a second module in their head.
#
# The type mapping is still the thing most worth pinning. `size` as `{"S": …}`
# instead of `{"N": …}` is exactly the mistake a hand-written attribute map
# makes, and it makes a row that sorts and compares wrong rather than one that
# fails.


def _items(snippet: str) -> list[dict]:
    return json.loads(_source_and_run(SEED, snippet))


def test_a_file_node_is_written_as_the_two_items_the_schema_describes():
    """Two items, one transaction, and the `NAME#` one deliberately narrow.

    A node that exists under one key and not the other either cannot be listed
    or cannot be opened. The listing item carries `node_id, lib, kind, path,
    created_at` and nothing else, because `size` and `content_type` are mutable
    and duplicating them would put every rename, move and text edit in the
    business of keeping two copies in step.
    """
    actions = _items(
        'node_items tbl lib-1 node-a node-p "a.PNG" file "/node-root/node-p/" '
        '"2026-08-19T09:12:44.000001+00:00" "image/png" 1234 '
        '"characters/char-1/node-a.PNG"'
    )

    assert [a["Put"]["ConditionExpression"] for a in actions] == \
        ["attribute_not_exists(pk)"] * 2
    assert actions[0]["Put"]["Item"] == {
        "pk": {"S": "NODE#node-a"}, "sk": {"S": "META"},
        "node_id": {"S": "node-a"}, "parent_id": {"S": "node-p"},
        "lib": {"S": "lib-1"}, "name": {"S": "a.PNG"}, "kind": {"S": "file"},
        "path": {"S": "/node-root/node-p/"},
        "created_at": {"S": "2026-08-19T09:12:44.000001+00:00"},
        "updated_at": {"S": "2026-08-19T09:12:44.000001+00:00"},
        "blob_key": {"S": "characters/char-1/node-a.PNG"},
        "size": {"N": "1234"}, "content_type": {"S": "image/png"},
        "reel": {"S": "lib-1"},
    }
    assert actions[1]["Put"]["Item"] == {
        "pk": {"S": "NODE#node-p"}, "sk": {"S": "NAME#a.PNG"},
        "node_id": {"S": "node-a"}, "lib": {"S": "lib-1"},
        "kind": {"S": "file"}, "path": {"S": "/node-root/node-p/"},
        "created_at": {"S": "2026-08-19T09:12:44.000001+00:00"},
    }


@pytest.mark.parametrize("content_type, in_the_reel", [
    ("image/png", True),
    ("video/mp4", True),
    ("application/json", False),
    ("text/plain; charset=utf-8", False),
    ("application/yaml", False),
])
def test_only_images_and_videos_carry_the_reel_key(content_type, in_the_reel):
    """**D5, and it is a sparse index, so the attribute IS the membership.**

    `by-recent` is hashed on `reel` rather than on `lib`, so a row without the
    attribute is simply not in the index. That is what fixes the pollution the
    re-key was introduced for: under the `lib`-hashed index every folder, every
    `request.json` and every `NAME#` item landed in the reel's enumeration and
    was filtered out in memory, consuming the `max_folder_objects` cap on the
    way.

    Cross-checked against `catalog_migrate.in_the_reel`, which makes the same
    decision on the migration side. The two writers agreeing is the point —
    a stack seeded from a fixture and a stack raised by the migrator must put
    the same rows in the reel.
    """
    actions = _items(
        f'node_items tbl lib-1 node-a node-p "a" file "/r/" "2026" '
        f'"{content_type}" 12 "libraries/lib-1/node-a"'
    )
    item = actions[0]["Put"]["Item"]

    assert ("reel" in item) is in_the_reel
    assert catalog_migrate.in_the_reel(
        {"kind": "file", "content_type": content_type}) is in_the_reel
    if in_the_reel:
        # The VALUE is the library id: the index is hashed on it, so every
        # image and video in one library shares a partition and the reel is one
        # query rather than a scan.
        assert item["reel"] == {"S": "lib-1"}


def test_a_folder_node_is_never_in_the_reel_and_carries_no_blob():
    """Absent, not null. `attribute_not_exists` is what a NULL would defeat."""
    actions = _items(
        'node_items tbl lib-1 node-f node-root "<slug>" folder "/node-root/" '
        '"2026-08-19T09:12:44.000001+00:00" "" 0 ""'
    )

    item = actions[0]["Put"]["Item"]
    for absent in ("blob_key", "size", "content_type", "reel"):
        assert absent not in item


@pytest.mark.parametrize("path, owner_kind, owner_root, expected_prefix", [
    ("<slug>/reference/face/front.png", "character", "<slug>", "characters/char-"),
    ("<project>/runs/one/out.mp4", "project", "<project>", "projects/proj-"),
    ("loose.png", "", "", "libraries/lib-"),
])
def test_a_blob_key_carries_the_owner_the_node_and_no_name(
        path, owner_kind, owner_root, expected_prefix):
    """**A bucket listing stops leaking hard rule #1.**

    `<owner_kind>/<owner_id>/<node_id>.<ext>`. The extension is decoration for
    a human reading the console — `content_type` on the row is authoritative —
    and nothing else in the key is derivable from a name. The old scheme was
    `blobs/<node_id>` flat, which leaked nothing either but gave no per-entity
    cost attribution, no per-entity lifecycle rule and no bulk delete that is
    one prefix.

    Material under the library root belongs to nobody in particular and sits
    under `libraries/<lib id>/`. That is a real state, not a fallback.
    """
    node_id = _source_and_run(SEED, f'derive_node_id "{BUCKET}" "{path}"')
    key = _source_and_run(
        SEED, f'blob_key_for "{BUCKET}" "{node_id}" "{path}" "{owner_kind}" "{owner_root}"')

    assert key.startswith(expected_prefix)
    assert key.endswith(f"/{node_id}.{path.rsplit('.', 1)[1]}")
    for leak in ("<slug>", "<project>", "reference", "runs", "face"):
        assert leak not in key


def test_a_blob_key_with_no_extension_is_still_well_formed():
    """A name may carry none; the key is a pointer and does not require one."""
    node_id = _source_and_run(SEED, f'derive_node_id "{BUCKET}" "notes"')
    key = _source_and_run(SEED, f'blob_key_for "{BUCKET}" "{node_id}" "notes" "" ""')
    assert key.endswith(f"/{node_id}")


def test_an_entity_is_a_record_a_claim_and_an_adoption():
    """Three actions, one transaction, and each is useless without the others.

    A record with no claim is unlistable and its slug is unprotected; a claim
    with no record points at nothing; a root folder with no `entity` pointer
    cannot be drawn as a character card and `GET /api/nodes/<id>/owner` has
    nothing to walk up to.

    **The root folder is ADOPTED, not created** — an `Update` that sets one
    attribute on a node the node pass already wrote. Creating a second folder
    would give the entity a root nobody browses.
    """
    actions = _items(
        'entity_items tbl lib-1 char-1 character "<slug>" node-root "2026" '
        "'{\"display_name\":\"<Name>\",\"fictional\":true,"
        '"default_set":["node-x"],"profile":{"identity":"<one line>"}}\''
    )

    record = actions[0]["Put"]["Item"]
    assert record["pk"] == {"S": "CHAR#char-1"} and record["sk"] == {"S": "META"}
    assert record["rev"] == {"N": "1"}
    assert record["root"] == {"S": "node-root"}
    # A list and a nested map, which a node row never needed — this is why the
    # marshaller had to learn `L` and `M`.
    assert record["default_set"] == {"L": [{"S": "node-x"}]}
    assert record["profile"] == {"M": {"identity": {"S": "<one line>"}}}
    assert record["fictional"] == {"BOOL": True}

    claim = actions[1]["Put"]["Item"]
    assert claim == {"pk": {"S": "LIB#lib-1"}, "sk": {"S": "CHARSLUG#<slug>"},
                     "entity": {"S": "char-1"}, "created": {"S": "2026"}}
    # Uniqueness is enforceable on a primary key and on nothing else, which is
    # why the claim exists at all rather than a GSI over the record.
    assert actions[1]["Put"]["ConditionExpression"] == "attribute_not_exists(pk)"

    adopt = actions[2]["Update"]
    assert adopt["Key"] == {"pk": {"S": "NODE#node-root"}, "sk": {"S": "META"}}
    assert adopt["ConditionExpression"] == "attribute_exists(pk)"
    assert adopt["ExpressionAttributeValues"] == {":entity": {"S": "char-1"}}


def test_a_project_claims_its_slug_in_a_different_namespace():
    """`CHARSLUG#` and `PROJSLUG#` — which is what lets a character and a
    project be called the same thing, settled by the command rather than by the
    library."""
    actions = _items(
        'entity_items tbl lib-1 proj-1 project "<slug>" node-root "2026" '
        "'{\"title\":\"<Title>\"}'"
    )
    assert actions[0]["Put"]["Item"]["pk"] == {"S": "PROJ#proj-1"}
    assert actions[1]["Put"]["Item"]["sk"] == {"S": "PROJSLUG#<slug>"}


def test_reference_rows_are_gapped_by_a_thousand():
    """**This is what kills filename magic.**

    `order` is an attribute, so `curate renumber` has nothing to maintain and a
    reorder is one write. The gap means inserting between two entries never
    touches a neighbour. The row names a NODE ID, so the image it describes can
    be called anything and renamed freely.
    """
    actions = _items(
        'reference_items tbl lib-1 char-1 "2026" '
        "'[{\"node\":\"node-x\",\"group\":\"face\",\"tags\":[\"face\"],"
        '"description":"front"},{"node":"node-y","group":"body"}]\''
    )

    assert [a["Put"]["Item"]["sk"]["S"] for a in actions] == \
        ["REF#node-x", "REF#node-y"]
    assert [a["Put"]["Item"]["order"]["N"] for a in actions] == ["1000", "2000"]
    assert actions[0]["Put"]["Item"]["tags"] == {"L": [{"S": "face"}]}
    # An undescribed reference is an ordinary state — it just cannot be picked
    # by tag and is invisible to whoever chooses the set.
    assert actions[1]["Put"]["Item"]["description"] == {"S": ""}


def test_the_root_is_one_item_with_no_parent_and_no_name():
    """#280: a `NAME#` item pairs a name with a parent, and the root has neither."""
    actions = _items(
        'library_items tbl lib-1 node-root "Studio" sub-9 '
        '"2026-08-19T09:12:44.000000+00:00"'
    )

    assert [a["Put"]["Item"]["pk"]["S"] for a in actions] == \
        ["LIB#lib-1", "USER#sub-9", "NODE#node-root"]
    root = actions[2]["Put"]["Item"]
    assert root["sk"] == {"S": "META"}
    assert root["path"] == {"S": "/"}
    assert "parent_id" not in root and "name" not in root
    # The library root is a folder and holds no media of its own, so it is not
    # in the reel either.
    assert "reel" not in root
    assert actions[1]["Put"]["Item"]["role"] == {"S": "owner"}


# ── the fixture contract ────────────────────────────────────────────────────

# A version-2 fixture: entity roots are children of the LIBRARY root, so there
# is no `projects/` folder in the paths any more. A version-1 fixture would load
# a library holding two folders literally called `characters` and `projects`,
# owned by nobody — which is why the version moved rather than the shape being
# widened quietly.
GOOD_CATALOG = {
    "version": 2,
    "library_name": "Studio",
    "entities": [
        {"kind": "character", "slug": "subject-a", "root": "subject-a",
         "display_name": "<Name>", "fictional": True,
         "default_set": ["subject-a/reference/a.PNG"],
         "references": [{"node": "subject-a/reference/a.PNG", "group": "face",
                         "description": "front, neutral", "tags": ["face"]}]},
        {"kind": "project", "slug": "porch-teaser", "root": "porch-teaser",
         "title": "<Title>", "characters": ["subject-a"]},
    ],
    "nodes": [
        {"path": "subject-a", "kind": "folder",
         "created_at": "2026-08-19T09:12:44.000000+00:00"},
        {"path": "subject-a/reference", "kind": "folder",
         "created_at": "2026-08-19T09:12:44.000001+00:00"},
        {"path": "subject-a/reference/a.PNG", "kind": "file",
         "source": "v1/media/a.png", "content_type": "image/png",
         "created_at": "2026-08-19T09:12:44.000002+00:00"},
        {"path": "porch-teaser", "kind": "folder",
         "created_at": "2026-08-19T09:12:44.000003+00:00"},
    ],
}
GOOD_MANIFEST = {
    "version": "v1", "object_count": 1, "total_bytes": 10,
    "objects": {"v1/media/a.png": {"size": 10, "sha256": "ab" * 32}},
}


def _problems(catalog: dict, manifest: dict) -> str:
    return _source_and_run(SEED, (
        f"fixture_problems {json.dumps(json.dumps(catalog))} "
        f"{json.dumps(json.dumps(manifest))}"
    ))


def test_a_well_formed_fixture_has_no_problems():
    assert _problems(GOOD_CATALOG, GOOD_MANIFEST) == ""


@pytest.mark.parametrize("mutate, expected", [
    (lambda c, m: c["nodes"].append(dict(c["nodes"][0])), "duplicate path"),
    (lambda c, m: c["nodes"][0].pop("created_at"), "no `created_at`"),
    (lambda c, m: c["nodes"].__setitem__(0, {**c["nodes"][0], "kind": "blob"}),
     "kind must be"),
    (lambda c, m: c["nodes"].pop(1), "its parent folder is not a node"),
    # The entity half of the contract. Optional as a whole, but anything it
    # DOES say has to resolve — a record pointing at a folder that is not there,
    # or a `REF#` row naming an image nobody can open, is a library that looks
    # seeded and is broken.
    (lambda c, m: c["entities"][0].update(root="not-a-folder"),
     "is not a folder node"),
    (lambda c, m: c["entities"][0].update(kind="sculpture"), "kind must be"),
    (lambda c, m: c["entities"][1].update(slug="Porch Teaser"),
     "slug must be lowercase"),
    (lambda c, m: c["entities"][1].update(slug="subject-a"),
     "two entities claim the slug"),
    (lambda c, m: c["entities"][0]["references"][0].update(node="subject-a/gone.png"),
     "is not a node in catalog.json"),
    (lambda c, m: c["entities"][0].update(default_set=["subject-a/gone.png"]),
     "default_set names"),
    (lambda c, m: c["entities"][1].update(characters=["subject-z"]),
     "which is not a character in this fixture"),
    (lambda c, m: c["entities"][0].update(root="subject-a/reference"),
     "must be a folder at the library root"),
    (lambda c, m: c["nodes"][2].pop("content_type"), "needs a `content_type`"),
    (lambda c, m: c["nodes"][2].update(source="v1/media/gone.png"),
     "is not in manifest.json"),

    (lambda c, m: m["objects"].update({"v1/media/spare.png": {"size": 1, "sha256": "cd"}}),
     "claimed by no node"),
    (lambda c, m: m.update(object_count=9), "object_count is 9"),
    (lambda c, m: m.update(total_bytes=9), "total_bytes is 9"),
    (lambda c, m: c["nodes"][2].update(path="subject-a/reference/../a.PNG"),
     "unusable name"),
])
def test_a_malformed_fixture_is_reported_before_anything_is_written(mutate, expected):
    """Every reason at once, not the first.

    A fixture is fixed by editing it in git and re-publishing (#284), so a list
    is one round trip where a stop-at-first is as many as there are mistakes.
    `catalog_seed.plan` collects `unmapped` for the same reason.
    """
    catalog = json.loads(json.dumps(GOOD_CATALOG))
    manifest = json.loads(json.dumps(GOOD_MANIFEST))
    mutate(catalog, manifest)

    assert expected in _problems(catalog, manifest)


# ── the shared material, with a stub in place of the AWS CLI ────────────────


def _push_plates(has_studio: bool) -> tuple[int, list[str]]:
    """Run `push_pose_plates` with a fake `studio` on PATH, and report its calls."""
    presence = "" if has_studio else "command() { return 1; }\n    "
    script = f"""
    set -euo pipefail
    fake_studio() {{
      printf '%s\\n' "$*" >&2
      return 0
    }}
    {presence}SHARED_MATERIAL_STUDIO=(fake_studio)
    source "{SHARED}"
    push_pose_plates "{STUDIO_DIR}" a-dev-bucket
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return result.returncode, result.stderr.splitlines()


def test_the_plates_are_pushed_through_the_cli_not_the_bucket():
    """**The push writes rows, so it cannot be an `aws s3 sync`.**

    `check_plates` resolves each plate as a name path, so a plate needs a node,
    and only the API writes one. This script pushed objects with `aws s3 sync`
    for as long as the plates were addressed by raw key; a stack provisioned
    that way after the entity model refused every shoot for want of a row, and
    named this script while doing it.
    """
    code, calls = _push_plates(has_studio=True)

    assert code == 0
    assert calls == ["config sync --apply --quiet"], calls
    assert not any("s3" in c for c in calls), calls


def test_a_missing_cli_is_not_a_failure():
    """`dev-setup.sh` runs from the SessionStart hook and must not fail a session.

    The same reasoning `config sync` applies to a missing sign-in: report and
    carry on, and let the first shoot name the real problem.
    """
    code, calls = _push_plates(has_studio=False)

    assert code == 0
    assert calls == [], calls


def test_a_folder_row_survives_the_tab_collapse_trap():
    """`read` with `IFS=$'\\t'` collapses RUNS of tabs — tab is IFS whitespace.

    A folder node carries no `source` and no `content_type`, so its row has two
    empty fields. Put them anywhere but last and `p<TAB>folder<TAB><TAB><TAB>T0`
    parses as three fields, landing the timestamp in `source` and leaving
    `created_at` empty — which writes a node with no `created_at` and sorts the
    whole library wrong. Caught here rather than in a fixture nobody has yet.

    **The ordering rule stopped being enough and a sentinel replaced it.** Two
    more columns joined the row with the entity model — `owner_kind` and
    `owner_root`, where a blob key gets its prefix — and they are empty
    INDEPENDENTLY of the other two: a folder has no source, material at the
    library root has no owner. Two holes, and no ordering puts both at the end.
    So nothing is emitted empty any more; `-` means absent and
    `node_row_fixup` turns it back. This test caught it — a folder row parsed
    as five fields and put `character` in `source`.
    """
    rows = _source_and_run(SEED, f"""
      catalog={json.dumps(json.dumps(GOOD_CATALOG))}
      while IFS=$'\\t' read -r path kind created_at source content_type \
                                owner_kind owner_root; do
        node_row_fixup
        printf '%s|%s|%s|%s|%s|%s|%s\\n' "$path" "$kind" "$created_at" "$source" \
               "$content_type" "$owner_kind" "$owner_root"
      done < <(jq -r "$NODE_ROWS_JQ" <<<"$catalog")
    """).splitlines()

    assert rows == [
        "subject-a|folder|2026-08-19T09:12:44.000000+00:00|||character|subject-a",
        "subject-a/reference|folder|2026-08-19T09:12:44.000001+00:00|||character|subject-a",
        "subject-a/reference/a.PNG|file|2026-08-19T09:12:44.000002+00:00"
        "|v1/media/a.png|image/png|character|subject-a",
        "porch-teaser|folder|2026-08-19T09:12:44.000003+00:00|||project|porch-teaser",
    ]
