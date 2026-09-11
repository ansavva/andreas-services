---
name: studio-media-image-upscale
description: Enlarge and restore an image that already exists, with Topaz Labs' upscaler (topazlabs/image-upscale) on Replicate as a recorded run. Use for low-resolution seed and reference material, phone-screenshot crops, and any source too small or too soft to hand a generator. The only model in the registry that restores rather than generates — it invents nothing, so identity survives it.
---

# studio-media-image-upscale

`topazlabs/image-upscale` — professional-grade super-resolution. **Every other
model here makes a picture; this one repairs the picture you have.** That is the
whole reason to reach for it: a seed photo is evidence of who someone is, and a
generative "upscaler" that redraws a face produces a better-looking image of a
slightly different person.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model image-upscale …`,
> and `studio models show image-upscale` for the live schema. This page covers
> only what is specific to this model.

## What is specific to this model

| | |
|---|---|
| Images field | `image` — a **single** image, bound with `--start-key` |
| Reference list | **none.** `--key`, `--character` and `--pick` do not apply |
| Prompt | **none.** It is the first model here that takes none |
| Accepts | `.jpg .jpeg .png .webp` |
| Output | `jpg` (default) or `png` |
| Scale | `None` (default) / `2x` / `4x` / `6x` |
| Enhancer | `Standard V2` · `Low Resolution V2` · `CGI` · `High Fidelity V2` · `Text Refine` |
| Faces | `face_enhancement` off by default; `_strength` 0.8, `_creativity` 0 |
| Framing | `subject_detection`: `None` / `All` / `Foreground` / `Background` |

**One image, bound as a start frame.** There is no reference array, so the
options that fill one are refused rather than ignored:

```bash
studio run --model image-upscale --project <project> \
  --start-key <node> --no-refs --name <output-name> \
  --extra '{"enhance_model":"High Fidelity V2","upscale_factor":"4x","face_enhancement":true,"face_enhancement_creativity":0}'
```

**No prompt.** `--prompt` is an error here, not a no-op: Topaz rejects a
payload carrying one.

## Which enhancer

| Source | Use |
|---|---|
| Long edge under ~600 px, visibly degraded | **`Low Resolution V2`** — built for exactly this |
| Merely soft, or already reasonably large | **`High Fidelity V2`** — preserves detail, adds least |
| Digital art, renders | `CGI` |
| Screenshots where legible text matters | `Text Refine` |
| Anything else | `Standard V2` |

**`face_enhancement_creativity` is the identity dial. Keep it at 0** for seed
and reference work. Above zero the model starts inventing plausible facial
detail, which is the one thing material that defines a character must not have.
`face_enhancement_strength` only controls how sharp the face is against the
background and is safe to leave at its default.

`subject_detection` reframes around whoever the model decides the subject is.
In a group photo that is a coin toss, so leave it `None` and crop before you
upscale — cropping first also stops you paying to enlarge background.

## It is priced on OUTPUT megapixels, not on time

One unit per 24 MP of result, and a unit is about $0.05. So the cost is set by
`upscale_factor` against the source size, not by how long it runs:

| Output | Cost |
|---|---|
| ≤ 24 MP | $0.05 |
| ≤ 48 MP | $0.10 |
| ≤ 96 MP | $0.20 |

A 2000 × 2800 source at `4x` lands at 89 MP and costs four times what the same
image at `2x` costs, for detail nothing downstream will read. **Pick the factor
from the size you actually want** — a long edge of 2000–3000 px keeps every
result in the cheapest band and is more than any engine here consumes.

## Where the result belongs

An upscale is a derived file, not a replacement. Keep the original: it is the
only record of what the source really contained, and a restoration is an
opinion about it. Land the result beside it under a name that says how it was
made, and put it into a character's pools deliberately —
`studio character add-to <name> seed <files>` for material, and — only once you
have looked at it, per hard rule #2b — a copy into the character's tree followed
by `studio describe <node> --tag default`. The tag is what makes an image
identity; the copy is what makes it this character's, because ownership is the
tree.

## How it goes wrong

Nothing here is a `denied` value — the README limits nothing the schema offers.
The failures are all failures of judgement about a restorer:

| Symptom | Cause | Fix |
|---|---|---|
| The face is sharp but subtly not the same person | `face_enhancement_creativity` above 0 | put it back to 0 and re-run; discard the first result rather than keeping it "because it looks better" |
| The result is framed on someone else | `subject_detection` other than `None` on a photo with more than one person | crop first, then upscale with detection off |
| A run cost four times what you expected | `upscale_factor` applied to an already-large source | the price is on output megapixels — check `source × factor` before submitting |
| Plastic skin, smeared hair | `Standard V2` on a badly degraded source | `Low Resolution V2`, which is trained for it |
| Output looks unchanged | `upscale_factor` left at its `None` default | it defaults to no enlargement; set `2x`/`4x`/`6x` explicitly |

The last one is the quiet one: `None` is a valid value and a valid *default*, so
a run that forgets the factor succeeds, bills, and returns the same size back.
