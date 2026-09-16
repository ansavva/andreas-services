---
name: studio-media-lora-train
description: Train a character LoRA for Wan 2.2 (the high/low-noise pair that runpod/wan-2-2-t2v-720-lora loads) as a recorded run of kind `training` — studio rents a Runpod GPU pod from the official ai-toolkit image, trains on the character's images tagged `dataset` with their descriptions as captions, files every checkpoint pair under <character>/models/, records pod-hours × rate as the cost and terminates the pod. Use when a character should be reproducible on video from a LoRA rather than from reference images, and for the retrain after an evaluation. Billed by the hour; nothing rents until `studio runs submit`.
---

# studio-media-lora-train

`runpod-pod/ai-toolkit-wan22-14b` — not a model but a **trainer**. A run
against it rents a machine with an 80 GB card, trains a Wan 2.2 14B LoRA on
a character's stills, and leaves a pair of `.safetensors` files per checkpoint
on the character — the pair [`studio-media-wan-2-2-i2v-lora`](../studio-media-wan-2-2-i2v-lora/SKILL.md)
loads. It is a run like any other: a draft with a plan and sends, a submit,
a callback or a reconcile, a cost. What is different is that the cost is
hours on a machine and the outputs are weights.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-2.2-lora-train …`,
> and `studio models show wan-2.2-lora-train` for the knobs. This page covers
> what is specific to training.

## What a LoRA is, in one paragraph

The model is a fixed table of fourteen billion numbers. Retraining it to know
one face would take days and produce a 28 GB file; a LoRA instead freezes the
model and learns a thin correction to it — a few hundred MB that says "adjust
these layers by this much." At inference the endpoint adds the correction onto
the frozen model from a URL, which is why the base never moves and only the
patch travels. Wan 2.2 samples in two stages, a high-noise expert (composition
and motion) then a low-noise one (detail), so a LoRA of a face is a **pair**.

## The dataset, before anything rents

| | |
|---|---|
| Which images | the character's files tagged **`dataset`** — bound with `--character <name> --pick-tag dataset`. 15–20 is the recipe; 5 is the floor; 40 the cap |
| What to pick | sharp, unobstructed face; only the subject in frame; spread across angle, distance, light, expression and **clothes**; no near-duplicates |
| Captions | each file's **description**, with the trigger put in front by the run. **Scene only, never the face**: `grey t-shirt, three-quarter view, golden hour, outdoor, waist-up`. The face is what the token learns; a described face is a face the model is told to ignore |
| Trigger | `trigger` — one made-up token every caption starts with and every later prompt will say, e.g. `ohwx_pt`. Required |

Write the captions in the app (the file's Description) or with `studio describe <node> --description "…"`.

## Invoke

```bash
# read the payload — which images, which captions, which card, the cost cap — and draft
studio run --model wan-2.2-lora-train --project <project> \
  --character <name> --pick-tag dataset \
  --extra '{"trigger":"ohwx_pt","steps":2000,"gpu":"a100"}' \
  --dry-run

# rent the machine (hard rule #2: this is the act)
studio runs submit <run>

# hours later — the callback closes it; locally, ask
studio runs show <run>
studio runs reconcile <run>
```

`--prompt` is refused: a trainer has no prompt. `--start-run`, `--ref-run`,
`--key` are refused for the same reason the sheet offers no tile — the
dataset is the character's, chosen by tag.

## The knobs

| | |
|---|---|
| `steps` | 250–4000, default **2000**. One step is one image through the model and one nudge to the LoRA; 2000 over 18 images sees each ~110 times |
| `save_every` | 250 (default) or 500 — a checkpoint pair per interval, the candidates the evaluation compares. Stop early if step 1000 already looks right: the later pairs are still filed |
| `rank` | 16 / **32** / 64 — the correction's thinness. 64 holds more and overfits sooner |
| `lr` | default 1e-4 |
| `resolution` | 512 / **768** / 1024 |
| `gpu` | **`a100`** (~$1.59/h secure) or `h100` (~$3.49/h). 80 GB trains bf16, unquantised. `4090` is listed and not yet supported by the job |
| `cloud` | **`secure`** (datacenter) or `community` (cheaper, peer hardware) |
| `base` | **`i2v`** — the base the inference endpoint runs; `t2v` for a text-to-video adapter |
| `max_hours` | 1–12, default **6**: the pod kills the trainer and reports `failed` past it. Billing cannot outlive this number |

## What it costs, and what it leaves

An A100 run of 2000 steps is roughly 1–2 h of training plus ~15 min pulling
the image and the ~70 GB base model: **about $3–5**. The run's `cost` is the
pod's hourly rate × the hours it existed, computed by the pod at the end.

Outputs land under **`<character>/models/`** as
`<trigger>-<run>_<step>_high_noise.safetensors` / `…_low_noise…` for each
save point, and the same without a step number for the final pair. The run
page lists them as file tiles; each opens a page with size, type and Download.

## After it succeeds — the evaluation

The same still, prompt and seed through `wan-2.2-i2v-lora` with each
checkpoint pair (`--lora-high-key` / `--lora-low-key`), plus once at
`lora_scale 0` as the untrained baseline. Score likeness and **bleed** —
training wardrobe or backgrounds turning up in scenes that never asked for
them. Bleed is overfitting: pick the earlier checkpoint, or retrain with
fewer steps and more varied images. A stranger is underfitting: more steps,
or better captions.

## Failure modes, named

- **`failed` — "trainer exited N"**: the log tail is in the run's response
  document. Most often a dataset image the trainer could not read.
- **`failed` — "the training pod is gone and reported no result"**: the
  machine died (a reclaimed host, an out-of-stock restart). Rerun.
- **A run stuck `running` past `max_hours`**: `studio runs reconcile <run>`
  reads the pod's report or its absence and closes it either way, terminating
  the pod if it is still there.
