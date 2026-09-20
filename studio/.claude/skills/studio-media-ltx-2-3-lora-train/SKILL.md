---
name: studio-media-ltx-2-3-lora-train
description: Train a character LoRA for Lightricks' LTX-2.3 22B (the single file that fal's ltx-2.3-22b/image-to-video/lora loads) as a recorded run of kind `training` — studio rents a Runpod GPU pod from the official ai-toolkit image, trains on the character's images tagged `dataset` with their descriptions as captions, files every checkpoint under <character>/models/, records pod-hours × rate as the cost and terminates the pod. Use when a character should be reproducible on LTX-2.3 video from a LoRA, or as the second trainer beside Wan 2.2's for the same dataset. Billed by the hour; nothing rents until `studio runs submit`.
---

# studio-media-ltx-2-3-lora-train

`runpod-pod/ai-toolkit-ltx23-22b` — not a model but a **trainer**, the
second one beside [`studio-media-lora-train`](../studio-media-lora-train/SKILL.md).
A run against it rents a machine with an 80 GB card, trains an LTX-2.3 22B
LoRA on a character's stills, and leaves **one** `.safetensors` file per
checkpoint on the character — the file
[`studio-media-ltx-2-3-i2v-lora`](../studio-media-ltx-2-3-i2v-lora/SKILL.md)
loads. Everything the Wan trainer's page says about the dataset, the
captions, the trigger, hard rule #2, what lands where and when, and the
failure modes holds here unchanged. This page is what differs.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model ltx-2.3-lora-train …`,
> and `studio models show ltx-2.3-lora-train` for the knobs. `ltx-2-lora-train`
> is an alias.

## What differs from the Wan trainer

| | |
|---|---|
| The model | LTX-2.3 22B, one transformer for text-to-video and image-to-video alike — so there is **no `base` knob**, and a checkpoint is **one file, not a pair** |
| The files | `<character>-<trigger>-<run>_<step>.safetensors` per save point, and the same without a step for the final one, under `<character>/models/`. The run page lists one link a row (`lora`) |
| What it fits in | the 22B checkpoint and its 12B text encoder are quantised on the pod to fit the card beside the activations; the LoRA itself trains in bf16. Not a knob |
| Samples | **text-only** stills, one per `sample_prompts` entry at each save point, filed under `<character>/models/samples/` beside the checkpoint. Because the model imagines the scene rather than re-rendering a photo, a sample here shows whether the face *travels* — the question the Wan `i2v` samples cannot answer. `[]` turns them off |
| `steps` | default **1500** (Wan's is 2000): a 22B model holds a face sooner, and each step is slower |
| `gpu` | default **`h100`** — A100 placement failed twice the night this was added |
| Cost | an H100 is ~$3.49/h; 1500 steps are roughly 1–1.5 h plus ~15 min pulling a 46 GB checkpoint and a 24 GB text encoder — **about $4–6** an attempt |
| Which endpoint loads it | `ltx-2.3-i2v-lora` (fal), with `--lora-key` |

## Invoke

```bash
studio run --model ltx-2.3-lora-train --project <project> \
  --character <name> --pick-tag dataset \
  --extra '{"trigger":"ohwx_pt","steps":1500,"gpu":"h100"}' \
  --dry-run

studio runs submit <run>       # hard rule #2: this is the act
studio runs show <run>         # checkpoints appear as they land
```

## After it succeeds

The same still, prompt and seed through `ltx-2.3-i2v-lora` with each
checkpoint (`--lora-key`), plus once at `lora_scale 0` as the untrained
baseline — the evaluation the Wan page describes, on the other model. Score
likeness and bleed the same way. The two trainers take the same dataset, so
a character trained on both is the comparison between the models rather
than between two datasets.
