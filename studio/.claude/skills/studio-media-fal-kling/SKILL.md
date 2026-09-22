---
name: studio-media-fal-kling
description: Generate video on Kling 3.0 / O3 through fal.ai (fal-kling-v3-i2v, fal-kling-o3-r2v) — the same model family as studio-media-kling on the provider that exposes ELEMENTS and VOICE BINDING. Use when a character must SPEAK in a chosen voice with lip-sync, when two subjects must each stay themselves across a shot, or when a scene should be cast from characters rather than from a flat reference list. An element is a subject; a voice sample is cloned once and bound to it, so the same character sounds the same in every later clip. For the Replicate entry — cheaper per second, no elements, no voice — use studio-media-kling.
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
frontal view and the rest its other angles (up to four images in all). That
is the same provenance a run page already prints under each send, so there is
no second place to say which pictures belong to whom.

Files belonging to nobody in particular — a project's input pool, a folder
somebody dropped stills into — share **one** element between them. That is
deliberate: three loose stills are three views of one thing far more often
than they are three subjects, and an element each would burn the cap of four
on a single character.

## A voice is bound to a subject, not to the run

```bash
studio upload --folder <name>/voice ~/takes/line-read.mp3   # 5–30 s, one clean voice
studio run --model fal-kling-v3-i2v --project <project> \
  --character <name> --start-key <node> \
  --voice-key <name>/voice/line-read.mp3 \
  --extra '{"duration":"8","generate_audio":true}' \
  --prompt "@Element1 looks up from the bench and says, \"You came back.\""
```

What happens at submit: the sample is registered once with Kling
(`fal-ai/kling-video/create-voice`), which answers a `voice_id`; the id is
written into **that character's element**; the model generates the video, the
dialogue, the delivery and the lip movement in one pass, in the voice it was
given.

**The id is cached on the audio node and reused forever.** That is the point
rather than an optimisation: a fresh id per run would be a fresh voice per
run, which is the feature backwards. Bind the same sample in next week's clip
and the character sounds the same.

**Put the sample in the character's own tree.** A voice groups onto a subject
the same way pictures do, so a sample sitting under a project binds to the
loose element and not to anybody in particular.

Rules the preflight enforces before anything bills:

| | |
|---|---|
| `generate_audio` | must be **true** with a voice bound. `false` renders a silent clip and the voice tier is billed anyway — the one failure the provider would not report |
| A voice needs a face | a sample bound with none of that character's pictures is an element that is a voice and nobody to speak it |
| Format | `.mp3 .wav .m4a .flac .mp4 .mov` — wider than what the library files as audio, because Kling reads a voice out of a video happily |
| Length | 5–30 seconds of ONE clean voice. fal refuses the rest, and it refuses it while the run is still a draft |
| Languages | English, Spanish, Japanese, Korean and Chinese natively, accents and code-switching included |

## What else differs from the Replicate entry

| | `replicate-kling` | here |
|---|---|---|
| Elements / voice | **none** — `generate_audio` only, and the model invents a voice per run | the whole of the above |
| `duration` | an integer, 3–15 | a **string**, `"3"`–`"15"` |
| `multi_prompt` | a JSON **string** of `{prompt, duration}` | a real **array** of them |
| Tier | `mode: standard / pro / 4k` on one entry | the **endpoint** is the tier; these two are 1080p |
| Negative prompt | in the prompt | a real `negative_prompt` on `fal-kling-v3-i2v`; none on `fal-kling-o3-r2v` |
| `cfg_scale` | — | 0–1 on `fal-kling-v3-i2v` |
| Price | per second, no voice tier | $0.112/s silent · $0.168/s with audio · **$0.196/s with a bound voice** (v3). O3 is $0.112 / $0.14 and does not price voice separately — the **cheaper of the two for a speaking character** |

Both take a start and end frame, native multi-shot to 6 cuts whose durations
must sum to `duration`, and the 2500-character prompt ceiling.

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

## Which of the three

- Words, a character, and **nobody speaks** → [`studio-media-kling`](../studio-media-kling/SKILL.md). Cheaper, and its 7-image reference list is simpler than four elements.
- A character **speaks, in a voice you choose**, from a chosen opening frame → `fal-kling-v3-i2v`.
- Two characters, each themselves, **no frame to open on** → `fal-kling-o3-r2v`.
- Motion copied off existing footage → [`studio-media-kling-v3-motion-control`](../studio-media-kling-v3-motion-control/SKILL.md).
