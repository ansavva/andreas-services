"""A training run: rent a machine, hand it a job, take its weights.

The one run kind whose provider is not a model. `runpod-pod` entries
(`registry.RUNPOD_POD`) describe a trainer — today ai-toolkit on Wan 2.2 —
and a run against one is still a run: a draft with a plan and sends, a
submit that moves it to `pending`, a callback or a `reconcile` that closes it,
a cost. What differs is inside those steps, and it is all here so
`services/generate.py` stays about models:

    dispatch  make the output nodes, mint the grants, write the manifest,
              rent the pod                                   ── billing starts
    progress  confirm each checkpoint as the pod says it landed; stay running
    report    what the pod wrote into the bucket, for `reconcile`
    adopt     confirm the checkpoints and samples the pod uploaded as outputs
    release   terminate the pod, drop the manifest              ── billing stops

## The job travels as a manifest, and the manifest is not a record

The pod needs the dataset, captions, a place to put each checkpoint, and a
way to say it is done. Every one of those is a presigned URL, and hard rule
#3 says a presigned URL is never stored on a record — so the manifest is a
plain object at `training/<run>/job.json`, not a catalog node, minted for the
run's time cap and deleted by `release`. The pod fetches it once through the
single environment variable it is given.

## Outputs are nodes before they are files

The checkpoints land on the character — `<character>/models/` — because a
LoRA of a person is identity material, like `reference/`. The nodes are made
at dispatch, each with a PUT grant on its own blob key, so the pod writes
straight into the bucket and `adopt` only has to confirm what arrived. A
node whose file never came (a run stopped early, a failed one) is deleted at
close, so `models/` holds weights and nothing that looks like weights.

## A checkpoint is visible when it lands, not when the run ends

An empty node is hidden from the library until its size and checksum are on
the row, and a run trains for an hour or two while pairs land every few
minutes. So the pod's uploader POSTs a progress document — `IN_PROGRESS`,
the names uploaded so far — to the same signed callback URL after each PUT,
and `confirm_progress` confirms those files and appends them to the run's
`outputs` while the run stays `running`. Best-effort on the pod's side and
idempotent on this one: a lost progress call costs nothing but the wait for
the next, `reconcile` confirms whatever has landed when asked, and `adopt`
at close re-confirms the whole set and drops the rest exactly as before.

## A save point is a pair of weights and a strip of pictures

Weights are nothing to look at. The first real run (2000 steps, a pair every
250) produced sixteen files and no way to see the face emerge without making
a video run by hand against each pair — the wrong default for a learning
loop. So the trainer samples at every save point: `sample_prompts` puts the
subject in scenes the dataset does not contain, one still per prompt at a
fixed seed, and the pod files each beside its pair as
`<stem>_<step:09d>_sample_<i>.jpg` (the final step's unnumbered, like the
final pair) under `<character>/models/samples/`. A subfolder, because
`models/` is a list of weights a person reaches into, and thirty-two
pictures beside sixteen files made it a wall; the run page is where a
sample is read, beside its checkpoint. Same mechanism as the weights: a
node and a PUT grant per expected sample at dispatch, confirmed as it
lands, dropped at close if it never came. `sample_prompts: []` turns
sampling off.

ai-toolkit names a sample `<ms-since-epoch>__<step:09d>_<i>.jpg` — the
time is not knowable at dispatch, so the uploader renames on the way up;
`SAMPLE_FILE` is that pattern, read off the trainer's source.
"""

import json
import logging
import re
from datetime import datetime, timezone

from studio_core.clients import runpod_pods
from studio_core.clients.aws import s3
from studio_core.errors import NotFoundError, ValidationError
from studio_core.services import catalog, keys, layout, registry

logger = logging.getLogger(__name__)

MANIFEST_KEY = "training/{run}/job.json"
RESULT_KEY = "training/{run}/result.json"

#: Where a character's weights live, beside `reference/`.
MODELS_FOLDER = "models"
#: Where the samples go, under `models/`.
SAMPLES_FOLDER = "samples"

#: The default sample prompts: scenes a character dataset typically does NOT
#: contain, so a sample shows whether the face travels rather than whether
#: the trainer memorised a photo. `{trigger}` is the run's trigger.
SAMPLE_PROMPTS = [
    "{trigger}, cooking in a bright kitchen, medium shot",
    "{trigger}, walking down a city street at night, neon signs, waist-up",
    "{trigger}, in a dark suit and tie at a formal event, head and shoulders",
    "{trigger}, sitting on a beach at sunset, full body",
]

#: The plan's knobs, and what a plan that does not say gets. Mirrors the
#: registry entry's defaults; read here so the manifest never lacks a value.
DEFAULTS = {
    "steps": 2000, "save_every": 250, "rank": 32, "lr": 1e-4,
    "resolution": 768, "gpu": "a100", "cloud": "secure", "base": "i2v",
    "max_hours": 6,
    "sample_prompts": SAMPLE_PROMPTS, "sample_seed": 42, "sample_steps": 20,
}

EXPERTS = ("high", "low")

#: What ai-toolkit calls a sample, in the `samples/` folder beside the
#: weights: `<ms-since-epoch>__<step:09d>_<prompt index>.jpg`. Read off
#: `jobs/process/BaseSDTrainProcess.py` (`sample()`: `filename =
#: f"[time]_{step_num}_[count].{ext}"` with `step_num = f"_{step:09d}"`,
#: hence the double underscore) and `toolkit/config_modules.py`
#: (`GenerateImageConfig._get_path_no_ext`: `[time]` is `int(time.time() *
#: 1000)`, `[count]` the bare index because `save_image_atomic(img, i)`
#: passes no `max_count`; `SampleConfig.ext` defaults to `jpg`). Verified
#: against ostris/ai-toolkit `main` on 2026-09-19.
SAMPLE_FILE = re.compile(r"^\d+__(\d{9})_(\d+)\.jpg$")
SAMPLE_CONTENT_TYPE = "image/jpeg"

_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(value: str) -> str:
    return _SLUG.sub("-", (value or "").lower()).strip("-") or "lora"


def _knobs(payload: dict) -> dict:
    knobs = {**DEFAULTS, **{k: v for k, v in payload.items() if k in DEFAULTS}}
    knobs["trigger"] = payload.get("trigger")
    if not isinstance(knobs["trigger"], str) or not knobs["trigger"].strip():
        raise ValidationError("a training run needs a `trigger` — the token its captions start with")
    knobs["max_hours"] = max(1, min(int(knobs["max_hours"]), 12))
    prompts = knobs["sample_prompts"]
    if not isinstance(prompts, list) or not all(isinstance(p, str) and p.strip() for p in prompts):
        raise ValidationError("`sample_prompts` is a list of prompts, each naming `{trigger}` — or [] for no samples")
    # Substituted here, once, so the manifest says exactly what the pod will
    # render and the pod substitutes nothing.
    knobs["sample_prompts"] = [p.replace("{trigger}", knobs["trigger"]) for p in prompts]
    knobs["sample_seed"] = int(knobs["sample_seed"])
    knobs["sample_steps"] = max(1, int(knobs["sample_steps"]))
    return knobs


def save_points(steps: int, save_every: int) -> list[int]:
    """The step counts ai-toolkit writes a checkpoint at, before the final one."""
    if save_every <= 0:
        return []
    return [s for s in range(save_every, steps + 1, save_every) if s < steps]


def expected_files(stem: str, steps: int, save_every: int) -> list[str]:
    """Every file the trainer will write, by ai-toolkit's own naming.

    `<name>_<step:09d>` for a periodic save and bare `<name>` for the final
    one, each split into `_high_noise` / `_low_noise` because
    `split_multistage_loras` is on — the pair the inference endpoint takes.
    """
    names = []
    for step in save_points(steps, save_every):
        for expert in EXPERTS:
            names.append(f"{stem}_{step:09d}_{expert}_noise.safetensors")
    for expert in EXPERTS:
        names.append(f"{stem}_{expert}_noise.safetensors")
    return names


def sample_name(stem: str, step: int | None, index: int) -> str:
    """What studio calls a sample: `<stem>_<step:09d>_sample_<i>.jpg`, and
    `<stem>_sample_<i>.jpg` for the final step — the same shape as the pair
    it sits beside, so the run page files it by step off the name alone."""
    return f"{stem}_sample_{index}.jpg" if step is None else f"{stem}_{step:09d}_sample_{index}.jpg"


def expected_samples(stem: str, steps: int, save_every: int, prompts: list[str]) -> list[str]:
    """Every sample the trainer will write, by studio's naming.

    One per prompt at each periodic save and at the final step. ai-toolkit
    samples in the loop wherever it saves (`sample_every` is set to
    `save_every`) and once more after the loop at `steps`, which the
    uploader files as the unnumbered final set. No baseline at step 0:
    `skip_first_sample` is on, since the untrained model at the prompt is
    the evaluation's `lora_scale 0` run, not a checkpoint.
    """
    names = []
    for step in save_points(steps, save_every):
        names.extend(sample_name(stem, step, i) for i in range(len(prompts)))
    names.extend(sample_name(stem, None, i) for i in range(len(prompts)))
    return names


def _caption(trigger: str, node: dict) -> str:
    """The trigger first, then whatever the file's description says.

    The article's rule: a caption names the scene — wardrobe, pose, light,
    background — and never the face; the face is what the token learns. A
    file with no description trains on the token alone, which is allowed and
    said in the manifest so the person can see which ones.
    """
    description = (node.get("description") or "").strip()
    return f"{trigger}, {description}" if description else trigger


def dispatch(record: dict, entry: dict, payload: dict, bindings: dict, *, webhook: str | None) -> dict:
    """Rent the machine and hand it the job. **This is the call that bills.**

    Returns what `routes/runs.py` expects of a provider: `{id, status}` with
    the pod id as the prediction id.
    """
    knobs = _knobs(payload)
    dataset_field = registry.field(entry, "images.refs") or "dataset"
    dataset_nodes = bindings.get(dataset_field) or []
    if isinstance(dataset_nodes, str):
        dataset_nodes = [dataset_nodes]
    if len(dataset_nodes) < 5:
        raise ValidationError(
            f"a training run needs at least 5 dataset images; got {len(dataset_nodes)}"
        )
    characters = record.get("characters") or []
    if len(characters) != 1:
        raise ValidationError("a training run is OF exactly one character — pass --character once")
    character = catalog.entity(catalog.ENTITY_CHARACTER, characters[0])
    models = layout.folder_under(character["root"], MODELS_FOLDER)

    run_id = record["id"]
    # **The file says whose it is.** `<character>-<trigger>-<run>`: a weights
    # file is opened from a folder listing, a sends line, a download — places
    # with no run beside it — and `ohwx-pt-2d9a376a` told a person the trigger
    # and a run id, not the character. The name is the character's slug at
    # dispatch; the run id keeps two trainings of one character apart.
    stem = _slug(f"{character.get('name') or 'character'}-{knobs['trigger']}-{run_id[4:12]}")
    ttl = knobs["max_hours"] * 3600 + 3600

    dataset = []
    for node_id in dataset_nodes:
        node = catalog.node(node_id)
        if not node.get("blob_key"):
            raise ValidationError(f"dataset node {node_id} has no bytes behind it")
        dataset.append({
            "name": node.get("name") or f"{node_id}.png",
            "url": s3.presign(node["blob_key"], expires_in=ttl),
            "caption": _caption(knobs["trigger"], node),
        })

    outputs: dict[str, str] = {}
    grants: dict[str, str] = {}
    owner = catalog.blob_owner_for(models["node_id"])
    for name in expected_files(stem, knobs["steps"], knobs["save_every"]):
        node = catalog.create_node(models["node_id"], name, catalog.KIND_FILE, owner=owner)
        outputs[name] = node["node_id"]
        grants[name] = s3.presign_put_unsized(
            node["blob_key"], content_type="application/octet-stream", expires_in=ttl)
    samples = expected_samples(stem, knobs["steps"], knobs["save_every"], knobs["sample_prompts"])
    if samples:
        # The folder is made only when there is something to put in it.
        folder = layout.folder_under(models["node_id"], SAMPLES_FOLDER)
        for name in samples:
            node = catalog.create_node(folder["node_id"], name, catalog.KIND_FILE, owner=owner)
            outputs[name] = node["node_id"]
            # The grant signs the content type, so the uploader must PUT
            # `image/jpeg` — it reads the type off the extension.
            grants[name] = s3.presign_put_unsized(
                node["blob_key"], content_type=SAMPLE_CONTENT_TYPE, expires_in=ttl)

    manifest_key = MANIFEST_KEY.format(run=run_id)
    result_key = RESULT_KEY.format(run=run_id)
    manifest_url = s3.presign(manifest_key, expires_in=ttl)

    # The pod first, so the manifest can carry what only the pod knows — its
    # id and its hourly rate — and the pod waits for the manifest to appear.
    pod = runpod_pods.create_pod(
        name=f"studio-train-{run_id[4:12]}",
        gpu=knobs["gpu"], cloud=knobs["cloud"],
        env={"STUDIO_JOB_URL": manifest_url},
        start_cmd=["bash", "-lc", BOOT],
    )
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "run": run_id,
        "pod": {"id": pod["id"], "rate": pod.get("costPerHr"), "created_at": created_at},
        "trainer": entry.get("model"),
        **{k: knobs[k] for k in ("trigger", "steps", "save_every", "rank", "lr",
                                 "resolution", "base", "max_hours",
                                 "sample_prompts", "sample_seed", "sample_steps")},
        "stem": stem,
        "dataset": dataset,
        "outputs": grants,
        "result_url": s3.presign_put_unsized(result_key, content_type="application/json", expires_in=ttl),
        "callback": webhook,
        "script": JOB_SCRIPT,
    }
    s3.put_text(manifest_key, json.dumps(manifest).encode(), "application/json")

    catalog.update_project_entity(
        catalog.ENTITY_RUN, record,
        {"payload": {**(record.get("payload") or {}),
                     "training": {"stem": stem, "outputs": outputs, "character": character["id"],
                                  "pod": manifest["pod"], "dataset": len(dataset)}}},
    )
    logger.info("Rented pod %s for training run %s (%d images, %d steps)",
                pod["id"], run_id, len(dataset), knobs["steps"])
    return {"id": pod["id"], "status": "IN_QUEUE", "costPerHr": pod.get("costPerHr")}


def report(record: dict) -> dict:
    """What the pod said — the same document a callback delivers, read from
    the bucket. Falls back to asking whether the machine is alive."""
    key = RESULT_KEY.format(run=record["id"])
    try:
        body = s3.get_body(key, 1 << 20)
    except NotFoundError:
        return runpod_pods.get_prediction(record.get("prediction_id") or "", model=record.get("model") or "")
    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        return {"id": record.get("prediction_id"), "status": "FAILED",
                "error": "the pod's result document is not JSON"}
    if not isinstance(result, dict):
        return {"id": record.get("prediction_id"), "status": "FAILED",
                "error": "the pod's result document is not an object"}
    return result


def adopt_outputs(record: dict, prediction: dict, status: str, error) -> tuple[list[str], str, str | None]:
    """Confirm the checkpoints and samples the pod uploaded; drop the rest.

    The pod PUT straight onto the nodes' blob keys, so each reported name is
    checked against the bucket and its size and checksum recorded. Nodes made
    at dispatch for files that never came are deleted whatever the outcome —
    a `models/` folder must not hold an empty file that looks like weights.
    """
    mapping = _mapping(record)
    uploaded = set(runpod_pods.output_urls(prediction)) if status == "succeeded" else set()

    outputs: list[str] = []
    for name, node_id in mapping.items():
        if name not in uploaded:
            _drop(node_id)
            continue
        if _confirm(node_id) is None:
            logger.warning("Pod reported %s uploaded but %s is empty", name, node_id)
            _drop(node_id)
            continue
        outputs.append(node_id)

    if status == "succeeded" and not outputs:
        return [], "failed", "the pod reported success but no checkpoint reached the bucket"
    return outputs, status, error


def confirm_progress(record: dict, prediction: dict) -> dict:
    """Confirm the checkpoints that have landed so far. The run stays `running`.

    Reached with a progress document from the pod — `output.uploaded` names
    what its uploader has PUT — or with a bare "the machine is alive" answer
    from `reconcile`, which names nothing; then every unconfirmed node is
    tried. A name already on the run's `outputs` is skipped, a name whose
    object is not in the bucket yet is skipped silently (the next call gets
    it), and nothing is dropped: only the close knows which nodes will never
    fill. Returns the run, rewritten only when something new was confirmed.
    """
    from studio_core.services import render  # circular at import time; not at call time
    mapping = _mapping(record)
    confirmed = list(record.get("outputs") or [])
    names = runpod_pods.output_urls(prediction) or list(mapping)
    added = []
    for name in names:
        node_id = mapping.get(name)
        if not node_id or node_id in confirmed:
            continue
        node = _confirm(node_id)
        if node is None:
            continue
        added.append(node_id)
        # A sample is a picture, and a picture on a running run draws now —
        # so it gets its poster now, as an upload does, not at the close.
        if render.wants_poster(node):
            render.queue_poster(record["lib"], node_id)
    if not added:
        return record
    outputs = confirmed + added
    # The listing row's thumbnail: the first picture to land, since a
    # weights file draws nothing — and the first file of any kind until one
    # does, so a run with sampling off still has a row.
    names = {node_id: name for name, node_id in mapping.items()}
    is_picture = lambda node_id: keys.kind(names.get(node_id, "")) == "image"  # noqa: E731
    listing = {}
    if not any(is_picture(node_id) for node_id in confirmed):
        pictures = [node_id for node_id in added if is_picture(node_id)]
        if pictures:
            listing["thumb"] = pictures[0]
        elif not confirmed:
            listing["thumb"] = added[0]
    logger.info("Run %s: %d of %d files landed", record["id"], len(outputs), len(mapping))
    return catalog.update_project_entity(catalog.ENTITY_RUN, record, {"outputs": outputs}, listing)


def _mapping(record: dict) -> dict[str, str]:
    """Expected file name → the node made for it at dispatch."""
    training = (record.get("payload") or {}).get("training") or {}
    return training.get("outputs") or {}


def _confirm(node_id: str) -> dict | None:
    """Record the size and checksum of what the pod PUT onto this node's key.

    The confirmed node, or None when there is nothing there yet. Idempotent:
    a node confirmed twice carries the same values twice. The content type
    is what the pod's PUT declared — `image/jpeg` for a sample, since the
    grant signed it — so a sample is an image to every tile that reads it.
    """
    try:
        node = catalog.node(node_id)
        metadata = s3.head(node["blob_key"])
    except NotFoundError:
        return None
    return catalog.set_blob(
        node_id, node["blob_key"],
        size=metadata.get("ContentLength", 0),
        content_type=metadata.get("ContentType") or "application/octet-stream",
        checksum=s3.content_hash(metadata),
    )


def _drop(node_id: str) -> None:
    try:
        catalog.delete_node(node_id)
    except Exception as exc:  # noqa: BLE001 — a leftover empty node is not worth a redrive
        logger.warning("Could not drop unfilled output node %s: %s", node_id, exc)


def release(record: dict) -> None:
    """Stop the meter and forget the grants. Called once the row is closed."""
    pod_id = record.get("prediction_id")
    if pod_id:
        try:
            runpod_pods.terminate(pod_id)
        except Exception as exc:  # noqa: BLE001 — the run is closed; the pod is a cleanup
            logger.error("Could not terminate pod %s for run %s: %s — terminate it by hand",
                         pod_id, record["id"], exc)
    try:
        s3.delete([MANIFEST_KEY.format(run=record["id"])])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not delete the manifest for %s: %s", record["id"], exc)


# ── what the pod runs ────────────────────────────────────────────────────────

#: The image's start command is replaced by this. It waits for the manifest —
#: written after the pod exists, because the manifest carries the pod's id
#: and rate — then runs the script the manifest carries. Nothing of studio is
#: baked into the image; the job arrives by URL.
BOOT = (
    "for i in $(seq 1 120); do curl -fsS \"$STUDIO_JOB_URL\" -o /tmp/job.json && break; sleep 5; done; "
    "test -s /tmp/job.json || { echo 'no job manifest'; exit 1; }; "
    "python3 -c \"import json;open('/tmp/job.sh','w').write(json.load(open('/tmp/job.json'))['script'])\" "
    "&& bash /tmp/job.sh"
)

#: The job. Bash around three Python passes: fetch the dataset and write the
#: ai-toolkit config; upload checkpoints as the trainer writes them, telling
#: the callback URL after each one; write the result and call back.
#: Everything the pod learns is in the manifest and everything it says goes
#: to the bucket — it holds no credential.
JOB_SCRIPT = r'''#!/usr/bin/env bash
set -uo pipefail
export PYTHONUNBUFFERED=1
# A pod restarts its container when the command exits, and the container disk
# survives the restart. Without this guard a finished job ran again: the trainer
# found its final checkpoint, exited 0 in seconds, and the result was re-written
# and re-sent with a bigger bill every six minutes until studio terminated the
# pod. Reported once, the machine holds idle for studio to terminate.
if [ -f /workspace/.reported ]; then echo "already reported; holding"; exec sleep infinity; fi
mkdir -p /workspace/dataset /workspace/output
cd /app/ai-toolkit

python3 - <<'PYEOF'
import json, pathlib, urllib.request, yaml
m = json.load(open("/tmp/job.json"))
ds = pathlib.Path("/workspace/dataset")
for item in m["dataset"]:
    p = ds / item["name"]
    urllib.request.urlretrieve(item["url"], p)
    p.with_suffix(".txt").write_text(item["caption"])
i2v = m.get("base", "i2v") == "i2v"
# Samples at every save point, one still per prompt, or none at all. The
# prompts arrive with the trigger already in them. `skip_first_sample`: no
# step-0 baseline, it is not a checkpoint. Field names are ai-toolkit's
# `SampleConfig` (toolkit/config_modules.py); `guidance_scale` is left at
# its default.
prompts = list(m.get("sample_prompts") or [])
cfg = {"job": "extension", "config": {"name": m["stem"], "process": [{
    "type": "sd_trainer", "training_folder": "/workspace/output", "device": "cuda:0",
    "network": {"type": "lora", "linear": m["rank"], "linear_alpha": m["rank"],
                "split_multistage_loras": True},
    "save": {"dtype": "float16", "save_every": m["save_every"], "max_step_saves_to_keep": 100},
    "datasets": [{"folder_path": "/workspace/dataset", "caption_ext": "txt",
                  "caption_dropout_rate": 0.05, "num_frames": 1, "resolution": [m["resolution"]]}],
    "train": {"batch_size": 1, "steps": m["steps"], "gradient_accumulation": 1,
              "train_unet": True, "train_text_encoder": False, "gradient_checkpointing": True,
              "noise_scheduler": "flowmatch", "timestep_type": "linear",
              "optimizer": "adamw8bit", "lr": m["lr"], "optimizer_params": {"weight_decay": 1e-4},
              "dtype": "bf16", "switch_boundary_every": 10, "cache_text_embeddings": True,
              "disable_sampling": not prompts, "skip_first_sample": True},
    "model": {"name_or_path": "Wan-AI/Wan2.2-I2V-A14B-Diffusers" if i2v else "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
              "arch": "wan22_14b_i2v" if i2v else "wan22_14b",
              "quantize": False, "low_vram": False,
              "model_kwargs": {"train_high_noise": True, "train_low_noise": True}},
    "sample": {"sampler": "flowmatch", "sample_every": m["save_every"] if prompts else 10**9,
               "sample_start_step": 0, "width": m["resolution"], "height": m["resolution"],
               "num_frames": 1, "prompts": prompts, "neg": "", "seed": m.get("sample_seed", 42),
               "walk_seed": False, "sample_steps": m.get("sample_steps", 20), "format": "jpg"},
}]}}
yaml.safe_dump(cfg, open("/tmp/train.yaml", "w"))
open("/tmp/uploader.py", "w").write(r"""
import json, os, pathlib, re, sys, time, urllib.request
m = json.load(open("/tmp/job.json"))
grants = m["outputs"]; out = pathlib.Path("/workspace/output") / m["stem"]
done = set(); sizes = {}
# ai-toolkit names a sample `<ms>__<step:09d>_<i>.jpg` (BaseSDTrainProcess.sample);
# studio's name for it is `<stem>_<step:09d>_sample_<i>.jpg`, unnumbered at
# the final step like the final pair. The grant is under studio's name.
SAMPLE = re.compile(r"^\d+__(\d{9})_(\d+)\.jpg$")
def studio_name(p):
    if p.parent.name != "samples": return p.name
    match = SAMPLE.match(p.name)
    if not match: return None
    step, index = int(match.group(1)), int(match.group(2))
    if step >= int(m["steps"]): return f"{m['stem']}_sample_{index}.jpg"
    return f"{m['stem']}_{step:09d}_sample_{index}.jpg"
def put(p, name):
    data = p.read_bytes()
    kind = "image/jpeg" if name.endswith(".jpg") else "application/octet-stream"
    req = urllib.request.Request(grants[name], data=data, method="PUT",
                                 headers={"Content-Type": kind})
    urllib.request.urlopen(req, timeout=600).read()
def progress():
    # Best effort: what has landed so far, so studio can show it before the
    # end. A failure here costs nothing — the final report names everything.
    if not m.get("callback"): return
    body = json.dumps({"id": m["pod"]["id"], "status": "IN_PROGRESS",
                       "output": {"uploaded": sorted(done)}}).encode()
    try:
        req = urllib.request.Request(m["callback"], data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as exc:
        print("progress callback failed", exc, flush=True)
def sweep(final=False):
    if not out.is_dir(): return
    files = sorted(out.glob("*_noise.safetensors")) + sorted((out / "samples").glob("*.jpg"))
    for p in files:
        name = studio_name(p)
        if not name or name in done or name not in grants: continue
        size = p.stat().st_size
        if not final and sizes.get(name) != size:
            sizes[name] = size; continue  # wait until the size holds still
        try:
            put(p, name); done.add(name); print("uploaded", p.name, "as", name, size, flush=True)
        except Exception as exc:
            print("upload failed", p.name, exc, flush=True); continue
        progress()
    json.dump(sorted(done), open("/tmp/uploaded.json", "w"))
if sys.argv[1:] == ["final"]:
    sweep(final=True); sweep(final=True)
else:
    while not os.path.exists("/tmp/train.exit"):
        sweep(); time.sleep(30)
""")
PYEOF

MAX_SECONDS=$(python3 -c "import json;print(int(json.load(open('/tmp/job.json'))['max_hours']*3600))")
( timeout ${MAX_SECONDS}s python run.py /tmp/train.yaml > /workspace/train.log 2>&1; echo $? > /tmp/train.exit ) &
python3 /tmp/uploader.py &
wait
python3 /tmp/uploader.py final

python3 - <<'PYEOF'
import json, time, urllib.request
from datetime import datetime, timezone
m = json.load(open("/tmp/job.json"))
code = int(open("/tmp/train.exit").read().strip() or "1")
try: uploaded = json.load(open("/tmp/uploaded.json"))
except Exception: uploaded = []
try: tail = open("/workspace/train.log", errors="replace").read()[-6000:]
except Exception: tail = ""
created = datetime.fromisoformat(m["pod"]["created_at"])
seconds = (datetime.now(timezone.utc) - created).total_seconds()
rate = m["pod"].get("rate") or 0
ok = code == 0 and bool(uploaded)
result = {"id": m["pod"]["id"], "status": "COMPLETED" if ok else "FAILED",
          "error": None if ok else (f"trainer exited {code}" if code else "no checkpoint was uploaded"),
          "output": {"uploaded": uploaded, "cost": round(rate * seconds / 3600, 4),
                     "seconds": round(seconds), "rate": rate, "exit_code": code,
                     "steps": m["steps"], "log_tail": tail}}
body = json.dumps(result).encode()
req = urllib.request.Request(m["result_url"], data=body, method="PUT",
                             headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=120).read()
if m.get("callback"):
    for attempt in range(6):
        try:
            req = urllib.request.Request(m["callback"], data=body, method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=60).read(); break
        except Exception as exc:
            print("callback failed", attempt, exc, flush=True); time.sleep(20)
PYEOF

# Reported. Hold the container so Runpod does not restart the job — studio's
# close terminates the pod, and `reconcile` does the same if the callback was
# lost. The meter runs while this holds, which is why the report went first.
touch /workspace/.reported
exec sleep infinity
'''
