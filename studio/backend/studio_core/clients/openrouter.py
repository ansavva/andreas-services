"""The OpenRouter HTTP client — the fourth provider, and the fourth billing surface.

Written against OpenRouter's **video generation API**: one route,
`POST https://openrouter.ai/api/v1/videos`, in front of every video model
OpenRouter resells, addressed by slug (`alibaba/wan-3.0`) and priced per
second of output at the upstream provider's list price — OpenRouter takes
its margin on credit purchases, not on inference. A registry entry whose
`model` is `openrouter/<slug>` is a model this service can run through it.
Wan 3.0 is the reason it exists: in September 2026 OpenRouter routes it
straight to Alibaba at a discount fal and Replicate do not pass on, and the
entry beside fal's lets a run be priced on either.

## What is the same as the other three, deliberately

The seam. `services/generate.py` reaches a provider through six names —
`create_prediction`, `get_prediction`, `normalise`, `download`,
`output_urls`, `cost` — and a `mode()` switch, and this module answers to the
same six. `STUDIO_OPENROUTER_MODE=fake` is set by `tests/conftest.py` beside
the other three, for the same reason and with the same three guards behind
it. `urllib`, no `requests`, no SDK, for the same reason as well: the API's
dependency set is the Lambda image's.

## What is different, and has to be

**The payload is translated, not passed through.** The other three take a
flat map of field → value, so `dispatch` writes a presigned URL straight
into the field the registry names. OpenRouter takes its images as objects in
two lists — `frame_images: [{type: image_url, image_url: {url}, frame_type:
first_frame}]` and `input_references: [{type: image_url, image_url: {url}}]`
— so the registry names the seam's fields (`first_frame`, `last_frame`,
`input_references`), `dispatch` binds them as it binds any other, and
`create_prediction` folds them into OpenRouter's shape at the last moment.
The same place `dispatch` folds a LoRA's scale in, for the same reason: the
translation belongs beside the wire, and the run record keeps the seam's
field names, which are what the `SEND#` rows already say.

**One slug serves every mode.** fal has an endpoint per mode and the
registry has an entry per endpoint; OpenRouter's `alibaba/wan-3.0` is
text-to-video with no frame and image-to-video with one. So there is ONE
entry with an optional `first_frame`, because `generate.entry_for` finds a
run's entry by model id and two entries sharing a slug would resolve to
whichever came first.

**A job is addressed by id alone**, as on Replicate: `GET /videos/<id>` is
global. `get_prediction` still takes `model`, keyword-only, because the seam
passes it and the other two need it.

**The document is OpenRouter's shape, and `normalise` is what turns it into
the seam's.** A poll answers `{id, status, unsigned_urls, usage, error}`; a
webhook wraps the same under `{type: video.generation.<status>, created_at,
data: {…}}`. `normalise` unwraps the envelope when there is one and writes
`output` as the `unsigned_urls` list, so the closing code reads one
vocabulary. `PROVIDER_STATUS` knows `pending` and `expired` for this one.

**The output URL needs the key.** `unsigned_urls` is a misnomer: each is
`/videos/<id>/content?index=N` on OpenRouter's own host and answers 401
without `Authorization`, so `download` here sends the bearer the other
clients' downloads do not. The URL is not a credential — it is the job id
again — which is why storing it in the run's response breaks no rule.

**The price is on the body.** `usage.cost` is what OpenRouter charged, in
dollars, so `cost.amount` is a real number here as it is on Runpod — and it
is the one place the discount OpenRouter advertises can be read off rather
than believed.

**OpenRouter signs a webhook only if the workspace has a secret**, and a
secret is a second thing to provision, so the callback URL carries its own
proof instead: `?sig=<HMAC-SHA256(key, run_id)>` under the API key this
service already holds, exactly as Runpod's does, and `services/callbacks.py`
recomputes it. `clients/runpod.py` says what that does and does not protect
against; nothing here differs.

**The schema is synthesised from the model list.** OpenRouter publishes no
OpenAPI document per model; `GET /videos/models` answers each model's
`supported_resolutions`, `supported_aspect_ratios`, `supported_durations`,
`supported_frame_images` and whether it takes a seed or audio, and
`model_schema` reads that into the two maps `services/schema.check` wants.
Live, like fal's, so `models refresh` sees what OpenRouter will accept
today; and narrower than fal's, because a knob the list does not name
(`negative_prompt`, prompt expansion) is one OpenRouter does not forward.

**The vocabulary is lower-case and has an `expired`.** `pending`,
`in_progress`, `completed`, `failed`, `cancelled`, `expired` — mapped in
`services/generate.PROVIDER_STATUS` next to the other three sets.
"""

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request

from studio_core import config
from studio_core.clients.aws import ssm
from studio_core.errors import ConfigError, UpstreamError

logger = logging.getLogger(__name__)

UA = "xharness-studio/1.0"
API_ROOT = "https://openrouter.ai/api/v1"

#: What a registry `model` starts with when it is this provider's. The rest is
#: the slug: `openrouter/alibaba/wan-3.0` → `alibaba/wan-3.0`.
PREFIX = "openrouter/"

LIVE, FAKE = "live", "fake"

#: Same bound as the other clients', for the same reason: a submit answers
#: 202 as soon as the job is queued, so this is a hung socket rather than a
#: slow model.
TIMEOUT = 30

#: The seam's names for the image inputs, and how each folds into OpenRouter's
#: request. A registry entry names these under `images.start` / `images.end` /
#: `images.refs`; nothing else in this service knows the wire shape.
FIRST_FRAME, LAST_FRAME, REFERENCES = "first_frame", "last_frame", "input_references"
FRAME_FIELDS = (FIRST_FRAME, LAST_FRAME)

#: The job's terminal words, as the poll route and the webhook both spell them.
TERMINAL = ("completed", "failed", "cancelled", "expired")


class OpenRouterError(UpstreamError):
    """A failed OpenRouter call. An `UpstreamError`, so it answers 502."""


class OutputGone(OpenRouterError):
    """The output is no longer at that URL.

    OpenRouter streams the file from the upstream provider and says nothing
    about how long it will; a 404 or 410 on the content route is the same
    situation as Replicate's expired file, and its own type for the same
    reason: the caller must not redrive it blindly.
    """


def is_model(model: str) -> bool:
    """Whether a registry `model` id names this provider."""
    return (model or "").startswith(PREFIX)


def slug_of(model: str) -> str:
    """The OpenRouter slug behind `openrouter/<slug>`."""
    if not is_model(model):
        raise ValueError(f"{model!r} is not an OpenRouter model id (no {PREFIX!r} prefix)")
    return model[len(PREFIX):]


def mode() -> str:
    """`live` or `fake`, read fresh on every call. See `replicate.mode`."""
    got = (os.environ.get("STUDIO_OPENROUTER_MODE") or LIVE).strip().lower()
    if got not in (LIVE, FAKE):
        raise ConfigError(f"STUDIO_OPENROUTER_MODE is {got!r}; it is {LIVE!r} or {FAKE!r}.")
    return got


def token() -> str:
    """The API key: the environment first, then the SSM SecureString.

    The same order and the same reasoning as `replicate.token`: `dev-up.sh`
    exports `OPENROUTER_API_KEY` from `dev.env`, the deployed function is
    handed a parameter *name* and reads the value at call time.
    """
    if mode() == FAKE:
        return "fake-no-token-needed"

    from_env = config.openrouter_token_env()
    if from_env:
        return from_env

    parameter = config.openrouter_token_parameter()
    if not parameter:
        raise ConfigError(
            "no OpenRouter credential is configured: set OPENROUTER_API_KEY, or "
            "STUDIO_OPENROUTER_TOKEN_PARAMETER naming an SSM SecureString"
        )
    return ssm.secure_parameter(parameter)


# ── the fake ────────────────────────────────────────────────────────────────


def _fake_id(model: str, payload: dict) -> str:
    digest = hashlib.sha256(
        (model + json.dumps(payload, sort_keys=True, default=str)).encode()
    ).hexdigest()
    return f"gen-vid-{digest[:10]}-{digest[10:30]}"


def _fake_created(job_id: str) -> dict:
    return {"id": job_id, "status": "pending",
            "polling_url": f"{API_ROOT}/videos/{job_id}"}


def _fake_settled(job_id: str) -> dict:
    """A completed job in the poll route's shape, normalised. `.invalid`, as
    the other fakes."""
    return normalise({
        "id": job_id,
        "generation_id": job_id,
        "polling_url": f"{API_ROOT}/videos/{job_id}",
        "status": "completed",
        "unsigned_urls": [f"https://fake.invalid/api/v1/videos/{job_id}/content?index=0"],
        "usage": {"cost": 0.0, "is_byok": False},
    })


# ── the client ──────────────────────────────────────────────────────────────


def _request(method: str, url: str, *, body: dict | None = None,
             auth: bool = True) -> tuple[int, dict]:
    """One call. Answers `(status, document)` for any HTTP status.

    Returns the error body rather than raising on it, as `fal._request` does,
    so a caller can decide what a 4xx means for the job it asked about. A
    transport failure still raises.
    """
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if auth:
        request.add_header("Authorization", f"Bearer {token()}")
    request.add_header("User-Agent", UA)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, json.loads(
                response.read().decode(errors="replace") or "{}", strict=False)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        logger.warning("%s %s -> %s: %s", method, url, exc.code, detail[:500])
        try:
            document = json.loads(detail, strict=False)
        except json.JSONDecodeError:
            document = {"error": {"message": detail}}
        return exc.code, document if isinstance(document, dict) else {"error": document}
    except OSError as exc:
        logger.warning("%s %s failed: %s", method, url, exc)
        raise OpenRouterError(f"{method} {url} failed: {exc}") from exc


def _error_text(document: dict) -> str:
    """OpenRouter's error bodies: `{"error": {"code": 402, "message": "…"}}`,
    or a bare `{"error": "…"}` on a job document."""
    error = document.get("error", document)
    if isinstance(error, dict):
        message = error.get("message")
        return message if isinstance(message, str) else json.dumps(error)
    return error if isinstance(error, str) else json.dumps(error)


def _refused(method: str, url: str, status: int, document: dict) -> OpenRouterError:
    """An OpenRouter answer that is a no, as the seam's error.

    Carries `status` and OpenRouter's own `message`, because `detail` is
    what `submit_run` writes on the draft it hands back — a `402
    Insufficient credits` is the ordinary one here, and the run should say
    so in those words.
    """
    return OpenRouterError(
        f"{method} {url} -> {status}: {json.dumps(document)[:500]}",
        status=status, detail=_error_text(document),
    )


def _image_part(url: str) -> dict:
    return {"type": "image_url", "image_url": {"url": url}}


def request_body(model: str, payload: dict, *, webhook: str | None = None) -> dict:
    """The seam's payload in OpenRouter's request shape. Pure; the module
    docstring says why the fold lives here.

    `first_frame` and `last_frame` (scalars) become `frame_images` entries
    carrying their `frame_type`; `input_references` (a list) becomes image
    parts. A frame field bound as a one-item list is unwrapped, so a registry
    entry that names one under `refs` by mistake still sends a frame rather
    than a 400. Everything else — `prompt`, `duration`, `resolution`,
    `aspect_ratio`, `generate_audio`, `seed` — is OpenRouter's own name
    already and passes through.
    """
    body: dict = {}
    frames: list[dict] = []
    references: list[dict] = []
    for field, value in payload.items():
        if field in FRAME_FIELDS:
            url = value[0] if isinstance(value, list) and value else value
            if isinstance(url, str) and url:
                frames.append({**_image_part(url), "frame_type": field})
        elif field == REFERENCES:
            items = value if isinstance(value, list) else [value]
            references.extend(_image_part(one) for one in items if isinstance(one, str) and one)
        else:
            body[field] = value
    if frames:
        body["frame_images"] = frames
    if references:
        body["input_references"] = references
    body["model"] = slug_of(model)
    if webhook:
        body["callback_url"] = webhook
    return body


def create_prediction(model: str, payload: dict, *, webhook: str | None = None) -> dict:
    """Queue a job. **This is the call that bills.**

    `POST /videos` answers 202 with the job's id and a polling URL the moment
    it is queued; the generation runs on OpenRouter's side and the webhook
    (or `reconcile`) closes it. Answers `{"id": ..., "status": "pending"}`
    once normalised, which is all `dispatch` reads.
    """
    if mode() == FAKE:
        logger.info("[openrouter:FAKE] create_prediction %s — nothing billed", model)
        return _fake_created(_fake_id(model, payload))

    url = f"{API_ROOT}/videos"
    status, document = _request("POST", url, body=request_body(model, payload, webhook=webhook))
    if status >= 400:
        raise _refused("POST", url, status, document)
    if not document.get("id"):
        # Accepted and named nothing. Handed back without an `id` so the
        # route closes the run `failed` as "no prediction id" — knowable,
        # unlike a dropped socket, and not a refusal either.
        logger.warning("POST %s -> %s carried no id: %s", url, status, json.dumps(document)[:500])
        return {}
    return normalise(document)


def get_prediction(prediction_id: str, *, model: str) -> dict:
    """One job, whatever state it is in. Reads; never bills.

    A 4xx here is about this caller or this id, never the job's own outcome
    — a failed job is a 200 with `status: failed` — so every HTTP error
    raises, and the queue retries rather than recording a paid generation as
    lost on a rate limit.
    """
    if mode() == FAKE:
        logger.info("[openrouter:FAKE] get_prediction %s", prediction_id)
        return _fake_settled(prediction_id)

    url = f"{API_ROOT}/videos/{prediction_id}"
    status, document = _request("GET", url)
    if status >= 400:
        raise _refused("GET", url, status, document)
    return normalise(document)


def normalise(document: dict) -> dict:
    """OpenRouter's document in the seam's shape: `id`, `status`, `output`, `error`.

    Applied to every document this module hands out and to every webhook body
    the consumer receives on the OpenRouter route. A webhook is an envelope —
    `{type: "video.generation.completed", created_at, data: {…}}` — and the
    job document is `data`; a poll answers the job document bare. Both land
    here, and a document already in the seam's shape (an `output` key and no
    `unsigned_urls`) is returned as it is, which is what makes the call safe
    to repeat.

    `output` is the `unsigned_urls` list on a completed job and `None`
    otherwise; `usage` and `generation_id` are kept for `cost` and for the
    stored response.
    """
    if isinstance(document.get("data"), dict) and str(document.get("type", "")).startswith("video.generation."):
        document = document["data"]
    if "output" in document and "unsigned_urls" not in document:
        return document
    status = str(document.get("status") or "").lower()
    urls = [one for one in (document.get("unsigned_urls") or []) if isinstance(one, str) and one]
    error = document.get("error")
    if status in TERMINAL and status != "completed" and error is None:
        error = f"the job {status}"
    out = {
        "id": document.get("id"),
        "status": status,
        "output": urls if status == "completed" else None,
        "error": None if error is None else _error_text({"error": error}),
    }
    for key in ("generation_id", "model", "usage", "polling_url"):
        if document.get(key) is not None:
            out[key] = document[key]
    return out


def output_urls(prediction: dict) -> list[str]:
    """Every file the job produced, in order — the `unsigned_urls`, once
    normalised. A `succeeded` job with nothing here is closed `failed` by the
    caller, exactly as with the other three."""
    output = prediction.get("output")
    if isinstance(output, str):
        return [output]
    return [one for one in (output or []) if isinstance(one, str)]


def cost(prediction: dict) -> dict | None:
    """What the job cost. **A price**, in dollars, from `usage.cost`.

    The one number that says what OpenRouter's discount is worth: the
    registry note carries the list rate, and this is what was charged. No
    duration is reported, so `predict_time` stays null.
    """
    usage = prediction.get("usage")
    amount = usage.get("cost") if isinstance(usage, dict) else None
    if amount is None:
        return None
    return {"amount": amount, "currency": "USD", "predict_time": None}


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
    """Stream one output file to `path`. Same contract as `replicate.download`,
    plus the bearer: the content route is OpenRouter's and refuses without it."""
    if mode() == FAKE:
        from studio_core.clients.replicate import placeholder_png
        logger.info("[openrouter:FAKE] download %s — a placeholder image", url)
        body = placeholder_png()
        with open(path, "wb") as handle:
            handle.write(body)
        return len(body)

    request = urllib.request.Request(url)
    request.add_header("Authorization", f"Bearer {token()}")
    request.add_header("User-Agent", UA)
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, \
                open(path, "wb") as handle:
            while chunk := response.read(1 << 20):
                written += len(chunk)
                if written > max_bytes:
                    raise OpenRouterError(
                        f"the model output exceeds {max_bytes} bytes; refusing it"
                    )
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            raise OutputGone(
                f"GET {url} -> {exc.code}: the output is not there") from exc
        raise OpenRouterError(f"GET {url} -> {exc.code}") from exc
    except OSError as exc:
        raise OpenRouterError(f"GET {url} failed: {exc}") from exc
    return written


# ── the schema ──────────────────────────────────────────────────────────────

_models: dict = {}
_models_fetched_at = 0.0
#: How long the fetched model list is trusted. It changes when OpenRouter
#: adds a model or a tier, which is rarely; a submit re-validates against it,
#: so a stale list costs at most one refused payload before the refetch.
MODELS_REFETCH_AFTER = 600.0


def models(*, refresh: bool = False) -> dict:
    """Every video model OpenRouter lists, keyed by slug. Cached per process.

    Unauthenticated on OpenRouter's side and read without the bearer, so a
    schema fetch needs no credential — `studio models show` works before a
    key is configured, as it does for fal.
    """
    global _models, _models_fetched_at
    stale = time.monotonic() - _models_fetched_at > MODELS_REFETCH_AFTER
    if _models and not (refresh or stale):
        return _models
    url = f"{API_ROOT}/videos/models"
    status, document = _request("GET", url, auth=False)
    if status >= 400:
        raise _refused("GET", url, status, document)
    listed = document.get("data") if isinstance(document.get("data"), list) else []
    found = {item["id"]: item for item in listed if isinstance(item, dict) and item.get("id")}
    if not found:
        raise OpenRouterError(f"GET {url} listed no video models")
    _models, _models_fetched_at = found, time.monotonic()
    return _models


def _properties(card: dict) -> tuple[dict, list[str]]:
    """The input properties and the required list, read off one model card."""
    props: dict = {
        "prompt": {"type": "string", "title": "Prompt",
                   "description": "What happens in the clip."},
    }
    frames = card.get("supported_frame_images") or []
    for field in FRAME_FIELDS:
        if field in frames:
            props[field] = {
                "type": "string", "format": "uri", "title": field.replace("_", " ").title(),
                "description": f"The clip's {field.replace('_', ' ')}. Sent as a `frame_images` entry.",
            }
    props[REFERENCES] = {
        "type": "array", "items": {"type": "string", "format": "uri"},
        "title": "Input references",
        "description": "Reference images to guide the clip. Honoured by providers that take them; OpenRouter's card does not say which.",
    }
    if card.get("supported_resolutions"):
        props["resolution"] = {"type": "string", "title": "Resolution",
                               "enum": list(card["supported_resolutions"])}
    if card.get("supported_aspect_ratios"):
        props["aspect_ratio"] = {"type": "string", "title": "Aspect ratio",
                                 "enum": list(card["supported_aspect_ratios"])}
    if card.get("supported_sizes"):
        props["size"] = {"type": "string", "title": "Size",
                         "enum": list(card["supported_sizes"])}
    durations = card.get("supported_durations") or []
    if durations:
        props["duration"] = {"type": "integer", "title": "Duration",
                             "enum": list(durations),
                             "minimum": min(durations), "maximum": max(durations)}
    if card.get("generate_audio"):
        props["generate_audio"] = {"type": "boolean", "title": "Generate audio", "default": True}
    if card.get("seed"):
        props["seed"] = {"type": "integer", "title": "Seed"}
    return props, ["prompt"]


def model_schema(model: str) -> tuple[dict, dict]:
    """`(input properties, all component schemas)` for `openrouter/<slug>`.

    Synthesised from the model's card on `GET /videos/models` — the module
    docstring says why there is nothing else to read. Returned under `Input`
    with a `required` list, because `services/schema.check` reads it there.

    The fake returns two empty maps, as `replicate.model_schema` does, and
    `check` reports a skipped validation rather than inventing a pass.
    """
    if mode() == FAKE:
        logger.info("[openrouter:FAKE] model_schema %s -> {}", model)
        return {}, {}
    slug = slug_of(model)
    card = models().get(slug) or models(refresh=True).get(slug)
    if card is None:
        raise OpenRouterError(f"OpenRouter lists no video model {slug!r}", status=404,
                              detail=f"no such video model on OpenRouter: {slug}")
    props, required = _properties(card)
    return props, {"Input": {"required": required, "properties": props}}
