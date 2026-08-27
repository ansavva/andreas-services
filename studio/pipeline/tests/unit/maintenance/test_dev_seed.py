"""`studio dev-seed publish` — the writer, against the loader that reads it.

`scripts/dev-aws-seed.sh` shipped first (#285) and defined `catalog.json` and
`manifest.json` field by field, because #284 only sketched them. That made the
contract one-sided. These tests are what make it two-sided: the documents this
module builds are fed to the loader's OWN `fixture_problems` shell function, so
a disagreement about a field is a red test rather than a fixture that reaches
the bucket and is rejected on somebody's machine.

Nothing here touches AWS. The dev stack is a moto bucket plus a moto table named
the way a real one is, because the first thing `publish` does is refuse a name
containing `prod` — and a suite that ran against the default names would be
testing the refusal and nothing else.
"""

import ast
import hashlib
import json
import pathlib

import boto3
import pytest
from click.testing import CliRunner
from moto import mock_s3

from studio_pipeline import cli
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.maintenance import dev_seed as ds
# The loader's own validator, not a second copy of it. `test_dev_scripts`
# already sources `dev-aws-seed.sh` and exposes `fixture_problems`; reaching for
# it here is the whole point — a reimplementation would agree with itself.
from tests.support import shell as loader

SOURCE = pathlib.Path(ds.__file__)

DEV_BUCKET = "studio-dev-abc123456789-media-us-east-1"
DEV_TABLE = "studio-dev-abc123456789-catalog"

LIB = "lib-11111111-2222-3333-4444-555555555555"
ROOT = "node-00000000-0000-0000-0000-000000000000"

REQUEST = json.dumps({"model": "kling", "project": "subject-a",
                      "prompt": "the runner moves down the track. Golden hour."})
RESULT = json.dumps({"status": "succeeded"})

# A miniature of what a dev stack looks like after a session driven with
# placeholders: a run folder with its two documents and an output, a folder
# three deep, an uppercase extension, and an empty folder — which is what #284's
# "zero-byte folder marker" becomes once a folder is a row rather than an object.
#
# **The project's folder is a child of the library root.** There is no
# `projects/` wrapper: an entity root is a top-level folder named by its slug,
# which is why `name_positions` reports under `ENTITY_ROOTS` and why a tree
# shaped the old way is refused — `projects` is not in `DEV_SUBJECTS`, and the
# publisher is right to say so.
#
# (path, kind, body). A folder's body is None.
TREE = [
    ("subject-a", "folder", None),
    ("subject-a/runs", "folder", None),
    ("subject-a/runs/2026-08-19_09-12-44_wave-porch", "folder", None),
    ("subject-a/runs/2026-08-19_09-12-44_wave-porch/request.json",
     "file", REQUEST.encode()),
    ("subject-a/runs/2026-08-19_09-12-44_wave-porch/result.json",
     "file", RESULT.encode()),
    ("subject-a/runs/2026-08-19_09-12-44_wave-porch/output",
     "folder", None),
    ("subject-a/runs/2026-08-19_09-12-44_wave-porch/output/wave-porch.JPEG",
     "file", b"jpeg-bytes-of-a-still"),
    ("subject-a/input", "folder", None),
    # A CHARACTER, so the `entities` half of the contract is exercised too.
    # It used not to be here, and that omission is why `build` could emit
    # `{"version": 1}` with no entities at all for as long as it did: the
    # loader treats `entities` as optional, so a fixture that described none
    # validated and loaded, and the only test that would have noticed built its
    # source stack out of node rows exclusively.
    ("subject-b", "folder", None),
    ("subject-b/reference", "folder", None),
    ("subject-b/reference/face", "folder", None),
    ("subject-b/reference/face/front.png", "file", b"png-bytes-of-a-face"),
]

CONTENT_TYPES = {"request.json": "application/json",
                 "result.json": "application/json",
                 "wave-porch.JPEG": "image/jpeg",
                 "front.png": "image/png"}

CHAR_ID = "char-00000000-0000-0000-0000-0000000000b0"
PROJ_ID = "proj-00000000-0000-0000-0000-0000000000a0"
FACE = "subject-b/reference/face/front.png"

#: Nested on purpose. A bible is maps inside maps with lists of maps in them
#: (`wardrobe.tops[].item`), and the publisher carries `profile` through as it
#: stands — so a fixture built from this one is also what proves the loader's
#: jq marshaller recurses. See `test_dev_scripts` on the flat version that
#: turned every inner map into a string.
PROFILE = {
    "schema_version": 2,
    "identity": {"apparent_age": "<age>", "signature_features": ["<cue>"]},
    "wardrobe": {"tops": [{"item": "<garment>", "colour": "black"}]},
}


def _node_id(path: str) -> str:
    """A stable stand-in for the `node-<uuid4>` the API mints.

    Deliberately NOT `catalog_seed.node_id`: a dev stack's ids come from
    `uuid.uuid4()` in the backend and are derived from nothing, which is the
    reason `publish` walks `parent_id` instead of deriving a path.
    """
    return "node-" + hashlib.sha256(path.encode()).hexdigest()[:32]


def _rows(tree=TREE, lib=LIB):
    """The `META` rows a dev stack holds for `tree`, plus the library and root."""
    stamp = "2026-08-19T09:12:44.{:06d}+00:00"
    items = [
        {"pk": f"LIB#{lib}", "sk": "META", "name": "Studio",
         "root_node": ROOT, "created_at": stamp.format(0)},
        {"pk": f"NODE#{ROOT}", "sk": "META", "node_id": ROOT, "lib": lib,
         "kind": "folder", "path": "/", "created_at": stamp.format(0),
         "updated_at": stamp.format(0)},
    ]
    for n, (path, kind, body) in enumerate(tree, start=1):
        parent, _, name = path.rpartition("/")
        row = {"pk": f"NODE#{_node_id(path)}", "sk": "META",
               "node_id": _node_id(path),
               "parent_id": _node_id(parent) if parent else ROOT,
               "lib": lib, "name": name, "kind": kind,
               "path": "/derived/elsewhere/", "created_at": stamp.format(n),
               "updated_at": stamp.format(n)}
        if kind == "file":
            row["blob_key"] = f"blobs/{_node_id(path)}"
            row["size"] = len(body)
            row["content_type"] = CONTENT_TYPES[name]
        items.append(row)

    # The entity rows. Six of them for two entities, because a record is
    # useless without its slug claim and a project's cast is rows rather than a
    # list on the record — see `services/catalog.py`. `publish` reads all of
    # these off the SAME scan that read the nodes above.
    items += [
        {"pk": f"LIB#{lib}", "sk": "CHARSLUG#subject-b",
         "entity": CHAR_ID, "created": stamp.format(90)},
        {"pk": f"CHAR#{CHAR_ID}", "sk": "META", "id": CHAR_ID, "lib": lib,
         "slug": "subject-b", "display_name": "<Name>", "fictional": True,
         "schema_version": 2, "rev": 1,
         "created": stamp.format(90), "updated": stamp.format(90),
         "root": _node_id("subject-b"), "hero": None,
         "default_set": [_node_id(FACE)], "profile": PROFILE},
        {"pk": f"CHAR#{CHAR_ID}", "sk": f"REF#{_node_id(FACE)}", "lib": lib,
         "group": "face", "order": 1000, "description": "front, neutral",
         "tags": ["face"], "created": stamp.format(91)},
        {"pk": f"LIB#{lib}", "sk": "PROJSLUG#subject-a",
         "entity": PROJ_ID, "created": stamp.format(92)},
        {"pk": f"PROJ#{PROJ_ID}", "sk": "META", "id": PROJ_ID, "lib": lib,
         "slug": "subject-a", "title": "<Title>", "description": "", "rev": 1,
         "created": stamp.format(92), "updated": stamp.format(92),
         "root": _node_id("subject-a"), "hero": None,
         "counts": {"runs": 1, "scenes": 0, "movies": 0}},
        {"pk": f"PROJ#{PROJ_ID}", "sk": f"CHAR#{CHAR_ID}", "lib": lib,
         "created": stamp.format(93)},
    ]
    return items


@pytest.fixture
def dev_stack(monkeypatch, tmp_path):
    """A moto bucket + table named as a real dev stack is, with the CLI aimed at it.

    `_no_live_dynamodb` in conftest already has a mock running, so the table is
    created into that one. The bucket needs its own mock.

    `FIXTURE_DIR` is redirected into tmp_path so an `--apply` in the suite cannot
    write into the repo — the git copy is the fixture, and a test that produced
    one would be a test that edits the repository.
    """
    # Environment variables rather than module constants: the bucket and table
    # are profile fields now, and with no profile selected the environment is
    # what answers. Patching a constant would have tested nothing after the
    # constants went away — which is exactly what it did.
    monkeypatch.setenv("STUDIO_S3_BUCKET", DEV_BUCKET)
    monkeypatch.setenv("STUDIO_CATALOG_TABLE", DEV_TABLE)
    monkeypatch.setattr(ds, "FIXTURE_DIR", tmp_path / "fixtures")

    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName=DEV_TABLE, BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"},
                   {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"}
                              for n in ("pk", "sk")],
    )
    with mock_s3():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=DEV_BUCKET)
        s3.create_bucket(Bucket="studio-dev-seed-us-east-1")
        for path, kind, body in TREE:
            if kind == "file":
                s3.put_object(Bucket=DEV_BUCKET, Key=f"blobs/{_node_id(path)}",
                              Body=body)
        for item in _rows():
            ddb.put_item(TableName=DEV_TABLE, Item=ddbc.to_item(item))
        yield {"s3": s3, "ddb": ddb, "fixtures": tmp_path / "fixtures"}


def _publish(*argv):
    return CliRunner().invoke(cli.main, ["dev-seed", "publish", *argv])


RUN = "subject-a/runs/2026-08-19_09-12-44_wave-porch"


# ── the money pin ───────────────────────────────────────────────────────────


def _code(path: pathlib.Path) -> str:
    """The module's source with every docstring removed.

    The analogue of `test_dev_scripts._code_lines`, which strips comments off
    the shell script for the same reason: this module's own prose says
    `REPLICATE_API_TOKEN` while explaining that it never reads one, and a scan
    that could not tell the two apart would be unusable.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_publish_cannot_reach_a_model_provider():
    """**The pin, and read what it does not catch.**

    #284: `--publish` is a copy. It generates nothing, so it costs nothing, and
    it carries no hard-rule-#2 approval gate of its own — the approval happened
    when a human ran the generations that filled the dev stack. `dev-aws-seed.sh`
    pins the same property about itself with a grep; this is the Python version.

    WHAT IT CATCHES: a generation added to this module directly — a provider's
    name, a provider credential, an HTTP client, a shell-out, or an import of
    the `engine` package, where every paid call in this repo lives.

    WHAT IT DOES NOT CATCH:

    - **Anything reached indirectly.** `adapters/s3` and `adapters/ddb` are
      imported here and neither is scanned. A paid call added to one of them,
      or to `catalog_seed`, is invisible to this.
    - **What the code does at runtime.** A scan of source, not an execution or a
      network sandbox. boto3 is allowed here and boto3 can be made to cost
      money.
    - **AWS's own charges.** S3 GETs and PUTs and a DynamoDB scan all cost
      fractions of a cent, and this command performs all three. The property is
      "no model inference is billed", not "zero spend".
    """
    code = _code(SOURCE).lower()
    for token, why in [
        ("replicate", "the model provider — publishing must never generate"),
        ("openai", "a model provider"),
        ("anthropic", "a model provider"),
        ("api_token", "a provider credential has no business in a copy"),
        ("api_key", "a provider credential has no business in a copy"),
        ("subprocess", "no shell-out; every paid command in this repo is one"),
        ("requests", "no HTTP client — this reads and writes S3 and DynamoDB"),
        ("urllib", "no HTTP client — this reads and writes S3 and DynamoDB"),
    ]:
        assert token not in code, f"{SOURCE.name} names {token!r}: {why}"

    imported = set()
    for node in ast.walk(ast.parse(SOURCE.read_text())):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    banned = [m for m in imported
              if m.startswith(("studio_pipeline.engine", "studio_pipeline.objects"))]
    assert not banned, f"{SOURCE.name} imports {banned}: the engine is what bills"


def test_publish_destroys_nothing():
    """A promotion adds. Emptying a dev stack is `dev-aws-reset.sh`."""
    code = _code(SOURCE)
    for token in ("delete_object", "delete_item", "delete_table", "rmtree",
                  "os.remove", "unlink"):
        assert token not in code, f"{SOURCE.name} calls {token!r}"


# ── the contract with the loader ────────────────────────────────────────────


def test_the_documents_pass_the_loaders_own_validator(dev_stack):
    """The two-sided half of "THE CONTRACT WITH #284".

    Not an assertion about fields — an execution of the shell function that will
    actually judge this fixture on a developer's machine. If `dev-aws-seed.sh`
    and this module ever disagree about a field name, a required key or the
    cross-check between the two documents, it fails here.
    """
    result = _apply("--path", RUN, "--path", "subject-a/input")
    assert result.exit_code == 0, result.output

    catalog, manifest = _documents(dev_stack)
    assert loader.problems(catalog, manifest) == ""


def _documents(dev_stack, version="v1"):
    """The two documents as published, read back out of the seed bucket."""
    def read(name):
        body = dev_stack["s3"].get_object(
            Bucket="studio-dev-seed-us-east-1", Key=f"{version}/{name}")["Body"].read()
        return json.loads(body)
    return read("catalog.json"), read("manifest.json")


def _apply(*argv):
    return _publish(*argv, "--apply", "--dev-subjects-only")


def test_the_git_copy_and_the_bucket_copy_are_byte_identical(dev_stack):
    """`catalog.json` is authoritative in git and copied into the bucket.

    Both are written from one in-memory document in one formatting, so the two
    cannot differ at publish time — which is what lets a later drift be found
    with a checksum instead of a parser.
    """
    assert _apply("--path", RUN).exit_code == 0

    for name in ("catalog.json", "manifest.json"):
        in_bucket = dev_stack["s3"].get_object(
            Bucket="studio-dev-seed-us-east-1", Key=f"v1/{name}")["Body"].read()
        in_git = (dev_stack["fixtures"] / "v1" / name).read_bytes()
        assert in_bucket == in_git


def test_the_manifest_describes_the_bytes_and_the_bytes_are_there(dev_stack):
    """Size and checksum come from what was read, not from the row that claims it.

    The row is what the API recorded; the manifest is what the loader verifies a
    download against. A manifest built from `size` on the row would pass here
    and fail on the first machine whose download disagreed with it.
    """
    assert _apply("--path", RUN).exit_code == 0
    catalog, manifest = _documents(dev_stack)

    assert manifest["object_count"] == 3
    for key, entry in manifest["objects"].items():
        body = dev_stack["s3"].get_object(
            Bucket="studio-dev-seed-us-east-1", Key=key)["Body"].read()
        assert entry["size"] == len(body)
        assert entry["sha256"] == hashlib.sha256(body).hexdigest()
    assert manifest["total_bytes"] == sum(
        e["size"] for e in manifest["objects"].values())
    assert {n["source"] for n in catalog["nodes"] if n["kind"] == "file"} \
        == set(manifest["objects"])


def test_the_fixture_carries_no_ids(dev_stack):
    """Ids belong to the machine being seeded, not to the stack promoted from.

    `dev-aws-seed.sh` derives every id as `uuid5` over `s3://<dev bucket>/<path>`,
    with the bucket name inside the derivation, so two machines derive different
    ids from one fixture. An id written here would be a foreign stack's.
    """
    assert _apply("--path", RUN).exit_code == 0
    catalog, _manifest = _documents(dev_stack)

    text = json.dumps(catalog)
    assert "node-" not in text and "lib-" not in text
    # `char-` and `proj-` too. The entity half arrived after this test did, and
    # an entity record is where the ids are: `root`, `hero` and every
    # `default_set` entry are node ids in the table and paths in the fixture.
    assert "char-" not in text and "proj-" not in text
    assert {k for node in catalog["nodes"] for k in node} <= {
        "path", "kind", "created_at", "source", "content_type"}


def test_created_at_is_carried_over_so_the_fixture_sorts_as_its_source_did(dev_stack):
    """The loader reads no clock, so the ordering has to come from here."""
    assert _apply("--path", RUN).exit_code == 0
    catalog, _ = _documents(dev_stack)
    stamps = [n["created_at"] for n in catalog["nodes"]]
    assert all(s.startswith("2026-08-19T09:12:44.") for s in stamps)
    assert len(set(stamps)) == len(stamps)


# ── choosing what to promote ────────────────────────────────────────────────


def test_publishing_everything_is_not_a_thing_you_can_ask_for(dev_stack):
    """No `--all`, and `--path` is required: the default promotes nothing.

    #284's failure mode is promoting a session's output wholesale, so the
    command with no arguments is a usage error rather than a whole library.
    """
    assert _publish().exit_code == 2
    assert _publish("--path", "/").exit_code == 1
    assert "library root" in _publish("--path", "/").output


def test_a_dry_run_is_the_default_and_writes_nothing(dev_stack):
    result = _publish("--path", RUN)
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert not (dev_stack["fixtures"]).exists()
    listed = dev_stack["s3"].list_objects_v2(Bucket="studio-dev-seed-us-east-1")
    assert listed.get("KeyCount") == 0


def test_apply_without_the_attestation_refuses(dev_stack):
    result = _publish("--path", RUN, "--apply")
    assert result.exit_code == 1
    assert "--dev-subjects-only" in result.output


def test_a_folder_brings_its_subtree_and_its_ancestors(dev_stack):
    """Ancestors are not a choice — the loader refuses a fixture missing one.

    `fixture_problems` reports "its parent folder is not a node in catalog.json"
    and will not invent one, because a silently-invented folder is a shape
    nobody reviewed.
    """
    assert _apply("--path", RUN).exit_code == 0
    catalog, _ = _documents(dev_stack)
    published = {n["path"] for n in catalog["nodes"]}

    # The project's own root and the `runs/` folder between it and the run —
    # ancestors are structural and the loader will not invent one.
    assert "subject-a" in published and "subject-a/runs" in published
    assert f"{RUN}/output/wave-porch.JPEG" in published
    # Not selected, not under the selection.
    assert "subject-a/input" not in published


def test_an_empty_folder_can_be_promoted_on_its_own(dev_stack):
    """#284's "zero-byte folder marker", translated.

    A folder is a catalog row now, and the loader's contract cannot express a
    marker object — a folder node may not carry a `source`. A childless folder
    node is what the app sees either way.
    """
    assert _apply("--path", "subject-a/input").exit_code == 0
    catalog, manifest = _documents(dev_stack)

    assert {n["path"] for n in catalog["nodes"]} == {"subject-a", "subject-a/input"}
    assert manifest["object_count"] == 0
    assert loader.problems(catalog, manifest) == ""


def test_a_selection_over_the_cap_is_refused(dev_stack):
    """A folder brings its subtree, which is how a chosen fixture goes wholesale."""
    result = _publish("--path", RUN, "--max-objects", "2")
    assert result.exit_code == 1
    assert "over the --max-objects cap" in result.output


def test_a_path_that_is_not_in_the_stack_is_named(dev_stack):
    result = _publish("--path", "subject-a/nope")
    assert result.exit_code == 1
    assert "no such path" in result.output


# ── hard rule #1 ────────────────────────────────────────────────────────────


def _put_nodes(ddb, tree):
    """The NODE rows for `tree`, dropped into the stack alongside the fixture's."""
    for item in _rows(tree=tree):
        if item["sk"] == "META" and item["pk"].startswith("NODE#"):
            ddb.put_item(TableName=DEV_TABLE, Item=ddbc.to_item(item))


def test_an_unlisted_name_anywhere_in_the_stack_refuses_the_publish(dev_stack):
    """The whole stack is checked, not just the selection.

    #284: "generating naturally and sanitising afterwards is the wrong order —
    the names would already be in the bucket, the run JSON and the S3 keys." So
    the property is that the stack was DRIVEN with subjects this repo publishes,
    and one unlisted top-level folder in a corner nobody is promoting still
    fails it.
    """
    _put_nodes(dev_stack["ddb"], [("rosalind", "folder", None)])

    result = _publish("--path", RUN)
    assert result.exit_code == 1
    # Reported under `entity roots`, because that is the only name position
    # left: a top-level folder is somebody's slug, and there is no
    # `characters/` folder to name the group after.
    assert "entity roots/ holds 'rosalind'" in result.output
    assert "not a dev subject this repo publishes" in result.output


def test_a_listed_dev_subject_publishes(dev_stack):
    """**The rule this replaced would have refused `jason` outright.**

    Hard rule #1 is env-scoped: a dev subject may be named in the repo, a
    production character may not. The old guard was a SHAPE regex —
    `subject-a`, `demo`, `<word>` — so the fixture's own subject failed it, and
    the only way through was to name the real thing something it is not.
    """
    assert "jason" in ds.DEV_SUBJECTS
    _put_nodes(dev_stack["ddb"], [("jason", "folder", None)])

    result = _publish("--path", RUN)
    assert result.exit_code == 0, result.output
    assert "REFUSED" not in result.output


def test_a_capitalised_segment_is_no_longer_refused(dev_stack):
    """The Title-Case refusal is DELETED, not adapted.

    It existed to catch a real name that the shape regex would otherwise wave
    through — `subject-a` and `mira` being the same string to a pattern. An
    allowlist has no such gap, so the check had nothing left to do except refuse
    perfectly ordinary folders: #284 asks for one deliberately awkward name in
    the fixture, and `IMG_1966_Original.JPG` only ever passed by accident of how
    narrowly the pattern was drawn.
    """
    _put_nodes(dev_stack["ddb"], [("subject-a", "folder", None),
                                  ("subject-a/Amelia-Hart", "folder", None)])

    result = _publish("--path", "subject-a/Amelia-Hart")
    assert result.exit_code == 0, result.output
    assert "REFUSED" not in result.output


def test_the_allowlist_is_the_gate_and_it_is_a_committed_list():
    """Adding a subject is a reviewed diff. That IS the mechanism.

    The other half is not here: `source()` refuses a `prod` bucket or table
    before anything is read, so "this is dev material" is enforced by
    construction and this list only decides which dev subjects are publishable.
    """
    assert isinstance(ds.DEV_SUBJECTS, frozenset)
    assert {"jason", "subject-a", "subject-b"} <= ds.DEV_SUBJECTS
    assert ds.name_problems({"n1": "rosalind"})
    assert ds.name_problems({"n1": "jason", "n2": "jason/reference"}) == []


def test_capitalised_tokens_in_promoted_text_are_reported_not_refused(dev_stack):
    """The half of hard rule #1 no list decides.

    A refusal on capitalised words in prose would fire on every sentence and be
    switched off within a week. So the tokens are printed, on the dry run,
    before the human types `--apply` — and `--dev-subjects-only` is where they
    say they read them. `name_problems` lists what that still cannot catch.
    """
    result = _publish("--path", RUN)
    assert result.exit_code == 0
    assert "READ THESE" in result.output
    assert "Golden" in result.output
    assert f"{RUN}/request.json" in result.output


# ── the stack it reads ──────────────────────────────────────────────────────


def test_promoting_from_production_is_refused(dev_stack, monkeypatch):
    """The mistake the first version of #284 made, guarded at the first read.

    That version copied production media into a shared bucket. Production
    material is not purpose-made for dev, and a fixture every machine downloads
    is the last place it belongs.
    """
    monkeypatch.setenv("STUDIO_S3_BUCKET", "studio-prod-media-us-east-1")
    result = _publish("--path", RUN)
    assert result.exit_code == 1
    assert "never from production" in result.output

    monkeypatch.setenv("STUDIO_S3_BUCKET", DEV_BUCKET)
    monkeypatch.setenv("STUDIO_CATALOG_TABLE", "studio-prod-catalog")
    assert "never from production" in _publish("--path", RUN).output


def test_the_path_is_the_chain_of_names_not_the_materialised_path(dev_stack):
    """`path` on a row is ancestor IDS; the fixture's `path` is ancestor NAMES.

    The fixture rows in this module carry a deliberately wrong `path` attribute
    for that reason — if `publish` ever read it instead of walking `parent_id`,
    every test above would produce `/derived/elsewhere/`.
    """
    lib = ds.read_library(dev_stack["ddb"])
    paths = ds.name_paths(lib)
    assert paths[ROOT] == ""
    assert paths[_node_id(RUN)] == RUN


def test_tree_lists_the_stack_by_path(dev_stack):
    result = CliRunner().invoke(cli.main, ["dev-seed", "tree"])
    assert result.exit_code == 0, result.output
    assert RUN in result.output
    assert "folder" in result.output and "file" in result.output


# ── the entity half ─────────────────────────────────────────────────────────
#
# `build` used to emit `{"version": 1, "nodes": …}` and no `entities` key at
# all, while `dev-aws-seed.sh` documented and validated version 2 with one.
# `fixture_problems` treats `entities` as optional and never checks `version`,
# so the wrong document validated, loaded, and produced loose folders under the
# library root with no character and no project. Every test below would have
# failed against that, and none of them existed.


def _entities(dev_stack, *paths):
    """Publish `paths` and return `{slug: entity}` out of the bucket copy."""
    assert _apply(*sum((["--path", p] for p in paths), [])).exit_code == 0
    catalog, _ = _documents(dev_stack)
    assert catalog["version"] == 2
    return {entity["slug"]: entity for entity in catalog["entities"]}


def test_a_character_is_promoted_with_its_references(dev_stack):
    """Root, references and `default_set` — all of them as PATHS, not ids."""
    character = _entities(dev_stack, "subject-b")["subject-b"]

    assert character["kind"] == "character"
    assert character["root"] == "subject-b"
    assert character["display_name"] == "<Name>"
    assert character["fictional"] is True
    assert character["references"] == [
        {"node": FACE, "group": "face", "order": 1000,
         "description": "front, neutral", "tags": ["face"],
         "created": "2026-08-19T09:12:44.000091+00:00"},
    ]
    assert character["default_set"] == [FACE]


def test_a_nested_bible_survives_the_promotion(dev_stack):
    """`profile` is carried through as it stands, maps and lists and all.

    Not a normalised copy: the fixture seeds a library that should look like the
    one it came from, and a publisher that flattened a bible would seed a
    character nobody could shoot. The loader's own jq marshaller is the other
    half of this and is pinned in `test_dev_scripts`.
    """
    character = _entities(dev_stack, "subject-b")["subject-b"]
    assert character["profile"] == PROFILE
    assert character["profile"]["wardrobe"]["tops"][0]["item"] == "<garment>"
    # Ints, not `Decimal`. DynamoDB deserialises every N to one and the document
    # is written with `json.dumps`, which refuses them — which is exactly how
    # this failed the first time a nested profile went through it.
    assert isinstance(character["profile"]["schema_version"], int)


def test_a_project_carries_its_cast_by_slug(dev_stack):
    """`characters` is `PROJ#`/`CHAR#` rows on the way in and slugs on the way out.

    Slugs rather than ids for the same reason as everything else here, and the
    loader cross-checks them against the characters the fixture itself carries.
    """
    promoted = _entities(dev_stack, "subject-a", "subject-b")
    assert promoted["subject-a"]["kind"] == "project"
    assert promoted["subject-a"]["title"] == "<Title>"
    assert promoted["subject-a"]["characters"] == ["subject-b"]
    assert promoted["subject-a"]["counts"] == {"runs": 1, "scenes": 0, "movies": 0}


def test_a_cast_member_who_was_not_promoted_is_dropped(dev_stack):
    """A project promoted without its character does not name one.

    The loader refuses `characters` naming a slug that is not in the fixture, so
    carrying the involvement row through unfiltered would publish a document
    that cannot load.
    """
    promoted = _entities(dev_stack, "subject-a")
    assert "subject-b" not in promoted
    assert promoted["subject-a"]["characters"] == []


def test_an_entity_whose_root_was_not_promoted_is_dropped(dev_stack):
    """Not repaired — dropped. Inventing the root would put an unreviewed folder
    in the fixture, and the loader refuses an entity whose root is missing."""
    assert "subject-b" not in _entities(dev_stack, RUN)


def test_promoting_a_subfolder_brings_the_entity_that_owns_it(dev_stack):
    """Because `expand` adds ancestors, and the top ancestor is the root.

    Not incidental — it is what makes `--path <project>/runs/<run>` produce a
    fixture that describes the project rather than a loose `runs` folder. The
    ancestors are added for the loader's sake ("its parent folder is not a node
    in catalog.json"), and the entity comes with them.
    """
    promoted = _entities(dev_stack, "subject-a/input")
    assert promoted["subject-a"]["kind"] == "project"
    assert promoted["subject-a"]["root"] == "subject-a"


def test_entities_is_written_even_when_there_are_none(dev_stack):
    """An empty list and an absent key load identically; the key is a statement.

    Driven through the builder rather than the CLI because every top-level
    folder in `TREE` is somebody's root, so there is no `--path` that reaches
    none of them — which is itself the point of the test above.
    """
    library = ds.read_library(dev_stack["ddb"])
    paths = ds.name_paths(library)
    library["records"] = {}
    assert ds.entities(library, paths, set(paths)) == []

    catalog, _manifest = ds.build(library, paths, set(), {}, "v1")
    assert catalog["version"] == 2
    assert catalog["entities"] == []


def test_a_default_set_entry_with_no_reference_row_is_dropped(dev_stack):
    """`default_set` must be a SUBSET of `references` or the loader refuses the
    whole fixture — so a record that disagrees with its own rows is filtered
    here rather than published and rejected on somebody's machine."""
    library = ds.read_library(dev_stack["ddb"])
    paths = ds.name_paths(library)
    library["records"][f"CHAR#{CHAR_ID}"]["default_set"] = [
        _node_id(FACE), _node_id("subject-b/reference"),
    ]
    selected = {node_id for node_id, path in paths.items()
                if path == "subject-b" or path.startswith("subject-b/")}

    character, = [e for e in ds.entities(library, paths, selected)
                  if e["slug"] == "subject-b"]
    assert character["default_set"] == [FACE]
