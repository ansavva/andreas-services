# studio — the run plan

> **STATUS: BUILT, except for the backfill against production.** Every phase has
> landed; `studio --profile prod catalog backfill-plans --apply` has not been
> run, so prod's 254 runs still carry no plan. `catalog verify` reports that as
> coverage rather than as a failure — see [The backfill](#the-backfill).

It extends [ENTITY_MODEL.md](ENTITY_MODEL.md) rather than replacing anything in
it. A run was already a row; this gives it the half a scene has and it did not —
a **plan**, authored before the submission, approved as an artifact rather than
as an answer in a terminal, and readable in the app.

**An earlier draft of this file said past runs could not be backfilled. That was
wrong on the facts** and the whole of it is replaced. The reasoning confused two
different things: the *service* may not decode `request.json`, because the
pipeline changes its shape freely; a *maintenance command in the pipeline* is
where that shape is owned. Measured against production, the reconstruction is
total.

---

## Vocabulary, because three words overlap

```
movie ⊃ scene ⊃ shot ⊃ panel
                 │       └── run   ← an image run.  cents.
                 └────────── run   ← a video run.   dollars.
```

- **run** — one submission to a model. A machine event. No name; addressed by id
  or `latest`. **The only tier where anything bills.**
- **shot** — a position in a scene's plan: `SCENE#<id>/SHOT#<shot_id>`. It exists
  before anything is rendered. It *binds* a run; it is not one.
- **panel** — a still inside a shot, in the shot row's `panels` list, with a role
  of `start` / `end` / `reference` / `sample`. Panels are why a storyboard is
  cheap: stills cost cents, so a flow is judged before a 15s shot is bought.
- **storyboard** — a scene's whole plan: `setting`, `defaults`, `logline` and its
  ordered `SHOT#` rows. Not an entity; there is no `BOARD#`.

**Storyboarding has no approval step, and never had one.** `scenes board` runs
the same `click.confirm` everything else does, and no scene, shot or panel
carries an approved state. A storyboard is an *economic* preview; hard rule #2's
confirm is an *approval* gate. This added the approval record, at the run tier only
— scenes inherit it, because `scenes board` and `scenes render` produce runs.

---

## What was missing

A run carried an envelope — status, model, timings, bindings, outputs, cost — and
no authored half at all. What a person intended went into `request.json`, the
**provider's** document, which this service is forbidden to read. Three
consequences:

1. **A run could be shown as outcome, never as intent.** `RunPage` drew the
   envelope, the outputs and the payload documents as text. Not what the run was
   *for*, because nothing recorded it.
2. **A binding could not explain itself.** `engine/submit.py::gather` decides
   which image lands in which field and in which position — an edit target first,
   then curated identity, then chained run outputs, then the working pool — and
   then discarded that reasoning. `bindings` was the residue: field name to node
   ids. **Position in that list is cited by the prompt** (a real production
   prompt reads "the FIRST image is an existing angle image of him"), so the ordering
   was load-bearing and its meaning was nowhere.
3. **Approval left no artifact.** Hard rule #2 says show the full payload, get an
   explicit yes, and re-approve after **any** edit. It was enforced by a
   `click.confirm`. Nothing could show that a run was approved, check that the
   payload still matched, or approve anything outside a terminal.

**The ordering that blocked all three was deliberate**, and this overturned it.
`engine/board.py` said: *a LABEL, not an id: the run does not exist yet and must
not, because hard rule #2 approves the payload before anything is recorded.* The
answer is that `record_request` already ran *before* `create_prediction`, so a
record has never meant "this billed" — moving it one step earlier makes the
approval a thing that can be recorded, re-checked and revoked. **The run row
stopped meaning "a submission happened" and started meaning "a submission was
intended",** which is what `draft` and `discarded` are for.

---

## The data model

### Today — a scene has two halves, a run had one

```
            A SCENE                                    A RUN  (before)
  ┌──────────────────────────────┐          ┌──────────────────────────────┐
  │ SCENE#<id> / META            │          │ RUN#<id> / META              │
  │  AUTHORED ─────────────────  │          │  AUTHORED ─────────────────  │
  │    title, logline            │          │                              │
  │    setting, defaults         │          │       ·· nothing ··          │
  │  RECORDED ─────────────────  │          │  RECORDED ─────────────────  │
  │    status, output, error     │          │    status, kind, model       │
  │                              │          │    engine, prediction_id     │
  │                              │          │    outputs, cost, error      │
  │                              │          │    bindings {field:[node]}   │
  └──────────────┬───────────────┘          └──────────────┬───────────────┘
                 │ SHOT#<id> × n                           │
                 ▼                                         ▼
  ┌──────────────────────────────┐          ┌──────────────────────────────┐
  │  AUTHORED                    │          │                              │
  │    order, beat, prompt       │          │       ·· no children ··      │
  │    panels[], motion          │          │                              │
  │  RECORDED                    │          │                              │
  │    run, node, shot_node      │          │                              │
  └──────────────────────────────┘          └──────────────────────────────┘
```

### Now — the run has the same two halves

```
  ┌────────────────────────────────────────────────────────────────┐
  │ RUN#<id> / META                                                │
  │                                                                │
  │  AUTHORED ── plan ───────────────────────────────────────────  │
  │    prompt      "…"  or  { … }        the structured document   │
  │    params      { aspect_ratio, quality, duration, extra… }     │
  │    origin      "authored" | "backfilled"                       │
  │    note        (nullable)                                      │
  │                                                                │
  │    plan_digest  sha256( plan ⊕ sends )   recomputed on write    │
  │                                                                │
  │  APPROVAL ───────────────────────────────────────────────────  │
  │    approval    { by, at, digest }  |  null                     │
  │                                                                │
  │  RECORDED ───────────────────────────────────────────────────  │
  │    status, kind, model, engine, prediction_id, counted         │
  │    submitted, completed, outputs, cost, error, lineage         │
  │    payload  { request, response, prompt }   ← blob ids, opaque │
  └───────────────────────────┬────────────────────────────────────┘
                              │  RUN#<id> / SEND#0001 … SEND#000n
                              ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  field    "input_images"      which model input it binds to    │
  │  role     "reference"         start | end | reference | input  │
  │  node     node-…              what was sent                    │
  │  source   { kind: "character",         WHY it was sent —       │
  │             character: char-…,         DERIVED, not reported   │
  │             group: "face" }                                    │
  └────────────────────────────────────────────────────────────────┘
```

`SEND#` is an **ordered child**, not an edge, for the reason the entity model
gives: it exists in a plan before anything is submitted, its identity is its
position, and the node it names is a field. The sort key is a zero-padded number
because **the order is cited by the prompt** — `SEND#10` would otherwise sort
before `SEND#2`, which is the same `-10`-before-`-2` failure the run outputs had
when their order came from a filename.

**`plan` is studio's and `payload.request` is the provider's.** That line is the
one a scene already holds: a shot's `motion.prompt` is authored and queryable
while the run it renders into keeps the provider payload as an undecoded blob.
Principle 4 is applied one tier down, not weakened. The plan carries no image
fields at all — those are sends, presigned in at the last moment.

**`bindings` is derived** from the send rows and keeps its old response shape, so
nothing that drew a run had to change. A run with no send rows falls back to the
stored attribute; that fallback retires itself once the backfill has run.

### `source` is derived, and that is what makes it one answer

`catalog.source_of` computes provenance from where a node sits:

```
    {"kind": "character",  "character": …, "group": "face", "order": 3000}
    {"kind": "run",        "run": …,       "output": 2}
    {"kind": "input-pool", "project": …,   "position": 4}
    {"kind": "object"}
```

The pipeline knows perfectly well why it picked an image — `gather` just chose it
— but the pipeline is not the only thing that creates runs, and a run
reconstructed from history has no `gather` behind it at all. Deriving it in the
API means a run submitted today and a run backfilled from August describe their
images in the same words, computed by the same code.

### Where `role` comes from — a symmetry that already existed

```
   STORYBOARD (built)                              RUN (this)

   panel.role                                      send.role
     start    ─┐    resolve_roles(shot)     ┌──►     start
     end       ├──► then submit.gather()    ├──►     end
     reference │    {field: [node, …]}      ├──►     reference
     sample   ─┘         ▲                  └──►     input
                         │
                    the role is USED here
                    and then DISCARDED
```

`sample` has no send: it binds to nothing, so it can never be something the model
was handed.

### The state machine, and the one gate

```
                          any plan or sends edit
              ┌───────────────────────────────────────┐
              │                                       │
              ▼                                       │
        ┌─────────┐   approve    ┌──────────┐         │    ┌─────────┐
        │  draft  │─────────────►│ approved │─────────┴───►│ pending │
        └────┬────┘  409 if the  └────┬─────┘   API 409s   └────┬────┘
             │       digest is        │         unless          │
             │       stale        revoke        the digest      ▼
             │                        │         still matches   ┌─────────┐
             │                        └──► draft                │ running │
             │ discard                                          └────┬────┘
             ▼                                                       │
       ┌───────────┐                            ┌────────────────────┴──────┐
       │ discarded │                            ▼          ▼                ▼
       └───────────┘                       succeeded    failed        cancelled
```

**The gate is on LEAVING the unsubmitted states, not on reaching `pending`, and
the difference is the whole of it.** `engine/submit.py` writes `running` when it
does not poll and `succeeded` when it does; it never passes through `pending` at
all. A check naming one status would have been enforced by the test suite and
bypassed by the only caller in existence — which is worse than no gate, because
it reads as working.

`adopted` is the one way out that the gate does not stand in front of: it wraps
an artifact that already existed, calls no provider and bills nothing. It was
also **missing from `RUN_STATUSES` entirely**, so `studio runs adopt` would have
been a 400 against this service; the pipeline's fake never validated a status, so
nothing caught it.

Two consequences of a row no longer asserting that anything happened:

- **`draft` and `discarded` are hidden from listings by default.** `?status=draft`
  or `?include=drafts` asks for them.
- **A draft is not counted** in the project's run count. The count is bumped by
  the transition out of the unsubmitted states, once, guarded by `counted`. The
  reverse — decrementing on the deletion of a draft that was never counted —
  would have taken the count permanently negative, and `delete_project`'s refusal
  reads counts, so a project holding nothing but drafts would have deleted them
  without a word. It asks for draft rows separately.

### What the digest is for

`plan_digest` hashes **everything a person approves**: the plan, and the ordered
sends as `(field, role, node)`. `source` is excluded — provenance is for a
reader, and re-deriving it more accurately later must not void an approval
nobody's payload changed.

It is recomputed by the API on every write that can change either, and never
accepted from a client. Approving sends the digest the client believes it is
approving; the API compares and answers **409** on a mismatch. That is
compare-and-swap, and it is the mechanical form of "re-approve after **any**
edit" — a rule that was remembered rather than checked, and that was broken in a
real session, which is why hard rule 2b exists.

**It is not a permission boundary and this file will not pretend it is.** The CLI
and the SPA hold ID tokens from the same Cognito pool, so an agent can approve a
run it wrote. What it cannot do is approve one payload and send another.

---

## API

Additive. Every existing route kept its shape.

| Route | |
|---|---|
| `POST /api/runs` | **Creates `draft`.** Body takes `plan` and `sends`; `bindings` is still accepted and read as sends with the role left null |
| `PATCH /api/runs/<id>/plan` | `{plan}` — a draft's authored fields. **Clears the approval and returns it to `draft`.** Refused once submitted |
| `PATCH /api/runs/<id>/sends` | `{sends}` — replace the ordered images. Same clearing rule. Every node is existence- and library-checked, and hard rule #3's URL refusal applies |
| `POST /api/runs/<id>/approve` | `{digest}` → **409 `stale_digest`** if it no longer matches, carrying the current one |
| `DELETE /api/runs/<id>/approve` | Revokes; back to `draft` |
| `PATCH /api/runs/<id>` | Leaving the unsubmitted states is **409 `not_approved`** unless approved with a current digest |
| `GET /api/runs/<id>` | Gains `plan`, `plan_digest`, `approval`, `stale` and `sends` (expanded, with role and source) |
| `GET /api/runs` | Gains `?include=drafts`; drafts and discards hidden otherwise |

A plan is validated as a map and no further: which knobs a model has is registry
data, the registry is the pipeline's, and a copy of it here would be a second
answer to what a model accepts.

---

## CLI

`studio run` is unchanged from the outside — invoking it without `--dry-run` *is*
the request to submit, so it drafts, approves and submits in one act. What
changed is that the yes leaves a row naming the payload it was for.

```
studio run … --dry-run                      # → a DRAFT, and prints its id
studio runs list <project> --status draft   # what is waiting
studio runs edit run-<uuid>                 # $EDITOR over the payload; withdraws the yes
studio runs approve run-<uuid>              # re-renders the payload, asks, approves
studio runs submit run-<uuid>               # refuses an unapproved or stale run
studio runs discard run-<uuid>              # a draft that will not be submitted
```

- **`--dry-run` persists a draft.** It rendered a payload to a terminal and kept
  nothing, so the thing hard rule #2 asks a person to read had no address. A
  draft costs a row and no bytes, is hidden from every listing, and is what
  `runs approve` acts on.
- **`--relayed`, and this bullet used to say there would never be one.** It said
  an approval flag is the door an agent walks through while believing some
  earlier exchange counted as approval, and that it would produce a
  *signed-looking* artifact. The second half was right, and was an argument
  against the *absence*: `yes | studio runs approve …` clears a `click.confirm`
  in one pipe, so the missing flag prevented nothing and made every relayed
  approval **identical to a click** — same `by`, same `at`, no trace of how the
  yes travelled. The rule wrote the artifact it was trying to prevent.

  So `via` is recorded: `interactive` for a yes given at the control — the app's
  button or a terminal confirm — and `relayed` for one an agent passed on with
  `--relayed`. `relayed` is the weaker claim, the app states it in words on the
  run page, and `runs approve --relayed` still prints the entire payload,
  because the gate was never the keystroke.

  What no flag can enforce is that a person really said yes. That was equally
  true of the confirm — a `y` proves a keypress, not a reading — which is why
  the option is named after the claim it makes rather than the prompt it skips.
- **`runs edit` is what a typo used to cost a re-draft.** The routes below have
  existed since a run gained a plan and nothing called them: a wrong word in a
  prompt meant discarding the draft and building it again, images and all. It
  opens `{prompt, params, note, sends}` in `$EDITOR` and patches only the half
  that moved — so a reword leaves the send rows alone and a reorder leaves the
  plan alone. `--dump` and `--file -` are the same thing without a terminal
  editor, which is how an agent edits one.
  - **A send is `field`, `role` and `node`, and the names are printed above the
    editor rather than carried in the document.** The order is the payload — a
    prompt citing "the first image" cites this list — and a caption inside a
    document that cannot be written to would read as though it could.
  - It refuses a submitted run for the same reason `PATCH /plan` does. A plan
    edited afterwards would sit beside `request.json` describing something that
    was never sent.
- **`runs discard` deletes the folder by default**, the opposite of `runs delete`.
  A submitted run's folder holds media somebody paid for; a draft's holds two
  payload documents and an empty `output/`.
- `scenes board` and `character turnaround` needed no change: their single confirm
  still gates the batch, and each submission now leaves an approval behind it.

---

## The web app

`RunPage` gained a **Plan** section above Outputs, built from the storyboard's own
components — `Frame`, `SendRow` and `Slot` from `components/scene/Sends.tsx` — on
the grounds that a shot and a run are the same object at two tiers and drawing
them differently is what would need justifying.

- **The sends draw as a filmstrip**, numbered in bind order, each captioned with
  where it came from: `character · face`, `earlier run · #2`, `input 4`.
- **The approve bar states the digest in words**, never as a hash: nobody has
  approved this / this exact payload is cleared / the payload changed after it
  was approved. It sits **below** the plan, because its own sentence says "reads
  the payload above" and because the control that leads to spending should not be
  the first thing on the screen.
- **`Bindings` now appears only for a run with no sends.** Plan → Images says
  everything it said and more, so drawing both put the same pictures on screen
  twice, the second time with less information.
- `RunsTable` offers `draft` in its filter. A hidden draft is the one thing a
  person has to be able to find — an invisible queue is one nobody works through.

**A draft can be edited in the app too — `RunPlanEditor`, behind an `Edit the
plan` button that appears only on an unsubmitted run.** It was the last thing the
plan made possible and the last thing built: the routes shipped with the plan and
the app could read a payload it could not change, so every correction went back
through a terminal.

- **A mode, not an always-editable form.** This page is read far more often than
  it is written, and the plan is the thing an approval names — a prompt sitting
  in a text box invites a keystroke into the document somebody is about to say
  yes to. The approve bar is hidden while the editor is open for the same reason:
  an approve button beside unsaved words is a yes to whichever of the two you
  were not looking at.
- **Two writes, and only the half that moved.** Each `PATCH` replaces its half
  whole, and each clears the approval — so sending both every time would withdraw
  a yes over an edit that touched one of them.
- **The images edit as a list, not as the filmstrip that draws them.** What is
  being edited is a sequence: a row per image, with the position, up and down,
  remove, and the model input it binds to. `MediaPicker` — the file-shaped twin
  of `DestinationPicker` — adds one by browsing the library, numbering each tile
  as it is picked because the order is what is being built.
- **A structured prompt stays JSON and a written one stays prose**, decided once
  from the run as it arrived rather than from what is in the box. `origin`
  survives a save: a reconstructed plan that quietly became an authored one would
  claim somebody wrote words that were read off a request document.
- **The field a new image binds is offered from what the run already binds**, as
  a suggestion rather than a menu. There is no registry in this app and there
  must not become one — `models.json` is the pipeline's — and a wrong field is
  refused at submit by the live schema check.

---

## The backfill

**Every past run reconstructs, and nothing is guessed.** Measured against
`studio-prod-catalog`:

| | |
|---|---|
| runs | **254** |
| with `request.json` | **254 / 254** |
| with `bindings` as node ids | **254 / 254** |
| distinct models, all in `models.json` | 3 |
| `backfill-plans` dry run: reconstructable | **254**, unreconstructable **0** |

```
  WHAT EXISTS                                       WHAT IS WRITTEN
  ───────────────────────────────                   ─────────────────────────────

  payload.request ──► request.json
      { "model": …,
        "input": {
           "prompt":        "…"      ─────────────► plan.prompt
           "aspect_ratio":  "…"  ─┐
           "output_format": "…"   ├──────────────► plan.params
           "quality":       "…"  ─┘
        } }                                        plan.origin  = "backfilled"

  bindings { "input_images": [n1 … n6] }
      ├─ field name           ───────────────────► send.field
      ├─ models.json[…].images ──────────────────► send.role
      ├─ position in the list ───────────────────► SEND#0001 … SEND#000n
      └─ each node's own ancestry ───────────────► send.source   (by the API)

  created  ─────────────────────────────────────► approval.at
                                                   approval.by = "backfill"
```

`input` holds the prompt and the params and **no image fields** — they were
presigned in after the record was written, which is why this is lossless. Checked
against a real production document before it was relied on.

**`approval.at` is a real timestamp, not a convenient one.** `record_request` is
called immediately after the terminal confirm returns, so a run's `created` is
within milliseconds of the moment somebody actually said yes. `by` names the
mechanism rather than a person, because nobody approved these in a browser and a
row implying they had would be undetectable later. The run page says so:
*approved before approvals were recorded.*

**Where it runs, and why not through the API.** `studio catalog backfill-plans`
is a maintenance command holding its own AWS clients, like `catalog gc` and
`catalog verify`. `PATCH /api/runs/<id>/plan` refuses a submitted run — a plan
edited after the fact would sit beside `request.json` describing something never
sent — and that refusal is load-bearing. A backfill route able to bypass it would
be a permanent hole cut for a one-shot.

**No journal**, unlike `gc` and `reseat`. Those journal because they *delete*.
This adds attributes and rows, touches no object in S3, and skips any run that
already has a plan, so a second run reports zero. `--apply` exists so a person
reads the report first.

**One gap nothing can close.** Before angle images became catalog nodes they
travelled through `gather` marked `shared:<key>` and were **stripped before the
record was written**. Runs from that era under-report their images, and a
text-only generation is indistinguishable from one. Counted in the report, never
invented.

```bash
studio --profile prod catalog backfill-plans          # dry run, the default
studio --profile prod catalog backfill-plans --apply
studio --profile prod catalog verify --library <lib>  # "runs with no plan" → 0
```

`catalog verify` reports a planless run as **coverage rather than corruption** and
does not fail on it: `reseat` refuses to run without a passing verify, and a
not-yet-run backfill blocking an unrelated destructive command would be the wrong
trade. What it *does* fail on is a plan whose stored digest disagrees with it —
silent until somebody submits, and then reported as "the payload changed", which
would be true of nothing anybody did.

---

## What is left

1. **Run the backfill against production.** Everything else has landed.
2. **Should a send get an edge row?** `RUN#<run>` / `NODE#<node>` would make
   "which runs sent this image" answerable through `by-sk` — useful before
   deleting a reference. The entity model's rule says an ordered child pointing
   at an *entity* gets an edge, and a node is not one. Worth doing anyway.
3. **Retire the stored `bindings` attribute** once every run has sends.
4. **Do drafts expire?** Proposed: no. A draft costs a row and no bytes.
5. **Does a scene learn about drafts?** `scenes render` could draft every shot and
   approve the board in one pass. Same mechanism, one tier up.
