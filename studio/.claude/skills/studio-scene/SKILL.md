---
name: studio-scene
description: Build a SCENE — a continuous piece longer than one generation — by chaining video runs, each starting from the previous clip's last frame, then stitching them into one cut. Use whenever a shot must run past a single model's duration ceiling (Kling stops at 15s), whenever a brief has several beats that must not be hard cuts, or whenever the user asks to continue, extend, or carry on from an existing clip. Owns the chain loop, the continuity rules that keep shots cutting together, the per-shot verification gate, and assembly via the scene store. For cutting several finished scenes into one piece, see studio-movie.
---

# studio-scene — a shot longer than one generation

`studio-shot` produces **one clip** from a brief: plan, still, animate. This
skill takes over where that stops — when the piece needs to run **past the
model's duration ceiling**, or through beats that must flow rather than cut.

The family:
- **`studio-shot`** — one brief → one clip. Start there.
- **`studio-scene`** (this) — many clips → one continuous piece.
- **`studio-s3`** — `studio frames` extracts the handoff frame and the
  verification grid; `studio scenes` is the scene store.
- **`studio-kling`** / **`studio-seedance`** — render each shot.

## Why chain at all

Three separate ceilings, and only chaining clears all three:

1. **Duration.** Kling caps at **15 s**. A 40-second piece is not one render.
2. **Drift is cumulative *within* a generation.** Faces and hands go first, and
   the back half of a long take is where they go. Four short shots each hold
   together better than one long one — the trade is that drift now appears
   *between* shots instead, which the continuity rules below manage.
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
| Both | **chain shots** — one take each, cut in post | An assembly step |

Chaining is how you get both. Each shot is a single continuous take, and shot
boundaries are where the cuts go — deliberately, where you chose them.

## The loop

Per shot, four steps. Only step 1 bills.

```bash
# 0. ONCE, before shot 2: name what shot 1 started from
studio frames chain <project>/<slug> --seed projects/<project>/input/<project>_in_<n>.png

# 1. render this shot from the previous frame, with the SCENE'S OWN frames as
#    references  (APPROVAL GATE — bills)
studio run --model kling --project <project> --input-file input.json --prompt-json shot.json \
  --project <project> --start-key projects/<project>/input/<project>_in_<n>.png \
  $(studio frames chain <project>/<slug> --args --max 7) \
  --slug <slug>-shot2 --poll

# 2. LOOK AT IT — a contact sheet can be read, a video cannot
studio frames grid <project>/latest --count 4 --dest /tmp/check

# 3. take the handoff frame into the input pool AND into the chain
studio frames last <project>/latest --add-input --chain <slug>

# 4. …repeat for the next shot, then assemble
studio scenes new <name> --slug <slug> \
  --shot <project>/<run_id>#1 --shot <project>/<run_id>#1 --shot <project>/latest#1
```

**Step 2 is not optional.** Each shot becomes the *input* to the next, so an
unnoticed defect is inherited by everything downstream and re-billed. Checking a
clip costs nothing; discovering the problem three shots later costs three shots.

**Step 3 writes to the input pool, never `reference/`.** An extracted frame is
model output. Chaining from `input/` is correct; promoting generated pixels into
the curated identity set is how drift compounds.

**Step 1's references are the scene's own frames, not the character's.** This is
the easiest thing in the whole loop to get wrong, because reaching for
`--character` is the habit everywhere else in the harness. See the section below
— it costs continuity, and the damage is inherited by every later shot.

## Continuity — what to hold, what to change

The largest source of inconsistency between shots is **workflow, not the model**.
Rewording between shots feels like refinement and is actually a different
creative direction each time, so every shot is self-consistent and inconsistent
with its neighbours. Kling has **no seed**, so byte-identical wording is the only
reproducibility lever that exists.

**Hold byte-identical across shots:** `style`, `camera` (unless the shot genuinely
moves), the drift terms in `negative`, `technical` (mode, resolution, audio).

**Change per shot:** `action`, and the parts of `subject` and `negative` that the
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

### `negative` has to be re-aimed every shot, and it is easy to miss

Terms that protected the previous shot will **fight** the next one. A shot that
ends an embrace needs the term that preserved it removed. The classic trap:
`changing wardrobe` is right for every shot until the shot where someone removes
a garment, where it silently opposes the whole shot.

Read `negative` against the new `action` each time and ask what now contradicts.

### Don't re-describe what the frame already shows

Standard image-to-video discipline, and it matters more here because every shot
after the first is driven by a frame: cut `scene` and `lighting`, keep `subject`
to an identity anchor plus the pose line. See `studio-prompt`.

## References for a shot come from the SCENE, not the character

Kling accepts `start_image` **and** `reference_images` together (Seedance does
not), so every shot after the first can carry references. **They should be the
scene's own frames**: the image shot 1 started from, plus each handoff frame
produced since.

**Not the character's curated `reference/` set.** Those images were shot in a
different context — another location, another wardrobe, another light — so
feeding them in mid-scene pulls the render toward that context and fights the
continuity the chain exists to hold. The scene's own frames are already on-model
for *this* scene in every respect that matters: setting, clothing, grade, and the
current state of the action.

Reach into `reference/` **only when the scene introduces something the existing
frames cannot show** — a garment comes off and no frame yet shows the subject
without it, a prop appears, a new character enters. Then send only the images
that show that specific thing, and drop them again once a frame in the chain
covers it.

`--chain` makes the list derived rather than remembered:

```bash
# once, naming what shot 1 started from
studio frames chain <project>/<slug> --seed projects/<project>/input/<project>_in_<n>.png

# each shot: the handoff frame is recorded as it is produced
studio frames last <project>/latest --add-input --chain <slug>

# next shot: paste the references straight in
studio run --model kling --project <project> … \
  $(studio frames chain <project>/<slug> --args --max 7)
```

**Mind the cap** — Kling takes 7 (4 alongside a reference video), so `--character`
on a larger curated set errors out anyway. `--max` trims by dropping the *middle*
of the chain: the seed anchors the look the whole scene inherits and the newest
frames carry the current state, so both ends are kept.

## `reference_video` is not continuation — don't reach for it

It looks like the answer and is not. Per the model's own README:

| `video_reference_type` | What it does |
|---|---|
| `base` | **Edits the supplied video** per the prompt. `duration` is ignored |
| `feature` | Borrows the reference's **camera movement and style** for new content |

Neither continues from the end. Also: **3–10 s only** (a 15 s shot must be
trimmed), `generate_audio` is **mutually exclusive** with it (`keep_original_sound`
is the only way to have sound), and `reference_images` drops 7 → 4.

`base` is genuinely the right tool for *"same moment, but they do this instead"*.
It is the wrong tool for *"and then…"*.

## Assembly

```bash
studio scenes new <project> --slug <slug> --shot <runref> --shot <runref> …
```

`--shot` order is cut order. The scene lands at
`projects/<project>/scenes/<YYYY-MM-DD_HH-MM-SS>_<slug>/` with `scene.json`, the
source clips copied into `shots/`, and the stitched video in `output/`.

Shots that agree on codec, geometry, frame rate and audio layout are
**stream-copied** — the cut is bit-for-bit the sources joined end to end. Shots
chained through this loop agree automatically, because each inherits its geometry
from the previous shot's frame. Mixing in a clip rendered at another `mode` or
aspect forces a re-encode, which `scene.json` records.

A scene is one continuous take. When a piece has genuine breaks in it — a change
of place, of time, of subject — build each stretch as its own scene and cut them
together with **`studio-movie`**, rather than hiding a hard cut inside something
that is supposed to read as one shot.

**Colour-match in an editor if the joins show.** A hard cut amplifies small
differences between generations, and no prompt wording prevents that.

## Failure modes seen in a real chain

| Symptom | Why | Move |
|---|---|---|
| Pose jumps at a shot boundary | No pose-continuity line | Add it to `subject`; put `the pose resetting` in `negative` |
| A garment appears in-hand while still worn | Removal is compressed into too little time | Give the motion more seconds — not more words |
| A prop invents itself (a lanyard becomes a badge, then vanishes) | It is in the frame and absent from the prompt | Name persistent props in `subject`, or accept it |
| On-screen text re-mangles every shot | Lettering is never stable | Add text in post |
| Held stillness fills with unbidden motion | Models fill empty time | Shorten the shot — a still beat needs 3–6 s, not 15 |
| A contradictory pose resolves itself | the direction asks for contact and separation at once | Settle the geometry in a **still** first, where it costs cents |

## Cost, and where the gate goes

Kling standard is **$0.168/s**, **$0.224/s** with audio — so a 15 s shot with
audio is ~$3.36 and a four-shot scene is real money. The full-payload approval
gate applies to **every shot**, because every shot is its own submission
(`CLAUDE.md` rule 2). Steps 2–4 move bytes only and need no approval.

Length is a lever, not a default: a still beat rendered at 6 s costs a third of
15 s and drifts less. Pick the duration the beat needs.

## Audio across shots

Direct it explicitly per shot — `generate_audio: true` alone tends to produce
arbitrary music. Name the ambience, name the sounds the action makes, and say
what to exclude. Keep the ambience wording **identical** across shots; it is
continuity like any other locked field, and a shifting soundbed makes joins
audible even when the picture matches.
