"""ONE submission lifecycle, for every model in the registry.

The image and video submitters were ~816 lines doing the same nine steps with
different field names. Those names are registry data now, so the steps live
here once:

    gather image inputs as NODE IDS
      -> reject what this model will not accept  (docs first, then live schema)
      -> render for approval / stop at --dry-run
      -> RECORD THE RUN                          (before submitting, so a
                                                  failure is still history)
      -> presign at the last moment              (never stored)
      -> create the prediction                   (this is what bills)
      -> poll                                    (never `Prefer: wait`)
      -> upload the output into the run
      -> close the run

Every invariant the two originals defended is defended here, and the places
where they legitimately differ — a video may be submitted without waiting, an
image may not be generated imageless by accident — are `KIND` below, not
branches scattered through the flow.

BINDINGS ARE NODE IDS
---------------------
`gather` resolves every image input to a node id, `record_request` stores those
ids, and a URL is refused twice — by `runs.check_bindings` before the request is
built and by the API when the record is written. A binding used to be an S3 key,
which any rename invalidated; the record now names the thing itself.

THERE IS NO EXCEPTION LEFT, AND THERE WAS ONE
---------------------------------------------
A pose plate is bound to the same field as the character's own images and its
POSITION in that list is cited by the prompt, so it could never be handled
somewhere else. While plates had no catalog node they travelled through `gather`
marked `shared:<key>`, stripped before the record was written and restored at
presign time — so a plate was sent and cited correctly and was *not* recorded,
which that marker's own comment called a real gap.

The gap is closed rather than narrowed: plates are ordinary nodes in the
library's `config/` folder, so `as_node` resolves one like any other name path
and a run records it. Everything the marker needed — `SHARED_PREFIX`,
`as_shared`, `is_shared`, `shared_key`, and `store.shared_presign` under it — is
deleted.
"""

import json
import os
import sys
import tempfile

from studio_pipeline.adapters import api
from studio_pipeline.adapters import entities
from studio_pipeline.adapters import replicate as RA
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
    `tests/cli_surface_reference.json`, which is a contract — but what they now
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

    Every reference has a row now, including a pose plate, so there is one
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
    plates, which had no id to record — the one thing a run could be shown and
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
    taken five 2.4 MiB plates — around 12 MiB — repeatedly and without
    complaint, so warning about them would be a false alarm on every reference
    shoot, and a warning that cries wolf is worse than none.

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
    holds exactly seven — the shape `shoot` produces — since binding that plus a
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


def preflight(entry: dict, payload: dict, bindings: dict, token: str) -> None:
    """Documented constraints first, then the live schema.

    Runs on --dry-run too, so an approved payload is a payload that submits.
    """
    model = entry["model"]
    _check_image_budget(entry, bindings)
    MS.check_denied(payload, entry, model)
    props, schemas = MS.fetch(model, token)
    alts: dict[str, dict] = {}
    if [k for k in list(payload) + list(bindings) if k not in props]:
        # Only on the error path — worth extra lookups to name the fix.
        for key, other in REG.of_kind(entry["kind"]).items():
            if key == entry["key"]:
                continue
            try:
                alts[key], _ = MS.fetch(other["model"], token)
            except MS.SchemaError:
                pass
    MS.check(payload, bindings, model, props, schemas, alternatives=alts)


# --------------------------------------------------------------------------
# 3. render — the approval view
# --------------------------------------------------------------------------

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
    endpoint = RA.predictions_endpoint(entry["model"])
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

def execute(entry: dict, payload: dict, bindings: dict, token: str, args) -> dict:
    """Run the submission and return the RUN RECORD.

    It returned an exit code, and every batch caller then went back for
    `<project>/latest` to find out which run it had just made — a lookup that is
    wrong the moment two runs land in one project close together, and that
    could not be right at all: a run has no name to be looked up by.
    Returning the record removes the question. Failure is still an exception, so
    the callers that only wanted "did it work" are unchanged.
    """
    kind = entry["kind"]
    d = defaults(kind)
    project = args.project          # the project record, resolved by the caller
    # **A FILENAME, NOT AN IDENTITY.** This used to be the run's slug, which
    # named the run, named its folder and named its outputs all at once. The run
    # and its folder are named by id now; what survives here is the only part
    # that was ever worth having — what the downloaded file is called.
    name = R.slugify(getattr(args, "name", None) or d["slug"])

    prompt_source = json.load(open(args.prompt_json)) if getattr(args, "prompt_json", None) else None
    # `--character` doubles as "resolve refs from" and "this run is of", which is
    # the same thing for `studio run`. A reference shoot resolves its own images
    # (seed photos, a pose plate) and so passes no `--character`, but the run is
    # still OF that character — and `runs find --character` is how that
    # association is read back. Hence the explicit override.
    characters = list(getattr(args, "record_characters", None) or args.character or [])
    try:
        record = R.record_request(
            project["id"], kind=kind, engine=entry["skill"],
            model=entry["model"], input=payload,
            # Node ids only. A pose plate is dropped here rather than stored as
            # a raw key, because a record that mixes the two addressing schemes
            # is exactly what the entity model exists to end — see the module
            # docstring for when this stops being lossy.
            bindings=recorded(bindings),
            characters=REFS.character_ids(characters),
            prompt_source=prompt_source)
    except R.RunError as e:
        raise SubmitError(f"refusing to record an invalid request: {e}")
    except REFS.RefError as e:
        raise SubmitError(f"refusing to record a run against an unknown character: {e}")
    run_id = record["id"]
    print(f"run {run_id}  (in {project['slug']})", file=sys.stderr)

    # Mint presigned URLs at the last possible moment; they are never stored.
    for f, val in bindings.items():
        payload[f] = ([presign(one) for one in val] if isinstance(val, list)
                      else presign(val))
    if bindings:
        print(f"minted presigned URL(s) for {sorted(bindings)}", file=sys.stderr)

    created = RA.create_prediction(entry["model"], payload, token)
    pid = created.get("id")
    if not pid:
        R.record_result(run_id, prediction_id=None, status="failed",
                        error="no prediction id returned")
        raise SubmitError(f"no prediction id returned: {json.dumps(created)[:400]}")

    if not (d["always_poll"] or getattr(args, "poll", False)):
        print(json.dumps({"run": run_id, "id": pid, "status": created.get("status")},
                         indent=2))
        print("not polling — re-run with --poll, or archive later with the prediction id.",
              file=sys.stderr)
        # The prediction id is recorded even though nothing waits for it: it is
        # the only handle on a video that is still rendering, and a run left at
        # `pending` forever is a row that lies about a submission that happened.
        #
        # `entities.patch_run`, not `runs.record_result` — that one closes a run:
        # it writes the response document and stamps `completed`, and neither is
        # true of a prediction still in flight.
        return entities.patch_run(run_id, status="running", prediction_id=pid)

    try:
        cur = RA.poll(pid, token, args.interval, args.timeout,
                      on_status=lambda s: print(f"  {s}", file=sys.stderr))
    except TimeoutError as e:
        R.record_result(run_id, prediction_id=pid, status="timeout", error=str(e))
        raise SubmitError(f"{e}; prediction {pid} may still be running.")

    if cur.get("status") != "succeeded":
        R.record_result(run_id, prediction_id=pid, status=cur.get("status"),
                        error=cur.get("error"))
        raise SubmitError(f"prediction {cur.get('status')}: {cur.get('error')}")

    out = cur.get("output")
    urls = [out] if isinstance(out, str) else list(out or [])
    if not urls:
        R.record_result(run_id, prediction_id=pid, status="succeeded",
                        error="no output returned")
        raise SubmitError("prediction succeeded but returned no output.")

    # --- the run OWNS its output; medium is an attribute, not a folder -------
    staged = tempfile.mkdtemp(prefix=d["tmp"])
    out_nodes = []
    for i, u in enumerate(urls, start=1):
        ext = os.path.splitext(u.split("?")[0])[1] or d["default_ext"]
        base = f"{name}{'' if len(urls) == 1 else f'-{i}'}{ext}"
        local = RA.download(u, os.path.join(staged, base))
        out_nodes.append(R.upload_output(run_id, local, base))
        if getattr(args, "dest", None):
            os.makedirs(args.dest, exist_ok=True)
            os.replace(local, os.path.join(args.dest, base))
        else:
            os.remove(local)

    closed = R.record_result(run_id, prediction_id=pid, status="succeeded",
                             outputs=out_nodes, source_urls=urls)
    print(json.dumps({
        "run": run_id, "runref": f"{run_id}#1", "model": entry["model"],
        "status": "succeeded", "outputs": out_nodes,
    }, indent=2))
    return closed
