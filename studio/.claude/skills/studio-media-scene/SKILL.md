---
name: studio-media-scene
description: Build a SCENE — a continuous piece longer than one generation — as a series of runs, one seed still, then each clip rendered from the previous clip's last frame, then cut into one take. Use whenever a shot must run past a single model's duration ceiling (Kling stops at 15s), whenever a brief has several beats that must not be hard cuts, or whenever the user asks to continue, extend, or carry on from an existing clip. Owns the loop, the continuity rules that keep clips cutting together, the per-clip verification gate, and the cut. For cutting several finished scenes into one piece, see studio-media-movie.
---

# studio-media-scene — a shot longer than one generation

`studio-media-shot` produces **one clip** from a brief: plan, still, animate. This
skill takes over where that stops — when the piece needs to run **past the
model's duration ceiling**, or through beats that must flow rather than cut.

The family:
- **`studio-media-shot`** — one brief → one clip. Start there.
- **`studio-media-scene`** (this) — many clips → one continuous piece.
- **`studio-media-s3`** — `studio frames` pulls the handoff frame and the
  verification grid; `studio scenes` is the scene store.
- **`studio-media-kling`** / **`studio-media-seedance`** / **`studio-media-seedance-2-5`** / **`studio-media-wan-3-0-i2v`** — render each clip.

## Pre-flight — settle it before anything renders

"Take our time and figure out what we're doing before we run something." A
clip is dollars and a scene is many of them; every question below is free to
ask and expensive to discover after a render. Ask them **before drafting**,
not after the first take comes back wrong. Measured 2026-09-18, one failure
per line.

1. **Every still that will be a start frame, an end frame or a reference is
   shown to the person and approved for LIKENESS first.** A doubtful face in
   an end frame is baked into the video: a still whose second figure was not
   the character went in as an end frame, the clip's back half carried the
   wrong face, and $1.80 was lost before anyone looked. Show the still, ask
   "is this them?", and only then bind it.
2. **Decide the whole beat list first.** Write every prompt, review them
   together with the person, then submit — not one beat at a time, each
   discovering the next. A scene planned as a whole is a set of drafts in the
   cut before the first one bills; `--dry-run` leaves exactly that.
3. **For an intimate or two-person beat, settle these in words before a
   prompt exists:**
   - who leads and who yields;
   - the tone — the bare word "kiss" produced both a tender take and a rough
     one; say which;
   - where each face is relative to the camera — one person's back to the
     lens is a geometry problem no prompt fixes, so it is a different seed;
   - height and wardrobe, and that both are *visible* in the seed;
   - whether the camera holds or follows;
   - sound ON, and which lines are spoken.
4. **Sound stays on unless the person says otherwise.** Muting to dodge
   invented speech is not a fix; the fix is a `dialogue` list, even of one
   line — [`studio-media-kling`](../studio-media-kling/SKILL.md#a-two-person-beat--measured-2026-09-18).
5. **Show, don't describe.** The seed and every result go to the person as a
   rendered image or a contact sheet (`studio frames grid`), with the run's
   link in the app beside it — never as a prose account of what the clip
   probably shows.

[`studio-media-shot`](../studio-media-shot/SKILL.md) points here for the
same reason: the checklist is the plan's first step, whichever skill owns the
plan.

## What a scene is

A **named, ordered series of runs** in a project, and nothing else. Two facts:

| Fact | How it is written |
|---|---|
| a run belongs to the scene | `studio run … --scene <name>` when it is made, or `studio scenes add` later |
| the **cut** — the clips, in stitch order | `studio scenes add` / `remove` / `order` |

Membership takes stills and clips alike: the seed frame, the contact sheets,
every take of every clip. The cut names only the video runs, in the order they
are stitched, and it is the whole of the plan — it may name a run that has not
rendered yet, and `assemble` refuses until every run in it has a clip.

There is no storyboard document, no plan file, no panels. A seed still is an
image run; a shot is a video run; the frame a shot opens on is that run's start
frame. `studio scenes show <project>/<name>` prints the record with its cut.

## Why build a scene out of shots

Three separate ceilings, and only a sequence of clips clears all three:

1. **Duration.** Kling caps at **15 s**. A 40-second piece is not one render.
2. **Drift is cumulative *within* a generation.** Faces and hands go first, and
   the back half of a long take is where they go. Four short clips each hold
   together better than one long one — the trade is that drift now appears
   *between* clips instead, which the continuity rules below manage.
3. **`multi_prompt` cuts.** Kling's native multi-shot is the obvious way to get
   several beats, and every beat is a **hard cut by design** — different framing,
   often a different angle. If the piece must read as one continuous take,
   `multi_prompt` is the thing to remove, not tune.

### The pacing trade nobody mentions until it bites

`multi_prompt` is also the **only** way to control *when* things happen: each
beat carries an explicit `duration`. Drop it for continuity and you lose timing
control completely — the model allocates the seconds itself, and long actions
get compressed. Written wording ("within the first second or two", "for the
whole rest of the shot") recovers some of it, but not reliably.

So the choice is real and worth stating to the user before spending:

| Want | Use | Cost |
|---|---|---|
| Exact beat timings | `multi_prompt` | Hard cuts between beats |
| One unbroken take | single `action` | No timing control |
| Both | **a sequence of clips** — one take each, cut in post | An assembly step |

A sequence of clips is how you get both. Each clip is a single continuous
take, and clip boundaries are where the cuts go — deliberately, where you
chose them.

## Seed still first

A scene is judged before it is bought. The first frame is a **still** — cents —
so the location, wardrobe, light and grade are settled where they can be looked
at, and the video model only has to carry motion. Every later clip opens on the
previous clip's last frame, so the seed is the look the whole scene inherits.

Write the motion prompt for each clip with `studio prompt` and paste what it
returns. On Kling that is prose in Kuaishou's own formula — subject and
movement, scene, camera, lighting, style, then `Shot N (Ns):` lines and a
closing `Avoid …` — built from the object you authored, so a hand-written
paragraph looks no different in the app. What the object buys is every
authoring check and the locked template, which is the only reproducibility
lever Kling has (it has no seed): hold the object byte-identical and the prose
is byte-identical.

### Two ways to chain, and the choice is per scene

**Chained — one seed, every later clip inferred.** Clip 1 opens on the seed
still; every later clip opens on the **literal last frame of the clip before
it**, pulled with `studio frames last`. This is the default and it is what makes
a scene read as one continuous take: only that exact frame makes the join
invisible, and a still composed for the same moment differs from it in a
hundred small ways that read as a jump. The cost is that the scene must be
rendered **in order** — clip N+1 has no start frame until clip N exists.

**Bracketed — a start and an end frame per clip.** Every clip is pinned at both
ends by stills you approved (`--start-key` and `--end-key`), and the model only
invents the movement between them. Use it when a beat has to land somewhere
exact. Two costs: the clips no longer chain from one another unless you also
carry the handoff, and on most engines **an end frame excludes the reference
list entirely** (see the table below), so the two frames have to say everything.

They mix. A clip that deliberately opens on a new composition takes its own
`--start-key` instead of the handoff.

### What each engine will actually accept

Read off the registry rather than restated per skill, because it is what the
submit path enforces — `studio models show <model>` prints it.

| engine | reference cap | start + references | end frame |
|---|---|---|---|
| `kling` | 7 | yes — but **the start frame counts toward the 7** | **excludes all references** |
| `seedance` | 9 | **no — a start frame excludes references** | allowed |
| `seedance-2.5` | 30 | **no — a start frame excludes references** | allowed — and forces `aspect_ratio: adaptive` |
| `veo-3.1` | 3 | yes | **excludes all references** |
| `grok-imagine-video` | none | — | none |
| `kling-v3-motion-control` | none | — | none — the reference **clip** (`--clip-run`) sets the motion and the length |
| `wan-2.6-t2v` | none | — | none — **takes no image at all**; it cannot continue a take, only open one |
| `wan-2.6-i2v` | none | — | none — the start frame is the only image, so the handoff frame carries everything |
| `wan-2.2-i2v-lora` | none | — | none — start frame plus a **LoRA pair** (`--lora-high-key` / `--lora-low-key`), which is what carries identity |
| `wan-2.2-i2v-studio` | none | — | allowed — start frame, an optional **end frame** to land on, the LoRA pair; our own endpoint, up to 161 frames |
| `wan-3.0-t2v` | none | — | none — takes no image; opens a take, cannot continue one |
| `wan-3.0-i2v` | none | — | allowed — start frame required, an end frame to land on; no references |
| `wan-3.0-r2v` | 10 | **no start frame at all** — references only, addressed as `Image 1…` in the prompt | none |
| `wan-3.0-openrouter` | none | — | allowed — an optional start frame, no end frame, no references; the same model on OpenRouter, priced on the run |

So "start plus six references" is a Kling sentence, not a general one. The
submit path resolves every payload against the model it names and refuses what
would be dropped, before anything bills.

### What each engine will actually render — contact between two people

Measured 2026-09-18 on prod, several runs per engine: **a kiss between two
adults**, from a start frame that already showed it. Moderation is per engine,
and most of it costs nothing — a refusal lands before the render or after it,
and nothing is billed either way.

| engine | a kiss | signature | billed |
|---|---|---|---|
| `kling` | **renders it** — no refusal across several runs, start frame + `reference_images` | its one fault: with `generate_audio: true` it invents dialogue even when `avoid` lists talking, speaking, dialogue. Set `generate_audio: false` and add sound in post | yes |
| `wan-3.0-i2v` (fal) | **refused at submit** | HTTP `422` on `body.prompt` for the wording; with the word removed, `422` on `body` — the prompt and image together | no |
| `wan-3.0-openrouter` | accepts the submit, renders, then **fails at Alibaba's output checker** | `Green net check failed for image (output): Output data may contain inappropriate content.` | no |
| `seedance-2.5` | **refused** — a fully clothed kiss too, and a start frame that is already a kiss still | `E005 The input or output was flagged as sensitive` | no |
| `veo-3.1` | **renders it** | same-sex intimacy came back with the wrong dynamic twice; faces drifted in a push-in close-up. Its `negative_prompt` is real — the only engine with one — and it does suppress dialogue | yes |
| `wan-2.6-i2v` (Runpod) | **renders anything** — `enable_safety_checker: false`, and a real `negative_prompt` | the motion is flat: the kiss lands at 2 s and holds static; skin reads plastic next to Wan 3.0; silent output | yes |

Shirtless massage and other contact clips pass on fal's Wan 3.0; the line is
the kiss. Each engine's page carries its own row in one line.

The same line runs through the image engines, where the seed is made.
`gpt-image-2.5-sunburst` flags (`E005`) an edit that re-poses a shirtless man
together with a second man — "eyes locked, a foot apart" — and refuses a kiss
still. `seedream-5-pro` renders a kiss still: "kissing on the lips" passes,
clothed or shirtless, where "French kiss" / "open-mouthed" wording was
refused. `nano-banana-pro` at `safety_filter_level: block_only_high` re-poses
a shirtless figure without complaint.

## The loop

Per clip, and only two steps bill.

```bash
# 1. name the scene  (free)
studio scenes new <project> --name <name>

# 2. the seed still  (SHOWS THE PAYLOAD, THEN ASKS — bills, cents)
studio run --model replicate-gpt-image-2 --project <project> --scene <name> \
    --character <character> --prompt-file seed.txt --name seed

# 3. LOOK AT IT — hard rule #2b: a seed nobody looked at is a scene nobody wanted

# 4. clip 1, opening on the seed  (SHOWS THE PAYLOAD, THEN ASKS — bills, dollars)
studio run --model replicate-kling --project <project> --scene <name> \
    --start-run <project>/latest#1 --input-file shot-01.json --name shot-01
studio scenes add <project>/<name> <project>/latest

# 5. look at the clip, then carry its last frame into the next one
studio frames grid <project>/latest --count 4 --dest /tmp/check
studio frames last <project>/latest --add-input          # -> a node id
studio scenes frames <project>/<name> --args --max 7     # -> --key … --key …

# 6. clip 2, opening on that frame, referencing the scene's own frames
studio run --model replicate-kling --project <project> --scene <name> \
    --start-key <node id from step 5> --key <…> --key <…> \
    --input-file shot-02.json --name shot-02
studio scenes add <project>/<name> <project>/latest

# …repeat 5 and 6 for each clip, then cut
studio scenes assemble <project>/<name>
```

**Step 5 is not optional.** Each clip becomes the input to the one after it, so
an unnoticed defect is inherited by everything downstream and re-billed.
Looking costs nothing.

**`--dry-run` leaves a draft, and a draft can already be in the cut.** The
payload has an address: open it in the app, link to it, submit it later with
`studio runs submit` — when a person says to. There is no approve step; the
submit command is the act. A draft in the cut is what a planned scene looks
like; `assemble` names every run in the cut that has no clip yet.

**A run made without `--scene` is not in the scene.** `studio scenes add` puts
it there — naming a run in the cut joins it — and a run that belongs to another
scene is refused, because a run belongs to at most one.

### The still is the seed, not every clip's start frame

A cut is seamless only from the **literal last frame** of the clip before it.
A still composed for the same moment differs from that frame in a hundred small
ways, all of which read as a jump. So after clip 1 the handoff frame opens each
clip, and the seed is a reference — still steering where the scene goes, no
longer breaking the join.

### The end frame is where control lives

Every clip that went wrong on 2026-09-18 was a beat with no still pinning it.
A seated man whose shorts were hidden under the desk stood up in invented
jeans — on Wan 3.0 twice and Kling once. "He is shorter" in prose did nothing
until a reference still showed the two heights side by side. A whistle told to
go on the floor went on the desk. Prose loses to what the model can see, and
where it sees nothing it invents. Three rules:

- **A seed must SHOW the wardrobe that has to survive.** A garment the frame
  hides is a garment the model redraws the moment it comes into view. Render
  the seed with the shorts in shot, or accept whatever stands up.
- **Height and proportion between two people come from a still, never from
  prose.** A reference or end frame that shows the difference holds it; a
  sentence does not, however many times it is reworded.
- **Describe the end frame accurately.** A prompt that said "arms hanging in
  a V" against an end still with the arms raised behind the head made the
  model jerk the arms up in the last half-second to reach the still. The still
  wins, so the prompt's last line says what the still shows.

So a beat that must land somewhere exact is a bracketed clip, and the still
that pins it is made first, where it costs cents and can be looked at.
[`studio-media-wan-3-0-i2v`](../studio-media-wan-3-0-i2v/SKILL.md) is the
engine that takes both frames without dropping anything else.

## Continuity — what to hold, what to change

The largest source of inconsistency between clips is **workflow, not the model**.
Rewording between clips feels like refinement and is actually a different
creative direction each time, so every clip is self-consistent and inconsistent
with its neighbours. Kling has **no seed**, so byte-identical wording is the only
reproducibility lever that exists.

**Hold byte-identical across clips:** `style`, `camera` (unless the shot genuinely
moves), the drift terms in `negative`, `technical` (mode, resolution, audio).

**Change per clip:** `action`, and the parts of `subject` and `negative` that the
new action requires.

### The pose-continuity line

A start frame fixes appearance but **not intent** — without being told, the model
resets to a neutral pose on frame one and the cut jumps. Carry the current pose
into `subject`:

```json
"subject": "The two people from the source image, unchanged — already mid-action in a close hold, …"
```

and point `negative` at the reset:

```json
"negative": "the pose resetting, the subjects starting apart, …"
```

### `negative` has to be re-aimed every clip, and it is easy to miss

Terms that protected the previous clip will **fight** the next one. A clip that
ends an embrace needs the term that preserved it removed. The classic trap:
`changing wardrobe` is right for every clip until the clip where someone removes
a garment, where it silently opposes the whole shot.

Read `negative` against the new `action` each time and ask what now contradicts.

### Don't re-describe what the frame already shows

Standard image-to-video discipline, and it matters more here because every clip
after the first is driven by a frame: cut `scene` and `lighting`, keep `subject`
to an identity anchor plus the pose line. See `studio-media-prompt`.

## References for a clip come from the SCENE, not the character

Kling accepts `start_image` **and** `reference_images` together (Seedance does
not), so every clip after the first can carry references. **They should be the
scene's own frames**: the seed clip 1 started from, plus each handoff frame
produced since.

**Not the character's curated `reference/` set.** Those images were shot in a
different context — another location, another wardrobe, another light — so
feeding them in mid-scene pulls the render toward that context and fights the
continuity a scene exists to hold. The scene's own frames are already on-model
for *this* scene in every respect that matters: setting, clothing, grade, and
the current state of the action.

Reach into `reference/` **only when the scene introduces something the existing
frames cannot show** — a garment comes off and no frame yet shows the subject
without it, a prop appears, a new character enters. Then send only the images
that show that specific thing, and drop them again once a frame in the scene
covers it.

**The list is derived, not kept.** `studio scenes frames` reads it off the cut:
the first frame each clip in the cut opened on, in order. There is nothing to
maintain, and nothing that can drift from the scene it describes — which a
separate list beside the scene, written by hand, reliably did.

**Mind the cap** — Kling takes 7 images in total, the start frame included.
`--max` trims: the seed anchors the look the whole scene inherits and the newest
frames carry the current state, so both ends are kept and the middle gives way.

> **A sequence with no scene behind it** — clips you are chaining ad hoc — still
> has `studio frames chain`, which keeps its own list in
> `<project>/chains/<slug>.json`. Use it only when there is no scene; a scene
> already knows.

## `reference_video` is not continuation — don't reach for it

It looks like the answer and is not. Per the model's own README:

| `video_reference_type` | What it does |
|---|---|
| `base` | **Edits the supplied video** per the prompt. `duration` is ignored |
| `feature` | Borrows the reference's **camera movement and style** for new content |

Neither continues from the end. Also: **3–10 s only** (a 15 s clip must be
trimmed), `generate_audio` is **mutually exclusive** with it (`keep_original_sound`
is the only way to have sound), and `reference_images` drops 7 → 4.

`base` is genuinely the right tool for *"same moment, but they do this instead"*.
It is the wrong tool for *"and then…"*.

## Assembly

```bash
studio scenes assemble <project>/<name>
```

The cut is the order. The scene lands at `<project>/scenes/<scene_id>/` with
each clip copied into `shots/`, and the stitched video in `output/`.

Re-cutting **keeps the cut it displaces.** Each cut is its own file: the first is
`output/<name>.mp4` and later ones take a suffix, `<name>-2.mp4` and up. The
scene's `output` names the newest and `cuts` lists the rest, newest first — so
two takes of one scene can be put side by side, which is the thing re-cutting is
for. `studio scenes outputs <project>/<name>` lists every cut, and one not
worth keeping is deletable like any other file.

**`cuts` never holds the current take.** `studio scenes show` straight after
an assemble lists the new file under `output` only; it joins `cuts` when the
next assemble displaces it. Observed three times and read as a lag — it is the
design. The newest cut is `output`; `cuts` is what it replaced.

No cut yet? `studio scenes assemble <project>/<name> --shot <runref> --shot
<runref>` orders the cut first, then stitches — so "just stitch these three
clips" is still one command.

Clips that agree on codec, geometry, frame rate and audio layout are
**stream-copied** — the cut is bit-for-bit the sources joined end to end. Clips
produced by this loop on one engine agree automatically, because each inherits
its geometry from the previous clip's frame. Mixing in a clip rendered at
another `mode` or aspect forces a re-encode, which the scene's record notes.
**So does mixing engines**: Kling renders at 24 fps and Wan 3.0 at 30, so a
cut holding both re-encodes to the first clip's rate, with every clip
conformed on its own before the join — `stitch.method` says which rate and
what differed. Until 2026-09-18 that re-encode froze the 30 fps clips for
their whole length while their audio ran on; a scene cut before then that
mixes engines needs re-cutting.

**The encode happens in the service, not on this machine.** `assemble` resolves
each run in the cut to its clip and asks for the cut; the joining, the copies
and the record are done where the video toolchain lives. The command waits and
prints as it goes — and `Ctrl-C` abandons the wait rather than the cut, which
finishes either way and leaves the scene saying so.

A scene is one continuous take. When a piece has genuine breaks in it — a change
of place, of time, of subject — build each stretch as its own scene and cut them
together with **`studio-media-movie`**, rather than hiding a hard cut inside
something that is supposed to read as one shot.

**Colour-match in an editor if the joins show.** A hard cut amplifies small
differences between generations, and no prompt wording prevents that.

## Failure modes seen in a real scene

| Symptom | Why | Move |
|---|---|---|
| Pose jumps at a clip boundary | No pose-continuity line | Add it to `subject`; put `the pose resetting` in `negative` |
| A garment appears in-hand while still worn | Removal is compressed into too little time | Give the motion more seconds — not more words |
| A prop invents itself (a lanyard becomes a badge, then vanishes) | It is in the frame and absent from the prompt | Name persistent props in `subject`, or accept it |
| On-screen text re-mangles every clip | Lettering is never stable | Add text in post |
| Held stillness fills with unbidden motion | Models fill empty time | Shorten the clip — a still beat needs 3–6 s, not 15 |
| A contradictory pose resolves itself | the direction asks for contact and separation at once | Settle the geometry in a **still** first, where it costs cents |

## Cost, and where the gate goes

Kling standard is **$0.168/s**, **$0.224/s** with audio — so a 15 s clip with
audio is ~$3.36 and a four-clip scene is real money. Show the full payload and
ask before **every clip**, because every clip is its own submission
(`CLAUDE.md` rule 2). Pulling frames, adding to the cut and assembling move
bytes only and need no asking.

Length is a lever, not a default: a still beat rendered at 6 s costs a third of
15 s and drifts less. Pick the duration the beat needs.

**Assembling is free; every render is not.** Assemble often — after every
clip lands — to check the joins; a cut costs nothing and a bad join found at
clip 2 saves clips 3 and 4. Test an idea at the cheapest tier that can show
it: a still first ($0.05–0.15), then an 8 s `standard` clip. Never test an
idea at `pro` 12 s — that tier is for the take that has already been proved.

## Audio across clips

Direct it explicitly per clip — `generate_audio: true` alone tends to produce
arbitrary music. Name the ambience, name the sounds the action makes, and say
what to exclude. Keep the ambience wording **identical** across clips; it is
continuity like any other locked field, and a shifting soundbed makes joins
audible even when the picture matches.

**Ambience is held; SFX are not.** They are two layers and only one of them is
continuity. The room tone, the weather, the traffic behind the wall — identical
wording, every clip. The sounds a particular beat *makes* — a floorboard creak,
fabric shifting, a fork on a plate — are written into the beat that causes
them and change with it. Working Kling prompts carry both in a per-shot
`Audio:` line; keeping them in one undifferentiated block is what makes a
soundbed wander.

**A spoken line belongs in the first ~10 seconds of its clip.** On Kling,
lip-sync is reported to come apart past roughly that mark, which makes a
15 s clip carrying dialogue at the end a bad buy however well the picture
holds — see
[`studio-media-kling`](../studio-media-kling/SKILL.md#dialogue-holds-for-about-ten-seconds-then-lip-sync-drifts).
So a clip is cut where the talking stops: dialogue early, action late, and a
conversation that runs long becomes two clips rather than one long one. That
is a scene decision, not a prompt one — it changes where the boundaries go.
