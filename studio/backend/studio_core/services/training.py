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

## An I2V sample is a photo re-rendered, not a scene imagined

The `i2v` base conditions every frame on a first image, at training and at
sampling alike, and a text-only sample crashed the first run that tried one
(`The size of tensor a (36) must match the size of tensor b (16)`, $0.66).
Read off ostris/ai-toolkit at 0.13.12 (`8bf12e47`), identical on `main`:

- `extensions_built_in/diffusion_models/wan22/wan22_14b_i2v_model.py`
  `generate_single_image`: with `gen_config.ctrl_img` set it opens the
  image, resizes it to the sample's size, prepares 16-channel latents and
  hands `add_first_frame_conditioning(...)` (`toolkit/models/wan21/wan_utils.py`)
  the result — 16 latent + 4 mask + 16 encoded-frame channels, 36 in all.
  With no `ctrl_img` it passes `latents=None`.
- `wan22_pipeline.py` `__call__`: 36-channel latents are split — the first 16
  denoise, the other 20 ride along as conditioning re-concatenated before
  each transformer call. `None` makes it `prepare_latents` with
  `transformer.config.in_channels`, which is 36 for the I2V transformer, and
  the 16-channel noise prediction then fails inside `scheduler.step`. That
  is the crash, and the control image is the only thing that avoids it.
- `num_frames: 1` is fine with a control image: `generate_single_image`
  snaps it to `((n - 1) // 4) * 4 + 1 = 1`, `add_first_frame_conditioning`
  builds a one-frame condition and a mask of `2 ** sum(temperal_downsample)`
  = 4 channels off one latent frame — the same call the trainer's own
  `get_noise_prediction` makes on every single-frame training batch.
- `toolkit/config_modules.py` `GenerateImageConfig._process_prompt_string`
  splits a prompt on `--` and reads `--ctrl_img <path>`, `--w`, `--h` and
  the rest off it; `jobs/process/BaseSDTrainProcess.py` `sample()` builds
  one `GenerateImageConfig(prompt=...)` per entry and says "it will
  autoparse the prompt". `SDTrainer.cache_sample_prompts` parses the same
  way, so `cache_text_embeddings: True` caches the bare prompt.

So on `i2v` every sample prompt carries `--ctrl_img /workspace/dataset/<image>`,
the images dealt round-robin from the dataset the pod downloaded, and the
manifest and the run say which photo each prompt re-renders (`samples`).
What comes back is that photo through the pair: the prompt steers little.
A clean, faithful frame says the pair still renders its subject; drift,
colour shift or a smeared face says the pair has damaged the model. Whether
the face travels to a new scene is the evaluation's question, on video.
`t2v` samples are text-only, as before.

## Three trainers, one run shape

`TRAINERS` says what each `runpod-pod` entry rents and what it leaves, keyed
by the entry's model id. Two run ai-toolkit off the same image and job
script — the script reads `arch` off the manifest and writes the config
that arch wants — and the third runs musubi-tuner off a plain PyTorch image,
because ai-toolkit has no HunyuanVideo arch. What a trainer writes differs
in one thing that every reader of the run has to know: **whether a
checkpoint is a pair or a file.** Wan 2.2 is two experts, so a save point
is `<stem>_<step>_high_noise` + `_low_noise`; LTX-2.3 and HunyuanVideo are
one transformer, so a save point is `<stem>_<step>.safetensors` — studio's
own name, which the uploader gives a musubi file on the way up (musubi
writes `<stem>-step<8 digits>`). `expected_files` takes the experts, and the
run page groups by step off the name either way.

Verified 2026-09-20 against ostris/ai-toolkit `8bf12e4` (0.13.12, the image
pinned in `clients/runpod_pods.py`): `LTX23Model.arch == "ltx2.3"`,
`toolkit/models/registry.py` names `Lightricks/LTX-2.3/ltx-2.3-22b-dev.safetensors`
with `quantize` and `quantize_te` on as its defaults, and
`generate_single_image` handles `num_frames == 1` as a still through the
text-to-video pipeline — so an LTX sample is text-only and shows whether the
face travels. The LoRA is saved in the original (ComfyUI) key layout
(`lora_keys_use_comfy_prefix`, `convert_lora_weights_before_save`), which is
the layout fal's `ltx-2.3-22b/*/lora` endpoints load. The HunyuanVideo job
is written against kohya-ss/musubi-tuner `4e7c714` (2026-09-16) and its
`docs/hunyuan_video.md`, and has **not** run on a pod: no hosted endpoint
loads a HunyuanVideo LoRA into image-to-video, so studio cannot use what it
would train yet, and the budget went to LTX.
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

#: Wan 2.2's two denoising experts, each its own LoRA file. A single-model
#: trainer has none: `experts=()` and a checkpoint is one file.
EXPERTS = ("high", "low")

#: Wan 2.2 trains against one of two bases; the other trainers have one model
#: for both modes, so `base` is not a knob of theirs and stays `None`.
WAN22 = "runpod-pod/ai-toolkit-wan22-14b"
LTX23 = "runpod-pod/ai-toolkit-ltx23-22b"
HUNYUAN = "runpod-pod/musubi-hunyuan-video"

#: The trainers, by the registry entry's model id. `arch` is what the job
#: script switches on; `experts` is how a checkpoint is named; `image` is
#: the pod's; `script` is the job; `defaults` overlay `DEFAULTS` for the
#: knobs a trainer spells differently; `samples` says whether the job can
#: draw a still at each save point at all.
TRAINERS: dict[str, dict] = {
    WAN22: {"arch": "wan22", "experts": EXPERTS, "image": None, "script": None,
            "defaults": {}, "samples": True},
    LTX23: {"arch": "ltx23", "experts": (), "image": None, "script": None,
            "defaults": {"base": None, "steps": 1500}, "samples": True},
    HUNYUAN: {"arch": "hunyuan", "experts": (), "image": "runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04",
              "script": "musubi", "defaults": {"base": None, "sample_prompts": [], "lr": 2e-4},
              "samples": False},
}


def trainer_of(entry: dict) -> dict:
    """What this entry rents and leaves — `TRAINERS` by model id, with the
    entry's own `defaults` laid over the trainer's for the knobs a plan may
    not say (the registry says `gpu: h100` for the LTX trainer; a plan the
    API was handed without one gets that, not the module's `a100`)."""
    model = entry.get("model") or ""
    try:
        trainer = TRAINERS[model]
    except KeyError:
        raise ValidationError(f"{model} is not a trainer this service knows how to drive") from None
    own = {k: v for k, v in (entry.get("defaults") or {}).items() if k in DEFAULTS}
    return {**trainer, "defaults": {**own, **trainer["defaults"]}}


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


def _knobs(payload: dict, trainer: dict = TRAINERS[WAN22]) -> dict:
    defaults = {**DEFAULTS, **trainer["defaults"]}
    knobs = {**defaults, **{k: v for k, v in payload.items() if k in defaults}}
    knobs["trigger"] = payload.get("trigger")
    if not isinstance(knobs["trigger"], str) or not knobs["trigger"].strip():
        raise ValidationError("a training run needs a `trigger` — the token its captions start with")
    knobs["max_hours"] = max(1, min(int(knobs["max_hours"]), 12))
    prompts = knobs["sample_prompts"]
    if not isinstance(prompts, list) or not all(isinstance(p, str) and p.strip() for p in prompts):
        raise ValidationError("`sample_prompts` is a list of prompts, each naming `{trigger}` — or [] for no samples")
    if prompts and not trainer["samples"]:
        raise ValidationError("this trainer draws no samples: pass `sample_prompts: []`")
    # ai-toolkit reads `--<flag>` off a sample prompt (`GenerateImageConfig`
    # splits on `--`), and the job appends its own; a prompt carrying one
    # would be cut there, silently.
    if any("--" in p for p in prompts):
        raise ValidationError("a sample prompt cannot contain `--`: the trainer reads it as a flag")
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


def expected_files(stem: str, steps: int, save_every: int,
                   experts: tuple[str, ...] = EXPERTS) -> list[str]:
    """Every file the trainer will write, by ai-toolkit's own naming.

    `<name>_<step:09d>` for a periodic save and bare `<name>` for the final
    one. With `experts` (Wan 2.2), each is split into `_high_noise` /
    `_low_noise` because `split_multistage_loras` is on — the pair the
    inference endpoint takes. With none (LTX-2.3, HunyuanVideo) a save point
    is the one file, which is also the name the uploader gives a musubi
    checkpoint on the way up.
    """
    names = []
    for step in save_points(steps, save_every):
        if experts:
            names.extend(f"{stem}_{step:09d}_{expert}_noise.safetensors" for expert in experts)
        else:
            names.append(f"{stem}_{step:09d}.safetensors")
    if experts:
        names.extend(f"{stem}_{expert}_noise.safetensors" for expert in experts)
    else:
        names.append(f"{stem}.safetensors")
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


def sample_records(prompts: list[str], dataset_names: list[str], base: str) -> list[dict]:
    """What sample `i` is, at every save point: its prompt, and on the `i2v`
    base the dataset photo it re-renders — `ctrl_img`, dealt round-robin
    over the dataset in manifest order, the rule the job applies on the pod
    (`JOB_SCRIPT`'s config pass reads the same `dataset[*].name` list).
    `None` on `t2v`, whose samples are text-only.
    """
    records = []
    for index, prompt in enumerate(prompts):
        ctrl = dataset_names[index % len(dataset_names)] if base == "i2v" and dataset_names else None
        records.append({"index": index, "prompt": prompt, "ctrl_img": ctrl})
    return records


def _caption(trigger: str, node: dict) -> str:
    """The trigger first, then whatever the file's description says.

    The article's rule: a caption names the scene — wardrobe, pose, light,
    background — and never the face; the face is what the token learns. A
    file with no description trains on the token alone, which is allowed and
    said in the manifest so the person can see which ones.
    """
    description = (node.get("description") or "").strip()
    return f"{trigger}, {description}" if description else trigger


def preflight(record: dict, entry: dict, payload: dict, bindings: dict) -> tuple[dict, list[str]]:
    """What the job needs, checked without writing or spending: the knobs,
    at least five dataset images, exactly one character.

    Called from `generate.prepare` **before the run moves to `pending`** —
    a refusal here leaves a draft. `dispatch` runs it again, since it is
    what it reads; raising there would leave `pending` with no pod behind
    it, the state that reads as "went out and never answered".
    """
    knobs = _knobs(payload, trainer_of(entry))
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
    return knobs, list(dataset_nodes)


def dispatch(record: dict, entry: dict, payload: dict, bindings: dict, *, webhook: str | None) -> dict:
    """Rent the machine and hand it the job. **This is the call that bills.**

    Returns what `routes/runs.py` expects of a provider: `{id, status}` with
    the pod id as the prediction id.

    **A failure part-way takes back what came before it.** The output nodes
    are made before the rent and the manifest is written after it, so a
    `create_pod` that failed — Runpod answered `500 create pod: This machine
    does not have the resources` on 2026-09-20 — left empty nodes under the
    character's `models/`, and a write failing after the rent would have
    left a billing pod and a manifest the same way. Everything from the
    first node on is inside one `try`, and `_abandon` undoes whatever it
    had reached: the pod terminated, the manifest deleted, the nodes and
    any folder made here dropped, so the character's tree is as it was.
    The run is the route's to put back — it reverts to `draft` on the
    exception this re-raises.
    """
    knobs, dataset_nodes = preflight(record, entry, payload, bindings)
    trainer = trainer_of(entry)
    character = catalog.entity(catalog.ENTITY_CHARACTER, record["characters"][0])

    run_id = record["id"]
    # What this call has made so far, for `_abandon`. Folders deepest first.
    made_nodes: list[str] = []
    made_folders: list[str] = []
    pod: dict | None = None
    manifest_key = MANIFEST_KEY.format(run=run_id)
    written = False
    try:
        models = _folder_made(character["root"], MODELS_FOLDER, made_folders)
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
        for name in expected_files(stem, knobs["steps"], knobs["save_every"], trainer["experts"]):
            node = catalog.create_node(models["node_id"], name, catalog.KIND_FILE, owner=owner)
            made_nodes.append(node["node_id"])
            outputs[name] = node["node_id"]
            grants[name] = s3.presign_put_unsized(
                node["blob_key"], content_type="application/octet-stream", expires_in=ttl)
        samples = expected_samples(stem, knobs["steps"], knobs["save_every"], knobs["sample_prompts"])
        if samples:
            # The folder is made only when there is something to put in it.
            folder = _folder_made(models["node_id"], SAMPLES_FOLDER, made_folders)
            for name in samples:
                node = catalog.create_node(folder["node_id"], name, catalog.KIND_FILE, owner=owner)
                made_nodes.append(node["node_id"])
                outputs[name] = node["node_id"]
                # The grant signs the content type, so the uploader must PUT
                # `image/jpeg` — it reads the type off the extension.
                grants[name] = s3.presign_put_unsized(
                    node["blob_key"], content_type=SAMPLE_CONTENT_TYPE, expires_in=ttl)

        result_key = RESULT_KEY.format(run=run_id)
        manifest_url = s3.presign(manifest_key, expires_in=ttl)

        # The pod first, so the manifest can carry what only the pod knows — its
        # id and its hourly rate — and the pod waits for the manifest to appear.
        pod = runpod_pods.create_pod(
            name=f"studio-train-{run_id[4:12]}",
            gpu=knobs["gpu"], cloud=knobs["cloud"],
            env={"STUDIO_JOB_URL": manifest_url},
            start_cmd=["bash", "-lc", BOOT],
            image=trainer["image"],
        )
        created_at = datetime.now(timezone.utc).isoformat()
        sample_plan = sample_records(knobs["sample_prompts"], [d["name"] for d in dataset], knobs["base"])
        manifest = {
            "run": run_id,
            "pod": {"id": pod["id"], "rate": pod.get("costPerHr"), "created_at": created_at},
            "trainer": entry.get("model"),
            "arch": trainer["arch"],
            "experts": list(trainer["experts"]),
            **{k: knobs[k] for k in ("trigger", "steps", "save_every", "rank", "lr",
                                     "resolution", "base", "max_hours",
                                     "sample_prompts", "sample_seed", "sample_steps")},
            "stem": stem,
            "dataset": dataset,
            "samples": sample_plan,
            "outputs": grants,
            "result_url": s3.presign_put_unsized(result_key, content_type="application/json", expires_in=ttl),
            "callback": webhook,
            "script": JOB_SCRIPTS[trainer["script"]],
        }
        s3.put_text(manifest_key, json.dumps(manifest).encode(), "application/json")
        written = True

        catalog.update_project_entity(
            catalog.ENTITY_RUN, record,
            {"payload": {**(record.get("payload") or {}),
                         # `samples` stays on the run: the manifest that also
                         # carries it is deleted at close, and which photo a
                         # sample re-rendered is read after that.
                         "training": {"stem": stem, "outputs": outputs, "character": character["id"],
                                      "pod": manifest["pod"], "dataset": len(dataset),
                                      "samples": sample_plan}}},
        )
    except Exception:
        _abandon(run_id, pod, manifest_key if written else None, made_nodes, made_folders)
        raise
    logger.info("Rented pod %s for training run %s (%d images, %d steps)",
                pod["id"], run_id, len(dataset), knobs["steps"])
    return {"id": pod["id"], "status": "IN_QUEUE", "costPerHr": pod.get("costPerHr")}


def _folder_made(parent_id: str, name: str, made_folders: list[str]) -> dict:
    """`layout.folder_under`, noting whether this call made the folder.

    A `models/` that already holds a character's weights is never dropped
    on a failed rent; one made a moment ago for this run is, so a failure
    leaves the character's tree exactly as it found it. Deepest first in
    `made_folders`, so `samples/` goes before `models/`.
    """
    try:
        return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])
    except NotFoundError:
        folder = layout.folder_under(parent_id, name)
        made_folders.insert(0, folder["node_id"])
        return folder


def _abandon(run_id: str, pod: dict | None, manifest_key: str | None,
             made_nodes: list[str], made_folders: list[str]) -> None:
    """Take back what a failed `dispatch` had reached. **The pod first**: it
    is the one thing here that bills. Every step is best-effort and logged,
    because the exception that got us here is the one worth raising."""
    if pod and pod.get("id"):
        try:
            runpod_pods.terminate(pod["id"])
        except Exception as exc:  # noqa: BLE001 — the rent failed after the pod; terminate by hand
            logger.error("Could not terminate pod %s after a failed dispatch of run %s: %s "
                         "— terminate it by hand", pod["id"], run_id, exc)
    if manifest_key:
        try:
            s3.delete([manifest_key])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not delete the manifest for %s: %s", run_id, exc)
    for node_id in made_nodes:
        _drop(node_id)
    for node_id in made_folders:
        _drop(node_id)
    logger.warning("Dispatch of training run %s failed; dropped %d output nodes it had made",
                   run_id, len(made_nodes))


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

#: What every job ends with, whatever trained: the uploader's final sweep,
#: the result document PUT to the bucket and POSTed to the callback, then
#: the hold. Its own constant so the two job scripts share it verbatim.
#:
#: A pod restarts its container when the command exits, and the container
#: disk survives the restart. Without the `.reported` guard at the top of
#: each script a finished job ran again: the trainer found its final
#: checkpoint, exited 0 in seconds, and the result was re-written and re-sent
#: with a bigger bill every six minutes until studio terminated the pod.
#: Reported once, the machine holds idle for studio to terminate.
REPORT = r'''python3 /tmp/uploader.py final

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

#: The uploader both jobs run beside the trainer: sweep the output folder,
#: PUT each finished file on its grant, tell the callback after each one.
#: Written to `/tmp/uploader.py` by the job's first Python pass. What it
#: knows about naming: ai-toolkit's sample name (`<ms>__<step:09d>_<i>.jpg`),
#: which it files under studio's; and musubi's checkpoint name
#: (`<stem>-step<8 digits>`), which it files as `<stem>_<step:09d>` — the
#: single-file shape `expected_files` promised. A pair file is already
#: named as studio expects and passes through.
UPLOADER = r'''
import json, os, pathlib, re, subprocess, sys, time, urllib.request
m = json.load(open("/tmp/job.json"))
grants = m["outputs"]; out = pathlib.Path("/workspace/output") / m["stem"]
done = set(); sizes = {}
# ai-toolkit names a sample `<ms>__<step:09d>_<i>.jpg` (BaseSDTrainProcess.sample);
# studio's name for it is `<stem>_<step:09d>_sample_<i>.jpg`, unnumbered at
# the final step like the final pair. The grant is under studio's name.
SAMPLE = re.compile(r"^\d+__(\d{9})_(\d+)\.jpg$")
# musubi-tuner names a periodic save `<stem>-step<8 digits>` (train_utils.STEP_FILE_NAME)
# and the last one `<stem>`; studio's name is `<stem>_<step:09d>` / `<stem>`.
MUSUBI = re.compile(r"^" + re.escape(m["stem"]) + r"-step(\d{8})\.safetensors$")
# Wan 2.2 writes a pair per save point; a one-model trainer writes one file.
WEIGHTS = "*_noise.safetensors" if m.get("experts", ["high", "low"]) else "*.safetensors"
def studio_name(p):
    if p.parent.name == "samples":
        match = SAMPLE.match(p.name)
        if not match: return None
        step, index = int(match.group(1)), int(match.group(2))
        if step >= int(m["steps"]): return f"{m['stem']}_sample_{index}.jpg"
        return f"{m['stem']}_{step:09d}_sample_{index}.jpg"
    match = MUSUBI.match(p.name)
    if match:
        step = int(match.group(1))
        if step >= int(m["steps"]): return f"{m['stem']}.safetensors"
        return f"{m['stem']}_{step:09d}.safetensors"
    return p.name
def convert(p):
    # A musubi LoRA is in sd-scripts' key layout; `--target other` rewrites
    # it to the diffusers/ComfyUI layout every loader outside musubi reads.
    if m.get("arch") != "hunyuan" or p.suffix != ".safetensors": return p
    target = pathlib.Path("/tmp/converted") / p.name
    target.parent.mkdir(exist_ok=True)
    subprocess.run([sys.executable, "/workspace/musubi-tuner/src/musubi_tuner/convert_lora.py",
                    "--input", str(p), "--output", str(target), "--target", "other"], check=True)
    return target
def put(p, name):
    data = convert(p).read_bytes()
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
    files = sorted(out.glob(WEIGHTS)) + sorted((out / "samples").glob("*.jpg"))
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
'''

#: The ai-toolkit job — Wan 2.2 and LTX-2.3. Bash around three Python
#: passes: fetch the dataset and write the ai-toolkit config for the
#: manifest's `arch`; upload checkpoints as the trainer writes them, telling
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
arch = m.get("arch", "wan22")
i2v = arch == "wan22" and m.get("base", "i2v") == "i2v"
# Samples at every save point, one still per prompt, or none at all. The
# prompts arrive with the trigger already in them. `skip_first_sample`: no
# step-0 baseline, it is not a checkpoint. Field names are ai-toolkit's
# `SampleConfig` (toolkit/config_modules.py); `guidance_scale` is left at
# its default.
prompts = list(m.get("sample_prompts") or [])
if i2v and prompts:
    # The I2V base samples from an image or not at all: without one,
    # wan22_pipeline prepares 36-channel latents against a 16-channel
    # prediction and the scheduler crashes (the trainer's first sample, the
    # first time). `--ctrl_img <path>` on the prompt is how ai-toolkit's
    # GenerateImageConfig takes the first frame (toolkit/config_modules.py,
    # `_process_prompt_string`; wan22_14b_i2v_model.generate_single_image
    # reads `gen_config.ctrl_img`). The photos are the dataset's, dealt
    # round-robin in manifest order — the same rule the manifest's
    # `samples` records — so each prompt re-renders one real photo through
    # the pair. `--w`/`--h` keep the photo's aspect: the sampler resizes the
    # control image to the sample's size, and a square would squash a face
    # into something likeness cannot be read off. Multiples of 16, Wan 2.2's
    # bucket divisibility.
    names = [item["name"] for item in m["dataset"]]
    def fit(path, size):
        try:
            from PIL import Image
            w, h = Image.open(path).size
        except Exception:
            return None
        scale = size / max(w, h)
        return max(16, int(w * scale) // 16 * 16), max(16, int(h * scale) // 16 * 16)
    flagged = []
    for i, prompt in enumerate(prompts):
        name = names[i % len(names)]
        box = fit(ds / name, m["resolution"])
        size = f" --w {box[0]} --h {box[1]}" if box else ""
        flagged.append(f"{prompt}{size} --ctrl_img /workspace/dataset/{name}")
        print("sample", i, "re-renders", name, flush=True)
    prompts = flagged
if arch == "wan22":
    model = {"name_or_path": "Wan-AI/Wan2.2-I2V-A14B-Diffusers" if i2v else "Wan-AI/Wan2.2-T2V-A14B-Diffusers",
             "arch": "wan22_14b_i2v" if i2v else "wan22_14b",
             "quantize": False, "low_vram": False,
             "model_kwargs": {"train_high_noise": True, "train_low_noise": True}}
    network = {"type": "lora", "linear": m["rank"], "linear_alpha": m["rank"],
               "split_multistage_loras": True}
    train = {"timestep_type": "linear", "switch_boundary_every": 10}
    sample = {}
else:
    # LTX-2.3 22B, the mono checkpoint (DiT, both VAEs, vocoder, connectors
    # in one file) and the Gemma 3 text encoder the arch names for itself.
    # `quantize` + `quantize_te` are the trainer's own defaults for this arch
    # (toolkit/models/registry.py): 22B in bf16 is 44 GB and Gemma 12B is 24
    # more, which an 80 GB card does not hold beside activations; the LoRA
    # itself trains in bf16 either way. `timestep_type: weighted` is the
    # arch's default too. One transformer, so no expert split: a save point
    # is one file. Samples are text-only stills (`num_frames: 1` is the still
    # path in ltx2.py's generate_single_image), at the guidance the arch's
    # registry names for it.
    model = {"name_or_path": "Lightricks/LTX-2.3/ltx-2.3-22b-dev.safetensors",
             "arch": "ltx2.3", "quantize": True, "quantize_te": True, "low_vram": False}
    network = {"type": "lora", "linear": m["rank"], "linear_alpha": m["rank"]}
    train = {"timestep_type": "weighted"}
    sample = {"guidance_scale": 3.0}
cfg = {"job": "extension", "config": {"name": m["stem"], "process": [{
    "type": "sd_trainer", "training_folder": "/workspace/output", "device": "cuda:0",
    "network": network,
    "save": {"dtype": "float16", "save_every": m["save_every"], "max_step_saves_to_keep": 100},
    "datasets": [{"folder_path": "/workspace/dataset", "caption_ext": "txt",
                  "caption_dropout_rate": 0.05, "num_frames": 1, "resolution": [m["resolution"]],
                  **({"cache_latents_to_disk": True} if arch != "wan22" else {})}],
    "train": {"batch_size": 1, "steps": m["steps"], "gradient_accumulation": 1,
              "train_unet": True, "train_text_encoder": False, "gradient_checkpointing": True,
              "noise_scheduler": "flowmatch",
              "optimizer": "adamw8bit", "lr": m["lr"], "optimizer_params": {"weight_decay": 1e-4},
              "dtype": "bf16", "cache_text_embeddings": True,
              "disable_sampling": not prompts, "skip_first_sample": True, **train},
    "model": model,
    "sample": {"sampler": "flowmatch", "sample_every": m["save_every"] if prompts else 10**9,
               "sample_start_step": 0, "width": m["resolution"], "height": m["resolution"],
               "num_frames": 1, "prompts": prompts, "neg": "", "seed": m.get("sample_seed", 42),
               "walk_seed": False, "sample_steps": m.get("sample_steps", 20), "format": "jpg", **sample},
}]}}
yaml.safe_dump(cfg, open("/tmp/train.yaml", "w"))
open("/tmp/uploader.py", "w").write(r"""''' + UPLOADER + r'''""")
PYEOF

MAX_SECONDS=$(python3 -c "import json;print(int(json.load(open('/tmp/job.json'))['max_hours']*3600))")
( timeout ${MAX_SECONDS}s python run.py /tmp/train.yaml > /workspace/train.log 2>&1; echo $? > /tmp/train.exit ) &
python3 /tmp/uploader.py &
wait
''' + REPORT

#: The musubi-tuner job — HunyuanVideo, which ai-toolkit has no arch for.
#: A plain PyTorch image, so the job installs the trainer first. Then the
#: trainer's own three stages (docs/hunyuan_video.md): cache the VAE latents,
#: cache the text-encoder outputs, train — the DiT is the official
#: `mp_rank_00_model_states.pt`, the text encoders ComfyUI's repackaged
#: files, all from ungated repos. Steps rather than epochs so `save_every`
#: means what it means on the other trainers. No sampling: musubi's sampler
#: needs the text encoders resident beside the DiT and its own prompt file
#: format, and nothing downstream loads this LoRA yet — so the entry's
#: `sample_prompts` is `[]` and `_knobs` refuses anything else.
#:
#: **Not yet run on a pod.** Written against musubi-tuner `4e7c714`; the
#: fake pod covers what studio does with it, not what the trainer does.
MUSUBI_JOB_SCRIPT = r'''#!/usr/bin/env bash
set -uo pipefail
export PYTHONUNBUFFERED=1
if [ -f /workspace/.reported ]; then echo "already reported; holding"; exec sleep infinity; fi
mkdir -p /workspace/dataset /workspace/output /workspace/models /workspace/cache
cd /workspace
if [ ! -d musubi-tuner ]; then git clone --depth 1 https://github.com/kohya-ss/musubi-tuner.git; fi
cd musubi-tuner
pip install -q -e . "huggingface_hub>=0.34" pyyaml

python3 - <<'PYEOF'
import json, pathlib, urllib.request
from huggingface_hub import hf_hub_download
m = json.load(open("/tmp/job.json"))
ds = pathlib.Path("/workspace/dataset")
for item in m["dataset"]:
    p = ds / item["name"]
    urllib.request.urlretrieve(item["url"], p)
    p.with_suffix(".txt").write_text(item["caption"])
models = "/workspace/models"
for repo, name in [("tencent/HunyuanVideo", "hunyuan-video-t2v-720p/transformers/mp_rank_00_model_states.pt"),
                   ("tencent/HunyuanVideo", "hunyuan-video-t2v-720p/vae/pytorch_model.pt"),
                   ("Comfy-Org/HunyuanVideo_repackaged", "split_files/text_encoders/llava_llama3_fp16.safetensors"),
                   ("Comfy-Org/HunyuanVideo_repackaged", "split_files/text_encoders/clip_l.safetensors")]:
    hf_hub_download(repo_id=repo, filename=name, local_dir=models)
    print("fetched", name, flush=True)
# musubi's dataset config (docs/dataset_config.md): one image folder with
# caption files beside the images, bucketed to the run's resolution.
r = int(m["resolution"])
open("/tmp/dataset.toml", "w").write(
    "[general]\nresolution = [%d, %d]\ncaption_extension = \".txt\"\nbatch_size = 1\n"
    "enable_bucket = true\nbucket_no_upscale = false\n\n"
    "[[datasets]]\nimage_directory = \"/workspace/dataset\"\ncache_directory = \"/workspace/cache\"\n" % (r, r))
open("/tmp/uploader.py", "w").write(r"""''' + UPLOADER + r'''""")
PYEOF

M=/workspace/models
python3 src/musubi_tuner/cache_latents.py --dataset_config /tmp/dataset.toml \
  --vae $M/hunyuan-video-t2v-720p/vae/pytorch_model.pt --vae_chunk_size 32 --vae_tiling \
  > /workspace/train.log 2>&1 || { echo 1 > /tmp/train.exit; }
python3 src/musubi_tuner/cache_text_encoder_outputs.py --dataset_config /tmp/dataset.toml \
  --text_encoder1 $M/split_files/text_encoders/llava_llama3_fp16.safetensors \
  --text_encoder2 $M/split_files/text_encoders/clip_l.safetensors --batch_size 16 \
  >> /workspace/train.log 2>&1 || { echo 1 > /tmp/train.exit; }

if [ ! -f /tmp/train.exit ]; then
MAX_SECONDS=$(python3 -c "import json;print(int(json.load(open('/tmp/job.json'))['max_hours']*3600))")
read STEM STEPS SAVE RANK LR < <(python3 -c "import json;m=json.load(open('/tmp/job.json'));print(m['stem'],m['steps'],m['save_every'],m['rank'],m['lr'])")
( timeout ${MAX_SECONDS}s accelerate launch --num_cpu_threads_per_process 1 --mixed_precision bf16 \
    src/musubi_tuner/hv_train_network.py \
    --dit $M/hunyuan-video-t2v-720p/transformers/mp_rank_00_model_states.pt \
    --dataset_config /tmp/dataset.toml --sdpa --mixed_precision bf16 \
    --optimizer_type adamw8bit --learning_rate $LR --gradient_checkpointing \
    --max_data_loader_n_workers 2 --persistent_data_loader_workers \
    --network_module networks.lora --network_dim $RANK \
    --timestep_sampling shift --discrete_flow_shift 7.0 \
    --max_train_steps $STEPS --save_every_n_steps $SAVE --seed 42 \
    --output_dir /workspace/output/$STEM --output_name $STEM >> /workspace/train.log 2>&1; echo $? > /tmp/train.exit ) &
python3 /tmp/uploader.py &
wait
fi
''' + REPORT

#: The job each trainer hands its pod, by `TRAINERS[...]["script"]`.
JOB_SCRIPTS = {None: JOB_SCRIPT, "musubi": MUSUBI_JOB_SCRIPT}
