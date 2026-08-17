---
name: studio-character
description: Manage on-model characters — create, update, list, curate, and load a character whose profile bible and reference library live in the xharness-prod-media-us-east-1 S3 bucket. Use whenever a request names a known/recurring character, or the user wants to add, edit, describe, curate, or inspect one. A character is DATA (an S3 record under characters/<name>/), not a per-character skill: this one skill manages them all, and its described reference index is how a SUBSET of a large reference library is chosen for a generation instead of sending the folder whole.
---

# studio-character

Characters are **data, not skills.** Instead of a skill per character, every
character is an S3 record managed by this one skill, used by the video pipeline
(`studio-prompt` to author the prompt, an engine skill to render). Part of the
**`studio-*`** family:

- **`studio-character`** (this skill) — owns character identity: the bible + refs.
- **`studio-prompt`** — authors the prompt as structured JSON, per engine.
- **`studio-seedance`** — renders via Seedance 2.0 on Replicate, saves to S3.
- **`studio-kling`** — renders via Kling 3.0 / O3 Omni on Replicate.

> **MANDATORY for any character video: never generate from a bare text prompt.**
> How identity is carried depends on the engine — on **Seedance**, pass the
> reference set in `reference_images`; on **Kling via Replicate** the same field
> exists (up to 7 images), so the set carries over — note Kling takes only
> `.jpg/.jpeg/.png`, so a `.webp` set needs converting. Driving from a start
> frame instead, paste a compressed identity block (`character.py textblock
> <name>`). Either way identity comes from the images + bible, motion/framing
> from the prompt.

## Where a character lives (S3)

Each character is a record under `characters/<name>/` in the
**`xharness-prod-media-us-east-1`** bucket (the generic **`s3`** skill is the
storage layer; auth is your `aws login`).

```
characters/<name>/profile.yaml   the bible — SOURCE OF TRUTH, one schema,
                                 including the DESCRIBED reference index
characters/<name>/reference/     generated character imagery, in purpose
                                 subfolders: face/ body/ wardrobe/ scene/ …
characters/<name>/corpus/        collected material about the character —
                                 uploads, keeper clips. Material, not identity.
characters/<name>/seed/          the founding real-world source photos
characters/<name>/archive/       retired material
```

A character record holds **no production history**. Runs, chains, scenes and
movies live under `projects/<project>/` (see the **`s3`** skill), because one
piece of work can involve several characters and a project can outlive any of
them. A run records which characters it used, so the association survives the
split: `runs.py find --character <name>`.

### The four pools, and what each is for

| | `reference/` | `corpus/` | `seed/` | `archive/` |
|---|---|---|---|---|
| Answers | *Who is this person, shown how?* | *What else do we have of them?* | *What were they built from?* | *What did we retire?* |
| Holds | generated imagery — face angles, body turnarounds, wardrobe, scene stills | uploads, keeper clips | the founding photographs | rejects, superseded takes |
| Sent to a model | a **chosen subset** | only by explicit key | rarely, by explicit key | **never**, unless the user names it |
| Indexed | yes — every image described in the bible | no | no | no |
| Numbered | `<name>_<group>_<n>.<ext>` within a group | basenames kept | basenames kept | basenames kept |

Only `reference/` is numbered, because only `reference/` is cited by slot.
Renaming a source photo throws away whatever its filename recorded.

The project's `input/` pool is a **separate thing entirely** — working material
for a piece of work, not anything about a character. Frames pulled off a clip
for chaining go there (`frames.py last --add-input`), never into `reference/`:
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
CH=.claude/skills/studio-character/scripts/character.py

uv run $CH refs <name> --describe            # what every image shows, and its tags
uv run $CH refs <name> --pick-tag face --keys
uv run $CH refs <name> --pick face/<name>_4.jpg,body/<name>_8.png --presign
uv run $CH default-set <name> --set face/<name>_4.jpg body/<name>_8.png
```

The same selectors exist on the runner: `--pick`, `--pick-tag`, and `--slots`
(positions **within the resolved selection** — slot N is the Nth image actually
sent, which is what `[ImageN]` refers to).

**Describe every image you add.** An undescribed image cannot be picked by tag
and is invisible to whoever chooses the set — so it may as well not be there.

```bash
uv run $CH add-refs <name> --to face /tmp/new/*.png   # numbered within face/
uv run $CH set-ref-desc <name> face/<name>_5.png \
  --description "Three-quarter right, looking off camera." --tags face,three-quarter
uv run $CH describe-refs <name> --from-json batch.json   # a whole pass, atomically
uv run $CH sync-refs <name> --apply                      # reconcile index vs folder
```

### Curating the pools

`curate.py` does the operations that go wrong by hand — every command is a DRY
RUN unless you pass `--apply`, and nothing is ever deleted outright:

```bash
CUR=.claude/skills/studio-character/scripts/curate.py

uv run $CUR groups   <name>                       # what reference/ holds, by group
uv run $CUR regroup  <name> face <name>_3.jpg     # move into a purpose subfolder
uv run $CUR dedupe   <name> --pool reference      # remove byte-identical copies
uv run $CUR renumber <name> --group face          # close holes -> contiguous 1..N
uv run $CUR move     <name> face/<name>_3.jpg --from reference --to archive
```

**Moving an image moves its records too.** Run records, scene manifests and
chains all store S3 keys, so moving an object invalidates every document that
cited it — `regroup` and `move` rewrite those documents in the same operation.
This is not hypothetical: curating without that step is what left 69 records
pointing at reference images that no longer existed. `rewrite.py check` reports
any that remain.

`set-refs` is gone. It physically rebuilt `reference/` because the folder *was*
the set being sent; `default_set` is now, so choosing is a description change,
not a file move.

## The bible is structured YAML — one schema, every character

`profile.yaml` is canonical in S3 (edit it via this skill). The schema is
[`templates/profile.yaml`](templates/profile.yaml) and **every character carries
the same top-level keys**, so a prompt or a check reads a path
(`consistency.must`, `identity.signature_features`) instead of pattern-matching
headings out of prose:

| Key | Holds |
|---|---|
| `schema_version` `name` `display_name` | the record's identity |
| `fictional` | invented character, or a real person's likeness — a consent question, answered before anything renders |
| `identity` | the card — age, build, height read, `signature_features[]`, home turf, register, speech |
| `face` | structure, skin, eyes, eyebrows, nose, mouth/jaw, facial hair, hair, ears |
| `body` | silhouette, arms, chest/shoulders, neck, lower body/hands, body hair, posture |
| `wardrobe` | `always_dressed`, `tops[]` by frequency, lower body, footwear, `accessories[]`, palette |
| `voice` | language, accent, `accent_cues[]`, manner, delivery |
| `rendering` | `default_style` + `optional_styles[]` (presets from `studio-prompt`), framing, backgrounds |
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

`character.py` **refuses to upload** a bible that does not parse or has lost a
top-level key: a character with no `consistency` block is a character that
silently stops being checked against. For a **worked example**, read a live one
(`uv run $CH show <name>`) before writing a new one.

## The management tool

[`scripts/character.py`](scripts/character.py) is the CRUD + load layer. It reuses
the **`s3`** skill's `s3_common.py` (the AWS-login-bridged boto3 client, the
key builders, natural sort) — one storage layer, one auth path, no bytes
in the agent context. Requires an `aws login` (see the `s3` skill).

```bash
CH=.claude/skills/studio-character/scripts/character.py

uv run $CH list                                  # every character
uv run $CH show <name>                           # print a character's profile.yaml (from S3)
uv run $CH create <name> --from-profile /tmp/<name>.md   # new character record
uv run $CH set-profile <name> /tmp/<name>.md     # replace the bible
uv run $CH edit <name>                           # pull the bible to edit locally; re-run to upload
uv run $CH add-refs <name> --to face /tmp/*.png  # add refs into a purpose group
uv run $CH refs <name> --describe                # what every image shows
uv run $CH refs <name> --presign --json          # generation-time: ordered signed URLs
uv run $CH refs <name> --pick-tag body --keys    # a named selection, as keys
uv run $CH pool <name> corpus                    # material, not identity
uv run $CH add-to <name> seed photo.jpg          # founding source photos
```

### Editing a bible by hand (`edit`)

`edit` round-trips `profile.yaml` so you can change it in a real editor. The first
run **pulls** it to `local/characters/<name>.md` (git-ignored) and prints the
path; once that working copy exists, the next run **pushes** it back — so the
loop is *run, edit, run again*. It prints a diff before uploading.

```bash
uv run $CH edit <name>            # 1st run: download   2nd run: upload
uv run $CH edit <name> --diff     # what have I changed vs S3?
uv run $CH edit <name> --discard  # bin my local edits, re-pull
```

It keeps two hidden sidecars next to the working copy — `.<name>.base.md` (the
pristine pull, for the diff) and `.<name>.etag` (the S3 ETag at pull time). The
ETag is what makes the push safe: if `profile.yaml` changed in S3 after you pulled,
the upload is **refused** rather than silently clobbering that change. `--force`
overrides, `--pull` / `--push` pin the direction, `--path` moves the working copy.

`add-refs --to <group>` numbers new images `<name>_<group>_<n>` continuing after
that group's current highest index; `--replace` renumbers from 1, `--start N`
sets an explicit start. The number is **not** the `[ImageN]` slot — slot N is
position N in the resolved selection, which is what a model actually receives.

## Generating a character video (the full flow)

1. **Load the bible.** `uv run $CH show <name>` — read it (esp. `consistency`
   and `identity.signature_features`). Don't generate from memory.
2. **Choose the reference subset.** Read what is available, then pick — the
   library is bigger than any cap:
   ```bash
   uv run $CH refs <name> --describe
   uv run $CH refs <name> --pick-tag face --presign --json > refs.json
   # -> [{ "key": "characters/<name>/reference/face/<name>_4.jpg", "url": "https://..." }, ...]
   ```
   Pass the `.url` values as `reference_images` (Seedance accepts up to 9) and
   cite them as `[Image1]…[ImageN]` — **slot N is position N in this list**.
   `reference_images` **cannot** be combined with a first-frame `image` on
   Seedance. Normally the runner does all of this: `studio.py run --project <p>
   --character <name> --pick-tag face`.
3. **Author the prompt.** Translate the bible into concrete visual/audio
   direction — ideally with **`studio-prompt`** (structured JSON): the character's
   look in `subject`, the scene action in `action`, and cite `[Image1]…` inside
   `subject`. Put any spoken line in **double quotes** so Seedance generates the
   audio in-character.
4. **Render + save** via an engine skill — **`studio-image`** for a still,
   **`studio-seedance`** or **`studio-kling`** for video. Ask which **project**
   first; each records the run and archives the artifact into
   `projects/<project>/runs/<run_id>/output/` automatically.
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
uv run $CH textblock <name>
```

If the bible has an authored `text_identity_block` it is printed verbatim;
otherwise the identity-bearing keys (`identity`, `face`, `body`, `wardrobe`,
`consistency`) are printed as raw material to compress into ~50-70 words. Write
the result back into `text_identity_block:` (`$CH edit <name>`) so it is authored
once and reused.

**With a start frame, keep the pasted block short.** The frame carries appearance
better than prose can, and a long identity paragraph fights it — see
`studio-kling`.

## Adding a new character

1. Write the bible from [`templates/profile.yaml`](templates/profile.yaml) (read
   an existing character's live bible, `uv run $CH show <name>`, as a reference).
   Fill **every** key — `create` refuses a bible missing any of them.
2. `uv run $CH create <name> --from-profile <your-bible.yaml>`.
3. `uv run $CH add-to <name> seed <source photos…>` — the founding images.
4. `uv run $CH add-refs <name> --to face <generated angles…>` (and `--to body`,
   `--to wardrobe`), then **describe them**: `describe-refs --from-json` for a
   batch, `set-ref-desc` for one.
5. `uv run $CH default-set <name> --set …` — the handful sent when nobody picks.
   Keep it under the smallest cap in play (Kling 7).

No new skill directory — ever. The character is now usable by the whole pipeline.
Names are lowercase `[a-z0-9_-]`. There is no reserved-name list: characters live
under `characters/`, so a project named `misc` simply is not one.

## A bible describes identity, not a fixed look

A character record is medium-agnostic on purpose:

- **Rendering style is a per-video choice.** The bible captures WHO the character
  is (face, build, wardrobe, voice); the look (realistic vs. a stylized/illustrated
  treatment) is set per video in the prompt's `style` field. Default to realistic
  unless a style is requested, and give any signature stylized look as an optional
  §5 preset rather than baking it into identity.
- **Wardrobe wording belongs to the ENGINE, not to identity.** Each engine has a
  per-model wording list (`s3/scripts/phrasebook.py`) giving preferred phrasing;
  it is data, and it changes. Keep it in the engine skill, never in a bible.
- **A bible built from photographs of a real person is a real person's likeness.**
  Generated video of an identifiable person is a consent question before it is a
  technical one — settle it before anything is published.
