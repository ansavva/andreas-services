"""`studio upload` / `download` / `presign`, now over the API (#302, step b).

**These had no tests before this file.** The three commands were migrated off
boto3 and the suite went on passing 431/431, which says nothing — nothing
invoked them. That silence is the reason the migration needed tests before it
could be believed, not after.

Stubbed at `store`, because what is under test here is the command layer: which
paths it builds, what order it lists in, and what it prints.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store


@pytest.fixture
def fake_store(monkeypatch):
    """A store holding one folder of files, in deliberately awkward order."""
    files = ["<name>_10.webp", "<name>_2.webp", "<name>_1.webp"]
    state = {"files": files, "written": {}, "presigned": []}

    def _children(path):
        if path != "characters/<name>/reference":
            raise api.NotFound(f"No such object: {path}", 404)
        return [{"name": n, "kind": "file", "id": f"node-{n}"} for n in state["files"]]

    def _presign(path, disposition="inline"):
        state["presigned"].append(path)
        return f"https://s3/signed/{path}"

    def _upload(path, source, content_type):
        state["written"][path] = (source.read_bytes(), content_type)
        return {"id": f"node-{pathlib.Path(path).name}"}

    def _download(path, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"bytes-of-" + path.encode())
        return destination

    monkeypatch.setattr(store, "children", _children)
    monkeypatch.setattr(store, "presign", _presign)
    monkeypatch.setattr(store, "upload", _upload)
    monkeypatch.setattr(store, "download", _download)
    return state


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


# ─────────────────────────────── presign ───────────────────────────────


def test_presign_a_single_key(fake_store):
    result = _run("presign", "--key", "projects/<p>/output/clip.mp4")

    assert result.exit_code == 0
    assert "https://s3/signed/projects/<p>/output/clip.mp4" in result.output


def test_presign_a_folder_preserves_natural_order(fake_store):
    """**The load-bearing assertion.**

    These URLs become `[Image1]..[ImageN]` positionally. The API returns children
    name-ascending, which is lexical — `_10` before `_2` — so a command that
    trusted that order would hand a model its references shuffled and the prompt
    would name the wrong one.
    """
    result = _run("presign", "--folder", "characters/<name>/reference", "--json")

    assert result.exit_code == 0
    keys = [entry["key"] for entry in json.loads(result.output)]
    assert keys == [
        "characters/<name>/reference/<name>_1.webp",
        "characters/<name>/reference/<name>_2.webp",
        "characters/<name>/reference/<name>_10.webp",
    ]


def test_presign_named_files_only(fake_store):
    result = _run(
        "presign", "--folder", "characters/<name>/reference", "<name>_2.webp", "--json"
    )

    assert [e["key"] for e in json.loads(result.output)] == [
        "characters/<name>/reference/<name>_2.webp"
    ]


def test_presign_names_what_is_missing(fake_store):
    result = _run("presign", "--folder", "characters/<name>/reference", "nope.webp")

    assert result.exit_code != 0
    assert "nope.webp" in result.output


def test_presign_needs_a_folder_or_a_key(fake_store):
    assert _run("presign").exit_code != 0


def test_expires_is_accepted_and_says_it_is_ignored(fake_store):
    """A flag that silently does nothing is the failure the rename avoided."""
    result = _run("presign", "--key", "a/b.mp4", "--expires", "60")

    assert result.exit_code == 0
    assert "--expires 60 is ignored" in result.output


def test_expires_is_silent_when_not_passed(fake_store):
    result = _run("presign", "--key", "a/b.mp4")

    assert "ignored" not in result.output


# ─────────────────────────────── download ──────────────────────────────


def test_download_list_is_natural_order(fake_store):
    result = _run("download", "--folder", "characters/<name>/reference", "--list")

    assert result.output.split() == ["<name>_1.webp", "<name>_2.webp", "<name>_10.webp"]


def test_download_all_writes_files(fake_store, tmp_path):
    result = _run(
        "download", "--folder", "characters/<name>/reference", "--all",
        "--dest", str(tmp_path), "--json",
    )

    assert result.exit_code == 0
    written = json.loads(result.output)
    assert set(written) == set(fake_store["files"])
    assert (tmp_path / "<name>_1.webp").read_bytes().startswith(b"bytes-of-")


def test_download_names_what_is_missing(fake_store, tmp_path):
    result = _run(
        "download", "--folder", "characters/<name>/reference", "nope.webp",
        "--dest", str(tmp_path),
    )

    assert result.exit_code != 0
    assert "nope.webp" in result.output


def test_download_from_a_missing_folder_says_so(fake_store, tmp_path):
    result = _run("download", "--folder", "characters/nobody", "--list")

    assert result.exit_code != 0
    assert "no such folder" in result.output


# ──────────────────────────────── upload ───────────────────────────────


def test_upload_writes_and_reports_the_path(fake_store, tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")

    result = _run("upload", "--folder", "projects/<p>/input", str(source), "--json")

    assert result.exit_code == 0
    entry = json.loads(result.output)[0]
    assert entry["key"] == "projects/<p>/input/clip.mp4"
    assert entry["id"] == "node-clip.mp4"
    assert fake_store["written"]["projects/<p>/input/clip.mp4"][1] == "video/mp4"


def test_upload_no_longer_prints_an_s3_uri(fake_store, tmp_path):
    """The CLI knows no bucket; printing one it guessed would be worse than the path."""
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")

    result = _run("upload", "--folder", "projects/<p>/input", str(source))

    assert "s3://" not in result.output
    assert "projects/<p>/input/clip.mp4" in result.output


def test_upload_can_presign_what_it_wrote(fake_store, tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")

    result = _run("upload", "--folder", "projects/<p>/input", str(source), "--presign", "--json")

    assert json.loads(result.output)[0]["url"].startswith("https://s3/signed/")


def test_upload_refuses_a_missing_file(fake_store, tmp_path):
    result = _run("upload", "--folder", "projects/<p>/input", str(tmp_path / "gone.mp4"))

    assert result.exit_code != 0
    assert "not a file" in result.output
