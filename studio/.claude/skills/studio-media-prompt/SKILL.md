---
name: studio-media-prompt
description: Author video prompts as one structured object for any studio-* engine (Seedance 2.0 and Kling 3.0 / O3 Omni, both on Replicate) and compile it to the text each vendor documents — JSON for Seedance, Kuaishou's subject + movement + scene + camera formula as prose for Kling. Use whenever a video request wants tight, repeatable control over camera / subject / action / scene / lighting / style / audio, a multi-shot timeline, an image-to-video shot, or a reusable prompt template. Validates the object (one camera move, no bare "fast", no camera verbs in the action, beat budget, start-frame redundancy) and routes technical fields and the negative prompt to wherever the target engine actually takes them. A prompting technique, not a separate model.
---

# studio-media-prompt — structured prompting for the studio-* engines

**The object is how the prompt is WRITTEN and checked; the engine receives
text.** Every engine's `prompt` field is a plain **text string**. You author one
object — subject, action, scene, camera, lighting, style, audio, negative — the
API validates it, and `studio prompt` compiles it into that string **in the
form the engine's vendor documents**:

| Engine | Wire form | Why |
|---|---|---|
| Seedance | the object as indented JSON | ByteDance's guidance endorses labelled structured text |
| Kling | Kuaishou's formula as prose — *subject + movement + scene + (camera + lighting + atmosphere)*, `Shot N (Ns):` lines for a timeline, `Avoid …` last | Nothing Kuaishou publishes mentions JSON; see [`studio-media-kling`](../studio-media-kling/SKILL.md#prose-not-json-what-kuaishou-actually-documents) |

Same object, same checks, same locked template. Only the serialisation differs,
and the object — not the wire text — is what `prompt.json` records beside a run.

This skill owns *how the prompt is authored*. Rendering belongs to an engine
skill:

| Engine skill | Model | Access | `--engine` |
|---|---|---|---|
| **`studio-media-seedance`** | Seedance 2.0 | Replicate, via `studio run --model seedance` | `seedance` (default) |
| **`studio-media-seedance-2-5`** | Seedance 2.5 | Replicate, via `studio run --model seedance-2.5` | `seedance` — same engine profile |
| **`studio-media-kling`** | Kling 3.0 Omni | Replicate, via `studio run --model kling` | `kling-replicate` |

Use this skill when the user wants precise, repeatable control, a multi-shot
timeline, or a template they can tweak. For a quick one-off, writing the prose
by hand is fine — don't force the object on everything.

> **Character videos:** the object controls the *words*; it does **not** replace
> character references. If the request names a known character, load
> **`studio-media-character`** first. On Seedance that means passing `reference_images`
> and citing them as `[Image1]`, `[Image2]`, …; on Kling via Replicate it is the
> same `reference_images` idea (up to 7), or a start frame plus
> `studio character textblock <name>` for a pasteable identity anchor.

## The one rule that shapes everything: text is TEXT

The model does not receive a JSON document over a typed API — it receives the
**serialized string**. So the object's job is human/agent legibility, the
checks, and a diffable template; the model still reads whatever it is given
top-to-bottom as text. Two consequences drive the whole schema:

1. **Subject + action lead.** The first ~20–30 words carry the most weight. Put
   `subject` and `action` first. (Some third-party guides push a *camera-first*
   order — ByteDance's and Kuaishou's own guidance both disagree, and so do we.
   `studio prompt` always emits subject/action first, in either wire form.)
2. **Technical fields are NOT prompt text.** `aspect_ratio`, `duration`,
   `resolution`, `seed`, `generate_audio` are real settings — Replicate input
   params on Seedance and Replicate-hosted Kling, the Kling API's own `settings`
   object otherwise. They belong there, not baked into
   the prompt string. The helper routes them for you.

## Schema

Author a single JSON object. Creative blocks become the prompt text — as JSON
on Seedance, as prose on Kling — and the `technical` block is split off to the
engine's settings.

```json
{
  "subject":  "WHO / WHAT is in frame — concrete, visual (wardrobe, age, build).",
  "action":   "ONE clear thing they do, concrete verbs. Subject motion only.",
  "scene":    "Where + when + atmosphere (location, time of day, weather, haze).",
  "camera":   { "shot": "medium", "movement": "slow push-in", "lens_mm": 35, "speed": "slow" },
  "lighting": "Physical light setup (key/rim/practical, colour, direction).",
  "style":    "Aesthetic + medium (film tone, grade, grain, animation style).",
  "audio":    "Named sound: ambience + SFX. Music mood if wanted.",
  "dialogue": [{"speaker": "Who", "line": "Spoken words — drive native lip-synced audio.", "delivery": "fast, urgent"}],
  "negative": "What to AVOID — jitter, bent limbs, temporal flicker, extra fingers.",
  "start_image": false,
  "technical": {
    "aspect_ratio": "16:9",
    "duration": 6,
    "resolution": "1080p",
    "generate_audio": true,
    "seed": 12345
  }
}
```

### Field notes

| Field | Goes to | Notes |
|---|---|---|
| `subject` | prompt | Lead block. Visual, not vibes. No camera verbs. |
| `action` | prompt | One action. **Subject** motion — camera motion goes in `camera`. |
| `scene` | prompt | Environment + atmosphere. **Omit when `start_image` is set.** |
| `camera.shot` | prompt | wide / medium / close / extreme close / over-shoulder. |
| `camera.movement` | prompt | **Exactly one** move (see list). Stacking degrades output. |
| `camera.lens_mm` | prompt | Focal length, e.g. `35`, `85`. Optional. |
| `camera.speed` | prompt | Qualify it — never bare `"fast"`. |
| `lighting` | prompt | Physical setup. **Omit when `start_image` is set.** |
| `style` | prompt | Medium + grade. `"cinematic"` is fine here (a style word, not filler). |
| `audio` | prompt | Name sounds explicitly; models only add audio you direct. |
| `dialogue` | prompt | Lines → native synced speech. A string, or `{speaker, line, delivery}` — Kuaishou: keep name, line and delivery together; on Kling that compiles to `Mom (fast, urgent): "…"`. |
| `negative` | prompt | Neither engine has a negative-prompt param; it is folded into the text — an `avoid` key on Seedance, a closing `Avoid …` sentence on Kling. |
| `start_image` | validator only | `true` when a start frame is supplied; enables redundancy checks. |
| `technical.*` | **engine settings** | A Replicate `input`, or the Kling API `settings` object. |

Camera movements (pick **one**): `push-in` · `pull-out` · `pan` · `tilt` ·
`tracking` · `orbit` · `aerial/drone` · `handheld` · `crane` · `rack focus` ·
`static/hold`. Write the move as a sentence the way Kuaishou's guide does —
"the camera slowly pushes toward the subject", "camera follows beside the
runner" — rather than a tag; and name pace with its words (*slow*, *steady*,
*quick*). Shot sizes and what each is for, from the same guide, are on
[`studio-media-kling`](../studio-media-kling/SKILL.md#kuaishous-prompt-guide-applied).

### Multi-shot: timeline mode

For a sequence, supply a `shots` array instead of a single `action`. Globals
(`subject`, `style`, `audio`, `lighting`) stay top-level; each shot carries its
own beat.

```json
{
  "subject": "A detective in a long coat",
  "style": "Neo-noir, teal/amber grade, 2.39:1",
  "shots": [
    { "t": "0s", "shot": "wide",   "camera": "static",       "description": "Stands at the end of a rain-slicked street" },
    { "t": "3s", "shot": "medium", "camera": "slow dolly in", "description": "Camera closes in from behind" },
    { "t": "6s", "shot": "close",  "camera": "hold",          "description": "Rain beads on his collar; he exhales" }
  ],
  "technical": { "duration": 8, "aspect_ratio": "21:9" }
}
```

**How many beats fit is engine-specific** — see the table below. The validator
warns when a timeline exceeds the target engine's budget.

## Rules the validator enforces (shared)

Treat warnings as author feedback; fix them before spending a render.

- **One camera move.** `"dolly in and orbit"` → chaos. One shot type + one move.
  On Kling, one *described* motion: Kuaishou's own showcase prompt is a dolly-in
  with a simultaneous subtle pan and tilt, written as a single controlled
  gesture, and the warning on it is advisory — see the Kling page.
- **No bare `"fast"`.** Qualify it: `"fast whip-pan"`, `"quick 1s push-in"`.
- **No camera verbs in `subject`/`action`.** Those blocks describe the subject;
  camera direction lives in `camera`. The verb form counts: `"she zooms toward
  the water"` warns as surely as `"a slow zoom"` does. Words with an innocent
  subject sense — `pans`, `tracks`, `tilts`, `cranes`, `drones` — are left alone
  unless the line names the camera as the one doing it (`"the camera pans across
  the bay"`), so `"she tilts her head"` is fine.
- **No vague adjectives** (`amazing`, `epic`, `stunning`, `beautiful`…). Models
  ignore mood words — describe what's observable instead. Kuaishou says the
  same: not "magic", but "swirling blue energy particles with an ethereal
  glow". A short quality tail in `style` ("photorealistic, 8K detail") is not
  a mood word and their own examples carry one.
- **Beat budget.** Too many beats for the duration means the model drops or
  morphs them.
- **60–100 words** of real content is the sweet spot for a single shot. Keys
  and structure don't count against you; padding prose does.
- **Technical fields** never sit in the prompt text.
- **Fix a seed** whenever the engine exposes one (Seedance does; **no Kling
  surface does**). Without one, every run rolls a fresh world and you cannot tell
  whether a change in output came from your edit or from the dice. Where no seed
  exists, hold the prompt byte-identical instead.

## Engine deltas

Everything above is shared. These differ, and `--engine` switches them:

| | `seedance` | `kling-replicate` |
|---|---|---|
| Wire form | the object as JSON | Kuaishou's formula as prose |
| Negative prompt | No param — folded in as `avoid` | No param — closing `Avoid …` sentence |
| Seed | **Yes** — use it | **None** |
| Beat budget | ~3 per 8s | **6 cuts** → `multi_prompt` array |
| Duration | 1–15s (`-1` = intelligent) | 3–15s |
| Aspect ratios | 16:9 4:3 1:1 3:4 9:16 21:9 9:21 adaptive | 16:9 9:16 1:1 |
| Resolutions | 480p 720p 1080p 4k | `mode`: standard/pro/4k |
| Prompt cap | ~4000 chars | **2500** |
| Reference tokens | `[Image1]` | `<<<image_1>>>` / `<<<video_1>>>` — **not** `[Image1]`, which is literal text here |
| Character identity | `reference_images` (≤9) | `reference_images` (≤7) |
| Image formats | wide | **jpg/jpeg/png only** |
| Technical fields → | Replicate `input` | Replicate `input` |

**The checking happens in the API.** `studio prompt` reads the object, sends it
to `POST /api/prompt`, and prints what comes back — so the same rules apply
wherever a prompt is authored rather than only at a terminal. Nothing is stored
and nothing bills; it is safe to run as often as you like.

`studio prompt` also checks a draft against the per-model **wording list** and
flags the preferred alternative where one is recorded — see
`studio phrasebook show <model>`. The list is data in
S3; when it cannot be read the validator says so rather than reporting the draft
checked.

**Dialogue goes early on Kling.** Lip-sync is reported to drift past ~10
seconds, so order `shots` with the spoken beats first and a wordless beat last,
and split anything that needs longer into two clips. Nothing validates this —
it is a drafting habit.

**No Kling surface has a seed.** Where Seedance gives you reproducibility for
free, Kling gives you none — holding the prompt byte-identical is the only lever,
which is what the locked-template discipline in `studio-media-kling` is for.

## Image-to-video: don't describe what the frame already shows

Applies to every engine. When a start frame is supplied it **already fixes** the
background, lighting, wardrobe, and the subject's appearance. Re-describing them
makes the model fight the image and drift — the most common image-to-video
failure, and it reads as a model problem when it is a prompt problem.

Set `"start_image": true` and:

- **Cut `scene` and `lighting`.** The frame owns them.
- **Shrink `subject`** to an identity anchor — `"The man from the source image,
  unchanged — same face, hair, build, wardrobe and accessories"`.
- **Repoint `negative` at drift**: `changing face, changing hairstyle, changing
  build, changing background, changing wardrobe, cuts, scene changes` plus the
  usual anatomy terms.
- **Match the output aspect ratio to the source image**, or accept an
  uncontrolled crop. Crop later in an editor where the loss is visible.

The validator warns if `scene`/`lighting` survive or if `subject` runs past ~40
words.

### Chaining generations

For a sequence longer than one render: export the last frame, use it as the next
start frame, and carry a **pose-continuity line** in the next `subject`
(`"…, arms already raised in a bicep flex"`) so the pose doesn't reset on frame
one. Hold `scene`, `style`, and the seed identical across shots. That is what
makes shots cut rather than jump.

## Style presets (reusable, character-agnostic)

`style` is where the render's LOOK is set, per video. These presets are **not
tied to any character** — drop one into `style` and combine it with a character's
references or start frame to render that character in that look.

**Realistic** — the default when no style is requested.

> `"Photorealistic live-action cinematic footage, full color, real human skin and hair, shallow depth of field, natural film grade with warm highlights, subtle grain."`

**Match source image** — for image-to-video, where the frame sets the look.

> `"Photorealistic live-action, matching the source image exactly."`

**Vintage ink comic** — a 1970s underground-comix / editorial-engraving look:
black-and-white pen-and-ink with heavy spot-blacks, dense cross-hatching and
stipple shading, high-contrast on aged paper, with occasional selective spot
color used sparingly for a joke or a signal.

> `"Vintage pen-and-ink comic illustration, bold variable-weight linework, dense cross-hatching and stipple shading, heavy spot-blacks, high-contrast black and white on aged paper with occasional selective spot color."`

## Show, ask, then send

**Nothing runs unless a person tells it to.** Show the complete payload as the two documents — `PROMPT` then `INPUT` — ask, and submit only when told. `--dry-run` renders exactly that and bills nothing. The submit command (`studio run`, or `studio runs submit` on a draft) IS the act; there is no separate approve step. Show the payload again after **any** edit: a yes to a plan, to a menu answer, or to a payload shown several messages ago is not an instruction to send the request about to go out.
Both engines bill per run, and both are submitted by the same command, so the
same rule applies to each.

## Workflow

### 1) Assemble + validate with the helper

The script takes your object (file, stdin, or `--json`), validates the shared and
engine-specific rules, splits `technical` off, and emits the result.

```bash
# Seedance (default) — technical becomes a Replicate `input` object
studio prompt prompt.json

# Kling 3.0 Omni on Replicate — shots compile to multi_prompt, negative folds into the prompt
studio prompt prompt.json --engine kling-replicate

# image-to-video checks without editing the file
studio prompt prompt.json --engine kling --start-image

# override technical fields inline
studio prompt prompt.json \
  --aspect-ratio 9:16 --duration 8 --resolution 1080p
```

Output shape (Seedance — the object as JSON):

```json
{
  "prompt": "{ …serialized creative JSON, negative folded in as `avoid`… }",
  "input":  { "prompt": "…", "aspect_ratio": "16:9", "duration": 6, "resolution": "1080p", "generate_audio": true },
  "engine": "seedance", "timeline": false, "warnings": [ … ]
}
```

Output shape (`kling-replicate` — the object as Kuaishou's prose, a ready
Replicate input, shots compiled to `multi_prompt`, no aspect_ratio because a
start frame is set):

```json
{
  "prompt": "The man from the source image, unchanged. Neo-noir grade.\n\nAvoid changing face, changing wardrobe, cuts.",
  "input": {
    "prompt": "…", "mode": "standard", "duration": 9, "generate_audio": false,
    "multi_prompt": "[{\"prompt\":\"Medium shot, static. He raises both arms…\",\"duration\":3}, …]"
  },
  "engine": "kling-replicate", "timeline": true, "warnings": [ … ]
}
```

**The beats are in `multi_prompt` and NOT in the prompt.** The prompt carries
what is true of every cut — subject, style, lighting, audio, the `Avoid` — and
the array carries what happens in each. `Shot N (Ns): …` lines appear in the
prompt only when the durations do not resolve, because then nothing else is
carrying the timeline. Settled 2026-09-22; see
[`studio-media-kling`](../studio-media-kling/SKILL.md#the-timeline-goes-out-once).

A single-shot Kling prompt is one paragraph in the formula's order — subject
and action joined into a sentence, then scene, camera (`Medium shot, slow
push-in, 35mm lens.`), lighting, style, audio — then dialogue as
`Speaker (delivery): "line"`, then `Avoid …`. Every rule
in that shape is Kuaishou's own — its prompt guide is worked through on
[`studio-media-kling`](../studio-media-kling/SKILL.md#kuaishous-prompt-guide-applied).

Flags: positional `source` (file or `-` for stdin) · `--json` · `--engine seedance|kling-replicate` · creative overrides (`--subject/--action/--scene/
--style/--lighting/--audio/--negative`, `--camera-movement/--camera-shot/
--lens-mm`) · `--start-image` · technical overrides (`--aspect-ratio/--duration/
--resolution/--seed/--no-audio`) · `--emit both|prompt|input` · `--compact` ·
`--strict` (non-zero exit on any warning). Invalid enums / durations exit
non-zero as **errors**, per engine.

### 2) Render via the engine skill

Both engines are driven by the same command. Save the `input` object to a file
and hand it to the runner, which records the run, submits without
`Prefer: wait`, polls, and archives the output:

```bash
studio prompt prompt.json --emit input > input.json
studio run --model seedance --project <project> --input-file input.json \
  --character <name> --name <file> --poll
```

- **Seedance** → **`studio-media-seedance`** (`--model seedance`). Bind identity
  with `--character` (it resolves the selection and presigns it); a first frame
  goes on `--start-run` / `--start-key` and **cannot** be combined with
  references here.
- **Kling** → **`studio-media-kling`** (`--model kling`). Same flags, and a start
  frame **does** combine with references. Kling takes only `.jpg/.jpeg/.png`.

**Never add an image to the payload as an https URL you produced yourself, and
never upload one to Replicate.** Uploading an asset *to* Replicate is exactly
what THE RULE forbids: everything sent to a model must already be in the media
library, and the runner mints the short-lived presigned URL at submit time. Any
image field baked into `input.json` is dropped for that reason.

## When NOT to use the object

- A single simple clip with no fussy camera/lighting needs → a prose prompt
  written by hand reads just as well and is faster to write.
- When identity is the whole point → the win is **references or a start frame**,
  not the prompt. Use the object for the surrounding motion/framing.
