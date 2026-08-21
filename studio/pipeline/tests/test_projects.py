"""`domain/projects` — the project record and its input pool, through the API (#305).

**Stubbed at `api` for the record and at `store` for the pool.** The record's
whole change is which requests a `project.json` becomes — a folder now has to be
created before the file can hang off it — so those tests assert on requests. The
pool's change is ordering and numbering, which are decisions `projects.py` makes
about a listing, so those stub the listing.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store
from studio_pipeline.domain import projects

PROJECT = "subject-a"


@pytest.fixture
def apis(monkeypatch):
    """Records every call; `/api/resolve` answers a folder unless told otherwise."""
    calls = []
    missing = set()

    def _get(_route, **params):
        calls.append(("GET", _route, params))
        if _route == "/api/resolve":
            path = params["path"]
            if path in missing:
                raise api.NotFound(f"no such node: {path}", 404)
            return {"id": f"node:{path}", "name": path.rsplit("/", 1)[-1], "kind": "folder"}
        raise AssertionError(f"unscripted GET {_route}")

    def _post(_route, payload=None, **params):
        calls.append(("POST", _route, payload))
        if _route == "/api/nodes":
            # A created folder stops being missing — otherwise `store.write`'s
            # own `resolve` of the parent would 404 on the folder `store.folder`
            # had just made, and the fixture would be asserting a bug.
            parent = payload["parent"].removeprefix("node:")
            path = f"{parent}/{payload['name']}" if parent else payload["name"]
            missing.discard(path)
            return {"id": f"node:{path}", "kind": payload["kind"]}
        return {"id": "node:new", "url": "https://s3/signed", "headers": {}}

    monkeypatch.setattr(api, "get", _get)
    monkeypatch.setattr(api, "post", _post)
    monkeypatch.setattr(store, "_put", lambda *a, **k: None)
    return calls, missing


def _created_folders(calls):
    return [payload["name"] for verb, route, payload in calls
            if verb == "POST" and route == "/api/nodes" and payload.get("kind") == "folder"]


# ──────────────────────────── the record ────────────────────────────


def test_writing_a_project_creates_its_folder_first(apis):
    """**The bug this migration would otherwise have shipped.**

    `project.json` was a bare `PutObject` and S3 invented `projects/<p>/` out of
    the slashes in the key. The catalog does not: a file node needs a parent
    that exists, so without this `projects new` fails on a folder nobody made —
    and so does every run recorded into the project afterwards.
    """
    calls, missing = apis
    missing.add(f"projects/{PROJECT}")

    projects.write_project({"name": PROJECT, "characters": []})

    assert _created_folders(calls) == [PROJECT]
    # And the file goes under it, not under whatever resolved last.
    created_file = [payload for verb, route, payload in calls
                    if verb == "POST" and route == "/api/nodes"
                    and payload.get("kind") == "file"]
    assert created_file == [{"parent": f"node:projects/{PROJECT}",
                             "name": "project.json", "kind": "file"}]


def test_the_first_project_in_a_fresh_library_creates_projects_too(apis):
    """`projects/` is not there either until something asks for it."""
    calls, missing = apis
    missing.update({"projects", f"projects/{PROJECT}"})

    projects.write_project({"name": PROJECT, "characters": []})

    assert _created_folders(calls) == ["projects", PROJECT]


def _capture_write(monkeypatch) -> dict:
    """Stub `store.write` and `store.folder`; return what the write was handed."""
    written = {}
    monkeypatch.setattr(store, "folder", lambda path: {"id": f"node:{path}"})
    monkeypatch.setattr(store, "write", lambda path, body, **kw: written.update(
        path=path, body=body, **kw) or {"id": "node:doc"})
    return written


def test_a_project_record_keeps_its_trailing_newline(monkeypatch):
    """These are read in a terminal, and every existing one in the tree has one."""
    written = _capture_write(monkeypatch)

    projects.write_project({"name": PROJECT, "characters": []})

    assert written["body"].endswith(b"\n")
    assert json.loads(written["body"].decode())["name"] == PROJECT


def test_a_project_record_stays_application_json(monkeypatch):
    """Unlike a run's documents, which the API stores as `text/plain`.

    The difference is real: a run document is bytes the pipeline reserves the
    right to reshape and nothing should parse, while this file is parsed by
    `read_project` on every `projects show`.
    """
    written = _capture_write(monkeypatch)

    projects.write_project({"name": PROJECT, "characters": []})

    assert written["content_type"] == "application/json"


def test_a_project_with_no_record_reads_as_none(monkeypatch):
    """A tree that predates `project.json` — `projects init` exists for it."""
    def _read(_path):
        raise api.NotFound("no such node", 404)

    monkeypatch.setattr(store, "read", _read)

    assert projects.read_project(PROJECT) is None


def test_a_refusal_is_not_a_missing_record(monkeypatch):
    """**This used to swallow every exception**, so a 403 read as "no project".

    `projects show` on a library you are not a member of would have reported an
    uncreated project rather than a refusal — and the fix for the wrong one of
    those is to create a duplicate.
    """
    def _read(_path):
        raise api.Forbidden("not your library", 403)

    monkeypatch.setattr(store, "read", _read)

    with pytest.raises(api.Forbidden):
        projects.read_project(PROJECT)


# ──────────────────────────── the input pool ────────────────────────────


def _pool(monkeypatch, *names):
    monkeypatch.setattr(store, "files", lambda _path: [{"name": n, "kind": "file"} for n in names])


def test_the_pool_does_not_resort_what_the_store_gave_it(monkeypatch):
    """**`engine/refs.py` hands these to a model positionally.**

    `store.files` already imposes natural order and `test_store_adapter` is where
    that is proved. What is checked here is that this module does not undo it:
    the names arrive `_1, _2, _10`, which is not lexical, and a `sorted()` added
    anywhere below would flip `_10` in front of `_2` and show the model the wrong
    image under the right name.
    """
    _pool(monkeypatch, f"{PROJECT}_in_1.png", f"{PROJECT}_in_2.png", f"{PROJECT}_in_10.png")

    assert [k.rsplit("/", 1)[-1] for k in projects.input_keys(PROJECT)] == [
        f"{PROJECT}_in_1.png", f"{PROJECT}_in_2.png", f"{PROJECT}_in_10.png",
    ]


def test_the_pool_holds_images_only(monkeypatch):
    """A stray document in the pool is not something to hand a model."""
    _pool(monkeypatch, f"{PROJECT}_in_1.png", "notes.txt")

    assert [k.rsplit("/", 1)[-1] for k in projects.input_keys(PROJECT)] == [
        f"{PROJECT}_in_1.png"
    ]


def test_the_next_index_is_read_off_the_names_not_counted(monkeypatch):
    """A pruned pool must not reuse a number.

    Two images answering to one name is unrecoverable by rerunning anything —
    the records that already point at `_3` would silently mean a different
    picture.
    """
    _pool(monkeypatch, f"{PROJECT}_in_1.png", f"{PROJECT}_in_7.png")

    assert projects.pool_max_index(PROJECT) == 7


def test_a_project_with_no_pool_yet_starts_at_zero(monkeypatch):
    """`store.files` reports a missing folder as empty; nothing here re-decides it."""
    _pool(monkeypatch)

    assert projects.pool_max_index(PROJECT) == 0


def test_adding_inputs_ensures_the_pool_folder_once(monkeypatch, tmp_path):
    """A project created before anything was uploaded has no `input/` node."""
    made, uploaded = [], []
    monkeypatch.setattr(store, "files", lambda _path: [])
    monkeypatch.setattr(store, "folder", lambda path: made.append(path) or {"id": "node:pool"})
    monkeypatch.setattr(store, "upload",
                        lambda path, source, **kw: uploaded.append(path) or {"id": "n"})
    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"png-bytes")

    added = projects.add_inputs(PROJECT, [str(tmp_path / "a.png"), str(tmp_path / "b.png")])

    assert made == [f"projects/{PROJECT}/input"], "the folder is ensured once, not per file"
    assert [a["n"] for a in added] == [1, 2]
    assert uploaded == [f"projects/{PROJECT}/input/{PROJECT}_in_1.png",
                        f"projects/{PROJECT}/input/{PROJECT}_in_2.png"]


# ──────────────────────────── the CLI ────────────────────────────


def test_projects_inputs_can_presign(media_bucket):
    """The same shadowing trap `runs outputs --presign` fell into."""
    result = CliRunner().invoke(cli.main, ["projects", "inputs", PROJECT, "--presign"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "https://" in result.output


def test_projects_inputs_says_expires_is_ignored(media_bucket):
    result = CliRunner().invoke(
        cli.main, ["projects", "inputs", PROJECT, "--presign", "--expires", "60"]
    )

    assert result.exit_code == 0, result.output
    assert "--expires 60 is ignored" in result.output
