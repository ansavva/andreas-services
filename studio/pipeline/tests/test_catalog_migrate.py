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
