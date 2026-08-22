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
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.maintenance import catalog_seed

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


def test_derived_ids_match_catalog_seed(monkeypatch):
    """The same library id, node ids and `path` values `catalog_seed` derives.

    Not a coincidence worth leaving untested: the scheme is what makes a re-seed
    converge, and `catalog_seed.verify` walks `path` to find drift. Two
    derivations that disagree would produce a second tree beside the first.
    """
    monkeypatch.setattr(catalog_seed.s3c, "BUCKET", BUCKET)

    assert _source_and_run(SEED, f'derive_library_id "{BUCKET}"') == catalog_seed.library_id()
    for path in ("", "projects", "projects/demo/a.PNG"):
        assert (_source_and_run(SEED, f'derive_node_id "{BUCKET}" "{path}"')
                == catalog_seed.node_id(path))
    for prefix in ("", "projects", "projects/demo/deeper"):
        assert (_source_and_run(SEED, f'materialised "{BUCKET}" "{prefix}"')
                == catalog_seed.materialised(prefix))


# ── the items, against the schema the Python writer uses ────────────────────


def _node(**over) -> dict:
    node = {"node_id": "node-a", "parent_id": "node-p", "lib": "lib-1",
            "name": "a.PNG", "kind": "file", "path": "/node-root/node-p/",
            "created_at": "2026-08-19T09:12:44.000001+00:00",
            "updated_at": "2026-08-19T09:12:44.000001+00:00",
            "blob_key": "blobs/node-a", "size": 1234, "content_type": "image/png"}
    node.update(over)
    return node


def test_a_node_is_written_as_the_two_items_catalog_seed_writes():
    """Attribute for attribute, including the types.

    A node is two items — the `META` record and the `NAME#` listing item — and
    one without the other is a node that either cannot be listed or cannot be
    opened. The bash loader and the Python seeder write into the same table, so
    a disagreement about a single attribute is a corrupt library, not a
    cosmetic difference. `size` as `{"S": …}` instead of `{"N": …}` is exactly
    the mistake this catches.
    """
    node = _node()
    actions = json.loads(_source_and_run(SEED, (
        'node_items tbl lib-1 node-a node-p "a.PNG" file "/node-root/node-p/" '
        '"2026-08-19T09:12:44.000001+00:00" "image/png" 1234'
    )))

    assert [a["Put"]["ConditionExpression"] for a in actions] == \
        ["attribute_not_exists(pk)"] * 2
    assert actions[0]["Put"]["Item"] == ddbc.to_item(catalog_seed.meta_item(node))
    assert actions[1]["Put"]["Item"] == ddbc.to_item(catalog_seed.index_item(node))


def test_a_folder_node_carries_no_blob_size_or_content_type():
    """Absent, not null. `attribute_not_exists` is what a NULL would defeat."""
    folder = _node(kind="folder", name="projects", node_id="node-f",
                   parent_id="node-root", path="/node-root/",
                   blob_key=None, size=None, content_type=None)
    actions = json.loads(_source_and_run(SEED, (
        'node_items tbl lib-1 node-f node-root "projects" folder "/node-root/" '
        '"2026-08-19T09:12:44.000001+00:00" "" 0'
    )))

    item = actions[0]["Put"]["Item"]
    assert item == ddbc.to_item(catalog_seed.meta_item(folder))
    for absent in ("blob_key", "size", "content_type"):
        assert absent not in item


def test_the_root_is_one_item_with_no_parent_and_no_name():
    """#280: a `NAME#` item pairs a name with a parent, and the root has neither."""
    actions = json.loads(_source_and_run(SEED, (
        'library_items tbl lib-1 node-root "Studio" sub-9 '
        '"2026-08-19T09:12:44.000000+00:00"'
    )))

    assert [a["Put"]["Item"]["pk"]["S"] for a in actions] == \
        ["LIB#lib-1", "USER#sub-9", "NODE#node-root"]
    root = actions[2]["Put"]["Item"]
    assert root["sk"] == {"S": "META"}
    assert root["path"] == {"S": "/"}
    assert "parent_id" not in root and "name" not in root
    assert actions[1]["Put"]["Item"]["role"] == {"S": "owner"}


# ── the fixture contract ────────────────────────────────────────────────────

GOOD_CATALOG = {
    "version": 1,
    "library_name": "Studio",
    "nodes": [
        {"path": "projects", "kind": "folder",
         "created_at": "2026-08-19T09:12:44.000000+00:00"},
        {"path": "projects/demo", "kind": "folder",
         "created_at": "2026-08-19T09:12:44.000001+00:00"},
        {"path": "projects/demo/a.PNG", "kind": "file",
         "source": "v1/media/a.png", "content_type": "image/png",
         "created_at": "2026-08-19T09:12:44.000002+00:00"},
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
    (lambda c, m: c["nodes"][2].pop("content_type"), "needs a `content_type`"),
    (lambda c, m: c["nodes"][2].update(source="v1/media/gone.png"),
     "is not in manifest.json"),
    (lambda c, m: m["objects"].update({"v1/media/spare.png": {"size": 1, "sha256": "cd"}}),
     "claimed by no node"),
    (lambda c, m: m.update(object_count=9), "object_count is 9"),
    (lambda c, m: m.update(total_bytes=9), "total_bytes is 9"),
    (lambda c, m: c["nodes"][2].update(path="projects/demo/../a.PNG"),
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


def _shared_material(head_exit: int) -> tuple[int, list[str]]:
    """Run `seed_phrasebook` against a fake `aws` that reports the HEAD's result.

    The functions take their AWS command as an overridable array precisely so
    this is possible without credentials.
    """
    script = f"""
    calls=()
    fake_aws() {{
      printf '%s\\n' "$*" >&2
      if [ "$1 $2" = "s3api head-object" ]; then return {head_exit}; fi
      return 0
    }}
    SHARED_MATERIAL_AWS=(fake_aws)
    source "{SHARED}"
    seed_phrasebook "{STUDIO_DIR}" a-dev-bucket
    """
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return result.returncode, result.stderr.splitlines()


def test_the_phrasebook_is_copied_when_the_key_is_absent():
    """#425: `PATCH /api/text` overwrites and never invents, so something has to
    put the first `wording.yaml` there or `phrasebook add` is unavailable."""
    code, calls = _shared_material(head_exit=1)

    assert code == 0
    assert any(c.startswith("s3 cp") and c.endswith(
        "s3://a-dev-bucket/phrasebook/wording.yaml --only-show-errors") for c in calls), calls


def test_the_phrasebook_is_left_alone_when_one_already_exists():
    """**The difference from the `config/` sync beside it.**

    From the first `studio phrasebook add` the bucket's copy is the live
    document. Re-syncing the repo's seed over it would delete recorded entries,
    and `dev-setup.sh` runs on every session.
    """
    code, calls = _shared_material(head_exit=0)

    assert code == 2
    assert not any(c.startswith("s3 cp") for c in calls), calls
