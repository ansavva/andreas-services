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

**The state machine stays in `routes/runs.py`.** Whether a run may be sent is
a property of the run row, not of the provider, and the route that owns the
state machine is the one that owns the transition. This module is handed a
record that route has already accepted; it does not re-check that and it must
not.

**The payload render stays in the CLI.** Hard rule #2 is about a person reading
two documents and deciding, and nothing here is in front of a person. What this
module guarantees is narrower and mechanical: it rebuilds the payload from the
**plan and from nothing else**, so what is sent is what was read.

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
import os
import re
import tempfile
from collections.abc import Callable

from studio_core import config
from studio_core.clients import fal, openrouter, replicate, runpod, runpod_pods
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.media import faststart, mime
from studio_core.services import catalog, layout, registry, schema

logger = logging.getLogger(__name__)

#: The providers' vocabularies on the left, studio's on the right. Two words
#: differ from Replicate's and both differences are deliberate: studio has no
#: `starting`/`processing` split (a run that has gone out is `running`, and a
#: second word for the first two seconds of it would be a state nothing acts
#: on), and `canceled` is spelled `cancelled` here because
#: `catalog.RUN_STATUSES` has always spelled it that way. Runpod's and fal's
#: words are upper-case on the wire and lower-cased before the lookup; fal's
#: queue words are Runpod's (and mean the same), its terminal words are its
#: own, and nothing collides, so one map serves all four. Anything
#: unrecognised is `failed` rather than passed through — an unmapped provider
#: word reaching `PATCH /api/runs/<id>` is a 400 on the one call that has to
#: succeed, because it is the only report a paid prediction will ever make.
PROVIDER_STATUS = {
    # Replicate
    "starting": "running",
    "processing": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "canceled": "cancelled",
    # Runpod
    "in_queue": "running",
    "in_progress": "running",
    "completed": "succeeded",
    "cancelled": "cancelled",
    "timed_out": "failed",
    # fal — `in_queue` / `in_progress` / `completed` above serve its status
    # route too; these two are its webhook's, and what `fal.normalise` writes
    # once the result has been read.
    "ok": "succeeded",
    "error": "failed",
    # OpenRouter — `in_progress` / `completed` / `failed` / `cancelled` above
    # serve it too; these two are its own. `pending` is the queue's word for
    # a job it has taken, which is `running` from this side, and `expired`
    # is a job OpenRouter gave up on before it produced anything.
    "pending": "running",
    "expired": "failed",
}

#: The client behind each provider name. All five answer to the same six
#: functions — `create_prediction`, `get_prediction`, `normalise`, `download`,
#: `output_urls`, `cost` — and an `OutputGone`; `clients/runpod.py` says why,
#: `clients/fal.py` says why `normalise` joined the list, and
#: `clients/runpod_pods.py` is the one that rents a machine instead.
CLIENTS = {registry.REPLICATE: replicate, registry.RUNPOD: runpod, registry.FAL: fal,
           registry.OPENROUTER: openrouter, registry.RUNPOD_POD: runpod_pods}


def provider_of(record: dict) -> str:
    """Which provider a run went to: what `submit` recorded, else inferred.

    Recorded on the run at submit time so that closing it — from a callback,
    from `reconcile`, months later — does not depend on the registry still
    carrying the model. A run written before the field existed has no
    `provider`, and every one of those went to Replicate unless its model id
    says otherwise.
    """
    recorded = record.get("provider")
    if recorded:
        return recorded
    model = record.get("model") or ""
    if runpod.is_model(model):
        return registry.RUNPOD
    if fal.is_model(model):
        return registry.FAL
    if openrouter.is_model(model):
        return registry.OPENROUTER
    return registry.REPLICATE


def client_for(provider: str):
    """The client module for a provider name. Unknown is a 500, not a guess."""
    try:
        return CLIENTS[provider]
    except KeyError:
        raise registry.RegistryError(f"no client for provider {provider!r}") from None

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
    silently become part of a payload somebody read as something else.
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
    for field in _scalar_fields(entry):
        if field in bindings:
            bindings[field] = bindings[field][0]
    return bindings


def _scalar_fields(entry: dict) -> set[str]:
    """The inputs that take ONE object: the frames, and the clip.

    `images.start` / `images.end` are strings on every model that has them,
    and `clips.source` — a motion reference, an edit source — is a string on
    every model that has one. Read here once, so `bindings_of` and
    `_check_scalar_fields` cannot disagree about which fields collapse.
    """
    images = entry.get("images") or {}
    clips = entry.get("clips") or {}
    return {images.get("start"), images.get("end"), clips.get("source")} - {None}


#: What a send with no role at all is taken to be inside an element. Every
#: send written by the CLI or the app carries one; a run reconstructed from
#: `bindings` alone does not (`routes/runs.sends_from_bindings` says why), and
#: a reference image is what the elements field is mostly made of.
DEFAULT_ELEMENT_ROLE = "reference"

#: The key a send with no subject behind it is grouped under. One bucket, not
#: one per node: three images a person dropped in from a folder are three
#: views of one thing far more often than they are three separate subjects,
#: and a prompt citing `@Element1` can say which.
LOOSE = "#loose"


def _subject_of(send: dict) -> str:
    """Which SUBJECT a send belongs to — the key its element is grouped under.

    **This is the whole trick, and it is not new machinery.** `catalog.source_of`
    already answers "why is this file being sent", derived from where the file
    sits in the tree, and for a character's reference photograph the answer is
    that character's id. An element is a subject. So grouping the sends by the
    provenance the run already records gives exactly the elements a person
    means — one per character, its images together, its voice with it — with no
    second place to say which pictures belong to whom and no way for the two to
    disagree.

    A file that belongs to nobody in particular (`kind: object`, an input-pool
    still, a run's own output) groups under `LOOSE`.
    """
    source = send.get("source") or {}
    return source.get("character") or source.get("location") or LOOSE


def element_groups(block: dict, send_entries: list[dict]) -> list[dict]:
    """The sends bound to the elements field, gathered into one object each.

    Ordered by first appearance, because `@Element1` is positional and bind
    order is the order a person put them on the bar.

    Within one element: the send that says `frontal` is the main view, and
    otherwise the FIRST image is — Kling wants one and would otherwise get an
    element that is all angles and no face. The rest are its other views, one
    clip at most, one voice at most.
    """
    field = block["field"]
    order: list[str] = []
    groups: dict[str, dict] = {}
    for send in send_entries:
        if send.get("field") != field:
            continue
        subject = _subject_of(send)
        if subject not in groups:
            order.append(subject)
            groups[subject] = {"subject": subject, "frontal": None, "refs": [],
                               "clip": None, "voice": None, "claimed": False}
        group = groups[subject]
        role = send.get("role") or DEFAULT_ELEMENT_ROLE
        node = send["node"]
        if role == "voice":
            group["voice"] = node
        elif role == "clip":
            group["clip"] = node
        elif role == "frontal":
            # An explicit frontal wins over the one picked for having been
            # first, and the one it displaces keeps its place at the head of
            # the other views rather than being dropped.
            if group["frontal"] is not None and not group["claimed"]:
                group["refs"].insert(0, group["frontal"])
            group["frontal"] = node
            group["claimed"] = True
        elif group["frontal"] is None:
            group["frontal"] = node
        else:
            group["refs"].append(node)
    return [groups[subject] for subject in order]


# ───────────────────────────────── preflight ─────────────────────────────────


def _check_image_budget(entry: dict, bindings: dict) -> None:
    """The model's cap on reference images, enforced while the run is a draft.

    **`max_refs` is the ceiling on the reference list, on every model that
    has one.** It used to be checked only on the models where a frame counts
    toward it, so a plain over-long list went out unchecked: twelve references
    to a model that takes ten reached fal, which answered `422 List should
    have at most 10 items` — after `pending`, as a run that read "Unexpected
    status code: 422" with nothing a person could act on. The SPA's tile and
    the CLI's `--character` both stop at the cap, but a picker held open, a
    model switched under an attached list, or a re-run seeded from an older
    run all get past them, and this is the one check nothing gets past.

    **Some models cap TOTAL images, not just the reference list.** Kling
    advertises `reference_images` "up to 7" and separately allows a start
    frame alongside them, which reads as 7 + 1 and is not: the cap counts
    every image, so a start frame leaves room for six references. Over the
    line it fails the whole prediction with `Error code 1201: The number of
    images and elements exceeds the limit, max number is 7`. Registry-driven
    rather than named per model: `start_counts_toward_max_refs`.
    """
    images = entry.get("images") or {}
    cap = images.get("max_refs")
    if not cap:
        return
    refs = bindings.get(images.get("refs")) or []
    if not isinstance(refs, list):
        refs = [refs]
    if not images.get("start_counts_toward_max_refs"):
        if len(refs) > cap:
            raise schema.SchemaError(
                f"{entry['key']} takes at most {cap} reference images — got "
                f"{len(refs)}. Take {len(refs) - cap} off and send again."
            )
        return
    extra = [f for f in (images.get("start"), images.get("end")) if f and bindings.get(f)]
    total = len(refs) + len(extra)
    if total > cap:
        raise schema.SchemaError(
            f"{entry['key']} accepts {cap} images IN TOTAL and the "
            f"{'/'.join(extra)} counts toward that — got {len(refs)} reference "
            f"image(s) plus {len(extra)}, which is {total}."
        )


#: fal's own sentence, from the Custom Elements section and the Known
#: Limitations of `fal-ai/kling-video/v3/pro/image-to-video`. Quoted rather
#: than paraphrased so a person reading the refusal can find it on the page.
VOICE_NEEDS_VIDEO = ("Voice binding is only supported for video elements, "
                     "not image elements.")
#: What to do about it — the two ways out, the first of which is the one
#: studio uses for now.
VOICE_NEEDS_VIDEO_ADVICE = (
    "Take the voice off and leave `generate_audio: true` on, so Kling invents "
    "the voice — or bind a short video of that subject in the same run, so its "
    "element carries a `video_url`. One element per request can carry a "
    "video, so one voice at most."
)
#: fal's own sentence, from a 422 on `fal-ai/kling-video/v3/pro/image-to-video`
#: (2026-09-23, `body.elements.2`). The OpenAPI document says nothing of it:
#: an IMAGE element needs a frontal view AND at least one other, and a lone
#: picture is refused. Quoted so the refusal can be matched to what fal says.
ELEMENT_NEEDS_TWO_VIEWS = ("Either frontal_image_url and reference_image_urls "
                           "or video_url must be provided.")


def _check_elements(entry: dict, send_entries: list[dict], payload: dict) -> None:
    """The rules an ELEMENT model has and a per-field schema cannot express.

    Every one of these fails at the provider otherwise, after `pending`, with
    a message about a JSON path rather than about the run:

    * **More subjects than the model takes.** Four is Kling's ceiling, and
      the fifth is `Error code 1201`.
    * **More views of one subject than it takes.** The element's own
      `reference_image_urls` is documented 1–3 alongside the frontal.
    * **Fewer views of one subject than it takes.** The same 1–3 has a floor
      the schema does not state and the server enforces: an image element
      with a frontal and no reference is refused, "Either frontal_image_url
      and reference_image_urls or video_url must be provided." So an element
      is `min_images_each` (2) to `max_images_each` (4) images — or a clip,
      which carries the subject without any.
    * **Two clips.** "A request can only have one element with a video",
      says the schema, and nothing enforces it until the request is made.
      Because a voice binds only to an element with a video (next bullet),
      this is also the cap on voices: **at most one bound voice per
      request.**
    * **A voice on an image element.** fal's page for
      `fal-ai/kling-video/v3/pro/image-to-video`, under Custom Elements and
      again under Known Limitations: "Voice binding is only supported for
      video elements, not image elements. Attempting voice binding with an
      image element returns an error." So a voice is refused unless its
      element carries a clip (`video_url`) — and a voice alone, with neither
      a picture nor a clip, is refused for the same reason. The path studio
      takes for now is the other one: no bound voice, `generate_audio: true`,
      and Kling invents the voices.
    * **A voice with the sound turned off.** This one costs real money for
      nothing: `generate_audio: false` produces a silent clip and the voice
      tier is billed anyway, which is the worst kind of mistake to leave to
      the provider — it does not fail, it just silently wastes the spend.
    * **A voice on a file the model will not read.** Checked against the
      entry's `audio.accepts_ext` rather than against what the library calls
      audio; see `registry.voice_accepts_ext`.
    """
    block = registry.elements(entry)
    voices = [send for send in send_entries if send.get("role") == "voice"]
    if block is None:
        if voices:
            raise ValidationError(
                f"{entry['key']} has no voice input — it takes no elements, so "
                "there is nothing for a voice to be bound to. "
                "fal-kling-v3-i2v and fal-kling-o3-r2v do."
            )
        return

    groups = element_groups(block, send_entries)
    cap = block.get("max")
    if cap and len(groups) > cap:
        raise schema.SchemaError(
            f"{entry['key']} takes at most {cap} elements and this run binds "
            f"{len(groups)} — one per character or location the images came "
            f"from. Bind fewer subjects."
        )
    each = block.get("max_images_each")
    floor = block.get("min_images_each")
    for index, group in enumerate(groups, start=1):
        images = len(group["refs"]) + (1 if group["frontal"] else 0)
        if each and images > each:
            raise schema.SchemaError(
                f"{entry['key']}: @Element{index} carries {images} images and "
                f"an element takes at most {each} — a frontal view and its "
                f"other angles."
            )
        if group["voice"] and not group["frontal"] and not group["clip"]:
            raise ValidationError(
                f"{entry['key']}: @Element{index} is a voice with nobody to "
                "speak it — no picture and no video of the subject. "
                + VOICE_NEEDS_VIDEO_ADVICE
            )
        if group["voice"] and not group["clip"]:
            raise ValidationError(
                f"{entry['key']}: @Element{index} binds a voice to an image "
                f"element, and fal refuses that: \"{VOICE_NEEDS_VIDEO}\" "
                + VOICE_NEEDS_VIDEO_ADVICE
            )
        # After the voice rules, so a voice on a lone picture is told about
        # the voice — the rule that has a way out studio takes for now.
        if floor and not group["clip"] and images < floor:
            raise ValidationError(
                f"{entry['key']}: @Element{index} carries {images} image(s) "
                f"and an image element takes at least {floor} — fal refuses "
                f"fewer: \"{ELEMENT_NEEDS_TWO_VIEWS}\" Bind a second view of "
                f"that subject. Two stills of one room group as one element "
                f"only when both sit in that location's tree, so copy the "
                f"second into the location's folder."
            )
    clips = [group for group in groups if group["clip"]]
    if len(clips) > 1:
        raise schema.SchemaError(
            f"{entry['key']} allows ONE element with a video and this run binds "
            f"{len(clips)}."
        )

    if not voices:
        return
    if payload.get("generate_audio") is False:
        raise ValidationError(
            f"{entry['key']}: a bound voice with `generate_audio: false` is a "
            "silent clip billed at the voice rate. Turn the audio on, or take "
            "the voice off."
        )
    allowed = registry.voice_accepts_ext(entry)
    if allowed:
        bad = [send["node"] for send in voices
               if not (catalog.node(send["node"]).get("name") or "")
               .lower().endswith(tuple(allowed))]
        if bad:
            raise schema.SchemaError(
                f"{entry['key']} clones a voice from {sorted(allowed)}; "
                f"{bad} is not one of those."
            )


#: fal says it on the `prompt` field of both its Kling entries, in its own
#: words; the input schema's `required` array is `["start_image_url"]` alone,
#: so a payload with no `prompt` is a complete one there. Replicate's proxy for
#: the same model family requires `prompt`, which is why this is a property of
#: the ENTRY — `video.shots_replace_prompt` — and not a rule about Kling.
EXCLUSIVE = "Either prompt or multi_prompt must be provided, but not both"


def _check_payload_rules(entry: dict, payload: dict) -> None:
    """Cross-field rules a per-field schema check cannot express.

    Scoped by the presence of the field, so each rule applies only to the models
    that actually have it. Kling bills per second and rejects a multi-shot
    timeline whose shot durations do not sum to `duration` (E006) — caught here,
    not after billing.

    **A payload carrying both text fields is refused, not repaired.** The CLI
    folds the globals into the first beat while it is building the payload, so
    the document a person read under hard rule #2 is the one that goes out;
    doing the same rewrite here, at submit, would change a payload after it was
    read and approved. See `submit.fold_timeline_globals` in the pipeline.
    """
    shots = []
    if payload.get("multi_prompt"):
        raw = payload["multi_prompt"]
        try:
            shots = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as exc:
            raise schema.SchemaError(f"multi_prompt is not valid JSON: {exc}") from exc
        # **A shot's duration is a string on fal and an integer on Replicate**,
        # and the same registry field `multi_prompt` is on both. Summed as
        # written, `"3" + "2"` is `TypeError` inside a preflight — a 500 about
        # a payload whose only fault was being spelled the way its own
        # provider spells it.
        want = payload.get("duration")
        try:
            total = sum(int(shot.get("duration", 0)) for shot in shots)
            want = None if want is None else int(want)
        except (TypeError, ValueError) as exc:
            raise schema.SchemaError(
                f"multi_prompt needs a number of seconds per shot: {exc}"
            ) from exc
        if want is not None and total != want:
            raise schema.SchemaError(
                f"multi_prompt shot durations sum to {total}s but duration is "
                f"{payload['duration']}s — they must be equal (this is E006)."
            )
        cap = registry.field(entry, "video.max_cuts")
        if cap and len(shots) > cap:
            raise schema.SchemaError(
                f"{entry['key']} allows at most {cap} shots; got {len(shots)}."
            )

    exclusive = registry.field(entry, "video.shots_replace_prompt")
    if shots and exclusive and payload.get("prompt"):
        raise schema.SchemaError(
            f"{entry['key']} takes a prompt OR a timeline, never both — its "
            f'schema says "{EXCLUSIVE}". Fold the globals into the first beat '
            f"of `multi_prompt` and drop `prompt`."
        )

    cap = registry.field(entry, "prompt.max_chars")
    if cap and len(payload.get("prompt") or "") > cap:
        raise schema.SchemaError(
            f"{entry['key']} caps the prompt at {cap} characters; "
            f"got {len(payload['prompt'])}."
        )
    # **Each beat has its own cap, and on fal it is not the prompt's.** fal's
    # OpenAPI caps `prompt` at 2500 and states no per-beat length; its server
    # answers "Prompt must not exceed 512 characters." on `multi_prompt.N.prompt`
    # (a 422 on 2026-09-23). `video.shot_max_chars` carries that where it is
    # known. Where it is not and the timeline replaced the prompt, the prompt's
    # own ceiling is the best word there is. Beat one is the one that trips it,
    # because the globals were folded into it. Not on Replicate, which declares
    # neither and sends the beats BESIDE a prompt that has its own cap.
    shot_cap = registry.field(entry, "video.shot_max_chars") or (
        cap if exclusive else None)
    if shot_cap:
        for index, shot in enumerate(shots, start=1):
            text = shot.get("prompt") or "" if isinstance(shot, dict) else ""
            if len(text) <= shot_cap:
                continue
            raise schema.SchemaError(
                f"{entry['key']} caps each beat at {shot_cap} characters and "
                f"shot {index} carries {len(text)}."
                + (" The globals fold into it, because a timeline is the only"
                   " text this model takes — cut them to one identity"
                   " sentence, and move what is really per-beat into the beat"
                   " it belongs to."
                   if index == 1 and exclusive else " Trim the beat.")
            )


def _check_scalar_fields(entry: dict, send_entries: list[dict]) -> None:
    """A scalar image field named by more than one send is not a payload.

    **`bindings_of` keeps the first and drops the rest, silently**, because a
    start frame is a string and a list would be a 422 from the provider. That
    collapse is right for one send and a lie for several: a run bound a start
    frame and five of a character's reference photographs, every one of them
    naming `image` because the editor copied the field off the row above, and
    the payload went out with one image and no `reference_images` at all. The
    run looked correct on screen — six images, six rows — and the five that
    mattered were discarded between the page and the provider.

    Refused rather than repaired: which field a reference belongs in is registry
    data the caller can read, and quietly moving somebody's images to a
    different input is the same class of silent decision.
    """
    images = entry.get("images") or {}
    scalars = _scalar_fields(entry)
    counts: dict[str, int] = {}
    for send in send_entries:
        field = send.get("field")
        if field in scalars:
            counts[field] = counts.get(field, 0) + 1
    over = sorted(f for f, n in counts.items() if n > 1)
    if not over:
        return
    refs = images.get("refs")
    raise ValidationError(
        f"{over[0]!r} takes ONE image and {counts[over[0]]} sends name it, so "
        f"{counts[over[0]] - 1} would be dropped without a word."
        + (f" Reference images go in {refs!r}." if refs
           else " This model takes no reference images.")
    )


def _check_exclusive_images(entry: dict, bindings: dict) -> None:
    """Fields the provider refuses to receive together.

    **The registry has said this for every model since it was written and
    nothing read it.** `start_excludes_refs` and `end_excludes_refs` existed as
    data with no enforcement anywhere, so a Veo run went out carrying both a
    start frame and reference images and came back
    `{'code': 3, 'message': 'Image and reference images cannot be both set.'}` —
    a constraint the entry could have stated and the preflight could have caught
    for nothing, after the run had already been submitted.

    Refused here rather than at the provider because a submission that fails
    there has already left `pending` behind it, and because the provider is the
    expensive place to learn something the registry knows.
    """
    images = entry.get("images") or {}
    refs = images.get("refs")
    if not refs or refs not in bindings:
        return
    for name in ("start", "end"):
        field = images.get(name)
        if images.get(f"{name}_excludes_refs") and field and field in bindings:
            raise ValidationError(
                f"{entry['model']} will not take {field!r} and {refs!r} together — "
                f"it refuses the request with both set. Send one or the other: "
                f"the {name} frame, or the reference images.")


def preflight(entry: dict, payload: dict, bindings: dict,
              send_entries: list[dict] | None = None) -> None:
    """Documented constraints first, then the live schema.

    **Runs before the transition to `pending`.** A payload the model will refuse
    must leave the run exactly as it was — a draft, editable, submittable again
    once fixed — rather than at `pending` with nothing behind it, which is the
    state that reads as "went out and never answered".
    """
    model = entry["model"]
    if send_entries is not None:
        _check_scalar_fields(entry, send_entries)
        _check_elements(entry, send_entries, payload)
    _check_exclusive_images(entry, bindings)
    # **Not on an element model.** `max_refs` counts entries in a flat list of
    # reference images, and on one of these the same field holds subjects —
    # with a voice sample among them, which is not an image at all. Counting
    # them together would refuse a run with two characters and four views
    # each, which is well inside what Kling takes. `_check_elements` is the
    # cap that applies, and it counts both of the things there are to count.
    if registry.elements(entry) is None:
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
    preflight(entry, payload, bindings, send_entries)
    if registry.provider_of(entry) == registry.RUNPOD_POD:
        # A trainer's own rules — the knobs, the dataset size, one character
        # — checked here so a refusal leaves a draft, not a `pending` run
        # with no pod behind it.
        from studio_core.services import training
        training.preflight(record, entry, payload, bindings)
    return entry, payload, bindings


# ──────────────────────────────── dispatching ────────────────────────────────


def callback_url(run_id: str, provider: str = registry.REPLICATE) -> str | None:
    """Where the provider should call back, or `None` when nothing can reach us.

    **The receiver's URL, not this API's**, and on a developer's machine those
    are not even the same host — see `config.webhook_base_url`. What arrives
    there is enqueued and processed elsewhere; nothing about that is visible from
    here, which is why this function is three lines.

    `None` is supported and means no webhook is asked for at all: the run is
    closed by `POST /api/runs/<id>/reconcile` instead.

    The run id is in the path rather than in a signed token because a Replicate
    callback is authenticated by its **signature**, not by the secrecy of its
    URL. A URL that had to be unguessable would be a second credential to store,
    rotate and leak; the run id is already public to anyone holding a link to
    the run page.

    **Runpod signs nothing, so its URL carries the proof instead**: `?sig=` is an
    HMAC of the run id under the API key this service already holds, and
    `services/callbacks.py` recomputes it. Not a second credential — the key is
    the one that paid for the job — and not secrecy of the URL either: a reader
    who has the URL has a signature for one run id and nothing else.

    **fal signs its callbacks** (ED25519, four headers), so its URL is bare
    like Replicate's; `clients/fal.py` has the check.

    **OpenRouter signs only when a workspace secret is configured**, which is
    a second thing to provision, so its URL carries Runpod's kind of proof
    under its own key; `clients/openrouter.py` says so.
    """
    base = config.webhook_base_url()
    if not base:
        return None
    url = f"{base}/api/hooks/{provider}/{run_id}"
    if provider in (registry.RUNPOD, registry.RUNPOD_POD):
        url += f"?sig={runpod.callback_signature(run_id)}"
    elif provider == registry.OPENROUTER:
        url += f"?sig={openrouter.callback_signature(run_id)}"
    return url


def voice_id_for(entry: dict, node_id: str, *, expires_in: int | None = None) -> str:
    """The provider's id for this voice sample, minted once and remembered.

    **Not a generation, and not billed as one.** Registering a sample is a
    separate endpoint (`registry.voice_endpoint`) that answers a string; the
    run that cites the string is what bills. It happens here, inside
    `dispatch`, because this is the moment the file has a URL a provider can
    fetch — hard rule #3 again, with a voice in place of a picture.

    The id is cached on the node, so a character registered for one clip is
    the SAME voice in the next one. That is not an optimisation: a fresh id
    per run would mean a fresh voice per run, and the entire point of binding
    one is that `@Element1` sounds the same across every scene it appears in.
    """
    endpoint = registry.voice_endpoint(entry)
    if not endpoint:
        raise registry.RegistryError(
            f"{entry['key']} binds a voice but names no `audio.create` endpoint")
    record = catalog.node(node_id)
    cached = catalog.voice_id(record, endpoint)
    if cached:
        logger.info("Reusing voice %s for %s", cached, node_id)
        return cached
    client = client_for(registry.provider_of(entry))
    if not hasattr(client, "create_voice"):
        raise registry.RegistryError(
            f"{registry.provider_of(entry)} has no way to register a voice")
    minted = client.create_voice(endpoint, presign_node(node_id, expires_in=expires_in))
    catalog.set_voice_id(node_id, endpoint, minted)
    return minted


def _element_objects(block: dict, send_entries: list[dict], *,
                     place: Callable[[str], str],
                     voice: Callable[[str], str]) -> list[dict]:
    """The `elements` array, with `place` and `voice` deciding what each slot holds.

    **One assembly for both callers**, so the preview a person reads before
    sending (hard rule #2) has the shape the provider is actually sent:
    `dispatch` passes a presigner and the voice registrar, the preview passes
    functions that answer node ids. Two copies of this loop would be the way
    the preview came to show a flat list while the wire carried objects.

    One object per subject, in bind order, so `@Element1` in the prompt is the
    first thing the run was given. An empty group is dropped rather than sent
    as `{}`: the provider reads an element with nothing in it as a validation
    error, and it can only arise from a send whose role the model has no slot
    for.
    """
    out: list[dict] = []
    for group in element_groups(block, send_entries):
        one: dict = {}
        if group["frontal"]:
            one[block["frontal"]] = place(group["frontal"])
        if group["refs"]:
            one[block["refs"]] = [place(node) for node in group["refs"]]
        if group["clip"] and block.get("clip"):
            one[block["clip"]] = place(group["clip"])
        if group["voice"] and block.get("voice"):
            one[block["voice"]] = voice(group["voice"])
        if one:
            out.append(one)
    return out


def elements_payload(entry: dict, block: dict, send_entries: list[dict],
                     *, expires_in: int | None = None) -> list[dict]:
    """The `elements` array, presigned and with every bound voice registered."""
    return _element_objects(
        block, send_entries,
        place=lambda node: presign_node(node, expires_in=expires_in),
        voice=lambda node: voice_id_for(entry, node, expires_in=expires_in),
    )


#: What the preview shows in a voice slot the provider has not named yet.
#: The id is minted at submit (`voice_id_for`), and minting it to draw a page
#: would be a call to the provider made by reading.
VOICE_PENDING = "<voice id minted at submit>"


def elements_preview(entry: dict, block: dict, send_entries: list[dict]) -> list[dict]:
    """The `elements` array as it WILL go out, with node ids where URLs will be.

    Same shape as `elements_payload`, built by the same loop. **Nothing is
    minted**: an image slot holds its node id (presigning to draw a preview
    would put live credentials in a page that is only being read), and a voice
    slot holds the id already cached on the node for this model's
    `audio.create` endpoint, or `VOICE_PENDING` — never `voice_id_for`, which
    calls the provider.
    """
    endpoint = registry.voice_endpoint(entry)

    def voice(node: str) -> str:
        cached = catalog.voice_id(catalog.node(node), endpoint) if endpoint else None
        return cached or VOICE_PENDING

    return _element_objects(block, send_entries, place=lambda node: node, voice=voice)


def dispatch(record: dict, entry: dict, payload: dict, bindings: dict,
             send_entries: list[dict] | None = None) -> dict:
    """Presign, then create the prediction. **This is the call that bills.**

    Called only after the run has been moved to `pending`, so the gate stands in
    front of the money rather than behind it. **Anything raised from here hands
    the run back as a draft**, with the reason in its `error` — `submit_run`
    owns that transition and says why. What this function owes it is that a
    raise leaves nothing behind: a hosted provider has no side effect before
    `create_prediction`, and `training.dispatch` takes back its nodes, its
    manifest and its pod before re-raising.

    **One exception, and it is deliberate.** Registering a voice
    (`voice_id_for`) happens before the prediction and is remembered on the
    node, so a dispatch that fails afterwards leaves a voice id behind. That
    is the point of caching it: the sample has not changed, the id is still
    true, and the next attempt reuses it instead of paying the round trip and
    handing the character a different voice.
    """
    provider = registry.provider_of(entry)
    if provider == registry.RUNPOD_POD:
        # A machine, not a model: the payload becomes a job manifest and the
        # "prediction" is a rented pod. Everything that follows here is about
        # presigning images INTO a request body, which a pod does not take.
        from studio_core.services import training
        return training.dispatch(record, entry, payload, bindings,
                                 webhook=callback_url(record["id"], provider))

    payload = dict(payload)
    # **A LoRA send goes out as `{path, scale}`, and the scale never goes out
    # by name.** `lora_scale` is a plan param so a person sets one number in
    # the sheet or with `--extra`; the endpoint has no such field, so it is
    # taken out here and written into every object. Popped even when no LoRA
    # is bound, or an unknown field would reach the provider.
    loras = registry.lora_fields(entry)
    scale_param = registry.lora_scale_param(entry)
    scale = payload.pop(scale_param, None) if scale_param else None
    if scale is None:
        scale = 1.0
    # A worker of ours queues: one worker, and a clip ahead of this one can
    # run half an hour, so its sends live as long as its output grant. A
    # public endpoint starts within seconds and gets the service's TTL. The
    # first proof run against `wan-2.2-i2v-studio` queued 16 minutes behind
    # the job before it and fetched its still one minute after the 15-minute
    # URL had expired — a 403, a failed run, and a paid render of nothing.
    grant = registry.output_grant(entry)
    ttl = OUTPUT_GRANT_TTL if grant else None
    # **An element model's reference field is not a list of URLs**, so it is
    # built rather than presigned in place: one object per subject, each with
    # its own views and, where one is bound, its own registered voice. It
    # needs the ROLE and the PROVENANCE of each send, which `bindings` threw
    # away — hence `send_entries` reaching this far down.
    block = registry.elements(entry)
    element_field = block["field"] if block else None
    for field, value in bindings.items():
        if field == element_field:
            payload[field] = elements_payload(entry, block, send_entries or [],
                                              expires_in=ttl)
        elif field in loras:
            nodes = value if isinstance(value, list) else [value]
            payload[field] = [{"path": presign_node(one, expires_in=ttl), "scale": scale}
                              for one in nodes]
        else:
            payload[field] = (
                [presign_node(one, expires_in=ttl) for one in value]
                if isinstance(value, list)
                else presign_node(value, expires_in=ttl)
            )
    if bindings:
        logger.info("Minted presigned URLs for %s on run %s",
                    sorted(bindings), record["id"])
    if grant:
        payload.update(output_grant_urls(record, grant))
    provider = registry.provider_of(entry)
    return client_for(provider).create_prediction(
        entry["model"], payload, webhook=callback_url(record["id"], provider)
    )


#: Where a rented worker's result lands before the closing path files it. Not
#: an entity's prefix: nothing in the catalog names a scratch key, and the
#: media bucket's `expire-scratch` lifecycle rule removes it after a week.
SCRATCH_PREFIX = "scratch"
#: How long the grant pair stays good. A cold worker pulls a 15 GB image and
#: loads 60 GB of weights before it renders, and the render itself can run
#: twenty minutes; six hours is generous and still bounded.
OUTPUT_GRANT_TTL = 6 * 3600


def output_grant_urls(record: dict, grant: dict) -> dict:
    """The two presigned URLs a worker of ours gets for its result.

    One scratch key, `scratch/<run id>/result<ext>`; a PUT the worker uploads
    to (`presign_put_unsized`, because the size of a clip is not known at
    dispatch) and a GET it answers as `output.result`, which the closing path
    downloads and files under `output/` like any provider's URL. The GET is
    ours, so `_unsigned_input` scrubs it out of the stored response the way it
    scrubs the inputs.
    """
    key = f"{SCRATCH_PREFIX}/{record['id']}/result{grant['ext']}"
    return {
        grant["put"]: s3.presign_put_unsized(
            key, content_type=grant["content_type"], expires_in=OUTPUT_GRANT_TTL),
        grant["get"]: s3.presign(key, expires_in=OUTPUT_GRANT_TTL),
    }


def presign_node(node_id: str, *, expires_in: int | None = None) -> str:
    """A short-lived GET for one node's bytes. **The only way to a provider.**

    The TTL is the service's (`STUDIO_PRESIGN_TTL_SECONDS`) unless the caller
    is `dispatch` sending to a worker of ours, which passes `OUTPUT_GRANT_TTL`
    because that worker queues (see `dispatch`). Nothing else gets to
    lengthen the window in which an identity reference is fetchable by
    anyone holding the URL.
    """
    record = catalog.node(node_id)
    if not record.get("blob_key"):
        raise ValidationError(
            f"node {node_id} has no bytes behind it and cannot be sent to a model"
        )
    return s3.presign(record["blob_key"], expires_in=expires_in)


# ───────────────────────────────── closing ──────────────────────────────────


def _cost(record: dict, prediction: dict) -> dict | None:
    """What the run cost, in whatever terms its provider will say.

    Replicate says a duration and never a price; a Runpod public endpoint says
    the price in dollars. Each client reads its own body, and both write the
    same three keys, so `runs list` prints `cost.amount` and skips a null.
    """
    return client_for(provider_of(record)).cost(prediction)


def _output_urls(record: dict, prediction: dict) -> list[str]:
    """Every file the prediction produced, in order — in the provider's shape."""
    return client_for(provider_of(record)).output_urls(prediction)


def _store_output(record: dict, folder_id: str, url: str, name: str) -> str:
    """Download one output and put it in the run's `output/` folder.

    **Through the filesystem, never through memory.** See
    `replicate.download` and `s3.put_file`: the bytes are streamed to `/tmp` and
    then sent as a single PUT, which keeps the callback's memory flat whatever
    the model produced and keeps the object's ETag the MD5 of its bytes so
    `set_blob` can record a real checksum.

    The node is created first because its id is what names the key — the same
    ordering every other upload path in this service uses.

    **No `owner` is passed in**, unlike the bulk copy path, because
    `create_numbered` resolves it. That is one ancestry read per output rather
    than one per close; a run produces a handful of files, so the saving the
    cache would buy is smaller than the branch needed to use it.
    """
    # **`create_numbered`, not `create_node`, and this is a retry bug rather than
    # a nicety.** A name clash in `create_node` is a `ConflictError`, and a close
    # that fails part-way through several outputs leaves the first one already
    # written — so the redrive hit the clash, failed identically every time, and
    # marched a paid generation to the dead-letter queue over a filename. The
    # numbered form means a retry lands `image (2).png` beside a stray from the
    # first attempt: one orphan file, which is tidyable, instead of a run that
    # can never close.
    node = catalog.create_numbered(folder_id, name, catalog.KIND_FILE)

    handle, staged = tempfile.mkstemp(prefix="studio-output-")
    os.close(handle)
    try:
        # **Typed by what the provider served, not by the filename.** The
        # `Content-Type` on the download is the type measured when the bytes
        # landed; the extension is the fallback. `media/mime.py` has the rule,
        # and the 47 `.webp` outputs stored `application/octet-stream` that
        # made it one.
        served = client_for(provider_of(record)).download(
            url, staged, max_bytes=config.max_output_bytes()).content_type
        content_type = mime.content_type_of(name, served)
        # **A clip is indexed for the browser before it is stored.** Every
        # provider writes `moov` last, which makes a tile's poster frame cost
        # the whole file; `media/faststart.py` has the measurement. Done here,
        # on the staged file, because this is the one moment the bytes are on
        # a disk this service owns — a refusal leaves the file as it came.
        indexed = faststart.is_mp4_name(name)
        if indexed and faststart.faststart(staged):
            logger.info("Faststarted output %s for run %s", node["node_id"], record["id"])
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
        # Marked whichever way the rewrite went: it ran over the staged file,
        # so the object is `moov`-first now, and a sweep need not re-read it.
        faststart=True if indexed else None,
    )
    logger.info("Stored output %s for run %s", node["node_id"], record["id"])
    return node["node_id"]


def _queue_posters(record: dict, outputs: list[str]) -> None:
    """Ask the render worker for a poster per output, so a tile need not load it.

    **Every output, still or clip.** Stills were skipped at first — "a still
    is its own poster" — and the feed drew each one whole: a 0.4 MB JPEG per
    tile at best, and the references a run was sent, uploaded phone photos and
    multi-megabyte PNGs, at worst. `media/imaging.poster` has the sizes.

    **Best effort, and it must be.** This runs inside the close of a paid
    run, and `render.queue_poster` says why nothing here may raise.
    """
    from studio_core.services import render  # circular at import time; not at call time
    for node_id in outputs:
        render.queue_poster(record["lib"], node_id)


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


def _store_all(record: dict, urls: list[str]) -> list[str]:
    """Download every output into the run's `output/` folder, in order."""
    folder = layout.folder_under(record["folder"], layout.OUTPUT_FOLDER)
    return [
        _store_output(record, folder["node_id"], url, name)
        for url, name in zip(urls, _output_names(record, urls))
    ]


def _after_the_output_expired(record: dict, gone: Exception):
    """**Ask once for a fresh URL; if the file is really gone, say so.**

    Replicate serves outputs on time-limited URLs and deletes the files after
    about an hour, and the two failures are indistinguishable at the socket. The
    first is recoverable — `GET /v1/predictions/<id>` re-signs the same file — so
    it is worth exactly one more request before giving up.

    **Giving up means closing the run `failed`, not retrying.** This used to be
    an exception that propagated, which put the message back on the queue to be
    attempted against a URL that will never work again, five times, and then into
    the dead-letter queue — where the run still said `running` and nobody was
    told anything. A run that says `failed` and names the reason is the honest
    outcome and the one somebody can act on: the generation was paid for, and its
    bytes are not recoverable.

    That is a real loss, and the reason it is survivable rather than guarded
    against is in `infra/modules/callbacks`: the window is bounded by how far
    behind the consumer can fall, and prod's consumer runs seconds after the
    callback.
    """
    logger.warning("Outputs for run %s were gone; asking for fresh URLs: %s",
                   record["id"], gone)
    client = client_for(provider_of(record))
    try:
        fresh = _output_urls(record, client.get_prediction(
            record["prediction_id"], model=record.get("model") or ""))
        if fresh:
            return _store_all(record, fresh), "succeeded", None
    except client.OutputGone:
        pass
    # Any other provider error propagates: the provider being unreachable IS
    # transient, and the queue should retry rather than declare a paid
    # generation lost on one bad round trip.

    return [], "failed", (
        "the prediction succeeded but its output was no longer available to "
        "download. The provider deletes output files some time after a "
        "prediction completes (Replicate after about an hour), and this "
        "callback was processed after that. The generation was paid for; its "
        "bytes are not recoverable."
    )


#: A value carrying a URI scheme. The same shape `routes/runs.py` refuses in a
#: binding, and for the same reason — `https:`, `s3:`, `data:` and `file:` are
#: all things that are not a node id. A node id holds no colon.
_URI = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def _is_our_grant(value) -> bool:
    """Whether `value` is a presigned URL on this service's own media bucket."""
    if not isinstance(value, str) or "X-Amz-Signature=" not in value:
        return False
    bucket = config.media_bucket()
    return bool(bucket) and bucket in value.split("?", 1)[0]


def _unsigned_input(record: dict, prediction: dict) -> dict:
    """The provider's echo of `input`, with our presigned URLs put back as node ids.

    **Hard rule #3 says a signed URL is never stored, and storing the response
    verbatim broke it.** A callback carries the payload back to us, image fields
    and all, and those fields hold the short-lived S3 URLs `dispatch` minted — so
    writing the document unchanged filed a set of working credentials for the
    library inside the run's own folder. They expire, and the reader already has
    access to the run, which is why this is a leak worth closing quietly rather
    than an incident. It is still the rule.

    **Substituted rather than redacted, because the node id is the better
    value.** A reader of `response.json` wants to know which image was in which
    field and in which position; a URL answered that badly and expired, and
    `[removed]` would not answer it at all. The mapping is the run's own `SEND#`
    rows, which are ordered — the same rows `dispatch` presigned in the same
    order — so position lines up by construction rather than by parsing anything
    out of a URL.

    **`output` is deliberately untouched.** Those URLs are the provider's, not
    ours: they grant nothing in this library, they are the only record of what
    the model actually returned, and the pipeline's `record_result` kept them for
    exactly that reason before this moved. The rule is about *our* signatures.

    Anything URL-shaped that cannot be mapped is replaced with a marker rather
    than left. A field this service cannot account for is the one case where
    guessing wrong means leaving a live URL in the document.
    """
    # Runpod echoes the `webhook` it was given, `?sig=` and all. The proof is
    # good for this one run, which is terminal by the time this is written, so
    # keeping it would grant nothing — and filing a signature is still the
    # thing this function exists not to do.
    webhook = prediction.get("webhook")
    if isinstance(webhook, str) and "?" in webhook:
        prediction = {**prediction, "webhook": webhook.split("?", 1)[0]}

    # The one exception to "output is untouched": a worker of ours answers
    # `result` with the GET grant `output_grant_urls` minted, which is OUR
    # signature on OUR bucket — the thing this function exists not to file.
    # The provider's own URLs carry no `X-Amz-Signature` for our bucket, so
    # nothing of theirs matches.
    output = prediction.get("output")
    if isinstance(output, dict) and _is_our_grant(output.get("result")):
        prediction = {**prediction, "output": {
            **output, "result": "[studio's own output grant; the file is under output/]"}}

    payload = prediction.get("input")
    if not isinstance(payload, dict):
        return prediction

    bound: dict[str, list[str]] = {}
    for send in catalog.sends(record["id"]):
        if send.get("field"):
            bound.setdefault(send["field"], []).append(send["node"])

    def swap(field: str, value, index: int = 0):
        # A LoRA send is `{path, scale}`; the URL is the path inside it.
        if isinstance(value, dict) and isinstance(value.get("path"), str):
            return {**value, "path": swap(field, value["path"], index)}
        if not isinstance(value, str) or not _URI.match(value):
            return value
        nodes = bound.get(field) or []
        return nodes[index] if index < len(nodes) else "[a presigned URL studio did not store]"

    rewritten = {}
    for field, value in payload.items():
        if isinstance(value, list):
            rewritten[field] = [swap(field, item, i) for i, item in enumerate(value)]
        else:
            rewritten[field] = swap(field, value)
    return {**prediction, "input": rewritten}


def _response_document(record: dict, prediction: dict) -> str | None:
    """The provider's response, stored verbatim as a node. Returns its id.

    The half of the run this service is forbidden to have an opinion about: it is
    encoded and written, and nothing here reads a key inside it — except the
    handful `close_from_prediction` reads off the *parsed* body it was handed,
    which is a different thing from decoding the stored document later.

    **Two exceptions, and both are named rather than silent.** `input` has its
    presigned URLs put back as node ids (`_unsigned_input`, hard rule #3), and an
    oversized `logs` is truncated. The document says so in both cases, because a
    document that has been edited and does not admit it is worse than one that
    was never stored.

    **`logs` is truncated; the document is never dropped.** This used to drop an
    oversized response whole, on the reasoning that half a JSON document is worse
    than none — which is true of truncating the *text*, and was the wrong remedy.
    A `logs` field runs to megabytes precisely when a video render **failed**, so
    the rule discarded the provider's account of the failure in exactly the case
    somebody needs it, leaving `error[:2000]` as the only record.

    So the one unbounded field is cut, in place, with a marker saying so. The
    result is still valid JSON and still the provider's own document; what it is
    not is verbatim, which is why it says so inside itself.
    """
    prediction = _unsigned_input(record, prediction)
    text = json.dumps(prediction, indent=2, sort_keys=True, default=str)
    if len(text.encode()) > config.max_text_bytes():
        prediction = dict(prediction)
        logs = prediction.get("logs")
        if isinstance(logs, str):
            # The tail, not the head: a render's logs end with the reason it
            # stopped, and the beginning is model boot-up nobody reads.
            keep = max(config.max_text_bytes() // 2, 1024)
            prediction["logs"] = (
                f"[… {len(logs) - keep} characters of logs dropped by studio; "
                f"the tail is kept because that is where a failure is …]\n"
                + logs[-keep:]
            )
        text = json.dumps(prediction, indent=2, sort_keys=True, default=str)

    if len(text.encode()) > config.max_text_bytes():
        # Something other than `logs` is enormous. Now there is nothing safe to
        # cut, and a document that cannot be stored is reported rather than
        # silently absent.
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

    A prediction still in flight is likewise a no-op — for a model. The webhook
    filter asks for `completed` only, so this should not happen; a reconcile
    against a running prediction reaches it every time, and the honest answer
    there is "nothing has changed yet". **A training pod is the exception**: it
    reports progress on the same signed URL as each checkpoint lands, and the
    run stays `running` while `training.confirm_progress` files what arrived —
    so a two-hour run shows its weights as they come rather than at the end.
    """
    if record.get("status") in catalog.TERMINAL_RUN_STATUSES:
        logger.info("Run %s is already %s; ignoring a repeat report",
                    record["id"], record["status"])
        return record

    provider_status = (prediction.get("status") or "").lower()
    status = PROVIDER_STATUS.get(provider_status, "failed")
    if status == "running":
        if provider_of(record) == registry.RUNPOD_POD:
            from studio_core.services import training
            return training.confirm_progress(record, prediction)
        return record

    urls = _output_urls(record, prediction) if status == "succeeded" else []
    error = prediction.get("error")
    if status == "succeeded" and not urls:
        # Paid for, and produced nothing. Calling that a success would put an
        # empty run in the grid with a thumbnail that never loads.
        status, error = "failed", "the prediction succeeded but returned no output"

    outputs: list[str] = []
    if provider_of(record) == registry.RUNPOD_POD:
        # The pod wrote its checkpoints straight into the bucket on grants
        # minted at dispatch; nothing is downloaded, the nodes are confirmed.
        from studio_core.services import training
        outputs, status, error = training.adopt_outputs(record, prediction, status, error)
    elif urls:
        try:
            outputs = _store_all(record, urls)
        except client_for(provider_of(record)).OutputGone as gone:
            outputs, status, error = _after_the_output_expired(record, gone)
            urls = outputs

    assignments: dict = {
        "status": status,
        "completed": catalog.now(),
        "error": None if error is None else str(error)[:2000],
        "prediction_id": prediction.get("id") or record.get("prediction_id"),
    }
    cost = _cost(record, prediction)
    if cost is not None:
        assignments["cost"] = cost

    listing: dict = {"status": status}
    if outputs:
        assignments["outputs"] = outputs
        _queue_posters(record, outputs)
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
    if provider_of(record) == registry.RUNPOD_POD:
        # The machine is done with, whichever way it ended. After the row is
        # written, so a terminate that fails leaves a closed run and a pod to
        # clean up by hand rather than a billing pod and a run that says nothing.
        from studio_core.services import training
        training.release(updated)
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
    if provider_of(record) == registry.RUNPOD_POD:
        from studio_core.services import training
        return close_from_prediction(record, training.report(record))
    client = client_for(provider_of(record))
    return close_from_prediction(
        record, client.get_prediction(prediction_id, model=record.get("model") or "")
    )
