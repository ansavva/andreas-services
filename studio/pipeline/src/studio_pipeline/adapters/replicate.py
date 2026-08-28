"""The shared Replicate HTTP client for every studio-* engine.

**THIS MODULE IS THE ENTIRE BILLING SURFACE OF STUDIO.** Every paid call in the
repo is one of the six functions below, and the only importers are six modules
under `engine/`: `turnaround`, `runner`, `submit`, `board`, `schema`, `add_model`.
The backend and the frontend import nothing of the sort — the deployed app has
no HTTP client in its dependencies at all — so "can this bill?" has exactly one
answer and it is here.

Lifted from three verbatim copies that had drifted apart in small ways. Holds
the two workarounds that are easy to lose in a rewrite, both learned the hard
way:

  * Cloudflare in front of Replicate rejects urllib's default "Python-urllib/x.y"
    User-Agent with a 403 (error 1010). A real UA is required on API calls AND
    on output downloads from replicate.delivery.
  * Never submit with `Prefer: wait`. A timed-out wait retries internally and
    can create duplicate BILLED predictions. Create, then poll.

`STUDIO_REPLICATE_MODE` — HOW A TEST AVOIDS SPENDING MONEY
----------------------------------------------------------
`live` (the default, and the default when nothing is set) is the client above.
`fake` answers all six functions locally: no socket is opened, no token is read,
nothing is billed.

**It is one switch because it used to be none.** Each test that reached the
engine monkeypatched this module by hand — `test_board.py` had a fixture
patching three functions, `test_turnaround.py` patched a fourth to refuse — and a new
test file that forgot simply called `api.replicate.com` for real. Stubbing
spread across the suite is not a policy; a mode the suite sets once is.

Three things about it are deliberate:

  * **`live` is the default, and `fake` is set only by `tests/conftest.py`.**
    An ordinary shell has neither, so `studio run` bills exactly as it always
    did — against dev or `--profile prod` alike — and hard rule #2's
    full-payload approval gate is untouched by any of this.
  * **The mode is read at CALL time**, not bound at import. Same reason
    `s3.bucket()` and `ddb.table()` are functions: a module constant is
    evaluated before Click has parsed anything.
  * **The fake is LOUD.** Every call prints to stderr and the media it writes is
    visibly a placeholder. A `fake` left on by accident has to be obvious inside
    one command, not discovered in a delivered render.

It is not the only guard. `tests/conftest.py` also blocks non-loopback sockets,
which catches a paid call reached INDIRECTLY — through a module this switch
knows nothing about — and that a config flag cannot see by construction.
"""

import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

from studio_pipeline import env_value

UA = "xharness-studio/1.0"
API_ROOT = "https://api.replicate.com/v1"

LIVE, FAKE = "live", "fake"

#: Where the fake looks for canned output before generating its own. A test that
#: needs a REAL clip — the one thing the generator below will not invent — puts
#: files here and the fake serves them by extension.
FAKE_DIR_VAR = "STUDIO_REPLICATE_FAKE_DIR"


class ReplicateError(Exception):
    """A failed Replicate call, or a missing token."""


def mode() -> str:
    """`live` or `fake`, read fresh on every call.

    An unrecognised value is a refusal rather than a fallback: falling back to
    `live` would turn a typo into a bill, and falling back to `fake` would turn
    one into a silently unrendered job.
    """
    got = (env_value("STUDIO_REPLICATE_MODE") or LIVE).strip().lower()
    if got not in (LIVE, FAKE):
        raise ReplicateError(
            f"STUDIO_REPLICATE_MODE is {got!r}; it is {LIVE!r} or {FAKE!r}.")
    return got


def _loud(what: str) -> None:
    """Say so, on stderr, every single time."""
    print(f"[replicate:FAKE] {what} — nothing was submitted and nothing billed",
          file=sys.stderr)


def load_token() -> str:
    """REPLICATE_API_TOKEN from the environment, the config dir, or the repo .env."""
    if mode() == FAKE:
        return "fake-no-token-needed"
    tok = env_value("REPLICATE_API_TOKEN")
    if tok:
        return tok
    # Names the config dir first because that is where it should be put now,
    # and names `studio/.env` because that is where an older checkout has it.
    raise ReplicateError(
        "REPLICATE_API_TOKEN not set. Put it in "
        "~/.config/andreas-services/studio/dev.env (preferred), export it, or "
        "leave it in studio/.env."
    )




# ── the fake ────────────────────────────────────────────────────────────────
#
# Deterministic on purpose: a prediction id is a hash of what was asked for, so
# two identical submissions in a test produce the same id and a diff of a run
# journal is stable. Nothing here sleeps, and nothing here opens a socket.

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _fake_id(model: str, payload: dict) -> str:
    digest = hashlib.sha256(
        (model + json.dumps(payload, sort_keys=True, default=str)).encode()
    ).hexdigest()
    return f"fake{digest[:20]}"


def _fake_prediction(prediction_id: str, model: str, payload: dict) -> dict:
    return {"id": prediction_id, "model": model, "input": payload,
            "status": "starting", "output": None,
            "urls": {"get": f"{API_ROOT}/predictions/{prediction_id}"}}


def _fake_settled(prediction_id: str) -> dict:
    """A succeeded prediction. The output URLs are `.invalid` deliberately.

    RFC 2606 reserves `.invalid`, so if `download` is ever reached in `live`
    mode against a fake's output the DNS lookup fails immediately and loudly
    rather than resolving to somebody's server.
    """
    return {"id": prediction_id, "status": "succeeded",
            "output": [f"https://fake.invalid/{prediction_id}/0.png"],
            "metrics": {"predict_time": 0.0}}


def _placeholder_image(dest: pathlib.Path) -> None:
    """A real, decodable image that is visibly not a render.

    Real because the pipeline does real work on outputs — it hashes them,
    builds contact sheets, reads their dimensions — and magic bytes with a PNG
    header on the front fail all of that in ways that look like pipeline bugs.
    Visibly a placeholder because a `fake` left on must be obvious on sight.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (512, 512), (255, 0, 220))
    draw = ImageDraw.Draw(image)
    for offset in range(-512, 512, 64):
        draw.line([(offset, 0), (offset + 512, 512)], fill=(0, 0, 0), width=8)
    draw.text((16, 16), "STUDIO FAKE\nnot a render", fill=(255, 255, 255))
    image.save(dest)


def _fake_download(url: str, local: str) -> str:
    dest = pathlib.Path(local)
    dest.parent.mkdir(parents=True, exist_ok=True)

    canned = os.environ.get(FAKE_DIR_VAR)
    if canned:
        source = pathlib.Path(canned) / f"output{dest.suffix.lower()}"
        if source.exists():
            _loud(f"download {url} <- {source}")
            dest.write_bytes(source.read_bytes())
            return local

    if dest.suffix.lower() in IMAGE_SUFFIXES:
        _loud(f"download {url} -> a generated placeholder image")
        _placeholder_image(dest)
        return local

    # **Video is the one thing this will not invent.** Encoding a real clip
    # would mean shelling out to ffmpeg on every download, and a test that
    # actually exercises a video path wants a known clip rather than a
    # generated one. Point STUDIO_REPLICATE_FAKE_DIR at a directory holding
    # `output.mp4` and it is served above; otherwise this is honest bytes with
    # a name on them, and anything that decodes will fail loudly rather than
    # subtly.
    _loud(f"download {url} -> placeholder bytes (no {FAKE_DIR_VAR} entry for "
          f"{dest.suffix or 'this extension'})")
    dest.write_bytes(b"studio-fake-output:" + url.encode())
    return local


# ── the client ──────────────────────────────────────────────────────────────


def api(method: str, url: str, token: str, body: dict | None = None) -> dict:
    if mode() == FAKE:
        _loud(f"{method} {url}")
        if url.endswith("/predictions") and body is not None:
            model = url.removeprefix(f"{API_ROOT}/models/").removesuffix("/predictions")
            return _fake_prediction(_fake_id(model, body.get("input", {})),
                                    model, body.get("input", {}))
        if "/predictions/" in url:
            return _fake_settled(url.rsplit("/", 1)[-1])
        # A schema read (`GET /models/<owner>/<name>`). An empty body is the
        # honest answer: the fake knows no schemas, and `engine/schema.py`
        # reports a missing one rather than inventing a validation pass.
        return {}
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
    if mode() == FAKE:
        _loud(f"GET {url} (text)")
        return f"# fake\n\nNo README was fetched. {url}\n"
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
    if mode() == FAKE:
        return _fake_download(url, local)
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
    if mode() == FAKE:
        _loud(f"poll {prediction_id} -> succeeded (immediately, no sleep)")
        settled = _fake_settled(prediction_id)
        if on_status:
            on_status(settled["status"])
        return settled
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


