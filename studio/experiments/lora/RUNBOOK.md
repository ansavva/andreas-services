# Character-LoRA experiment — runbook

**Question this answers:** does a per-character FLUX LoRA beat studio's
reference-image approach (nano-banana-pro + curated refs) on identity, on a
blind side-by-side?

**Posture: privacy-first.** Subject photos exist in studio S3, on a
single-tenant RunPod Secure Cloud pod, and nowhere else. No photo ever
touches a third-party model API. Everything subject-derived on the pod lives
on the **container disk** and is destroyed by `lora-lab teardown`. The one
thing that survives a teardown is the `/weights` network volume, and it is
allowed to survive **because nothing subject-derived may ever be on it** —
it holds public model weights and tools only, and `lora-lab pod verify`
audits that. Everything fetched lands under `local/`, which never leaves
this machine.

**Status of this tree:** experiment-grade and entirely gitignored
(`studio/experiments/` in the root .gitignore). Nothing deploys, nothing is
recorded in studio's catalog — the grids under `local/` are the only record
of on-pod generations. The one studio-recorded step is the Gate-2 baseline,
which is a normal billed run under hard rule #2 (full payload approval).

## The architecture (changed 2026-08-24)

The RunPod deployment split — after a session of SSH-assembled pods, slow-pod
pip lotteries and per-pod 20-45GB re-downloads:

| Layer | Carries | Where |
|---|---|---|
| **image** | code + deps: ComfyUI (pinned commit), PuLID nodes and their pip stack, pod scripts, an entrypoint that starts sshd + ComfyUI | `docker/`, pushed to ECR `lora-lab-pod`; RunPod pulls it via a repo policy |
| **volume** | every model weight, OneTrainer + its venv, the HF cache | 250GB Secure Cloud network volume, mounted `/weights`, survives pods |
| **env** | config + secrets: `PUBLIC_KEY`, `HF_TOKEN` | create-pod env vars; the entrypoint writes them to `/etc/lab.env` (0600) |
| **container disk** | ALL subject data: refs, dataset, training output, checkpoints, renders | `/workspace`, destroyed by Terminate — the privacy mechanism |

There is **no bootstrap step**. By the time SSH answers, ComfyUI is starting.
`pod verify` is the health check + privacy audit that replaced it.

Consequences to know:

- **The volume pins the datacenter.** Every pod must be rented where the
  volume lives, so create it (`volume up --dc …`) in a DC the console's
  Storage page shows with 4090 stock. The a5000/a6000 fallbacks on `pod up
  --gpu` matter more than they used to.
- **SSH remains only as the data/control channel** — the ComfyUI tunnel
  (still 127.0.0.1-only; RunPod's HTTP proxy would expose it unauthenticated)
  and scp/rsync for refs, datasets and checkpoints. Nothing is installed over
  SSH anymore.
- **Trained LoRA checkpoints are subject-derived** and therefore live under
  `/workspace/train` and link into `/opt/ComfyUI/models/loras/` — both
  container disk. extra-paths deliberately does not map `loras` to the volume.

**Known caveats, stated up front**

- **FLUX.1-dev is licensed non-commercial.** Fine for this personal library;
  any commercial use of LoRA outputs forces a re-decision (SDXL+InstantID, or
  a licensed FLUX tier).
- **An image LoRA does not load into LTX video.** The video step later needs
  its own LTX-architecture LoRA. This experiment validates the dataset+recipe
  and produces consistent stills that feed the existing video engines
  frame-first.
- **Two schema risks, both designed to fail fast with the fix visible:**
  RunPod's REST field names — now for `/networkvolumes` as well as create-pod
  (`adapters/runpod.py` prints the full error body) — and OneTrainer's config
  schema (`assets/train-config.template.json` carries its own re-derivation
  note; the ai-toolkit template is the fallback).
- The expansion step's likeness ceiling (PuLID ≈ close-but-not-exact)
  propagates into the LoRA. Gate 1 curation is the only defense: an
  almost-right candidate is poison, reject it.

## Prerequisites (once)

| What | Where |
|---|---|
| `RUNPOD_API_KEY` | `~/.config/andreas-services/studio/dev.env` (preferred) or `studio/.env` |
| `HF_TOKEN`, FLUX.1-dev license **accepted** on `black-forest-labs/FLUX.1-dev` | same file |
| SSH keypair; public key becomes a pod env var | `~/.ssh/id_ed25519.pub` (or `LORA_LAB_SSH_PUBKEY`; private via `LORA_LAB_SSH_KEY`) |
| RunPod account with Secure Cloud billing | runpod.io console |
| **The pod image, built and pushed** | `docker/build.sh` — creates the ECR repo, sets the RunPod pull policy, pushes, records the URI in `docker/IMAGE` |
| **ECR registered in RunPod** | console → Settings → Container Registry Authentication, AFTER the first `build.sh` run (RunPod validates the policy at registration) |
| **The weights volume** | `lora-lab volume up --dc <id>` — pick the DC from the console's Storage page, it must stock 4090s |
| `studio` CLI signed into **prod** | `scripts/prod-login.sh` |
| lab installed | `cd studio/experiments/lora && uv sync` |

**Costs.** RTX 4090 Secure Cloud ≈ $0.69/hr; a full cycle is 5–8 pod-hours
(~$3.50–5.50) plus a few dollars of Gate-2 baseline renders. Standing costs,
new with this architecture and deliberate: the volume ~$17.50/mo (250GB @
$0.07/GB/mo), ECR ~$2/mo storage, and ~$1–2 of AWS egress per **cold** image
pull (a fresh pod on a host that hasn't cached the image). When the
experiment concludes: `lora-lab volume down` and delete the ECR repo — the
RUNBOOK's Decision section is where that gets decided.

## Milestone 0 — smoke (do this before anything else)

```bash
scripts/prod-login.sh                       # prod session for the studio CLI
studio character selection <slug> --presign # proves refs + presign path; sanity-check the list
lora-lab volume up --dc <id>                # once ever: confirms cost, creates the volume
lora-lab pod up                             # confirms cost, rents the pod (pulls the image)
lora-lab pod verify                         # ssh + volume mount + ComfyUI + /weights audit
lora-lab smoke                              # one plain FLUX render, fetched to local/smoke/
lora-lab pod down                           # terminate unless continuing into Session A
```

`smoke` passing proves: RunPod REST create/status, the ECR pull, the volume
mount, SSH + tunnel, ComfyUI queue API, fetch. It renders a lighthouse,
deliberately — no subject data is on the pod yet. Its first run downloads
FLUX onto the volume; every later run, on any pod, finds it there.

## Milestone 0b — video engines (optional)

```bash
lora-lab smoke-video --engine ltx23    # or ltx098, ltx25, wan, wan14b
```

**This is not part of the LoRA experiment.** An image LoRA loads into none of
these, and nothing downstream consumes the clips. It answers the prior
question — can this pod drive a local video model at all, and which is worth
building a video-LoRA recipe on — before phase 2 commits to one.

Weights are fetched on demand by the baked-in `pod-assets.sh` — see **Lazy
install** below. Clips land in `local/smoke/` as VP9 `.webm` (Chrome and VLC
play it; QuickTime does not).

On the 250GB volume the engines coexist — the old delete-to-make-room dance
is retired, with one exception: adding `flux2dev` (~54GB) to everything else
overflows 250GB, and the fix is growing the volume in the console (size only
increases) or deleting an engine you are done with under `/weights/models/`.

### Measured 2026-08-24, one RTX 4090, same prompt and seed throughout

| `--engine` | model | output | wall-clock | verdict |
|---|---|---|---|---|
| `ltx098` | LTX-Video 13B 0.9.8 dev fp8 (15.7GB) | 768x512, 97f @25fps | 77s | coherent, soft and hazy |
| `ltx23` | LTX-2.3 22B distilled fp8 (29.5GB) | 768x512, 97f @25fps | 53s | **much sharper than 0.9.8, and faster** |
| `ltx25` | LTX-2.5 22B distilled int8 (21.5GB) | 768x512, 97f @25fps | 70s | different, not clearly better than 2.3 |
| `wan` | Wan 2.2 TI2V 5B fp16 (10GB) | 1280x704, 49f @24fps | 93s | sharp, warm, strong detail |
| `wan14b` | Wan 2.2 T2V 14B fp8 pair (28.6GB) | 1280x720, 49f @16fps | 11m48s | smoother orbit, cooler grade, **7.6x the GPU time of the 5B** |

Wall-clock is per queued prompt including first-use model load, not pure
sampling. The 14B number is the one to weigh: on this card it costs 7.6x the
5B for a difference that is real but not seven-fold. (Measured on the old
architecture; model load now reads off the network volume rather than a
local disk, so first-load times may differ somewhat. Sampling is unchanged.)

`ltx23` beating `ltx098` on both quality and speed is the distilled 8-step
schedule — 29.5GB of weights against 24GB of VRAM, streamed from the pod's
503GB of system RAM, and still faster than a 13B that fits.

### Traps, measured the expensive way

**LTX-2.5 is gated.** `Lightricks/LTX-2.5` is `gated=auto`; the account behind
`HF_TOKEN` must accept its licence at huggingface.co/Lightricks/LTX-2.5 or
every file 403s with no other symptom. Accepted 2026-08-24. `LTX-2.3`,
`LTX-2.3-fp8` and `Comfy-Org/ltx-2` are ungated.

2.5 ships **split** — transformer, text encoder, VAE, audio VAE and duration
head as separate files — where 2.3 is one checkpoint. ComfyUI ships no local
workflow template for 2.5, only API-node ones, so `smoke-ltx25.json` was
derived from the 2.3 template: same sampler backbone, different loaders.
Stock ones turned out to be enough — `UNETLoader` takes the transformer,
`CLIPLoader` with `type=ltxv` auto-detects the Gemma-4 encoder, and the two
VAEs load through `VAELoader`. No `LTXAVTextEncoderLoader`, which 2.3 needs
only because its text encoder reads config out of the checkpoint.

**LTX-2.5 did not beat 2.3 here.** On the same prompt and seed it flew higher
and put more spray and haze in the air; 2.3 held more detail in the
lighthouse, and ran in 53s against 70s. One prompt and one seed is not a
verdict — but "newest" did not settle it, and if a video LoRA gets built,
2.3's shipped identity LoRAs (`id-lora-celebvhq`, `id-lora-talkvid`) are a
reason to weigh it seriously.

**Deleting weights frees nothing while ComfyUI is running.** It holds the
files open, so `rm` drops the name and `df` does not move; the next download
then dies of no space. Still true on the volume. Stop ComfyUI first —
`tmux kill-session -t comfy` — and `lora-lab` will restart it on the next
command that needs it.

### Why these variants

LTX at 22B reaches a 4090 only quantized. Wan's 5B is the variant Wan ships
for 24GB cards; the 14B is a mixture-of-experts pair sampled in two stages,
high-noise then low-noise, which is why it is two files and not one. Note the
VAEs differ: the 5B takes `wan2.2_vae`, the 14B pair takes `wan_2.1_vae`.

## Lazy install — what a fresh pod actually costs

**Nothing, once the volume is warm.** The image carries all code; the volume
carries all weights; a fresh pod is `pod up` → image pull → ComfyUI starting.
The first command that needs an engine still downloads it — **once ever, onto
the volume** — and every pod after that finds it mounted:

| Component | GB | Pulled in by |
|---|---|---|
| `encoders` | 6 | any of flux1dev / sd35 / ltx098 — CLIP-L + T5-XXL, shared |
| `flux1dev` | 13 | `--engine flux1dev`, `expand`, `validate` |
| `flux2dev` | 54 | `--engine flux2dev` — overflows the 250GB volume alongside everything else |
| `sd35` | 17 | `--engine sd35` |
| `ltx098` `ltx23` `ltx25` | 16 / 43 / 39 | that video engine |
| `wan` `wan14b` | 19 / 30 | that video engine |
| `pulid` | 3 | `expand`, `masks` — weights only; the nodes are baked into the image |
| `onetrainer` | 40 | `train` — OneTrainer venv + the FLUX.1-dev base |

Each component drops a `/weights/.asset-<name>-done` marker, which is how the
CLI knows what is present without listing the volume — and, being on the
volume, "present" survives pods. `pod-assets.sh` (baked into the image at
`/opt/lab/`) is idempotent; a re-run on a present component costs one ssh
round trip.

Two consequences worth knowing:

- **`train`'s first-ever run installs before it confirms.** OneTrainer plus
  the FLUX base is ~40GB; discovering that *after* answering "start
  training?" reads as a hang. Once on the volume, this cost is gone forever.
- **The OneTrainer venv is built by the image's python3.12.** If a future
  image tag moves the python minor version, the venv's shebangs break; the
  fix is deleting `/weights/tools/OneTrainer` and re-running `train`.

### Measured 2026-08-25 — the architecture's first full night

- `pod up` → verified ready: **~5 min** (20GB ECR pull included). Smoke on a
  warm volume: **6 min pod-time end to end**.
- Volume downloads at DC speed: **330MiB/s** (flux fp8 in ~35s). The whole
  lazy-install table above is a one-time cost now.
- First full training session (18-image dataset, 2000 steps / 112 epochs,
  masked, AdamW, COMFY_LORA out): **~56s/epoch on a 4090, 1h52m total**;
  8 periodic saves + final, 155MB each; 12-prompt validation grid per
  checkpoint. Whole chain unattended.
- Traps found and fixed en route, each recorded beside the code it bit:
  ssh draining piped stdin (`shell.run -n`), tmux outliving a crashed
  trainer (alive = trainer process), OneTrainer sampling crash class
  (sampling off; samples.json still required at startup), `SAFETENSORS` vs
  `COMFY_LORA` (silent save failure), bitsandbytes refusing 8-bit + bf16,
  EU-RO-1 stock drying up at night (rental retry loop), CUDA host filter
  (`allowedCudaVersions`).

## Generating from your own prompt

`smoke-video` answers "does this work". `gen` answers "what does it make" —
same graphs, same fetch, your prompt, any registered engine, image or video.

```bash
lora-lab gen --engine flux1dev --prompt "..."          # image
lora-lab gen --engine ltx23    --prompt "..."          # video
```

| Option | Notes |
|---|---|
| `--engine` | `flux1dev` `flux2dev` `sd35` (image); `ltx098` `ltx23` `ltx25` `wan` `wan14b` (video) |
| `--prompt` | required |
| `--negative` | video only — FLUX's graph has no negative node |
| `--seed` | default random, and **printed**, so a good accident is repeatable |
| `--width` `--height` | override the graph's default |
| `--length` | frames; video only |
| `--steps` | ignored by `ltx23` and `wan14b`, which have no single step count |
| `--out` | default `local/gen/` |

Anything an engine cannot take is **named** on stdout rather than dropped
silently — `note: flux1dev takes no --negative, --length`. Weights are
fetched on first use for that engine, so the first `gen` on a cold engine
downloads (to the volume, once ever) before it renders.

Everything under `local/gen/` is ad-hoc output. It is not part of the
experiment, is recorded nowhere, and is gitignored with the rest of this tree.

## Session A — expansion (~1.5–2.5 pod-hours)

```bash
lora-lab pod up && lora-lab pod verify      # if not already up
lora-lab refs <slug>       # mint presigned URLs, pull refs onto the pod
lora-lab expand <slug>     # ~20 variations x 2 seeds via PuLID-FLUX
lora-lab pod down          # or roll straight into Session B
```

Output: `local/<slug>/candidates/` + `candidates-sheet.png`.

### Gate 1 — curation (human, unhurried, free)

Pick **15–20** keepers into `local/<slug>/dataset/`. Reject: likeness drift
("almost right" is poison), anatomy errors, repeated near-duplicates. Aim for
spread across angle/lighting/expression/distance. If the subject's real
photos are usable quality, put them in too — weight them by duplication.
Then:

```bash
lora-lab captions <slug>   # scaffold .txt files; EDIT EACH (assets/captions.md)
```

## Session B — train + validate (~3–5 pod-hours)

```bash
lora-lab pod up && lora-lab pod verify      # a fresh pod is fine — the volume remembers
lora-lab masks <slug>                       # pushes dataset, writes face masks for masked training
lora-lab train <slug> --steps 2000          # confirms, then OneTrainer in tmux
lora-lab train-status <slug>                # watch; ~2–4h for 2000 steps on a 4090
lora-lab fetch-checkpoints <slug>           # pulls *.safetensors, links them for ComfyUI
lora-lab validate <slug>                    # 12 fixed prompts x each checkpoint
lora-lab teardown                           # remove subject data, TERMINATE
```

Checkpoints land every 250 steps; the interesting comparisons are usually
1000 / 1500 / 2000. Overfit shows as training wardrobe/backgrounds bleeding
into validation scenes that never asked for them.

## Gate 2 — baseline (billed, hard rule #2)

Render the same 12 prompts (`assets/validation-prompts.yaml`, `{trigger}`
replaced by a plain description) through **nano-banana-pro with the
character's references** as normal recorded studio runs — full PROMPT/INPUT
approval per submit, `--project` chosen explicitly.

## Phase 3 — scoring

Blind, shuffled A/B per prompt (LoRA best-checkpoint vs baseline). Score each
against the character's reference set and its profile `consistency` block:

| Axis | Scale |
|---|---|
| identity likeness | 1–5 |
| `consistency.must` all present / `never` all absent | pass/fail |
| prompt adherence | 1–5 |
| artifact severity | none / minor / disqualifying |
| overfit bleed (training wardrobe/pose/background in unrelated scenes) | count |

## Decision

- **Integrate (phase 2)** if the LoRA wins or ties identity on ≥70% of the 12,
  passes every must/never, and bleeds on ≤2. Phase-2 sketch: lift
  `adapters/runpod.py` + the domain modules into `studio_pipeline`; a provider
  seam beside the Replicate adapter; `LORA#` rows on the character mirroring
  `REF#`; a `models/` character folder + CLI folder support; then an
  LTX-architecture LoRA recipe for video.
- **Iterate once** if close: re-curate, re-caption, adjust steps; one retrain
  is inside budget.
- **Stop** if it still loses after one retrain, or expansion can't produce a
  curatable dataset from the refs. Write down why, here, before deleting
  anything. Then `lora-lab volume down` and delete the ECR repo
  (`aws ecr delete-repository --repository-name lora-lab-pod --force`) — the
  standing costs end with the experiment.

## Teardown invariants (every session)

1. `lora-lab teardown` (or `pod down`) — **Terminate**, never Stop: Stop keeps
   the container disk, keeps billing it, and keeps the photos in existence.
2. **The `/weights` volume survives Terminate, deliberately.** That is safe
   only while it holds public weights and tools and nothing else —
   `lora-lab pod verify` audits its top level and shouts at anything
   unexpected. Never point a dataset, a training output dir or a fetch at
   `/weights`.
3. Verify in the RunPod console: no pod. (The volume remains, by design, until
   the experiment's Decision.)
4. Presigned URLs self-expire (900s); `refs` deletes urls.json on both sides.
5. `local/<slug>/` stays on this machine; it holds subject data — treat it
   like the photos it contains.

## Storing the artifact

```bash
lora-lab store <slug> local/<slug>/checkpoints/<best>.safetensors
```

Uploads into the character's **corpus** pool via the studio CLI (300s PUT
window; on a slow uplink it may time out — keeping the file local-only is
fine, nothing in studio consumes a LoRA yet).
