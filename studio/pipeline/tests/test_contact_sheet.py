"""`studio contact-sheet --character` — gathering a pool through the store (#305).

The grid itself is covered in `test_shoot.py`; what is new here is where the
tiles come from. A listing is one level deep and `reference` — this command's
default pool — holds group folders and no images of its own. So the walk, and
the names it produces, are the whole subject of this file.

The walk is now by NODE ID rather than by prefix: it starts from the pool folder
the character record names and descends through `store.children_of`. The
relative path survives only as a caption, which is exactly the split the entity
model draws — an id to fetch by, a name to read.
"""

from __future__ import annotations

import pathlib

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import contact_sheet as SHEET

NAME = "subject-a"


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def test_a_pool_of_group_folders_is_gathered_recursively(library, tmp_path):
    """**The load-bearing one.** `reference/` holds only `face/` and `body/`.

    A one-level listing finds no images at all and the default invocation exits
    saying the pool is empty — for a character whose whole reference library is
    there.
    """
    out = tmp_path / "sheet.png"
    result = _run("contact-sheet", "--character", NAME, "--out", str(out))

    assert result.exit_code == 0, result.output
    assert "3 tiles" in result.output
    assert out.exists()


def test_the_group_survives_into_the_local_name(library, tmp_path):
    """`face/<name>_1` and `body/<name>_1` are two images with one basename.

    Downloaded under bare basenames they land on one path: the second overwrites
    the first, and the sheet shows that image twice under one caption. The
    caption is the local filename, so the group has to be in it.
    """
    paths = SHEET._gather_from_store(NAME, "reference", str(tmp_path))

    assert [pathlib.Path(p).name for p in paths] == [
        "body_full-length.webp",
        "face_front-neutral.webp",
        "face_three-quarter.webp",
    ]
    assert all(pathlib.Path(p).exists() for p in paths)


def test_a_pool_that_is_not_there_says_so(library, tmp_path):
    """A character with no `seed/` is a clean refusal, not a traceback."""
    result = _run("contact-sheet", "--character", "subject-b",
                  "--folder", "seed", "--out", str(tmp_path / "sheet.png"))

    assert result.exit_code == 1
    assert "no images under subject-b/seed" in result.output


def test_a_refused_pool_is_not_an_empty_one(library, monkeypatch, tmp_path):
    """A 403 must not read as "this character has no images".

    The forgiving read is gone from this path — a pool folder is resolved off
    the character record and created if absent, so there is no 404 left to
    swallow — but the property it protected still has to hold: a refusal is a
    different fact from an empty pool, and three modules once lost that
    distinction by catching bare `Exception`.
    """
    def refused(_node_id):
        raise api.Forbidden("not a member of this library", 403)

    monkeypatch.setattr(store, "children_of", refused)

    with pytest.raises(api.Forbidden):
        SHEET._gather_from_store(NAME, "reference", str(tmp_path))


def test_contact_sheet_can_sheet_one_group_of_a_pool(library, tmp_path):
    """Eyeballing `seed/current/` used to mean downloading it by hand and coming
    back through `--src` — the workaround this command exists to remove."""
    record = CHARACTER.resolve("subject-a")
    seed = CHARACTER.pool_folder(record, "seed")
    group = store.ensure_child_folder(seed["id"], "current")
    library.fake.put_file(group["id"], "in-the-group.png", b"png-bytes")

    out = tmp_path / "sheet.png"
    result = _run("contact-sheet", "--character", "subject-a",
                  "--folder", "seed", "--group", "current", "--out", str(out))

    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "1 tiles" in result.output or "(1 tile" in result.output
