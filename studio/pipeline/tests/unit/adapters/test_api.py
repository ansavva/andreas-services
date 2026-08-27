"""`adapters/api` — the one transport every CLI call goes through (#301).

**Stubbed at `urlopen`, not at `_send`.** Stubbing the private sender would skip
the half most likely to be wrong: `urllib` raises `HTTPError` for any 4xx/5xx, and
that exception *is* the response — letting it close unread throws away the only
message the API sent. These tests drive that path.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from studio_pipeline.adapters import api, auth


class _Response(io.BytesIO):
    """The subset of an `http.client.HTTPResponse` that `_send` touches."""

    def __init__(self, status: int, body: bytes) -> None:
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _http_error(status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x/api/nodes", status, "err", {}, io.BytesIO(body))


@pytest.fixture(autouse=True)
def _signed_in(monkeypatch):
    """A session that never touches Cognito, and a record of refreshes."""
    calls = {"refresh": 0}

    def _id_token(*, refresh: bool = False) -> str:
        if refresh:
            calls["refresh"] += 1
            return "refreshed-token"
        return "stored-token"

    monkeypatch.setattr(auth, "id_token", _id_token)
    monkeypatch.setattr(auth, "api_url", lambda: "https://studio-api.example")
    monkeypatch.delenv("STUDIO_LIBRARY_ID", raising=False)
    return calls


def _serve(monkeypatch, *responses):
    """Answer successive calls with the given responses; record the requests."""
    seen = []
    queue = list(responses)

    def _urlopen(request, timeout=None):  # noqa: ARG001
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, urllib.error.HTTPError):
            raise item
        return item

    monkeypatch.setattr(api.urllib.request, "urlopen", _urlopen)
    return seen


def test_a_successful_call_returns_the_decoded_body(monkeypatch):
    _serve(monkeypatch, _Response(200, b'{"id": "node-1"}'))

    assert api.get("/api/nodes/node-1") == {"id": "node-1"}


def test_the_bearer_token_is_sent(monkeypatch):
    seen = _serve(monkeypatch, _Response(200, b"{}"))

    api.get("/api/libraries")

    assert seen[0].get_header("Authorization") == "Bearer stored-token"


def test_the_library_header_is_sent_when_set(monkeypatch):
    monkeypatch.setenv("STUDIO_LIBRARY_ID", "lib-1")
    seen = _serve(monkeypatch, _Response(200, b"{}"))

    api.get("/api/nodes", parent="node-root")

    assert seen[0].get_header(api.LIBRARY_HEADER.capitalize()) == "lib-1"
    assert seen[0].full_url.endswith("?parent=node-root")


def test_a_401_refreshes_once_and_retries(monkeypatch, _signed_in):
    seen = _serve(
        monkeypatch,
        _http_error(401, b'{"message": "Unauthorized"}'),
        _Response(200, b'{"ok": true}'),
    )

    assert api.get("/api/libraries") == {"ok": True}
    assert _signed_in["refresh"] == 1
    assert seen[1].get_header("Authorization") == "Bearer refreshed-token"


def test_a_second_401_says_what_to_do(monkeypatch, _signed_in):
    _serve(
        monkeypatch,
        _http_error(401, b'{"message": "Unauthorized"}'),
        _http_error(401, b'{"message": "Unauthorized"}'),
    )

    with pytest.raises(api.ApiError) as caught:
        api.get("/api/libraries")

    assert "studio login" in str(caught.value)
    assert caught.value.status == 401
    # Exactly one refresh: a client that retried forever on a dead session would
    # hammer Cognito and never tell anyone.
    assert _signed_in["refresh"] == 1


def test_a_403_is_its_own_type(monkeypatch):
    """403 and 401 say opposite things — signing in again does not help here."""
    _serve(monkeypatch, _http_error(403, b'{"error": "You are not a member of lib-2."}'))

    with pytest.raises(api.Forbidden) as caught:
        api.get("/api/nodes/node-1")

    assert "not a member" in str(caught.value)


def test_a_409_is_its_own_type(monkeypatch):
    """The UI keeps the rename field open on this; the CLI prompts rather than retries."""
    _serve(monkeypatch, _http_error(409, b'{"error": "\'characters\' already exists here"}'))

    with pytest.raises(api.Conflict):
        api.post("/api/nodes", {"parent": "node-root", "name": "characters"})


def test_a_404_is_its_own_type(monkeypatch):
    _serve(monkeypatch, _http_error(404, b'{"error": "No such object: node-nope"}'))

    with pytest.raises(api.NotFound):
        api.get("/api/nodes/node-nope")


def test_a_5xx_surfaces_the_apis_message(monkeypatch):
    _serve(monkeypatch, _http_error(502, b'{"error": "Could not read the catalog"}'))

    with pytest.raises(api.ApiError) as caught:
        api.get("/api/libraries")

    assert caught.value.status == 502
    assert "Could not read the catalog" in str(caught.value)


def test_a_non_json_gateway_body_falls_back_to_the_status(monkeypatch):
    """**The failure #301 names.** API Gateway's rejections are not always JSON.

    A client that threw on the parse would turn "your token expired" into a
    traceback with no status in it.
    """
    _serve(
        monkeypatch,
        _http_error(401, b"<html>Unauthorized</html>"),
        _http_error(401, b"<html>Unauthorized</html>"),
    )

    with pytest.raises(api.ApiError) as caught:
        api.get("/api/libraries")

    assert caught.value.status == 401
    assert "HTTP 401" in str(caught.value)


def test_an_unreachable_api_is_not_a_traceback(monkeypatch):
    def _urlopen(request, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(api.urllib.request, "urlopen", _urlopen)

    with pytest.raises(api.ApiError) as caught:
        api.get("/api/libraries")

    assert "Could not reach" in str(caught.value)
    assert caught.value.status == 0


def test_an_empty_body_is_an_empty_dict(monkeypatch):
    """A caller never has to tell "no content" from "failed" — exceptions carry that."""
    _serve(monkeypatch, _Response(204, b""))

    assert api.delete("/api/nodes/node-1") == {}


def test_libraries_returns_a_list_even_if_the_api_is_odd(monkeypatch):
    _serve(monkeypatch, _Response(200, json.dumps([{"id": "lib-1"}]).encode()))

    assert api.libraries() == [{"id": "lib-1"}]
