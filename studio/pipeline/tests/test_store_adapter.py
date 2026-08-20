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
