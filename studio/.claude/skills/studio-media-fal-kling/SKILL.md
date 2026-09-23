---
name: studio-media-fal-kling
description: Generate video on Kling 3.0 / O3 through fal.ai (fal-kling-v3-i2v, fal-kling-o3-r2v) — the same model family as studio-media-kling on the provider that exposes ELEMENTS and VOICE BINDING. Use when two subjects must each stay themselves across a shot, when a scene should be cast from characters rather than from a flat reference list, or when a character must speak — in a voice Kling invents from the dialogue, the default; a CHOSEN voice needs a VIDEO element, one per request, which studio does not bind yet. An element is a subject: an image set or a clip. For the Replicate entry — cheaper per second, no elements, no voice binding — use studio-media-kling.
---

# studio-media-fal-kling

Two entries, one family:

| Registry key | Endpoint | Opens on |
|---|---|---|
| `fal-kling-v3-i2v` | `fal/fal-ai/kling-video/v3/pro/image-to-video` | a **required** start frame |
| `fal-kling-o3-r2v` | `fal/fal-ai/kling-video/o3/pro/reference-to-video` | nothing — the elements carry it |

> Invocation, hard rule #2, run recording and validation are shared — see
> [`studio-media-core`](../studio-media-core/SKILL.md):
> `studio run --model fal-kling-v3-i2v …`, and
> `studio models show fal-kling-v3-i2v` for the live schema. Prompting is
> Kling's, unchanged: [`studio-media-kling`](../studio-media-kling/SKILL.md)
> is the page for the formula, the shot structure and where dialogue has to
> sit. **This page is about the two things only fal exposes.**

**Live on fal since 2026-09-23.** The first fal Kling render succeeded on
`fal-kling-v3-i2v`: three image elements — two characters, and one room bound
as a frontal plus a reference — a 13 s three-beat timeline, `generate_audio`
on, no negative prompt. The limits below marked *measured* come from that
day's submits; the ones marked *assumed* have not been sent.

## An element is a subject

Kling on fal does not take a flat list of reference images. It takes
`elements` — up to **4**, each one a subject:

```
{ frontal_image_url, reference_image_urls[], video_url, voice_id }
```

and the prompt addresses them positionally: `@Element1`, `@Element2`, in bind
order.

**You do not build them.** Bind images the way you bind them on any other
engine — `--character <name>`, `--location <name>`, `--key <node>` — and the
API groups them into elements **by where each file sits**: every image out of
one character's tree becomes that character's element, its first image the
frontal view and the rest its other angles (**two to four** images in all). A
clip out of that tree lands on the same element as its `video_url`. That is
the same provenance a run page already prints under each send, so there is no
second place to say which pictures belong to whom.

**An image element needs at least two pictures — a frontal AND a reference —
or a clip.** fal's OpenAPI document does not say so; its server does. A lone
frontal came back as a 422 (2026-09-23, on the v3 endpoint; assumed for O3):

> Either frontal_image_url and reference_image_urls or video_url must be provided.

So `elements.min_images_each` is 2 on both entries, and a subject bound with
one picture is refused while the run is still a draft, quoting that sentence —
by `studio run` for a `--character` or `--location` that yields one image, and
by the API for any element, `--key` included. Bind a second view of that
subject. **Two stills of one room make one element only when both sit in the
same subject's tree**: a room still from a project's input pool and another
from the location group as two elements, one image each, and both are refused.
Copy the second still into the location's folder so they group.

Files belonging to nobody in particular — a project's input pool, a folder
somebody dropped stills into — share **one** element between them. That is
deliberate: three loose stills are three views of one thing far more often
than they are three subjects, and an element each would burn the cap of four
on a single character.

## A voice binds to a VIDEO element — one per run

fal's page for the v3 endpoint says it twice, in its element section and
again under Known Limitations:

> Voice binding is only supported for video elements, not image elements.
> Attempting voice binding with an image element returns an error.

An element is "either an image set (frontal + optional reference images) or a
video", and `video_url` adds "A request can only have one element with a
video." So a run carries **at most one bound voice**, on the one subject bound
by a clip. A character bound from its stills cannot hold one — the preflight
refuses the pairing while the run is still a draft, quoting fal's sentence.

**The default: Kling invents the voice.** `generate_audio` is on by default on
both entries. Write the dialogue into the prompt with a speaker and a delivery
on every line, exactly as
[`studio-media-kling`](../studio-media-kling/SKILL.md#how-the-working-prompts-write-dialogue-and-audio)
describes, and the model voices it and moves the lips in the same pass:

```bash
studio run --model fal-kling-v3-i2v --project <project> \
  --character <name> --start-key <node> \
  --extra '{"duration":"8"}' \
  --prompt "@Element1 looks up from the bench. @Element1 (quiet, relieved): \"You came back.\""
```

An invented voice is a new voice per run; two clips will not agree. That is
the trade for now.

**A chosen voice is not available yet.** It needs a video element, and
studio does not bind a clip into an element: neither fal entry declares a
`clips.source`, so `--clip-key` is refused on both and the create sheet draws
no Source video tile for them. `--voice-key` and the Voice tile therefore have
nothing to bind to today — every element studio builds is an image set, and
the preflight refuses a voice on one while the run is still a draft, quoting
fal's sentence above. Leave the voice off.

The fix is two lines, deferred by decision rather than unknown:
`clips.source: "elements"` on both registry entries, and the pipeline's bind
putting the clip into the elements list beside the pictures instead of letting
the references overwrite it (the voice is already appended that way). The
grouping at submit already puts a `clip` send into its subject's element as
`video_url`, and a voice from the same subject's tree lands beside it.

When it lands, the sample is registered once with Kling
(`fal-ai/kling-video/create-voice`), which answers a `voice_id`; the id is
cached on the audio node and reused forever — a fresh id per run would be a
fresh voice per run, which is the feature backwards.

Rules the preflight enforces before anything bills — the clip rows are for the video element once studio can bind one:

| | |
|---|---|
| Two images per image element | a frontal **and** at least one reference, or a `video_url` — fal: "Either frontal_image_url and reference_image_urls or video_url must be provided." Four at most |
| `generate_audio` | must be **true** with a voice bound. `false` renders a silent clip and the voice tier is billed anyway — the one failure the provider would not report |
| A voice needs a video | a voice on an element with no `video_url` is refused, quoting fal's sentence above |
| One per run | one element with a video per request, so one bound voice |
| The clip | 3–10 s, at least 720 px, 24–60 fps, at most 200 MB — fal's `video_url` schema |
| Format | `.mp3 .wav .mp4 .mov` — create-voice's list |
| Length | 5–30 seconds of ONE clean voice. fal refuses the rest, and it refuses it while the run is still a draft |
| Languages | English, Spanish, Japanese, Korean and Chinese natively, accents and code-switching included |

## What else differs from the Replicate entry

| | `replicate-kling` | here |
|---|---|---|
| Elements / voice | **none** — `generate_audio` only, and the model invents a voice per run | elements; an invented voice, as there — a bound voice needs a video element studio cannot bind yet |
| `duration` | an integer, 3–15 | a **string**, `"3"`–`"15"` |
| `multi_prompt` | a JSON **string** of `{prompt, duration}`, sent **beside** the prompt | a real **array**, and it **replaces** the prompt; **512 characters per beat, each `@Element` tag costing extra** — see below |
| Tier | `mode: standard / pro / 4k` on one entry | the **endpoint** is the tier; these two are 1080p |
| Negative prompt | in the prompt | a real `negative_prompt` on `fal-kling-v3-i2v`; none on `fal-kling-o3-r2v` |
| `cfg_scale` | — | 0–1 on `fal-kling-v3-i2v` |
| Price | per second, no voice tier | $0.112/s silent · $0.168/s with audio, an invented voice · **$0.196/s with a bound voice** (v3). O3 is $0.112 / $0.14 and does not price voice separately — the **cheaper of the two for a speaking character**, either kind of voice |

Both take a start and end frame, native multi-shot to 6 cuts whose durations
must sum to `duration`, and a 2500-character ceiling on a single `prompt`. On
fal a timeline's beats are capped far lower — 512 each, below.

## A timeline REPLACES the prompt here

fal's schema says it on the `prompt` field of both entries, in its own words:

> Text prompt for video generation. **Either prompt or multi_prompt must be
> provided, but not both.**

The other half of the sentence is the input schema's `required` array, which on
`fal-ai/kling-video/v3/pro/image-to-video` is `["start_image_url"]` alone: a
payload with no `prompt` at all is a complete one. So on these two entries a
multi-shot run sends **`multi_prompt` and nothing else**, and a payload
carrying both is refused while the run is still a draft, quoting that line.

That is the opposite of [`studio-media-kling`](../studio-media-kling/SKILL.md),
where Replicate's proxy **requires** `prompt` and the two go out together. Same
model family, two provider contracts — which is why the rule is registry data
per entry rather than something true of Kling.

**Every beat is capped at 512 characters — beat one included.** fal's server
enforces it and its OpenAPI document does not state it; a live submit came
back 422 (2026-09-23, v3 endpoint, no charge):

> body.multi_prompt.0.prompt: Value error, Prompt must not exceed 512 characters.

The 2500 of `prompt.max_chars` belongs to the single `prompt` field only, which
a timeline run does not send. `video.shot_max_chars` is 512 on both entries —
measured on v3, **assumed** on O3, which shares its multi-shot schema.

**Each `@Element` tag costs more than its nine characters.** fal's 512 is not
the last check: fal passes the beat to Kling, and Kling checks it again. Three
submits on 2026-09-23 were accepted by fal and refused by Kling with

> Unexpected status code: 422: body: multiPrompt[0].prompt: size must be between 0 and 512

fal's error detail shows the forwarded request, and the beat in it is ours
verbatim — nothing prepended. Kling names only the first failing shot, so
the other two beats of that timeline were never reported. The fourth submit
rendered:

| What was sent | Characters | `@Element` tags | Kling's answer |
|---|---|---|---|
| Shot one of the refused timeline | 492 | 5 | refused on `multiPrompt[0]`, three submits |
| Shot two, same timeline | 484 | 6 | not reported (fail-fast on shot one) |
| Shot three, same timeline | 496 | 5 | not reported |
| The fourth submit, three beats | 359 / 464 / 462 | 4 each | **rendered** |

*Inferred* from those four points, stated nowhere by fal or Kling: Kling
expands each `@ElementN` into an internal token of about 15 characters, about
+6 a tag. 492 + 5 × 6 = 522 fails; 464 + 4 × 6 = 488 passes. The registry
carries 8 a tag (`video.shot_tag_chars`), margin over the 6, so the budget is

```
len(beat) + 8 × (number of @Element tags)  ≤  512  — studio refuses above it
                                           ≤  500  — what to write to
```

and `studio run` and the API both refuse a beat over 512 on that count,
showing the sum. Measured on v3; **assumed** on O3.

**Tag each subject once per beat, then name it in prose.** `@Element1 sits
at the table. @Element2 leans in; the seated man looks up.` — not a tag on
every mention. Four tags a beat rendered; five and six were refused.

**The negative prompt does not share the budget.** Neither ours nor fal's
default: setting `negative_prompt` to `""` on one of the refused submits changed
nothing, so the keep-outs are not what put a beat over.

**The globals go into the FIRST beat — and have to fit in it.** Whatever you
pass as `--prompt` is prepended to beat one by `studio run`, and the payload
you are shown before you spend is the folded one. A fold that takes beat one
over 512 — tags counted as above — is refused before the draft is written,
naming the beat, its length, how much of it the globals were and what the
tags add. So on fal **the globals are tiny and each
beat carries itself**:

- **Beat one** opens with the identity anchor, **once, in one sentence** —
  who, as `@Element1`, and the room element tagged once.
- **Every beat**: camera, action, and one `Audio:` line.
- **Dialogue** with a speaker and a delivery label, in the beat it is spoken in
  (`@Element1 (quiet, relieved): "You came back."`).
- Lighting, grade and the `Avoid …` list get a clause, not a paragraph — the
  `negative_prompt` field on v3 takes the keep-outs off the beat altogether.

```bash
studio run --model fal-kling-v3-i2v --project <project> \
  --character <name> --start-key <node> \
  --prompt "@Element1 on a wet platform at night, sodium light." \
  --extra '{"duration":"10","multi_prompt":[
      {"prompt":"Wide shot, static. The train pulls away behind @Element1. Audio: brakes hiss, rain.","duration":"5"},
      {"prompt":"Close on @Element1, handheld. @Element1 (under breath, tired): \"Missed it.\" Audio: station tannoy, far off.","duration":"5"}]}'
```

First beat, not every beat: Kuaishou's own multi-shot guidance is "define the
setting first, then organize by shot order" — a preamble, not a refrain — the
model reads the beats in order, and a copy per beat multiplies the text by the
cut count against a ceiling it has to fit under.

**The cap is checked per beat, on both sides.** `studio run` checks the fold
before a draft is written; the API checks every beat again at submit, so a
timeline authored in the app or pasted into `--extra` is held to the same 512,
tags weighted. The refusal names the beat and its length, shows the sum when
tags pushed it over (`shot 2 is 484 characters and carries 6 @Element tags,
which Kling counts as about 532 of its 512 (484 + 6 × 8)`), and says when the
globals landed in it.

**The object you author does not change.** `--prompt-json` still records the
authored document as `prompt.json` beside the run, unchanged; only the wire
shape differs.

**`image_urls` on the O3 entry is deliberately not bound.** It is a second
reference list for style, cited as `@Image1`, and a registry entry names one
reference field — this one names `elements`, because that is the list a voice
and an identity attach to. A style reference that is nobody's identity belongs
in the prompt or on a start frame.

## From the app

The create sheet draws a **Voice** tile beside Start frame, End frame, Image
refs and Source video, on these two models and no others — a role is offered
only where the chosen model's entry declares a field for it. The picker lists
audio; a tile plays in place so a take can be heard before it is bound; the
bound sample rides on the strip like any picture and says `Voice` under it.
It takes one, and its hint says it is not available yet on these models:
with no video element to land on, leave it empty and Kling invents the voice.

## Which of the three

- Words, a character, and **nobody speaks** → [`studio-media-kling`](../studio-media-kling/SKILL.md). Cheaper, and its 7-image reference list is simpler than four elements.
- A character **speaks in a voice Kling invents** → any of the three. `replicate-kling` or `fal-kling-v3-i2v` from a chosen opening frame; `fal-kling-o3-r2v` with none, and the cheapest of the fal two with audio on.
- A character **speaks in a voice you choose** → not yet. It needs a **video element**, which studio does not bind — see [above](#a-voice-binds-to-a-video-element--one-per-run).
- Two characters, each themselves, **no frame to open on** → `fal-kling-o3-r2v`.
- Motion copied off existing footage → [`studio-media-kling-v3-motion-control`](../studio-media-kling-v3-motion-control/SKILL.md).
