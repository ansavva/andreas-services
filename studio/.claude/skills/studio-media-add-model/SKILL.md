---
name: studio-media-add-model
description: Add a new Replicate model to the studio-* harness — fetch its live input schema and README, propose a registry entry for review, write it to the registry, then write the model's own skill page. Use whenever a new or different Replicate model should become invokable (a newer image model, another video engine, a model someone linked), or when an existing entry needs re-checking against a changed schema. Covers what to verify by hand, what belongs on a model page, and why the schema alone is not enough.
---

# studio-media-add-model — onboarding a Replicate model

Models are **data**. Adding one is an entry in the model registry plus a skill
page — no submitter to write, no five files to edit. Once registered, a model is
immediately invokable by `studio run --model <key>` and convertible for by
`studio convert --for <key>`.

Onboarding is two jobs with a clean seam. The command does the part that is
mechanical — fetch, infer, propose, write the registry. **You write the page**,
because the part worth reading is judgement about the model, and that comes from
the README and from comparing it against its siblings.

## The command

```bash
studio add-model openai/gpt-image-2            # propose only — writes NOTHING
studio add-model openai/gpt-image-2 --write    # append to the registry
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
4. **Write.** `--write` appends the entry to the registry. It writes nothing
   else. **The registry is the deployed service's file**, so the entry is a repo
   change reviewed in the PR and it reaches production when the backend deploys.
   A local dev API serves it immediately, which is where step 6 verifies.
5. **Write the skill page** — see below. Nothing generates it for you.
6. **Verify** before spending anything real:
   ```bash
   studio models show <key>
   studio run --model <key> \
     --project <project> --prompt "test" --no-refs --dry-run
   ```

## Writing the model's skill page

Create `studio-media-<key>/SKILL.md`, where `<key>` is the registry key with
dots replaced by dashes. The `studio-media-` prefix is not optional — it is the
family for using the pipeline, it is what `add-model` records in the registry's
`skill` field, and a directory outside either family fails the skills linter. **Read two or three existing model skills first** —
`studio-media-kling`, `studio-media-gpt-image-2` and `studio-media-nano-banana-pro` are the fullest
— and match their shape. They are the specification; this list is the checklist.

A model page carries only what is **specific to this model**. The runner,
hard rule #2, the run store and S3-only origin are `studio-media-core`'s to
explain, and repeating them here is how they drift.

| Section | What goes in it |
|---|---|
| Frontmatter | `name`, and a `description` that says which medium it generates and when to reach for this model over its siblings — that sentence is what selects the skill |
| One-line placement | What it is for, and the one thing it does better than the others |
| Invoke | A real `studio run --model <key>` line with the flags this model actually needs |
| Inputs that matter | The two or three fields worth setting, with values that work — not a schema dump; `studio models show <key>` prints the live schema |
| `denied` values | Anything the schema offers and the model ignores, and what happens if you pass it |
| Formats and caps | Reference-image cap, accepted extensions, prompt ceiling — and the conversion needed to hand it a still from another engine |
| Failure modes | How output goes wrong on *this* model and what to change in the prompt |

Two things not to write: **no character names anywhere** (hard rule 1 — use
`<name>`), and **no module paths, file names or function names**. A skill
describes the CLI surface; implementation belongs in
[docs/PIPELINE.md](../../../docs/PIPELINE.md), and the **skills linter** fails
the build if a media skill names one. That linter is not part of the pipeline
test suite and deliberately does not live under `tests/` — checking markdown is
not what that suite is for. Pre-commit runs it locally and the PR workflow
enforces it; `studio-code-pipeline` says where it is.

Everything in the table is in what `add-model` already printed, plus the model's
README. If a section would be a `TODO`, the page is not finished — an unfinished
model page is worse than none, because it reads as documentation.

> **Why this is not generated.** It was, until August 2026: a format string in
> the onboarding command emitted this page as boilerplate wrapped around a
> `TODO` comment asking for exactly the judgement above. The boilerplate rotted
> unread
> and began stamping a long-dead path into every new model's docs, while the
> only valuable part was never filled in by the thing that had already fetched
> the README. Prose is authored, not formatted.

## Keeping an entry honest

Schemas change under you. Re-snapshot after any model update:

```bash
studio models refresh [<key>]
```

Only `snapshot` is rewritten — the curated fields (`denied`, caps, notes)
survive untouched. Submission always re-validates live, so a stale snapshot
costs at most a retry.

## Retiring a model

Remove its entry from the registry and delete its `studio-media-<key>/` skill
directory. `studio models` lists what is registered and `studio models show
<key>` prints the entry, so you can see what is going. Past runs are unaffected:
`runs/` is append-only history and records the Replicate model id, so an
unregistered model still reads back as its raw id.
