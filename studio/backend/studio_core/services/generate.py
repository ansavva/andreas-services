"""The half of a run that bills, and the one place that closes one.

**This is `engine/submit.py`'s second half, moved.** The nine steps it named —
gather, preflight, render, draft, presign, create, poll, upload, close — are now
split across the two halves of studio along the line of who can do them:

    gather ─┐
    render  ├─ the CLI, and the SPA's plan editor.  Authoring.  Nothing bills.
    draft  ─┘
    ─────────────────────────────────────────────────────────────────────────
    preflight ─┐
    presign     │
    create      ├─ HERE.  The only thing holding a provider credential.
    upload      │
    close      ─┘

**`poll` is not in that list and its absence is the point of the change.** A
prediction was waited on by the process that started it, so a 15-minute video
meant a terminal somebody could not close, a killed CLI meant a run wedged at
`pending` forever, and the SPA could not submit at all. Replicate calls back on
completion instead, and `close` runs off that callback.

**`close` is reached from three places and is written once.** That invariant is
what this module exists to hold, and it is why closing a run is a function here
rather than code in whichever handler happens to be running:

| Trigger | Where it runs |
|---|---|
| `services/callbacks.py`, driven by `handlers/aws/worker` | prod — an SQS consumer draining what the receiver queued |
| `services/callbacks.py`, driven by `handlers/local/consumer` | a developer's laptop, long-polling that machine's own queue, running the working tree |
| `POST /api/runs/<id>/reconcile` | a callback that never arrived, and any machine with no receiver provisioned |

The first two are the same module reached by different drivers; the third asks
the provider directly rather than waiting to be told. All three land in
`close_from_prediction`, which is **idempotent**: a run already in a terminal
state is returned untouched rather than having its output uploaded twice. That
matters more than it looks — SQS is at-least-once and the receiver acks before
anything has been verified, so a duplicate is ordinary traffic rather than an
incident.

## What did NOT move, and why

**The approval gate stays in `routes/runs.py`.** It is a property of the run row,
not of the provider, and the route that owns the state machine is the one that
owns the transition it guards. This module is handed a record whose approval has
already been checked and whose `plan_digest` still matches; it does not re-derive
that and it must not.

**The payload render stays in the CLI.** Hard rule #2 is about a person reading
two documents and answering, and nothing here is in front of a person. What this
module guarantees is narrower and mechanical: it rebuilds the payload from the
**plan and from nothing else**, so what is sent is what was approved.

**The download does not happen in the request that receives the callback**, and
that is the other half of the split. `handlers/aws/hook` enqueues the raw body
and answers in milliseconds; pulling a 200 MB clip through the socket Replicate
is waiting on would hold it open for the length of the transfer, and an
exception part-way would lose an output somebody had already paid for with
nothing to retry from. It is a queue redrive now.

## Hard rule #3, at the only moment it can be broken

Assets reach Replicate only as short-lived presigned URLs minted here, at the
last possible moment, and never stored. `routes/runs.py` refuses a URL-shaped
binding when the run is written, which is what makes that possible: every send
names a node, so there is nothing to sign but this bucket's own objects.
"""

import json
import logging
import mimetypes
import os
import re
import tempfile

from studio_core import config
from studio_core.clients import replicate
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import catalog, layout, registry, schema

logger = logging.getLogger(__name__)

#: Replicate's vocabulary on the left, studio's on the right. Two words differ
#: and both differences are deliberate: studio has no `starting`/`processing`
#: split (a run that has gone out is `running`, and a second word for the first
#: two seconds of it would be a state nothing acts on), and `canceled` is spelled
#: `cancelled` here because `catalog.RUN_STATUSES` has always spelled it that
#: way. Anything unrecognised is `failed` rather than passed through — an
#: unmapped provider word reaching `PATCH /api/runs/<id>` is a 400 on the one
#: call that has to succeed, because it is the only report a paid prediction
#: will ever make.
PROVIDER_STATUS = {
    "starting": "running",
    "processing": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "canceled": "cancelled",
}

#: What an output file is called when the run named nothing. A filename, never an
#: identity: a run is addressed by its id.
DEFAULT_NAME = {"image": "image", "video": "video"}
DEFAULT_EXT = {"image": ".jpg", "video": ".mp4"}

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """A safe stem for a downloaded file. Mirrors the pipeline's `runs.slugify`."""
    return _SLUG.sub("-", (value or "").strip().lower()).strip("-") or "output"


# ─────────────────────────── rebuilding the payload ───────────────────────────


def entry_for(record: dict) -> dict:
    """The registry entry this run was drafted against, found by model id.

    By `model` rather than by `engine`: `engine` records the skill name, which is
    prose that has been renamed before, while the model id is what the provider
    is actually called.

    A run naming a model the deployed registry does not carry is a **404 about
    the model**, not a 500. `models.json` ships in the image, so this is what a
    draft written against a newer checkout looks like when it is submitted
    against an older deploy — and the fix is a deploy, which the message should
    not hide behind "internal error".
    """
    entry = registry.by_model_id(record.get("model") or "")
    if entry is None:
        raise NotFoundError(
            f"model {record.get('model')!r} is not in the registry this API "
            "shipped with"
        )
    return entry


def payload_of(record: dict) -> dict:
    """The provider input, rebuilt from the plan and from nothing else.

    `plan.params` plus `plan.prompt`, which is exactly what the plan took apart
    when the draft was written. **Image fields are absent on purpose**: they are
    sends, and they are presigned in by `dispatch` at the last moment.

    Anything else on the plan — `version`, `origin`, `note` — is studio's own
    bookkeeping and is not sent. The filter is an allowlist of the two halves
    rather than a denylist of the rest, so a field added to the plan later cannot
    silently become part of a payload somebody approved as something else.
    """
    plan = record.get("plan") or {}
    params = plan.get("params")
    payload = dict(params) if isinstance(params, dict) else {}
    if plan.get("prompt") is not None:
        payload["prompt"] = plan["prompt"]
    return payload


def bindings_of(send_entries: list[dict], entry: dict) -> dict:
    """The sends, in the shape the provider's input takes.

    Order within a field is the order of the send rows, which is the order the
    model is handed — and which a prompt citing "the first image" depends on.

    **A start or end frame is a SCALAR, not a one-item list**, and that asymmetry
    is the provider's rather than ours: `reference_images` is an array while
    `start_image` is a string. Sending `{"start_image": ["https://…"]}` is a
    `422 Invalid type. Expected: string, given: array` from Replicate — after the
    run has been moved to `pending`, so the draft wedges instead of submitting.
    Which fields are scalar is registry data (`images.start` / `images.end`), the
    same source the send rows read to get their role.
    """
    bindings: dict[str, list[str] | str] = {}
    for send in send_entries:
        field = send.get("field")
        if not field:
            continue
        bindings.setdefault(field, []).append(send["node"])
    images = entry.get("images") or {}
    for name in ("start", "end"):
        field = images.get(name)
        if field and field in bindings:
            bindings[field] = bindings[field][0]
    return bindings


# ───────────────────────────────── preflight ─────────────────────────────────


def _check_image_budget(entry: dict, bindings: dict) -> None:
    """Some models cap TOTAL images, not just the reference list.

    Kling advertises `reference_images` "up to 7" and separately allows a start
    frame alongside them, which reads as 7 + 1 and is not: the cap counts every
    image, so a start frame leaves room for six references. Over the line it
    fails the whole prediction with `Error code 1201: The number of images and
    elements exceeds the limit, max number is 7`.

    Cheap to hit and easy to miss, because the two halves of the rule sit in
    different fields. Registry-driven rather than named per model:
    `start_counts_toward_max_refs`.
    """
    images = entry.get("images") or {}
    cap = images.get("max_refs")
    if not cap or not images.get("start_counts_toward_max_refs"):
        return
    refs = bindings.get(images.get("refs")) or []
    extra = [f for f in (images.get("start"), images.get("end")) if f and bindings.get(f)]
    total = len(refs) + len(extra)
    if total > cap:
        raise schema.SchemaError(
            f"{entry['key']} accepts {cap} images IN TOTAL and the "
            f"{'/'.join(extra)} counts toward that — got {len(refs)} reference "
            f"image(s) plus {len(extra)}, which is {total}."
        )


def _check_payload_rules(entry: dict, payload: dict) -> None:
    """Cross-field rules a per-field schema check cannot express.

    Scoped by the presence of the field, so each rule applies only to the models
    that actually have it. Kling bills per second and rejects a multi-shot
    timeline whose shot durations do not sum to `duration` (E006) — caught here,
    not after billing.
    """
    if payload.get("multi_prompt"):
        raw = payload["multi_prompt"]
        try:
            shots = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            raise schema.SchemaError(f"multi_prompt is not valid JSON: {exc}") from exc
        total = sum(shot.get("duration", 0) for shot in shots)
        if payload.get("duration") is not None and total != payload["duration"]:
            raise schema.SchemaError(
                f"multi_prompt shot durations sum to {total}s but duration is "
                f"{payload['duration']}s — they must be equal (this is E006)."
            )
        cap = registry.field(entry, "video.max_cuts")
        if cap and len(shots) > cap:
            raise schema.SchemaError(
                f"{entry['key']} allows at most {cap} shots; got {len(shots)}."
            )

    cap = registry.field(entry, "prompt.max_chars")
    if cap and len(payload.get("prompt") or "") > cap:
        raise schema.SchemaError(
            f"{entry['key']} caps the prompt at {cap} characters; "
            f"got {len(payload['prompt'])}."
        )


def preflight(entry: dict, payload: dict, bindings: dict) -> None:
    """Documented constraints first, then the live schema.

    **Runs before the transition to `pending`.** A payload the model will refuse
    must leave the run exactly as it was — approved, editable, submittable again
    once fixed — rather than at `pending` with nothing behind it, which is the
    state that reads as "went out and never answered".
    """
    model = entry["model"]
    _check_image_budget(entry, bindings)
    _check_payload_rules(entry, payload)
    schema.check_denied(payload, entry, model)
    props, schemas = schema.fetch(model)
    schema.check(payload, bindings, model, props, schemas)


def prepare(record: dict, send_entries: list[dict]) -> tuple[dict, dict, dict]:
    """Everything needed to send, checked, with nothing written and nothing spent."""
    entry = entry_for(record)
    payload = payload_of(record)
    bindings = bindings_of(send_entries, entry)
    preflight(entry, payload, bindings)
    return entry, payload, bindings


# ──────────────────────────────── dispatching ────────────────────────────────


def callback_url(run_id: str) -> str | None:
    """Where Replicate should call back, or `None` when nothing can reach us.

    **The receiver's URL, not this API's**, and on a developer's machine those
    are not even the same host — see `config.webhook_base_url`. What arrives
    there is enqueued and processed elsewhere; nothing about that is visible from
    here, which is why this function is three lines.

    `None` is supported and means no webhook is asked for at all: the run is
    closed by `POST /api/runs/<id>/reconcile` instead.

    The run id is in the path rather than in a signed token because the callback
    is authenticated by its **signature**, not by the secrecy of its URL. A URL
    that had to be unguessable would be a second credential to store, rotate and
    leak; the run id is already public to anyone holding a link to the run page.
    """
    base = config.webhook_base_url()
    return f"{base}/api/hooks/replicate/{run_id}" if base else None


def dispatch(record: dict, entry: dict, payload: dict, bindings: dict) -> dict:
    """Presign, then create the prediction. **This is the call that bills.**

    Called only after the run has been moved to `pending`, so the gate stands in
    front of the money rather than behind it. A failure here therefore leaves the
    run at `pending` with no prediction id, which is exactly the state that reads
    as "a submission went out and never answered" — deliberately not rewritten to
    `failed`, because a network error on the way *out* cannot distinguish a
    request the provider never saw from one it accepted and answered into a
    dropped socket.
    """
    payload = dict(payload)
    for field, value in bindings.items():
        payload[field] = (
            [presign_node(one) for one in value]
            if isinstance(value, list)
            else presign_node(value)
        )
    if bindings:
        logger.info("Minted presigned URLs for %s on run %s",
                    sorted(bindings), record["id"])
    return replicate.create_prediction(
        entry["model"], payload, webhook=callback_url(record["id"])
    )


def presign_node(node_id: str) -> str:
    """A short-lived GET for one node's bytes. **The only way to Replicate.**

    There is no expiry argument: the TTL is the service's
    (`STUDIO_PRESIGN_TTL_SECONDS`) and a caller does not get to lengthen the
    window in which an identity reference is fetchable by anyone holding the URL.
    """
    record = catalog.node(node_id)
    if not record.get("blob_key"):
        raise ValidationError(
            f"node {node_id} has no bytes behind it and cannot be sent to a model"
        )
    return s3.presign(record["blob_key"])


# ───────────────────────────────── closing ──────────────────────────────────


def _cost(prediction: dict) -> dict | None:
    """What the run cost, as far as the provider will say — which is not a price.

    **Replicate's prediction body carries no money in it.** Billing is per second
    of the model's hardware and the rate lives on the account, not on the
    response, so an `amount` computed here would be a number this service made
    up. What is real is `metrics.predict_time`, and it is what a price would be
    derived from, so it is recorded under the same key the app already reads and
    `amount` stays null.

    `runs list` prints `cost.amount` and already skips a null, so a run shows no
    price rather than a wrong one.
    """
    metrics = prediction.get("metrics") or {}
    predict_time = metrics.get("predict_time")
    if predict_time is None:
        return None
    return {"amount": None, "currency": None, "predict_time": predict_time}


def _output_urls(prediction: dict) -> list[str]:
    """Every file the prediction produced, in order.

    A model returns a bare string for a single output and a list for several, and
    a few return neither — a `succeeded` prediction with no output at all is
    closed as `failed` by the caller, because a run that cost money and produced
    nothing is not a success whatever the provider calls it.
    """
    output = prediction.get("output")
    if isinstance(output, str):
        return [output]
    return [item for item in (output or []) if isinstance(item, str)]


def _store_output(record: dict, folder_id: str, owner, url: str,
                  name: str) -> str:
    """Download one output and put it in the run's `output/` folder.

    **Through the filesystem, never through memory.** See
    `replicate.download` and `s3.put_file`: the bytes are streamed to `/tmp` and
    then sent as a single PUT, which keeps the callback's memory flat whatever
    the model produced and keeps the object's ETag the MD5 of its bytes so
    `set_blob` can record a real checksum.

    The node is created first because its id is what names the key — the same
    ordering every other upload path in this service uses.
    """
    node = catalog.create_node(
        folder_id, name, catalog.KIND_FILE, owner=owner
    )
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"

    handle, staged = tempfile.mkstemp(prefix="studio-output-")
    os.close(handle)
    try:
        replicate.download(url, staged, max_bytes=config.max_output_bytes())
        s3.put_file(node["blob_key"], staged, content_type)
    finally:
        # A partial download is not left behind for the next invocation to
        # inherit: `/tmp` survives a warm start, so an aborted 200 MB clip would
        # otherwise eat the ephemeral disk one failure at a time.
        if os.path.exists(staged):
            os.remove(staged)

    metadata = s3.head(node["blob_key"])
    catalog.set_blob(
        node["node_id"],
        node["blob_key"],
        size=metadata.get("ContentLength", 0),
        content_type=metadata.get("ContentType") or content_type,
        checksum=s3.content_hash(metadata),
    )
    logger.info("Stored output %s for run %s", node["node_id"], record["id"])
    return node["node_id"]


def _output_names(record: dict, urls: list[str]) -> list[str]:
    """What each downloaded file is called.

    **A filename, not an identity.** This used to be the run's slug, which named
    the run, named its folder and named its outputs all at once; the run and its
    folder are named by id now and what survives here is the only part that was
    ever worth having.

    The stem comes off the run's `output_name`, recorded when the draft was
    written, and the extension off the output URL — a model may return a `.webp`
    where its registry entry says `.jpg`, and the file should say what it is.
    """
    kind = record.get("kind") or "image"
    stem = slugify(record.get("output_name") or DEFAULT_NAME.get(kind, kind))
    names = []
    for index, url in enumerate(urls, start=1):
        ext = os.path.splitext(url.split("?")[0])[1] or DEFAULT_EXT.get(kind, "")
        suffix = "" if len(urls) == 1 else f"-{index}"
        names.append(f"{stem}{suffix}{ext}")
    return names


def _response_document(record: dict, prediction: dict) -> str | None:
    """The provider's response, stored verbatim as a node. Returns its id.

    The half of the run this service is forbidden to have an opinion about: it is
    encoded and written, and nothing here reads a key inside it — except the
    handful `close_from_prediction` reads off the *parsed* body it was handed,
    which is a different thing from decoding the stored document later.

    Oversized responses are dropped rather than truncated. A `logs` field can run
    to megabytes on a failed video, and half a JSON document is worse than none:
    it looks readable and is not.
    """
    text = json.dumps(prediction, indent=2, sort_keys=True, default=str)
    if len(text.encode()) > config.max_text_bytes():
        logger.warning("Response for run %s is too large to store (%d bytes)",
                       record["id"], len(text.encode()))
        return None

    folder = record["folder"]
    node = catalog.create_node(
        folder, "response.json", catalog.KIND_FILE,
        owner=catalog.blob_owner_for(folder),
    )
    body = text.encode()
    s3.put_text(node["blob_key"], body, "text/plain; charset=utf-8")
    catalog.set_blob(node["node_id"], node["blob_key"], size=len(body),
                     content_type="text/plain; charset=utf-8")
    return node["node_id"]


def close_from_prediction(record: dict, prediction: dict) -> dict:
    """Record what a prediction did. **The one closing implementation.**

    Reached from the webhook in prod and from `reconcile` in local development,
    and it must not matter which — a run closed by a poll and a run closed by a
    callback are the same row.

    **Idempotent, because a webhook is at-least-once delivery.** A run already in
    a terminal state is returned untouched: a duplicate callback must not upload
    the output a second time, which would double the run's `outputs` list and
    leave two copies of a video in the bucket. That is normal traffic rather than
    an incident, so it is not logged as one.

    A prediction still in flight is likewise a no-op. The webhook filter asks for
    `completed` only, so this should not happen; a reconcile against a running
    prediction reaches it every time, and the honest answer there is "nothing has
    changed yet".
    """
    if record.get("status") in catalog.TERMINAL_RUN_STATUSES:
        logger.info("Run %s is already %s; ignoring a repeat report",
                    record["id"], record["status"])
        return record

    provider_status = (prediction.get("status") or "").lower()
    status = PROVIDER_STATUS.get(provider_status, "failed")
    if status == "running":
        return record

    urls = _output_urls(prediction) if status == "succeeded" else []
    error = prediction.get("error")
    if status == "succeeded" and not urls:
        # Paid for, and produced nothing. Calling that a success would put an
        # empty run in the grid with a thumbnail that never loads.
        status, error = "failed", "the prediction succeeded but returned no output"

    assignments: dict = {
        "status": status,
        "completed": catalog.now(),
        "error": None if error is None else str(error)[:2000],
        "prediction_id": prediction.get("id") or record.get("prediction_id"),
    }
    cost = _cost(prediction)
    if cost is not None:
        assignments["cost"] = cost

    listing: dict = {"status": status}
    if urls:
        folder = layout.folder_under(record["folder"], layout.OUTPUT_FOLDER)
        owner = catalog.blob_owner_for(folder["node_id"])
        outputs = [
            _store_output(record, folder["node_id"], owner, url, name)
            for url, name in zip(urls, _output_names(record, urls))
        ]
        assignments["outputs"] = outputs
        # The first output becomes the listing row's thumbnail, which is what
        # lets the runs grid draw without reading an envelope per tile.
        if not record.get("outputs"):
            listing["thumb"] = outputs[0]

    response_node = _response_document(record, prediction)
    if response_node:
        assignments["payload"] = {
            **(record.get("payload") or {}), "response": response_node
        }

    updated = catalog.update_project_entity(
        catalog.ENTITY_RUN, record, assignments, listing
    )
    logger.info("Closed run %s as %s", record["id"], status)
    return updated


def reconcile(record: dict) -> dict:
    """Ask the provider what happened, and close the run on the answer.

    **The answer to "what happens to a prediction whose webhook never
    arrives".** A callback can be lost — a deploy mid-flight, a signature that
    fails verification, a bug in this service — and without this a run sits at
    `running` with a prediction id forever: legible, and never resolved.

    It is also how local development works at all, because Replicate cannot call
    `localhost`. That the two share one route is not a coincidence worth
    apologising for: "the callback did not arrive" and "there was never going to
    be a callback" are the same situation from this side.

    A run with no prediction id has nothing to ask about — it never reached the
    provider — so it is a conflict rather than a 404: the fix is to submit it,
    and saying so is more useful than reporting a missing prediction.
    """
    prediction_id = record.get("prediction_id")
    if not prediction_id:
        raise ConflictError(
            f"run {record['id']} is {record.get('status')} and carries no "
            "prediction id — nothing was ever sent to the provider"
        )
    return close_from_prediction(record, replicate.get_prediction(prediction_id))
