"""The shared Replicate HTTP client for every studio-* engine.

Lifted from three verbatim copies that had drifted apart in small ways. Holds
the two workarounds that are easy to lose in a rewrite, both learned the hard
way:

  * Cloudflare in front of Replicate rejects urllib's default "Python-urllib/x.y"
    User-Agent with a 403 (error 1010). A real UA is required on API calls AND
    on output downloads from replicate.delivery.
  * Never submit with `Prefer: wait`. A timed-out wait retries internally and
    can create duplicate BILLED predictions. Create, then poll.
"""

import json
import time
import urllib.error
import urllib.request

from studio_pipeline import env_value

UA = "xharness-studio/1.0"
API_ROOT = "https://api.replicate.com/v1"


class ReplicateError(Exception):
    """A failed Replicate call, or a missing token."""


def load_token() -> str:
    """REPLICATE_API_TOKEN from the environment, falling back to the repo .env."""
    tok = env_value("REPLICATE_API_TOKEN")
    if tok:
        return tok
    raise ReplicateError("REPLICATE_API_TOKEN not set (environment or studio/.env).")


def api(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req) as r:
            # Replicate's `logs` field can carry raw control characters.
            return json.loads(r.read().decode(), strict=False)
    except urllib.error.HTTPError as e:
        raise ReplicateError(f"{method} {url} -> {e.code}: {e.read().decode()[:500]}")


def api_text(url: str, token: str) -> str:
    """GET a non-JSON endpoint. The README endpoint returns raw markdown."""
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req) as r:
            return r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        raise ReplicateError(f"GET {url} -> {e.code}: {e.read().decode()[:300]}")


def download(url: str, local: str) -> str:
    """Fetch an output file. Uses an explicit UA — see the note above."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req) as r, open(local, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return local


def create_prediction(model: str, payload: dict, token: str) -> dict:
    """Start a prediction on `owner/name`. Bills. No `Prefer: wait` — see above."""
    return api("POST", f"{API_ROOT}/models/{model}/predictions", token, {"input": payload})


def predictions_endpoint(model: str) -> str:
    """The URL a payload will be POSTed to — shown in the approval render."""
    return f"{API_ROOT}/models/{model}/predictions"


def poll(prediction_id: str, token: str, interval: int, timeout: int,
         on_status=None) -> dict:
    """Poll until the prediction settles. Raises TimeoutError past `timeout`.

    Returns the final prediction body; the caller decides what a non-succeeded
    status means, since it still has a run record to close out.
    """
    url = f"{API_ROOT}/predictions/{prediction_id}"
    deadline = time.time() + timeout
    cur = api("GET", url, token)
    while cur.get("status") not in ("succeeded", "failed", "canceled"):
        if time.time() > deadline:
            raise TimeoutError(f"gave up after {timeout}s")
        time.sleep(interval)
        cur = api("GET", url, token)
        if on_status:
            on_status(cur.get("status"))
    return cur


