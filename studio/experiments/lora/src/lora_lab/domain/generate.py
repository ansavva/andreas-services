"""The on-pod generation drivers: smoke, expand, validate.

All three are the same motion — parameterize a stored graph, queue it through
the tunnel, fetch what came out — differing only in which graph and how many
times. None of this is recorded in studio's catalog; the fetched files under
local/ are the only record, and the RUNBOOK says so.
"""

import pathlib
import random
import time
import zlib

import click
import yaml

from lora_lab import ASSETS_DIR, LOCAL_DIR
from lora_lab.adapters import comfy, shell
from lora_lab.domain import graphs, pod, refs, sheet

COMFY_PORT = 8188
# One fixed seed base so a re-run reproduces the same candidates.
SEED_BASE = 990001

SMOKE_PROMPT = (
    "cinematic photograph of a weathered lighthouse on a rocky coast at golden hour, "
    "crashing waves, dramatic sky, 35mm, sharp focus"
)

# The same scene as the still, given motion: comparable subject matter, and
# the moving parts (water, cloud, light sweep) are what separate a working
# video model from one producing a slideshow.
SMOKE_VIDEO_PROMPT = (
    "cinematic aerial shot slowly orbiting a weathered lighthouse on a rocky coast at "
    "golden hour, waves crashing against the rocks and spraying, clouds drifting, the "
    "beam sweeping across the water, 35mm film, shallow depth of field"
)
SMOKE_VIDEO_NEGATIVE = (
    "static, still frame, blurry, low quality, distorted, watermark, text, "
    "jpeg artifacts, overexposed"
)

# engine -> stored graph. All of them write through SaveWEBM at node 9 and
# carry their seed at node 13; graphs.with_video_prompt owns the rest. The
# 14B Wan samples in two stages, so node 13 is its high-noise pass and node 14
# takes the leftover noise with add_noise disabled — one seed still decides
# the clip.
VIDEO_ENGINES = {
    "ltx098": "smoke-ltx.json",
    "ltx23": "smoke-ltx23.json",
    "ltx25": "smoke-ltx25.json",
    "wan": "smoke-wan.json",
    "wan14b": "smoke-wan14b.json",
}

# Component -> rough on-disk size in GB, for the pre-download space check
# against the /weights volume. On 250GB everything except flux2dev coexists;
# adding it too means growing the volume or dropping an engine.
ASSET_GB = {
    "encoders": 6, "flux1dev": 13, "flux2dev": 54, "sd35": 17, "ltx098": 16, "ltx23": 43,
    "ltx25": 39, "wan": 19, "wan14b": 30, "pulid": 3, "onetrainer": 40,
}

# What each engine needs installed. `encoders` is shared — CLIP-L and T5-XXL
# serve FLUX, SD 3.5 and LTX 0.9.8 alike — so it is listed rather than folded
# into three components that would each download it.
ENGINE_ASSETS = {
    "flux1dev": ["encoders", "flux1dev"],
    # No `encoders`: FLUX.2 brings its own Mistral-3-Small text encoder and its
    # own VAE, and shares nothing with the T5-XXL line.
    "flux2dev": ["flux2dev"],
    "sd35": ["encoders", "sd35"],
    "ltx098": ["encoders", "ltx098"],
    "ltx23": ["ltx23"],
    "ltx25": ["ltx25"],
    "wan": ["wan"],
    "wan14b": ["wan14b"],
}

IMAGE_ENGINES = {
    "flux1dev": "smoke-flux.json",
    "flux2dev": "smoke-flux2.json",
    "sd35": "smoke-sd35.json",
}

ENGINES = {**IMAGE_ENGINES, **VIDEO_ENGINES}


def gen(engine: str, prompt: str, *, negative: str | None = None, seed: int | None = None,
        width: int | None = None, height: int | None = None, length: int | None = None,
        steps: int | None = None, out: str | None = None) -> None:
    """Run any registered engine on your own prompt.

    The smoke commands answer "does this work"; this one answers "what does it
    make". Same graphs, same fetch, no fixed prompt — and it prints the seed it
    used, so an accidental good result is reproducible.
    """
    graph_name = ENGINES.get(engine)
    if not graph_name:
        raise click.ClickException(
            f"unknown engine {engine!r} — one of {', '.join(sorted(ENGINES))}"
        )
    if not (ASSETS_DIR / "workflows" / graph_name).is_file():
        raise click.ClickException(
            f"{engine} has no workflow yet ({graph_name}). See RUNBOOK.md, Milestone 0b."
        )

    is_video = engine in VIDEO_ENGINES
    if seed is None:
        seed = random.randrange(2**31)
    if negative is None and is_video:
        negative = SMOKE_VIDEO_NEGATIVE

    pod.ready()
    pod.ensure(ENGINE_ASSETS[engine], ASSET_GB)

    graph, ignored = graphs.customize(
        graphs.load(graph_name), engine=engine, prompt=prompt, negative=negative,
        seed=seed, prefix=f"gen-{engine}", width=width, height=height,
        length=length, steps=steps,
    )
    if ignored:
        click.echo(f"note: {engine} takes no {', '.join(ignored)} — ignored, everything else applied")

    out_dir = pathlib.Path(out) if out else LOCAL_DIR / "gen"
    ip, port = pod.endpoint()
    with shell.tunnel(ip, port, COMFY_PORT, COMFY_PORT):
        if not comfy.alive():
            raise click.ClickException("ComfyUI is not answering — check `lora-lab pod status`")
        click.echo(f"queued {engine}, seed {seed}…")
        files = comfy.run_graph_files(graph, timeout=3600 if is_video else 900)
    if not files:
        raise click.ClickException(f"{engine} produced no output — check /workspace/comfy.log")
    for path in _fetch_named(files, out_dir, f"{engine}-{seed}-{int(time.time())}"):
        click.echo(f"fetched {path}")


def _fetch(images: list[bytes], out_dir, stem: str) -> list:
    """Write fetched render bytes as PNGs. Restored 2026-08-25: the rename to
    _fetch_named dropped this original and left smoke/expand/validate calling
    a name that no longer existed — found by the first smoke on the new
    architecture, at the very last step of an otherwise green run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, blob in enumerate(images):
        p = out_dir / (f"{stem}.png" if len(images) == 1 else f"{stem}-{i}.png")
        p.write_bytes(blob)
        paths.append(p)
    return paths


def _fetch_named(files: list[tuple[str, bytes]], out_dir, stem: str) -> list:
    """_fetch, keeping the extension ComfyUI chose. A clip and a frame arrive
    through the same API and differ only by suffix."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (name, blob) in enumerate(files):
        suffix = pathlib.Path(name).suffix or ".bin"
        p = out_dir / (f"{stem}{suffix}" if len(files) == 1 else f"{stem}-{i}{suffix}")
        p.write_bytes(blob)
        paths.append(p)
    return paths


def smoke() -> None:
    """Milestone 0: one plain FLUX.1-dev txt2img on the pod, no LoRA, no PuLID.

    Proves the whole stack — RunPod API, image pull, SSH, volume mount,
    ComfyUI queue, tunnel, fetch — before any subject data is involved.
    """
    pod.ready()
    pod.ensure(ENGINE_ASSETS["flux1dev"], ASSET_GB)
    ip, port = pod.endpoint()
    with shell.tunnel(ip, port, COMFY_PORT, COMFY_PORT):
        if not comfy.alive():
            raise click.ClickException("ComfyUI is not answering — check `lora-lab pod status`")
        graph = graphs.with_prompt(
            graphs.load("smoke-flux.json"), SMOKE_PROMPT, seed=SEED_BASE, prefix="smoke"
        )
        click.echo("queued smoke render (first run compiles the model — a few minutes)…")
        images = comfy.run_graph(graph, timeout=900)
    paths = _fetch(images, LOCAL_DIR / "smoke", f"smoke-{int(time.time())}")
    for p in paths:
        click.echo(f"fetched {p}")
    click.echo("smoke test PASSED — the RunPod stack works end to end.")


def smoke_video(engine: str) -> None:
    """Milestone 0b: one short clip per video engine, fetched to local/smoke/.

    Not part of the LoRA experiment — an image LoRA does not load into either
    of these. It answers the prior question of whether this pod can drive a
    local video model at all, and how the two compare, before anyone commits
    to a video-LoRA recipe. Subject-free, like the FLUX smoke.
    """
    graph_name = VIDEO_ENGINES.get(engine)
    if not graph_name:
        raise click.ClickException(
            f"unknown engine {engine!r} — one of {', '.join(sorted(VIDEO_ENGINES))}"
        )
    pod.ready()
    pod.ensure(ENGINE_ASSETS[engine], ASSET_GB)

    ip, port = pod.endpoint()
    with shell.tunnel(ip, port, COMFY_PORT, COMFY_PORT):
        if not comfy.alive():
            raise click.ClickException("ComfyUI is not answering — check `lora-lab pod status`")
        graph = graphs.with_video_prompt(
            graphs.load(graph_name),
            SMOKE_VIDEO_PROMPT,
            SMOKE_VIDEO_NEGATIVE,
            seed=SEED_BASE,
            prefix=f"smoke-{engine}",
        )
        click.echo(f"queued {engine} clip (first run loads ~10–16GB of weights)…")
        files = comfy.run_graph_files(graph, timeout=1800)
    if not files:
        raise click.ClickException(f"{engine} produced no output — check /workspace/comfy.log")
    paths = _fetch_named(files, LOCAL_DIR / "smoke", f"smoke-{engine}-{int(time.time())}")
    for p in paths:
        click.echo(f"fetched {p}")
    click.echo(f"{engine} video smoke PASSED.")


def expand(slug: str, ref_index: int) -> None:
    """Session A: expand the subject references into training candidates."""
    pod.ready()
    # The only command that needs the PuLID face-stack weights. The nodes and
    # their pip deps are baked into the image, so no ComfyUI restart anymore.
    pod.ensure(ENGINE_ASSETS["flux1dev"] + ["pulid"], ASSET_GB)
    pod.ensure_comfy()
    ip, port = pod.endpoint()
    matrix = yaml.safe_load((ASSETS_DIR / "expansion-matrix.yaml").read_text())
    variations = matrix["variations"]
    out_dir = LOCAL_DIR / slug / "candidates"

    # The refs must already be on the pod, and ComfyUI loads them by relative
    # path via its extra input dir (extra-paths.yaml points `lab` at
    # /workspace/dataset).
    listing = shell.run(ip, port, f"ls {refs.REMOTE_SUBJECT_DIR}/ref-*.png 2>/dev/null", check=False)
    ref_files = [l.strip() for l in listing.splitlines() if l.strip()]
    if not ref_files:
        raise click.ClickException(f"no references on the pod — run `lora-lab refs {slug}` first")
    subject = f"subject/{ref_files[min(ref_index, len(ref_files) - 1)].rsplit('/', 1)[1]}"
    click.echo(f"{len(ref_files)} reference(s) on pod; conditioning on {subject}")
    click.echo(f"{len(variations)} variations × {matrix.get('per_variation', 2)} seeds")

    base = graphs.with_subject(graphs.load("expand-pulid.json"), subject)
    per = int(matrix.get("per_variation", 2))
    with shell.tunnel(ip, port, COMFY_PORT, COMFY_PORT):
        comfy.require_nodes(["ApplyPulidFlux", "PulidFluxModelLoader"])
        total = len(variations) * per
        done = 0
        for var in variations:
            for s in range(per):
                stem = f"{var['id']}-s{s}"
                prompt = matrix["base_prompt"].format(scene=var["prompt"])
                g = graphs.with_prompt(base, prompt, seed=SEED_BASE + zlib.crc32(stem.encode()) % 10_000, prefix=stem)
                images = comfy.run_graph(g, timeout=900)
                _fetch(images, out_dir, stem)
                done += 1
                click.echo(f"[{done}/{total}] {stem}")

    out = LOCAL_DIR / slug / "candidates-sheet.png"
    sheet.contact_sheet(list(out_dir.glob("*.png")), out)
    click.echo(f"contact sheet: {out}")
    click.echo(
        "GATE 1: curate by hand — copy the 15–20 keepers into "
        f"{LOCAL_DIR / slug / 'dataset'}/ and write captions (see assets/captions.md; "
        f"`lora-lab captions {slug}` scaffolds the .txt files)."
    )


def validate(slug: str, strength: float) -> None:
    """Render the fixed validation grid with each fetched checkpoint."""
    pod.ready()
    pod.ensure(ENGINE_ASSETS["flux1dev"], ASSET_GB)
    ip, port = pod.endpoint()
    prompts = yaml.safe_load((ASSETS_DIR / "validation-prompts.yaml").read_text())["prompts"]
    trigger = f"ohwx_{slug}"

    # Checkpoints are symlinked into ComfyUI's lora dir by the train step;
    # validate whatever is there.
    listing = shell.run(
        ip, port, "ls /opt/ComfyUI/models/loras/*.safetensors 2>/dev/null", check=False
    )
    ckpts = [l.strip().rsplit("/", 1)[1] for l in listing.splitlines() if l.strip()]
    if not ckpts:
        raise click.ClickException("no checkpoints in ComfyUI/models/loras — run `lora-lab train` first")
    click.echo(f"validating {len(ckpts)} checkpoint(s) × {len(prompts)} prompts")

    base = graphs.load("validate-lora.json")
    with shell.tunnel(ip, port, COMFY_PORT, COMFY_PORT):
        for ckpt in ckpts:
            out_dir = LOCAL_DIR / slug / "validation" / ckpt.removesuffix(".safetensors")
            g_lora = graphs.with_lora(base, ckpt, strength)
            for p in prompts:
                text = p["prompt"].format(trigger=trigger)
                g = graphs.with_prompt(g_lora, text, seed=SEED_BASE + p["seed_offset"], prefix=p["id"])
                images = comfy.run_graph(g, timeout=900)
                _fetch(images, out_dir, p["id"])
                click.echo(f"{ckpt} · {p['id']}")
            sheet.contact_sheet(
                list(out_dir.glob("*.png")),
                LOCAL_DIR / slug / "validation" / f"{ckpt.removesuffix('.safetensors')}-sheet.png",
            )
    click.echo(f"grids under {LOCAL_DIR / slug / 'validation'} — score per RUNBOOK phase 3.")
