---
name: studio-media-scene
description: Build a SCENE — a continuous piece longer than one generation — by storyboarding it as panels, rendering each shot from the previous shot's last frame, then stitching them into one cut. Use whenever a shot must run past a single model's duration ceiling (Kling stops at 15s), whenever a brief has several beats that must not be hard cuts, or whenever the user asks to continue, extend, or carry on from an existing clip. Owns the storyboard, the shot loop, the continuity rules that keep shots cutting together, the per-shot verification gate, and assembly via the scene store. For cutting several finished scenes into one piece, see studio-media-movie.
---

# studio-media-scene — a shot longer than one generation

`studio-media-shot` produces **one clip** from a brief: plan, still, animate. This
skill takes over where that stops — when the piece needs to run **past the
model's duration ceiling**, or through beats that must flow rather than cut.

The family:
- **`studio-media-shot`** — one brief → one clip. Start there.
- **`studio-media-scene`** (this) — many clips → one continuous piece.
- **`studio-media-s3`** — `studio frames` extracts the handoff frame and the
  verification grid; `studio scenes` is the scene store.
- **`studio-media-kling`** / **`studio-media-seedance`** — render each shot.

## Why build a scene out of shots

Three separate ceilings, and only a sequence of shots clears all three:

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
| Both | **a sequence of shots** — one take each, cut in post | An assembly step |

A sequence of shots is how you get both. Each shot is a single continuous take, and shot
boundaries are where the cuts go — deliberately, where you chose them.

## Storyboard first

A scene is planned before it is bought. Each shot gets one or more **panels** —
stills, which cost cents — so the flow can be read before any video bills. The
panels are not thrown away once looked at: they become the images the video
model renders from.

    plan  ->  panels  ->  shots  ->  the cut

The plan is a local JSON file you write and ingest. It is prose about a
particular scene, so it lives in the library as data — a node in the catalog,
under the scene it plans — never in the repository.

```json
{
  "characters": ["<name>"],
  "setting": "One paragraph — location, wardrobe, light, grade. Prepended
              byte-identical to every panel prompt.",
  "defaults": {
    "model": "kling", "panel_model": "nano-banana-pro",
    "duration": 5, "extra": {"mode": "standard", "generate_audio": false}
  },
  "shots": [
    {
      "id": "shot-01",
      "beat": "one line, for the board caption",
      "panels": [
        {"role": "start", "prompt": "the still prompt for this panel",
         "references": {"characters": ["<name>"], "pick_tag": "face"}},
        {"role": "sample", "prompt": "what the peak of this beat looks like"}
      ],
      "motion": {"prompt": "<the COMPILED prompt document — see below>", "duration": 10}
    }
  ]
}
```

### `motion.prompt` is a COMPILED document, not a paragraph

**Author it with `studio prompt`, and paste what it returns.** The field is a
string either way, and that is the trap — prose is accepted, renders, and looks
fine right up until the scene page draws it:

```bash
studio prompt shot.json --engine kling-replicate --emit prompt
# -> {"prompt": "{\n  \"subject\": …}", …}   ← the `prompt` STRING goes in motion.prompt
```

The app decides how to draw a motion prompt by trying to parse it. A compiled
document draws as **subject / action / camera / style / avoid**; a paragraph
draws as one undifferentiated block. So a hand-written scene looks unlike every
scene planned properly, and you find out after the plan is in.

The model's own preference is genuinely unsettled — Kuaishou's material uses
prose — so prose is **noted, not rejected** (`scenes check` says so before
anything bills). What it costs is everything around the model:

- **None of the authoring checks run** — one camera move, no bare `fast`, no
  camera verbs in the action, the beat budget, the phrasebook's per-model wording.
- **`camera` never becomes a field**, so "locked off" ends up buried in a sentence.
- **The negative is folded in by hand** rather than routed to wherever the target
  engine takes it — and Kling has no `negative_prompt` at all.
- **The locked template stops being enforceable.** Holding `style` and `camera`
  byte-identical across shots is the only reproducibility lever Kling has, since
  it has no seed, and nobody maintains byte-identical prose paragraphs.

Note that `negative` on the way in is called `avoid` on the way out; the
compiler renames it. `prompt_json` is a separate, mostly-unused field — it is
**not** where the document goes.

`id` is the merge key. Revising means re-ingesting with `--force`, which carries
every run, panel and cut across — so rewording a beat cannot orphan a clip you
already paid for. A panel whose prompt changed keeps its image and is marked
**stale**: the picture on disk no longer illustrates the words beside it. That is
a warning, not a block.

### Panels inherit from each other

Panel 1 renders from the character's references alone. Every later panel renders
from those **plus the panels already on the board**, so the board converges on
one location, wardrobe and grade instead of drifting a shot at a time. Two things
follow, and both bite if you do not expect them:

- the board renders **in order**, and
- **re-rendering panel *k* invalidates everything after it**, because they were
  rendered against the old one.

`setting` is the second, cheaper lever on the same problem: repeated
byte-identically in front of every panel prompt, it survives a panel being
re-rendered alone.

### What a panel is FOR — the four slots

A panel declares a `role`, and the role is the same question as **does this reach
the model at all**. Every one of them is optional; a shot may have none.

| role | sent as | how many | what it is for |
|---|---|---|---|
| `start` | the engine's first-frame field | 0–1 | the literal frame the shot opens on |
| `end` | the engine's last-frame field | 0–1 | the literal frame it lands on |
| `reference` | the engine's reference list | 0–n | steers the look; fixes no frame |
| **`sample`** | **nothing** | 0–n | **a picture of the shot, for a person** |

**A sample is never sent.** It exists so a fifteen-second render can be judged
before it is bought rather than after — a still that says "this is what this beat
should look like", which the model neither sees nor has to obey. It is a
storyboard artifact, not an input, and it is optional like everything else: board
a sample for the two shots you are unsure about and none for the rest.

Left unstated, roles fall back to **position** over the binding panels only —
first is `start`, last is `end`, the rest are `reference`. Samples are skipped in
that count, so `[sample, start]` has a start frame rather than a demoted one.
State the role when it matters; a shot with one panel and no role is a start
frame.

### Two ways to storyboard, and the choice is per scene

Both are supported and they differ only in **where the start frames come from**.

**Chained — one seed, every later shot inferred.** Shot 1 gets a start frame;
every later shot opens on the **literal last frame of the shot before it**, taken
with `scenes handoff`. This is the default and it is what makes a scene read as
one continuous take: only that exact frame makes the join invisible, and a panel
composed for the same moment differs from it in a hundred small ways that read as
a jump. The cost is that the scene must be rendered **in order** — shot N+1 has
no start frame until shot N exists.

**Bracketed — a start and an end frame per shot.** Every shot is pinned at both
ends by compositions you approved, and the model only invents the movement
between them. Use it when a beat has to land somewhere exact. Two costs: the
shots no longer chain from one another unless you also carry the handoff, and on
most engines **an end frame excludes the reference list entirely** (see the table
below), so the two frames have to say everything.

They mix. A scene is chained by default and a single shot can be bracketed by
giving it an `end` panel; a shot that deliberately opens on a new composition
sets `use_handoff: false` and keeps its own start panel.

### What each engine will actually accept

Read off the registry rather than restated per skill, because it is what the
submit path enforces — `studio models show <model>` prints it.

| engine | reference cap | start + references | end frame |
|---|---|---|---|
| `kling` | 7 | yes — but **the start frame counts toward the 7** | **excludes all references** |
| `seedance` | 9 | **no — a start frame excludes references** | allowed |
| `veo-3.1` | 3 | yes | **excludes all references** |
| `grok-imagine-video` | none | — | none |

So "start plus six references" is a Kling sentence, not a general one. Author the
plan in slots and let the engine's own rules decide what survives; `studio scenes
check` resolves every shot against the model it names and reports what would be
dropped, before anything bills.

## The loop

Per shot, and only two steps bill.

```bash
# 1. write the plan, then ingest it  (free)
studio scenes new <project> --slug <slug> --from-json plan.json
studio scenes plan <project>/<slug>          # read it back as a table
studio scenes check <project>/<slug>         # would every payload be accepted?

# 2. render the panels  (APPROVAL GATE — bills, cents each)
studio scenes board <project>/<slug> --dry-run --review-sheet /tmp/board
studio scenes board <project>/<slug>

# 3. LOOK AT THE BOARD — a sheet can be read, a plan cannot
studio scenes sheet <project>/<slug> --out /tmp/board

# 4. render one shot  (APPROVAL GATE — bills, dollars)
studio scenes render <project>/<slug> --shot 1

# 5. look at the clip, then carry its last frame into the next shot
studio frames grid <project>/latest --count 4 --dest /tmp/check
studio scenes handoff <project>/<slug> --shot 2

# …repeat 4 and 5 for each shot, then cut
studio scenes assemble <project>/<slug>
```

**Step 3 is not optional.** Each panel becomes the input to the next, and each
shot becomes the input to the one after it, so an unnoticed defect is inherited
by everything downstream and re-billed. Looking costs nothing.

**`--shot` is required on `render`.** There is no whole-scene default: a
four-shot scene with audio is real money, and shot N+1's start frame does not
exist until shot N is rendered and its handoff taken.

### `--dry-run` leaves a draft, and a draft has to be put back on its shot

`scenes render --dry-run` writes a **draft run per shot** rather than printing a
payload that scrolls away, so the thing hard rule #2 asks a person to read has an
address: it can be opened in the app, linked to, and approved later.

```bash
studio scenes render <project>/<slug> --shot 1 --dry-run   # -> draft run-…
studio runs approve run-…                                  # read it, say yes
studio runs submit run-…                                   # bills
studio scenes attach <project>/<slug> --shot 1 --run run-… # tell the scene
```

**That last line is not optional and is easy to miss.** `scenes render` without
`--dry-run` records the run on the shot itself; a run submitted any other way —
from one of these drafts, from `studio run`, or re-submitted after a wedged one
was deleted — does not know it belongs to a shot. The scene is then left holding
shots that have plainly rendered while `run` stays null, and the failure surfaces
much later and somewhere else:

- `scenes handoff` finds no previous shot to carry a frame from, and
- `scenes assemble` refuses the cut with *"N shot(s) have not been rendered"*.

`scenes attach` is what closes that loop. It takes a run that **succeeded** and
is of **kind `video`** — attaching a draft, a failed run or a still would put a
shot into `rendered` with nothing to cut, which is the same broken scene reached
from the other side.

**`scenes handoff` replaces the old three-step dance** of grabbing a frame,
adding it to the input pool and recording it in a list kept beside the scene.
The scene now records it directly, so there is no second list to point at the
wrong thing — which the hand version could and did.

### The panel is usually not the start frame

A cut is seamless only from the **literal last frame** of the shot before it. A
panel composed for the same moment differs from that frame in a hundred small
ways, all of which read as a jump. So once a shot has a handoff frame, the
handoff opens the shot and the start panel **is demoted to a reference** — still
steering where the shot goes, no longer breaking the join. The render says so
when it happens.

Shot 1 has nothing before it, so its first panel really is its start frame. A
shot that deliberately opens on a new composition can set `use_handoff: false`
and keep its panel.

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
to an identity anchor plus the pose line. See `studio-media-prompt`.

## References for a shot come from the SCENE, not the character

Kling accepts `start_image` **and** `reference_images` together (Seedance does
not), so every shot after the first can carry references. **They should be the
scene's own frames**: the image shot 1 started from, plus each handoff frame
produced since.

**Not the character's curated `reference/` set.** Those images were shot in a
different context — another location, another wardrobe, another light — so
feeding them in mid-scene pulls the render toward that context and fights the
continuity a scene exists to hold. The scene's own frames are already on-model
for *this* scene in every respect that matters: setting, clothing, grade, and the
current state of the action.

Reach into `reference/` **only when the scene introduces something the existing
frames cannot show** — a garment comes off and no frame yet shows the subject
without it, a prop appears, a new character enters. Then send only the images
that show that specific thing, and drop them again once a frame in the scene
covers it.

**The list is derived, not kept.** `studio scenes render` reads it off the plan:
shot 1's opening panel is the seed, and every later shot's recorded handoff is
the frame the shot before it produced. There is nothing to maintain, and nothing
that can drift from the scene it describes — which a separate list beside the
scene, written by hand, reliably did.

**Mind the cap** — Kling takes 7 images in total, the start frame included. Set
`max_scene_frames` in a shot's `motion.references` to trim: the seed anchors the
look the whole scene inherits and the newest frames carry the current state, so
both ends are kept and the middle gives way.

> **A sequence with no scene behind it** — clips you are chaining ad hoc, with no
> plan — still has `studio frames chain`, which keeps its own list in
> `<project>/chains/<slug>.json`. Use it only when there is no scene; for
> anything planned, the scene already knows.

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
studio scenes assemble <project>/<slug>
```

Shot order is cut order, taken from the plan. The scene lands at
`<project>/scenes/<slug>/` with the source clips copied
into `shots/`, and the stitched video in `output/`.

Re-cutting **overwrites** `output/<slug>.mp4`: the path keeps its record, so
everything naming the scene stays true, and the folder shows current state
instead of accumulating cuts nobody prunes.

**Do not count on getting the previous cut back.** Production keeps prior
revisions; a local dev stack deliberately does not, and your commands run
against a dev stack. If a cut is worth keeping, keep it under its own slug
before re-cutting — this is the page you are on when you re-cut, so it is the
page that has to say so.

No storyboard? `studio scenes assemble <project>/<slug> --shot <runref> --shot
<runref>` appends runs directly, so "just stitch these three clips" is still one
command and a board stays optional.

Shots that agree on codec, geometry, frame rate and audio layout are
**stream-copied** — the cut is bit-for-bit the sources joined end to end. Shots
produced by this loop agree automatically, because each inherits its geometry
from the previous shot's frame. Mixing in a clip rendered at another `mode` or
aspect forces a re-encode, which the scene's record notes.

A scene is one continuous take. When a piece has genuine breaks in it — a change
of place, of time, of subject — build each stretch as its own scene and cut them
together with **`studio-media-movie`**, rather than hiding a hard cut inside something
that is supposed to read as one shot.

**Colour-match in an editor if the joins show.** A hard cut amplifies small
differences between generations, and no prompt wording prevents that.

## Failure modes seen in a real scene

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
