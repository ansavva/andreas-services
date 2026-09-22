"""The model registry: what each engine accepts, and what it will refuse.

`models.json` sits beside this module and is the single source of truth for
every studio-* tool — which image fields a model has, how many references it
takes, which extensions it will accept, what its prompt ceiling is, and the
snapshot of its live Replicate schema.

## Why it is here and not in the pipeline

**It was the pipeline's, and this service kept a hand-written partial copy of
it.** `routes/characters.py` carried

    ENGINE_CAPS = {"kling": 7, "seedance": 9, "nano-banana": 14}

— three of nine model families, consulted by `GET /api/characters/<id>/selection`
to refuse an over-cap reference selection. So `gpt-image-2`, which studio's own
docs name as the default for character frames, had **no cap server-side at all**,
and neither did `veo-3.1`, `grok-imagine-video` or `image-upscale`. A selection
aimed at any of them came back unrefused however large it was, while the CLI
refused it correctly off the real registry. Two answers to "how many references
may this model see", disagreeing, with only one of them auditable after the fact.

`routes/runs.py` argued against exactly this in a comment — *"a second copy of it
here is a second answer to what a model accepts"* — and was right; the copy
existed anyway, one file over. The fix is not to delete the caps but to make this
service read the real thing.

## What follows from the move

The registry is now part of the deployed contract, which has two consequences
worth stating rather than discovering:

* **A new model needs a deploy before production can use it.** `studio
  add-model` writes this file, and `studio models refresh` rewrites the
  snapshots; both are repo edits, reviewed in a PR, and the API serves what
  shipped. Against a local dev API the change is live immediately, because
  `dev-up.sh` runs this code from source.
* **The pipeline reads it through `GET /api/models`** rather than off disk, so
  there is one copy at runtime as well as one in the repo.

Nothing here fetches a live schema. `snapshot` is what `models refresh`
recorded; the authoritative check against the provider's own schema happens at
submit time, where a payload can still be refused before anything bills.
"""

from __future__ import annotations

import functools
import json
import pathlib

from studio_core.errors import NotFoundError

PATH = pathlib.Path(__file__).resolve().parent.parent / "models.json"


class RegistryError(Exception):
    """The registry is missing, malformed, or was asked for an unknown model."""


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    """Every entry, keyed by registry name, in file order.

    Cached for the life of the Lambda container: the file ships in the image and
    cannot change under a running process, so re-reading it per request would be
    a syscall per `GET /api/characters/<id>/selection` for a value that is
    frozen at build time. `_load.cache_clear()` exists for the tests.
    """
    try:
        data = json.loads(PATH.read_text())
    except FileNotFoundError as exc:
        raise RegistryError(f"registry not found at {PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{PATH} is not valid JSON: {exc}") from exc

    models = data.get("models")
    if not isinstance(models, dict) or not models:
        raise RegistryError(f"{PATH} has no `models` object")
    return models


def all() -> dict[str, dict]:
    """Every entry, keyed by registry name, each carrying its own `key`."""
    return {key: {**entry, "key": key} for key, entry in _load().items()}


def keys() -> list[str]:
    return sorted(_load())


def _aliases() -> dict[str, str]:
    out = {}
    for key, entry in _load().items():
        out[key] = key
        for alias in entry.get("aliases") or []:
            out[alias] = key
    return out


def get(name: str) -> dict:
    """One entry by registry key or alias, with its key attached.

    Raises `NotFoundError` rather than `RegistryError` because every caller here
    is a route, and an unknown model is a 404 about the request rather than a
    500 about the file.
    """
    resolved = _aliases().get(name)
    if resolved is None:
        raise NotFoundError(name)
    return {**_load()[resolved], "key": resolved}


def find(name: str) -> dict | None:
    """`get`, but `None` for an unknown model — for callers deciding rather than serving."""
    resolved = _aliases().get(name)
    return None if resolved is None else {**_load()[resolved], "key": resolved}


def by_model_id(model_id: str) -> dict | None:
    """One entry by model id (`owner/name`, `runpod/<endpoint>`, `fal/<endpoint>` or
    `openrouter/<slug>`), or `None`."""
    for key, entry in _load().items():
        if entry.get("model") == model_id:
            return {**entry, "key": key}
    return None


#: The providers an entry may name. `replicate` is what an entry with no
#: `provider` key means — every entry written before there was a second one.
#: `runpod-pod` is not a hosted model at all: it is a machine studio rents by
#: the hour and drives with a job manifest — the training provider. See
#: `services/training.py`.
REPLICATE, RUNPOD, FAL, OPENROUTER, RUNPOD_POD = "replicate", "runpod", "fal", "openrouter", "runpod-pod"
PROVIDERS = (REPLICATE, RUNPOD, FAL, OPENROUTER, RUNPOD_POD)

#: The run kind a `runpod-pod` entry produces. Its outputs are weights, not
#: pictures, and they are filed on the character rather than the run.
TRAINING = "training"


def provider_of(entry: dict | None) -> str:
    """Which provider runs this entry: its `provider` key, else `replicate`.

    A registry key rather than an inference from the model id's prefix, so an
    entry says what it is and a reader does not have to know that `runpod/`,
    `fal/` and `openrouter/` are not Replicate owners. `runpod.is_model`,
    `fal.is_model` and `openrouter.is_model` exist for the one place that has
    only the id — a run record older than the `provider` field.
    """
    got = (entry or {}).get("provider") or REPLICATE
    if got not in PROVIDERS:
        raise RegistryError(
            f"{(entry or {}).get('key', '?')} names provider {got!r}; "
            f"it is one of {PROVIDERS}"
        )
    return got


def field(entry: dict, path: str, default=None):
    """Read a dotted path out of an entry: `field(e, "images.max_refs")`.

    A stored `null` reads as the default, which is the whole reason callers use
    this instead of a `.get()` chain: `max_refs: null` means "no cap", and the
    caller asking wants to be told "no cap" once rather than distinguish absent
    from null at every site.
    """
    cursor = entry
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return default
        cursor = cursor[part]
    return default if cursor is None else cursor


def accepts_ext(entry: dict) -> set[str]:
    """The image extensions this model will take."""
    return set(field(entry, "images.accepts_ext", []) or [])


def lora_fields(entry: dict) -> set[str]:
    """The inputs that take LoRA weights, or an empty set where the model has none.

    An entry names them under `loras` by slot — `high` and `low` for Wan 2.2's
    two-stage denoiser, which loads a separate adapter for each — and each
    slot is a field taking a LIST of `{path, scale}` objects. The slot names
    are the pipeline's business (they become `--lora-high-key` and friends);
    this service only needs to know which fields hold weights so `dispatch`
    can shape them and `_unsigned_input` can put the node ids back.
    """
    loras = entry.get("loras") or {}
    return {v for k, v in loras.items() if k not in ("accepts_ext", "scale_param") and isinstance(v, str)}


def elements(entry: dict) -> dict | None:
    """How this model takes SUBJECTS, or None where it takes a flat list.

    An element is one subject as one object — a frontal view, its other
    angles, optionally a clip, optionally a bound voice — and the prompt cites
    it positionally (`@Element1`). The entry names the field it goes in and
    what each part of it is called:

        {"field": "elements", "frontal": "frontal_image_url",
         "refs": "reference_image_urls", "clip": "video_url",
         "voice": "voice_id", "max": 4, "max_images_each": 4}

    **Only Kling on fal has this so far, and the shape is registry data
    anyway**, because the alternative is a branch reading `if model.startswith
    ("fal/fal-ai/kling")` inside `dispatch` — which is the per-model code the
    registry exists to not have.
    """
    block = entry.get("elements")
    return block if isinstance(block, dict) and block.get("field") else None


def voice_field(entry: dict) -> str | None:
    """The model input a VOICE SAMPLE binds to, or None where it takes none.

    Not the field the id is written into — that is `elements.voice`, one level
    down inside the object. This is the field a *send* names, so that a bound
    sample is an ordinary `SEND#` row with a role, checked and displayed like
    every other bound file rather than being a second kind of attachment.
    """
    return field(entry, "audio.voice")


def voice_accepts_ext(entry: dict) -> set[str]:
    """The file types this model will clone a voice from.

    Wider than `keys.AUDIO_EXTENSIONS` on purpose: Kling reads a voice out of
    an `.mp4` as happily as out of a `.wav`, and refusing one because the
    library files it under a different tile would be studio's rule rather than
    the model's.
    """
    return set(field(entry, "audio.accepts_ext", []) or [])


def voice_endpoint(entry: dict) -> str | None:
    """Where a sample is registered before a run can cite it.

    A provider model id (`fal/fal-ai/kling-video/create-voice`), so the same
    `clients/` seam that runs a generation runs this too, and so the cached id
    on a node can be keyed by the thing that issued it.
    """
    return field(entry, "audio.create")


def output_grant(entry: dict) -> dict | None:
    """The upload a worker of ours wants minted into its request, or None.

    A public endpoint hosts its own output and answers a URL. A worker studio
    rents (`worker/wan22/`) has nowhere to put a file, so the entry says
    `output_grant: {put, get, content_type, ext}` and `dispatch` mints two
    presigned URLs on one scratch key — a PUT the worker uploads to under the
    `put` field name, a GET it hands back as `output.result` under the `get`
    name — so the closing path files the clip exactly as it files a public
    endpoint's. Both names default to what the wan22 handler reads.
    """
    grant = entry.get("output_grant")
    if not grant:
        return None
    return {
        "put": grant.get("put") or "output_url",
        "get": grant.get("get") or "result_url",
        "content_type": grant.get("content_type") or "application/octet-stream",
        "ext": grant.get("ext") or "",
    }


def lora_scale_param(entry: dict) -> str | None:
    """The plan param carrying the LoRA strength, or None. **Studio's own name.**

    The endpoint wants a `scale` inside every `{path, scale}` object and has no
    top-level field for it; a person wants one number. So the entry's `input`
    block declares it — `lora_scale` — as if it were the model's, the create
    sheet and the CLI treat it like any other setting, and `dispatch` folds it
    into each object and never sends the name. Registry data rather than a
    constant so another provider can spell it differently.
    """
    return field(entry, "loras.scale_param")


def of_kind(kind: str) -> dict[str, dict]:
    """Every entry of one kind, keyed by registry name."""
    return {key: entry for key, entry in all().items() if entry.get("kind") == kind}


def images() -> dict[str, dict]:
    return of_kind("image")


def videos() -> dict[str, dict]:
    return of_kind("video")


def reference_cap(name: str) -> int | None:
    """How many reference images `name` may be shown, or `None` for no cap.

    **The function `ENGINE_CAPS` was standing in for**, and it differs from that
    dict in more than coverage. The old lookup matched on a *prefix* so that
    `nano-banana-pro` and `nano-banana-2` shared one number; this resolves the
    actual entry, so two members of a family may legitimately differ — and an
    alias resolves too, which the prefix match got right only by accident.

    An unknown model is `None` rather than an error: `?engine=` is an optional
    hint on a read route, and a caller that did not say what it was feeding
    cannot be told it fed too much.
    """
    entry = find(name)
    return None if entry is None else field(entry, "images.max_refs")
