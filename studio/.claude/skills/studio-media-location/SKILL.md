---
name: studio-media-location
description: Manage LOCATIONS — the places a frame is shot in (a room, a set, a street, a stage) whose bible and reference views live in studio's media library, so a set built once can be described once and rendered on-model in every later frame. Use whenever a request names a recurring place, wants to build, describe, photograph or inspect one, or wants a character rendered IN a known setting. A location is DATA (a catalog record with a folder of images) managed by this one skill, the same way studio-media-character manages every character; `--location` on `studio run` binds one beside the cast.
---

# studio-media-location

A location is **where the frame is** — a kitchen, a back alley, a stage set —
and it has to look the same from one render to the next the way a character
does. Studio houses it exactly as it houses a character: a record with a
bible, a folder of images, and `default`-tagged views a generation is shown.
Part of the **`studio-*`** family:

- **`studio-media-location`** (this skill) — owns the place: the bible + views.
- **`studio-media-character`** — owns who is in it; the two bind side by side.
- **`studio-media-image`** / an engine skill — render the frame.
- **`studio-media-prompt`** — authors the prompt, citing the views by slot.

> **A set you have built is not housed until it is a location.** A folder of
> renders in a project is a run's output; nothing later can ask for "the
> kitchen" by name, narrow to its wide, or find every shot made in it. Make
> the location, copy the keeper views into it, tag them, write the bible.
> After that `--location <name>` is the whole of putting a frame there.

## Where a location lives

**A location is a record, not a folder.** An id that never changes, a free-text
`name` that is a label, a bible held as structured fields, and described views
— all queryable. It owns a folder, named by its id, where its images live. Two
locations may share a name; every address is the id. **`studio-media-s3`** is
the storage layer; `studio login` is the auth.

```
<place>/reference/    the views a generation is shown — tag `default` + a vantage
<place>/corpus/       photographs, plans, mood boards. Material, not identity.
<place>/archive/      retired material
```

These names are a convention, made on first use. Rename one, add your own —
an image is a reference because a tag says so, never because of its folder.

A location holds **no production history**. Runs belong to a project; a run
records where it was shot, so `studio runs find --location <place>` answers
"every frame made in this room" across every project.

## The bible: what is FIXED, where the light is, where the camera stands

A location has no face and no wardrobe. What holds it on-model is its
geography, so the schema (`studio location create` seeds it) is:

| Section | What goes in it |
|---|---|
| `identity` | the card: kind, scale, era and place, 2–4 signature cues, register |
| `space` | what is FIXED — the plan, floor, walls, ceiling, openings, built-in furniture, materials, condition |
| `dressing` | what is in it and could move — props with placement, signage text verbatim, clutter |
| `lighting` | every source, the named **states** (day, night, practicals only), colour temperature, mood |
| `palette` | dominant colours, accents, textures |
| `rendering` | default style, framing, lens, and the named **vantages** — camera positions a shot can be called for by |
| `consistency` | must / never / drift_modes — the checklist a render is read back against |
| `text_identity_block` | ~50–70 words for engines with no reference system: the plan, the fixed furniture, the light sources, the materials |

**Name the vantages and the lighting states, then USE the names.** A prompt
that says "reverse to the window, night" against a bible that defines both is
repeatable; one that describes the room again from scratch every time drifts
the way a character prompt drifts without a bible.

```bash
studio location create <place>            # the record, seeded from the blank template
studio location edit <place>              # pull the bible to a local YAML; re-run to push
studio location show <place> --profile    # the bible as one document
studio location textblock <place>         # the raw material for the ~60-word block
```

## Views: a location is a library, and TAGS say which part to send

The engines cap reference images hard and send them in full, and a location's
views join **the same list as the characters'** — after them, so the prompt
cites `[ImageN]` by the slot each lands in. So a location has to choose too,
and it chooses the way a character does: a tag on the file.

    default              this is one of the views a generation is shown
    wide reverse detail  what the view is — a VANTAGE, and any word you like
    plan                 a floor plan or an overhead; sent when the layout matters

```bash
studio location images <place>                        # every image, and how it is tagged
studio describe <node> --tag default --tag wide       # this is what makes it a view
studio location selection <place>                     # the `default` views
studio location selection <place> --tag wide --presign  # narrowed to a vantage
```

**Two or three `default` views, not eight.** A character's face and a room's
wide compete for the same cap; three views of the same wall push out the
reference that holds the face. Tag the establishing wide and one reverse
`default`; leave the details tagged by vantage and reach for them with
`--location-tag detail` when a shot needs one.

**Describe every view you add.** An undescribed image is invisible to whoever
chooses the set:

```bash
studio describe <node> --text "Wide from the door: counter left, window ahead, table right." \
  --tag default --tag wide
```

## Rendering a frame in a location

```bash
studio run --model nano-banana-pro --project <project> \
  --character <name> --location <place> --location-tag wide \
  --prompt "<name> at the counter, night state, reverse to the window" --dry-run
```

`--location` is repeatable. Its views land after every character's in the
reference list; `--location-tag` narrows every location named. The draft
records `locations` beside `characters`, so the project feed filters by it
and `runs find --location` finds it. **Hard rule #2 is unchanged**: `--dry-run`
shows the payload, a person says yes, `studio runs submit` sends.

Driving an engine with no reference system, paste the location's
`text_identity_block` beside the character's — `studio location textblock
<place>` prints the block, or the raw sections to write it from.

## THE TWO HUMAN GATES

Both of `studio-media-character`'s gates hold here, unchanged:

1. **Spending.** Show the complete payload, wait for a yes to *that payload*,
   submit only when told.
2. **Identity.** A rendered view of a room does **not** become the room's
   identity because it rendered well. Show it, wait for a yes, then copy it
   into the location's tree and tag it. A run leaves its results where they
   are; the copy is the act, and in the app it is `Copy into a character or
   location…` on the run's output.

```bash
studio download <project>/latest#1 --dest /tmp/promote
studio upload --folder <loc-id>/reference /tmp/promote/<file>   # the id `studio location show` prints
studio describe <node> --tag default --tag wide
```

**`--folder` takes the location's id, not its name.** An entity's root folder
is named by its id, and `studio upload` walks folder names from the library
root — so `<place>/reference` makes a loose folder called `<place>` beside the
location rather than filing into it. `studio location add-to <place> corpus
<file>` resolves the name for you and is the right door for material; the
identity pool is filed by id and tagged.

## Building a set from nothing

A set that does not exist yet is rendered before it is housed, and the order
matters:

1. **Write the bible first** — the plan, the fixed furniture, the light
   sources. A render made from a bible is a render the next one can be checked
   against; one made from a loose prompt is a picture of somewhere.
2. **Render the establishing wide** from the bible's `space` and `lighting`
   text, empty of characters, in the `default_style` (`studio-media-image`).
3. **Promote it** — gate #2 — as `default` + `wide`.
4. **Render the reverse and any detail** with the wide bound as `--location`,
   so they agree with it; promote each by vantage.
5. Only now put a character in it.

## The management tool

```bash
studio location list                                   # every location
studio location show <place>                           # the record: bible, tags, folders
studio location create <place>                         # new record, blank bible
studio location set-profile <place> /tmp/<place>.yaml  # replace the bible
studio location edit <place>                           # pull; edit; re-run to push
studio location images <place>                         # every image, and how it is tagged
studio location selection <place> --presign --json     # generation-time: ordered signed URLs
studio location pool <place> corpus                    # material, not identity
studio location add-to <place> corpus plan.pdf photo.jpg
studio location rename <old> <new>                     # one field on one row
studio location delete <place>                         # refuses while a project or run names it
```

Every command is `studio character`'s under a different noun — one command
tree, built twice — so anything the character skill says about `edit`, `rev`
conflicts, pools and curation holds here verbatim. Hard rule #1 holds too: a
production location is never named in the repo.
