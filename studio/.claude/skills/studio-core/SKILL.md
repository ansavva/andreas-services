---
name: studio-core
description: The shared machinery every studio-* engine runs on — the model REGISTRY (models.json), the one submit lifecycle, live schema validation, and the studio.py runner that invokes any registered model. Use when invoking a model generically, inspecting what a model accepts, refreshing schema snapshots, or working on the studio-* plumbing itself. For guidance on a SPECIFIC model, use that model's own skill; to add a new one, use studio-add-model.
---

# studio-core — the runner every model shares

**Models are data, not code.** One entry per model in
[`scripts/models.json`](scripts/models.json), one runner over all of them. Adding
a model is a reviewed data change plus a generated doc — never an edit to five
scripts, which is what it used to be.

This skill is the plumbing. For how to *use* a given model, read its own skill:

| Model | Skill |
|---|---|
| `nano-banana-pro` | [`studio-nano-banana-pro`](../studio-nano-banana-pro/SKILL.md) |
| `nano-banana-2` | [`studio-nano-banana-2`](../studio-nano-banana-2/SKILL.md) |
| `gpt-image-2` | [`studio-gpt-image-2`](../studio-gpt-image-2/SKILL.md) |
| `gpt-image-1.5` | [`studio-gpt-image-1-5`](../studio-gpt-image-1-5/SKILL.md) |
| `seedance` | [`studio-seedance`](../studio-seedance/SKILL.md) |
| `kling` | [`studio-kling`](../studio-kling/SKILL.md) |

The rest of the family — a model skill points here, and here points onward, so
the shared prose lives in one place rather than six:

| Skill | For |
|---|---|
| [`studio-image`](../studio-image/SKILL.md) | The frame-first workflow: why render a still before a video, run chaining, the approval gate |
| [`studio-shot`](../studio-shot/SKILL.md) | Orchestrating a whole shot — brief → plan → still → clip |
| [`studio-prompt`](../studio-prompt/SKILL.md) | Authoring video prompts as structured JSON |
| [`studio-character`](../studio-character/SKILL.md) | Character identity: the bible and the two image pools |
| [`studio-add-model`](../studio-add-model/SKILL.md) | Adding a model to the registry |
| [`s3`](../s3/SKILL.md) | The asset store and the run store |

## The runner

```bash
STUDIO=.claude/skills/studio-core/scripts/studio.py

uv run $STUDIO models                    # every registered model
uv run $STUDIO models show gpt-image-2   # entry + LIVE input schema + caveats
uv run $STUDIO models refresh            # re-snapshot schema enums into models.json

uv run $STUDIO run --model <key> --project <project> --prompt "..." --character <name> \
  --slug <slug> --dry-run
```

`--model` takes any registry key, image or video; the entry decides which image
fields exist and what the caps are. There is deliberately **no default model** —
the engines are peers, chosen per shot.

**`--project` is required and never inferred.** A run belongs to a project, and
where output lands is the one thing rerunning a command cannot undo — so it is
asked for, not guessed. Omitting it errors with the list of existing projects.
Establish the project *before* showing a payload for approval: approving a
payload should never imply approving where it lands.

Image inputs: `--character <name>` (repeatable — one piece of work can involve
several) · `--pick` / `--pick-tag` / `--slots` to choose from that character's
reference index · `--ref-run` · `--image-run` · `--input N` (the **project's**
working pool) · `--key`. Video first/last frame: `--start-run` / `--start-key` /
`--end-run` / `--end-key`, which error clearly when aimed at a model that has no
such field.

**`--character` does not mean "send everything".** It used to, which worked only
while a character's `reference/` was kept under the smallest engine cap. It is a
library now, so `--character` alone sends that character's `default_set`, and an
over-cap selection is **refused** with the index printed rather than truncated —
which images a generation saw should not be decided by a folder listing. Slot N
is position N in the resolved selection.

## What runs before anything bills

`--dry-run` renders the payload for approval and submits nothing. The same
checks run on a dry run as on a real submit, so **an approved payload is a
payload that submits**:

1. **`denied`** — documented constraints the schema does *not* enforce. The
   generated schema is sometimes more permissive than the model (`gpt-image-2`
   publishes `background: "transparent"`, which its docs say is unsupported).
2. **Cross-field rules** — Kling's multi-shot durations must sum to `duration`
   (E006); prompt length caps.
3. **The live schema** — unknown fields, enum membership, numeric range. When a
   field is aimed at the wrong model, the error names the model that takes it.

```
error: openai/gpt-image-2 does not accept: ['input_fidelity']
  `input_fidelity` is accepted by: gpt-image-1.5
```

## The files

| File | Purpose |
|---|---|
| `models.json` | **The registry.** Single source of truth for every studio-* tool. |
| `registry.py` | Load / look up / list; `save_snapshot` for refreshes. |
| `studio.py` | The CLI above. |
| `submit.py` | The one submit lifecycle, image and video alike. |
| `model_schema.py` | Live schema fetch; validates fields, enums, ranges, `denied`. |
| `replicate_api.py` | Token, HTTP, download, poll. |
| `refs.py` | Character reference selection / project input pool → S3 keys. |

The run store itself stays in the `s3` skill
([`s3/scripts/runs.py`](../s3/scripts/runs.py)) — that is storage, this is
invocation.

## `snapshot` — why there are two copies of the enums

Each entry carries a `snapshot` of its schema's enums and ranges. It exists so
**`studio-prompt` can validate a prompt offline**, without a network call. It is
advisory only: everything that submits re-validates against the live schema, so
a stale snapshot can cost a retry but can never let a bad payload bill. Refresh
with `studio.py models refresh`.

## Schema vs docs

Both are wrong sometimes, in opposite directions:

- `gpt-image-2`'s **schema** offers `background: "transparent"`; its README says
  that is unsupported. → the schema is too permissive; record it in `denied`.
- The same **README** lists three aspect ratios where the schema has eighteen.
  → the docs are stale; the schema is right.

**Trust the schema for what a field accepts, the docs for what the model
actually honours.** `studio-add-model` reads both for exactly this reason.

## Invariants this machinery defends

- **S3 is the only origin.** Nothing is ever uploaded to Replicate. Assets reach
  it only as presigned URLs minted at submit time, and signed URLs are never
  stored — run records hold S3 keys, and `runs.py` refuses a URL-shaped binding.
- **The request is recorded before submitting**, so a failed render
  is still history.
- **Never `Prefer: wait`.** A timed-out wait retries internally and can create
  duplicate *billed* predictions. Create, then poll.
- **Identity and working material stay distinct** — a character's `reference/`
  is identity, chosen from a described index and capped by the model; a
  project's `input/` is uncapped working material, picked from by number. A
  frame pulled off a run goes to the project pool, never into a character.
- **A run records where it lives and who is in it** — `project` and
  `characters[]`, the latter inferred from the bindings rather than trusted from
  the flags, so it cannot disagree with the images actually sent.
