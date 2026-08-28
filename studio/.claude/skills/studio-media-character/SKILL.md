---
name: studio-media-character
description: Manage on-model characters — create, update, list, curate, and load a character whose profile bible and reference library live in studio's media library. Use whenever a request names a known/recurring character, or the user wants to add, edit, describe, curate, or inspect one. A character is DATA (a catalog record with a folder of images), not a per-character skill: this one skill manages them all, and its described reference index is how a SUBSET of a large reference library is chosen for a generation instead of sending the folder whole.
---

# studio-media-character

Characters are **data, not skills.** Instead of a skill per character, every
character is an S3 record managed by this one skill, used by the video pipeline
(`studio-media-prompt` to author the prompt, an engine skill to render). Part of the
**`studio-*`** family:

- **`studio-media-character`** (this skill) — owns character identity: the bible + refs.
- **`studio-media-prompt`** — authors the prompt as structured JSON, per engine.
- **`studio-media-seedance`** — renders via Seedance 2.0 on Replicate, saves to S3.
- **`studio-media-kling`** — renders via Kling 3.0 / O3 Omni on Replicate.

> **MANDATORY for any character video: never generate from a bare text prompt.**
> How identity is carried depends on the engine — on **Seedance**, pass the
> reference set in `reference_images`; on **Kling via Replicate** the same field
> exists (up to 7 images), so the set carries over — note Kling takes only
> `.jpg/.jpeg/.png`, so a `.webp` set needs converting. Driving from a start
> frame instead, paste a compressed identity block (`studio character textblock
> <name>`). Either way identity comes from the images + bible, motion/framing
> from the prompt.

## Where a character lives (S3)

**A character is a record, not a folder.** It has an id that never changes, a
`slug` you type, a bible held as structured fields, and a set of described
references — all of it queryable. It also owns a folder, `<name>/`, where its
images actually live. The generic **`studio-media-s3`** skill is the storage
layer; `studio login` is the auth.

```
<name>/reference/     the images its references point at, in purpose
                      subfolders: face/ body/ wardrobe/ frame/ …
<name>/corpus/        collected material — uploads, keeper clips.
                      Material, not identity.
<name>/seed/          the founding real-world source photos
<name>/archive/       retired material
```

**The bible is not a file.** There is no `profile.yaml` to fetch: identity is a
validated map on the record, which is why `studio character show` prints it
without touching S3 and why the web app can render it as a form rather than as
a textarea full of YAML.

**These four folders are a starting layout, not a schema.** Rename one, delete
one, add your own — an image is a reference because a row says so, never because
of the folder it sits in.

A character holds **no production history**. Runs, chains, scenes and movies
belong to a project (see the **`studio-media-s3`** skill), because one piece of
work can involve several characters and a project can outlive any of them. A run
records which characters it used, so the association survives the split:
`studio runs find --character <name>`.

### The four pools, and what each is for

| | `reference/` | `corpus/` | `seed/` | `archive/` |
|---|---|---|---|---|
| Answers | *Who is this person, shown how?* | *What else do we have of them?* | *What were they built from?* | *What did we retire?* |
| Holds | generated imagery — face angles, body turnarounds, wardrobe, in-world frames | uploads, keeper clips | the founding photographs | rejects, superseded takes |
| Sent to a model | a **chosen subset** | only by explicit key | rarely, by explicit key | **never**, unless the user names it |
| Indexed | yes — every image described in the bible | no | no | no |
| Numbered | no — `order` is an attribute | basenames kept | basenames kept | basenames kept |

**Nothing is numbered any more, and no filename means anything.** A reference is
a row that carries its own `group`, `order`, description and tags, so an image
may be called whatever it was called when it arrived. Slot N is position N in
the resolved selection, exactly as before — but it is `order` on the row that
decides where an image lands, not a trailing digit in its name.

That is what retired `curate renumber` and `curate regroup`: there are no holes
to close, and moving an image between groups writes one row and no object. Use
`studio character order` to move an entry and `studio character regroup` to
change its group.

The project's `input/` pool is a **separate thing entirely** — working material
for a piece of work, not anything about a character. Frames pulled off a clip
for chaining go there (`studio frames last --add-input`), never into `reference/`:
an extracted frame is model output, and promoting it into identity feeds
generated pixels back in as identity and compounds drift.

### `reference/` is a library, and the bible says which part to send

The engines cap reference images hard — **Kling 7, Seedance 9, Nano Banana 14** —
and they are sent *in full*. `reference/` holds far more than that, so something
has to choose. That something is the bible:

```yaml
references:
  - file: face/<name>_4.jpg          # path relative to reference/
    description: Head and shoulders, front on, looking straight down the lens,
                 grey studio backdrop.
    tags: [face, front, neutral, studio]
default_set:                          # sent when --character is given alone
  - face/<name>_4.jpg
  - body/<name>_8.png
```

**`--character` no longer means "send everything".** It used to, which worked
only while the folder was kept small enough to fit the smallest cap. Now a
selection is either named or comes from `default_set`, and an over-cap selection
is **refused** with the index printed — because which images a generation saw
should not be decided by whatever a folder listing happened to return.

```bash
studio character refs <name> --describe            # what every image shows, and its tags
studio character refs <name> --pick-tag face --keys
studio character refs <name> --pick face/<name>_4.jpg,body/<name>_8.png --presign
studio character default-set <name> --set face/<name>_4.jpg --set body/<name>_8.png
```

The same selectors exist on the runner: `--pick`, `--pick-tag`, and `--slots`
(positions **within the resolved selection** — slot N is the Nth image actually
sent, which is what `[ImageN]` refers to).

**Describe every image you add.** An undescribed image cannot be picked by tag
and is invisible to whoever chooses the set — so it may as well not be there.

```bash
studio character add-refs <name> /tmp/new/*.png --to face    # NAME first, then files
studio character set-ref-desc <name> <node> \
  "Three-quarter right, looking off camera." --tags face,three-quarter
studio character describe-refs <name> --from-json batch.json   # a whole pass, atomically
studio character order <name> <node> --after <node>            # move it in the group
studio character selection <name> --tag face --limit 7         # what a model would see
```

**`sync-refs` is gone and cannot come back.** It reconciled the bible's index
against what was actually in the folder, which was a job only because the two
were separate things that could disagree. A reference *is* a row about a node:
there is no folder listing to drift from.

### Curating the pools

`studio curate` does the operations that go wrong by hand — every command is a DRY
RUN unless you pass `--apply`, and nothing is ever deleted outright:

```bash
studio curate groups <name>                         # what reference/ holds, by group
studio curate dedupe <name> --pool reference        # remove byte-identical copies
studio curate move   <name> <file> --from reference --to archive
```

**Moving an image no longer moves anything else, and that is the change worth
knowing.** Run records, scene manifests and chains stored S3 keys, so moving an
object invalidated every document that cited it — which is what once left 69
records pointing at reference images that no longer existed, and why a `rewrite`
command existed to find them. Every record names a **node id** now. A rename or
a move is a row write; nothing that cited the image stops resolving, so there is
nothing to reconcile and no `rewrite` command to run.

`set-refs` is gone. It physically rebuilt `reference/` because the folder *was*
the set being sent; `default_set` is now, so choosing is a description change,
not a file move.

## The bible is structured YAML — one schema, every character

The bible is a field on the character's record (edit it via this skill). One schema,
and **every character carries the same top-level keys**, so a prompt or a check
reads a path
(`consistency.must`, `identity.signature_features`) instead of pattern-matching
headings out of prose:

| Key | Holds |
|---|---|
| `schema_version` `name` `display_name` | the record's identity |
| `identity` | the card — age, build, height read, `signature_features[]`, home turf, register, speech |
| `face` | structure, skin, eyes, eyebrows, nose, mouth/jaw, facial hair, hair, ears |
| `body` | silhouette, arms, chest/shoulders, neck, lower body/hands, body hair, posture |
| `wardrobe` | `always_dressed`, `tops[]` by frequency, lower body, footwear, `accessories[]`, palette |
| `voice` | language, accent, `accent_cues[]`, manner, delivery |
| `rendering` | `default_style` + `optional_styles[]` (presets from `studio-media-prompt`), framing, backgrounds |
| `references` | every image in `reference/`, as `{file, description, tags[]}` — the index that makes a large library choosable |
| `default_set` | the reference files sent when `--character` is given with no selector; keep it under the smallest cap in play (Kling 7) |
| `consistency` | `must[]` · `never[]` · `drift_modes[{failure, fix}]` |
| `text_identity_block` | the authored ~50-70 word compression (see below) |

Two rules the schema exists to hold:

- **Describe WHO the character is, never how the record was made.** No "built
  from N references", no "the source images span X years", no era-of-the-archive
  notes. Provenance is not identity, it does not help a model render anything,
  and it rots the moment the reference set is re-curated. A fact worth keeping
  out of that reasoning belongs in the key it describes — "no grey in the hair"
  goes in `consistency.never`, not in a paragraph explaining which images it
  came from.
- **Identity is style-agnostic.** Rendering is a per-render choice, which is why
  it lives in its own `rendering:` key rather than inside the face and body prose.

`consistency` earns its shape: `must` and `never` are the checklist to verify a
render against, and each `drift_modes` entry pairs the **failure** with the
**fix** — what to actually write in the prompt — so naming a drift and correcting
it are never separated.

`studio character` **refuses to upload** a bible that does not parse or has lost a
top-level key: a character with no `consistency` block is a character that
silently stops being checked against. For a **worked example**, read a live one
(`studio character show <name>`) before writing a new one.

## The management tool

`studio character` is the CRUD + load layer. It goes through the same storage
layer as everything else in **`studio-media-s3`** — one API session, one natural
sort — so there is one auth path and no bytes in the
agent context. Requires `studio login` (see the `studio-media-s3` skill).

```bash
studio character list                                  # every character
studio character show <name>                           # the record: bible, refs, folders
studio character create <name> --from-profile /tmp/<name>.yaml   # new character record
studio character set-profile <name> /tmp/<name>.yaml     # replace the bible
studio character edit <name>                           # pull the bible to edit locally; re-run to upload
studio character add-refs <name> /tmp/*.png --to face  # add refs into a purpose group
studio character refs <name> --describe                # what every image shows
studio character refs <name> --presign --json          # generation-time: ordered signed URLs
studio character refs <name> --pick-tag body --keys    # a named selection, as keys
studio character pool <name> corpus                    # material, not identity
studio character add-to <name> seed photo.jpg          # founding source photos
studio character rename <old> <new>                    # a new slug, records and all
```

### Renaming a character

A slug is a path segment, so a new one is not an edit — it is a move of every
object in the record, plus a rewrite of everything that named the old one. Doing
those separately is how a record ends up half-renamed:

```bash
studio character rename <old> <new>            # DRY RUN: the whole plan
studio character rename <old> <new> --apply
studio character rename <old> <new> --display-name "Some Name" --apply
```

**One conditional write, and nothing moves.** The slug is an attribute on the
character's row, not a path segment, so a rename swaps the slug claim, updates
the record and renames the character's root folder — four operations in one
transaction. No object is copied, no record is rewritten, and every reference,
run and binding still resolves, because all of them name node ids.

That is the whole of what this used to be. It moved objects whose basenames
carried the slug, rewrote the bible's paths, and patched every run, scene,
movie and project record that cited one of those keys — and a `--dry-run` was
worth having because the plan was large enough to want reading first.

Two things it deliberately leaves alone. A **project** that happens to share the
character's name is not renamed, and neither is a slug written into prose — a
prompt that names the character still says the old one — text is text, and
nothing rewrites prose.

It refuses a destination that already exists rather than merging into it.

### Editing a bible by hand (`edit`)

`edit` round-trips the bible as YAML so you can change it in a real editor. The first
run **pulls** it to `local/characters/<name>.yaml` (git-ignored) and prints the
path; once that working copy exists, the next run **pushes** it back — so the
loop is *run, edit, run again*. It prints a diff before uploading.

```bash
studio character edit <name>            # 1st run: download   2nd run: upload
studio character edit <name> --diff     # what have I changed vs S3?
studio character edit <name> --discard  # bin my local edits, re-pull
```

It keeps two hidden sidecars next to the working copy — `.<name>.base.yaml` (the
pristine pull, for the diff) and `.<name>.etag` (the version recorded at pull
time). That second one makes the push safe: if the bible changed after you
pulled, the upload is **refused** rather than silently clobbering the change.
`--force` overrides, `--pull` / `--push` pin the direction, `--path` moves the
working copy.

**It is `rev`, and it is compare-and-swap rather than check-then-write.** The
guard was the S3 ETag, then the record's `updated_at` — both read first and
written second, with a gap in which someone else's write lands and is lost. The
bible is a field on a row now, so the push sends the `rev` it was pulled at and
the API refuses the write itself. There is no gap. A stale push fails with the
two revisions named, and re-pulling is the whole recovery.

The same guard covers the index commands (`add-refs`, `describe-refs`,
`set-ref-desc`, `default-set`), because a bible is edited by a
person and by those commands at once.

`add-refs --to <group>` numbers new images `<name>_<group>_<n>` continuing after
that group's current highest index; `--replace` renumbers from 1, `--start N`
sets an explicit start. The number is **not** the `[ImageN]` slot — slot N is
position N in the resolved selection, which is what a model actually receives.

## Generating a character video (the full flow)

1. **Load the bible.** `studio character show <name>` — read it (esp. `consistency`
   and `identity.signature_features`). Don't generate from memory.
2. **Choose the reference subset.** Read what is available, then pick — the
   library is bigger than any cap:
   ```bash
   studio character refs <name> --describe
   studio character refs <name> --pick-tag face --presign --json > refs.json
   # -> [{ "node": "node-…", "name": "<file>.jpg", "url": "https://..." }, ...]
   ```
   Pass the `.url` values as `reference_images` (Seedance accepts up to 9) and
   cite them as `[Image1]…[ImageN]` — **slot N is position N in this list**.
   `reference_images` **cannot** be combined with a first-frame `image` on
   Seedance. Normally the runner does all of this: `studio run --project <p>
   --character <name> --pick-tag face`.
3. **Author the prompt.** Translate the bible into concrete visual/audio
   direction — ideally with **`studio-media-prompt`** (structured JSON): the character's
   look in `subject`, the scene action in `action`, and cite `[Image1]…` inside
   `subject`. Put any spoken line in **double quotes** so Seedance generates the
   audio in-character.
4. **Render + save** via an engine skill — **`studio-media-image`** for a still,
   **`studio-media-seedance`** or **`studio-media-kling`** for video. Ask which **project**
   first; each records the run and archives the artifact into
   the run's own `output/` folder automatically.
   Consider rendering a **still first** and animating it: a start frame carries
   identity *and* composition, which `reference_images` alone cannot on Seedance.
5. **Verify against `consistency`** — every `must` present, every `never` absent;
   regenerate if any hard cue is off, using the matching `drift_modes[].fix`.

## Carrying a character to an engine with no reference system

Both Seedance and Kling-on-Replicate hold identity through `reference_images`,
so prefer that. When driving from a **start frame** instead — or on any surface
without a reference set — the character has to survive as prose. Compress the
bible into a pasteable block:

```bash
studio character textblock <name>
```

If the bible has an authored `text_identity_block` it is printed verbatim;
otherwise the identity-bearing keys (`identity`, `face`, `body`, `wardrobe`,
`consistency`) are printed as raw material to compress into ~50-70 words. Write
the result back into `text_identity_block:` (`studio character edit <name>`) so it is authored
once and reused.

**With a start frame, keep the pasted block short.** The frame carries appearance
better than prose can, and a long identity paragraph fights it — see
`studio-media-kling`.

## Adding a new character

1. Write the bible. `studio character create <name>` with no `--from-profile`
   starts one from the blank template; read a live one
   (`studio character show <name>`) as a worked example. Fill **every** key —
   `create` refuses a bible missing any of them.
2. `studio character create <name> --from-profile <your-bible.yaml>`.
3. `studio character add-to <source photos…> <name> seed` — the founding images.
4. **`studio character turnaround <name> --project <project>`** — the standard face and
   body set, described and indexed in one pass. See below.
5. `studio character add-refs <stills…> <name> --to wardrobe` for anything the
   standard set does not cover, then **describe them**: `describe-refs
   --from-json` for a batch, `set-ref-desc` for one.

## THE TWO HUMAN GATES

**A character's `reference/` is the one thing here you cannot fix later.** Runs
are append-only history, descriptions can be rewritten, a project can be renamed
— but what sits in `reference/` is *who the character is*, and every later render
is held against it. So two separate decisions belong to the person, and neither
may be inferred:

1. **Spending.** Show the complete payload as the two documents — `PROMPT` then
   `INPUT` — and wait for a yes to **that payload**. Not to a plan, not to a
   menu option, not to "shall I shoot?". A payload approved earlier in the
   conversation is not an approval of the one about to be sent; re-show it.
2. **Identity.** A generated image does **not** become a reference
   because it rendered successfully. Show it, and wait for a yes before it is
   added, replaced, renumbered or archived. This includes `reference/`,
   `default_set`, and anything in the bible's `references:` index.

Both of these have been broken in practice, in the same session:

- a shoot was submitted on the strength of a multiple-choice answer rather than
  a shown payload, using a `--yes` flag that no longer exists;
- its result was then written straight into a character's face group, which
  nobody had agreed to.

The tools now enforce what they can. `shoot` has no approval flag and asks
interactively, and it **never files its own output** — results stay in their run
until someone promotes them with `add-refs --from-run`. What the tools cannot
enforce is an agent deciding a previous message counted as approval. It does not.
When in doubt, render the payload into the conversation and stop.

## The standard set (`shoot`)

A reference library is chosen from **by tag**, so an angle nobody shot is an angle
nobody can pick. `shoot` renders the fourteen every character should have —
eight `face` and six `body`. Face is a full turn: front, three-quarter and
profile to each side, both three-quarter-backs, and back. Body is the same turn
**without the two front three-quarters**, whose angle image is refused as
sensitive content by every model that has tried it. Face angles are cropped at
mid-chest; body angles are the whole figure, head to feet.

**Direction is always the edge of frame the face points toward**, never the
subject's own left or right. `three_quarter_left` means the nose points at the
left edge. This is not pedantry: the wording it replaced said "turned to THEIR
LEFT so the viewer sees the LEFT side of the face", which instructs two opposite
rotations at once, and both three-quarters duly came back facing the same way.

Each is one recorded run built from three things: a **angle image** (a generic,
anonymous, untextured figure that says only how to stand), the character's **seed
photographs** (who it is), and a prompt filled from the character's own bible —
its usual top, and every cue in `consistency.must`.

```bash
studio character turnaround <name> --project <project> --dry-run   # fourteen payloads, no spend
studio character turnaround <name> --project <project>             # shows them, then asks
studio character turnaround <name> --project <project> --group face
studio character turnaround <name> --project <project> --angle body_back   # re-shoot one
```

- **Nothing bills without approval.** Every payload is shown in full and the
  batch then needs an explicit yes. There is no flag that answers it.
- **Nothing enters the character.** Results stay in their runs; the shoot prints
  the `add-refs --from-run` line for each. Look before promoting:
  `studio runs outputs <project>/latest --presign`.
- **`--project` is required**, as it is for any generating command.
- **Identity comes from `seed/`** when it has any, because driving a shoot off
  already-generated references feeds model output back in as identity and
  compounds drift. `--identity refs` / `--pick` / `--pick-tag` override that.
- **The medium comes from the character**, not from the spec — an angle renders in
  whatever `rendering.default_style` says, and is told to match the medium of
  the reference images it is given. A character drawn in ink is not turned into a
  photograph.
- **`--model` overrides the engine** for every angle; the spec's defaults are
  chosen so any registered image model accepts them. A dry run preflights the
  override, so a model that would refuse it costs nothing to find out.
- **`--review-sheet DIR` shows the images each payload sends**, captioned
  `[ImageN]` in the order the model receives them. A key is a name; a name is not
  a look, and the mistakes that matter here are visual.
- The angle images live in the repo under `studio/config/` and are copied to the
  bucket by `studio/scripts/dev-setup.sh`. If a shoot says one is missing, re-run
  that script.

Promoting a keeper, once a person has seen it and said so:

```bash
studio runs outputs <project>/latest --presign          # look at it first
studio character add-refs <name> --to face --from-run <project>/latest#1
studio character set-ref-desc face/<file> <name> --description "…" --tags face,front
studio character default-set <name> --set …             # under the Kling cap of 7
```

`studio character create <name> --from-profile <bible> --turnaround --project <p>`
creates and shoots in one command, through the same two gates.

No new skill directory — ever. The character is now usable by the whole pipeline.
Names are lowercase `[a-z0-9_-]`. There is no reserved-name list: characters live
under `characters/`, so a project named `misc` simply is not one.

### When an angle image comes back wrong, read the bible before rewriting the prompt

A turnaround fills its prompts from the bible, so an angle image that is confidently and
repeatably wrong is usually the record being followed correctly. Rewording the
prompt against it just argues with the source. In one session the same character
came back short and stocky, then narrow-chinned, then long-haired at the nape —
and each time the bible said exactly that: a height he did not have, a chin the
photographs contradicted, hair described as running long at the back. The prompt
machinery was faultless throughout.

So when a result is off, ask which field produced it and check that field against
the seed photographs. Fixing the record fixes every future generation; fixing the
prompt fixes one.

Four failure shapes worth knowing, because none is obvious from reading the text:

- **A field can be missing rather than wrong.** The chin was described twice
  under `face:` and never appeared in `consistency.must`, which is the list the
  prompt foregrounds — present in the record, absent from the payload.
- **Amount and colour are separate claims.** "Only a little chest hair" was read
  as *faint* as well as *sparse*, so it came back nearly invisible while the
  densely-described legs came out dark. Say how much and how dark independently.
- **Width words say nothing about depth.** "Full square chest, rounded capped
  deltoids" describes a front view. The profiles rendered flat as a board until
  the bible said the chest stands forward of the ribcage — front-on language
  cannot be checked from the side.
- **State the numbers you have.** `identity.height_read` is usually the only
  proportion given as a figure, and a figure on a plain backdrop has no scale of
  its own. Adjectives lose to an angle image; a stated height does not.

### Making a matched pair without a second render

Opposite angles — the two three-quarters, the two profiles — are meant to be the
same person turned. Two renders of one prompt will differ in build, scale and
hair however tight the wording, because they are two rolls of a die.

**Mirror one instead.** A horizontal flip of the right three-quarter *is* the
left three-quarter, and being literally the same pixels it matches on every axis
a second render could drift on. Record the provenance in the description and tag
it `mirrored`, so nobody later reads it as independent evidence of the face. It
costs nothing, and it is what `config/angle/` already does for its own angle images.

## A bible describes identity, not a fixed look

A character record is medium-agnostic on purpose:

- **Rendering style is a per-video choice.** The bible captures WHO the character
  is (face, build, wardrobe, voice); the look (realistic vs. a stylized/illustrated
  treatment) is set per video in the prompt's `style` field. Default to realistic
  unless a style is requested, and give any signature stylized look as an optional
  §5 preset rather than baking it into identity.
- **Wardrobe wording belongs to the ENGINE, not to identity.** Each engine has a
  per-model wording list (`studio phrasebook`) giving preferred phrasing;
  it is data, and it changes. Keep it in the engine skill, never in a bible.


## Seeing what is in a pool, as opposed to what is in the index

**A pool is a folder tree; the reference index is rows. They disagree, and only
one command shows the difference.**

```bash
studio character pool <name> reference --group face      # what is IN the folder
studio character pool <name> reference --unreferenced    # …that no REF# row names
studio character refs <name>                             # what the INDEX holds
studio character pool <name> seed --group current        # any pool, any subfolder
```

`reference` used to be refused here on the grounds that pools are material and
references are identity — true of the rows, and not of the folder they sit in. A
file can sit in `reference/body/` with no row naming it, and with `refs` reading
the index and `pool` refusing the pool, nothing could see it. Twelve such files
sat unnoticed in one library. `--unreferenced` is the question that finds them,
and it compares **node ids** rather than filenames.

Those files are inert where they are — never selected, never counted against the
engine caps, never in the default set — so archiving them is legibility rather
than a fix.

## Reorganising, and the one command that destroys

```bash
studio curate move <name> current/<file> --from seed --to seed --to-group earlier
studio curate move <name> <file> --from seed --to archive --to-group crops
studio curate drop <name> <node> --pool archive --apply
```

**`--to-group` puts the file in a subfolder of the destination pool.** Without
it the destination was always a pool root, so `--from seed --to seed` — the
shape of every "it is in the wrong subfolder" fix — moved the file *out* of its
subfolder and in beside the originals. A pool could be organised and never
reorganised.

**`curate drop` is the only command here that deletes on request**, and it is
deliberately awkward: every file named explicitly, dry run by default, no
globbing. It exists because there was previously no way to remove a mistaken
upload at all — a file could be moved between pools forever and never
destroyed, so `archive/` slowly became where things went to not be deleted.

**It refuses a reference rather than detaching one.** `dedupe` detaches in the
same act because it is removing a duplicate of something the character still
has; dropping removes the thing itself, and whether a character still IS what
that image shows is hard rule #2b's question. `studio character detach` first.
