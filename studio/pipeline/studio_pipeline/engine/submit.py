"""submit.py — ONE submission lifecycle, for every model in the registry.

The image and video submitters were ~816 lines doing the same nine steps with
different field names. Those names are registry data now, so the steps live
here once:

    gather image inputs as S3 KEYS
      -> reject what this model will not accept  (docs first, then live schema)
      -> render for approval / stop at --dry-run
      -> RECORD THE REQUEST                      (before submitting, so a
                                                  failure is still history)
      -> presign at the last moment              (never stored)
      -> create the prediction                   (this is what bills)
      -> poll                                    (never `Prefer: wait`)
      -> archive the output into the run
      -> record the result

Every invariant the two originals defended is defended here, and the places
where they legitimately differ — a video may be submitted without waiting, an
image may not be generated imageless by accident — are `KIND` below, not
branches scattered through the flow.
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

from studio_pipeline.engine import model_schema as MS  # noqa: E402
from studio_pipeline.engine import refs as REFS  # noqa: E402
from studio_pipeline.engine import registry as REG  # noqa: E402
from studio_pipeline.engine import replicate_api as RA  # noqa: E402
from studio_pipeline.store import runs as R  # noqa: E402

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
# 1. gather — every image input, as S3 keys, never URLs
# --------------------------------------------------------------------------

def gather(entry: dict, s3, args) -> dict:
    """Resolve all image inputs to S3 keys and bind them to this model's fields.

    Returns {field: key | [keys]}. Order matters for the reference list: an
    explicitly named edit target first, then curated identity, then chained run
    outputs, then the working pool, then raw keys.
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
    # runs live under a project now, so defaulting to the character name would
    # look for history in a folder that has none.
    project = args.project
    if start_field:
        if start_run:
            bindings[start_field] = R.resolve_output_keys(
                s3, start_run, project, kinds=exts)[0]
        elif start_key:
            bindings[start_field] = start_key
        if end_run or end_key:
            if start_field not in bindings:
                raise SubmitError(
                    f"a last frame requires a first frame ({end_field} needs {start_field}).")
            bindings[end_field] = (
                R.resolve_output_keys(s3, end_run, project, kinds=exts)[0]
                if end_run else end_key
            )

    # --- the reference / input list ----------------------------------------
    slots = [int(s) for s in args.slots.split(",")] if getattr(args, "slots", None) else None
    pick = [x.strip() for x in args.pick.split(",")] if getattr(args, "pick", None) else None
    tags = [t.strip() for t in args.pick_tag.split(",")] if getattr(args, "pick_tag", None) else None
    cap = imgs.get("max_refs")
    keys: list[str] = []
    if getattr(args, "image_run", None):
        keys += R.resolve_output_keys(s3, args.image_run, project, kinds=exts)
    for character in (args.character or []):
        keys += REFS.character_ref_keys(character, slots, pick, tags,
                                        cap=cap, cap_name=entry["key"])
    for ref in getattr(args, "ref_run", None) or []:
        keys += R.resolve_output_keys(s3, ref, project, kinds=exts)
    if getattr(args, "input", None):
        keys += REFS.project_input_keys(project, args.input)
    keys += getattr(args, "key", None) or []

    seen: set[str] = set()
    keys = [k for k in keys if not (k in seen or seen.add(k))]  # de-dupe, keep order

    if keys:
        if start_field in bindings and imgs.get("start_excludes_refs"):
            raise SubmitError(
                f"{entry['key']}: `{start_field}` and `{refs_field}` are mutually exclusive.\n"
                f"       A start frame already carries identity — drop "
                f"--character/--ref-run, or drop the start frame."
            )
        bad = [k for k in keys if os.path.splitext(k)[1].lower() not in exts]
        if bad:
            raise SubmitError(
                f"{entry['key']} accepts only {sorted(exts)}; incompatible: {bad}\n"
                f"       convert with: uv run .claude/skills/studio-s3/scripts/s3_convert.py "
                f"--for {entry['key']} …"
            )
        if cap and len(keys) > cap:
            raise SubmitError(
                f"{entry['key']} accepts at most {cap} images; got {len(keys)}.\n"
                f"       Narrow the reference selection (--pick / --pick-tag, or the "
                f"character's default_set) rather than hoping the extras are dropped.")
        bindings[refs_field] = keys

    return bindings


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

def preflight(entry: dict, payload: dict, bindings: dict, token: str) -> None:
    """Documented constraints first, then the live schema.

    Runs on --dry-run too, so an approved payload is a payload that submits.
    """
    model = entry["model"]
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

    Image inputs appear as the S3 key that will be signed into the field at
    submit time: the signed URL is ~2 KB of noise and expires, so the key is
    the reviewable form.
    """
    endpoint = RA.predictions_endpoint(entry["model"])
    if as_json:
        return json.dumps({
            "run": run, "model": entry["model"], "endpoint": endpoint,
            "input": payload, "bindings": bindings,
        }, indent=2, ensure_ascii=False)
    return R.render_payload(run, entry["model"], endpoint, payload, bindings)


# --------------------------------------------------------------------------
# 4-9. execute — record, presign, submit, poll, archive, record
# --------------------------------------------------------------------------

def execute(entry: dict, payload: dict, bindings: dict, s3, token: str, args) -> int:
    kind = entry["kind"]
    d = defaults(kind)
    project = args.project
    run_id = R.new_run_id(args.slug)
    run = f"{project}/{run_id}"

    prompt_source = json.load(open(args.prompt_json)) if getattr(args, "prompt_json", None) else None
    try:
        R.record_request(s3, project, run_id, kind=kind, engine=entry["skill"],
                         model=entry["model"], input=payload, bindings=bindings,
                         characters=args.character or [], prompt_source=prompt_source)
    except R.RunError as e:
        raise SubmitError(f"refusing to record an invalid request: {e}")
    print(f"run {run}", file=sys.stderr)

    # Mint presigned URLs at the last possible moment; they are never stored.
    for f, val in bindings.items():
        payload[f] = (R.presign(s3, val, args.expires) if isinstance(val, list)
                      else R.presign(s3, [val], args.expires)[0])
    if bindings:
        print(f"minted presigned URL(s) for {sorted(bindings)}", file=sys.stderr)

    created = RA.create_prediction(entry["model"], payload, token)
    pid = created.get("id")
    if not pid:
        R.record_result(s3, project, run_id, prediction_id=None, status="failed",
                        error="no prediction id returned")
        raise SubmitError(f"no prediction id returned: {json.dumps(created)[:400]}")

    if not (d["always_poll"] or getattr(args, "poll", False)):
        print(json.dumps({"run": run, "id": pid, "status": created.get("status")}, indent=2))
        print("not polling — re-run with --poll, or archive later with the prediction id.",
              file=sys.stderr)
        return 0

    try:
        cur = RA.poll(pid, token, args.interval, args.timeout,
                      on_status=lambda s: print(f"  {s}", file=sys.stderr))
    except TimeoutError as e:
        R.record_result(s3, project, run_id, prediction_id=pid, status="timeout", error=str(e))
        raise SubmitError(f"{e}; prediction {pid} may still be running.")

    if cur.get("status") != "succeeded":
        R.record_result(s3, project, run_id, prediction_id=pid, status=cur.get("status"),
                        error=cur.get("error"))
        raise SubmitError(f"prediction {cur.get('status')}: {cur.get('error')}")

    out = cur.get("output")
    urls = [out] if isinstance(out, str) else list(out or [])
    if not urls:
        R.record_result(s3, project, run_id, prediction_id=pid, status="succeeded",
                        error="no output returned")
        raise SubmitError("prediction succeeded but returned no output.")

    # --- the run OWNS its output; medium is an attribute, not a folder -------
    staged = tempfile.mkdtemp(prefix=d["tmp"])
    out_keys = []
    for i, u in enumerate(urls, start=1):
        ext = os.path.splitext(u.split("?")[0])[1] or d["default_ext"]
        base = f"{R.slugify(args.slug)}{'' if len(urls) == 1 else f'-{i}'}{ext}"
        local = RA.download(u, os.path.join(staged, base))
        out_keys.append(R.upload_output(s3, project, run_id, local, base))
        if getattr(args, "dest", None):
            os.makedirs(args.dest, exist_ok=True)
            os.replace(local, os.path.join(args.dest, base))
        else:
            os.remove(local)

    R.record_result(s3, project, run_id, prediction_id=pid, status="succeeded",
                    outputs=out_keys, source_urls=urls)
    print(json.dumps({
        "run": run, "runref": f"{run}#1", "model": entry["model"],
        "status": "succeeded", "outputs": out_keys,
    }, indent=2))
    return 0
