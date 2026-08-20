"""`domain/runs` — the run store recorded through the API (#304).

**Stubbed at `api`, not at `store`.** What #304 changed is which request a run
becomes, so the assertions are about the request: which route, which parent,
which documents, and what happens when the API refuses. Stubbing `store` would
assert that `runs.py` calls the functions it obviously calls.

The one exception is the CLI test at the bottom, which runs against the moto
shim because what it is checking — that `--presign` reaches real code at all —
is a dispatch question, and dispatch is what the shim exists to keep testable.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store
from studio_pipeline.domain import runs as R

PROJECT = "subject-a"
RUN_ID = "2026-08-04_21-30-54_wave-porch"
RUNS_FOLDER = f"projects/{PROJECT}/runs"


@pytest.fixture
def apis(monkeypatch):
    """Records every API call; answers `/api/resolve` with a folder per path.

    Deliberately generous about what resolves: these tests are about the
    requests `runs.py` makes, and a fixture that also modelled the catalog's
    404s would be a second implementation of it to keep in step.
    """
    calls = []
    refuse = set()

    def _get(_route, **params):
        calls.append(("GET", _route, params))
        if _route == "/api/resolve":
            path = params["path"]
            if path in refuse:
                raise api.NotFound(f"no such node: {path}", 404)
            return {"id": f"node:{path}", "name": path.rsplit("/", 1)[-1], "kind": "folder"}
        raise AssertionError(f"unscripted GET {_route}")

    def _post(_route, payload=None, **params):
        calls.append(("POST", _route, payload))
        if _route in refuse:
            raise api.Conflict("already exists", 409)
        return {"id": "node:new", "kind": "folder"}

    def _patch(_route, payload, **params):
        calls.append(("PATCH", _route, payload))
        return {"id": _route.rsplit("/", 1)[-1]}

    monkeypatch.setattr(api, "get", _get)
    monkeypatch.setattr(api, "post", _post)
    monkeypatch.setattr(api, "patch", _patch)
    return calls, refuse


def _posted(calls, route):
    return [payload for verb, seen, payload in calls if verb == "POST" and seen == route]


# ──────────────────────────── recording a run ────────────────────────────


def test_recording_a_run_posts_the_folder_and_its_documents_together(apis):
    """One request makes the run and writes what was sent — that is the route."""
    calls, _ = apis

    R.record_request(PROJECT, RUN_ID, kind="image", engine="nano-banana-pro",
                     model="google/nano-banana-pro", input={"prompt": "a porch"},
                     bindings={"image_input": [f"characters/{PROJECT}/reference/face_1.webp"]})

    (body,) = _posted(calls, "/api/runs")
    assert body["parent"] == f"node:{RUNS_FOLDER}"
    assert body["name"] == RUN_ID
    assert list(body["documents"]) == ["request.json"]


def test_a_structured_prompt_is_recorded_beside_the_request(apis):
    """`prompt.json` exists so the authored source survives, not just the string."""
    calls, _ = apis

    R.record_request(PROJECT, RUN_ID, kind="video", engine="kling", model="kwaivgi/x",
                     input={}, prompt_source={"camera": "static"})

    (body,) = _posted(calls, "/api/runs")
    assert list(body["documents"]) == ["request.json", "prompt.json"]
    assert json.loads(body["documents"]["prompt.json"]) == {"camera": "static"}


def test_the_recorded_request_is_the_document_a_reader_gets_back(apis):
    """The API stores these bytes and never decodes them, so this is the record."""
    calls, _ = apis

    R.record_request(PROJECT, RUN_ID, kind="image", engine="nano-banana-pro",
                     model="google/nano-banana-pro", input={"prompt": "a porch"},
                     bindings={"image_input": f"characters/{PROJECT}/reference/face_1.webp"},
                     characters=[PROJECT], extra={"slot": "face_front"})

    (body,) = _posted(calls, "/api/runs")
    doc = json.loads(body["documents"]["request.json"])
    assert doc["run_id"] == RUN_ID
    assert doc["project"] == PROJECT
    assert doc["characters"] == [PROJECT]
    assert doc["bindings"] == {"image_input": f"characters/{PROJECT}/reference/face_1.webp"}
    assert doc["slot"] == "face_front"


def test_a_url_shaped_binding_is_refused_before_anything_is_sent(apis):
    """Hard rule #3's enforcement point.

    The API stores these documents as bytes and never reads a path inside one,
    so this is the only place the rule can be applied — and it has to fire
    *before* the request, because a run recorded with a presigned URL in it is
    already the damage.
    """
    calls, _ = apis

    with pytest.raises(R.RunError, match="looks like a URL"):
        R.record_request(PROJECT, RUN_ID, kind="image", engine="x", model="y", input={},
                         bindings={"image_input": "https://example.test/signed"})

    assert _posted(calls, "/api/runs") == []


def test_a_run_recorded_twice_is_refused_by_name(apis):
    """A run id carries a timestamp to the second, so a 409 is a re-send."""
    calls, refuse = apis
    refuse.add("/api/runs")

    with pytest.raises(R.RunError, match="already recorded"):
        R.record_request(PROJECT, RUN_ID, kind="image", engine="x", model="y", input={})

    assert len(_posted(calls, "/api/runs")) == 1


def test_recording_a_run_in_a_project_with_no_runs_folder_yet_creates_one(apis):
    """`projects/<p>/runs/` was free in S3 and is a row now."""
    calls, refuse = apis
    refuse.add(RUNS_FOLDER)

    R.record_request(PROJECT, RUN_ID, kind="image", engine="x", model="y", input={})

    assert {"parent": f"node:projects/{PROJECT}", "name": "runs", "kind": "folder"} in _posted(
        calls, "/api/nodes"
    )


# ──────────────────────────── outputs ────────────────────────────


def test_an_output_goes_into_the_runs_output_folder(monkeypatch, tmp_path):
    """`<run>/output/<file>`, and the folder is ensured on the way.

    Not `POST /api/runs`'s `outputs` field: a node name is one segment, so that
    route would put the artifact flat in the run folder.
    """
    made, uploaded = [], []
    monkeypatch.setattr(store, "folder", lambda path: made.append(path) or {"id": "node:out"})
    monkeypatch.setattr(store, "upload",
                        lambda path, source, **kw: uploaded.append((path, kw)) or {"id": "n"})
    local = tmp_path / "wave-porch.jpeg"
    local.write_bytes(b"jpeg-bytes")

    path = R.upload_output(PROJECT, RUN_ID, str(local))

    assert path == f"projects/{PROJECT}/runs/{RUN_ID}/output/wave-porch.jpeg"
    assert made == [f"projects/{PROJECT}/runs/{RUN_ID}/output"]
    assert uploaded == [(path, {"content_type": "image/jpeg"})]


def test_outputs_come_back_in_natural_order_not_the_apis(monkeypatch):
    """**Positional, so this decides which frame a model is handed.**

    The API returns children name-ascending, which is lexical: `-10` before
    `-2`. These paths become `[Image1]..[ImageN]`, so trusting that order hands
    a model the wrong image under the right name.
    """
    monkeypatch.setattr(store, "children", lambda _path: [
        {"name": "clip-1.mp4", "kind": "file"},
        {"name": "clip-10.mp4", "kind": "file"},
        {"name": "clip-2.mp4", "kind": "file"},
    ])

    assert [p.rsplit("/", 1)[-1] for p in R.run_outputs(PROJECT, RUN_ID)] == [
        "clip-1.mp4", "clip-2.mp4", "clip-10.mp4",
    ]


def test_a_folder_inside_a_runs_output_is_not_an_output(monkeypatch):
    """The catalog returns both kinds in one list; `list_objects_v2` did not."""
    monkeypatch.setattr(store, "children", lambda _path: [
        {"name": "frames", "kind": "folder"},
        {"name": "clip.mp4", "kind": "file"},
    ])

    assert [p.rsplit("/", 1)[-1] for p in R.run_outputs(PROJECT, RUN_ID)] == ["clip.mp4"]


def test_a_run_that_never_produced_output_has_none(monkeypatch):
    """A failure or a timeout has no `output/` folder, and that is not an error."""
    def _children(_path):
        raise api.NotFound("no such node", 404)

    monkeypatch.setattr(store, "children", _children)

    assert R.run_outputs(PROJECT, RUN_ID) == []


# ──────────────────────────── documents ────────────────────────────


def test_a_document_that_is_not_there_reads_as_none(monkeypatch):
    """`result.json` is absent until a run finishes; `run_record` asks anyway."""
    def _read(_path):
        raise api.NotFound("no such node", 404)

    monkeypatch.setattr(store, "read", _read)

    assert R.read_json(f"projects/{PROJECT}/runs/{RUN_ID}/result.json") is None


def test_a_document_is_written_as_text_not_json(monkeypatch):
    """Matches what `POST /api/runs` does to `request.json`.

    Otherwise a run's two documents would carry different content types
    depending only on which code path wrote them — and `application/json` is an
    invitation to parse bytes the pipeline reserves the right to reshape.
    """
    written = {}
    monkeypatch.setattr(store, "write",
                        lambda path, body, **kw: written.update(path=path, body=body, **kw))

    R.record_result(PROJECT, RUN_ID, prediction_id="p1", status="succeeded", outputs=[])

    assert written["content_type"] == "text/plain; charset=utf-8"
    assert json.loads(written["body"].decode())["status"] == "succeeded"


# ──────────────────────────── adopting ────────────────────────────


def test_adopting_moves_the_node_and_keeps_its_id(apis, monkeypatch):
    """A move rewrites one row. The copy-and-delete it replaces did not keep an id.

    That is the point worth asserting: anything already naming this file — a
    share link included — still names it after it has been adopted.
    """
    calls, _ = apis
    artifact = f"projects/{PROJECT}/output/{RUN_ID}.mp4"
    real_resolve = store.resolve
    monkeypatch.setattr(store, "resolve", lambda path: (
        {"id": "node:the-artifact", "kind": "file"} if path == artifact else real_resolve(path)
    ))
    monkeypatch.setattr(store, "write", lambda path, body, **kw: {"id": "node:doc"})

    path = R.adopt(PROJECT, artifact)

    assert path == f"projects/{PROJECT}/runs/{RUN_ID}/output/{RUN_ID}.mp4"
    output = f"node:projects/{PROJECT}/runs/{RUN_ID}/output"
    assert ("PATCH", "/api/nodes/node:the-artifact", {"parent": output}) in calls
    # The run exists before the artifact is moved into it, so a failure leaves a
    # run with a `request.json` and no output rather than an orphan.
    verbs = [f"{verb} {route}" for verb, route, _ in calls]
    assert verbs.index("POST /api/runs") < verbs.index("PATCH /api/nodes/node:the-artifact")


def test_adopting_something_already_inside_its_run_is_refused(apis):
    """The basename IS a run id, so `adopt` would derive the folder it is in."""
    _, _ = apis
    inside = f"projects/{PROJECT}/runs/{RUN_ID}/output/{RUN_ID}.mp4"

    with pytest.raises(R.RunError, match="already inside its run"):
        R.adopt(PROJECT, inside)


# ──────────────────────────── the CLI ────────────────────────────


def test_runs_outputs_can_presign(media_bucket):
    """**`--presign` raised `TypeError` for as long as it existed.**

    The flag's parameter is named `presign` and so is the module's function, so
    inside `do_outputs` the flag shadowed it and `presign(...)` called `True`.
    `--help` printed happily; nothing ever invoked it. `--expires` is asserted
    on separately because it is now a warning rather than a value.
    """
    result = CliRunner().invoke(cli.main, ["runs", "outputs", f"{PROJECT}/latest", "--presign"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "https://" in result.output


def test_runs_outputs_says_expires_is_ignored(media_bucket):
    """A flag that silently does nothing is the failure the rename avoided."""
    result = CliRunner().invoke(
        cli.main, ["runs", "outputs", f"{PROJECT}/latest", "--presign", "--expires", "60"]
    )

    assert result.exit_code == 0, result.output
    assert "--expires 60 is ignored" in result.output
