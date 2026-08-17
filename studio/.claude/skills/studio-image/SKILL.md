---
name: studio-image
description: The FRAME-FIRST WORKFLOW for still images in the studio-* pipeline — why to render a frame before a video, how runs chain, the approval gate, how images reach Replicate (presigned S3 URLs only), and handing a still to a video engine. Use whenever the user wants to create, render, or edit an image, a frame, a poster, a thumbnail, or a start frame to animate, and whenever choosing between the image models. Each model has its own skill (studio-nano-banana-pro, studio-nano-banana-2, studio-gpt-image-2, studio-gpt-image-1-5); this covers what is true of all of them.
---

# studio-image — image generation as a recorded run

The **frame-first** engine of the **`studio-*`** family. Render a still on
Replicate, keep the whole submission as a run in S3, then animate the result.

The family:
- **`studio-image`** (this skill) — the image workflow, common to every image model.
- **`studio-core`** — the runner, the model registry, and validation.
- **`studio-prompt`** — authors prompts as structured JSON.
- **`studio-character`** — owns character identity: the bible + reference set.
- **`studio-seedance`** / **`studio-kling`** — render video, and can take this
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
already be an S3 object, and it reaches Replicate only as a short-lived
**presigned URL** minted at submit time. Consequently `request.json` stores S3
**keys**, never signed URLs — they expire, they are ~2 KB of noise, and they
carry time-limited bucket access that must not outlive the request.
`runs.py` refuses to record a URL-shaped binding, so this is enforced in code.

To use a local file, upload it to S3 first (`studio-s3` skill), then reference its key.

## The models — peers, no default, one skill each

`--model` is **required**. The engines are peers, chosen per shot, not by house
habit. Each has its own skill with its schema, caveats and levers:

| `--model` | Skill | Reach for it when |
|---|---|---|
| `nano-banana-pro` | [`studio-nano-banana-pro`](../studio-nano-banana-pro/SKILL.md) | Default for character frames. Legible text, 4K, ≤14 refs, tunable safety filter |
| `nano-banana-2` | [`studio-nano-banana-2`](../studio-nano-banana-2/SKILL.md) | Fast/cheap iteration; the extreme `1:4`…`8:1` ratios; search grounding |
| `gpt-image-2` | [`studio-gpt-image-2`](../studio-gpt-image-2/SKILL.md) | Newest OpenAI. Dense text, precise edits, pixel-exact sizes, automatic high fidelity |
| `gpt-image-1.5` | [`studio-gpt-image-1-5`](../studio-gpt-image-1-5/SKILL.md) | Transparent backgrounds, or fidelity dialled **down** |

```bash
uv run $STUDIO models                    # the registry
uv run $STUDIO models show <model>       # entry + LIVE schema + caveats
```

`openai/gpt-image-1` is deliberately **not** registered: it requires bringing
your own verified OpenAI key, where the others bill through Replicate.

**They are peers, not variants — assume nothing carries over.** Only `prompt`,
`aspect_ratio` and `output_format` exist on all four, and even those disagree
about values (Google spells a format `jpg`, OpenAI spells it `jpeg`; accepted
aspect ratios range from three values to eighteen). Never port a payload between
models by hand — `models show` prints the real schema, and the runner rejects a
mismatch before it bills.

To add a model, use [`studio-add-model`](../studio-add-model/SKILL.md).

## Generating

```bash
STUDIO=.claude/skills/studio-core/scripts/studio.py

uv run $STUDIO run --model nano-banana-pro --project <project> \
  --prompt "..." --character <name> --slug <slug>
```

One runner serves every model, image and video — see
[`studio-core`](../studio-core/SKILL.md).

`--character` does two things: supplies the chosen reference subset as identity,
names the run's owner, and puts the run under that character in S3. Add
`--slots 1,2,4` to use part of the set. `--extra '{"…"}'` passes model-specific
inputs. `--dry-run` prints the exact payload and submits nothing.

### Validation — the whole payload, before anything is recorded

`--extra`, `--aspect-ratio`, and the image field are **all** checked against the
target model's live schema before the run is recorded and before anything bills.
Unknown fields, bad enum values and out-of-range numbers are rejected locally,
plus documented constraints the schema does not enforce. `--dry-run` runs the
same check, so an approved payload is a payload that submits. When a field is
aimed at the wrong model, the error names the one that takes it:

```
$ uv run $STUDIO run --model gpt-image-2 --project <project> --extra '{"input_fidelity":"high"}' …
error: openai/gpt-image-2 does not accept: ['input_fidelity']
  `input_fidelity` is accepted by: gpt-image-1.5
  valid inputs: ['aspect_ratio', 'background', 'input_images', …]
```

The full mechanism — `denied`, cross-field rules, the live schema pass — lives in
[`studio-core`](../studio-core/SKILL.md#what-runs-before-anything-bills).

## Runs — every submission is recorded

Writes through the shared store, [`studio-s3/scripts/runs.py`](../studio-s3/scripts/runs.py):

```
projects/<project>/runs/<YYYY-MM-DD_HH-MM-SS>_<slug>/
    request.json    what we sent — references as S3 KEYS
    prompt.json     the studio-prompt source, when one was used
    result.json     prediction id, status, media types, output keys
    output/         the artifact(s)
```

The run **owns its output**. Medium is an attribute, never a folder name, so the
same shape holds for one video or ten images. The request is written *before*
submitting, so a failed render is still history.

```bash
RUNS=.claude/skills/studio-s3/scripts/runs.py
uv run $RUNS list <project>
uv run $RUNS show <project>/latest
uv run $RUNS outputs <project>/latest --presign
```

## Chaining — feeding a run into the next one

Runs are addressed by **runref**: `<project>/<run_id>`, `<project>/latest`, a unique
slug fragment, or a bare run id when `--character` supplies the owner. Append
`#N` to pick the Nth output (1-based); the default is every output.

| Flag | Meaning |
|---|---|
| `--ref-run <runref>` | Use that run's output as **reference material** (repeatable) |
| `--image-run <runref>` | Use that run's output as the **primary image being edited** |
| `--key <s3 key>` | Use an explicit S3 object (repeatable) |

```bash
# refine a frame using the previous frame plus part of the curated set
uv run $STUDIO run --model nano-banana-pro --project <project> --prompt "..." \
  --character <name> --slots 1,2 --ref-run <project>/latest#1 --slug <slug>

# then animate it — the payoff
uv run .claude/skills/studio-core/scripts/studio.py run \
  --model kling --project <project> --input-file input.json --character <name> \
  --start-run <project>/latest#1 --slug <slug> --poll
```

Inputs are de-duplicated and order is preserved: `--image-run` first, then the
character's set, then `--ref-run`, then `--key`.

## Approval gate (MANDATORY) — the FULL payload, as two JSON documents

**Show the user the complete `input` object and wait for explicit approval before
submitting.** Every parameter, not just the prompt: a wrong `aspect_ratio` or a
wrong model bills exactly like a wrong prompt. Re-approve after *any* edit.

`--dry-run` renders it in the house format — two documents, because nesting the
prompt inside the payload double-escapes it into one unreadable line:

```
===== 1/2  PROMPT — serialized into the `prompt` string at submit time =====
"Use the FIRST image as the base and keep it otherwise unchanged: …"

===== 2/2  INPUT — the parameters this model receives =====
{
  "run": "<name>/2026-01-31_09-15-00_<slug>",
  "model": "google/nano-banana-pro",
  "endpoint": "https://api.replicate.com/v1/models/google/nano-banana-pro/predictions",
  "input": {
    "aspect_ratio": "match_input_image",
    "prompt": "<< see document 1/2 — PROMPT >>",
    "image_input": ["<presigned: characters/<name>/reference/<name>_11.png>", …]
  }
}
```

`--dry-run --json` emits the raw payload plus its `bindings` instead, for
machines. The renderer is shared (`s3/scripts/runs.py: render_payload()`), so
image and video submissions review identically.

**Image prompts are prose, not structured JSON.** `studio-prompt`'s schema is
camera/action/scene shaped and targets the video engines only
(`--engine seedance|kling-replicate`), so document 1/2 is a plain string here.

**Retrying is not re-approving — but changing the payload is.** A transient
`E003 ModelRateLimitError` (Replicate capacity) can be retried with the identical
payload. Do NOT quietly set `allow_fallback_model: true` to get past it: that
reroutes to a *different model* (`bytedance/seedream-5`) than the one approved.

## A failure mode worth recognising

| Error | Means | Lever |
|---|---|---|
| `E003 ModelRateLimitError` | Replicate capacity, nothing to do with your payload | Retry unchanged, or move to another model. It can persist — Nano Banana Pro rejected 5 consecutive attempts in one 10-minute window after succeeding minutes earlier |

Keep "keep unchanged" clauses **short** when editing. Long enumerations of what
to preserve dilute the instruction and hurt edit quality, which is why the
ordering guidance above leads with the change.

## Handing a still to a video engine — mind the format

**GPT Image writes `.webp` by default, and Kling accepts only `.jpg/.jpeg/.png`.**
So a still rendered here cannot always be passed straight to `studio-kling` as a
start frame; the submitter rejects the binding up front rather than letting the
render fail. Convert first — the source run output is append-only history, so it
is copied, never re-encoded in place:

```bash
uv run .claude/skills/studio-s3/scripts/s3_convert.py \
  --run <project>/latest#1 --for kling --add-input <name>
# -> projects/<project>/input/<project>_in_<n>.png   (prints the new key)
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
uv run $STUDIO run --model nano-banana-pro --project <project> --slug <slug> \
  --key projects/<project>/input/<project>_in_3.png \
  --character <name> --pick-tag face \
  --aspect-ratio match_input_image --prompt "Use the FIRST image as the base…"
```

`--key` comes first in the binding order, so the edit target leads and the
character's references follow. When the images you want are a character's, name
them with `--pick` / `--pick-tag` rather than raw `--key`s — the bible's index
says what each one shows, and the cap is enforced against the selection.

## Character work

Load the bible first (`studio-character`: `character.py show <name>`) and render
from the reference set — never from memory. Verify the result against the
bible's `consistency` block before animating it; a drifted frame propagates
into every video made from it.

Note that a generated frame promoted into a character's `reference/` is model
output re-entering as identity input, which compounds drift. A frame pulled off
a run belongs in the **project's** input pool; promoting one into a character is
a deliberate curation decision, and it should be described in the bible when it
happens (`character.py set-ref-desc`).
