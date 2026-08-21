"""`studio contact-sheet --character` — gathering a pool through the store (#305).

The grid itself is covered in `test_shoot.py`; what is new here is where the
tiles come from. `list_keys` listed a prefix recursively and the store's `files`
lists one level, and `reference` — this command's default pool — holds group
folders and no images of its own. So the walk, and the names it produces, are
the whole subject of this file.
"""

from __future__ import annotations

import pathlib

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store
from studio_pipeline.domain import contact_sheet as SHEET

NAME = "subject-a"


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def test_a_pool_of_group_folders_is_gathered_recursively(media_bucket, tmp_path):
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


def test_the_group_survives_into_the_local_name(media_bucket, tmp_path):
    """`face/<name>_1` and `body/<name>_1` are two images with one basename.

    Downloaded under bare basenames they land on one path: the second overwrites
    the first, and the sheet shows that image twice under one caption. The
    caption is the local filename, so the group has to be in it.
    """
    paths = SHEET._gather_from_store(NAME, "reference", str(tmp_path))

    assert [pathlib.Path(p).name for p in paths] == [
        f"body_{NAME}_1.webp",
        f"face_{NAME}_1.webp",
        f"face_{NAME}_2.webp",
    ]
    assert all(pathlib.Path(p).exists() for p in paths)


def test_a_pool_that_is_not_there_says_so(media_bucket, tmp_path):
    """A character with no `seed/` is a clean refusal, not a traceback."""
    result = _run("contact-sheet", "--character", "subject-b",
                  "--folder", "seed", "--out", str(tmp_path / "sheet.png"))

    assert result.exit_code == 1
    assert "no images under characters/subject-b/seed" in result.output


def test_a_refused_pool_is_not_an_empty_one(media_bucket, monkeypatch, tmp_path):
    """A 403 must not read as "this character has no images".

    `children_or_empty` swallows a 404 and only a 404 — the distinction three
    modules lost by catching bare `Exception`.
    """
    def refused(_path):
        raise api.Forbidden("not a member of this library", 403)

    monkeypatch.setattr(store, "children", refused)

    with pytest.raises(api.Forbidden):
        SHEET._gather_from_store(NAME, "reference", str(tmp_path))
