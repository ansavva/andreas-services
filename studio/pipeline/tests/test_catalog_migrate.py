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
