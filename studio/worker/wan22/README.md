# `worker/wan22/` — studio's own Wan 2.2 I2V endpoint

A Runpod **serverless endpoint we own** that runs Wan 2.2 14B image-to-video
with a trained LoRA pair loaded onto both experts, and takes what Runpod's
public `wan-2-2-t2v-720-lora` endpoint refuses: an end frame, any length,
portrait, steps, guidance, shift, a negative prompt, a repeatable seed. The
registry entry is `wan-2.2-i2v-studio`; studio calls it exactly the way it
calls the public endpoints (`provider: runpod`, `POST /v2/<id>/run`, the
callback, `output.result` + `output.cost`), so `clients/runpod.py` needed no
new code — the one addition to the backend is the **output grant** below.

## The pieces

| | Where | What |
|---|---|---|
| Handler | [`handler.py`](handler.py) | The Runpod serverless handler: flat request in, ComfyUI workflow built and queued, mp4 out. Downloads frames and LoRAs from presigned URLs, caches LoRAs on the volume, PUTs the result to a presigned URL |
| Model paths | [`extra_model_paths.yaml`](extra_model_paths.yaml) | Tells ComfyUI the weights are under `/runpod-volume/models/` |
| Start | [`start.sh`](start.sh) | ComfyUI in the background (`COMFY_ARGS` for flags), then the handler. The template's start command off the volume; the Dockerfile's CMD |
| Weights | [`download-weights.sh`](download-weights.sh) | Run on a pod by `runpod-volume-setup.sh`: the fp16 expert pair, the fp8 T5, the VAE, the Lightning 4-step pair — 66 GB, from Hugging Face |
| Image | [`Dockerfile`](Dockerfile) | `FROM runpod/worker-comfyui:5.10.0-base` + the two files. **Optional** — see "Code on the volume" |
| Scripts | `studio/scripts/runpod-volume-setup.sh`, `runpod-endpoint-up.sh`, `runpod-endpoint-down.sh` | Volume + weights + code; template + endpoint + a cold-start ping; teardown |
| Registry | `backend/studio_core/models.json` → `wan-2.2-i2v-studio` | The schema; `output_grant` is what makes the backend mint the upload URL |
| Skill | `studio/.claude/skills/studio-media-wan-2-2-i2v-studio/` | How to invoke it |

## How a job flows

```
studio run …  ──►  API dispatch  ──►  POST api.runpod.ai/v2/<id>/run
                    │ presigns image, end_image, the LoRA pair (GET, 15 min)
                    │ mints output_url (PUT) + result_url (GET) on scratch/<run>/result.mp4
                    ▼
              worker (ComfyUI)  ── downloads frames + LoRAs (cache) ── renders ── ffmpeg faststart
                    │ PUT mp4 → output_url
                    ▼
              {"output": {"result": <result_url>, "cost": <usd>, "seed": …, "seconds": …}}
                    │ webhook → /api/hooks/runpod/<run>?sig=…   (or `studio runs reconcile`)
                    ▼
              close_from_prediction: GET result_url, file under the run's output/, record cost
```

**Why the grant pair.** A public endpoint hosts its output on
`image.runpod.ai` for a week. Our worker has nowhere to put a file and holds
no AWS credential (hard rule: S3 is the only origin, and a worker gets
presigned URLs, never a key). So `generate.dispatch` reads
`output_grant` off the entry and adds two presigned URLs to the payload: a
PUT the worker uploads to, and a GET it echoes back as `result` so the
closing path treats it like any provider's URL. The key is
`scratch/<run id>/result.mp4`; the closing path copies the bytes into the
run's own folder and the bucket's `expire-scratch` lifecycle rule removes
the scratch object after 7 days. `_unsigned_input` scrubs the GET out of
the stored response document, the way it scrubs the presigned inputs.

## ComfyUI, not diffusers

Wan 2.2's two-expert sampling, a LoRA per expert (`LoraLoaderModelOnly`)
and first-last-frame conditioning (`WanFirstLastFrameToVideo`, used by
ComfyUI's own `video_wan2_2_14B_flf2v` template) are all core nodes, and the
community trains and tests Wan LoRAs against exactly these nodes. The stock
`runpod/worker-comfyui` image already carries ComfyUI 0.34, torch, ffmpeg
and the Runpod SDK, so the whole image side of this is a handler file.
diffusers' `WanImageToVideoPipeline` had no FLF path and would have needed
its own offloading to fit the fp16 pair on 80 GB.

The graph is the official Wan 2.2 14B I2V template: `UNETLoader` ×2 (fp16),
`CLIPLoader` (umt5-xxl fp8, type `wan`), `VAELoader`, the LoRA chain on
each expert, `ModelSamplingSD3` shift on both, `WanImageToVideo` (or
`WanFirstLastFrameToVideo` with an end frame), `KSamplerAdvanced` ×2 — the
high-noise expert for the first half of the steps, the low-noise one for
the rest — `VAEDecode`, `CreateVideo`, `SaveVideo` (mp4/h264), then
`ffmpeg -movflags +faststart`.

**fp16 experts, not fp8.** ComfyUI folds a LoRA into the weight dtype at
load; into fp8 that rounds a rank-32 adapter away. fp16 is 57 GB for the
pair, and ComfyUI keeps one expert resident at a time, so it fits an 80 GB
card. The T5 is fp8 (the official templates' choice; it is not touched by
the LoRA).

## The request

Everything the registry entry's `input` block lists; the handler's `parse`
is the authority. In short:

| Field | Default | |
|---|---|---|
| `prompt` | required | say the LoRA's trigger word |
| `image` | required | presigned URL of the start frame |
| `end_image` | — | presigned URL of the last frame → FLF mode |
| `high_noise_loras`, `low_noise_loras` | `[]` | `[{path, scale}]`, presigned `.safetensors` URLs |
| `negative_prompt` | Wan's standard negative | |
| `num_frames` | 81 | 4k+1; rounds down. `STUDIO_MAX_FRAMES` (241) caps it on the worker, the registry at 161 |
| `fps` | 16 | playback rate of the file |
| `width`, `height` | from the still | 1280x720 landscape / 720x1280 portrait when unset; both or neither |
| `mode` | `quality` | `fast` loads the Wan 2.2 Lightning 4-step pair ahead of yours: 4 steps, cfg 1, shift 5 |
| `steps`, `guidance`, `shift` | the mode's | quality 20 / 3.5 / 8.0 (the official template's); fast 4 / 1.0 / 5.0 |
| `seed` | −1 (random) | the response says which was used |
| `output_url`, `result_url` | — | the grant pair; minted by the backend |
| `op: "ping"` | — | answers what the worker sees on the volume, no GPU work; `runpod-endpoint-up.sh` uses it |

Response: `{"result", "cost", "seconds", "render_seconds", "bytes", "frames",
"fps", "width", "height", "seed", "end_frame", "loras", "worker"}`, or
`{"error": "<why>"}` for a request the handler refused (the run is closed
`failed` with that reason). `cost` is `seconds × STUDIO_USD_PER_SECOND`
from the template — Runpod prices a custom endpoint by worker time and
sends no figure, so the worker computes it from the price the template
was created with (`runpod-common.sh`, H100 flex).

**LoRA cache.** `models/loras/studio-cache/<sha256 of the URL without its
query>[:40].safetensors` on the volume. The query is the signature, which
changes every submit; the path is the library's blob key, which does not —
so the second run with the same pair downloads nothing. Nothing prunes the
cache yet; a pair is 0.6 GB and the volume has 35 GB free.

## Code on the volume, image stock

The endpoint's template runs the **unmodified** `runpod/worker-comfyui:5.10.0-base`
with `bash /runpod-volume/studio/start.sh` as its start command: our
`start.sh` copies `handler.py` and `extra_model_paths.yaml` from the volume
into place, starts ComfyUI with our flags and then the handler.
`runpod-volume-setup.sh` puts the three files there (`--code-only` for a
code change; workers pick it up at their next cold start).

This is deliberate, not a shortcut around the Dockerfile:

- **No registry to keep alive.** Runpod pulls Docker Hub without auth; a
  private ECR image needs a repository policy for Runpod's roles plus a
  console-side registration (see the earlier `lora-lab-pod` experiment), and
  a plain registry credential for ECR expires in 12 h.
- **No Docker daemon needed** to ship a handler fix, and no 15 GB push.
- The image is one Runpod already caches on its hosts, which is most of a
  cold start.

The [`Dockerfile`](Dockerfile) bakes the same three files for a machine that
has a daemon and a registry (`--platform linux/amd64`, push, then
`runpod-endpoint-up.sh --image <ref>` — the start-command override is
dropped and the image's CMD runs). Both paths run the same handler against
the same ComfyUI.

## Build, deploy, tear down

```bash
./studio/scripts/runpod-volume-setup.sh          # once: volume (100 GB, US-CA-2) + weights + code; ~5 min on a pod
./studio/scripts/runpod-endpoint-up.sh           # template + endpoint (0..1 workers, idle 60 s) + a cold-start ping
#   → put the printed id into models.json / the e2e fixture as runpod/<id>
./studio/scripts/runpod-volume-setup.sh --code-only   # after editing handler.py
./studio/scripts/runpod-endpoint-down.sh         # endpoint + template; the volume stays (--volume removes it)
```

The key comes from `RUNPOD_API_KEY` or `~/.config/andreas-services/studio/prod.env`
— the same key the deployed API spends under. Never print it.

Prod's API needs `RUNPOD_API_KEY` (it has it: the public Wan endpoints use
it) and nothing new: the endpoint id is in the registry entry, which ships
in the image.

## Cost

| | |
|---|---|
| Idle | **$0** — min workers 0; a worker stops 60 s after its last job |
| Standing | the volume: 100 GB × $0.07/GB/month ≈ **$7/month** |
| Active | the GPU's flex price per second while a job runs — H100 $0.00116/s (~$4.18/h), A100 80 GB $0.00076/s. First in the list wins when in stock |
| A clip | see the measurements below: **$1.66 for 121 frames** (7.5 s) in quality mode with an end frame, on the serverless worker |
| Setup | one pod for the download (~$0.10 on an A40; the 4090 used for the code sync was cents) |

The public LoRA endpoint is $0.56 for its 8 s clip, so this is **not
cheaper** — it is the one that goes past 8 s, lands on a frame, and does
portrait. `mode: fast` brings a clip to about a third of the quality price.

### Measured, 2026-09-20

All 720x1280 (a portrait still), fp16 experts, the character's newest
trained pair on both experts, seed 8.

| Where | Job | Steps | Time | Cost |
|---|---|---|---|---|
| dev pod, H100 SXM | 81 frames, I2V | 20 (quality) | 11:50 render, **34 s/step** | pod time |
| dev pod, H100 SXM | 121 frames, FLF (end frame) | 20 | 11:47 render, 34 s/step — the same per step as 81 frames | pod time |
| dev pod, H100 SXM | 121 frames, FLF | 4 (fast) | **6:24** including both expert loads after a restart; ~18 s/step at cfg 1 | pod time |
| **serverless worker, H100 SXM** | 121 frames, FLF | 20 (quality) | **23:53** (1433 s), **70 s/step** | **$1.66** |
| serverless worker | `op: ping`, cold | — | 49 s to an answer (image cached on the host) | ~$0.06 |

**The serverless worker ran at half the pod's speed on the same GPU type**
(70 s/step against 34 s/step; the first model load took 71 s against 35 s).
Same image, same ComfyUI flags, same volume. Unexplained tonight — a
shared or throttled host, or the volume's read path on that host. Two
things to try first: `runpodctl serverless logs` on the next job to see
whether a different host is faster, and an A100 80 GB worker (second in
the GPU list) for comparison. The costs above are what a clip costs
**until that is understood**: ~$1.70 for 7.5 s in quality mode, about a
third of that in fast mode.

**Speed-ups not yet taken**: SageAttention in the image (needs the
Dockerfile path); fp8 experts with `--fast fp8_matmul` on H100 (costs LoRA
fidelity, see above). `--disable-dynamic-vram` was tried and changed
nothing.

## Limits and known edges

- **One worker.** `workersMax: 1` on purpose: a second one doubles the
  standing risk of an idle GPU and the volume's read bandwidth is shared.
  Two runs submitted together queue; the second waits.
- **Execution timeout 40 min** on the endpoint, 40 min `STUDIO_MAX_SECONDS`
  in the handler (interrupts ComfyUI). 161 frames at 20 steps is ~25 min.
- **The still is centre-cropped** to the requested aspect by
  `WanImageToVideo`; a 3:4 still into 720x1280 loses its top and bottom.
- **The end frame is a condition, not a guarantee**: Wan lands on it
  closely, not pixel-exactly.
- **The grant pair lasts 6 h** (`generate.OUTPUT_GRANT_TTL`); a job queued
  longer than that (a run submitted while the endpoint is throttled for
  hours) uploads to an expired URL and the run closes `failed`.
- `_unsigned_input` replaces `output_url` / `result_url` in the stored
  request with the "presigned URL studio did not store" marker, as it does
  for any URL-shaped field it cannot map to a send.
