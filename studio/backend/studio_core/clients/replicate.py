"""The Replicate HTTP client. **THIS MODULE IS THE ENTIRE BILLING SURFACE.**

It was the pipeline's, at `adapters/replicate.py`, and that module's docstring
made the same claim for the CLI: every paid call in the repo was one of its six
functions and the deployed app had no HTTP client in its dependencies at all. The
second half of that is what changed. Generation moved here so that a submission
survives the process that started it — a webhook closes the run rather than a
poll loop somebody has to leave a terminal open for — and the credential had to
move with it.

So the sentence is preserved rather than deleted: **the only paid calls in this
repository are `create_prediction` below and nothing else.** Everything else here
reads — a schema, a README, a prediction's status, a webhook secret — and the
pipeline now holds no provider token at all.

Two workarounds carried over verbatim, both learned the hard way and both easy to
lose in a rewrite:

  * Cloudflare in front of Replicate rejects urllib's default
    `Python-urllib/x.y` User-Agent with a 403 (error 1010). A real UA is required
    on API calls **and** on output downloads from `replicate.delivery`.
  * **Never submit with `Prefer: wait`.** A timed-out wait retries internally and
    can create duplicate BILLED predictions. Create, then let the webhook answer.

`urllib` rather than `requests`, because the backend's dependency set does not
carry an HTTP client and adding one to reach a single host would be the largest
part of this change by weight. The pipeline's version made the same choice.

`STUDIO_REPLICATE_MODE` — HOW A TEST AVOIDS SPENDING MONEY
----------------------------------------------------------
`live` is the default and `fake` is set only by `tests/conftest.py`, exactly as
in the pipeline — so a `dev-up.sh` session bills precisely as it always did and
hard rule #2's approval gate is untouched by any of this. `fake` answers every
function locally: no socket is opened, no token is read, nothing is billed.

**The two halves of studio deliberately spell this the same way.** The pipeline's
suite has had the switch since the engine was one module; this one had nothing to
guard, because nothing here could reach a provider. Now that both can, a reader
who knows one suite's guard knows the other's, and a divergence between them is
visible rather than a thing to discover.

Three guards, failing differently on purpose — the same three the pipeline runs:

| Guard | Catches |
|---|---|
| `STUDIO_REPLICATE_MODE=fake` | every call through this module |
| a dud `REPLICATE_API_TOKEN` | a live call if the mode is ever unset — 401, not a bill |
| an autouse socket guard | a paid call reached **indirectly**, which neither of the above can see |
"""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import struct
import time
import urllib.error
import urllib.request
import zlib

from studio_core import config
from studio_core.clients.aws import ssm
from studio_core.errors import ConfigError, UpstreamError

logger = logging.getLogger(__name__)

UA = "xharness-studio/1.0"
API_ROOT = "https://api.replicate.com/v1"

LIVE, FAKE = "live", "fake"

#: How long any single Replicate HTTP call may take. Every one of them is a
#: small JSON round trip — creating a prediction returns as soon as it is
#: queued, because there is no `Prefer: wait` — so this bounds a hung socket
#: rather than a slow model. Downloads pass their own, larger value.
TIMEOUT = 30


class ReplicateError(UpstreamError):
    """A failed Replicate call.

    An `UpstreamError`, so `app_factory` answers 502 without this module knowing
    anything about HTTP status codes: the provider failing is not the caller's
    request being wrong.
    """


def mode() -> str:
    """`live` or `fake`, read fresh on every call.

    An unrecognised value is a refusal rather than a fallback: falling back to
    `live` would turn a typo into a bill, and falling back to `fake` would turn
    one into a silently unrendered job. Read at call time and not bound at
    import, so a test that sets it after this module is imported is still obeyed.
    """
    got = (os.environ.get("STUDIO_REPLICATE_MODE") or LIVE).strip().lower()
    if got not in (LIVE, FAKE):
        raise ConfigError(
            f"STUDIO_REPLICATE_MODE is {got!r}; it is {LIVE!r} or {FAKE!r}."
        )
    return got


def token() -> str:
    """The provider token: the environment first, then the SSM SecureString.

    **The environment is checked first and that is not a security hole**, it is
    what makes local development work. `dev-up.sh` runs this API as an ordinary
    process on a laptop that has no parameter of its own, with the token already
    in `~/.config/andreas-services/studio/dev.env`. The deployed function has no
    such variable — the deploy workflow sets a parameter *name* and never a
    value — so in prod this always falls through to SSM.

    A machine that has neither is a `ConfigError` and a 500 naming both places,
    rather than a 401 from Replicate that reads as the provider being down.
    """
    if mode() == FAKE:
        return "fake-no-token-needed"

    from_env = config.replicate_token_env()
    if from_env:
        return from_env

    parameter = config.replicate_token_parameter()
    if not parameter:
        raise ConfigError(
            "no Replicate credential is configured: set REPLICATE_API_TOKEN, or "
            "STUDIO_REPLICATE_TOKEN_PARAMETER naming an SSM SecureString"
        )
    return ssm.secure_parameter(parameter)


# ── the fake ────────────────────────────────────────────────────────────────
#
# Deterministic on purpose: a prediction id is a hash of what was asked for, so
# two identical submissions in a test produce the same id. Nothing here sleeps,
# and nothing here opens a socket.


def _fake_id(model: str, payload: dict) -> str:
    digest = hashlib.sha256(
        (model + json.dumps(payload, sort_keys=True, default=str)).encode()
    ).hexdigest()
    return f"fake{digest[:20]}"


def _fake_created(prediction_id: str, model: str, payload: dict) -> dict:
    return {
        "id": prediction_id,
        "model": model,
        "input": payload,
        "status": "starting",
        "output": None,
        "urls": {"get": f"{API_ROOT}/predictions/{prediction_id}"},
    }


def _fake_settled(prediction_id: str) -> dict:
    """A succeeded prediction. The output URL is `.invalid` deliberately.

    RFC 2606 reserves `.invalid`, so if `download` is ever reached in `live` mode
    against a fake's output the DNS lookup fails immediately and loudly rather
    than resolving to somebody's server.
    """
    return {
        "id": prediction_id,
        "status": "succeeded",
        "output": [f"https://fake.invalid/{prediction_id}/0.png"],
        "metrics": {"predict_time": 0.0},
    }


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (
        struct.pack(">I", len(body))
        + kind
        + body
        + struct.pack(">I", binascii.crc32(kind + body) & 0xFFFFFFFF)
    )


def placeholder_png(side: int = 64) -> bytes:
    """A real, decodable PNG that is visibly not a render.

    Real because things downstream do real work on an output — they hash it, the
    SPA draws it, `s3.content_hash` records its MD5 — and magic bytes with a PNG
    header on the front fail all of that in ways that look like service bugs.
    Visibly a placeholder because a `fake` left on must be obvious on sight, so
    it is flat magenta.

    Hand-rolled from `zlib` and `struct` rather than through Pillow: the backend
    installs `--only main` into the Lambda image and an imaging library added for
    a test fixture would ship to production. Thirty lines beats a dependency.
    """
    row = b"\x00" + b"\xff\x00\xdc" * side
    raw = row * side
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


# ── the client ──────────────────────────────────────────────────────────────


def _request(method: str, url: str, *, body: dict | None = None,
             text: bool = False):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token()}")
    request.add_header("User-Agent", UA)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        logger.warning("%s %s -> %s: %s", method, url, exc.code, detail)
        raise ReplicateError(f"{method} {url} -> {exc.code}: {detail}") from exc
    except OSError as exc:
        logger.warning("%s %s failed: %s", method, url, exc)
        raise ReplicateError(f"{method} {url} failed: {exc}") from exc
    if text:
        return raw
    # Replicate's `logs` field can carry raw control characters.
    return json.loads(raw, strict=False)


def create_prediction(model: str, payload: dict, *, webhook: str | None = None) -> dict:
    """Start a prediction on `owner/name`. **This is the call that bills.**

    `webhook_events_filter` is `["completed"]` and not the default. Replicate
    will otherwise deliver `start`, `output` and `logs` events too, and every one
    of them would wake a Lambda that has nothing to do — `output` in particular
    fires per partial result, so a run would pay a cold start per intermediate
    frame to look at a row and put it back.

    No `Prefer: wait`. See the module docstring: a timed-out wait retries
    internally and can create a second BILLED prediction for one submission.
    """
    if mode() == FAKE:
        logger.info("[replicate:FAKE] create_prediction %s — nothing billed", model)
        return _fake_created(_fake_id(model, payload), model, payload)

    body: dict = {"input": payload}
    if webhook:
        body["webhook"] = webhook
        body["webhook_events_filter"] = ["completed"]
    return _request("POST", f"{API_ROOT}/models/{model}/predictions", body=body)


def get_prediction(prediction_id: str) -> dict:
    """One prediction, whatever state it is in. Reads; never bills."""
    if mode() == FAKE:
        logger.info("[replicate:FAKE] get_prediction %s", prediction_id)
        return _fake_settled(prediction_id)
    return _request("GET", f"{API_ROOT}/predictions/{prediction_id}")


def predictions_endpoint(model: str) -> str:
    """The URL a payload will be POSTed to — shown in the approval render."""
    return f"{API_ROOT}/models/{model}/predictions"


def model_schema(model: str) -> tuple[dict, dict]:
    """`(input properties, all component schemas)` for `owner/name`.

    Both halves are needed: enums frequently live behind a `$ref` to a sibling
    component rather than inline on the property itself.

    The fake returns two empty maps, which is the honest answer — it knows no
    schemas — and `services.schema.check` reads that as "could not fetch" and
    reports a skipped validation rather than inventing a pass.
    """
    if mode() == FAKE:
        logger.info("[replicate:FAKE] model_schema %s -> {}", model)
        return {}, {}
    body = _request("GET", f"{API_ROOT}/models/{model}")
    schemas = (
        (body.get("latest_version") or {})
        .get("openapi_schema", {})
        .get("components", {})
        .get("schemas", {})
    )
    return schemas.get("Input", {}).get("properties", {}), schemas


def model_readme(model: str) -> str:
    """The model's README as raw markdown. Read by `studio add-model`."""
    if mode() == FAKE:
        return f"# fake\n\nNo README was fetched. {model}\n"
    return _request("GET", f"{API_ROOT}/models/{model}/readme", text=True)


def webhook_secret() -> str:
    """The account's default webhook signing key, cached for the container.

    One key for the whole account rather than one per webhook, which is why this
    is safe to cache: it changes only when a person rotates it, and a rotation
    invalidates in-flight callbacks either way.
    """
    if mode() == FAKE:
        return "whsec_ZmFrZS1zZWNyZXQtbm90LXJlYWw="
    if not _SECRET:
        body = _request("GET", f"{API_ROOT}/webhooks/default/secret")
        key = body.get("key")
        if not key:
            raise ReplicateError("the webhook secret endpoint returned no key")
        _SECRET.append(key)
    return _SECRET[0]


#: A one-element list rather than a module global rebound by `webhook_secret`,
#: so `reset_secret` below is the only thing that clears it and a reader looking
#: for "who invalidates this" finds one answer.
_SECRET: list[str] = []


def reset_secret() -> None:
    """Drop the cached webhook secret. For tests, and for a rotation."""
    _SECRET.clear()


def verify_webhook(secret: str, webhook_id: str, timestamp: str,
                   signature_header: str, body: bytes, tolerance: int) -> None:
    """Raise unless this really is Replicate calling, recently.

    Replicate signs webhooks the Standard Webhooks way: the signed content is
    `<id>.<timestamp>.<body>`, the MAC is HMAC-SHA256 under the base64 secret
    with its `whsec_` prefix stripped, and the header carries a **space-separated
    list** of `v1,<base64>` pairs so a key rotation can present two at once. Any
    one of them matching is a pass.

    **The body must be the exact bytes that arrived.** Re-serialising the parsed
    JSON changes key order and whitespace and produces a MAC over something the
    sender never signed — which fails closed, so it would present as "every
    callback is forged" rather than as a signing bug.

    Two separate refusals, and the timestamp one is not decoration: a signature
    stays valid forever, so without a bounded window a captured callback could be
    replayed to re-close a run and re-upload its output indefinitely.
    """
    if not (webhook_id and timestamp and signature_header):
        raise ValueError("the callback carried no signature headers")

    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        raise ValueError("the callback's timestamp is not an integer") from None
    if abs(time.time() - sent_at) > tolerance:
        raise ValueError("the callback's timestamp is outside the accepted window")

    try:
        key = base64.b64decode(secret.split("_", 1)[-1])
    except (ValueError, binascii.Error):
        raise ValueError("the webhook secret is not base64") from None

    signed = f"{webhook_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    for candidate in signature_header.split():
        version, _, value = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(value, expected):
            return
    raise ValueError("the callback's signature does not match")


def download(url: str, path: str, *, max_bytes: int) -> int:
    """Stream one output file to `path`. Returns the byte count.

    **To disk in chunks, never into memory.** A 200 MB clip held as a `bytes` is
    200 MB of Lambda heap that the upload then has to hold a second time; going
    through the filesystem keeps the callback's memory flat whatever the model
    produced, and lets the object go up as a single `PutObject` so its ETag
    stays the MD5 of its bytes. See `config.max_output_bytes`.

    `max_bytes` is enforced as the bytes arrive rather than from
    `Content-Length`, which a provider need not send and which a caller must not
    be asked to trust. Over the line the partial file is left for the caller's
    `finally` to clear and the download is refused.
    """
    if mode() == FAKE:
        logger.info("[replicate:FAKE] download %s — a placeholder image", url)
        body = placeholder_png()
        with open(path, "wb") as handle:
            handle.write(body)
        return len(body)

    request = urllib.request.Request(url)
    request.add_header("User-Agent", UA)
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, \
                open(path, "wb") as handle:
            while chunk := response.read(1 << 20):
                written += len(chunk)
                if written > max_bytes:
                    raise ReplicateError(
                        f"the model output exceeds {max_bytes} bytes; refusing it"
                    )
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        raise ReplicateError(f"GET {url} -> {exc.code}") from exc
    except OSError as exc:
        raise ReplicateError(f"GET {url} failed: {exc}") from exc
    return written
