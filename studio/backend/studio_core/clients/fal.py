"""The fal.ai HTTP client — the third provider, and the third billing surface.

Written against fal's **queue API**: a hosted model addressed as
`https://queue.fal.run/<endpoint>`, priced per second of output, with no
deploy and no worker of ours — the same arrangement as Runpod's public
endpoints, so a registry entry whose `model` is `fal/<endpoint>` is a model
this service can run without a Replicate listing. Wan 3.0 is the reason it
exists: in September 2026 fal hosts it and neither Replicate nor Runpod does.

## What is the same as the other two, deliberately

The seam. `services/generate.py` reaches a provider through six names —
`create_prediction`, `get_prediction`, `normalise`, `download`,
`output_urls`, `cost` — and a `mode()` switch, and this module answers to the
same six. `STUDIO_FAL_MODE=fake` is set by `tests/conftest.py` beside the
other two, for the same reason and with the same three guards behind it.
`urllib`, no `requests`, no `fal-client`, for the same reason as well: the
API's dependency set is the Lambda image's.

## What is different, and has to be

**A request is addressed by app AND id**, as on Runpod by endpoint: status
is `/<owner>/<app>/requests/<id>/status`, so `get_prediction` takes the
model too. **The app, not the endpoint.** `alibaba/wan-3.0/text-to-video`
submits at that full path, but its requests live under `alibaba/wan-3.0` —
the third segment is a route inside the app, and a status GET with it in
the URL answers 405. Measured 2026-09-16 on the first live run, which the
CLI's wait then could not read (the generation was unaffected). The
status route answers 202, not 200, while the request is in flight.

**The result is a second call.** Runpod's status answers with the output in
it; fal's status says only `IN_QUEUE` / `IN_PROGRESS` / `COMPLETED`, and the
output is at `/<endpoint>/requests/<id>` once it is `COMPLETED`. A failed
request is `COMPLETED` too — the queue is done with it — and it is the result
route that answers with the error, as an HTTP error status. `get_prediction`
makes both calls and hands back one document.

**The document is fal's shape, and `normalise` is what turns it into the
seam's.** A webhook body is `{request_id, status: OK|ERROR, payload, error}`;
the closing code reads `id`, `status`, `output`, `error`. Rather than teach
`close_from_prediction` a second vocabulary for every key, each client
normalises its own document and the other two clients' `normalise` is the
identity. `PROVIDER_STATUS` knows `ok` and `error` for this one.

**The output is a file object, not a URL.** `payload.video` is
`{url, content_type, file_size, width, height, fps, duration}`; a model with
several outputs answers `images: [{url}, …]`. `output_urls` reads both.

**No price on the body.** fal bills per second of output at a published
rate, and says nothing about money in the response. `cost.amount` stays
null rather than being a number this service multiplied out itself — the
registry note carries the rate, and fal's dashboard is the bill. What is
real is `metrics.inference_time` on the status document, recorded as
`predict_time` when present.

**fal signs its webhooks with ED25519**, not an HMAC: four
`X-Fal-Webhook-*` headers and a public key set at a well-known URL. The
message is `request_id \\n user_id \\n timestamp \\n sha256(body)`; the key
set is fetched once per process and refreshed on a verification miss, since
a rotated key is the ordinary reason a signature stops matching. So the
callback URL carries nothing (unlike Runpod's `?sig=`), the receiver
forwards those four headers (like Replicate's three), and `cryptography` —
already in the image for Cognito's RS256 — does the check.

**The vocabulary is upper-case and short.** `IN_QUEUE`, `IN_PROGRESS`,
`COMPLETED` on the status route, `OK` / `ERROR` on the webhook, mapped in
`services/generate.PROVIDER_STATUS` next to the other two sets.
"""

import base64
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from studio_core import config
from studio_core.clients import replicate
from studio_core.clients.aws import ssm
from studio_core.errors import ConfigError, UpstreamError

logger = logging.getLogger(__name__)

UA = "xharness-studio/1.0"
API_ROOT = "https://queue.fal.run"
#: Where fal publishes each endpoint's OpenAPI document — unauthenticated, and
#: the same document its model page renders. `model_schema` reads it.
OPENAPI_URL = "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={endpoint}"
#: The public keys fal signs webhooks with.
JWKS_URL = "https://rest.fal.ai/.well-known/jwks.json"

#: What a registry `model` starts with when it is this provider's. The rest is
#: the endpoint id: `fal/alibaba/wan-3.0/text-to-video` →
#: `alibaba/wan-3.0/text-to-video`.
PREFIX = "fal/"

LIVE, FAKE = "live", "fake"

#: Same bound as the other clients', for the same reason: a queue submit
#: returns as soon as the request is queued, so this is a hung socket rather
#: than a slow model.
TIMEOUT = 30

#: The headers a fal webhook carries its proof in, lower-cased as API Gateway
#: and the receiver hand them on. `hook_handler.SIGNATURE_HEADERS` repeats
#: them as a literal because that file imports nothing from here.
SIGNATURE_HEADERS = (
    "x-fal-webhook-request-id",
    "x-fal-webhook-user-id",
    "x-fal-webhook-timestamp",
    "x-fal-webhook-signature",
)


class FalError(UpstreamError):
    """A failed fal call. An `UpstreamError`, so it answers 502."""


class OutputGone(FalError):
    """The output file is no longer at that URL.

    fal keeps a request's result for about an hour (six minutes past 10 KB),
    and the files it links for longer but not forever. Its own type for the
    same reason as Replicate's: the caller must not redrive it blindly.
    """


def is_model(model: str) -> bool:
    """Whether a registry `model` id names this provider."""
    return (model or "").startswith(PREFIX)


def endpoint_of(model: str) -> str:
    """The endpoint id behind `fal/<endpoint>` — where a request is submitted."""
    if not is_model(model):
        raise ValueError(f"{model!r} is not a fal model id (no {PREFIX!r} prefix)")
    return model[len(PREFIX):]


def app_of(model: str) -> str:
    """`<owner>/<app>` — where a request's status and result live.

    The first two segments of the endpoint; anything after them is a route
    inside the app and is not part of a request's address. See the module
    docstring for how that was learned.
    """
    return "/".join(endpoint_of(model).split("/")[:2])


def mode() -> str:
    """`live` or `fake`, read fresh on every call. See `replicate.mode`."""
    got = (os.environ.get("STUDIO_FAL_MODE") or LIVE).strip().lower()
    if got not in (LIVE, FAKE):
        raise ConfigError(f"STUDIO_FAL_MODE is {got!r}; it is {LIVE!r} or {FAKE!r}.")
    return got


def token() -> str:
    """The API key: the environment first, then the SSM SecureString.

    The same order and the same reasoning as `replicate.token`: `dev-up.sh`
    exports `FAL_KEY` from `dev.env`, the deployed function is handed a
    parameter *name* and reads the value at call time.
    """
    if mode() == FAKE:
        return "fake-no-token-needed"

    from_env = config.fal_token_env()
    if from_env:
        return from_env

    parameter = config.fal_token_parameter()
    if not parameter:
        raise ConfigError(
            "no fal.ai credential is configured: set FAL_KEY, or "
            "STUDIO_FAL_TOKEN_PARAMETER naming an SSM SecureString"
        )
    return ssm.secure_parameter(parameter)


# ── the fake ────────────────────────────────────────────────────────────────


def _fake_id(model: str, payload: dict) -> str:
    digest = hashlib.sha256(
        (model + json.dumps(payload, sort_keys=True, default=str)).encode()
    ).hexdigest()
    return f"fake-{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _fake_created(request_id: str) -> dict:
    return {"id": request_id, "status": "IN_QUEUE"}


def _fake_settled(request_id: str) -> dict:
    """A completed request in the webhook's shape, normalised. `.invalid`, as
    the other fakes."""
    return normalise({
        "request_id": request_id,
        "gateway_request_id": request_id,
        "status": "OK",
        "payload": {
            "video": {
                "url": f"https://fake.invalid/{request_id}/video.mp4",
                "content_type": "video/mp4",
            },
            "seed": 7,
            "duration": 5.0,
        },
    })


# ── the client ──────────────────────────────────────────────────────────────


def _request(method: str, url: str, *, body: dict | None = None,
             auth: bool = True) -> tuple[int, dict]:
    """One call. Answers `(status, document)` for any HTTP status.

    Returns the error body rather than raising on it, because on fal an HTTP
    error from the result route IS the request's outcome — see
    `get_prediction`. A transport failure still raises.
    """
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if auth:
        request.add_header("Authorization", f"Key {token()}")
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
            document = {"detail": detail}
        return exc.code, document if isinstance(document, dict) else {"detail": document}
    except OSError as exc:
        logger.warning("%s %s failed: %s", method, url, exc)
        raise FalError(f"{method} {url} failed: {exc}") from exc


def _refused(method: str, url: str, status: int, document: dict) -> FalError:
    """A fal answer that is a no, as the seam's error.

    Carries `status` and fal's own `detail`, because `detail` is what
    `submit_run` writes on the draft it hands back — without it a `401
    Authentication is required` reached the run as a URL and a blob, back
    when a submission that raised wedged the run at `pending` (2026-09-16).
    """
    return FalError(
        f"{method} {url} -> {status}: {json.dumps(document)[:500]}",
        status=status, detail=_error_text(document),
    )


def _error_text(document: dict) -> str:
    """fal's error bodies: `{"detail": "…"}`, or `{"detail": [{msg, loc}, …]}`
    from validation."""
    detail = document.get("detail", document)
    if isinstance(detail, list):
        return "; ".join(
            f"{'.'.join(str(p) for p in (item.get('loc') or []))}: {item.get('msg')}"
            if isinstance(item, dict) else str(item)
            for item in detail
        )
    return detail if isinstance(detail, str) else json.dumps(detail)


def create_prediction(model: str, payload: dict, *, webhook: str | None = None) -> dict:
    """Queue a request on the endpoint. **This is the call that bills.**

    The queue route, never `fal.run/<endpoint>` — the synchronous host holds
    the socket for the length of the generation, which is the same trap as
    Replicate's `Prefer: wait` and Runpod's `/runsync`. Queue it, and let the
    webhook (or `reconcile`) close it.

    The body is the payload itself — fal takes no `{"input": …}` envelope —
    and the webhook rides as a query parameter, `fal_webhook`. Answers
    `{"id": ..., "status": "IN_QUEUE"}` once normalised, which is all
    `dispatch` reads.
    """
    if mode() == FAKE:
        logger.info("[fal:FAKE] create_prediction %s — nothing billed", model)
        return _fake_created(_fake_id(model, payload))

    url = f"{API_ROOT}/{endpoint_of(model)}"
    if webhook:
        url += "?" + urllib.parse.urlencode({"fal_webhook": webhook})
    status, document = _request("POST", url, body=payload)
    if status >= 400:
        raise _refused("POST", url, status, document)
    if not document.get("request_id"):
        # Accepted and named nothing. Handed back without an `id` so the
        # route closes the run `failed` as "no prediction id" — knowable,
        # unlike a dropped socket, and not a refusal either.
        logger.warning("POST %s -> %s carried no request_id: %s",
                       url, status, json.dumps(document)[:500])
        return {}
    return normalise(document)


def get_prediction(prediction_id: str, *, model: str) -> dict:
    """One request, whatever state it is in, as one document. Reads; never bills.

    Two calls when the queue is done with it — the status, then the result —
    because the status route carries no output and the result route answers
    404 while the request is still running. An HTTP error from the result
    route is the request's own failure and closes the run `failed`, except
    the three that are about this caller rather than the request: a bad key
    (401/403) and a rate limit (429) raise, so the queue retries rather than
    recording a paid generation as lost.
    """
    if mode() == FAKE:
        logger.info("[fal:FAKE] get_prediction %s", prediction_id)
        return _fake_settled(prediction_id)

    base = f"{API_ROOT}/{app_of(model)}/requests/{prediction_id}"
    status, document = _request("GET", f"{base}/status")
    if status >= 400:
        raise _refused("GET", f"{base}/status", status, document)
    state = (document.get("status") or "").upper()
    if state != "COMPLETED":
        return {"id": prediction_id, "status": state or "IN_QUEUE",
                "metrics": document.get("metrics") or {}}

    result_status, result = _request("GET", base)
    if result_status in (401, 403, 429):
        raise _refused("GET", base, result_status, result)
    if result_status >= 400:
        return normalise({
            "request_id": prediction_id, "status": "ERROR",
            "error": f"{result_status}: {_error_text(result)}",
            "metrics": document.get("metrics") or {},
        })
    return normalise({
        "request_id": prediction_id, "status": "OK", "payload": result,
        "metrics": document.get("metrics") or {},
    })


def _without_echo(payload: dict) -> dict:
    """fal's validation detail minus the `input` each item echoes.

    A 422 item is `{type, loc, msg, input}`, and for an image field `input`
    is the list of presigned URLs `dispatch` minted — hard rule #3 says a
    signed URL is never stored, and this document is stored. `loc` and `msg`
    are the complaint; the echo is the payload, which the run already holds
    by node id.
    """
    detail = payload.get("detail")
    if not isinstance(detail, list):
        return payload
    return {**payload, "detail": [
        {k: v for k, v in item.items() if k != "input"} if isinstance(item, dict) else item
        for item in detail
    ]}


def normalise(document: dict) -> dict:
    """fal's document in the seam's shape: `id`, `status`, `output`, `error`.

    Applied to every document this module hands out and to every webhook body
    the consumer receives on the fal route — so the closing code reads one
    vocabulary. A document already in the seam's shape (an `id` and no
    `request_id`) is returned as it is, which is what makes the call safe to
    repeat and what lets the fakes above be written in either shape.

    `payload_error` — fal could not serialise the model's answer — is a
    failure whatever `status` says: there is nothing to download.

    **On an error the reason is under `payload`, not `error`.** fal's webhook
    and its result route both put a one-line wrapper in `error` — "Unexpected
    status code: 422" — and the model app's actual complaint in `payload`, as
    the `{"detail": [{loc, msg}, …]}` document a 422 carries. Reading `error`
    alone closed a run with the wrapper and threw the 18 KB that said
    `reference_image_urls: List should have at most 10 items` away, which
    is what left a person asking what a 422 means. The two are joined here,
    wrapper first, and `detail` keeps fal's document so the stored response
    still has it whole.
    """
    if "request_id" not in document:
        return document
    status = (document.get("status") or "").upper()
    error = document.get("error")
    if document.get("payload_error"):
        status, error = "ERROR", document["payload_error"]
    detail = None
    if status == "ERROR" and isinstance(document.get("payload"), dict):
        detail = _without_echo(document["payload"])
        words = _error_text(detail)
        if words and words != str(error):
            error = f"{error}: {words}" if error else words
    out = {
        "id": document["request_id"],
        "status": status,
        "output": document.get("payload") if status == "OK" else None,
        "error": None if error is None else str(error),
    }
    if detail is not None:
        out["detail"] = detail
    if document.get("metrics"):
        out["metrics"] = document["metrics"]
    return out


def output_urls(prediction: dict) -> list[str]:
    """Every file the request produced, in order.

    fal answers a file as an object — `{url, content_type, …}` — under
    `video` for the video models and `images` (a list) for the image ones;
    a `videos` list and a single `image` are read too, in that order, so a
    sibling endpoint does not need a second reader. A bare URL string in any
    of those places is accepted as well. A `succeeded` request with nothing
    here is closed `failed` by the caller, exactly as with the other two.
    """
    output = prediction.get("output")
    if not isinstance(output, dict):
        return [output] if isinstance(output, str) else []
    urls: list[str] = []
    for key in ("video", "videos", "image", "images"):
        value = output.get(key)
        items = value if isinstance(value, list) else [value]
        for item in items:
            url = item.get("url") if isinstance(item, dict) else item
            if isinstance(url, str) and url:
                urls.append(url)
    return urls


def cost(prediction: dict) -> dict | None:
    """What the request cost, as far as fal will say — which is not a price.

    Per second of output at the rate the registry note records, and the body
    carries no money. `predict_time` is `metrics.inference_time` when the
    status route reported one (a webhook body never does); `amount` stays
    null so `runs list` shows no price rather than a computed one.
    """
    metrics = prediction.get("metrics") or {}
    inference = metrics.get("inference_time")
    if inference is None:
        return None
    return {"amount": None, "currency": None, "predict_time": inference}


# ── the callback ────────────────────────────────────────────────────────────

_keys: list = []
_keys_fetched_at = 0.0
#: How long a fetched key set is trusted before a verification miss is allowed
#: to refetch it. Bounds how often a stream of forged callbacks can make this
#: process call fal, not how long a real key is believed — a real key that
#: verifies never triggers a refetch at all.
KEYS_REFETCH_AFTER = 300.0


def public_keys(*, refresh: bool = False) -> list:
    """fal's ED25519 verification keys, fetched once per process.

    `refresh=True` refetches, but only if the current set is older than
    `KEYS_REFETCH_AFTER` — the reason is above. Loaded lazily so the API
    never calls fal on import, and never at all unless a fal callback
    arrives.
    """
    global _keys, _keys_fetched_at
    stale = time.monotonic() - _keys_fetched_at > KEYS_REFETCH_AFTER
    if _keys and not (refresh and stale):
        return _keys
    status, document = _request("GET", JWKS_URL, auth=False)
    if status >= 400:
        raise FalError(f"GET {JWKS_URL} -> {status}")
    keys = []
    for jwk in document.get("keys") or []:
        raw = (jwk.get("x") or "") if isinstance(jwk, dict) else ""
        if not raw:
            continue
        try:
            keys.append(Ed25519PublicKey.from_public_bytes(_b64url_decode(raw)))
        except ValueError:
            continue
    if not keys:
        raise FalError(f"GET {JWKS_URL} carried no usable ED25519 key")
    _keys, _keys_fetched_at = keys, time.monotonic()
    return _keys


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_webhook(headers: dict, body: bytes, tolerance_seconds: int) -> None:
    """Raise `ValueError` unless `body` really came from fal.

    The message fal signs is the four values joined by newlines — request id,
    user id, timestamp, and the hex SHA-256 of the raw body — and the
    signature is hex ED25519 over it, checked against each published key in
    turn. The timestamp is bounded first, so a captured callback re-sent
    after the window is refused before any key is tried. A miss against the
    cached keys retries once against a fresh set, because rotation is the
    ordinary reason a real signature stops matching.
    """
    request_id = headers.get("x-fal-webhook-request-id", "")
    user_id = headers.get("x-fal-webhook-user-id", "")
    timestamp = headers.get("x-fal-webhook-timestamp", "")
    signature = headers.get("x-fal-webhook-signature", "")
    if not (request_id and user_id and timestamp and signature):
        raise ValueError("the callback is missing one of the four X-Fal-Webhook headers")
    try:
        stamp = int(timestamp)
    except ValueError:
        raise ValueError("the callback's timestamp is not an integer") from None
    if abs(time.time() - stamp) > tolerance_seconds:
        raise ValueError("the callback's timestamp is outside the tolerance window")
    try:
        raw_signature = bytes.fromhex(signature)
    except ValueError:
        raise ValueError("the callback's signature is not hex") from None

    message = "\n".join(
        [request_id, user_id, timestamp, hashlib.sha256(body).hexdigest()]
    ).encode()

    for attempt in (False, True):
        for key in public_keys(refresh=attempt):
            try:
                key.verify(raw_signature, message)
                return
            except InvalidSignature:
                continue
    raise ValueError("the callback's signature matches none of fal's keys")


def download(url: str, path: str, *, max_bytes: int) -> replicate.Downloaded:
    """Stream one output file to `path`. Same contract as `replicate.download`."""
    if mode() == FAKE:
        logger.info("[fal:FAKE] download %s — a placeholder image", url)
        body = replicate.placeholder_png()
        with open(path, "wb") as handle:
            handle.write(body)
        # No served type: the placeholder is a PNG whatever the test named
        # the output, and the name is what the test meant.
        return replicate.Downloaded(len(body), None)

    request = urllib.request.Request(url)
    request.add_header("User-Agent", UA)
    written = 0
    served = None
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, \
                open(path, "wb") as handle:
            served = response.headers.get("Content-Type")
            while chunk := response.read(1 << 20):
                written += len(chunk)
                if written > max_bytes:
                    raise FalError(
                        f"the model output exceeds {max_bytes} bytes; refusing it"
                    )
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404, 410):
            raise OutputGone(
                f"GET {url} -> {exc.code}: the output is not there") from exc
        raise FalError(f"GET {url} -> {exc.code}") from exc
    except OSError as exc:
        raise FalError(f"GET {url} failed: {exc}") from exc
    return replicate.Downloaded(written, served)


# ── the schema ──────────────────────────────────────────────────────────────


def _flatten_nullable(spec: dict) -> dict:
    """`anyOf: [X, {type: null}]` → X's keys on the spec itself.

    fal's generated schemas spell every optional field that way, and
    `services/schema.check` range-checks a field only when `type`, `minimum`
    and `maximum` sit at the top level. A one-armed `anyOf` is what the
    check would otherwise skip — `duration` 2–30 was the field that showed
    it. Anything with two non-null arms is left alone.
    """
    arms = [arm for arm in spec.get("anyOf") or [] if arm.get("type") != "null"]
    if len(arms) != 1 or "anyOf" not in spec:
        return spec
    flat = {key: value for key, value in spec.items() if key != "anyOf"}
    return {**arms[0], **flat}


def model_schema(model: str) -> tuple[dict, dict]:
    """`(input properties, all component schemas)` for `fal/<endpoint>`.

    Read from the OpenAPI document fal publishes for every endpoint — the
    same one its model page renders — so, unlike a Runpod entry, a fal entry
    carries no `input` block of its own and `models refresh` sees what the
    provider will accept today. The input component is the one the submit
    route's request body names; it is returned under `Input` as well as its
    own name, because `services/schema.check` reads `required` from `Input`.

    The fake returns two empty maps, as `replicate.model_schema` does, and
    `check` reports a skipped validation rather than inventing a pass.
    """
    if mode() == FAKE:
        logger.info("[fal:FAKE] model_schema %s -> {}", model)
        return {}, {}
    endpoint = endpoint_of(model)
    url = OPENAPI_URL.format(endpoint=urllib.parse.quote(endpoint, safe="/"))
    status, document = _request("GET", url, auth=False)
    if status >= 400:
        raise _refused("GET", url, status, document)
    schemas = (document.get("components") or {}).get("schemas") or {}
    submit = (document.get("paths") or {}).get(f"/{endpoint}") or {}
    ref = (
        ((submit.get("post") or {}).get("requestBody") or {})
        .get("content", {}).get("application/json", {}).get("schema", {})
        .get("$ref", "")
    )
    name = ref.rsplit("/", 1)[-1] if ref else next(
        (key for key in schemas if key.endswith("Input")), "")
    component = dict(schemas.get(name) or {})
    props = {
        key: _flatten_nullable(spec)
        for key, spec in (component.get("properties") or {}).items()
    }
    component["properties"] = props
    return props, {**schemas, "Input": component}

