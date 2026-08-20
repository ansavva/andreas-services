"""One transport for every studio API call (#301).

Every HTTP call the CLI makes goes through `request`. That is the point: bearer
token, refresh-on-401, library header and error mapping are decided once, and no
caller re-decides any of them.

**Two error shapes, not one.** The API answers `{"error": "..."}`; API Gateway's
Cognito authorizer answers `{"message": "Unauthorized"}` — and a gateway response
is not guaranteed to be JSON at all. Parsing failures therefore fall back to the
status rather than raising, because a client that throws on an unparseable body
turns "your token expired" into a traceback. `frontend/src/apis/client.ts` handles
exactly this and is the reference.

**Refresh is driven by the API's 401, not by the token's `exp`.** A clock that
disagrees with Cognito's would either refresh on every call or never. One retry,
then the error says what to do.

`urllib` rather than `requests`: the pipeline's dependency set is small on
purpose, and this needs nothing `urllib` lacks.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from studio_pipeline.adapters import auth

# The header naming which library a request is about. Absent on almost every
# request — the common case is one library, and asking a user to name the only
# thing they have is a question with one answer.
LIBRARY_HEADER = "X-Studio-Library"

TIMEOUT_SECONDS = 30


class ApiError(RuntimeError):
    """The API refused or failed. `status` is the HTTP code."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class NotFound(ApiError):
    """404."""


class Forbidden(ApiError):
    """403 — signing in again will not help. See the API's `errors.ForbiddenError`."""


class Conflict(ApiError):
    """409 — a name collision. The caller usually wants to prompt, not retry."""


def _library() -> str | None:
    import os

    return os.environ.get("STUDIO_LIBRARY_ID") or None


def _decode(body: bytes, status: int) -> str:
    """The most useful message this response can yield.

    Order matters: the API's own `error` first, the gateway's `message` second,
    the status last. Never raises — an unparseable body is a fact about the
    response, not a reason to lose the status.
    """
    try:
        parsed = json.loads(body.decode())
    except (ValueError, UnicodeDecodeError):
        return f"HTTP {status}"
    if isinstance(parsed, dict):
        for key in ("error", "message"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return f"HTTP {status}"


def _raise(status: int, body: bytes) -> None:
    message = _decode(body, status)
    if status == 403:
        raise Forbidden(message, status)
    if status == 404:
        raise NotFound(message, status)
    if status == 409:
        raise Conflict(message, status)
    if status == 401:
        raise ApiError(f"{message} — run: studio login", status)
    raise ApiError(message, status)


def _send(method: str, url: str, token: str, payload: dict | None) -> tuple[int, bytes]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - https, our own API
    request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    library = _library()
    if library:
        request.add_header(LIBRARY_HEADER, library)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        # Read the body here: an HTTPError *is* the response, and letting it
        # close unread throws away the only message the API sent.
        return error.code, error.read()
    except urllib.error.URLError as error:
        raise ApiError(f"Could not reach {auth.api_url()}: {error.reason}", 0) from error


def request(method: str, path: str, payload: dict | None = None, **params) -> dict | list:
    """Call the API, refreshing the token once if it says the token is stale.

    Returns the decoded body. A 204 or an empty body is `{}` rather than `None`,
    so a caller never has to distinguish "no content" from "failed" — the
    exceptions carry that.
    """
    url = f"{auth.api_url()}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"

    status, body = _send(method, url, auth.id_token(), payload)
    if status == 401:
        # One retry, with a token refreshed against Cognito rather than read
        # from the file. If it 401s again the session is genuinely dead, and
        # `_raise` says what to do about it.
        status, body = _send(method, url, auth.id_token(refresh=True), payload)

    if status >= 400:
        _raise(status, body)
    if not body:
        return {}
    try:
        return json.loads(body.decode())
    except (ValueError, UnicodeDecodeError) as error:
        raise ApiError(f"The API returned a body that is not JSON (HTTP {status}).", status) from error


def get(path: str, **params) -> dict | list:
    return request("GET", path, None, **params)


def post(path: str, payload: dict | None = None, **params) -> dict | list:
    return request("POST", path, payload or {}, **params)


def patch(path: str, payload: dict, **params) -> dict | list:
    return request("PATCH", path, payload, **params)


def delete(path: str, **params) -> dict | list:
    return request("DELETE", path, None, **params)


def libraries() -> list:
    """The caller's libraries. The one route that is not library-scoped."""
    result = get("/api/libraries")
    return result if isinstance(result, list) else []
