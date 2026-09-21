---
name: studio-media-image
description: The FRAME-FIRST WORKFLOW for still images in the studio-* pipeline — why to render a frame before a video, how runs chain, the show-then-ask rule, how images reach Replicate (presigned S3 URLs only), and handing a still to a video engine. Use whenever the user wants to create, render, or edit an image, a frame, a poster, a thumbnail, or a start frame to animate, and whenever choosing between the image models. Each model has its own skill (studio-media-nano-banana-pro, studio-media-nano-banana-2, studio-media-gpt-image-2, studio-media-gpt-image-2-5-sunburst, studio-media-gpt-image-2-5-flare, studio-media-gpt-image-1-5, studio-media-seedream-5-pro, studio-media-krea-2-large, studio-media-flux-2-pro, studio-media-z-image-turbo); this covers what is true of all of them.
---

# studio-media-image — image generation as a recorded run

The **frame-first** engine of the **`studio-*`** family. Render a still on
Replicate, keep the whole submission as a run in S3, then animate the result.

The family:
- **`studio-media-image`** (this skill) — the image workflow, common to every image model.
- **`studio-media-core`** — the runner, the model registry, and validation.
- **`studio-media-prompt`** — authors prompts as structured JSON.
- **`studio-media-character`** — owns character identity: the bible + reference set.
- **`studio-media-seedance`** / **`studio-media-kling`** — render video, and can take this
  skill's output as their first frame.

## Why generate a frame before generating video

Both video engines force a choice: on Seedance, `image` and `reference_images`
are **mutually exclusive**, so you get identity *or* an exact composition, never
both. Generating the frame first collapses that trade-off — identity is baked
into the frame's pixels, so a start frame carries **both**.

It is also where the money is. An image is cents and a bad one is discarded for
free; a 5-second Kling clip at ~$0.168/s is ~$0.84 and a bad one is a total
loss. Iterate on the frame, spend on the motion once.

## THE RULE — S3 is the only origin

**Assets are never uploaded to Replicate.** Everything sent to a model must
already be in the media library, and it reaches Replicate only as a short-lived
**presigned URL** minted at submit time. Consequently `request.json` stores
**paths**, never signed URLs — they expire, they are ~2 KB of noise, and they
carry time-limited access that must not outlive the request.
The run store refuses to record a URL-shaped binding, so this is enforced in code.

To use a local file, put it in the library first — `studio upload` mints the
catalog record and the presigned PUT together, so no cloud credential is
involved (`studio-media-s3` skill). Working material for a piece of work belongs
in the project's input pool: `studio projects add-inputs <img> <project>`.

## The models — one skill each, one default

`--model` is **required** and is never inferred. The engines are otherwise peers,
chosen per shot rather than by house habit — with one standing exception:
**a character frame defaults to `gpt-image-2`**, because it holds reference
images at high fidelity automatically. Each has its own skill with its schema,
caveats and levers:

| `--model` | Skill | Reach for it when |
|---|---|---|
| `gpt-image-2` | [`studio-media-gpt-image-2`](../studio-media-gpt-image-2/SKILL.md) | Default for character frames. Dense text, precise edits, pixel-exact sizes, automatic high fidelity |
| `gpt-image-2.5-sunburst` | [`studio-media-gpt-image-2-5-sunburst`](../studio-media-gpt-image-2-5-sunburst/SKILL.md) | Newest OpenAI, tuned for **editing precision** — change one thing and keep the rest; `xhigh`/`max` quality for finals; transparent backgrounds endorsed. Priced per tier, `auto` bills like `xhigh` |
| `gpt-image-2.5-flare` | [`studio-media-gpt-image-2-5-flare`](../studio-media-gpt-image-2-5-flare/SKILL.md) | Sunburst's **fast** sibling — same schema and prices, tuned for speed and volume. Drafts and iteration; pay for Sunburst when the edit must be exact |
| `nano-banana-pro` | [`studio-media-nano-banana-pro`](../studio-media-nano-banana-pro/SKILL.md) | Legible text, 4K, ≤14 refs, tunable safety filter |
| `nano-banana-2` | [`studio-media-nano-banana-2`](../studio-media-nano-banana-2/SKILL.md) | Fast/cheap iteration; the extreme `1:4`…`8:1` ratios; search grounding |
| `gpt-image-1.5` | [`studio-media-gpt-image-1-5`](../studio-media-gpt-image-1-5/SKILL.md) | Transparent backgrounds, or fidelity dialled **down** |
| `seedream-5-pro` | [`studio-media-seedream-5-pro`](../studio-media-seedream-5-pro/SKILL.md) | Blending up to 10 references into one composition; flat per-image price; 2K ceiling |
| `krea-2-large` | [`studio-media-krea-2-large`](../studio-media-krea-2-large/SKILL.md) | Photoreal or painterly looks with no character in frame; a **style** transferred from ≤10 images; `creativity` from `raw` to `high`; a seed |
| `flux-2-pro` | [`studio-media-flux-2-pro`](../studio-media-flux-2-pro/SKILL.md) | **Editing** existing frames in words — ≤8 input images addressed by index; legible text; exact pixel sizes; a seed; per-megapixel price. No negative prompt |
| `z-image-turbo` | [`studio-media-z-image-turbo`](../studio-media-z-image-turbo/SKILL.md) | **Fast and cheap** — a flat $0.005 a draw on Runpod's endpoint, not Replicate; photoreal plates, legible English/Chinese text, a seed, a light image-to-image pass. No reference images |

```bash
studio models                    # the registry
studio models show <model>       # entry + LIVE schema + caveats
```

`openai/gpt-image-1` is deliberately **not** registered: it requires bringing
your own verified OpenAI key, where the others bill through Replicate.

**They are peers, not variants — assume nothing carries over.** Only `prompt`,
`aspect_ratio` and `output_format` exist on all four, and even those disagree
about values (Google spells a format `jpg`, OpenAI spells it `jpeg`; accepted
aspect ratios range from three values to eighteen). Never port a payload between
models by hand — `models show` prints the real schema, and the runner rejects a
mismatch before it bills.

To add a model, use [`studio-media-add-model`](../studio-media-add-model/SKILL.md).

## Generating

```bash
studio run --model gpt-image-2 --project <project> \
  --prompt "..." --character <name> --name <file>
```

One runner serves every model, image and video — see
[`studio-media-core`](../studio-media-core/SKILL.md).

`--character` does two things: it supplies that character's chosen reference
subset as identity, and it records the character on the run so
`studio runs find --character <name>` can answer later. It does **not** decide
where the run lands — every run belongs to a project, which is why
`--project` is required and never inferred. It is repeatable: one piece of work
can involve several characters.

Add `--slots 1,2,4` to use part of the resolved selection. `--extra '{"…"}'`
passes model-specific inputs. `--dry-run` prints the exact payload and submits
nothing.

### Validation — the whole payload, before anything is recorded

`--extra`, `--aspect-ratio`, and the image field are **all** checked against the
target model's live schema before the run is recorded and before anything bills.
Unknown fields, bad enum values and out-of-range numbers are rejected locally,
plus documented constraints the schema does not enforce. `--dry-run` runs the
same check, so the payload a person read is the payload that submits. When a field is
aimed at the wrong model, the error names the one that takes it:

```
$ studio run --model gpt-image-2 --project <project> --extra '{"input_fidelity":"high"}' …
error: openai/gpt-image-2 does not accept: ['input_fidelity']
  `input_fidelity` is accepted by: gpt-image-1.5
  valid inputs: ['aspect_ratio', 'background', 'input_images', …]
```

The full mechanism — `denied`, cross-field rules, the live schema pass — lives in
[`studio-media-core`](../studio-media-core/SKILL.md#what-runs-before-anything-bills).

## Runs — every submission is recorded

Writes through the shared run store:

```
<project>/runs/<run_id>/
    request.json    what we sent — references as S3 KEYS
    prompt.json     the studio-media-prompt source, when one was used
    result.json     prediction id, status, media types, output keys
    output/         the artifact(s)
```

The run **owns its output**. Medium is an attribute, never a folder name, so the
same shape holds for one video or ten images. The request is written *before*
submitting, so a failed render is still history.

```bash
studio runs list <project>
studio runs show <project>/latest
studio runs outputs <project>/latest --presign
```

## Chaining — feeding a run into the next one

Runs are addressed by **runref**: `<project>/<run_id>`, `<project>/latest`, a unique
name fragment, or a bare run id when the project is supplied out of band
(`--project`). Append
`#N` to pick the Nth output (1-based); the default is every output.

| Flag | Meaning |
|---|---|
| `--ref-run <runref>` | Use that run's output as **reference material** (repeatable) |
| `--image-run <runref>` | Use that run's output as the **primary image being edited** |
| `--key <s3 key>` | Use an explicit S3 object (repeatable) |

```bash
# refine a frame using the previous frame plus part of the curated set
studio run --model nano-banana-pro --project <project> --prompt "..." \
  --character <name> --slots 1,2 --ref-run <project>/latest#1 --name <file>

# then animate it — the payoff
studio run \
  --model kling --project <project> --input-file input.json --character <name> \
  --start-run <project>/latest#1 --name <file> --poll
```

Inputs are de-duplicated and order is preserved: `--image-run` first, then the
character's set, then `--ref-run`, then `--key`.

## Hard rule #2 (MANDATORY) — the FULL payload, as two JSON documents

**Nothing runs unless a person tells it to.** Show the complete payload as the two documents — `PROMPT` then `INPUT` — ask, and submit only when told. `--dry-run` renders exactly that and bills nothing. The submit command (`studio run`, or `studio runs submit` on a draft) IS the act; there is no separate approve step. Show the payload again after **any** edit: a yes to a plan, to a menu answer, or to a payload shown several messages ago is not an instruction to send the request about to go out. Every parameter, not just the prompt: a wrong `aspect_ratio` or a wrong
model bills exactly like a wrong prompt.

`--dry-run` renders it in the house format — two documents, because nesting the
prompt inside the payload double-escapes it into one unreadable line:

```
===== 1/2  PROMPT — serialized into the `prompt` string at submit time =====
Use the FIRST image as the base and keep it otherwise unchanged: …

===== 2/2  INPUT — the parameters this model receives =====
{
  "run": "run-<uuid>",
  "model": "google/nano-banana-pro",
  "endpoint": "https://api.replicate.com/v1/models/google/nano-banana-pro/predictions",
  "input": {
    "aspect_ratio": "match_input_image",
    "prompt": "<< see document 1/2 — PROMPT >>",
    "image_input": ["<presigned: <name>/reference/face/<file>.png>", …]
  }
}
```

`--dry-run --json` emits the raw payload plus its `bindings` instead, for
machines. The payload renderer is shared by every engine, so
image and video submissions review identically.

**Image prompts are prose, not a structured object.** `studio-media-prompt`'s
schema is camera/action/scene shaped and targets the video engines only
(`--engine seedance|kling-replicate`), so document 1/2 is the text verbatim here.

**Retrying an identical payload needs no second look — a changed payload does.** A transient
`E003 ModelRateLimitError` (Replicate capacity) can be retried with the identical
payload. Do NOT quietly set `allow_fallback_model: true` to get past it: that
reroutes to a *different model* (`bytedance/seedream-5`) than the one shown.

## A failure mode worth recognising

| Error | Means | Lever |
|---|---|---|
| `E003 ModelRateLimitError` | Replicate capacity, nothing to do with your payload | Retry unchanged, or move to another model. It can persist — Nano Banana Pro rejected 5 consecutive attempts in one 10-minute window after succeeding minutes earlier |

Keep "keep unchanged" clauses **short** when editing. Long enumerations of what
to preserve dilute the instruction and hurt edit quality, which is why the
ordering guidance above leads with the change.

## Handing a still to a video engine — mind the format

**GPT Image writes `.webp` by default, and Kling accepts only `.jpg/.jpeg/.png`.**
So a still rendered here cannot always be passed straight to `studio-media-kling` as a
start frame; the submitter rejects the binding up front rather than letting the
render fail. Convert first — the source run output is append-only history, so it
is copied, never re-encoded in place:

```bash
studio convert \
  --run <project>/latest#1 --for kling --add-input <project>
# -> <project>/input/<file>.png   (prints the new node)
```

`--for` converts only when the target engine would reject the current format and
otherwise prints the existing key untouched, so it is safe to run unconditionally
in a chain. Passing `"output_format": "png"` via `--extra` on a GPT Image run
avoids the round trip entirely.

## Ordering multiple image inputs

When editing one image using others as reference, **order is load-bearing**: the
base image goes first, references after. Name the roles in the prompt to match
(`the FIRST image` / `the SECOND and THIRD images`) rather than trusting the
model to infer them.

```bash
studio run --model nano-banana-pro --project <project> --name <file> \
  --key <project>/input/<file>.png \
  --character <name> --pick-tag face \
  --aspect-ratio match_input_image --prompt "Use the FIRST image as the base…"
```

`--key` comes first in the binding order, so the edit target leads and the
character's references follow. When the images you want are a character's, name
them with `--pick` / `--pick-tag` rather than raw `--key`s — the bible's index
says what each one shows, and the cap is enforced against the selection.

## Two characters in one frame — one at a time, never both at once

**Do not put two characters' reference sets in one generation.** A model
handed nine faces of two men and told which indices are whom still averages:
each figure comes back a composite, near enough to fool a glance and wrong on
every feature that matters. Measured, not assumed — one run of exactly that
shape produced two strangers who each half-resembled their source.

What works is a **chain of two runs, holding one identity per run:**

1. **The first character alone**, framed for the second. Their `default` set
   only, and the prompt says where they stand and that the other half of the
   frame is empty: "in the LEFT HALF of the frame, looking to the right at
   someone just out of frame; the RIGHT HALF is open space beside him".
2. **A Sunburst edit adding the second.** The first run's output is the edit
   target and goes first; the second character's face references follow; the
   prompt says *add a second man in the empty space*, *keep the first man and
   everything else exactly as it is*, and *the second man is the man in the
   remaining images, and ONLY him*.

```bash
studio run --model gpt-image-2.5-flare --project <project> \
  --character <name-1> --pick-tag default --aspect-ratio 3:2 \
  --name two-shot-step1 --prompt-file step1.txt

studio run --model gpt-image-2.5-sunburst --project <project> \
  --image-run <project>/latest --character <name-2> --pick-tag default,face \
  --aspect-ratio 3:2 --name two-shot-step2 --prompt-file step2.txt
```

Sunburst is what makes step 2 hold: it treats the photo as ground truth and
paints only what the instruction names, so the first character survives
pixel-for-pixel and the only face it draws is the second's. A third character
is a third link in the same chain. Wardrobe, height and build for each figure
go in the prompt from each bible — the references carry the face; the prompt
carries the rest, including "a little shorter than the first man" so the two
read at their own heights rather than the model's default.

## A new two-person pose, built in three stills

A companion to the [re-pose chain](#re-pose-one-person-per-generation) —
one figure per generation — for a pose where the two end up **close and
face-to-face**, measured 2026-09-18. Sunburst flags that one (`E005`) when a
shirtless man is already in the frame, so the whole chain runs on
[`nano-banana-pro`](../studio-media-nano-banana-pro/SKILL.md), and the skin
comes off last:

1. **Re-pose the first figure alone** from a single-figure base still —
   "reproduce it exactly … change only his pose".
2. **Add the second figure CLOTHED.** Nano Banana Pro binds identity better
   dressed, and most character references are dressed anyway. Name the
   references in the prompt and describe the person **from them** — told
   "hair short and neat" with the references bound but unnamed, it invented a
   stranger.
3. **Remove the shirt as a one-thing edit** — the only change in that prompt.

```bash
studio run --model nano-banana-pro --project <project> \
  --input <N> --aspect-ratio match_input_image --name pose-1 \
  --prompt "Reproduce the image exactly … change only his pose: …"

studio run --model nano-banana-pro --project <project> \
  --input <M> --character <name-2> --pick-tag default,face \
  --aspect-ratio match_input_image --name pose-2 \
  --prompt "Use the FIRST image as the base … add the man from the SECOND and THIRD images, dressed as he is there, …"

studio run --model nano-banana-pro --project <project> \
  --input <K> --aspect-ratio match_input_image --name pose-3 \
  --prompt "Reproduce the image exactly; the only change: the man on the left is now shirtless."
```

**The `E005` is about the pose, not the skin.** Sunburst passed the same two
men, one shirtless, when they were not face-to-face — hands on the shoulders
from behind — and flagged them a foot apart, eyes locked. Read the flag as
"this blocking", not "this wardrobe".

**Faces LEVEL and facing each other is geometry every engine renders.** One
person bending down over another's head is not, on any of them; when a
pose keeps coming back wrong, redesign the blocking rather than reword it —
a lean-in with one hand on the desk and one on the chair arm worked where
the bend-over did not.

## Character work

Load the bible first (`studio-media-character`: `studio character show <name>`) and render
from the reference set — never from memory. Verify the result against the
bible's `consistency` block before animating it; a drifted frame propagates
into every video made from it.

Note that a generated frame promoted into a character's `reference/` is model
output re-entering as identity input, which compounds drift. A frame pulled off
a run belongs in the **project's** input pool; promoting one into a character is
a deliberate curation decision, and it should be described in the bible when it
happens — copy it into the character and tag it (`studio describe <node> --tag default --tag face`).

## Re-pose one person per generation

A two-person frame is built one identity per run — one figure rendered alone,
the second added by a Sunburst edit that holds the first pixel-for-pixel. The
same rule holds when the frame exists and a figure has to **move**: an edit
that re-poses two people at once either blends them or is flagged (Sunburst
returned `E005` on "eyes locked, a foot apart" with a shirtless figure in the
frame). Measured 2026-09-18. The chain that works:

1. **Re-pose the first figure alone**, on `nano-banana-pro`, from the
   single-figure base still — "reproduce it exactly … change only his pose".
   `safety_filter_level: block_only_high` re-poses a shirtless figure without
   complaint.
2. **Add the second figure with Sunburst**, that character's references after
   the edit target, the prompt saying the first figure and everything else
   stay exactly as they are.

```bash
studio run --model nano-banana-pro --project <project> \
  --input <N> --aspect-ratio match_input_image --name repose-step1 \
  --prompt "Reproduce the image exactly … change only his pose: …"

studio run --model gpt-image-2.5-sunburst --project <project> \
  --image-run <project>/latest --character <name-2> --pick-tag default,face \
  --name repose-step2 --prompt-file step2.txt
```

**Pass only the references that match the target angle.** Redrawing a
character in profile wants the profile face reference and the profile body
reference, and nothing else: adding the front-face reference pulled the result
frontal and lost the nose. `--pick-tag` with the angle's tag is the selector;
`--character` alone sends the whole `default` set.

## Seed quality before a video engine

Two levers at generation time, and one after. `nano-banana-pro` takes
`resolution: "2K"` (its default — check the payload, `1K` is the soft one);
Sunburst takes `quality: "high"` for the frame that ships (`medium` is the
registry default, priced per tier). Everything else is
[`studio-media-image-upscale`](../studio-media-image-upscale/SKILL.md) on the
finished still. A video engine inherits the seed's softness and never adds
detail back.

## What the image engines refuse

The line is a kiss, and it sits in different places per engine — measured
2026-09-18. `gpt-image-2.5-sunburst` refuses a kiss still, and flags an edit
that re-poses a shirtless man together with a second man (`E005`).
`seedream-5-pro` renders one: "kissing on the lips" passes, clothed or
shirtless, where "French kiss" / "open-mouthed" wording was refused.
`nano-banana-pro` at `block_only_high` re-poses a shirtless figure. The
video side of the same map is on
[`studio-media-scene`](../studio-media-scene/SKILL.md#what-each-engine-will-actually-render--contact-between-two-people).
