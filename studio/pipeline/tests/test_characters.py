"""The character record through the API (#305) — mainly, what replaced the ETag.

`characters/profile.py` carried an optimistic-concurrency check built on the S3
ETag: read it, and refuse to write if it moved. The catalog exposes no ETag and
deliberately never will — `blob_key` does not leave the API — so the check now
compares the node's `updated_at`.

**That check is the reason this file exists.** It is what stops `edit --push` of
an hour-old local copy from reverting every description the index commands wrote
in the meantime, and it is written `if recorded and current and ...` — so
anything that makes the version unreadable turns the guard OFF rather than
failing. It has to be tested at the seam, not through the moto shim, because the
shim is exactly what hid that once already.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store
from studio_pipeline.domain.characters import base, profile, refs

NAME = "subject-a"


@pytest.fixture
def resolves(monkeypatch):
    """`store.resolve` answering from a mutable record. Returns the record."""
    node = {"id": "node-bible", "kind": "file", "updated_at": "2026-08-20T10:00:00.000001+00:00"}

    def _resolve(_path):
        if node is None:
            raise api.NotFound("no such node", 404)
        return dict(node)

    monkeypatch.setattr(store, "resolve", _resolve)
    return node


# ──────────────────────────── the version token ────────────────────────────


def test_the_version_is_the_nodes_updated_at(resolves):
    assert profile.remote_version(NAME) == resolves["updated_at"]


def test_a_character_with_no_bible_has_no_version(monkeypatch):
    def _resolve(_path):
        raise api.NotFound("no such node", 404)

    monkeypatch.setattr(store, "resolve", _resolve)

    assert profile.remote_version(NAME) is None


def test_a_refusal_is_not_a_missing_bible(monkeypatch):
    """**This caught every exception, and the consequence was not a wrong answer.**

    A missing version disables the conflict check, so a 403 here would have
    turned the guard off silently rather than reporting it — the write would
    then proceed against a bible the caller could not even read.
    """
    def _resolve(_path):
        raise api.Forbidden("not your library", 403)

    monkeypatch.setattr(store, "resolve", _resolve)

    with pytest.raises(api.Forbidden):
        profile.remote_version(NAME)


def test_writing_with_a_stale_version_is_refused(resolves, monkeypatch):
    written = []
    monkeypatch.setattr(store, "folder", lambda path: {"id": "node-folder"})
    monkeypatch.setattr(store, "write", lambda *a, **k: written.append(a))

    with pytest.raises(SystemExit):
        profile.write_profile(NAME, {"name": NAME}, "a-version-from-before")

    assert written == [], "the refusal has to come before the write, not after"


def test_writing_with_the_current_version_goes_through(resolves, monkeypatch):
    written = []
    monkeypatch.setattr(store, "folder", lambda path: {"id": "node-folder"})
    monkeypatch.setattr(store, "write", lambda path, body, **kw: written.append(path))

    profile.write_profile(NAME, {"name": NAME}, resolves["updated_at"])

    assert written == [f"characters/{NAME}/profile.yaml"]


def test_writing_a_bible_creates_the_characters_folder(resolves, monkeypatch):
    """The catalog has no folder until something asks for one.

    Every index command writes into a character that already exists, so this
    looks like belt and braces — but `rename` writes the bible at the NEW slug,
    where nothing has been created yet. It stays until `rename` moves onto the
    API (#306), and it is asserted rather than assumed because a negative
    control found the line covered by nothing.
    """
    made = []
    monkeypatch.setattr(store, "folder", lambda path: made.append(path) or {"id": "n"})
    monkeypatch.setattr(store, "write", lambda *a, **k: None)

    profile.write_profile(NAME, {"name": NAME})

    assert made == [f"characters/{NAME}"]


def test_uploading_a_file_creates_the_folder_it_goes_in(monkeypatch, tmp_path):
    """`character create` is the first write a character ever gets."""
    made, uploaded = [], []
    monkeypatch.setattr(store, "folder", lambda path: made.append(path) or {"id": "n"})
    monkeypatch.setattr(store, "upload", lambda path, src, **k: uploaded.append(path))
    local = tmp_path / "profile.yaml"
    local.write_text("name: x\n")

    base.put_file(str(local), f"characters/{NAME}/profile.yaml")

    assert made == [f"characters/{NAME}"]
    assert uploaded == [f"characters/{NAME}/profile.yaml"]


def test_writing_without_a_version_does_not_check(resolves, monkeypatch):
    """`None` means "I did not read one" — `create` and `rename` write that way."""
    written = []
    monkeypatch.setattr(store, "folder", lambda path: {"id": "node-folder"})
    monkeypatch.setattr(store, "write", lambda path, body, **kw: written.append(path))

    profile.write_profile(NAME, {"name": NAME})

    assert len(written) == 1


def test_fetch_reads_the_version_before_the_bytes(monkeypatch):
    """The order is the recoverable one, and it is not arbitrary.

    A write landing between the two calls then yields a version OLDER than the
    text, so the next push refuses and re-reads. The other order yields a
    version NEWER than the text, and the next push overwrites a change it never
    saw — silently, which is the failure the check exists to prevent.
    """
    order = []
    monkeypatch.setattr(store, "resolve",
                        lambda _p: order.append("version") or {"updated_at": "v1"})
    monkeypatch.setattr(store, "read", lambda _p: order.append("bytes") or b"name: x\n")

    text, version = profile.fetch_profile(NAME)

    assert order == ["version", "bytes"]
    assert (text, version) == ("name: x\n", "v1")


# ──────────────────────────── the reference index ────────────────────────────


def test_reference_files_are_found_inside_their_group_folders(monkeypatch):
    """**The one listing that must stay recursive.**

    The index keys entries on `face/<name>_1.png`. A listing one folder deep
    would return the group folders and none of the images in them, and
    `sync_index` would then mark every described entry `missing` — losing
    descriptions because of how a listing was done.
    """
    tree = {
        f"characters/{NAME}/reference": [
            {"name": "face", "kind": "folder"},
            {"name": "loose.png", "kind": "file"},
        ],
        f"characters/{NAME}/reference/face": [
            {"name": f"{NAME}_1.png", "kind": "file"},
            {"name": f"{NAME}_10.png", "kind": "file"},
            {"name": f"{NAME}_2.png", "kind": "file"},
            {"name": "notes.txt", "kind": "file"},
        ],
    }
    monkeypatch.setattr(store, "children_or_empty", lambda path: tree.get(path, []))

    assert refs.ref_files(NAME) == [
        f"face/{NAME}_1.png", f"face/{NAME}_2.png", f"face/{NAME}_10.png", "loose.png",
    ]


def test_a_character_with_no_reference_folder_lists_nothing(monkeypatch):
    monkeypatch.setattr(store, "children_or_empty", lambda _path: [])

    assert refs.ref_files(NAME) == []


def test_a_missing_sidecar_is_an_empty_caption_not_a_failure(monkeypatch):
    """Sidecars predate the index; most images have none."""
    def _read(_path):
        raise api.NotFound("no such node", 404)

    monkeypatch.setattr(store, "read", _read)

    assert refs._sidecar_caption("characters/x/reference/face/a.png") == ""


# ──────────────────────────── pool numbering ────────────────────────────


def test_the_next_reference_number_ignores_the_group_folders(monkeypatch):
    """The subfolder exclusion went with the recursive listing that needed it.

    `store.files` is one level deep, so an image in `reference/face/` is simply
    not among `reference/`'s children — where the recursive listing returned it
    and the filter had to put it back.
    """
    monkeypatch.setattr(store, "files", lambda path: (
        [{"name": f"{NAME}_1.png"}, {"name": f"{NAME}_7.png"}]
        if path == f"characters/{NAME}/reference" else []
    ))

    assert base.pool_max_index(NAME, "reference") == 7


def test_numbering_inside_a_group_is_its_own(monkeypatch):
    monkeypatch.setattr(store, "files", lambda path: (
        [{"name": f"{NAME}_face_3.png"}]
        if path == f"characters/{NAME}/reference/face" else []
    ))

    assert base.pool_max_index(NAME, "reference", "face") == 3


# ──────────────────────────── the CLI ────────────────────────────


def test_character_pool_can_presign(media_bucket):
    result = CliRunner().invoke(cli.main, ["character", "pool", NAME, "seed", "--presign"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "https://" in result.output


def test_character_pool_says_expires_is_ignored(media_bucket):
    result = CliRunner().invoke(
        cli.main, ["character", "pool", NAME, "seed", "--presign", "--expires", "60"]
    )

    assert result.exit_code == 0, result.output
    assert "--expires 60 is ignored" in result.output


def test_character_refs_can_presign(media_bucket):
    result = CliRunner().invoke(cli.main, ["character", "refs", NAME, "--presign"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "https://" in result.output
