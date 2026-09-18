---
name: studio-media-wan-3-0-i2v
description: Animate one still into video with Alibaba's Wan 3.0 image-to-video (fal/alibaba/wan-3.0/image-to-video) on fal.ai's queue API as a recorded run — a required start frame, an optional end frame to land on, native audio, any length from 2 to 30 seconds. Use when a clip must open on a chosen frame (the frame-first workflow), when it must also close on one, when a character's identity is already in a still and no reference set is needed, or when a continuation clip needs more than 15 seconds in one pass. Per second at 480p/720p/1080p. For a clip from words alone use studio-media-wan-3-0-t2v; for references instead of a frame, studio-media-wan-3-0-r2v.
---

# studio-media-wan-3-0-i2v

`fal/alibaba/wan-3.0/image-to-video` — Wan 3.0 from a still, on **fal.ai**.
One required start frame, an optional last frame, a clip of 2–30 seconds
that opens on the first and — when given — lands on the second, with audio
generated in the same pass. The frame-first workflow every other video
engine here uses, plus the first-and-last interpolation only Veo and Seedance
also offer.

> Invocation, hard rule #2, run recording and validation are shared —
> see [`studio-media-core`](../studio-media-core/SKILL.md): `studio run --model wan-3.0-i2v …`,
> and `studio models show wan-3.0-i2v` for the schema. Everything about
> provider, price, duration, resolution, aspect, audio, seed, prompt
> expansion and thinking is as on [`studio-media-wan-3-0-t2v`](../studio-media-wan-3-0-t2v/SKILL.md);
> this page covers only what differs.

## What is specific to this model

| | |
|---|---|
| Start frame | `start_image_url` — **required.** Bound with `--start-run <run>` (its first output) or `--start-key <node>`; jpg/png/webp. The clip opens on it |
| End frame | `end_image_url` — optional. `--end-run` / `--end-key`. The clip lands on it; the model interpolates between the two |
| References | **none.** Identity comes from the frame. For a reference set use [`studio-media-wan-3-0-r2v`](../studio-media-wan-3-0-r2v/SKILL.md) |
| Aspect | `aspect_ratio: adaptive` (default) follows the start frame; a named ratio reframes it |
| Price | as t2v — per second by resolution; the frames cost nothing extra |

## Invoke

```bash
# animate the first output of a still run, five seconds at 720p
studio run --model wan-3.0-i2v --project <project> \
  --start-run <project>/<still-run> \
  --extra '{"duration":5}' \
  --prompt "…"

# open on one frame and land on another
studio run --model wan-3.0-i2v --project <project> \
  --start-run <project>/<frame-a> --end-run <project>/<frame-b> \
  --extra '{"duration":8,"resolution":"1080p"}' \
  --prompt "…"
```

## Prompting

The prompt describes **motion**, not the frame — the frame is already
there. Say what moves, how the camera moves, and what is heard. Anything
in the prompt that contradicts the still is a fight the still usually
wins. With an end frame, describe the path between the two rather than
either endpoint — and describe each endpoint **accurately** where you do
name it: a prompt that said "arms hanging in a V" against an end still with
the arms raised behind the head made the model jerk the arms up in the last
half-second to reach the still. The still wins; the words have to agree with
it.

### What worked — measured 2026-09-18

A start **and** an end frame, **12–18 s per clip carrying two or three
beats**, 720p, `enable_prompt_expansion: false`, `enable_thinking: false`,
and a prose prompt with a `Start:` line, a short paragraph per beat, and an
`End:` line. The model followed that shape better than one paragraph. fal's
note that expansion off "is likely to degrade generation quality" is written
for a terse prompt; a structured one carries what expansion would add, and
off is the setting these clips were measured with:

```
Start: <what the start frame shows>.

<beat one — a short paragraph>.

<beat two>.

End: <what the end frame shows>.
```

```bash
--extra '{"duration":15,"resolution":"720p","enable_prompt_expansion":false,"enable_thinking":false}'
```

- A 15 s clip carried five beats — a sip, a spill, a whistle off, a shirt
  off, a hand through the hair, back to the papers. The one it dropped was
  the object placement: the whistle went on the desk, not the floor. Where a
  thing must land is pinned by the end still, not by a sentence — see
  [`studio-media-scene`](../studio-media-scene/SKILL.md#the-end-frame-is-where-control-lives).
- Natural reactions — a glance, a breath, a laugh — render well when each is
  written as a beat of its own.
- Chaining keeps colour: `studio frames last <run> --add-input` off the
  previous clip is the next clip's `--start-key`, and the grade carries.
- **Don't ask for one 30 s take.** The price is per second, so nothing is
  saved; only the first and last frames are anchored, so the beats between
  compress; and one bad beat re-rolls the whole clip. Two clips cost the
  same and re-roll separately.

## What it refuses, and what fal refuses

**A kiss between two adults is refused at submit.** HTTP `422` on
`body.prompt` for the wording; with the word removed, `422` on `body` — the
prompt and the start image together. Nothing is billed. Shirtless massage
and other contact clips pass. The map across every engine is on
[`studio-media-scene`](../studio-media-scene/SKILL.md#what-each-engine-will-actually-render--contact-between-two-people).

**`403 User is locked. Reason: TOP_UP` / `Exhausted balance` is fal's
account, not the payload.** Nothing is billed and the run lands `failed` — and
a failed run cannot be resubmitted; redraft it with `--again`, as
[`studio-media-core`](../studio-media-core/SKILL.md#a-failed-run-is-redrafted-not-resubmitted)
explains.

## Where it sits

The continuation engine of the Wan family: a
[`studio-media-scene`](../studio-media-scene/SKILL.md) chain renders each
clip from the previous clip's last frame, and this is the model that takes
that frame. Against [`studio-media-wan-2-6-i2v`](../studio-media-wan-2-6-i2v/SKILL.md)
it adds an end frame, any length to 30 s, portrait, audio, and loses the
negative prompt.
