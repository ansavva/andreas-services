"""`studio upload` / `download` / `presign` / `convert`, over the API (#302, #305).

**These had no tests before this file.** The three commands were migrated off
boto3 and the suite went on passing 431/431, which says nothing — nothing
invoked them. That silence is the reason the migration needed tests before it
could be believed, not after. `convert` joined them for the same reason.

Stubbed at `store`, because what is under test here is the command layer: which
paths it builds, what order it lists in, and what it prints. The `convert`
section is the exception and uses the moto fixture instead — it re-encodes with
PIL, so it needs bytes that are really an image.
"""

from __future__ import annotations

import io
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
    state = {"files": files, "written": {}, "presigned": [], "ensured": []}

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

    def _folder(path):
        """`upload` ensures its destination now, as `convert --dest-key` does."""
        state["ensured"].append(path)
        return {"id": f"node-{path}", "kind": "folder"}

    monkeypatch.setattr(store, "children", _children)
    monkeypatch.setattr(store, "presign", _presign)
    monkeypatch.setattr(store, "upload", _upload)
    monkeypatch.setattr(store, "download", _download)
    monkeypatch.setattr(store, "folder", _folder)
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


# ─────────────────────────────── convert ───────────────────────────────
#
# `library`, not `fake_store`: PIL has to open the source, so the bytes have to
# be a real image rather than a marker — and the destination is the project's
# input pool, which is a real API call.


@pytest.fixture
def source_png(library):
    """A real PNG in the tree, since the fixture's images are markers.

    Returns its NODE ID. `--key` still takes a name path too, and one of the
    tests below uses one; a runref resolves to an id, which is the shape that
    matters now.
    """
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, "PNG")
    corpus = library.fake._child(library.character_root, "corpus")
    return library.fake.put_file(corpus["id"], "photo.png",
                                 buffer.getvalue())["id"]


def test_convert_lands_in_the_input_pool_as_a_node(source_png, library):
    """`projects.add_inputs` owns the destination, and this proves it is asked.

    **The numbering it used to own is gone.** This test asserted that a pool
    holding `<project>_in_3` produced `<project>_in_4`, because `--input N`
    meant "the file whose name ends `_N`" and a second implementation of that
    rule would overwrite an existing input. `--input N` is a POSITION in the
    API's listing now, so a converted file keeps whatever basename it arrived
    with and the pool has no numbering left to get wrong.

    What is still worth pinning is that the command prints a node id and that
    the bytes reach the pool — because the destination is the one thing about a
    convert that cannot be undone by running it again.
    """
    from studio_pipeline.domain import projects as PROJECTS

    result = _run("convert", "--key", source_png, "--to", "jpg",
                  "--add-input", "porch-teaser")

    assert result.exit_code == 0, result.output
    node_id = result.output.splitlines()[0]
    assert node_id.startswith("node-")
    pool = PROJECTS.input_pool(PROJECTS.resolve("porch-teaser"))
    landed = next(e for e in pool if e["id"] == node_id)
    assert landed["content_type"] == "image/jpeg"


def test_convert_to_an_explicit_destination_ensures_the_parent(
        source_png, library, monkeypatch):
    """Folders were free in S3 and are catalog rows now.

    `--dest-key` is the flag most likely to name a folder nothing has written
    to yet, and `store.write` resolves the parent it is handed rather than
    inventing it.
    """
    made = []
    real = store.folder

    def spy(path):
        made.append(path)
        return real(path)

    monkeypatch.setattr(store, "folder", spy)

    result = _run("convert", "--key", source_png, "--to", "webp",
                  "--dest-key", "porch-teaser/derived/frame.webp")

    assert result.exit_code == 0, result.output
    # A spy that DELEGATES, not one that answers. A stub returning a fake node
    # would prove the call was made and hide whether the folder it named could
    # actually be created — and `store.write` resolves the parent immediately
    # afterwards, so a lie here fails one line later.
    # `store.folder` recurses to make any missing ancestor, so the deepest path
    # is asked for first and its parents follow. That the WHOLE chain is walked
    # is the property — a project that has never had a `derived/` is the case
    # this flag most often meets.
    assert made[0] == "porch-teaser/derived"
    assert store.resolve("porch-teaser/derived/frame.webp")["kind"] == "file"


def test_convert_names_a_source_that_is_not_there(library):
    """A runref can resolve to something nothing wrote; a traceback does not say
    which. Named for a NAME PATH here, which is still what a person types."""
    result = _run("convert", "--key", "porch-teaser/input/nothing.png",
                  "--to", "jpg", "--add-input", "porch-teaser")

    assert result.exit_code == 1
    assert "porch-teaser/input/nothing.png" in result.output


def test_no_command_offers_an_expiry_it_cannot_honour(fake_store):
    """**`--expires` is gone from all eleven commands that declared it.**

    The API signs presigned URLs against its own credentials and owns the TTL
    (`STUDIO_PRESIGN_TTL_SECONDS`), so no number typed at the CLI could ever
    reach it. Eight of the eleven warned that they were ignoring it; three —
    `run`, and the `scenes` commands that pass their options down to it — took
    it silently. A flag that does nothing is the failure the `XHARNESS_S3_*`
    rename was designed around, and warning about it every time was a
    workaround for not having removed it.
    """
    result = _run("presign", "--key", "a/b.mp4", "--expires", "60")

    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


def test_upload_creates_the_destination_folder(fake_store, tmp_path):
    """**The gap that made a pool impossible to organise.**

    `store.folder` is idempotent and creates missing ancestors, and
    `convert --dest-key` has always called it. `upload` went straight to
    `store.upload`, so the first file into a new subfolder died on the parent
    that did not exist — and nothing in the CLI created one.
    """
    source = tmp_path / "shot.webp"
    source.write_bytes(b"webp")

    result = _run("upload", "--folder", "characters/<name>/seed/current", str(source))

    assert result.exit_code == 0, result.output
    assert "characters/<name>/seed/current/shot.webp" in result.output
    assert fake_store["ensured"] == ["characters/<name>/seed/current"]
