"""Load and parameterize the ComfyUI workflow graphs in assets/workflows/.

Each graph is stored in ComfyUI API format with well-known node ids; this
module owns which ids carry the knobs. Change a workflow's structure and this
is the one file that must agree with it.
"""

import copy
import json

from lora_lab import ASSETS_DIR

WORKFLOWS = ASSETS_DIR / "workflows"

# Node ids inside the stored graphs. Kept here, not scattered.
PROMPT_NODE = "6"       # CLIPTextEncode (positive)
SEED_NODE = "25"        # RandomNoise / KSampler seed carrier
LATENT_NODE = "27"      # EmptySD3LatentImage (width/height)
SAVE_NODE = "9"         # SaveImage (filename_prefix)
PULID_IMAGE_NODE = "40" # LoadImage (subject reference) — expand graph only
LORA_NODE = "50"        # LoraLoaderModelOnly — validate graph only

# Video graphs. The two engines sample through different node classes —
# SamplerCustom for LTX, KSampler for Wan — so they cannot share a seed key.
# They do share the node id, and with_video_prompt sniffs the key, which keeps
# one constant here instead of a per-engine table.
NEG_PROMPT_NODE = "7"   # CLIPTextEncode (negative) — video graphs only
VIDEO_SEED_NODE = "13"


def load(name: str) -> dict:
    return json.loads((WORKFLOWS / name).read_text())


def with_prompt(graph: dict, prompt: str, *, seed: int, prefix: str) -> dict:
    g = copy.deepcopy(graph)
    g[PROMPT_NODE]["inputs"]["text"] = prompt
    g[SEED_NODE]["inputs"]["noise_seed"] = seed
    g[SAVE_NODE]["inputs"]["filename_prefix"] = prefix
    return g


def with_video_prompt(
    graph: dict, prompt: str, negative: str, *, seed: int, prefix: str
) -> dict:
    """Parameterize a video graph. Same motion as with_prompt, plus a negative
    prompt — both video engines take one, and FLUX does not."""
    g = copy.deepcopy(graph)
    g[PROMPT_NODE]["inputs"]["text"] = prompt
    g[NEG_PROMPT_NODE]["inputs"]["text"] = negative
    sampler = g[VIDEO_SEED_NODE]["inputs"]
    sampler["noise_seed" if "noise_seed" in sampler else "seed"] = seed
    g[SAVE_NODE]["inputs"]["filename_prefix"] = prefix
    return g


def with_subject(graph: dict, remote_image: str) -> dict:
    g = copy.deepcopy(graph)
    g[PULID_IMAGE_NODE]["inputs"]["image"] = remote_image
    return g


def with_lora(graph: dict, lora_name: str, strength: float = 0.8) -> dict:
    g = copy.deepcopy(graph)
    g[LORA_NODE]["inputs"]["lora_name"] = lora_name
    g[LORA_NODE]["inputs"]["strength_model"] = strength
    return g


# --- ad-hoc generation ------------------------------------------------------
#
# `lora-lab gen` parameterizes any stored graph without knowing which engine it
# is. That works because every graph in assets/workflows/ puts the same knob at
# the same node id — prompt at 6, negative at 7, latent at 27, save at 9 — so
# the differences between engines stay inside the JSON.
#
# Knobs are looked up rather than declared per engine, and `customize` reports
# what it could not honour instead of silently dropping it. Two graphs really
# do differ: the FLUX graph has no negative node, and it carries its seed on
# RandomNoise at 25 while the video graphs carry theirs at 13.

SIZE_NODE = "27"                                # width / height / length
SEED_NODES = (SEED_NODE, VIDEO_SEED_NODE)       # "25" (FLUX), then "13" (video)
SEED_KEYS = ("noise_seed", "seed")              # SamplerCustom* vs KSampler*
STEPS_NODES = ("17", "13")                      # scheduler first, then sampler

# Engines whose step count is not a single number. ltx23 rides a hand-written
# sigma list (ManualSigmas), and wan14b splits its steps across two samplers at
# a fixed handover — changing one number there desynchronises end_at_step and
# buys either a half-denoised clip or a wasted pass.
FIXED_SCHEDULE = {"ltx23", "wan14b"}


def _put(graph: dict, node: str, key: str, value) -> bool:
    if node in graph and key in graph[node]["inputs"]:
        graph[node]["inputs"][key] = value
        return True
    return False


def _put_first(graph: dict, nodes, keys, value) -> bool:
    """Set the first (node, key) pair that exists. Engines disagree on where a
    seed or a step count lives; the graphs are the record, not a table here."""
    for node in nodes:
        for key in keys:
            if _put(graph, node, key, value):
                return True
    return False


def customize(graph: dict, *, engine: str, prompt: str, seed: int, prefix: str,
              negative: str | None = None, width: int | None = None,
              height: int | None = None, length: int | None = None,
              steps: int | None = None) -> tuple[dict, list[str]]:
    """Apply what this graph can take. Returns it, and the asks it ignored."""
    g = copy.deepcopy(graph)
    ignored: list[str] = []

    def ask(applied: bool, label: str) -> None:
        if not applied:
            ignored.append(label)

    ask(_put(g, PROMPT_NODE, "text", prompt), "--prompt")
    _put(g, SAVE_NODE, "filename_prefix", prefix)
    ask(_put_first(g, SEED_NODES, SEED_KEYS, seed), "--seed")
    if negative is not None:
        ask(_put(g, NEG_PROMPT_NODE, "text", negative), "--negative")
    for name, value in (("width", width), ("height", height), ("length", length)):
        if value is not None:
            ask(_put(g, SIZE_NODE, name, value), f"--{name}")
    if steps is not None:
        if engine in FIXED_SCHEDULE:
            ignored.append("--steps")
        else:
            ask(_put_first(g, STEPS_NODES, ("steps",), steps), "--steps")
    return g, ignored
