"""
Headless-render fetch backend.

Some webpage sources don't serve their content to a plain HTTP GET: the markup
arrives only after client-side JavaScript runs, or the site sits behind a
JS/proof-of-work bot challenge (e.g. SiteGround's sgcaptcha) that returns a
challenge stub to anything that isn't a real browser. For those sources the
admin sets `render_js` and the processor swaps the in-process `fetcher.fetch_url`
for `fetch_rendered` here.

`fetch_rendered` is a drop-in for `fetch_url`: same `(url, timeout) -> (status,
html)` contract, so it slots straight into the pipeline's injectable `fetch_fn`.
The actual browser lives in a dedicated `scout-source-renderer` Lambda (Chromium
is too heavy for the shared events-api image); we invoke it synchronously and
return its rendered HTML. A hard failure raises, mirroring `fetch_url` raising on
HTTP errors, so the pipeline records it as a failed link outcome (or fails the
run for the root page) rather than silently extracting from nothing.
"""

import json
import os

import boto3

_lambda = None

# Generous default: a render includes page load plus, for challenged sites, the
# in-page proof-of-work solve and its redirect. The renderer also enforces its
# own per-page timeout; this is the outer invoke ceiling.
DEFAULT_TIMEOUT = 60


def _client():
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda")
    return _lambda


def fetch_rendered(url, timeout=DEFAULT_TIMEOUT):
    """Render `url` in the headless-browser Lambda and return (status, html).

    Raises RuntimeError on an unconfigured renderer or a render failure, so the
    caller treats it like any other fetch error."""
    fn = os.environ.get("SCOUT_RENDERER_FN")
    if not fn:
        raise RuntimeError("SCOUT_RENDERER_FN is not configured")

    resp = _client().invoke(
        FunctionName=fn,
        InvocationType="RequestResponse",
        Payload=json.dumps({"url": url, "timeout_ms": int(timeout) * 1000}).encode(),
    )
    # An unhandled exception inside the renderer surfaces as FunctionError.
    if resp.get("FunctionError"):
        raw = resp["Payload"].read().decode("utf-8", errors="replace")
        raise RuntimeError(f"renderer error: {raw}")

    payload = json.loads(resp["Payload"].read().decode("utf-8", errors="replace"))
    status = int(payload.get("status") or 0)
    if status < 200 or payload.get("error"):
        raise RuntimeError(payload.get("error") or f"render failed (status {status})")
    return status, payload.get("html") or ""
