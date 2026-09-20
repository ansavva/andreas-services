"""studio's own Wan 2.2 I2V worker — a Runpod serverless handler over ComfyUI.

One job is one clip: a start frame (and optionally an end frame) in, an
H.264 mp4 out, with a trained LoRA pair loaded onto Wan 2.2's two experts.
The request is the flat document `studio`'s registry entry
`wan-2.2-i2v-studio` sends — the same field names Runpod's public
`wan-2-2-t2v-720-lora` endpoint takes (`image`, `prompt`,
`high_noise_loras`, `low_noise_loras`, `seed`), plus what that endpoint
refuses to take: `end_image`, `num_frames`, `fps`, `width`/`height`,
`steps`, `guidance`, `shift`, `negative_prompt`.

## Shape of the answer

`{"result": <url>, "cost": <usd>, ...}` — the public endpoints' shape, so
`clients/runpod.py` in the backend reads it with no new code. `result` is
the `result_url` the request carried (a presigned GET of the object this
worker PUT to `output_url`); the backend files it under the run's `output/`
like any other provider's file. `cost` is worker seconds × `STUDIO_USD_PER_SECOND`
(set on the endpoint template to the GPU's per-second flex price), because a
custom endpoint gets no price from Runpod the way a public one does.

## Where things live

ComfyUI is the stock `runpod/worker-comfyui` install at `/comfyui`, started
by that image's `start.sh` before this handler. Weights are on the network
volume (`/runpod-volume/models/...`, see `extra_model_paths.yaml`), never in
the image. LoRAs arrive as presigned URLs and are cached on the same volume
under `models/loras/studio-cache/<sha256 of the URL without its query>.safetensors`
— the query is the signature, which changes every submit; the path is the
library's blob key, which does not.

## Why ComfyUI and not diffusers

Wan 2.2's two-expert sampler, per-expert LoRA loading and first-last-frame
conditioning are all first-class nodes here (`WanImageToVideo`,
`WanFirstLastFrameToVideo`, `LoraLoaderModelOnly`), the community trains and
tests Wan LoRAs against exactly these nodes, and the 14B fp16 pair fits an
80 GB card with ComfyUI's own offloading. diffusers' `WanImageToVideoPipeline`
had none of the FLF path and needed its own memory management.
"""

import glob
import hashlib
import json
import logging
import os
import random
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import runpod

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("studio-wan22")

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
COMFY_ROOT = os.environ.get("COMFY_ROOT", "/comfyui")
VOLUME = os.environ.get("STUDIO_VOLUME_ROOT", "/runpod-volume")
LORA_CACHE = os.path.join(VOLUME, "models", "loras", "studio-cache")
LORA_SUBDIR = "studio-cache"

HIGH = os.environ.get("STUDIO_WAN_HIGH", "wan2.2_i2v_high_noise_14B_fp16.safetensors")
LOW = os.environ.get("STUDIO_WAN_LOW", "wan2.2_i2v_low_noise_14B_fp16.safetensors")
T5 = os.environ.get("STUDIO_WAN_T5", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
VAE = os.environ.get("STUDIO_WAN_VAE", "wan_2.1_vae.safetensors")
#: The Wan 2.2 Lightning 4-step distillation pair (lightx2v, Seko V1), on
#: the volume beside the weights. `mode: fast` puts them first in each
#: expert's LoRA chain and samples 4 steps at cfg 1, shift 5 — the settings
#: its own ComfyUI workflow ships — for roughly a fifth of the render time.
LIGHTNING_HIGH = "lightning/wan2.2_i2v_lightning_4step_high.safetensors"
LIGHTNING_LOW = "lightning/wan2.2_i2v_lightning_4step_low.safetensors"
MODES = {
    # steps, guidance, shift — the defaults each mode takes when the request
    # names none. A request may override any of the three.
    "quality": (20, 3.5, 8.0),
    "fast": (4, 1.0, 5.0),
}

#: Dollars per worker-second, from the template. Zero means "unpriced" and
#: the answer carries `cost: null` rather than a made-up zero.
USD_PER_SECOND = float(os.environ.get("STUDIO_USD_PER_SECOND", "0") or 0)
#: Frames the card is allowed. 241 (15 s at 16 fps) was the ceiling tried on
#: an H100 80GB; the registry caps lower than this.
MAX_FRAMES = int(os.environ.get("STUDIO_MAX_FRAMES", "241"))
#: Wall-clock cap on one ComfyUI prompt before it is interrupted.
MAX_SECONDS = int(os.environ.get("STUDIO_MAX_SECONDS", "2400"))
DOWNLOAD_TIMEOUT = 300

#: Wan's own negative prompt, the one every official template ships.
DEFAULT_NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
    "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，"
    "画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
    "杂乱的背景，三条腿，背景人很多，倒着走"
)

VERSION = "2026-09-20.2"


class JobError(Exception):
    """A refusal this worker can name; goes back as the job's `error`."""


# ── input ───────────────────────────────────────────────────────────────────


def _int(inp: dict, name: str, default: int, lo: int, hi: int) -> int:
    value = inp.get(name, default)
    if value is None:
        value = default
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise JobError(f"{name} must be an integer")
    if not lo <= value <= hi:
        raise JobError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def _float(inp: dict, name: str, default: float, lo: float, hi: float) -> float:
    value = inp.get(name, default)
    if value is None:
        value = default
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise JobError(f"{name} must be a number")
    if not lo <= value <= hi:
        raise JobError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def _url(inp: dict, name: str, required: bool) -> str | None:
    value = inp.get(name)
    if not value:
        if required:
            raise JobError(f"{name} is required")
        return None
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        raise JobError(f"{name} must be an http(s) URL")
    return value


def _loras(inp: dict, name: str) -> list[tuple[str, float]]:
    raw = inp.get(name) or []
    if not isinstance(raw, list):
        raise JobError(f"{name} must be a list of {{path, scale}}")
    out = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise JobError(f"each {name} entry is {{path, scale}}")
        scale = item.get("scale", 1.0)
        try:
            scale = float(scale)
        except (TypeError, ValueError):
            raise JobError(f"{name}.scale must be a number")
        out.append((item["path"], scale))
    return out


def parse(inp: dict) -> dict:
    """The request, checked and defaulted. Raises `JobError` with a reason."""
    prompt = inp.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise JobError("prompt is required")
    frames = _int(inp, "num_frames", 81, 5, MAX_FRAMES)
    if (frames - 1) % 4:
        # Wan's VAE packs 4 frames per latent frame plus one; anything else
        # is rounded down to the nearest valid length rather than refused.
        frames = 4 * ((frames - 1) // 4) + 1
    width = inp.get("width")
    height = inp.get("height")
    if (width is None) != (height is None):
        raise JobError("width and height go together")
    seed = _int(inp, "seed", -1, -1, 2**53)
    if seed < 0:
        seed = random.randint(0, 2**32 - 1)
    mode = inp.get("mode") or "quality"
    if mode not in MODES:
        raise JobError(f"mode is one of {sorted(MODES)}, got {mode!r}")
    steps, guidance, shift = MODES[mode]
    return {
        "prompt": prompt,
        "negative_prompt": inp.get("negative_prompt") or DEFAULT_NEGATIVE,
        "image": _url(inp, "image", required=True),
        "end_image": _url(inp, "end_image", required=False),
        "high_noise_loras": _loras(inp, "high_noise_loras"),
        "low_noise_loras": _loras(inp, "low_noise_loras"),
        "num_frames": frames,
        "fps": _int(inp, "fps", 16, 1, 60),
        "width": None if width is None else _int(inp, "width", 1280, 256, 1920),
        "height": None if height is None else _int(inp, "height", 720, 256, 1920),
        "mode": mode,
        "steps": _int(inp, "steps", steps, 2, 60),
        "guidance": _float(inp, "guidance", guidance, 0.0, 20.0),
        "shift": _float(inp, "shift", shift, 0.0, 30.0),
        "seed": seed,
        "output_url": _url(inp, "output_url", required=False),
        "result_url": _url(inp, "result_url", required=False),
    }


# ── files ───────────────────────────────────────────────────────────────────


def _fetch(url: str, path: str, *, timeout: int = DOWNLOAD_TIMEOUT) -> int:
    """Stream `url` to `path` through a `.part` file; the size in bytes."""
    tmp = path + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": "studio-wan22-worker"})
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(tmp, "wb") as out:
            while chunk := response.read(1 << 22):
                out.write(chunk)
                written += len(chunk)
    except urllib.error.HTTPError as exc:
        raise JobError(f"GET {url.split('?')[0]} -> {exc.code}") from exc
    except OSError as exc:
        raise JobError(f"GET {url.split('?')[0]} failed: {exc}") from exc
    if written == 0:
        raise JobError(f"GET {url.split('?')[0]} returned an empty body")
    os.replace(tmp, path)
    return written


def cache_key(url: str) -> str:
    """The cache file for a LoRA URL: a hash of everything but the query."""
    stable = url.split("?", 1)[0]
    return hashlib.sha256(stable.encode()).hexdigest()[:40] + ".safetensors"


def cached_lora(url: str) -> str:
    """The LoRA at `url`, on the volume; ComfyUI's name for it."""
    os.makedirs(LORA_CACHE, exist_ok=True)
    name = cache_key(url)
    path = os.path.join(LORA_CACHE, name)
    if not os.path.exists(path):
        started = time.time()
        size = _fetch(url, path)
        log.info("cached LoRA %s (%d MB, %.1fs)", name, size >> 20, time.time() - started)
    else:
        # Touch it: the cache is pruned by age, and a hit is a use.
        os.utime(path, None)
    return f"{LORA_SUBDIR}/{name}"


def input_image(url: str, tag: str) -> str:
    """Download a frame into ComfyUI's input dir; the filename `LoadImage` wants."""
    folder = os.path.join(COMFY_ROOT, "input")
    os.makedirs(folder, exist_ok=True)
    name = f"studio-{tag}-{uuid.uuid4().hex[:8]}.img"
    _fetch(url, os.path.join(folder, name))
    return name


def image_size(name: str) -> tuple[int, int]:
    from PIL import Image
    with Image.open(os.path.join(COMFY_ROOT, "input", name)) as image:
        return image.size


# ── the graph ───────────────────────────────────────────────────────────────


def build_graph(p: dict, start: str, end: str | None, high: list, low: list, prefix: str) -> dict:
    """The Wan 2.2 14B I2V workflow, API format, with the LoRA chains in.

    Mirrors ComfyUI's official `video_wan2_2_14B_i2v` / `_flf2v` templates:
    two experts, `ModelSamplingSD3` shift on both, the high-noise expert
    denoising the first half of the steps and the low-noise expert the
    second, Wan's negative, `CreateVideo` + `SaveVideo` for the mp4.
    """
    n: dict[str, dict] = {}

    def node(key, class_type, **inputs):
        n[key] = {"class_type": class_type, "inputs": inputs}
        return [key, 0]

    high_model = node("high", "UNETLoader", unet_name=HIGH, weight_dtype="default")
    low_model = node("low", "UNETLoader", unet_name=LOW, weight_dtype="default")
    if p["mode"] == "fast":
        # The distillation adapter goes on first, the character's after it,
        # the way Lightning's own workflow stacks a style LoRA.
        high = [(LIGHTNING_HIGH, 1.0), *high]
        low = [(LIGHTNING_LOW, 1.0), *low]
    for i, (name, scale) in enumerate(high):
        high_model = node(f"high_lora{i}", "LoraLoaderModelOnly",
                          model=high_model, lora_name=name, strength_model=scale)
    for i, (name, scale) in enumerate(low):
        low_model = node(f"low_lora{i}", "LoraLoaderModelOnly",
                         model=low_model, lora_name=name, strength_model=scale)
    high_model = node("high_shift", "ModelSamplingSD3", model=high_model, shift=p["shift"])
    low_model = node("low_shift", "ModelSamplingSD3", model=low_model, shift=p["shift"])

    clip = node("clip", "CLIPLoader", clip_name=T5, type="wan", device="default")
    vae = node("vae", "VAELoader", vae_name=VAE)
    positive = node("pos", "CLIPTextEncode", clip=clip, text=p["prompt"])
    negative = node("neg", "CLIPTextEncode", clip=clip, text=p["negative_prompt"])
    start_image = node("start", "LoadImage", image=start)

    common = dict(positive=positive, negative=negative, vae=vae,
                  width=p["width"], height=p["height"], length=p["num_frames"], batch_size=1)
    if end:
        end_image = node("end", "LoadImage", image=end)
        node("i2v", "WanFirstLastFrameToVideo", start_image=start_image, end_image=end_image, **common)
    else:
        node("i2v", "WanImageToVideo", start_image=start_image, **common)
    cond_pos, cond_neg, latent = ["i2v", 0], ["i2v", 1], ["i2v", 2]

    split = max(1, p["steps"] // 2)
    sampled = node("k_high", "KSamplerAdvanced", model=high_model, add_noise="enable",
                   noise_seed=p["seed"], steps=p["steps"], cfg=p["guidance"],
                   sampler_name="euler", scheduler="simple", positive=cond_pos,
                   negative=cond_neg, latent_image=latent, start_at_step=0,
                   end_at_step=split, return_with_leftover_noise="enable")
    sampled = node("k_low", "KSamplerAdvanced", model=low_model, add_noise="disable",
                   noise_seed=p["seed"], steps=p["steps"], cfg=p["guidance"],
                   sampler_name="euler", scheduler="simple", positive=cond_pos,
                   negative=cond_neg, latent_image=sampled, start_at_step=split,
                   end_at_step=10000, return_with_leftover_noise="disable")
    frames = node("decode", "VAEDecode", samples=sampled, vae=vae)
    video = node("video", "CreateVideo", images=frames, fps=float(p["fps"]))
    node("save", "SaveVideo", video=video, filename_prefix=prefix, format="mp4")
    return n


# ── ComfyUI ─────────────────────────────────────────────────────────────────


def _comfy(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(COMFY + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def wait_for_comfy(timeout: int = 600) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _comfy("GET", "/system_stats")
            return
        except Exception:
            time.sleep(1)
    raise JobError("ComfyUI did not come up")


def run_graph(graph: dict, job: dict) -> dict:
    """Queue the prompt and block until it is in history; the history entry."""
    client_id = uuid.uuid4().hex
    try:
        queued = _comfy("POST", "/prompt", {"prompt": graph, "client_id": client_id})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        raise JobError(f"ComfyUI refused the workflow: {detail}") from exc
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise JobError(f"ComfyUI gave no prompt id: {queued}")
    started = time.time()
    last_note = 0.0
    while True:
        elapsed = time.time() - started
        if elapsed > MAX_SECONDS:
            try:
                _comfy("POST", "/interrupt", {})
            finally:
                raise JobError(f"the render passed {MAX_SECONDS}s and was interrupted")
        history = _comfy("GET", f"/history/{prompt_id}").get(prompt_id)
        if history:
            status = history.get("status") or {}
            if status.get("status_str") == "error" or not status.get("completed", True):
                raise JobError("ComfyUI failed: " + _comfy_error(status))
            return history
        if elapsed - last_note >= 30:
            last_note = elapsed
            runpod.serverless.progress_update(job, f"rendering, {int(elapsed)}s")
        time.sleep(2)


def _comfy_error(status: dict) -> str:
    for message in status.get("messages") or []:
        if isinstance(message, list) and message and message[0] == "execution_error":
            detail = message[1] if len(message) > 1 and isinstance(message[1], dict) else {}
            node = detail.get("node_type") or detail.get("node_id") or "?"
            return f"{node}: {detail.get('exception_message') or detail.get('exception_type')}"
    return json.dumps(status)[:1000]


# ── output ──────────────────────────────────────────────────────────────────


def faststart(src: str, dst: str) -> None:
    """The mp4 with its moov atom in front — and H.264 if it was not already."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name", "-of", "csv=p=0", src],
        capture_output=True, text=True, check=False,
    )
    codec = probe.stdout.strip()
    if codec == "h264":
        args = ["-c", "copy"]
    else:
        args = ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, *args,
                    "-movflags", "+faststart", dst], check=True)


def upload(path: str, url: str) -> int:
    """PUT the file to the presigned URL. The content type is in the signature."""
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        body = handle.read()
    request = urllib.request.Request(url, data=body, method="PUT",
                                     headers={"Content-Type": "video/mp4",
                                              "Content-Length": str(size)})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise JobError(f"PUT to output_url -> {exc.code}: {detail}") from exc
    return size


# ── the handler ─────────────────────────────────────────────────────────────


def ping() -> dict:
    """What this worker is and can see, without touching the GPU."""
    models = {}
    for sub in ("diffusion_models", "text_encoders", "vae"):
        folder = os.path.join(VOLUME, "models", sub)
        models[sub] = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    cache = sorted(os.listdir(LORA_CACHE)) if os.path.isdir(LORA_CACHE) else []
    return {"version": VERSION, "models": models, "lora_cache": cache,
            "usd_per_second": USD_PER_SECOND, "max_frames": MAX_FRAMES}


def handler(job: dict) -> dict:
    started = time.time()
    inp = job.get("input") or {}
    if inp.get("op") == "ping":
        return ping()
    try:
        p = parse(inp)
        wait_for_comfy()
        tag = uuid.uuid4().hex[:12]
        start = input_image(p["image"], f"{tag}-start")
        end = input_image(p["end_image"], f"{tag}-end") if p["end_image"] else None
        if p["width"] is None:
            # Landscape stills get 1280x720, portrait 720x1280; nothing else.
            w, h = image_size(start)
            p["width"], p["height"] = (1280, 720) if w >= h else (720, 1280)
        high = [(cached_lora(url), scale) for url, scale in p["high_noise_loras"]]
        low = [(cached_lora(url), scale) for url, scale in p["low_noise_loras"]]

        prefix = f"studio/{tag}"
        graph = build_graph(p, start, end, high, low, prefix)
        log.info("rendering %dx%d x%d frames, %d steps, seed %d, %d+%d loras, end frame %s",
                 p["width"], p["height"], p["num_frames"], p["steps"], p["seed"],
                 len(high), len(low), bool(end))
        render_started = time.time()
        run_graph(graph, job)
        render_seconds = time.time() - render_started

        found = sorted(glob.glob(os.path.join(COMFY_ROOT, "output", prefix + "*.mp4")))
        if not found:
            raise JobError("ComfyUI finished but wrote no mp4")
        final = os.path.join(COMFY_ROOT, "output", f"{prefix}-final.mp4")
        faststart(found[-1], final)
        size = os.path.getsize(final)
        if p["output_url"]:
            upload(final, p["output_url"])
        seconds = time.time() - started
        result = p["result_url"]
        if not result and p["output_url"]:
            result = p["output_url"].split("?", 1)[0]
        out = {
            "result": result,
            "cost": round(seconds * USD_PER_SECOND, 4) if USD_PER_SECOND else None,
            "seconds": round(seconds, 1),
            "render_seconds": round(render_seconds, 1),
            "bytes": size,
            "frames": p["num_frames"],
            "fps": p["fps"],
            "width": p["width"],
            "height": p["height"],
            "seed": p["seed"],
            "end_frame": bool(end),
            "mode": p["mode"],
            "steps": p["steps"],
            "loras": {"high": len(high), "low": len(low)},
            "worker": VERSION,
        }
        if not p["output_url"]:
            # No grant to upload on: a pod-side test. Keep the file where the
            # cleanup below will not reach it.
            kept = f"/tmp/studio-{tag}.mp4"
            shutil.copyfile(final, kept)
            out["local_path"] = kept
        return out
    except JobError as exc:
        log.warning("job refused: %s", exc)
        return {"error": str(exc), "seconds": round(time.time() - started, 1)}
    finally:
        for stale in glob.glob(os.path.join(COMFY_ROOT, "input", "studio-*.img")):
            try:
                os.remove(stale)
            except OSError:
                pass
        shutil.rmtree(os.path.join(COMFY_ROOT, "output", "studio"), ignore_errors=True)


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
