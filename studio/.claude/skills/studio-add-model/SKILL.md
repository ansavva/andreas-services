---
name: studio-add-model
description: Add a new Replicate model to the studio-* harness — fetch its live input schema and README, propose a registry entry for review, write it to models.json, and scaffold the model's own skill. Use whenever a new or different Replicate model should become invokable (a newer image model, another video engine, a model someone linked), or when an existing entry needs re-checking against a changed schema. Covers what to verify by hand and why the schema alone is not enough.
---

# studio-add-model — onboarding a Replicate model

Models are **data**. Adding one is an entry in
[`engine/models.json`](../../../pipeline/src/studio_pipeline/engine/models.json) plus a
skill doc — no submitter to write, no five files to edit. Once registered, a
model is immediately invokable by `studio run --model <key>`, importable by
the backfill, and convertible for by `s3_convert --for <key>`.

## The command

```bash

studio add-model openai/gpt-image-2            # propose only — writes NOTHING
studio add-model openai/gpt-image-2 --write    # append to the registry + scaffold the skill
```

It prints two documents, matching the house review format:

```
===== 1/2  PROPOSED REGISTRY ENTRY — review before writing =====
{ …the entry… }

===== 2/2  WHAT WAS INFERRED vs GUESSED =====
  - kind=image — inferred from the presence of no video-ish fields
  - max_refs=null — no documented cap found for `input_images`; VERIFY
  - README CAVEAT: GPT Image 2 doesn't support transparent backgrounds.
      <-- names schema value(s) ['transparent']; STRONG `denied` candidate
```

**Read document 2 before writing.** It separates what was read off the schema
from what was guessed, and it is the only part that needs a human.

## Why it reads the README as well as the schema

Each catches what the other misses. Both of these are real:

| | Schema says | Docs say | Who is right |
|---|---|---|---|
| `gpt-image-2` `background` | `transparent` is valid | "doesn't support transparent backgrounds" | **Docs** — schema is too permissive |
| `gpt-image-2` `aspect_ratio` | 18 values incl. pixel sizes | lists 3 | **Schema** — the README is stale |

So: **the schema is authoritative for what a field accepts, the docs for what
the model actually honours.** A value the schema allows but the model ignores
would validate and then quietly do nothing — which is why the script greps the
README for limiting sentences and flags any that name a live schema value as a
`denied` candidate.

## The procedure

1. **Propose.** `studio add-model <owner>/<name>` — nothing is written.
2. **Check what was guessed.** Especially:
   - `images.refs` — must be the *array* field. A scalar `image` is a first
     frame, not a reference set (this is how Seedance names it).
   - `images.max_refs` — the cap. Usually stated in the field description; if
     the note says VERIFY, read the model page.
   - `images.accepts_ext` — Kling rejects `.webp`; most others take it.
   - `images.start_excludes_refs` — **Seedance forbids a start frame together
     with references; Kling allows both.** Nothing in the schema says so.
   - For video, the whole `video` block is a template — set `max_cuts`,
     `technical`, and `resolution_map` by hand.
3. **Add `denied`** for anything the README says is unsupported but the schema
   still offers.
4. **Write.** `--write` appends the entry and scaffolds
   `studio-<name>/SKILL.md`.
5. **Fill in the skill's TODOs** — what the model is good at, how it differs
   from its siblings, which inputs matter in practice.
6. **Verify** before spending anything real:
   ```bash
   studio models show <key>
   studio run --model <key> \
     --project <project> --prompt "test" --no-refs --dry-run
   ```

## Keeping an entry honest

Schemas change under you. Re-snapshot after any model update:

```bash
studio models refresh [<key>]
```

Only `snapshot` is rewritten — the curated fields (`denied`, caps, notes)
survive untouched. Submission always re-validates live, so a stale snapshot
costs at most a retry.

## Retiring a model

Delete its entry from `models.json` and its `studio-<name>/` directory. Past
runs are unaffected: `runs/` is append-only history and records the Replicate
model id, so an unregistered model still reads back as its raw id.
