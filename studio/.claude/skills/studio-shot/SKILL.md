---
name: studio-shot
description: Produce one finished SHOT end to end from a plain-language brief — plan the steps, render a still, then animate it — as a chain of recorded runs. Use whenever a request describes MOTION ("him doing X", "filmed from the front as he…", "a clip of…") rather than a single frame, or whenever a job needs more than one studio-* call in sequence. Owns the frame-first workflow, the approval gates between steps, the plan-as-JSON format the user approves before anything bills, and what the finished shot leaves behind in S3.
---

# studio-shot — one brief, one finished shot

The **orchestration** layer of the **`studio-*`** family. The other skills each
own one call; this one owns the *sequence* — turning "him doing pull-ups, filmed
from the front" into a plan, then into a still, then into a clip, with an
approval gate at each point where money moves.

| Skill | Owns |
|---|---|
| **`studio-shot`** (this) | the workflow: plan → still → animate → deliver |
| `studio-scene` | a piece **longer than one clip**: chained shots, stitched |
| `studio-movie` | several finished **scenes** cut into one piece |
| `studio-character` | identity: the bible and the described reference library |
| `studio-prompt` | authoring a *video* prompt as structured JSON |
| `studio-image` | rendering one still |
| `studio-seedance` / `studio-kling` | rendering one video |
| `studio-s3` | the run store and format conversion |

## Why frame-first, always

A brief that describes motion still starts with a **still**. Three reasons, each
learned the expensive way:

1. **Both video engines force a choice.** On Seedance, `image` and
   `reference_images` are mutually exclusive — identity *or* an exact
   composition, never both. A generated start frame carries **both**, because
   identity is baked into its pixels.
2. **Iteration is cheap on the frame.** An image is cents; a Kling clip at
   ~$0.168/s is dollars, and a bad one is a total loss.
3. **Composition is decided where you can see it.** Framing, wardrobe, and
   equipment are settled in a still you can look at, so the video prompt only has
   to carry *motion*.

## The plan comes first, as JSON

**Before any step runs, show the user the whole plan** — every step, the model it
uses, and the prompt it will send — as JSON. This is the workflow-level version
of the full-payload approval gate: it lets the user redirect at step 1 instead of
after three billed calls.

```json
{
  "brief": "<the user's words, verbatim>",
  "shape": "still -> video",
  "steps": [
    {
      "n": 1,
      "skill": "studio-image",
      "produces": "the start frame",
      "model": "google/nano-banana-pro",
      "identity_from": "reference set (6 images)",
      "prompt": { "…the image prompt as JSON…" },
      "input": { "…the Replicate input…" },
      "output": "run {owner}/{ts}_{slug} -> output/{slug}.jpg",
      "gate": "approve payload; then eyeball the frame against the bible `consistency`"
    },
    {
      "n": 2,
      "skill": "s3",
      "produces": "a Kling-compatible copy, only if needed",
      "command": "studio convert --run {owner}/latest#1 --for kling --add-input {owner}",
      "gate": "none — no model call, nothing bills"
    },
    {
      "n": 3,
      "skill": "studio-kling",
      "produces": "the clip",
      "model": "kwaivgi/kling-v3-omni-video",
      "start_frame": "the run output from step 1",
      "prompt": { "…the studio-prompt JSON…" },
      "input": { "…the Replicate input…" },
      "output": "run {owner}/{ts}_{slug} -> output/{slug}.mp4",
      "gate": "approve payload (two-document review)"
    }
  ]
}
```

Steps that call a model carry a **gate**; steps that only move bytes do not.

## The workflow

### 1. Read the brief for medium

Motion words — *doing*, *filmed as*, *goes up and down*, *walks*, *turns* — mean
the deliverable is a **clip**, and the shape is `still -> video` even though the
user may have said "image". A single static description is `still` only.

### 2. Load identity before writing anything

`studio character show {name}` — render from the bible, never from memory. Note the
`consistency` block; it is what step 1's output gets judged against.

Choose the identity source deliberately:

- **New scene** (a gym, a poolside, anywhere not already photographed) → the
  **reference subset**, via `--character {name}` (plus `--pick-tag` when the
  default set is not the right one for this shot).
- **Editing an existing frame** → that frame from the **project's input pool**,
  via `--input N`. Do **not** pass `--character` as well; it drags the whole
  identity set into an edit that only needs one image.

### 3. Author the still prompt

Prose, not structured JSON — `studio-prompt`'s schema is camera/action/scene
shaped and targets the video engines only. Describe the **frame**, not the
motion: the pose at the *start* of the movement. For a repeated movement, that
is the bottom or rest position, so the clip has somewhere to travel.

**Dress the subject for the setting.** It suits the scene and it keeps the frame
on-brief.

### 4. Render, then actually look at it

Approve the payload, run it, then verify against the bible's `consistency` before spending
video money. A drifted frame propagates into every clip made from it.

**Regions the model invented deserve extra scepticism** — anything outside the
source crop (legs below a seated frame, a background that was not there) is
fabricated, not preserved.

### 5. Normalise the format

```bash
studio convert --run {owner}/latest#1 --for kling --add-input {owner}
```

Safe to run unconditionally: an already-accepted image is left untouched and its
key printed. GPT Image writes `.webp`; Kling takes only `.jpg/.jpeg/.png`.

### 6. Author the video prompt

Via `studio-prompt --engine kling-replicate` with `"start_image": true`. The
frame already fixes background, lighting, and wardrobe, so:

- **cut `scene` and `lighting`** — re-describing them makes the model fight the frame
- **shrink `subject`** to an identity anchor
- put the movement in `action`, the framing in `camera` — **one** move
- point `negative` at drift *and* at cuts, if the brief says one continuous take

### 7. Animate from the frame

```bash
studio run --model kling --project <project> \
  --input-file input.json --project {project} --prompt-json prompt.json \
  --start-run {name}/latest#1 --slug {slug} --poll
```

### 8. Deliver

Hand back the clip, its runref, and what to change if it is close. Because the
structured prompt is stored as `prompt.json` in the run, a revision edits one
field rather than rewriting a string — and on Kling, which has **no seed**,
holding everything else byte-identical is the only way a comparison means
anything.

## What a finished shot leaves behind

A **chain of runs**, not loose files:

```
projects/{project}/runs/{ts}_{slug}-frame/     request.json  prompt.json  result.json  output/frame.jpg
projects/{project}/runs/{ts}_{slug}/           request.json  prompt.json  result.json  output/clip.mp4
                                          ^ request.json binds start_image to the frame's S3 KEY
```

The second run's `bindings` name the first run's output key, so the lineage is
recorded rather than remembered. Failed attempts stay in the chain too — a run
that errored is history worth keeping, and it is how the failure modes in
`studio-image` came to be written down.

Curated folders are untouched by any of this: `reference/` only changes as a
deliberate curation decision, never as a side effect of a shot.

## Failure modes that interrupt a shot

Each is documented where it belongs; recognising them mid-workflow matters here:

| Symptom | Reality | Move |
|---|---|---|
| `E003 ModelRateLimitError` | Replicate capacity; nothing to do with the payload | Retry unchanged, or switch model. **Never** silently set `allow_fallback_model` — it renders on a different model than the one approved |
| `E006` | Shot durations must sum to `duration` | Guarded locally before submitting |
| Start frame rejected | `.webp` into Kling | Step 5 |
| Output looks identical to input | The edit was buried under preservation wording | Lead with the change; keep "keep unchanged" short |

## When NOT to use this skill

A single still with no motion → just `studio-image`. A clip from an existing
frame with no new still needed → just the engine skill. This skill earns its
place when a brief spans **more than one call** and the user should see the whole
plan before the first one bills.

**A piece longer than one clip → [`studio-scene`](../studio-scene/SKILL.md).**
This skill delivers *one* clip. When the brief outruns the engine's duration
ceiling (Kling stops at 15 s), or has beats that must flow rather than hard-cut,
the shape is `still -> video -> video -> …`: each part starts from the previous
shot's last frame and the shots are stitched into a scene. `studio-scene` owns
that loop, the continuity rules, and assembly.
