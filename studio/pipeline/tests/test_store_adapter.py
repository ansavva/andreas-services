"""`adapters/store` — the media store reached through the API (#302, step a).

**Stubbed at `api` and at `urlopen`, not at `store`.** The two halves fail
differently and both matter: an API call that 404s is a missing node, and a
presigned URL that fails is almost always an expired signature. A test that
stubbed `store` itself would assert nothing about either.
"""

from __future__ import annotations

import io
import urllib.error

import pytest

from studio_pipeline.adapters import api, store


class _Response(io.BytesIO):
    def __init__(self, body: bytes = b"") -> None:
        super().__init__(body)
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def apis(monkeypatch):
    """Records every API call and answers from a scripted table."""
    calls = []
    table = {}

    # `_route`, not `path`: `store.resolve` calls `api.get(..., path=...)`, and a
    # stub whose first parameter is also named `path` collides with the keyword.
    def _get(_route, **params):
        calls.append(("GET", _route, params))
        return table[("GET", _route)]

    def _post(_route, payload=None, **params):
        calls.append(("POST", _route, payload))
        value = table[("POST", _route)]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(api, "get", _get)
    monkeypatch.setattr(api, "post", _post)
    return calls, table


def test_resolve_asks_the_api_for_a_name_path(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1", "name": "face_01.png"}

    assert store.resolve("/characters/<name>/reference/face_01.png")["id"] == "node-1"
    # Leading and trailing slashes are the caller's habit, not the API's problem.
    assert calls[0][2] == {"path": "characters/<name>/reference/face_01.png"}


def test_read_fetches_the_presigned_url_not_the_api(apis, monkeypatch):
    """Bytes never travel through the API — that is what keeps a video out of the Lambda."""
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed"}
    fetched = {}

    def _urlopen(url, timeout=None):  # noqa: ARG001
        fetched["url"] = url if isinstance(url, str) else url.full_url
        return _Response(b"the-bytes")

    monkeypatch.setattr(store.urllib.request, "urlopen", _urlopen)

    assert store.read("characters/<name>/reference/face_01.png") == b"the-bytes"
    assert fetched["url"] == "https://s3/signed"


def test_presign_passes_the_disposition_through(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed"}

    assert store.presign("clip.mp4", disposition="attachment") == "https://s3/signed"
    assert calls[-1][2] == {"disposition": "attachment"}


def test_write_creates_then_uploads_then_confirms(apis, monkeypatch):
    """The order is the recoverable one: a failure before confirm leaves a placeholder."""
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-parent"}
    table[("POST", "/api/nodes")] = {"id": "node-new"}
    table[("POST", "/api/nodes/node-new/upload-url")] = {
        "url": "https://s3/put",
        "headers": {"Content-Length": "9", "Content-Type": "text/plain"},
    }
    table[("POST", "/api/nodes/node-new/confirm-upload")] = {"id": "node-new", "size": 9}
    sent = {}

    def _urlopen(request, timeout=None):  # noqa: ARG001
        sent["method"] = request.method
        sent["body"] = request.data
        sent["type"] = request.get_header("Content-type")
        return _Response()

    monkeypatch.setattr(store.urllib.request, "urlopen", _urlopen)

    result = store.write("projects/<project>/notes.txt", b"the-bytes", content_type="text/plain")

    assert result["size"] == 9
    assert sent["method"] == "PUT"
    assert sent["body"] == b"the-bytes"
    # Exactly the headers the API signed — anything else fails the signature.
    assert sent["type"] == "text/plain"
    assert [c[0] + " " + c[1] for c in calls] == [
        "GET /api/resolve",
        "POST /api/nodes",
        "POST /api/nodes/node-new/upload-url",
        "POST /api/nodes/node-new/confirm-upload",
    ]


def test_writing_over_an_existing_file_keeps_its_node(apis, monkeypatch):
    """A replace must not mint a new id — every record naming it would go stale."""
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-existing"}
    table[("POST", "/api/nodes")] = api.Conflict("'notes.txt' already exists here", 409)
    table[("POST", "/api/nodes/node-existing/upload-url")] = {
        "url": "https://s3/put",
        "headers": {"Content-Length": "3", "Content-Type": "text/plain"},
    }
    table[("POST", "/api/nodes/node-existing/confirm-upload")] = {"id": "node-existing"}
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: _Response())

    assert store.write("projects/<project>/notes.txt", b"new", content_type="text/plain")["id"] == (
        "node-existing"
    )


def test_a_failed_fetch_does_not_echo_the_signed_url(apis, monkeypatch):
    """A presigned URL in a traceback is a working credential in the scrollback."""
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed?X-Amz-Signature=abc"}

    def _urlopen(url, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("Forbidden")

    monkeypatch.setattr(store.urllib.request, "urlopen", _urlopen)

    with pytest.raises(store.StoreError) as caught:
        store.read("clip.mp4")

    assert "X-Amz-Signature" not in str(caught.value)
    assert "Forbidden" in str(caught.value)


def test_children_lists_one_level(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-folder"}
    table[("GET", "/api/nodes")] = [{"id": "node-a", "name": "a.png"}]

    assert store.children("characters/<name>/reference")[0]["name"] == "a.png"
    assert calls[-1][2] == {"parent": "node-folder"}


def test_download_writes_to_disk_creating_parents(apis, monkeypatch, tmp_path):
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed"}
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: _Response(b"xyz"))

    written = store.download("clip.mp4", tmp_path / "nested" / "clip.mp4")

    assert written.read_bytes() == b"xyz"


def test_resolve_goes_through_the_real_api_signature(monkeypatch):
    """**The regression guard for a bug the other tests here could not see.**

    Every test above stubs `api.get`, and a stub is free to name its first
    parameter anything. The real one was not: `def get(path, **params)`, while
    `store.resolve` calls `api.get("/api/resolve", path=...)`. The two collided,
    so `resolve` raised `TypeError` on every call — and the suite was green,
    because no test drove the real signature.

    This one stubs `urlopen` instead, so the signature is part of what is
    asserted.
    """
    from studio_pipeline.adapters import auth

    monkeypatch.setattr(auth, "id_token", lambda **_: "token")
    monkeypatch.setattr(auth, "api_url", lambda: "https://api.example")
    seen = {}

    def _urlopen(request, timeout=None):  # noqa: ARG001
        seen["url"] = request.full_url
        return _Response(b'{"id": "node-1"}')

    monkeypatch.setattr(api.urllib.request, "urlopen", _urlopen)

    assert store.resolve("characters/<name>/reference")["id"] == "node-1"
    assert "path=characters" in seen["url"]


# ──────────────────────────── folders (#304) ────────────────────────────
#
# Folders were free in S3 — a key with slashes in it looked like one — and are
# rows now. `store.folder` is what a caller uses to say a run exists before
# writing a document inside it.


def test_an_existing_folder_is_returned_without_creating_anything(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-runs", "kind": "folder"}

    assert store.folder("projects/<project>/runs")["id"] == "node-runs"
    assert not [call for call in calls if call[0] == "POST"]


def test_a_missing_folder_is_created_under_its_parent(apis, monkeypatch):
    calls, table = apis
    # `store.folder` resolves the folder and then its parent, and both are
    # `GET /api/resolve` — so this one answers by path rather than by route.
    def _get(_route, **params):
        calls.append(("GET", _route, params))
        if params.get("path") == "projects/<project>/runs":
            raise api.NotFound("no such node", 404)
        return {"id": "node-project", "kind": "folder"}

    monkeypatch.setattr(api, "get", _get)
    table[("POST", "/api/nodes")] = {"id": "node-runs", "kind": "folder"}

    assert store.folder("projects/<project>/runs")["id"] == "node-runs"
    assert calls[-1] == (
        "POST", "/api/nodes",
        {"parent": "node-project", "name": "runs", "kind": "folder"},
    )


def test_a_folder_that_appears_between_the_resolve_and_the_create_is_not_an_error(
    apis, monkeypatch
):
    """409 means somebody else made it, and the node they made is the answer."""
    calls, table = apis
    answers = [api.NotFound("no such node", 404), {"id": "node-parent", "kind": "folder"},
               {"id": "node-theirs", "kind": "folder"}]

    def _get(_route, **params):
        calls.append(("GET", _route, params))
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(api, "get", _get)
    table[("POST", "/api/nodes")] = api.Conflict("'runs' already exists here", 409)

    assert store.folder("projects/<project>/runs")["id"] == "node-theirs"


def test_a_file_is_not_a_folder(apis):
    """Refused here, where the path is still known.

    `catalog.create_node` would refuse the children one at a time, naming the
    parent's id — which says nothing about which path was wrong.
    """
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1", "kind": "file"}

    with pytest.raises(store.StoreError, match="is a file"):
        store.folder("projects/<project>/project.json")


def test_a_missing_chain_of_folders_is_created_deepest_last(apis, monkeypatch):
    """Ancestors too, so a caller states the path it wants rather than walking it.

    `projects/<p>/runs/<run>/output` is four levels below the root and a fresh
    project has none of them: `projects/<p>` is written by `project create` and
    the rest were free in S3. Creating only the leaf would 404 on its parent.
    """
    calls, table = apis
    present = {"projects"}

    def _get(_route, **params):
        calls.append(("GET", _route, params))
        path = params.get("path")
        if path not in present:
            raise api.NotFound(f"no such node: {path}", 404)
        return {"id": f"node:{path}", "kind": "folder"}

    def _post(_route, payload=None, **params):
        calls.append(("POST", _route, payload))
        return {"id": f"node:{payload['name']}", "kind": "folder"}

    monkeypatch.setattr(api, "get", _get)
    monkeypatch.setattr(api, "post", _post)

    store.folder("projects/<project>/runs")

    assert [payload["name"] for verb, route, payload in calls
            if verb == "POST" and route == "/api/nodes"] == ["<project>", "runs"]
