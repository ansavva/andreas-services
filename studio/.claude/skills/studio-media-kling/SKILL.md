---
name: studio-media-kling
description: Generate videos with Kling 3.0 / O3 Omni via kwaivgi/kling-v3-omni-video on Replicate (pay-per-second, reference_images for characters, locations, props and styles, native multi-shot). Use whenever a video is rendered on Kling rather than Seedance. Covers the model schema, native multi-shot up to 6 cuts, start/end frames, image-to-video prompting, naming references in the prompt with <<<image_N>>>, where dialogue has to sit, cross-clip consistency, and chaining into a scene. Pair with studio-media-prompt (--engine kling-replicate) and studio-media-character.
---

# studio-media-kling — Kling 3.0 / O3 Omni

The Kling rendering engine of the `studio-*` family. Kling is the counterpart to
`studio-media-seedance`: reach for it when you want native multi-shot, when a subject
needs more than ~3 beats, or when a draft renders better here than there.

Rendered with **`kwaivgi/kling-v3-omni-video` on Replicate** (`--engine
kling-replicate`), which reuses the Replicate token, upload helper and S3 flow
`studio-media-seedance` already has.

> Kling's own API (`api-singapore.klingai.com`) hosts the same models but bills
> against prepaid resource packages rather than per second, so it is not used
> here. A working client for it was removed in favour of Replicate; recover it
> from git history if a package is ever purchased.

The family:
- **`studio-media-prompt`** — authors the prompt. `--engine kling-replicate`
  compiles the object into the prose Kuaishou documents (see
  [below](#prose-not-json-what-kuaishou-actually-documents)), a `shots`
  timeline into the model's `multi_prompt` array, and emits a ready Replicate
  `input`.
- **`studio-media-character`** — `reference_images` here behaves like Seedance's, so a
  character's existing S3 reference set carries over. `studio character textblock`
  gives a pasteable identity anchor when driving from a start frame instead.
- **`studio-media-seedance`** — the other model family, with its own schema.
- **`studio-media-kling-v3-motion-control`** — the same house, a different
  job: the motion is copied from a reference clip rather than directed by a
  prompt. Reach for it when the movement already exists as footage.

## The model

`kwaivgi/kling-v3-omni-video` — <https://replicate.com/kwaivgi/kling-v3-omni-video>

| Input | Notes |
|---|---|
| `prompt` | **max 2500 chars.** Supports `<<<image_1>>>` / `<<<video_1>>>` template refs — see [below](#references-are-elements-not-just-characters--and-the-prompt-can-name-them). |
| `start_image` | First frame. `.jpg/.jpeg/.png`, **max 10 MB**, min 300px, aspect 1:2.5–2.5:1. |
| `end_image` | Last frame; requires `start_image`. |
| `reference_images` | "Elements, scenes, or styles" in the schema's own words — a character, a location plate, a prop, a style frame, and a request may mix them. **The cap of 7 counts the start frame too** — see below. 4 with a reference video. |
| `reference_video` | 3–10s, `.mp4/.mov`, ≤200 MB; `video_reference_type` `feature` (style/camera) or `base` (editing). Binds with `--clip-run` / `--clip-key`, or the sheet's **Source video** tile. |
| `multi_prompt` | JSON-encoded array `[{"prompt": "...", "duration": N}]`. **Max 6 shots, ≥1 s each, durations must sum to `duration`.** A beat's text may carry `<<<image_N>>>` — the README's own multi-shot example does. |
| `mode` | `standard` = 720p · `pro` = 1080p · `4k`. |
| `aspect_ratio` | `16:9` · `9:16` · `1:1`. **Required only when there is no start frame.** |
| `duration` | 3–15 seconds. |
| `generate_audio` | Default false. Mutually exclusive with a reference video. **On, it invents speech** unless a `dialogue` list gives it lines — see below. |

**No `seed` and no `negative_prompt`.** Negative direction goes in the prompt
text; `--engine kling-replicate` folds it in. With no seed, holding the prompt
byte-identical is the only reproducibility lever — see the locked template below.

**Audio is either directed or invented.** With `generate_audio: true` and a
`dialogue` list, Kling lip-syncs two short lines well in an 8 s clip under a
slow push-in. With `generate_audio: true` and no lines it invents dialogue —
on a kiss it did so even with `avoid` naming talking, speaking and dialogue,
and `avoid` is folded into the prompt, so nothing stronger exists here. A
clip that must be silent is `generate_audio: false`, with sound added in
post; Veo's real `negative_prompt` is the only field that suppresses speech
without switching audio off. **Lines land in the first ~10 s and drift after**
— see [below](#dialogue-holds-for-about-ten-seconds-then-lip-sync-drifts).

**Kling renders a kiss between two adults** — no refusal across several
runs, from a start frame with `reference_images`. The map across every
engine, and what each refuses, is on
[`studio-media-scene`](../studio-media-scene/SKILL.md#what-each-engine-will-actually-render--contact-between-two-people).

### Cost

| Mode | No audio | With audio |
|---|---|---|
| standard (720p) | **$0.168/s** | $0.224/s |
| pro (1080p) | $0.224/s | $0.28/s |
| 4k | $0.42/s | $0.42/s |

A 9s standard clip is ~$1.52. Iterate at `standard`, finish at `pro`.

## Hard constraints

| | |
|---|---|
| Duration | 3–15 s |
| Multi-shot | **6 cuts max**, ≥1 s each, summing to the total |
| Aspect ratio | 16:9 · 9:16 · 1:1 (ignored when a start frame is supplied) |
| Images | `.jpg/.jpeg/.png` only — **`.webp` is rejected**, so convert S3 references |
| Image COUNT | **7 in total**, start frame included — so 6 references at most alongside one |
| Start **and** end frame | **2 images TOTAL** — `reference_images` must be empty. See below |
| Prompt | 2500 chars |

`studio prompt --engine kling-replicate` enforces these as hard errors at
author time rather than after a spent generation.

### The image cap counts the start frame

`reference_images` takes up to 7, and a start frame may be combined with them —
which reads as 7 + 1 and is not. The limit is **seven images in total**, so a
start frame leaves room for six references. Exceeding it fails the prediction
outright:

```
Error code 1201: The number of images and elements exceeds the limit, max number is 7.
```

It fails fast and cheap, but only after a submit, and the two facts that produce
the mistake sit in different rows of the schema table above. With a character
whose `default_set` holds seven — a full face turnaround plus body angle images, which
is the shape `shoot` produces — binding `--character` and a start frame together
is over the line by exactly one. Narrow the selection with `--pick`; the start
frame already carries wardrobe and framing, so drop a body angle image rather than a
face one.

### An end frame clears the reference list

A start frame and `reference_images` combine happily — that is the whole reason
to reach for this model over Seedance. Add an **end** frame and that stops being
true: the request is then capped at those two images and rejected outright if
anything else is present.

```
Error (E006): Cannot use reference images together with end_image when
start_image is set (max 2 images with end frame).
```

Nothing in the live schema says so, and the fields are independently valid, so
this surfaces only after a submit. It is worth knowing because bracketing a shot
between two approved compositions is otherwise the strongest thing you can do
here — the prompt then only has to describe the movement between them. Just do
not also send references: the two frames have already fixed the look at both
ends.

Enforced locally, so it costs a message rather than a round trip.

## References are elements, not just characters — and the prompt can name them

The live schema's own wording for `reference_images` is "reference images for
elements, scenes, or styles". Character consistency is the common use and not
the only one: a **location plate**, a **prop**, an **animal** and a **style
frame** are all valid entries, and one request may mix them — four references
covering two people, a room and a dog is a documented shape, not an abuse —
and it is how the shots in the prompt pack below are actually built, with the
location plate tagged in the prompt like any other reference.

**The prompt can address them positionally.** `prompt` "Supports
`<<<image_1>>>`, `<<<video_1>>>` template references" — the index is the
reference's place in the `reference_images` array, 1-based, and `<<<video_1>>>`
is `reference_video`. That turns a reference list from a bag of hints into
something directable:

```
<<<image_1>>> and <<<image_2>>> stand in the room of <<<image_3>>>.
<<<image_1>>> rises and says "I got it". <<<image_4>>> trots in behind him.
```

`studio prompt --engine kling-replicate` does not emit these tokens — write
them into `subject`, `action` or a `shots[].description` and they reach the
wire verbatim, because the compiler serialises prose rather than escaping it.
**Confirm on the compiled string `studio prompt` prints before submitting**;
that check is free and the render is not.

**There is a second spelling in the wild: `@image1`.** Kuaishou's own product
uses `@`-prefixed tags — the 3.0 Omni guide writes characters as `@Name` — and
every working prompt in Dan Kieft's
[prompt pack](https://docs.google.com/document/d/1JxYJzqJ3ICCQsP_H9yZ0YsUE2jpeuDgvJe0ULBins18/edit)
tags reference slots that way instead: `background @image3`, `@image1 stands
up`, `@image4 naturally jumps up onto the desk`. Those prompts ran, so the
spelling works **through Kuaishou's own surface**. `<<<image_1>>>` is what
Replicate's schema documents, and that is the one to default to here; if a
render ignores the tags, the other spelling is the first thing to try, and
worth recording either way — neither has been sent from this repo.

Seedance's token is a third, `[Image1]`, and none of the three are
interchangeable: the wrong spelling is literal text in the prompt rather than
an error.

The 1-based ordering is read off the schema's wording, not measured here.
`studio runs show` prints the request's reference list in order, which is how
to check after the fact what `<<<image_2>>>` actually pointed at.

**What decides that order is the FLAG, and `--key` comes last.** `studio run`
builds the list in a fixed sequence: `--image-run`, then every `--character`,
then every `--location`, then `--ref-run`, then `--input`, then `--key`. So a character's picture bound with `--key` — the natural thing
to reach for when it is not tagged `default` — lands *after* the location
plate, and a prompt saying "the man from `<<<image_1>>>`" then points at an
empty room. Measured 2026-09-22 on a dev stack, and it is silent: every image
is valid, the caps pass, and only the render would show it. Bind identity with
`--character` + `--pick` / `--pick-tag` so it sorts first, and read the order
back off the dry run before submitting.

### More references is not more control

Consistency falls off as the list grows: the more elements a single generation
has to hold, the more likely one of them mutates — a reported four-reference
run grew a tail out of a dog's head while the two people held fine. The cap is
7; the working number is smaller. Spend the slots on what the shot cannot do
without, and settle anything fiddly in a **still** first.

Two corollaries worth having:

- **Three angles beat seven for one character.** Front, side and back is
  enough data to stop the model inventing a face it never saw, and it leaves
  slots for the location and the props. A character's full `default_set` is
  the wrong default here — `--pick` it down. Better still, spend **one** slot:
  a [composite
  plate](../studio-media-character/SKILL.md#a-composite-plate-puts-three-angles-in-one-slot)
  carries all three angles in a single image, which is what keeps room under
  the seven for a location and the previous clip's last frame.
- **A secondary character can be prose-only.** A described-but-unreferenced
  person stayed consistent across the cuts of a single multi-shot generation.
  Within one generation, description is enough for anyone who is not the
  subject; *across* generations it is not, which is what the locked template
  is for.

## Workflow

**No token export is needed, and no token at all.** The CLI holds no Replicate
credential — `studio run` asks the API to submit, and the API is what carries the
provider token. Older notes opening with `set -a; . ./.env; set +a` are a no-op.

```bash
# 1) author + validate; emits a ready Replicate input
studio prompt shot.json \
  --engine kling-replicate

# 2) submit as a recorded run — the shared submitter serves both video engines.
#    It records the run, mints presigned URLs at submit time, polls WITHOUT
#    Prefer:wait (a timed-out wait retries internally and bills duplicates),
#    and archives the finished video into the run.
studio run \
  --model kling --project <project> --input-file input.json \
  --character <name> --name <file> --poll
```

Bind images with `--start-run` / `--end-run` (→ `start_image` / `end_image`),
`--ref-run` (→ `reference_images`), or `--key` for an explicit S3 object; a
reference clip with `--clip-run` / `--clip-key` (→ `reference_video`). Unlike
Seedance, Kling lets a start frame and `reference_images` combine. Kling accepts
only `.jpg/.jpeg/.png`, and the submitter rejects a `.webp` binding up front
rather than letting the render fail.

**Show the user the exact payload and submit only when told** — every run
bills, and the submit command is the act.

Parsing note: Replicate's `logs` field can contain raw control characters, so
`json.loads(..., strict=False)` when reading a prediction. Strict parsing fails.

### Output — the run owns it

Every submission is a run under `<project>/runs/<run_id>/`,
holding `request.json` (inputs as S3 **keys**), `result.json`, and `output/` with
the video. `--poll` archives it automatically — download-then-upload, so bytes
never pass through the agent context. Replicate output URLs are not permanent.

**S3 is the only origin: assets are never uploaded to Replicate**, only presigned
from the bucket at submit time. Inspect runs with `studio runs`
(`list` / `show` / `outputs --presign`).

## Image-to-video: don't describe what the frame already shows

A start frame **already fixes** background, lighting, wardrobe and appearance.
Re-describing them makes the model fight the image and drift — the most common
image-to-video failure, and it reads as a model problem when it is a prompt
problem.

Set `"start_image": true` in the object and:

- **Cut `scene` and `lighting`.** The frame owns them.
- **Shrink `subject`** to an identity anchor — `"The man from the source image,
  unchanged — same face, hair, build and wardrobe"`.
- **Repoint `negative` at drift**: `changing face, changing hairstyle, changing
  build, changing background, changing wardrobe, cuts, scene changes`, plus the
  usual anatomy terms.
- **The frame sets the output shape.** `aspect_ratio` is ignored, so crop the
  frame to the ratio you want. Kling also normalises dimensions — a 1024×1024
  source came back 960×960.
- **Watch the frame edges for wide poses.** Elbows-out clips in a narrow crop.

The validator warns if `scene`/`lighting` survive or `subject` runs past ~40 words.

## Consistency across clips: lock the template, add only deltas

The largest source of multi-clip inconsistency is **workflow, not the model**.
Refining wording between generations is the natural impulse and it is the bug:
each reworded prompt is a slightly different creative direction, so every clip is
self-consistent but inconsistent with its neighbours.

**Write each character and environment once, reuse it byte-for-byte.** Per-clip
variation must be **additive on top of** the locked base, never substituted into
it. Freeze `subject`, `scene`, `style`, `lighting`; let only `shots` change. With
no seed available anywhere on Kling, this is the *only* reproducibility lever.

### Chaining beyond one generation

Full workflow — the loop, the continuity rules, the per-part verification gate
and assembly — lives in **[`studio-media-scene`](../studio-media-scene/SKILL.md)**. In short:

1. Render part 1 with `--scene <name>`, so it belongs to the scene.
2. Export its **last frame** with `studio frames last <runref> --add-input`;
   hand the node id to part 2 as `--start-key`.
3. Carry a **pose-continuity line** in part 2's `subject` — `"…, arms already
   raised in a bicep flex"` — so the pose doesn't reset on frame one.
4. Hold the locked base identical.
5. **Colour-match in assembly**; a hard cut amplifies small differences.

Put each part in the cut with `studio scenes add`, then `studio scenes
assemble`. Parts chained this way inherit their geometry from each other, so
the stitch is a stream copy with no re-encode.

**Binding the frame: `--start-key`, not `--key`.** `--key` adds an explicit S3
object to `reference_images`; the first/last frame flags are `--start-key` /
`--start-run` (and `--end-key` / `--end-run`). Passing a start frame via `--key`
silently produces a reference-image render instead — it validates and bills.

### Shorter clips drift less

Drift accumulates within a generation; faces and hands go first. If a clip falls
apart in its back half, cut beats or duration rather than rewording.

> In tension with the 6-cut ceiling: a 15 s six-cut run may drift more than three
> chained 5 s runs. Untested for *drift* — but see below: for a **continuous**
> piece the question does not arise, because `multi_prompt` beats are cuts.

### `multi_prompt` beats are CUTS — and they are the only timing control

Two verified facts that pull against each other, and the choice between them
should be put to the user before spending:

- **Every `multi_prompt` beat is a hard cut** — framing and often camera angle
  change at each boundary. Asking for "one continuous take" while passing
  `multi_prompt` cannot work; the field is the cause, so remove it rather than
  fighting it with wording.
- **`multi_prompt` is also the only way to control *when* things happen.** Each
  beat carries an explicit `duration`. Drop it and the model allocates the
  seconds itself: long or fiddly actions get compressed, and a beat you wanted
  held gets rushed. Phrases like `"within the first second or two"` and `"for the
  whole rest of the shot"` recover some of it, unreliably.

Getting both means **chaining** — one continuous take per part, cut where you
chose. See [`studio-media-scene`](../studio-media-scene/SKILL.md).

### Favour slow, deliberate motion

Kling is markedly more consistent on slow controlled movement than on fast action
or complex environmental interaction. When a shot keeps breaking, ask whether a
slower version conveys the same idea.

Worth testing (community-sourced, unverified): an explicit `"background geometry
stays locked while the subject moves"` line, and giving the motion a concrete
secondary anchor (water rippling, fabric shifting).

**Don't rely on the model for on-screen text** — lettering is re-mangled between
runs. Add it in post.

## A two-person beat — measured 2026-09-18

One scene on prod, several takes per finding: two men, a chair, a wall, a
kiss, 8–12 s clips at `standard` and `pro`. What held, in the order it
matters. Run the
[pre-flight](../studio-media-scene/SKILL.md#pre-flight--settle-it-before-anything-renders)
first; every line below was settled after a render that should have been
settled before one.

- **A `dialogue` list constrains speech; its absence invites it.** With the
  list present — even one whispered line — Kling rendered exactly those words
  and nothing else, through an 8–12 s clip with a kiss in it. With
  `generate_audio: true` and no list it invented lines. So when audio is on
  the list is always there, even if it is one line; muting to dodge invented
  speech is not the fix.
- **High-level beats beat choreography.** "The shirtless man stands up out of
  the chair and, kissing him, pushes the man in the polo back against the
  wall and pins him there" landed cleanly. The detailed version — "forearm
  across his chest, other hand slapping flat on the wall beside his head, two
  quick steps" — tangled the arms. Two simultaneous arm instructions tangle;
  **one arm action per beat**. Detail belongs in the stills, intent in the
  video prompt.
- **`static/hold, locked off` is not honoured when the subjects cross the
  room.** The camera re-framed to follow in three takes. If the subjects
  travel, ask for it — "a smooth pan following them, keeping both in frame,
  then holding" — and that is rendered well.
- **Put the previous clip's LAST FRAME in `reference_images`**, beside the
  character references, to carry height and the two figures' relationship
  into the next clip. It held. The 7-image cap counts the start frame, so
  drop a redundant face angle to make room for it.
- **Quality: `mode: pro` from a 2K still with a static camera was the visible
  jump.** Faces held for 12 s at 1080p with no push-in. Push in only on the
  final beat. And `scenes assemble` conforms every shot to the **first**
  shot's size, so a `pro` clip lands at 720p inside a cut that opened at
  `standard` — decide the mode for the scene, not the clip.
- **A kiss renders from a start frame plus references, and it renders with
  an end frame too** — the end frame must be a non-kiss still. The
  refusal map across engines is on
  [`studio-media-scene`](../studio-media-scene/SKILL.md#what-each-engine-will-actually-render--contact-between-two-people).

## Legacy parameters in old guides — all wrong now

Third-party Kling guides are overwhelmingly written against API 1.x:

| Claimed | Reality |
|---|---|
| JWT signed from AccessKey + SecretKey | Plain `Authorization: Bearer <key>` |
| `model_name` in the body | Model is in the path / the Replicate model id |
| `cfg_scale`, `mode: std\|pro` | Not present (Replicate's `mode` is resolution) |
| `duration: "5"\|"10"` as a string | Integer, 3–15 |
| `negative_prompt` field | Not present |
| A `seed` | Not present |

## Prose, not JSON: what Kuaishou actually documents

**Kling receives the prompt as prose.** `studio prompt --engine kling-replicate`
takes the same object as every engine and serialises it in the form
Kuaishou's own material uses, not as JSON. Until 2026-09-20 it sent the
object as indented JSON — a form validated on Seedance, per ByteDance's
guidance, and never on Kling. The braces, quotes and key names were reaching
a 2,500-character text field as literal characters. Researched and settled
that day; what was found:

- **Kuaishou's prompt guide** gives one formula — *Subject (description) +
  Subject Movement + Scene (description) + (Camera Language + Lighting +
  Atmosphere)* — and says "use simple words and sentence structures". No JSON,
  no key:value form, anywhere in the text-to-video guide, the 3.0 Omni user
  guide or the prompt blog.
- **The 3.0 Omni guide writes multi-shot as lines** — `Shot 1 (2s): …` or
  `[00:00–00:02] wide shot: …` — with characters as `@Name` and dialogue in
  quotes under a speaker label.
- **The only JSON the model parses is `multi_prompt`**, a typed Replicate
  field taking `[{"prompt", "duration"}]`. Each shot's `prompt` inside it is
  prose. Confirmed against the live schema, which also has no `negative_prompt`
  and no `seed`, whatever the README says.
- **fal's Kling 3.0 guide** says the same in different words: think in shots,
  label each, anchor characters early, use filmmaking vocabulary. No
  benchmark between formats.
- **Every source claiming Kling "prefers JSON"** was selling a JSON prompt
  generator, cited no Kuaishou document and showed no side-by-side.
- **What the evidence does support** is structure over an undifferentiated
  paragraph — explicit shot boundaries, one named camera move, subject first.
  Those are content rules and the validator enforces them regardless of form.

So the wire text is now:

```
<subject> <action>. <scene>. <Shot type>, <movement>, <lens>mm lens. <lighting>. <style>. <audio>.

Speaker: "line"

Avoid <negative>.
```

The paragraph follows the formula's order and the negative closes it, because
Kling has nowhere else to put it. **The beats are not in here** — they are in
`multi_prompt`; see [below](#the-timeline-goes-out-once). `Shot N (Ns): …`
lines are written into the prompt only when the durations do not resolve and
no `multi_prompt` goes out, and then they are the only timeline there is.

**Nothing about the locked template changes**: the object is still what you
author, diff and hold byte-identical across a scene, and it is still what
`prompt.json` records beside the run. Only the string built from it differs —
and a byte-identical object serialises to a byte-identical string.

### The timeline goes out ONCE

Until 2026-09-22 the compiler wrote the beats **twice** — `Shot N (Ns): …`
lines in the prompt *and* the same beats in `multi_prompt`. Measured on a
four-beat 15 s draft on prod: 2,494 characters of a 2,500-character cap, of
which the shot block was **1,366** — 55% of the budget spent restating what the
typed field already held, six characters from the hard refusal, in a second
wording built by different code from the same `shots[]`.

Nothing asks for that. Replicate's README puts the beats in the array alone:

> ### Multi-shot mode
> Use the `multi_prompt` parameter for videos with multiple scenes. Pass a JSON
> array of shot definitions, each with a prompt and duration (up to 6 shots).
> ```json
> [{"prompt": "<<<image_1>>> opens a door and steps inside", "duration": 5},
>  {"prompt": "<<<image_1>>> looks around the room in surprise", "duration": 5}]
> ```

And Kuaishou's "define the setting first, then organize the scene by shot
order" describes a prompt with **no structured field to put the order in**;
with `multi_prompt` the order *is* the field. So the division of labour is:

| | carries |
|---|---|
| `prompt` (required, always sent) | what is true of every cut — the setting, the cast and their `<<<image_N>>>` tags, lighting, style, audio, `Avoid …` |
| `multi_prompt` | what happens, cut by cut, with each beat's seconds |

Answering the question this arrangement provokes — *why am I sending a prompt
AND a multi-prompt?* — `prompt` is `required` in the live schema, so something
has to be in it, and the globals are what a per-beat array has nowhere to put.
The app says the same thing on the create panel, under the switch.

Not yet measured: whether the prose form tracks the brief better than the JSON
did. It is the vendor's documented form, which is the reason to default to it;
a same-beat, same-start-frame pair would show the size of the difference.

## Kuaishou's prompt guide, applied

Source: [Kling AI Prompt Guide: The Secret to Cinematic Video Prompts](https://kling.ai/blog/kling-ai-prompt-guide)
(kling.ai, 2026-08-07). Its opening line: "strong cinematic prompts are built
from clear scene direction rather than secret formulas." Read against what
`studio prompt` does, rule by rule.

### Its five elements are the object's keys

| Kuaishou | Object key | Its example direction |
|---|---|---|
| Subject | `subject` | "A woman in a striped shirt, a perfume bottle on a velvet pedestal" |
| Action | `action` / `shots[].description` | "Walks toward camera, swirls juice in glass, turns and smiles" |
| Scene | `scene` | "Outdoor terrace, old street in Madrid, studio product set" |
| Camera | `camera` | "Close-up, wide shot, low angle, slow push-in, tracking shot" |
| Lighting and mood | `lighting` + `style` | "Natural sunlight, golden hour, cold blue night, soft haze" |

Nothing to translate: the prose the compiler emits is these five, in this
order.

### Describe what is visible, never the effect you want

Kuaishou's own words: avoid "magic"; write "swirling blue energy particles
with an ethereal glow". Movement is visible things — "smoke drifting upward,
flames bending in wind, runner leaning forward". Atmosphere is visible things —
"haze, rim light, long shadows, reflections on wet pavement". This is the
vague-adjective warning, from the vendor. **Their examples do end on a
quality tail** — "Photorealistic, 8K detail, masterpiece cinematography";
"High consistency, cinematic lighting, 4K, realistic textures" — so a short
tail in `style` is not filler here. The validator does not flag those words.

### Camera: plain sentences, and the vendor stacks moves

The guide's camera table is written as sentences, not tags — "The camera slowly
pushes toward the subject", "Camera follows beside the runner", "Camera pans
across the room or tilts up to the sign". Write `camera.movement` that way.
Shot sizes it defines: **extreme close-up** (an eye, a small object), **medium
close-up** (upper torso up — dialogue and expression), **full body** (subject
plus some surroundings — action and clothing), **establishing wide** (location
and scale). Composition words it accepts: *centered*, *rule of thirds*,
*off-center*.

**Kuaishou's own showcase prompt composes three moves in one shot** — a
dolly-in that "simultaneously performs a subtle pan right and a gentle tilt
upward", described as one continuous, controlled motion. `studio prompt` warns
on a stacked move. On Kling read that warning as *"is this one described
motion, or two competing ones?"* — a dolly with a drift written as a single
gesture is what the vendor shows; "dolly in and orbit" is still chaos. The
warning is advisory and stays.

### Pacing has words

| Cue | Write it as | For |
|---|---|---|
| Slow | "a slow push-in as the character thinks" | calm, intimacy, suspense |
| Steady | "a steady tracking shot following the subject" | readable action, continuity |
| Quick | "a quick cut to a close-up reaction" | energy, surprise, a transition |
| A defined length | a `shots[].dur` — Custom Multi-Shot | structured scenes, dialogue beats |

Bare "fast" is not on their list either.

### Native audio and dialogue

- **Keep the speaker's name, line and delivery together.** The compiler puts a
  `delivery` on the label — `Mom (fast, urgent): "Shoes. Now."` — from
  `dialogue: [{"speaker", "line", "delivery"}]`.
- **Label every speaker plainly** in a multi-speaker scene.
- **Describe ambience as a place with an acoustic detail** — "an indoor living
  room with a subtle air-conditioner hum" — in `audio`. Dialogue, SFX and
  ambience are one generation with the picture under `generate_audio: true`.
- Five languages: Chinese, English, Japanese, Korean, Spanish; accents and
  dialects; mixed languages in one scene, with lip movement following.

### Consistency is a held description — the locked template, from the vendor

"Reference workflows are most useful when the prompt keeps the character,
product, or prop description steady while the scene, camera angle, or action
changes." And what that description holds: "clothing, hairstyle, props, and
the role the character plays in the scene." That is
[the locked template](#consistency-across-clips-lock-the-template-add-only-deltas)
stated by Kuaishou. Pair it with clean references — `reference_images` here,
a video reference on Omni when the same subject crosses angles.

### Multi-shot: setting first, then shots in order

"A strong Multi-Shot prompt should define the setting first, then organize the
scene by shot order so each beat has a clear purpose." The compiler's lead
paragraph then `Shot N (Ns):` lines is exactly that. The guide's own example
uses a third bracketed spelling — `[Shot 1: Wide shot] … [Shot 2: Medium shot]
… [Shot 3: Close-up shot] …` with the style tail after the last shot — so any
of the three documented spellings is read; ours carries the duration the
Custom mode wants. A practitioner's pack uses a fourth — `SHOT 1 [3 sec]`,
duration in the header — which also works, so the label's shape is not what
the model is reading. Custom Multi-Shot controls per shot: content, duration,
size and perspective, camera movement — the four things a `shots[]` entry has.

### Text in frame

Kling 3.0 renders lettering. For a label, sign, caption or packaging: "write
the exact words, placement, surface, and camera distance. Keep the text short
when readability matters", and frame and light for it. Treat it as
composition — where, how large, what around it stays clear.

### Their workflow is the phrasebook

"Start with a simple base prompt and then experiment with different speeds,
movements, and variations in framing. Record which combinations are most
effective … a personal library of proven prompts." Vary one thing per run
against a held base, and write what held into `studio phrasebook` and the
locked template.

## A creator walkthrough, applied

Sources: Dan Kieft, [*STOP Wasting Credits & Master Kling 3.0 in 25
Minutes*](https://youtu.be/b_RghITuQQM) (2026-02-24, 25 min) and the
[prompt pack](https://docs.google.com/document/d/1JxYJzqJ3ICCQsP_H9yZ0YsUE2jpeuDgvJe0ULBins18/edit)
behind it — a dozen prompts that produced the video's clips, which is the more
useful half: they are working text, not advice about text. Both driven through
OpenArt's hosted Kling 3.0 / Omni rather than Replicate, so the UI affordances
in them are not ours and the model behaviour is. **Nothing below is measured
here** — each line is one experienced user's reported result, which is a
hypothesis to design a run around, not a fact to build on. Where it meets
something this file measured, the measurement wins and the difference is
stated.

### His prompt structure is this object, in a different order

The video's answer to "how do I prompt Kling" is a seven-segment checklist,
and it is worth reading as independent confirmation of the schema rather than
as news — six of the seven are keys you already fill in:

| His segment | Key | Note |
|---|---|---|
| Camera | `camera` | He writes it **first** |
| Subject | `subject` | |
| Action | `action` / `shots[].description` | |
| Environment | `scene` | |
| Lighting | `lighting` | "a bit optional" |
| Texture | — | **No key.** Folds into `style` |
| Audio | `audio` | "a bit optional" |

Two things to take from it and one to leave:

- **Texture is the only segment with nowhere to go.** Surface language —
  grain, sheen, wet asphalt, worn fabric — is real direction and it lands in
  `style` alongside the grade. Worth naming when a shot's material qualities
  matter; Kuaishou's own guide says the same thing under "describe what is
  visible".
- **A shot line is camera + action + a length, fused.** His example is "an
  over-the-shoulder close-up as she leans in" — one clause carrying the
  framing and the beat, which is the shape `shots[]` compiles to. Nothing to
  change; it is a good model of how short a beat description can be.
- **Leave the camera-first ordering.** Kuaishou's guide is subject-first and
  that is what the compiler emits. One creator's habit does not outrank the
  vendor's documentation, the segments are the same either way, and nothing in
  the video tests the order against anything.

He also calls the last three optional. Treat that as his shorthand, not
permission: `audio` is what stops
[invented music and invented speech](#a-two-person-beat--measured-2026-09-18),
which is measured here.

### One reference, many angles — what multi-shot is actually for

The framing that makes `multi_prompt` worth its hard cuts: **one reference
image, up to six angles of the same subject, held consistent by the model**.
The alternative it replaces is four prompts, four reference images and four
generations stitched afterwards.

So there are now two reasons to reach for it, and they are different jobs —
[controlling *when* things
happen](#multi_prompt-beats-are-cuts--and-they-are-the-only-timing-control),
and getting coverage of one subject cheaply. For the second, chaining is the
expensive way round.

### Dialogue holds for about ten seconds, then lip-sync drifts

The sharpest finding in the piece, and it argues *against* the 15 s ceiling
rather than for it: past roughly 10 seconds the mouth separates from the audio
— reported across his own runs and corroborated in his comments, on a feature
Kuaishou markets as improved.

The rule that follows, adopted here: **put every spoken line in the first ~10
seconds, and give the remaining seconds to action rather than speech.** With
`multi_prompt`, that means the dialogue beats come first and a wordless beat
closes. It composes with what this file measured — a `dialogue` list constrains
speech, its absence invites it — into one shape: audio on, a list present,
lines early, silence last.

A clip whose dialogue genuinely needs more than 10 seconds is two clips.

### How the working prompts write dialogue and audio

The pack's twelve prompts are consistent about this, and it is craft the
five-element formula does not cover.

**A speaker label is `[Name: delivery]` on its own line, the line in quotes
beneath it.** The compiler emits Kuaishou's other documented form —
`Name (delivery): "line"` — and the two are alternatives, not a hierarchy.
What matters is that **a delivery is always present**: "hushed whisper",
"calm, flat", "overly forced gravel voice", "stuttering and blushing",
"barely audible, shattered". A bare line with no delivery is a performance
left to the model, and performance is [what this engine is reportedly best
at](#what-it-is-reported-to-be-good-at) — so it is worth directing.

Three devices inside the quoted text itself:

- **Capitals carry volume** — `"WHERE IS HE?"`.
- **Periods between words beat it out** — `"WHERE. IS. HE."`.
- **`Beat.` is an explicit pause** mid-line, between two quoted fragments,
  which is how a held silence gets timed inside a beat rather than across one.

**`(O.S.)` puts a line off-screen** — `The Man (O.S., chewing): "It's about
loyalty."` while the shot is on the listener. That is the reaction shot, and
without the marker the model has to guess whether to cut to the speaker.

**Speakers can be labelled by position when nobody has a reference** —
`[Foreground Player: casual]` and `[Seated Player: breathy]` distinguish two
unnamed men in one frame by where they sit. Useful before a character exists,
and it composes with a tagged reference for anyone who does.

**Every shot carries its own `Audio:` line, and it is specific.** Not "room
tone" but "cardboard rustle, distant birds outside, light fabric movement" —
or "tiny claws tapping wood, soft fabric drag, gentle room tone". Read the
pattern as two layers: a **held ambience** that should read identically in
every shot, and **beat-specific SFX** naming the sounds *this* action makes.
The object has one `audio` field for the first; the second belongs in the
`shots[].description` that causes it. See
[`studio-media-scene`](../studio-media-scene/SKILL.md#audio-across-clips).

### Morphing scales with duration *and* with prompt complexity

Long generations morph — a face or a garment sliding into something else
mid-shot. The reported levers are two, and only one of them is the one people
reach for: shorten the clip **or simplify the prompt**. This file already says
[shorter clips drift less](#shorter-clips-drift-less); the second half is new
and matters, because the instinct when a shot breaks is to add wording, which
is the wrong direction.

### Motion carries across a `multi_prompt` cut

A subject leaning in at the end of one beat was still leaning in at the start
of the next. Beats are hard cuts in framing, [as this file
says](#multi_prompt-beats-are-cuts--and-they-are-the-only-timing-control), but
the model appears to carry physical state across the boundary. If it holds,
the [pose-continuity
line](../studio-media-scene/SKILL.md#the-pose-continuity-line) that a *chained
clip* needs is redundant *within* one generation — write the pose once, in the
beat that starts it.

### One complete prompt, annotated

Everything above was extracted from working prompts; this is one of them
intact, because the rules are abstractions of the thing and the thing is
shorter. Four shots, 12 seconds, four references — two people, an animal and a
location. Reproduced in **the pack's own spelling**, which is not the one this
repo emits; the mapping follows.

```
SHOT 1 [3 sec]
@image4 is the background. Medium tracking shot slowly dolly pushing in on
@image1 kneeling beside an open cardboard box while a big @image2 drags along
a small box. She points at a small blanket on the sofa and says
[woman: casual]
"Pokie, could you fetch me that blanket?"
Audio: cardboard rustle, distant birds outside, light fabric movement.

SHOT 2 [2 sec]
Low-angle medium shot on @image2 waddling to the sofa. She reaches down to
take the small blanket.
Audio: tiny claws tapping wood, soft fabric drag, gentle room tone.

SHOT 3 [4 sec]
Locked-off interior shot facing the sliding glass doors as @image3 walks past
outside along the garden path. He stops and glances through the glass,
noticing @image1 and @image2.
[Man: friendly, raised voice]
"Oh—hey! You must be the new neighbors!"
Audio: faint outdoor footsteps on stone, muffled voice through glass, light
breeze in grass.

SHOT 4 [3 sec]
Over-the-shoulder from outside, through the glass of @image1 as she turns
toward the door, sunlight edging her silhouette.
[Woman: stuttering and blushing]
"Oh, hi! Yes we are!"
Audio: subtle fabric shift, soft daylight ambience, distant birds.
```

What it demonstrates, in the order it appears:

- **A location tagged like a person.** `@image4 is the background` — the plate
  occupies a reference slot and is addressed the same way the cast is.
- **One camera move per shot,** each shot opening with its framing: dolly in,
  low-angle static, locked-off, over-the-shoulder. No shot stacks two.
- **Durations sum to the total** — 3 + 2 + 4 + 3 = 12, which is what
  `multi_prompt` requires.
- **Every line carries a delivery** — `casual`, `friendly, raised voice`,
  `stuttering and blushing` — and every speaker is labelled even though only
  two of them talk.
- **Audio is per shot and specific**, and the ambience repeats: "distant birds
  outside" in shot 1, "distant birds" in shot 4.
- **And it breaks the ten-second rule, visibly.** Shot 4 runs 9–12 s and
  carries a spoken line, which crosses the mark where lip-sync is reported to
  come apart — and lip-sync is exactly what the video names as the one flaw in
  this clip. The pack is not a set of perfect prompts; it is a set of prompts
  that ran. Moving that last line into shot 3 and closing on the wordless beat
  is the fix, and it costs nothing. See
  [the ten-second rule](#dialogue-holds-for-about-ten-seconds-then-lip-sync-drifts).

And one thing to *not* copy: the ambience wording drifts — "gentle room tone",
"soft daylight ambience", "light breeze in grass" are three names for one
place. [Hold it identical](../studio-media-scene/SKILL.md#audio-across-clips)
and let only the beat's own sounds change.

**In this repo the same shot is an object, and the compiler spells it
differently.** The shape survives; four things are renamed:

| The pack | Here |
|---|---|
| `SHOT 1 [3 sec]` | a `shots[]` entry with `dur` → `Shot 1 (3s):` |
| `@image1` | `<<<image_1>>>` — [the spelling question](#references-are-elements-not-just-characters--and-the-prompt-can-name-them) |
| `[woman: casual]` + line beneath | `dialogue: [{"speaker", "line", "delivery"}]` → `Woman (casual): "…"` |
| per-shot `Audio:` line | held ambience in `audio`, beat sounds in the `shots[].description` |

Three devices this example happens not to use, from elsewhere in the pack:

```
Bucket Vigilante (overly forced gravel voice): "WHERE IS HE?"
"Don't play games with me." Beat. Louder, more forced: "WHERE. IS. HE."
The Man (O.S., chewing): "It's about loyalty."
```

### Multi-shot may be unavailable when both frames are set

Reported as a flat UI restriction: with a start frame **and** an end frame,
multi-shot is not offered. Nothing in the Replicate schema forbids the
combination, and this repo has never sent one — but it sits beside a
[constraint we did hit](#an-end-frame-clears-the-reference-list), where the
same pair caps the request at two images, so treat a bracketed multi-beat
request as likely to fail and cheap to avoid.

Wanting both the bracket and the cuts is the case for chaining:
[`studio-media-scene`](../studio-media-scene/SKILL.md).

### What it is reported to be good at

Two claims worth knowing when choosing an engine, both unmeasured here:

- **Facial expression and emotion** — the strongest thing in his showcase, and
  the reason to send a performance beat here rather than to a model picked for
  motion.
- **Prompt coherence on an odd brief** — briefs that Kling 2.6 mangled and Veo
  3.1 refused outright came back readable. A shot that failed elsewhere is
  worth one attempt here before the brief is blamed.

### What to not take from it

**"Meta-prompt it with an LLM"** — that is `studio prompt`, and his own caveat
is the important half: an LLM-written prompt you did not read is a slot
machine. Which is also [hard rule #2](../../../CLAUDE.md) — the payload gets
shown and a person says send. The camera-first ordering is the other one; see
[above](#his-prompt-structure-is-this-object-in-a-different-order).

## Verified runs

`kwaivgi/kling-v3-omni-video`, image-to-video from a 1024×1024 PNG, `multi_prompt`
with 3 × 3 s beats, `mode: standard`, no audio → **succeeded** in 128 s,
9.041 s of 960×960 output, $1.52. No content-policy rejection.

**A four-part chained scene**, each part driven by the previous part's last
frame, `mode: standard`, `generate_audio: true` throughout (15 s + 10 s + 10 s +
6 s → 41.2 s assembled). Findings worth keeping:

- **`start_image` + `reference_images` together works, and stays targeted.** With
  **two** people in frame and references for only **one**, the references did not
  bleed onto the second person — they kept their own face.
- **In a chained scene, those references should be the scene's own frames** — the
  image part 1 started from plus each handoff frame — not the character's curated
  `reference/` library. Those images were made in another context and pull the
  render toward it. Reach into `reference/` only when the scene introduces
  something no existing frame shows. See
  [`studio-media-scene`](../studio-media-scene/SKILL.md); `studio scenes frames`
  derives the list from the cut.
- **Every shot came back 960×960 24 fps / AAC 44.1 kHz stereo**, so chained shots
  stitch as a stream copy with no re-encode.
- **Audio needs directing.** `generate_audio: true` with no `audio` block tends to
  invent music; naming the ambience, the sounds the action makes, and what to
  exclude gets a usable bed. Keep that wording identical across shots or the
  joins become audible.
- **Removing a garment duplicates it.** Mid-clip the shirt was in his hand *and*
  on his body before resolving. Compression, not wording — the fix is more
  seconds for the motion.
- **Props not named in the prompt improvise.** A lanyard in the source frame
  became an ID badge, then vanished. Name persistent props in `subject` or accept
  the drift.
- **Held stillness holds** at short duration — a 6 s "hold a look" beat stayed
  still with no invented motion, where 15 s of it would likely not have.
- **A physically contradictory pose resolves itself toward the default.** A
  direction requiring two subjects to be in close contact *and* held apart at
  arm's length came back as ordinary close contact every time, across several
  rewordings and with the contradiction named in `negative`. Settle that kind of
  geometry in a **still** first — the model is not going to hold a pose that
  fights itself.
- **What the start frame hides, the model invents.** A seated man whose shorts
  were under the desk stood up in jeans — here once and on Wan 3.0 twice, and
  no wording held the wardrobe. A seed must *show* what has to survive, and a
  beat that must land somewhere exact is pinned by an end still, not prose —
  [`studio-media-scene`](../studio-media-scene/SKILL.md#the-end-frame-is-where-control-lives).
  Here that costs the reference list (an end frame caps the request at two
  images), so bracket on Kling only when the two frames already say everything.
