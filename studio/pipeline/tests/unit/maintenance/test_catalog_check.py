"""Which library the migration runs against — the one choice prod forces.

`catalog gc` and the seed loader have their own files; this one exists for the
selection, because that is where the command met production and lost.

**A prod table holds two libraries and always will.** The real one, and
`lib-smoke`, which `scripts/prod-seed-smoke.py` writes so the post-deploy smoke
test can sign in as an account that is a member of exactly one library — the
mechanism the smoke test rests on rather than a courtesy, so it is permanent.

The command refused that outright on its first run against prod, with a message
claiming it migrated "the one the bucket names". Nothing names a library: a
bucket holds bytes, and the table is the only thing that knows a library exists.
So there was no way to proceed and no way to find out there was no way except by
running it.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.maintenance import catalog_check as cm

REAL = "lib-bf3b86ef-2569-5c55-8ccb-f03cbe3443b5"
SMOKE = "lib-smoke"


def _library(ddb, lib: str, name: str, root: str) -> None:
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": f"LIB#{lib}", "sk": "META", "name": name, "root_node": root}))
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": f"NODE#{root}", "sk": "META", "node_id": root, "lib": lib,
         "kind": "folder", "name": "/", "path": "/"}))


def test_one_library_needs_no_flag(catalog_table):
    """The single-library case is unchanged — this is what dev stacks look like."""
    _library(catalog_table, REAL, "Studio", "node-root")
    assert cm.read_catalog(catalog_table)["lib"] == REAL


def test_two_libraries_refuse_and_name_both(catalog_table):
    """And the refusal has to be actionable, which the original was not.

    It listed the ids under a sentence describing a selection it did not
    implement. Printing the flag that resolves it is the difference between a
    message you can act on and one you have to read the source to act on.
    """
    _library(catalog_table, REAL, "Studio", "node-root")
    _library(catalog_table, SMOKE, "Smoke test", "node-smoke-root")

    result = CliRunner().invoke(cli.main, ["catalog", "verify"])
    assert result.exit_code != 0
    assert "more than one library" in result.output
    assert f"--library {REAL}" in result.output
    assert f"--library {SMOKE}" in result.output


def test_the_named_library_is_the_one_planned(catalog_table):
    _library(catalog_table, REAL, "Studio", "node-root")
    _library(catalog_table, SMOKE, "Smoke test", "node-smoke-root")

    assert cm.read_catalog(catalog_table, REAL)["lib"] == REAL
    assert cm.read_catalog(catalog_table, REAL)["root"] == "node-root"
    # And the smoke library is reachable the same way, so nothing about this
    # privileges the real one — the caller decides, every time.
    assert cm.read_catalog(catalog_table, SMOKE)["root"] == "node-smoke-root"


def test_a_library_that_is_not_there_lists_the_ones_that_are(catalog_table):
    """A typo in an id is the likeliest way this flag is got wrong."""
    _library(catalog_table, REAL, "Studio", "node-root")
    _library(catalog_table, SMOKE, "Smoke test", "node-smoke-root")

    with pytest.raises(SystemExit):
        cm.read_catalog(catalog_table, "lib-typo")


def test_every_phase_takes_the_flag(catalog_table):
    """A flag on one command and not the next is a run that checks one library
    and rewrites another.

    There were three phases under a `migrate` group; `plan` and `apply` are
    retired and `verify` was promoted to `catalog verify`, which is the spelling
    five call sites already used. `--library` still has to be on both survivors.
    """
    catalog = cli.main.get_command(None, "catalog")
    for name in ("verify", "reseat"):
        command = catalog.get_command(None, name)
        flags = {flag for p in command.params for flag in getattr(p, "opts", [])}
        assert "--library" in flags, f"studio catalog {name}"


# ── the keys a legacy document names ────────────────────────────────────────

def _file(ddb, node_id: str, parent: str, name: str, blob_key: str) -> None:
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": f"NODE#{node_id}", "sk": "META", "node_id": node_id,
         "parent_id": parent, "lib": REAL, "kind": "file", "name": name,
         "blob_key": blob_key, "size": 9, "content_type": "image/png"}))


def _folder(ddb, node_id: str, parent: str, name: str) -> None:
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": f"NODE#{node_id}", "sk": "META", "node_id": node_id,
         "parent_id": parent, "lib": REAL, "kind": "folder", "name": name}))


def _tree(ddb):
    """Root, `config/pose/face/`, and one plate whose blob key is NOT its path.

    That mismatch is the whole point. `studio config sync` uploads a plate
    through the API, so its bytes land under the id scheme — the name path and
    the blob key have not been the same string since.
    """
    _library(ddb, REAL, "Studio", "node-root")
    _folder(ddb, "node-config", "node-root", "config")
    _folder(ddb, "node-pose", "node-config", "pose")
    _folder(ddb, "node-face", "node-pose", "face")
    _file(ddb, "node-plate", "node-face", "three-quarter.png",
          f"libraries/{REAL}/node-plate.png")


def test_a_key_that_is_a_blob_key_resolves_exactly(catalog_table):
    _tree(catalog_table)
    cat = cm.read_catalog(catalog_table, REAL)
    hits: list[str] = []
    assert cm.resolve_key(cat, f"libraries/{REAL}/node-plate.png", hits) == "node-plate"
    assert hits == [], "an exact hit must not be reported as an assumption"


def test_a_legacy_key_resolves_by_name_path_and_is_reported(catalog_table):
    """**The 28 bindings the first real migration lost, one per run.**

    Every historical reference shoot bound a pose plate, recorded as
    `config/pose/face/<file>.png` — which was the S3 key and the name path at
    once, because before the catalog they were the same string. The seed
    deliberately recorded no node for `config/`, so the exact lookup answered
    nothing and every one of those bindings was dropped from its envelope.
    """
    _tree(catalog_table)
    cat = cm.read_catalog(catalog_table, REAL)
    hits: list[str] = []

    assert cm.resolve_key(cat, "config/pose/face/three-quarter.png", hits) == "node-plate"
    assert hits == ["config/pose/face/three-quarter.png"], \
        "a path hit is an assumption and must be counted for reporting"


def test_a_key_that_is_neither_still_resolves_to_nothing(catalog_table):
    """The fallback must not turn a genuinely missing object into a false hit."""
    _tree(catalog_table)
    cat = cm.read_catalog(catalog_table, REAL)
    hits: list[str] = []
    assert cm.resolve_key(cat, "config/pose/face/deleted.png", hits) is None
    assert hits == []


# ── the row shape the API reads ─────────────────────────────────────────────
#
# **`verify` passed over 32 rows the app could not read, so these test the
# ATTRIBUTES rather than the existence of a row.**
#
# The API's unmarshaller drops `pk` and `sk` and derives nothing from either, so
# an entity id living only in the key reads back as a record without one and
# every listing 500s on `record["id"]`. That is what the first prod migration
# wrote. A listing row additionally needs `created`, which is what the runs
# screen sorts and `--since`-filters on.

def _entity(kind: str, **over) -> dict:
    """One entity dict of `kind`, with every field its builder reads."""
    common = {"id": f"{kind[:4]}-0000", "lib": REAL, "slug": "subject-a",
              "created": "2026-01-01T00:00:00+00:00",
              "updated": "2026-01-02T00:00:00+00:00"}
    shapes = {
        "character": {**common, "display_name": "Subject A", "fictional": True,
                      "schema_version": 3, "root": "node-root-a", "hero": None,
                      "default_set": [], "profile": {}, "refs": []},
        "project": {**common, "title": "Subject A", "description": "",
                    "root": "node-root-a", "hero": None, "characters": [],
                    "counts": {"runs": 0, "scenes": 0, "movies": 0}},
        "run": {**common, "project": "proj-0000", "status": "succeeded",
                "run_kind": "image", "engine": "replicate", "model": "m",
                "prediction_id": "p", "submitted": None, "completed": None,
                "bindings": {}, "characters": [], "folder": "node-folder-a",
                "outputs": [], "lineage": [], "cost": None, "error": None,
                "payload": {}},
        "scene": {**common, "project": "proj-0000", "title": "Scene",
                  "status": "cut", "folder": "node-folder-a", "output": None,
                  "document": {}, "shots": []},
        "movie": {**common, "project": "proj-0000", "title": "Movie",
                  "status": "cut", "folder": "node-folder-a", "output": None,
                  "document": {}, "scenes": []},
    }
    return {**shapes[kind], **over}


def _written(kind: str) -> list[dict]:
    """Every document `kind`'s builder would put, unmarshalled."""
    return [ddbc.from_item(action["Put"]["Item"])
            for group in cm.GROUPS[kind](_entity(kind))
            for action in group if "Put" in action]


@pytest.mark.parametrize("kind", ["character", "project", "run", "scene", "movie"])
def test_the_entity_record_carries_its_id_as_an_attribute(kind):
    """`pk` is not enough — `_entity` drops it and the API reads `record["id"]`."""
    meta = [doc for doc in _written(kind) if doc["sk"] == "META"]
    assert len(meta) == 1, f"{kind} must write exactly one META row"
    assert meta[0].get("id") == _entity(kind)["id"], \
        f"a {kind} record without `id` makes every listing 500"


@pytest.mark.parametrize("kind", ["run", "scene", "movie"])
def test_the_listing_row_carries_id_and_created(kind):
    """The runs screen sorts on `created` and links on `id`; it reads neither key."""
    entity = _entity(kind)
    listing = [doc for doc in _written(kind)
               if doc["pk"].startswith("PROJ#") and doc["sk"].startswith(
                   f"{cm.PARTITION[kind]}#")]
    assert len(listing) == 1, f"{kind} must write exactly one listing row"
    assert listing[0].get("id") == entity["id"]
    assert listing[0].get("created") == entity["created"], \
        "a listing row with no `created` sorts as '' and vanishes under --since"


def test_a_runs_updated_comes_off_the_document_not_a_clock():
    """Latest timestamp the run carries, falling back rather than dating to now."""
    assert cm.run_updated(_entity("run", completed="C", submitted="S")) == "C"
    assert cm.run_updated(_entity("run", completed=None, submitted="S")) == "S"
    assert cm.run_updated(_entity("run", completed=None, submitted=None)) == \
        _entity("run")["created"]






# ── reseat: copy, repoint, delete ───────────────────────────────────────────
#
# **`reseat_one` shipped with two bugs in four lines and no test that ran it.**
# `ExpressionAttributeValues2=None` is not a boto3 parameter, and the condition
# referenced a `:old` nothing defined — so every entry raised
# `ParamValidationError` *after* its copy had already landed. Against prod that
# was 257 copies, 0 rows repointed, 0 old objects removed.
#
# The only reseat test before these asserted that `--library` was a flag. So
# these exercise the function against moto: the happy path, the condition that
# makes the copy and the repoint describe one object, and the ordering the
# docstring rests on.

def _file_node(ddb, node_id: str, blob_key: str) -> None:
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": f"NODE#{node_id}", "sk": "META", "node_id": node_id, "lib": REAL,
         "kind": "file", "name": "x.png", "blob_key": blob_key}))


def _blob_key(ddb, node_id: str) -> str:
    return ddbc.from_item(ddb.get_item(
        TableName=ddbc.table(),
        Key=ddbc.to_item({"pk": f"NODE#{node_id}", "sk": "META"}))["Item"])["blob_key"]


def _keys(s3) -> list[str]:
    from studio_pipeline.adapters import s3 as s3c
    return sorted(o["Key"] for o in
                  s3.list_objects_v2(Bucket=s3c.bucket()).get("Contents", []))


def _entry(node="node-1", frm="characters/subject-a/reference/face/x.png",
           to="characters/char-1/node-1.png") -> dict:
    return {"node": node, "from": frm, "to": to}


def _seed(bucket, catalog_table, entry):
    from studio_pipeline.adapters import s3 as s3c
    bucket.put_object(Bucket=s3c.bucket(), Key=entry["from"], Body=b"png-bytes")
    _file_node(catalog_table, entry["node"], entry["from"])


def test_reseat_copies_repoints_and_deletes(bucket, catalog_table):
    """The whole point, and the regression test for both shipped bugs."""
    entry = _entry()
    _seed(bucket, catalog_table, entry)

    assert cm.reseat_one(bucket, catalog_table, entry) is None

    assert _keys(bucket) == [entry["to"]], "old object must be gone, new one there"
    assert _blob_key(catalog_table, entry["node"]) == entry["to"]
    from studio_pipeline.adapters import s3 as s3c
    assert bucket.get_object(Bucket=s3c.bucket(), Key=entry["to"])["Body"].read() \
        == b"png-bytes", "the bytes must survive the move"


def test_reseat_refuses_a_row_that_moved_under_it(bucket, catalog_table):
    """`blob_key = :old` is what ties the copy and the repoint to one object.

    Without the condition this would point the row at bytes copied from where
    it used to be — the failure the condition exists to make impossible, and
    the one the undefined `:old` meant was never actually guarded.
    """
    entry = _entry()
    _seed(bucket, catalog_table, entry)
    _file_node(catalog_table, entry["node"], "blobs/somewhere-else")  # a concurrent writer

    problem = cm.reseat_one(bucket, catalog_table, entry)

    assert problem is not None and "ConditionalCheckFailed" in problem
    assert _blob_key(catalog_table, entry["node"]) == "blobs/somewhere-else", \
        "the row another writer set must not be overwritten"
    assert entry["from"] in _keys(bucket), \
        "a failed repoint must not reach the delete"


def test_reseat_leaves_the_bytes_when_the_repoint_fails(bucket, catalog_table):
    """Copy, then repoint, then delete — a break anywhere loses no bytes."""
    entry = _entry(node="node-missing")
    from studio_pipeline.adapters import s3 as s3c
    bucket.put_object(Bucket=s3c.bucket(), Key=entry["from"], Body=b"png-bytes")
    # No row at all: the conditional update cannot match, so the delete is
    # never reached and both copies of the bytes are still there.
    assert cm.reseat_one(bucket, catalog_table, entry) is not None
    assert entry["from"] in _keys(bucket)
    assert entry["to"] in _keys(bucket)


def test_reseat_is_idempotent_after_an_interrupted_copy(bucket, catalog_table):
    """Interrupted after the copy: the row still names the old key, so a re-run
    repeats the copy onto the same key and finishes the job."""
    entry = _entry()
    _seed(bucket, catalog_table, entry)
    from studio_pipeline.adapters import s3 as s3c
    bucket.copy_object(Bucket=s3c.bucket(), Key=entry["to"],
                       CopySource={"Bucket": s3c.bucket(), "Key": entry["from"]})

    assert cm.reseat_one(bucket, catalog_table, entry) is None
    assert _keys(bucket) == [entry["to"]]
    assert _blob_key(catalog_table, entry["node"]) == entry["to"]


def test_reseat_never_names_a_version(bucket, catalog_table, monkeypatch):
    """A `VersionId` on the delete is what turns a tombstone into a removal.

    The grant is deliberately not held, so this cannot be caught in production
    — only here.
    """
    entry = _entry()
    _seed(bucket, catalog_table, entry)
    seen = {}
    real = bucket.delete_object
    monkeypatch.setattr(bucket, "delete_object",
                        lambda **kw: (seen.update(kw), real(**kw))[1])

    cm.reseat_one(bucket, catalog_table, entry)

    assert "VersionId" not in seen


# ── the key is flat, and still not authoritative ────────────────────────────
#
# `<owner_kind>/<owner_id>/<node_id><ext>`. Three segments, and the same string
# `services/catalog.py::blob_key_for` stamps at creation — a second opinion
# about what a key should be IS drift, so the two agreeing is the property, not
# a coincidence worth restating in two places.
#
# `desired_key` spent a while building `<owner_kind>/<owner_id>/<folders>/<name>`
# instead, on the argument that structure is free once nothing parses a key. It
# was not free. The leaf was the file's own name, so a bucket listing spelled out
# character names again — hard rule #1, one segment lower than the slug D2
# removed — and every rename drifted a key, which made `reseat` endless. Both
# are gone with the folders.
#
# What that gave up is a bucket a person can read: a listing is UUIDs now and the
# catalog is the only thing that can say what a byte is. Accepted deliberately;
# the table's PITR and deletion protection are the whole safety net and nothing
# writes a manifest into the bucket.
#
# The safety of a key in EITHER shape rests on one property, which is what the
# last test here guards: **nothing parses a blob_key.**

def _tree_for_key(ddb):
    """A character with a nested pool, and one file at the bottom of it."""
    _library(ddb, REAL, "Studio", "node-root")
    _folder(ddb, "node-chars", "node-root", "characters")
    _folder(ddb, "node-a", "node-chars", "subject-a")
    _folder(ddb, "node-ref", "node-a", "reference")
    _folder(ddb, "node-face", "node-ref", "face")
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": "NODE#node-img", "sk": "META", "node_id": "node-img",
         "parent_id": "node-face", "lib": REAL, "kind": "file",
         "name": "IMG_4580.png", "blob_key": "blobs/node-img",
         "content_type": "image/png",
         "path": "node-root/node-chars/node-a/node-ref/node-face"}))


def _plan_with_one_character(ddb):
    cat = cm.read_catalog(ddb, REAL)
    return {"lib": REAL, "catalog": cat, "characters": [
        {"id": "char-1", "root": "node-a", "slug": "subject-a"}], "projects": []}


def test_the_key_names_the_owner_and_the_node_and_nothing_else(catalog_table):
    """Three segments. `reference/face/` and the filename are the tree's job.

    The node sits four folders deep under a character and none of that reaches
    the key. `IMG_4580.png` in particular does not: a leaf that is the file's
    own name is how a listing of this bucket started spelling out character
    names again.
    """
    _tree_for_key(catalog_table)
    plan = _plan_with_one_character(catalog_table)
    nodes = plan["catalog"]["nodes"]

    assert cm.desired_key(plan, nodes, nodes["node-img"]) == \
        "characters/char-1/node-img.png"


def test_renaming_a_file_does_not_drift_its_key(catalog_table):
    """**The reason the folders went.** A rename is a row write and nothing else.

    Under the descriptive scheme the leaf was the node's `name`, so renaming a
    file changed where its bytes belonged and `verify` reported it — which made
    drift the normal state of any library anyone worked in, and `reseat` a chore
    with no end. The leaf is the node id now and no rename touches it.
    """
    _tree_for_key(catalog_table)
    plan = _plan_with_one_character(catalog_table)
    nodes = plan["catalog"]["nodes"]
    before = cm.desired_key(plan, nodes, nodes["node-img"])

    nodes["node-img"]["name"] = "porch-wave.png"

    assert cm.desired_key(plan, nodes, nodes["node-img"]) == before
    assert cm.key_drift(plan, nodes) == \
        [{"node": "node-img", "from": "blobs/node-img", "to": before}]


def test_the_extension_is_the_only_thing_the_name_contributes(catalog_table):
    """Decoration for the S3 console, and lowercased the way the API writes it.

    `content_type` on the row is authoritative. A name with no extension gets a
    key with none — the alternative is guessing one from the content type, which
    is a second opinion about a string a signature is scoped to.
    """
    _tree_for_key(catalog_table)
    plan = _plan_with_one_character(catalog_table)
    nodes = plan["catalog"]["nodes"]

    nodes["node-img"]["name"] = "IMG_4580.PNG"
    assert cm.desired_key(plan, nodes, nodes["node-img"]).endswith("/node-img.png")

    nodes["node-img"]["name"] = "LICENCE"
    assert cm.desired_key(plan, nodes, nodes["node-img"]) == "characters/char-1/node-img"


def test_the_two_key_builders_agree():
    """`desired_key` and the API's `blob_key_for` must produce the same string.

    They are the same decision made in two packages — the pipeline does not
    import the backend and never has — and if they disagree, every key the API
    stamps is drift the moment it is written and `reseat` rewrites the library on
    every run, forever. Read as source text because that is the only seam
    available across the two, and the same technique
    `test_no_caller_splits_a_blob_key` already uses.
    """
    import pathlib
    import re

    backend = (pathlib.Path(cm.__file__).parents[4] / "backend" / "studio_core"
               / "services" / "catalog.py").read_text()
    stamped = re.search(r"def blob_key_for\(.*?\n    return ([^\n]+)", backend, re.S)
    assert stamped, "blob_key_for is gone or no longer returns on one line"
    literal = stamped.group(1).strip()

    # The SHAPE, not a diff of two f-strings: three segments, the owner in the
    # second, the node id in the third. A FOURTH is the descriptive scheme
    # coming back, and the fourth is the one that leaked names.
    segments = literal.split("/")
    assert len(segments) == 3, literal
    assert "owner_id" in segments[1], literal
    assert "node_id" in segments[2], literal


def test_material_outside_any_entity_is_filed_under_the_library(catalog_table):
    """The pose plates. Owned by no character and no project, so the library's.

    `config/pose/` is the tree's, not the key's — the plates are reached by
    walking nodes like everything else. The one thing the key still has to get
    right is which of the three prefixes it lands under.
    """
    _library(catalog_table, REAL, "Studio", "node-root")
    _folder(catalog_table, "node-config", "node-root", "config")
    _folder(catalog_table, "node-pose", "node-config", "pose")
    catalog_table.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": "NODE#node-plate", "sk": "META", "node_id": "node-plate",
         "parent_id": "node-pose", "lib": REAL, "kind": "file",
         "name": "front.png", "blob_key": f"libraries/{REAL}/node-plate.png",
         "path": "node-root/node-config/node-pose"}))
    cat = cm.read_catalog(catalog_table, REAL)
    plan = {"lib": REAL, "catalog": cat, "characters": [], "projects": []}

    assert cm.desired_key(plan, cat["nodes"], cat["nodes"]["node-plate"]) == \
        f"libraries/{REAL}/node-plate.png"


def test_no_caller_splits_a_blob_key():
    """**The property the whole scheme rests on.**

    A descriptive key is safe only while it is decoration. The moment anything
    derives truth from one, a rename is a data migration again and the entity
    model is back where it started — which is exactly the bug class that cost
    69 stranded records and `domain/rewrite.py`.

    So: no module may take a `blob_key` apart. `desired_key` BUILDS one and is
    not exempt by kindness — it is exempt because it never reads an existing key
    to decide anything.

    **`is_api_blob` is the one exemption, and it is narrow enough to name.** It
    splits a key to read its SHAPE — is the first segment one of the three owner
    prefixes, does the second start with an id prefix — and derives no value from
    it at all: not the owner, not the path, not the filename. A rename does not
    change that shape and neither does a move, so the hazard this test exists to
    prevent cannot arise from it. It has to read something, because a signed
    upload must refuse a key written before this catalog existed (#309), and the
    shape is the only signal that survives a node moving.

    Exempted BY NAME rather than by loosening the pattern, so the next split
    still fails here and has to argue for itself.
    """
    import pathlib
    import re

    roots = [pathlib.Path(cm.__file__).parents[1],                      # pipeline
             pathlib.Path(cm.__file__).parents[4] / "backend" / "studio_core"]
    taking_apart = re.compile(
        r"blob_key[^\n]*?\.(?:split|rsplit|partition|removeprefix|removesuffix)\(|"
        r"(?:splitext|dirname|basename)\([^)]*blob_key")

    # `<file>::<function>` — see the docstring for why this one is safe.
    exempt = {"catalog.py::is_api_blob"}

    def enclosing(lines: list[str], index: int) -> str:
        """The `def` this line sits under, for matching against `exempt`."""
        for candidate in range(index, -1, -1):
            stripped = lines[candidate].lstrip()
            if stripped.startswith("def ") and not lines[candidate].startswith(" " * 8):
                return stripped[4:].split("(")[0]
        return "?"

    offenders, claimed = [], set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            lines = path.read_text().splitlines()
            for number, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                if taking_apart.search(line):
                    where = f"{path.name}::{enclosing(lines, number - 1)}"
                    if where in exempt:
                        claimed.add(where)
                        continue
                    offenders.append(f"{where} (line {number}): {line.strip()}")

    assert not offenders, (
        "a blob_key is a pointer, not a path — nothing may parse one:\n  "
        + "\n  ".join(offenders))
    # An exemption nobody uses is an exemption nobody has re-argued for.
    assert claimed == exempt, f"stale exemption(s): {sorted(exempt - claimed)}"


# ── an already-migrated library is planned from its rows ────────────────────
#
# `apply` CONSUMES the legacy layout: a character's bible becomes the `profile`
# attribute on its record and the document goes. So the walk that reads that
# layout finds adopted folders and no documents, and plans nothing — which made
# every phase after `plan` unrunnable, and `reseat` actively dangerous.

def _adopted_character(ddb):
    """A library whose one character has already been migrated.

    Root folder adopted (it carries `entity`), record written, slug claimed,
    one reference row — and NO `profile.yaml`, because `apply` consumed it.
    """
    _library(ddb, REAL, "Studio", "node-root")
    _folder(ddb, "node-chars", "node-root", "characters")
    _folder(ddb, "node-a", "node-chars", "subject-a")
    _file(ddb, "node-img", "node-a", "IMG_4580.png", "blobs/node-img")
    # `path` is the materialised ancestor list and `desired_key` walks it to find
    # the owner. Written explicitly because the shared helpers do not: a node
    # with no `path` has no ancestors, so every key built from it falls through
    # to the library and this fixture would pass for the wrong reason.
    for node_id, path in (("node-chars", "node-root"),
                          ("node-a", "node-root/node-chars"),
                          ("node-img", "node-root/node-chars/node-a")):
        ddb.update_item(TableName=ddbc.table(),
                        Key=ddbc.to_item({"pk": f"NODE#{node_id}", "sk": "META"}),
                        UpdateExpression="SET #p = :p",
                        ExpressionAttributeNames={"#p": "path"},
                        ExpressionAttributeValues=ddbc.to_item({":p": path}))
    ddb.update_item(TableName=ddbc.table(),
                    Key=ddbc.to_item({"pk": "NODE#node-a", "sk": "META"}),
                    UpdateExpression="SET #e = :e",
                    ExpressionAttributeNames={"#e": "entity"},
                    ExpressionAttributeValues=ddbc.to_item({":e": "char-0001"}))
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": "CHAR#char-0001", "sk": "META", "id": "char-0001", "lib": REAL,
         "slug": "subject-a", "root": "node-a", "default_set": [],
         "created": "2026-01-01T00:00:00+00:00"}))
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": "CHAR#char-0001", "sk": "REF#node-img", "lib": REAL,
         "group": "face", "order": 1000}))


def test_an_adopted_folder_is_not_an_unparseable_document(bucket, catalog_table):
    """**The gate that made every later phase unrunnable.**

    The walk wants `profile.yaml` under a character's folder. `apply` consumed
    it. Reporting that as UNPARSEABLE calls a migration success a migration
    failure — and `_session` dies on a non-zero count for every phase except
    `plan`, so `verify` and `reseat` could never run again.
    """
    _adopted_character(catalog_table)
    plan = cm.build_plan(bucket, catalog_table, REAL)

    assert plan["unparseable"] == []
    assert [c["id"] for c in plan["characters"]] == ["char-0001"]
    assert plan["characters"][0]["adopted"] is True
    assert plan["characters"][0]["root"] == "node-a"
    # The child rows the record does not carry as attributes, read back off
    # their own rows because `report` counts them.
    assert plan["characters"][0]["refs"] == [{"node": "node-img"}]


def test_reseat_files_an_adopted_library_under_its_owner(bucket, catalog_table):
    """**The reason this is a data-loss bug and not a papercut.**

    `owners()` is built from `plan["characters"]` and `plan["projects"]`. With
    both empty every file falls through to the library branch of `desired_key`,
    so a `reseat` re-files the WHOLE library under `libraries/` — 1200 objects
    in production — instead of the ones that had drifted.

    The empty plan below is exactly what `build_plan` returned before adopted
    entities were read back, so this asserts the old behaviour as the hazard and
    the new behaviour as the fix.
    """
    _adopted_character(catalog_table)
    nodes = cm.read_catalog(catalog_table, REAL)["nodes"]

    blind = {"lib": REAL, "characters": [], "projects": []}
    assert cm.desired_key(blind, nodes, nodes["node-img"]) == \
        f"libraries/{REAL}/node-img.png"

    plan = cm.build_plan(bucket, catalog_table, REAL)
    assert cm.desired_key(plan, nodes, nodes["node-img"]) == \
        "characters/char-0001/node-img.png"


# `test_apply_writes_nothing_for_an_adopted_entity` was here and came across in
# the merge with #503. It exercised `phase_apply`, which this branch retires
# along with `plan` and `backfill` — prod carries its entity rows and nothing in
# the product can produce a library that needs raising. The two #503 tests that
# matter, `test_an_adopted_folder_is_not_an_unparseable_document` and
# `test_reseat_files_an_adopted_library_under_its_owner`, cover code that stayed
# and are directly above.




# ── edges ───────────────────────────────────────────────────────────────────
#
# The backfill for records made before a relationship was a row. Every
# assertion here is about telling an EDGE row from a LISTING row, because they
# share a prefix and only one of them is this command's business.


def _put(ddb, doc):
    ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item(doc))


def _record(ddb, pk, **fields):
    _put(ddb, {"pk": pk, "sk": "META", "lib": REAL, **fields})


def test_a_movie_gets_an_edge_for_every_scene_it_cuts(catalog_table):
    _record(catalog_table, "MOVIE#movie-1", scenes=["scene-1", "scene-2"])

    missing = cm.edge_plan(catalog_table)["missing"]

    assert set(missing) == {("MOVIE#movie-1", "SCENE#scene-1"),
                            ("MOVIE#movie-1", "SCENE#scene-2")}


def test_a_reprise_wants_one_edge_not_two(catalog_table):
    """The list keeps the duplicate; an edge is set membership."""
    _record(catalog_table, "MOVIE#movie-1", scenes=["scene-1", "scene-1"])

    assert list(cm.edge_plan(catalog_table)["missing"]) == [
        ("MOVIE#movie-1", "SCENE#scene-1")]


def test_a_scene_gets_an_edge_for_the_run_each_shot_binds(catalog_table):
    _record(catalog_table, "SCENE#scene-1")
    _put(catalog_table, {"pk": "SCENE#scene-1", "sk": "SHOT#shot-01", "run": "run-1"})
    _put(catalog_table, {"pk": "SCENE#scene-1", "sk": "SHOT#shot-02"})  # planned

    assert list(cm.edge_plan(catalog_table)["missing"]) == [
        ("SCENE#scene-1", "RUN#run-1")]


def test_a_run_gets_an_edge_to_its_parent(catalog_table):
    _record(catalog_table, "RUN#run-2", lineage={"from_run": "run-1", "from_output": None})
    _record(catalog_table, "RUN#run-1", lineage={"from_run": None, "from_output": None})

    assert list(cm.edge_plan(catalog_table)["missing"]) == [("RUN#run-2", "RUN#run-1")]


def test_a_listing_row_is_not_mistaken_for_an_edge(catalog_table):
    """`RUN#<created>#<id>` under a project. Two separators, not one.

    Matching on the prefix alone would sweep every listing row in the library
    into this and rewrite it — they are the rows a project's grid pages
    through, and they carry a projection an edge row does not have.
    """
    _record(catalog_table, "MOVIE#movie-1", scenes=["scene-1"])
    _put(catalog_table, {"pk": "PROJ#proj-1", "sk": "RUN#2026-08-27T00:00:00Z#run-1",
                         "lib": REAL, "id": "run-1", "status": "succeeded"})

    plan = cm.edge_plan(catalog_table)
    assert ("PROJ#proj-1", "RUN#2026-08-27T00:00:00Z#run-1") not in plan["present"]
    assert list(plan["missing"]) == [("MOVIE#movie-1", "SCENE#scene-1")]


def test_an_edge_that_is_already_there_is_not_written_again(catalog_table):
    _record(catalog_table, "MOVIE#movie-1", scenes=["scene-1"])
    _put(catalog_table, {"pk": "MOVIE#movie-1", "sk": "SCENE#scene-1", "lib": REAL})

    assert cm.edge_plan(catalog_table)["missing"] == {}


def test_the_backfill_is_a_dry_run_until_it_is_applied(catalog_table):
    _record(catalog_table, "MOVIE#movie-1", scenes=["scene-1"])

    result = CliRunner().invoke(cli.main, ["catalog", "edges"])
    assert result.exit_code == 0, result.output
    assert "dry run" in result.output
    assert cm.edge_plan(catalog_table)["missing"] != {}

    applied = CliRunner().invoke(cli.main, ["catalog", "edges", "--apply"])
    assert applied.exit_code == 0, applied.output
    assert cm.edge_plan(catalog_table)["missing"] == {}


def test_the_backfill_can_be_run_twice(catalog_table):
    """Additive and idempotent, which is what makes it safe to re-run."""
    _record(catalog_table, "MOVIE#movie-1", scenes=["scene-1"])

    for _ in range(2):
        assert CliRunner().invoke(
            cli.main, ["catalog", "edges", "--apply"]).exit_code == 0

    assert cm.edge_plan(catalog_table)["missing"] == {}


def test_verify_reports_a_missing_edge(catalog_table):
    """Reported, never repaired. `catalog edges` writes; verify counts."""
    _record(catalog_table, "MOVIE#movie-1", scenes=["scene-1"])

    plan = cm.edge_plan(catalog_table)
    assert list(plan["missing"]) == [("MOVIE#movie-1", "SCENE#scene-1")]


def test_verify_reports_an_edge_to_a_record_that_is_gone(catalog_table):
    """A stale edge is a link to nothing — the other half of the same check."""
    _record(catalog_table, "MOVIE#movie-1", scenes=[])
    _put(catalog_table, {"pk": "MOVIE#movie-1", "sk": "SCENE#scene-gone", "lib": REAL})

    assert cm.edge_plan(catalog_table)["stale"] == [("MOVIE#movie-1", "SCENE#scene-gone")]


def test_involvement_links_are_not_called_stale(catalog_table):
    """`PROJ#/CHAR#` is a set a person edits — nothing derives it.

    A checker that compared it against a derived set would call every
    involvement link in the library stale and bury the two real findings.
    """
    _record(catalog_table, "PROJ#proj-1")
    _put(catalog_table, {"pk": "PROJ#proj-1", "sk": "CHAR#char-1", "lib": REAL})
    _put(catalog_table, {"pk": "RUN#run-1", "sk": "CHAR#char-1", "lib": REAL})

    plan = cm.edge_plan(catalog_table)
    assert plan["stale"] == []
    assert plan["missing"] == {}


def test_a_run_boarded_into_a_panel_is_an_edge_too(catalog_table):
    """The only shape the production library actually has.

    Every shot there has an empty `run` — that field is the motion render —
    while the boarded stills carry a run per panel. Deriving from `run` alone
    found nothing in a library holding twenty-five of them.
    """
    _record(catalog_table, "SCENE#scene-1")
    _put(catalog_table, {"pk": "SCENE#scene-1", "sk": "SHOT#shot-01",
                         "panels": [{"n": 1, "run": "run-1"}, {"n": 2, "run": "run-2"}]})

    assert set(cm.edge_plan(catalog_table)["missing"]) == {
        ("SCENE#scene-1", "RUN#run-1"), ("SCENE#scene-1", "RUN#run-2")}


def test_a_shot_that_continues_from_a_run_is_an_edge_too(catalog_table):
    _record(catalog_table, "SCENE#scene-1")
    _put(catalog_table, {"pk": "SCENE#scene-1", "sk": "SHOT#shot-01",
                         "opens_on": {"node": "node-x", "from_run": "run-9"}})

    assert list(cm.edge_plan(catalog_table)["missing"]) == [("SCENE#scene-1", "RUN#run-9")]


def test_a_panel_with_no_run_yet_is_not_an_edge(catalog_table):
    """A planned panel has `run: null`. It is not a link to nothing."""
    _record(catalog_table, "SCENE#scene-1")
    _put(catalog_table, {"pk": "SCENE#scene-1", "sk": "SHOT#shot-01",
                         "panels": [{"n": 1, "run": None}],
                         "opens_on": {"node": None, "from_run": None}})

    assert cm.edge_plan(catalog_table)["missing"] == {}
