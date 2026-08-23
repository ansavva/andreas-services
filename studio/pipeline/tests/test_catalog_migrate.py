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
from studio_pipeline.maintenance import catalog_migrate as cm

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

    result = CliRunner().invoke(cli.main, ["catalog", "migrate", "plan"])
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
    """`plan` alone would be a trap: the phases are separate invocations, so a
    flag on one and not the next is a migration that plans one library and
    applies another."""
    migrate = cli.main.get_command(None, "catalog").get_command(None, "migrate")
    for name in ("plan", "apply", "verify"):
        command = migrate.get_command(None, name)
        flags = {flag for p in command.params for flag in getattr(p, "opts", [])}
        assert "--library" in flags, f"studio catalog migrate {name}"
    reseat = cli.main.get_command(None, "catalog").get_command(None, "reseat")
    assert "--library" in {f for p in reseat.params for f in getattr(p, "opts", [])}


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


def test_backfill_adds_only_what_is_missing_and_overwrites_nothing(catalog_table):
    """The repair path: a row an older version of this file wrote incompletely."""
    catalog_table.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": "CHAR#char-0000", "sk": "META", "lib": REAL, "slug": "renamed"}))

    added = cm.backfill(catalog_table, {"pk": "CHAR#char-0000", "sk": "META",
                                        "id": "char-0000", "slug": "subject-a",
                                        "lib": REAL}, apply=True)

    assert added == ["id"], "only the absent attribute is written"
    stored = ddbc.from_item(catalog_table.get_item(
        TableName=ddbc.table(),
        Key=ddbc.to_item({"pk": "CHAR#char-0000", "sk": "META"}))["Item"])
    assert stored["id"] == "char-0000"
    assert stored["slug"] == "renamed", \
        "a slug edited through the app since the migration must survive repair"


def test_backfill_reports_without_writing_when_not_applying(catalog_table):
    catalog_table.put_item(TableName=ddbc.table(), Item=ddbc.to_item(
        {"pk": "CHAR#char-0000", "sk": "META", "lib": REAL}))

    assert cm.backfill(catalog_table, {"pk": "CHAR#char-0000", "sk": "META",
                                       "id": "char-0000"}, apply=False) == ["id"]
    stored = ddbc.from_item(catalog_table.get_item(
        TableName=ddbc.table(),
        Key=ddbc.to_item({"pk": "CHAR#char-0000", "sk": "META"}))["Item"])
    assert "id" not in stored, "a dry run must not write"
