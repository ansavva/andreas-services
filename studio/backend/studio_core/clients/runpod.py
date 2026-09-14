"""The Runpod HTTP client — the second provider, and the second billing surface.

`clients/replicate.py` opens with **"THIS MODULE IS THE ENTIRE BILLING SURFACE"**
and that sentence is no longer true: `create_prediction` below bills too. It is
written against Runpod's *public endpoints* — hosted models addressed as
`https://api.runpod.ai/v2/<endpoint>/run`, priced per image, with no deploy and
no worker of ours — so a registry entry whose `model` is `runpod/<endpoint>`
is a model this service can run without a Replicate listing. `z-image-turbo`
was the first: it is on Replicate too, and the decision was to call Runpod
directly rather than go through a reseller.

## What is the same as Replicate, deliberately

The seam. `services/generate.py` holds one closing implementation and reaches
the provider through five names — `create_prediction`, `get_prediction`,
`download`, `output_urls`, `cost` — and a `mode()` switch, so this module
answers to the same five and a reader who knows the other client knows this
one. `STUDIO_RUNPOD_MODE=fake` is set by `tests/conftest.py` beside
`STUDIO_REPLICATE_MODE=fake`, for the same reason and with the same three
guards behind it. `urllib`, no `requests`, for the same reason as well.

## What is different, and has to be

**A job is addressed by endpoint AND id.** Replicate's `/predictions/<id>` is
global; Runpod's status is `/v2/<endpoint>/status/<id>`, so `get_prediction`
takes the model too. `services/generate.py` passes the run's own `model` on
every read.

**The output is a document, not a URL.** A public endpoint answers
`{"output": {"result": "<url>", "cost": 0.005}}` — the URL under `result`
(the article that introduced the model said `image_url`; it was wrong, and
the shape here is the one measured on 2026-09-14), and the **price in
dollars**, which Replicate never sends. `output_urls` and `cost` read those.

**Runpod signs nothing.** No `webhook-signature`, no per-account secret, no
Standard-Webhooks envelope — the callback is a bare POST of the job document.
So the callback URL carries its own proof: `?sig=<HMAC-SHA256(key, run_id)>`
under the API key this service already holds, and `services/callbacks.py`
recomputes it before believing the body. Replay is harmless rather than
guarded: `close_from_prediction` is idempotent and refuses a job id that is
not the run's, so a captured callback re-sent can only re-report what it
already reported. What the signature stops is a **forged** body closing a run
with somebody else's output, which the run id alone — public to anyone with a
link — would not.

**The vocabulary is upper-case and has a `TIMED_OUT`.** `IN_QUEUE`,
`IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, mapped in
`services/generate.PROVIDER_STATUS` next to Replicate's words; the two sets do
not collide once lower-cased.
"""

import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request

from studio_core import config
from studio_core.clients.aws import ssm
from studio_core.errors import ConfigError, UpstreamError

logger = logging.getLogger(__name__)

UA = "xharness-studio/1.0"
API_ROOT = "https://api.runpod.ai/v2"

#: What a registry `model` starts with when it is this provider's. The rest is
#: the public endpoint id: `runpod/z-image-turbo` → `z-image-turbo`.
PREFIX = "runpod/"

LIVE, FAKE = "live", "fake"

#: Same bound as Replicate's, for the same reason: `/run` returns as soon as the
#: job is queued, so this is a hung socket rather than a slow model.
TIMEOUT = 30


class RunpodError(UpstreamError):
    """A failed Runpod call. An `UpstreamError`, so it answers 502."""


class OutputGone(RunpodError):
    """The output file is no longer at that URL.

    Runpod serves public-endpoint outputs from `image.runpod.ai` and the
    article says the URLs last seven days. Its own type for the same reason as
    Replicate's: the caller must not redrive it blindly.
    """


def is_model(model: str) -> bool:
    """Whether a registry `model` id names this provider."""
    return (model or "").startswith(PREFIX)


def endpoint_of(model: str) -> str:
    """The public endpoint id behind `runpod/<endpoint>`."""
    if not is_model(model):
        raise ValueError(f"{model!r} is not a Runpod model id (no {PREFIX!r} prefix)")
    return model[len(PREFIX):]


def mode() -> str:
    """`live` or `fake`, read fresh on every call. See `replicate.mode`."""
    got = (os.environ.get("STUDIO_RUNPOD_MODE") or LIVE).strip().lower()
    if got not in (LIVE, FAKE):
        raise ConfigError(
            f"STUDIO_RUNPOD_MODE is {got!r}; it is {LIVE!r} or {FAKE!r}."
        )
    return got


def token() -> str:
    """The API key: the environment first, then the SSM SecureString.

    The same order and the same reasoning as `replicate.token`: `dev-up.sh`
    exports `RUNPOD_API_KEY` from `dev.env`, the deployed function is handed a
    parameter *name* and reads the value at call time.
    """
    if mode() == FAKE:
        return "fake-no-token-needed"

    from_env = config.runpod_token_env()
    if from_env:
        return from_env

    parameter = config.runpod_token_parameter()
    if not parameter:
        raise ConfigError(
            "no Runpod credential is configured: set RUNPOD_API_KEY, or "
            "STUDIO_RUNPOD_TOKEN_PARAMETER naming an SSM SecureString"
        )
    return ssm.secure_parameter(parameter)


# ── the fake ────────────────────────────────────────────────────────────────


def _fake_id(model: str, payload: dict) -> str:
    digest = hashlib.sha256(
        (model + json.dumps(payload, sort_keys=True, default=str)).encode()
    ).hexdigest()
    return f"fake{digest[:20]}-u1"


def _fake_created(job_id: str) -> dict:
    return {"id": job_id, "status": "IN_QUEUE"}


def _fake_settled(job_id: str) -> dict:
    """A completed job in the public-endpoint shape. `.invalid`, as Replicate's."""
    return {
        "id": job_id,
        "status": "COMPLETED",
        "delayTime": 0,
        "executionTime": 0,
        "output": {"cost": 0.0, "result": f"https://fake.invalid/{job_id}/result.png"},
    }


# ── the client ──────────────────────────────────────────────────────────────


def _request(method: str, url: str, *, body: dict | None = None) -> dict:
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
        raise RunpodError(f"{method} {url} -> {exc.code}: {detail}") from exc
    except OSError as exc:
        logger.warning("%s %s failed: %s", method, url, exc)
        raise RunpodError(f"{method} {url} failed: {exc}") from exc
    return json.loads(raw, strict=False)


def create_prediction(model: str, payload: dict, *, webhook: str | None = None) -> dict:
    """Queue a job on the public endpoint. **This is the call that bills.**

    `/run`, never `/runsync`: the synchronous form holds the socket for the
    length of the generation and answers 408 past its ceiling — with the job
    still running and still billed — which is the same trap as Replicate's
    `Prefer: wait`. Queue it, and let the webhook (or `reconcile`) close it.

    Answers `{"id": ..., "status": "IN_QUEUE"}`, which is all `dispatch` reads.
    """
    if mode() == FAKE:
        logger.info("[runpod:FAKE] create_prediction %s — nothing billed", model)
        return _fake_created(_fake_id(model, payload))

    body: dict = {"input": payload}
    if webhook:
        body["webhook"] = webhook
    return _request("POST", f"{API_ROOT}/{endpoint_of(model)}/run", body=body)


def get_prediction(prediction_id: str, *, model: str) -> dict:
    """One job, whatever state it is in. Reads; never bills.

    Needs the model because the status route is per endpoint — see the module
    docstring. `model` is keyword-only so a caller cannot hand the two strings
    over the wrong way round.
    """
    if mode() == FAKE:
        logger.info("[runpod:FAKE] get_prediction %s", prediction_id)
        return _fake_settled(prediction_id)
    return _request("GET", f"{API_ROOT}/{endpoint_of(model)}/status/{prediction_id}")


def output_urls(prediction: dict) -> list[str]:
    """Every file the job produced, in order.

    A public endpoint returns `output.result` — a URL, or a list of them for a
    model that makes several. A bare string or list at `output` is accepted
    too, so a custom worker that answers Replicate's way is not refused on
    shape alone. A `succeeded` job with nothing here is closed `failed` by the
    caller, exactly as with Replicate.
    """
    output = prediction.get("output")
    if isinstance(output, dict):
        output = output.get("result", output.get("image_url"))
    if isinstance(output, str):
        return [output]
    return [item for item in (output or []) if isinstance(item, str)]


def cost(prediction: dict) -> dict | None:
    """What the job cost. **A price this time**, not just a duration.

    A public endpoint says what it charged, in dollars, under `output.cost` —
    the one thing Replicate's body never carries. Recorded under the same keys
    `runs list` already prints, with `predict_time` from `executionTime`
    (milliseconds, converted) so the two providers' runs read alike.
    """
    output = prediction.get("output")
    amount = output.get("cost") if isinstance(output, dict) else None
    execution_ms = prediction.get("executionTime")
    if amount is None and execution_ms is None:
        return None
    return {
        "amount": amount,
        "currency": "USD" if amount is not None else None,
        "predict_time": None if execution_ms is None else execution_ms / 1000,
    }


# ── the callback ────────────────────────────────────────────────────────────


def callback_signature(run_id: str) -> str:
    """The proof a callback URL for `run_id` carries. See the module docstring."""
    return hmac.new(token().encode(), run_id.encode(), hashlib.sha256).hexdigest()


def verify_callback(run_id: str, signature: str) -> None:
    """Raise unless `signature` is the one `callback_signature` minted for this run."""
    if not signature:
        raise ValueError("the callback carried no signature")
    if not hmac.compare_digest(signature, callback_signature(run_id)):
        raise ValueError("the callback's signature does not match")


def download(url: str, path: str, *, max_bytes: int) -> int:
    """Stream one output file to `path`. Same contract as `replicate.download`."""
    if mode() == FAKE:
        from studio_core.clients.replicate import placeholder_png
        logger.info("[runpod:FAKE] download %s — a placeholder image", url)
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
                    raise RunpodError(
                        f"the model output exceeds {max_bytes} bytes; refusing it"
                    )
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404, 410):
            raise OutputGone(
                f"GET {url} -> {exc.code}: the output is not there") from exc
        raise RunpodError(f"GET {url} -> {exc.code}") from exc
    except OSError as exc:
        raise RunpodError(f"GET {url} failed: {exc}") from exc
    return written
