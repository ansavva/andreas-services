---
name: studio-media-core
description: The shared machinery every studio-* engine runs on — the model REGISTRY (models.json), the one submit lifecycle, live schema validation, and the shared runner that invokes any registered model. Use when invoking a model generically, inspecting what a model accepts, refreshing schema snapshots, or working on the studio-* plumbing itself. For guidance on a SPECIFIC model, use that model's own skill; to add a new one, use studio-media-add-model.
---

# studio-media-core — the runner every model shares

**Models are data, not code.** One entry per model in the **registry**, one
runner over all of them. Adding a model is a reviewed data change plus a written
page — never an edit to five scripts, which is what it used to be.
`studio models` is the whole surface onto it.

This skill is the plumbing. For how to *use* a given model, read its own skill:

| Model | Skill |
|---|---|
| `nano-banana-pro` | [`studio-media-nano-banana-pro`](../studio-media-nano-banana-pro/SKILL.md) |
| `nano-banana-2` | [`studio-media-nano-banana-2`](../studio-media-nano-banana-2/SKILL.md) |
| `gpt-image-2` | [`studio-media-gpt-image-2`](../studio-media-gpt-image-2/SKILL.md) |
| `gpt-image-1.5` | [`studio-media-gpt-image-1-5`](../studio-media-gpt-image-1-5/SKILL.md) |
| `seedance` | [`studio-media-seedance`](../studio-media-seedance/SKILL.md) |
| `kling` | [`studio-media-kling`](../studio-media-kling/SKILL.md) |

The rest of the family — a model skill points here, and here points onward, so
the shared prose lives in one place rather than six:

| Skill | For |
|---|---|
| [`studio-media-image`](../studio-media-image/SKILL.md) | The frame-first workflow: why render a still before a video, run chaining, the approval gate |
| [`studio-media-shot`](../studio-media-shot/SKILL.md) | Orchestrating a whole shot — brief → plan → still → clip |
| [`studio-media-prompt`](../studio-media-prompt/SKILL.md) | Authoring video prompts as structured JSON |
| [`studio-media-character`](../studio-media-character/SKILL.md) | Character identity: the bible and the two image pools |
| [`studio-media-add-model`](../studio-media-add-model/SKILL.md) | Adding a model to the registry |
| [`studio-media-s3`](../studio-media-s3/SKILL.md) | The asset store and the run store |

## The runner

```bash
studio models                    # every registered model
studio models show gpt-image-2   # entry + LIVE input schema + caveats
studio models refresh            # re-snapshot schema enums into models.json
                                 # (the backend's copy — it reaches prod on deploy)

studio run --model <key> --project <project> --prompt "..." --character <name> \
  --name <file> --dry-run
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

## Where this lives

The registry is data — one JSON document that every studio-* tool reads, and the
only thing you edit to add a model. `studio models show <key>` prints an entry
alongside the live schema; `studio-media-add-model` is how a new one gets written.

**It is the deployed service's document, and the CLI reads it from there.** It
used to ship inside the pipeline, and the app kept a three-engine copy of the
reference caps that disagreed with it — so a selection the CLI refused, the app
allowed. One copy now, served to both. Two things follow: reading the registry
needs a session like every other command, and a model added here reaches
production when the backend deploys. Against a local dev API it is live at once.

The code behind these commands is mapped in
[docs/PIPELINE.md](../../../docs/PIPELINE.md#the-modules). The run store is
storage rather than invocation, so it belongs to
[`studio-media-s3`](../studio-media-s3/SKILL.md).

## `snapshot` — why there are two copies of the enums

Each entry carries a `snapshot` of its schema's enums and ranges. It exists so
**`studio-media-prompt` can validate a prompt offline**, without a network call. It is
advisory only: everything that submits re-validates against the live schema, so
a stale snapshot can cost a retry but can never let a bad payload bill. Refresh
with `studio models refresh`.

## Schema vs docs

Both are wrong sometimes, in opposite directions:

- `gpt-image-2`'s **schema** offers `background: "transparent"`; its README says
  that is unsupported. → the schema is too permissive; record it in `denied`.
- The same **README** lists three aspect ratios where the schema has eighteen.
  → the docs are stale; the schema is right.

**Trust the schema for what a field accepts, the docs for what the model
actually honours.** `studio-media-add-model` reads both for exactly this reason.

## Invariants this machinery defends

- **The store is the only origin.** Nothing is ever uploaded to Replicate.
  Assets reach it only as presigned URLs minted at submit time, and signed URLs
  are never stored — run records hold **paths**, and the run store refuses a
  URL-shaped binding. A path looks key-shaped because of how the tree was laid
  out; that coincidence ends at the first rename, so read it as a path (see
  [`studio-media-s3`](../studio-media-s3/SKILL.md)).
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


## Two guards on `studio run`

**`--again` — the same payload is not submitted twice by accident.** Model,
inputs and bound images are fingerprinted, and a repeat within the same project
is refused with the earlier run named. It exists because a batch driven by a
shell script was started twice when the harness reported it finished and it had
not: ~46 images were generated twice and the results overwrote each other, so
nothing looked wrong afterwards. Passing `--again` submits anyway — re-rolling a
generative model with the same prompt is a normal thing to want, and the point
is that it is a decision somebody makes rather than something a script does in
silence.

**It is a query against the run store, not a local file.** It used to be a
per-machine list beside the credentials, which caught the same machine
submitting twice — what actually happened — and nothing else. The fingerprint is
recorded on the run now, so a second machine and a colleague are caught too. An
unsubmitted draft never counts: repeating a `--dry-run` is ordinary.

**An `owner/name` that is not a registry key runs off the live schema.** Trying
a model before onboarding it had no supported path, so a four-way upscaler
comparison ran three of them straight against the provider — no validation, no
approval render, no run records.

```bash
studio run --model vendor/some-upscaler --project <p> --start-key <node> --no-refs --dry-run
```

The entry is inferred in memory by the same code `studio add-model` proposes
from, and **nothing is written to the registry** — onboarding stays a deliberate
act with a skill page attached. Inferred fields are guesses, `accepts_ext`
especially, so the run warns. A registry key never contains a slash, so a
misspelt one still fails here rather than reaching a provider.
