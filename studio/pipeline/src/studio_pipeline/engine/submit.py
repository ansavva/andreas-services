"""ONE submission lifecycle, for every model in the registry.

The image and video submitters were ~816 lines doing the same nine steps with
different field names. Those names are registry data now, so the steps live
here once — but **only the first four of them are still in this process**:

    gather image inputs as NODE IDS               ── here
      -> reject what this model will not accept   ── here (a courtesy; see below)
      -> render for approval / stop at --dry-run  ── here.  HARD RULE #2.
      -> RECORD THE RUN as a DRAFT                ── here
      ─────────────────────────────────────────────────────────────────────────
      -> presign at the last moment               ── the API
      -> create the prediction                    ── the API.  This bills.
      -> upload the output into the run           ── the callback consumer
      -> close the run                            ── the callback consumer

**`poll` is gone from that list entirely and its absence is the change.** The
prediction used to be waited on by this process, so a 15-minute video meant a
terminal nobody could close, `Ctrl-C` left a run wedged at `pending` with a
prediction still running, and the SPA could not submit at all because it had no
credential and nothing to wait in. Replicate calls the API back now. What is left
here is `wait_for`, which watches the run row and can be interrupted without
losing anything — the generation is not attached to this terminal any more.

**Nothing in this module holds a Replicate token, and nothing in this package
does.** `adapters/replicate.py` is deleted. The one paid call in the repository
is `clients/replicate.create_prediction` in the backend, reached through
`POST /api/runs/<id>/submit`.

What did NOT move is the half that faces a person. `gather` decides which image
lands in which field and in which position, `render` prints the two documents
hard rule #2 asks somebody to read, and `draft` records the payload before any of
it is approved. Those are authoring, they bill nothing, and they belong where the
person is.

Every invariant the two originals defended is defended here or in
`services/generate.py`, and the places where the two mediums legitimately differ
— a video may be submitted without waiting, an image may not be generated
imageless by accident — are `KIND` below, not branches scattered through the flow.

BINDINGS ARE NODE IDS
---------------------
`gather` resolves every image input to a node id, `record_request` stores those
ids, and a URL is refused twice — by `runs.check_bindings` before the request is
built and by the API when the record is written. A binding used to be an S3 key,
which any rename invalidated; the record now names the thing itself.

THERE IS NO EXCEPTION LEFT, AND THERE WAS ONE
---------------------------------------------
An angle image is bound to the same field as the character's own images and its
POSITION in that list is cited by the prompt, so it could never be handled
somewhere else. While angle images had no catalog node they travelled through `gather`
marked `shared:<key>`, stripped before the record was written and restored at
presign time — so an angle image was sent and cited correctly and was *not* recorded,
which that marker's own comment called a real gap.

The gap is closed rather than narrowed: angle images are ordinary nodes in the
library's `config/` folder, so `as_node` resolves one like any other name path
and a run records it. Everything the marker needed — `SHARED_PREFIX`,
`as_shared`, `is_shared`, `shared_key`, and `store.shared_presign` under it — is
deleted.
"""

import json
import os
import pathlib
import sys
import time

from studio_pipeline.adapters import api
from studio_pipeline.adapters import entities
from studio_pipeline.adapters import store
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import refs as REFS
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import schema as MS

# Where the two mediums genuinely differ. Everything else is shared.
KIND = {
    "image": {
        "slug": "image", "interval": 5, "timeout": 600,
        "default_ext": ".jpg", "tmp": "studio-image-",
        # An image with no inputs is nearly always a mistake, so it must be
        # asked for explicitly. A video without them is merely off-model.
        "require_images": True,
        "always_poll": True,
    },
    "video": {
        "slug": "video", "interval": 15, "timeout": 3600,
        "default_ext": ".mp4", "tmp": "studio-video-",
        "require_images": False,
        "always_poll": False,
    },
}


class SubmitError(Exception):
    """Anything that should stop the run before it bills."""


def defaults(kind: str) -> dict:
    return KIND[kind]


# --------------------------------------------------------------------------
# 0. addressing — what a gathered image reference is
# --------------------------------------------------------------------------

def as_node(value: str) -> str:
    """A node id passed through; anything else read as a name path and resolved.

    `--key`, `--start-key` and `--end-key` are frozen flag names — they are in
    `tests/contracts/cli_surface_reference.json`, which is a contract — but what they now
    take is a node id. A name path is still accepted and resolved because a
    person reaching for one of these flags is looking at a listing rather than
    at a row, and `GET /api/resolve` is exactly the translation between the two.
    """
    if value.startswith("node-"):
        return value
    try:
        return store.resolve(value)["id"]
    except api.NotFound as exc:
        raise SubmitError(
            f"no such object: {value}\n"
            f"       pass a node id, or a path like <character>/reference/face/<file>"
        ) from exc


#: node id -> its record, for the life of the process. A node's name and size do
#: not change under a running command, and the same handful of images is looked
#: at three times — by the format check, by the byte warning and by the approval
#: render. Fetching each once is the difference between one request per image and
#: three.
_RECORDS: dict[str, dict] = {}


def describe(ref: str) -> dict:
    """`{"name", "size"}` for one gathered image.

    Every reference has a row now, including an angle image, so there is one
    answer rather than two. `size` may still be absent — a placeholder whose
    upload was never confirmed has no bytes — and the byte warning reads that as
    "not known" rather than as 0, which is a real size.
    """
    if ref not in _RECORDS:
        _RECORDS[ref] = store.node(ref)
    record = _RECORDS[ref]
    return {"name": record.get("name") or "", "size": record.get("size")}


def _ext(ref: str) -> str:
    return os.path.splitext(describe(ref)["name"])[1].lower()


def _label(ref: str) -> str:
    """`<name> (<ref>)` — what a person reads in the approval render.

    A node id alone is unreviewable, and hard rule #2 is a rule about a payload
    a person can actually check. The id stays beside the name because it is what
    the record will hold and what a follow-up command takes.
    """
    return f"{describe(ref)['name']} ({ref})"


def flatten(bindings: dict) -> list[str]:
    """Every gathered reference across every field, in field order."""
    out: list[str] = []
    for value in bindings.values():
        out += value if isinstance(value, list) else [value]
    return out


def recorded(bindings: dict) -> dict:
    """The bindings a run RECORDS.

    Every gathered reference is a node id now, so this is the identity function
    and is kept as a named seam rather than inlined. It used to drop the pose
    angle images, which had no id to record — the one thing a run could be shown and
    not remember. See the module docstring for why that is over.
    """
    return dict(bindings)


def presign(ref: str) -> str:
    """A short-lived URL for one gathered reference. **The only way to Replicate.**

    There is no expiry to pass: the API signs against its own credentials and
    owns the TTL (`STUDIO_PRESIGN_TTL_SECONDS`). The `--expires` flag that used
    to be threaded down to here is gone. See `runs.presign`.
    """
    return store.presign_node(ref)


# --------------------------------------------------------------------------
# 1. gather — every image input, as node ids, never URLs
# --------------------------------------------------------------------------

def gather(entry: dict, args) -> dict:
    """Resolve all image inputs to node ids and bind them to this model's fields.

    Returns `{field: node | [nodes]}`. Order matters for the reference list: an
    explicitly named edit target first, then curated identity, then chained run
    outputs, then the working pool, then explicitly named objects.

    `args.project` is the project RECORD. It used to be a slug, and every use
    below is a reason it should not be: a runref defaults against the project's
    id, and the id is what the run record stores.
    """
    imgs = entry.get("images") or {}
    refs_field = imgs.get("refs")
    start_field, end_field = imgs.get("start"), imgs.get("end")
    exts = REG.accepts_ext(entry)
    bindings: dict[str, list[str] | str] = {}

    # --- first / last frame (video engines only) ---------------------------
    start_run = getattr(args, "start_run", None)
    start_key = getattr(args, "start_key", None)
    end_run = getattr(args, "end_run", None)
    end_key = getattr(args, "end_key", None)
    if (start_run or start_key or end_run or end_key) and not start_field:
        raise SubmitError(
            f"{entry['key']} has no first/last frame input — "
            f"--start-run/--start-key/--end-run/--end-key do not apply to it."
        )
    # A bare runref resolves inside the PROJECT, never inside a character —
    # runs belong to a project now, so defaulting to the character name would
    # look for history somewhere that has none.
    project = args.project
    if start_field:
        if start_run:
            bindings[start_field] = R.resolve_output_nodes(
                start_run, project["id"], kinds=exts)[0]
        elif start_key:
            bindings[start_field] = as_node(start_key)
        if end_run or end_key:
            if start_field not in bindings:
                raise SubmitError(
                    f"a last frame requires a first frame ({end_field} needs {start_field}).")
            bindings[end_field] = (
                R.resolve_output_nodes(end_run, project["id"], kinds=exts)[0]
                if end_run else as_node(end_key)
            )

    # --- the reference / input list ----------------------------------------
    slots = [int(s) for s in args.slots.split(",")] if getattr(args, "slots", None) else None
    pick = [x.strip() for x in args.pick.split(",")] if getattr(args, "pick", None) else None
    tags = [t.strip() for t in args.pick_tag.split(",")] if getattr(args, "pick_tag", None) else None
    cap = imgs.get("max_refs")
    nodes: list[str] = []
    if getattr(args, "image_run", None):
        nodes += R.resolve_output_nodes(args.image_run, project["id"], kinds=exts)
    for character in (args.character or []):
        nodes += REFS.character_ref_nodes(character, slots, pick, tags,
                                          cap=cap, cap_name=entry["key"])
    for ref in getattr(args, "ref_run", None) or []:
        nodes += R.resolve_output_nodes(ref, project["id"], kinds=exts)
    # `input_`, because `input` shadows the builtin and Click was given the safe
    # spelling. This read `args.input` through a defaulting getattr, so
    # `--input 3` bound NOTHING and said nothing — the quietest possible failure:
    # either a confusing "no image inputs", or a run that proceeds without the
    # image the caller asked for. Both spellings are accepted now.
    numbers = getattr(args, "input_", None) or getattr(args, "input", None)
    if numbers:
        nodes += REFS.project_input_nodes(project, numbers)
    nodes += [as_node(k) for k in (getattr(args, "key", None) or [])]

    seen: set[str] = set()
    nodes = [n for n in nodes if not (n in seen or seen.add(n))]  # de-dupe, keep order

    # The format rule applies to EVERY image, not just the reference list. It
    # used to be checked inside the `if nodes:` block below, so a `.webp` start
    # frame sailed through to a model that rejects `.webp` and failed at the
    # provider instead — after the submit, and with the provider's wording
    # rather than the one that names `studio convert`. A start frame is the
    # commonest thing to hand straight from an image run, which is exactly where
    # `.webp` comes from.
    #
    # The extension comes off the node's NAME, not off a key: a node's name is
    # what a person sees and what `content_type` agrees with, and there is no
    # key here to read one from any more.
    frames = [bindings[f] for f in (start_field, end_field) if f and f in bindings]
    bad_frames = [f for f in frames if _ext(f) not in exts]
    if bad_frames:
        raise SubmitError(
            f"{entry['key']} accepts only {sorted(exts)}; incompatible: "
            f"{[_label(f) for f in bad_frames]}\n"
            f"       convert with: studio convert "
            f"--for {entry['key']} --key <node> --add-input <project>"
        )

    if nodes and refs_field is None:
        # A model with no reference LIST still has an image field, and binding
        # to `None` produced a dict with a null key that surfaced two calls
        # later as `TypeError: '<' not supported between NoneType and str`
        # inside the schema error path — an unreadable crash in the code whose
        # job is to explain the fault.
        raise SubmitError(
            f"{entry['key']} takes no reference list — it has a single image "
            f"input, `{start_field}`.\n"
            f"       Bind it with --start-key <node> rather than --key/--character."
        )

    if nodes:
        # A LAST frame can exclude the reference list even where a first frame
        # does not. Kling takes a start frame and references together happily,
        # but the moment an end frame joins them the payload is capped at those
        # two images and the whole request is rejected. Nothing in the live
        # schema says so — it surfaces only as an E006 after the submit, which
        # is why it is recorded in the registry rather than learned twice.
        if end_field in bindings and imgs.get("end_excludes_refs"):
            raise SubmitError(
                f"{entry['key']}: with both `{start_field}` and `{end_field}` set, "
                f"`{refs_field}` must be empty — it takes those two images and no more.\n"
                f"       Drop the references, or drop the end frame and let the "
                f"prompt describe where the shot lands.")
        if start_field in bindings and imgs.get("start_excludes_refs"):
            raise SubmitError(
                f"{entry['key']}: `{start_field}` and `{refs_field}` are mutually exclusive.\n"
                f"       A start frame already carries identity — drop "
                f"--character/--ref-run, or drop the start frame."
            )
        bad = [n for n in nodes if _ext(n) not in exts]
        if bad:
            raise SubmitError(
                f"{entry['key']} accepts only {sorted(exts)}; incompatible: "
                f"{[_label(n) for n in bad]}\n"
                f"       convert with: studio convert "
                f"--for {entry['key']} --key <node> --add-input <project>"
            )
        if cap and len(nodes) > cap:
            raise SubmitError(
                f"{entry['key']} accepts at most {cap} images; got {len(nodes)}.\n"
                f"       Narrow the reference selection (--pick / --pick-tag, or the "
                f"character's default_set) rather than hoping the extras are dropped.")
        bindings[refs_field] = nodes

    _warn_total_bytes(entry, bindings)
    return bindings


#: Measured, not documented. Every generation that succeeded sent no more than
#: 6.41 MiB of images in total; the three that failed sent 13.89 MiB. A single
#: 3.10 MiB image passed on its own, so the limit is on the SUM and not on any
#: one file. This sits just above the largest known-good total.
BYTES_WARN = 6.5 * 1024 * 1024


def _warn_total_bytes(entry: dict, bindings: dict) -> None:
    """Warn when a VIDEO payload carries more image data than has ever worked.

    A warning, not an error: 6.41 MiB is the largest total observed to succeed,
    which is not the same as a documented ceiling, and refusing a payload on a
    measurement would be worse than sending it.

    It is worth saying at all because of HOW it fails. An oversized payload is
    accepted, sits for over two minutes, and comes back `PA — Prediction
    interrupted; please retry`, with no `started_at`, no metrics and empty logs.
    That reads as an upstream blip and invites retrying it unchanged, which is
    exactly what three consecutive failures were spent on.

    Video only, because that is where the evidence is. The image models have
    taken five 2.4 MiB angle images — around 12 MiB — repeatedly and without
    complaint, so warning about them would be a false alarm on every reference
    turnaround, and a warning that cries wolf is worse than none.

    The sizes come off the node rows the format check already fetched, where
    this used to be a `HEAD`-shaped call per key. A reference of unknown size —
    shared material, or a placeholder never confirmed — is skipped rather than
    counted as zero, so the total is honest about being a lower bound.
    """
    if entry.get("kind") != "video":
        return
    refs = flatten(bindings)
    if not refs:
        return
    try:
        sizes = [describe(ref)["size"] for ref in refs]
    except Exception:  # noqa: BLE001
        return  # sizing is a courtesy; never let it break a submit
    total = sum(size for size in sizes if size)
    if total <= BYTES_WARN:
        return
    print(f"warning: this payload carries {total / 1048576:.1f} MiB of images across "
          f"{len(refs)} file(s).\n"
          f"         No generation above ~6.4 MiB has ever completed here — over that "
          f"it tends to be accepted, hang, and fail as `PA`, which looks retryable and "
          f"is not.\n"
          f"         studio convert --key <node> --to jpeg --add-input <project>",
          file=sys.stderr)


def check_payload_rules(entry: dict, payload: dict) -> None:
    """Cross-field rules a per-field schema check cannot express.

    Scoped by the presence of the field, so each rule applies only to the
    models that actually have it.
    """
    # Kling bills per second and rejects a multi-shot timeline whose shot
    # durations don't sum to `duration` (E006) — catch it here, not after billing.
    if payload.get("multi_prompt"):
        mp = payload["multi_prompt"]
        try:
            shots = json.loads(mp) if isinstance(mp, str) else mp
        except json.JSONDecodeError as e:
            raise SubmitError(f"multi_prompt is not valid JSON: {e}")
        total = sum(s.get("duration", 0) for s in shots)
        if payload.get("duration") is not None and total != payload["duration"]:
            raise SubmitError(
                f"multi_prompt shot durations sum to {total}s but duration is "
                f"{payload['duration']}s — they must be equal (this is E006).")
        cap = REG.field(entry, "video.max_cuts")
        if cap and len(shots) > cap:
            raise SubmitError(
                f"{entry['key']} allows at most {cap} shots; got {len(shots)}.")

    cap = REG.field(entry, "prompt.max_chars")
    if cap and len(payload.get("prompt") or "") > cap:
        raise SubmitError(
            f"{entry['key']} caps the prompt at {cap} characters; "
            f"got {len(payload['prompt'])}.")


# --------------------------------------------------------------------------
# 2. preflight — reject what this model will not accept, before anything bills
# --------------------------------------------------------------------------

def _check_image_budget(entry: dict, bindings: dict) -> None:
    """Some models cap TOTAL images, not just the reference list.

    Kling advertises `reference_images` "up to 7" and separately allows a start
    frame alongside them, which reads as 7 + 1 and is not: the cap counts every
    image, so a start frame leaves room for six references. Over the line it
    fails the whole prediction with

        Error code 1201: The number of images and elements exceeds the limit,
        max number is 7.

    Cheap to hit and easy to miss, because the two halves of the rule sit in
    different fields. It bites hardest with a character whose `default_set`
    holds exactly seven — the shape `turnaround` produces — since binding that plus a
    start frame is over by one.

    Registry-driven rather than named per model: `start_counts_toward_max_refs`.
    """
    images = entry.get("images") or {}
    cap = images.get("max_refs")
    if not cap or not images.get("start_counts_toward_max_refs"):
        return
    refs = bindings.get(images.get("refs")) or []
    extra = [f for f in (images.get("start"), images.get("end")) if f and bindings.get(f)]
    total = len(refs) + len(extra)
    if total > cap:
        raise SubmitError(
            f"{entry['key']} accepts {cap} images IN TOTAL and the "
            f"{'/'.join(extra)} counts toward that — got {len(refs)} reference "
            f"image(s) plus {len(extra)}, which is {total}.\n"
            f"       Narrow the selection to {cap - len(extra)} with --pick; the "
            f"start frame already carries wardrobe and framing, so drop a body "
            f"reference rather than a face one.")


def preflight(entry: dict, payload: dict, bindings: dict) -> None:
    """Documented constraints first, then the live schema.

    Runs on --dry-run too, so an approved payload is a payload that submits.

    **A courtesy now, not the gate.** The API runs its own copy of this at submit
    time (`services/generate.preflight`), because the SPA submits too and never
    passes through here. What this one buys is the message: it happens before the
    draft is written, so a bad payload never becomes a row, and it can afford the
    sibling-model lookup below that names where an unknown field *is* accepted.

    **No token.** The schema is read through `GET /api/models/<name>/schema` —
    see `engine/schema.py` for why the credential left this package.
    """
    model = entry["model"]
    _check_image_budget(entry, bindings)
    MS.check_denied(payload, entry, model)
    props, schemas = MS.fetch(model)
    alts: dict[str, dict] = {}
    if [k for k in list(payload) + list(bindings) if k not in props]:
        # Only on the error path — worth extra lookups to name the fix.
        for key, other in REG.of_kind(entry["kind"]).items():
            if key == entry["key"]:
                continue
            try:
                alts[key], _ = MS.fetch(other["model"])
            except MS.SchemaError:
                pass
    MS.check(payload, bindings, model, props, schemas, alternatives=alts)


# --------------------------------------------------------------------------
# 3. render — the approval view
# --------------------------------------------------------------------------

#: What the approval render says the payload will be POSTed to.
#:
#: **A string this process no longer calls**, and it stays because hard rule #2
#: is about what a person can check: a payload document that did not say where it
#: was going would be a worse thing to approve. It came from
#: `adapters/replicate.predictions_endpoint`, which went with the rest of that
#: module when the submission moved into the API.
REPLICATE_PREDICTIONS = "https://api.replicate.com/v1/models/{model}/predictions"


def predictions_endpoint(model: str) -> str:
    """The URL the API will POST this payload to. Shown, never called."""
    return REPLICATE_PREDICTIONS.format(model=model)


def render(entry: dict, run: str, payload: dict, bindings: dict, as_json: bool) -> str:
    """The two-document approval render, or raw JSON for machines.

    **Hard rule #2's surface.** Image inputs appear as what will be signed into
    the field at submit time: the signed URL is ~2 KB of noise and expires, so it
    is never the reviewable form.

    What is reviewable changed with the record. A node id is the honest
    identifier and is unreadable, so the human render shows `<name> (<id>)` —
    the name is what makes the payload checkable, and the id is what the record
    will hold and what a follow-up command takes. `--json` keeps bare ids,
    because its consumer is a machine that wants the identity and not the label.
    """
    endpoint = predictions_endpoint(entry["model"])
    if as_json:
        return json.dumps({
            "run": run, "model": entry["model"], "endpoint": endpoint,
            "input": payload, "bindings": bindings,
        }, indent=2, ensure_ascii=False)
    readable = {
        field: ([_label(one) for one in value] if isinstance(value, list)
                else _label(value))
        for field, value in bindings.items()
    }
    return R.render_payload(run, entry["model"], endpoint, payload, readable)


# --------------------------------------------------------------------------
# 4-9. execute — record, presign, submit, poll, upload, close
# --------------------------------------------------------------------------

def plan_of(entry: dict, payload: dict) -> dict:
    """The AUTHORED half of a run — what a person decided, as studio's own data.

    **The line is drawn at the rendered provider input**, which is the same line
    a scene already holds: a shot's `motion.prompt` is authored and queryable
    while the run it renders into keeps the provider payload as an undecoded
    blob. `plan` is studio's; `request.json` is the provider's; neither is a copy
    of the other, because the plan carries no image fields at all — those are
    sends, and they are presigned in at the last moment.
    """
    return {
        "version": 1,
        "origin": "authored",
        "prompt": payload.get("prompt"),
        "params": {k: v for k, v in payload.items() if k != "prompt"},
    }


def sends_for(entry: dict, bindings: dict) -> list[dict]:
    """Every bound image as an ordered send, with the ROLE the registry gives it.

    **The role is the half `bindings` threw away.** `gather` decides an image is
    a start frame or a reference and then records a `{field: [node, …]}` map, so
    a run page could say six images went out and never which was which. The
    mapping from field name to role is registry data — `images.start`, `.end`,
    `.refs` — so it is read from the entry rather than guessed from the name.

    `source` is left out deliberately: the API derives it from where each node
    sits, so a run submitted today and a run reconstructed from history describe
    their images in the same words. See `catalog.source_of`.
    """
    images = entry.get("images") or {}
    role_of = {images.get(name): role for name, role in
               (("start", "start"), ("end", "end"), ("refs", "reference"))
               if images.get(name)}
    return [
        {"field": field, "role": role_of.get(field, "input"), "node": node}
        for field, value in bindings.items()
        for node in (value if isinstance(value, list) else [value])
    ]


#: The states a run reaches without ever having been sent. A draft that was
#: written and abandoned billed nothing, so it must not make the next identical
#: payload read as a duplicate — which is the one thing the local ledger got
#: right for free, by only ever being written after a successful submit.
NEVER_BILLED = ("draft", "discarded")


def already_submitted(record: dict) -> dict | None:
    """An EARLIER run that sent this exact payload to this project, or `None`.

    **The fingerprint is read off the draft, never computed here.** That is the
    whole point: the API derives it from `plan_digest`, which is derived from the
    plan and the sends, and a second implementation this side of the wire would
    be a fourth hash of one thing in a repository that has already been bitten by
    the third. `plan_digest` had three implementations and one of them silently
    disagreed over `Decimal`, reporting 131 healthy runs as stale.

    So the order is: draft first — a row, no bytes, nothing billed — then ask
    whether anything else here carries the same fingerprint.

    Never-billed states are excluded, which is the property the local ledger got
    for free by only ever being written after a successful submit. An abandoned
    draft must not make the next identical payload look like a duplicate.

    Failures are swallowed. This is a guard rail, and one that cannot reach the
    API must not be the thing that blocks a legitimate submission: a false
    negative costs money once, a false refusal costs somebody their afternoon.
    """
    fingerprint = record.get("fingerprint")
    if not fingerprint:
        return None
    try:
        found = entities.query_runs(project=record["project"],
                                    fingerprint=fingerprint, include="drafts")
    except api.ApiError:
        return None
    for run in (found or {}).get("runs") or []:
        if run.get("id") != record["id"] and run.get("status") not in NEVER_BILLED:
            return run
    return None


def draft(entry: dict, payload: dict, bindings: dict, args) -> dict:
    """Create the run as a DRAFT. **Nothing has billed and nothing is approved.**

    Split out of `execute` so that the payload a person reads has an address.
    `--dry-run` stops here, which is the point of the split: what used to be a
    block of text that scrolled away is a record that can be opened in the app,
    edited, linked to and approved later.
    """
    kind = entry["kind"]
    project = args.project          # the project record, resolved by the caller
    prompt_source = json.load(open(args.prompt_json)) if getattr(args, "prompt_json", None) else None
    # `--character` doubles as "resolve refs from" and "this run is of", which is
    # the same thing for `studio run`. A turnaround resolves its own images
    # (seed photos, an angle image) and so passes no `--character`, but the run is
    # still OF that character — and `runs find --character` is how that
    # association is read back. Hence the explicit override.
    characters = list(getattr(args, "record_characters", None) or args.character or [])
    try:
        return R.record_request(
            project["id"], kind=kind, engine=entry["skill"],
            model=entry["model"], input=payload,
            bindings=recorded(bindings),
            plan=plan_of(entry, payload),
            sends=sends_for(entry, bindings),
            characters=REFS.character_ids(characters),
            prompt_source=prompt_source,
            # **What the output file will be called, recorded at DRAFT time.**
            # It used to be an argument to the download, because the download
            # happened in this process. The API downloads now, driven by a
            # callback that arrives with no request body — so if the name is not
            # on the row before the submission, nothing will ever know it.
            #
            # Not part of `plan`, deliberately: `plan_digest` hashes the plan, so
            # a filename in there would void an approval over something the
            # provider is never sent.
            name=R.slugify(getattr(args, "name", None) or defaults(kind)["slug"]))
    except R.RunError as e:
        raise SubmitError(f"refusing to record an invalid request: {e}")
    except REFS.RefError as e:
        raise SubmitError(f"refusing to record a run against an unknown character: {e}")


def approve(record: dict) -> dict:
    """Record approval of exactly the payload that was just rendered.

    **The digest is what makes this an approval rather than a timestamp.** It is
    the one the API computed when the draft was written, so approving says yes to
    a specific set of words and a specific ordered list of images — and the API
    refuses it if either has moved since.

    This does not weaken hard rule #2 and it does not satisfy it either. The rule
    is about a person reading a payload and answering; what this adds is that the
    answer survives, names what it was an answer to, and dies when that changes.
    """
    try:
        return entities.approve_run(record["id"], record["plan_digest"])
    except api.ApiError as exc:
        raise SubmitError(
            f"could not approve run {record['id']}: {exc}\n"
            f"       If the payload moved since it was rendered, read it again: "
            f"studio runs show {record['id']}"
        ) from exc

def execute(entry: dict, payload: dict, bindings: dict, args,
            on_drafted=None) -> dict:
    """Draft, approve, submit — and return the RUN RECORD.

    **Unchanged from the outside, and that is deliberate.** Invoking `studio run`
    without `--dry-run` is the request to submit, exactly as it has always been,
    so the approval is recorded here rather than demanded as a second command.
    What changed is that the yes now leaves a row naming the payload it was for.

    A person who wants the two steps apart has them: `--dry-run` leaves the
    draft, and `studio runs approve` re-renders it and asks.

    It returned an exit code once, and every batch caller then went back for
    `<project>/latest` to find out which run it had just made — a lookup that is
    wrong the moment two runs land in one project close together, and that could
    not be right at all: a run has no name to be looked up by.

    **`on_drafted` runs between the draft and the approval**, which is the only
    window where a duplicate can be refused for free: the draft exists, so its
    fingerprint does, and nothing has billed. `runner.py` passes the refusal;
    a caller that does not care passes nothing and the flow is what it was.

    **The `token` argument is gone from here and from `submit`.** Nothing in this
    package holds a Replicate credential any more; the API does.
    """
    record = draft(entry, payload, bindings, args)
    if on_drafted is not None:
        on_drafted(record)
    approve(record)
    return submit(entry, record, payload, bindings, args)


def submit(entry: dict, record: dict, payload: dict, bindings: dict,
           args) -> dict:
    """Ask the API to send it. **One call, and this process stops being load-bearing.**

    This function was 100 lines: patch to `pending`, presign every binding, create
    the prediction, poll until it settled, download each output, upload it into
    the run, close the row. All of that is `POST /api/runs/<id>/submit` and a
    callback now, and what it cost to keep here is worth restating rather than
    forgetting:

    * **A generation was attached to a terminal.** A 15-minute video meant a
      window nobody could close, and `Ctrl-C` at minute 14 left a run at
      `running` with a prediction still billing and nothing to record it.
    * **The SPA could not submit at all.** It has no provider credential and
      nowhere to poll from, so every generation had to originate in a CLI.
    * **The download was this machine's.** A 200 MB clip came down a home
      connection and went back up to S3.

    `payload` and `bindings` are still parameters and are still **not sent**. The
    API rebuilds both from the run's own plan and sends, which is the point: a
    payload assembled twice is two opinions about what was approved. They are
    here because the caller has them and because `--dest` and the render below
    read them, and they are deliberately not passed to the route.

    **What is preserved exactly:** the API moves the run to `pending` before it
    calls the provider, so the approval gate still stands in front of the money
    and a submission that dies in flight still reads as "went out and never
    answered" rather than as a draft.
    """
    kind = entry["kind"]
    d = defaults(kind)
    project = args.project          # the project record, resolved by the caller
    run_id = record["id"]
    print(f"run {run_id}  (in {project['name']})", file=sys.stderr)

    try:
        sent = entities.submit_run(run_id)
    except api.ApiError as exc:
        raise SubmitError(
            f"refusing to submit run {run_id}: {exc}\n"
            f"       Read the payload and approve it: studio runs approve {run_id}"
        ) from exc

    prediction = sent.get("prediction_id")
    # **How this run will be closed**, decided by the API and reported rather
    # than guessed. `webhook` means Replicate will call back and the row is what
    # to watch; `poll` means nothing on the internet can reach that API — a
    # machine with no receiver provisioned — and `reconcile` is what moves it.
    callback = sent.get("callback") or "poll"
    print(f"submitted — prediction {prediction} (closed by {callback})",
          file=sys.stderr)

    if not (d["always_poll"] or getattr(args, "poll", False)):
        print(json.dumps({"run": run_id, "id": prediction, "status": sent.get("status")},
                         indent=2))
        print(f"not waiting — the run closes on its own. Watch it with: "
              f"studio runs show {run_id}", file=sys.stderr)
        return sent

    closed = wait_for(run_id, callback, args.interval, args.timeout)

    if closed.get("status") != "succeeded":
        raise SubmitError(
            f"run {run_id} {closed.get('status')}: {closed.get('error')}")

    outputs = [o.get("node") for o in closed.get("outputs") or [] if o.get("node")]
    if getattr(args, "dest", None):
        _save_local(closed, args.dest)

    print(json.dumps({
        "run": run_id, "runref": f"{run_id}#1", "model": entry["model"],
        "status": "succeeded", "outputs": outputs,
    }, indent=2))
    return closed


def wait_for(run_id: str, callback: str, interval: int, timeout: int) -> dict:
    """Watch a run until it settles. **Waiting, not driving.**

    The distinction is the whole of what changed. This used to poll the
    *provider* holding the only handle on a running prediction, so interrupting
    it lost the generation. It polls the *run row* now: the work is being closed
    by something else, and `Ctrl-C` here abandons a wait rather than a
    generation. Whatever this process does or does not do, the run finishes.

    Two ways to ask, and the API said which applies at submit time:

    * `webhook` — read the row. Something else is closing it.
    * `poll` — nothing can reach that API, so this drives `reconcile`, which asks
      the provider and closes the run in the same call. Same closing code either
      way; see `services/generate.py`.

    A timeout is **not** a failure of the run and does not mark it as one. The
    prediction is still going and will still be closed; what ran out is this
    terminal's patience, and the message says how to pick the thread back up.
    """
    deadline = time.time() + timeout
    seen = None
    while True:
        try:
            current = (entities.reconcile_run(run_id) if callback == "poll"
                       else entities.get_run(run_id))
        except api.ApiError as exc:
            raise SubmitError(
                f"could not read run {run_id} while waiting: {exc}\n"
                f"       The generation is unaffected: studio runs show {run_id}"
            ) from exc

        status = current.get("status")
        if status != seen:
            print(f"  {status}", file=sys.stderr)
            seen = status
        if status in TERMINAL:
            return current
        if time.time() > deadline:
            raise SubmitError(
                f"gave up waiting after {timeout}s; run {run_id} is {status} and "
                f"is still going.\n"
                f"       Nothing was lost — it closes on its own. Check it with: "
                f"studio runs show {run_id}\n"
                f"       Or close it now with:  studio runs reconcile {run_id}")
        time.sleep(interval)


#: What `wait_for` stops on. **Studio's words, not the provider's** — the API
#: owns the run's status and maps `canceled` to `cancelled` on the way in, so a
#: caller here never sees Replicate's vocabulary.
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "discarded"})


def _save_local(record: dict, dest: str) -> None:
    """`--dest`: keep a copy of each output on this machine.

    The bytes used to be here already — they came down from the provider through
    this process — so this was `os.replace` out of a temporary directory. The
    output goes provider → API → S3 now and never touches this machine, so a
    local copy is a download, and it is one that happens **after** the run is
    safely closed rather than being on the path to closing it.
    """
    os.makedirs(dest, exist_ok=True)
    for output in record.get("outputs") or []:
        node = output.get("node")
        if not node:
            continue
        name = output.get("name") or node
        store.download_node(node, pathlib.Path(dest) / name)
        print(f"saved {os.path.join(dest, name)}", file=sys.stderr)
