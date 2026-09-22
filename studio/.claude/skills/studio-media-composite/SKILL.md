---
name: studio-media-composite
description: Lay several images out as ONE multi-angle plate — a front, a three-quarter and a back on a single sheet — so a turnaround reaches an engine that takes only one image, or spends only one of its reference slots. Use when a model has a single `image` field, when a reference cap is tight, when a subject keeps coming back with the wrong profile or the wrong build, or when a request asks for a character sheet, a turnaround sheet, a contact strip or a multi-view reference. The plate is an ordinary node in the subject's tree, described and tagged beside the panels it was made from.
---

# studio-media-composite

**One image can hold several views of one subject, and most engines never find
that out.** A model given a single frontal headshot renders a convincing front
and invents the profile; given a front, a three-quarter and a back on one sheet,
it has the turn. The sheet costs one slot.

That is the whole idea. `studio composite` is the verb.

```bash
studio composite --key <node> --key <node> --key <node> \
    --dest-key <subject-root>/reference/wardrobe/<outfit>/<file>.png
```

## When a plate is the right move

| Situation | Why a plate helps |
|---|---|
| The engine takes **one** image — a start frame, a lone `image` field | The only way to show more than one view at all |
| The reference cap is tight | Kling counts seven *including* the start frame, so three loose angles plus a frame is over half the budget; one plate leaves room for the location and the previous clip's last frame |
| The subject renders frontally whatever you ask | The profile it never saw is now in frame |
| The build comes back at the model's defaults | A head-to-feet row states proportion in pixels, not adjectives |
| Two subjects in one shot, both on-model | Each gets one plate instead of three of a shared budget |

**When it is the wrong move:** a plate is not a substitute for sending the
right single reference. `studio-media-character` measures this — a profile shot
wants the profile reference and nothing arguing with it, and a plate that
includes the front is a plate that includes the argument. Reach for a plate when
the slot count forces the issue or when one image must carry the whole turn, not
as a default.

**Composite the renders that were already approved — never prompt a model for a
sheet.** Asked for a three-angle triptych, a model returns three *new* faces in
one file: a fresh roll of the die, baked into a single node that then reads as
authoritative. This command assembles pixels somebody has already looked at,
which is the whole reason it is a Pillow operation and not a generation.

**Not `studio contact-sheet`.** That builds a captioned grid of a whole pool
into `review/`, for eyeballing which pose is which — the captions are baked into
the pixels, which makes it the wrong image to send a model.

## Choosing the three

**This is the judgement, and nothing automates it.** The command lays out what
it is given, in the order it is given, and sorts nothing — a plate built from
the wrong three is worse than no plate.

The default triple is **front, three-quarter, back**. It is a rotation: each
panel shows something the others do not, and together they close the turn.
Adding the second three-quarter or a profile is a fourth panel, not a
replacement for one of these.

Two rules that bite:

- **Direction is the edge of frame the face points toward**, the same as it is
  in a turnaround. `three-quarter-right` means the nose points at the right edge.
- **Prefer a genuine render over a mirrored one.** A subject's set usually holds
  both three-quarters and one of them is a horizontal flip of the other, tagged
  `mirrored`. A plate carrying two views of the same pixels shows the model one
  angle and claims two.

Find them by tag rather than by filename:

```bash
studio character images <name> --tag wardrobe,<outfit>
studio character images <name> --tag body,front
```

## The four plates a wardrobe wants

A subject photographed in an outfit usually has four sheets worth making, and
they are not interchangeable:

| Plate | Panels | Carries |
|---|---|---|
| dressed headshots | the three headshot angles, in the outfit | the face, and the collar and neckline |
| dressed full-length | the three body angles, in the outfit | the outfit's cut, length and fall |
| undressed headshots | the three headshot angles, without the top | the face and the neck, nothing a garment hides |
| undressed full-length | the three body angles, without the top | the build itself — the thing prose is worst at |

The undressed pair is not a variant of the dressed pair. A garment hides the
shoulder line and the waist, which is exactly what a model guesses wrong; a
plate that states them is what stops the guess. Both halves matter, because a
plate showing only the build gives the wardrobe nothing to copy.

**A plate is only true for the outfit it shows**, so a wardrobe change is a new
pair rather than an edit — which is why the filing convention is one pair per
wardrobe and the undressed look counts as its own.

## The geometry, and why it is printed

```bash
studio composite --key <node> --key <node> --key <node> \
    --gap 6 --direction row --background '#ffffff' \
    --dest-key <subject-root>/reference/wardrobe/<outfit>/<file>.png
```

**Panels are normalised to a common edge — downscale only.** The shortest panel
sets a row's height; the narrowest sets a column's width. A panel smaller than
its neighbours is the reason to shrink them, never to invent pixels for it: a
genuine render beside an upscaled one reads as two subjects. The command says on
stderr when it rescaled anything, because the finished sheet does not show it.

**The gutter is not decoration, and 0 is the wrong default.** Panels butted edge
to edge on a shared white ground merge: two shoulders meet at the seam and one
figure appears to have four arms. `--gap` is a **percentage of the panel edge**
rather than a pixel count, so the same number lays the same-looking sheet out of
600-pixel panels and out of 1536-pixel ones. It defaults to 6 and runs around
the outside as well, so no figure sits against the sheet's edge.

**`--background` is only visible in the gutter.** A white gutter behind panels
already shot on a white seamless backdrop is invisible and separates them
perfectly well — the point is the gap, not a line. Reach for a colour when the
panels' own grounds differ and the sheet needs to read as deliberate.

`--to` and `--quality` behave as they do on `studio convert`. The format follows
the first panel unless told otherwise; a 3×1536-pixel PNG plate is 4–8 MB, which
every engine here accepts, and `--to jpg` takes it under 1 MB if a cap bites.

**Nothing is modified.** The panels survive the plate — it is a new node beside
them, and the turnaround is still a turnaround.

## Filing a plate

A plate lands wherever `--dest-key` says, and **beside its panels is usually
right**: it is a view of the same subject in the same outfit, and a reader
finding the outfit should find the sheet. `--add-input <project>` is the other
destination, for a plate made to feed one specific piece of work.

Then describe it, because an undescribed image is invisible to whoever chooses a
reference set:

```bash
studio describe <node> --text "Three angles on one sheet: front, three-quarter
  right, back, left to right. <what they are wearing>. A multi-angle reference
  plate — the three source renders composited, not a new generation." \
  --tag wardrobe --tag composite --tag multi-angle --tag full-body
```

Tag `composite` and `multi-angle` so the plates are findable as a family, and
**carry every angle the sheet contains** — `front`, `three-quarter-right`,
`back`. Tag-based selection is how a subject is chosen from, so a plate that
does not carry its angles is a picture nobody can pick.

**Say in the description that it is composited.** A plate is derived from images
already in the library, and a reader who mistakes it for an independent render
counts the same evidence three times.

## Keep it out of the default set

**A plate is an alternative to the `default` set, not a member of it.** Sending
both ships the same three angles twice and spends exactly the cap the plate
exists to save. So it is tagged `composite` and its angles, and it is not tagged
`default`.

That is also the identity gate answering itself: compositing spends nothing, so
hard rule #2 is not at stake here, but hard rule #2b is — putting `default` on
an image is a person's decision, made separately from anything else agreed to.
`studio-media-character` states both gates and what broke when they were
inferred.

## Handing a plate to an engine

A plate is an ordinary image node, so every route an image takes is open to it —
`--pick` it by node, or `--pick-tag composite` to send the family.

**Say what it is in the prompt.** A model shown a sheet with no explanation may
render the sheet: three figures on a white ground, side by side. One sentence
prevents it — *"the reference image is a three-view sheet of one person: front,
three-quarter and back of the same subject"* — and it belongs in the prompt's
subject, beside the `[ImageN]` citation.

**Slot N is still position N in the resolved selection.** A plate occupies one
slot however many views it holds, which is the point.

## Related

- `studio-media-character` — the turnaround the panels come from, the standard
  set, the tags, and both human gates
- `studio-media-image` — the frame-first workflow and the image engines
- `studio-media-s3` — addressing, uploading and presigning anything in the tree
- `studio-media-kling`, `studio-media-seedance` — the reference caps a plate is
  usually working around
