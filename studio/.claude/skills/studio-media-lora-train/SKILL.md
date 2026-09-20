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
| `sample_prompts` | the stills drawn at every save point, one per prompt — see [Samples](#samples-the-face-emerging-a-save-point-at-a-time). Default four scenes; `[]` for none |
| `sample_seed` | default **42**, held across the run, so the only thing that changes down a column is the LoRA |
| `sample_steps` | sampler steps per still, default **20** |

## What it costs, and what it leaves

An A100 run of 2000 steps is roughly 1–2 h of training plus ~15 min pulling
the image and the ~70 GB base model: **about $3–5**. The run's `cost` is the
pod's hourly rate × the hours it existed, computed by the pod at the end.

Outputs land under **`<character>/models/`** as
`<trigger>-<run>_<step>_high_noise.safetensors` / `…_low_noise…` for each
save point, and the same without a step number for the final pair. The run
page lists them one row per save point, the pair beside it and that step's
samples under it; each file opens a page with size, type and Download.

**They appear as they land, not at the end.** The pod tells studio after each
checkpoint it uploads, so a pair shows up in `<character>/models/` and on the
still-`running` run within a minute of the trainer saving it — every ~8
minutes on an A100 at 250-step intervals. Evaluate the early pairs while the
later ones train. If a run is `running` and shows nothing where you expected
a pair, `studio runs reconcile <run>` files whatever has reached the bucket
without closing the run.

## Samples: the face emerging, a save point at a time

Weights are nothing to look at, and the first real run proved it: sixteen
files and no way to see whether the face was there without a video run by
hand against each pair. So at every save point the trainer also **draws one
still per `sample_prompts` entry** with the pair it just wrote — same
prompts, same seed each time, so reading down the list is watching the LoRA
and nothing else change. They land under **`<character>/models/samples/`**
as `<trigger>-<run>_<step>_sample_<i>.jpg` (the final step's unnumbered,
like the final pair) and the run page shows each row's strip under its pair,
as the samples arrive.

**What a sample is depends on `base`.** The `i2v` base — the default, the
one `wan-2.2-i2v-lora` runs — conditions every frame on a first image, at
training and at sampling alike: asked for a still from text alone it crashes
(`The size of tensor a (36) must match the size of tensor b (16)`, the
first run that tried, $0.66 lost). So on `i2v` **each prompt re-renders one
dataset photo**: the photos are dealt round-robin over the dataset in
manifest order — prompt 0 gets the first photo, prompt 1 the second, and so
on, wrapping — and the run records which (`training.samples`, one
`{index, prompt, ctrl_img}` per prompt). The still keeps the photo's
aspect. The prompt steers little; what you get is **this photo, through
this pair**. On `t2v` a prompt is text-only and draws the scene it names.

The defaults put the subject where a dataset usually does not — a kitchen, a
night street, a formal suit, a beach. On `t2v` that is the point: a sample
of the training scene only shows what was memorised. On `i2v` the words
matter less than the photo behind them, and there is no harm in leaving
them. Write your own with `{trigger}` where the token goes, and no `--` in
them — the trainer reads `--x` as a flag, and the job appends its own:

```bash
studio run --model wan-2.2-lora-train --project <project> \
  --character <name> --pick-tag dataset \
  --extra '{"trigger":"ohwx_pt","sample_prompts":["{trigger}, on a ski slope, goggles up, medium shot"],"sample_seed":7}' \
  --dry-run
```

`"sample_prompts": []` turns sampling off. Each prompt costs ~20 sampler
steps of a 14B model per save point — about a minute on an A100 for the
four defaults, so ~8 minutes over a 2000-step run.

**What to look for, down the column — on `i2v`, a photo re-rendered:**

| Reading | It says |
|---|---|
| the photo, clean, the same person | **intact** — the pair still renders its subject; take it to the evaluation |
| the same photo, a face drifting from it, colour shifted, smeared | **damage** — the pair has hurt the model; the row before this one, or a lower `lr` / fewer steps next time |
| a photo, a stranger in it | the token has not bound, or the low-noise expert has lost the face — read on, and evaluate on video |

Whether the face **travels** — into a scene the dataset never showed — an
I2V still cannot say; that is the evaluation's question, on video, below.

**On `t2v`, a scene imagined:**

| Reading | It says |
|---|---|
| a stranger, or a generic face | **underfit** — the token has not bound yet; read on, or more steps next time |
| the person, in the scene the prompt asked for | **right** — this is the pair to evaluate on video |
| the person, but wearing the dataset's clothes, in its lighting, against its backgrounds | **bleed** — overfitting; the pair before this one, or fewer steps and more varied images next time |
| the same face, then a slightly worse one | past the peak; the earlier row is the candidate |

A sample is a still off a video model at 20 steps, so judge likeness and
bleed, not polish.

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
- **`failed` at the first save point, log tail
  `The size of tensor a (36) must match the size of tensor b (16)`**: an
  `i2v` sample drawn from text alone. The job now hands every `i2v` sample a
  dataset photo (a prompt with a `--` of its own is refused at submit, since
  the trainer would read it as a flag); if it recurs, the trainer's image
  has changed how a sample takes its image — the pod log's `sample N
  re-renders <photo>` lines say what the job handed it.
- **`failed` — "the training pod is gone and reported no result"**: the
  machine died (a reclaimed host, an out-of-stock restart). Rerun.
- **A run stuck `running` past `max_hours`**: `studio runs reconcile <run>`
  reads the pod's report or its absence and closes it either way, terminating
  the pod if it is still there.
