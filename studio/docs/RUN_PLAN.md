# studio — the run plan

> **STATUS: BUILT. The backfill against production was never run, and the tool
> for it is deleted.** Prod's 254 pre-plan runs carry no plan and now never will:
> `catalog backfill-plans` went with the rest of the AWS-direct `maintenance/`
> layer, along with the `catalog verify` that reported the gap. Those runs are
> history — they render, they list, and their payload documents are intact; what
> they lack is the authored half, which was always going to be reconstructed
> rather than real. See [The backfill](#the-backfill) for what it would have
> done and why it is not worth resurrecting.

It extends [ENTITY_MODEL.md](ENTITY_MODEL.md) rather than replacing anything in
it. A run was already a row; this gives it the half a scene has and it did not —
a **plan**, authored before the submission, kept as an artifact rather than
as text that scrolled past in a terminal, and readable in the app.

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

**Nothing has an approve step.** `scenes board` runs a `click.confirm` at the
terminal, and no scene, shot, panel — or run — carries an approved state. A run
did, for a while: an `approval` row bound to a digest of the plan, written by an approve
subcommand or by the app before it submitted, and checked by the API at
submit. **Decision 2026-09-04 removed it everywhere.** The record it kept
was never a stronger claim than the command that submitted; the submit is the
act. A storyboard is an *economic* preview; hard rule #2 is show, ask, submit
when told.

---

## The data model

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
  │    fingerprint  sha256( model ⊕ plan ⊕ sends )   on every write │
  │                                                                │
  │  RECORDED ───────────────────────────────────────────────────  │
  │    status, kind, model, engine, prediction_id, counted         │
  │    submitted, completed, outputs, cost, error                  │
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

### The state machine

```
                any plan or sends edit (stays a draft)
              ┌──────────────┐
              │              │
              ▼              │
        ┌─────────┐          │     submit      ┌─────────┐
        │  draft  │──────────┴────────────────►│ pending │
        └────┬────┘   `studio run`,            └────┬────┘
             │        `studio runs submit`,         │
             │        Send in the app —             ▼
             │        the call IS the decision  ┌─────────┐
             │ discard                          │ running │
             ▼                                  └────┬────┘
       ┌───────────┐                ┌────────────────┴──────────┐
       │ discarded │                ▼          ▼                ▼
       └───────────┘           succeeded    failed        cancelled
```

**There is no `approved` state and no gate between `draft` and `pending`.**
There was one: `approve` moved a draft to `approved` with a digest, an edit
moved it back, and the API 409'd a submit whose digest had moved. Decision
2026-09-04 deleted the lot — the recorded yes was never a stronger claim than
the submit command, and a second gesture over a payload already on screen is
what teaches a person to click through the first. What remains on leaving
`draft` is bookkeeping: the run is **counted** once, and `submitted` is stamped.

`adopted` is the one way out that is not a submission: it wraps an artifact
that already existed, calls no provider and bills nothing. It was once
**missing from `RUN_STATUSES` entirely**, so `studio runs adopt` would have been
a 400 against this service; the pipeline's fake never validated a status, so
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

### What the fingerprint is for

`submission_fingerprint` hashes the model, the plan, and the ordered sends as
`(field, role, node)`. `source` is excluded — provenance is for a reader, and
re-deriving it more accurately later must not make two identical payloads read
as different. It is recomputed by the API on every write that can change any of
the three, never accepted from a client, and it answers one question:
**has this exact payload already gone out here?** — `GET /api/runs?fingerprint=`,
which the run page reads for `DuplicateNotice`.

The hash under it, `plan_digest` in `services/digest.py`, is the same function
that once backed the approval record. It is kept because the fingerprint is
derived from it and a second hash would be a fourth implementation in a
repository already bitten by the third; it is no longer stored on the row.

**Nothing here is a permission boundary and this file will not pretend it is.**
The CLI and the SPA hold ID tokens from the same Cognito pool, so an agent can
submit a run it wrote. Hard rule #2 is what stops that: nothing runs unless a
person tells it to, and the submit command is that telling.

---

## API

Additive. Every existing route kept its shape.

| Route | |
|---|---|
| `POST /api/runs` | **Creates `draft`.** Body takes `plan` and `sends`; `bindings` is still accepted and read as sends with the role left null |
| `PATCH /api/runs/<id>/plan` | `{plan}` — a draft's authored fields. Moves the fingerprint. Refused once submitted |
| `PATCH /api/runs/<id>/sends` | `{sends}` — replace the ordered images. Same rule. Every node is existence- and library-checked, and hard rule #3's URL refusal applies |
| `PATCH /api/runs/<id>` | Leaving the unsubmitted states counts the run and stamps `submitted`; no approval is checked |
| `POST /api/runs/<id>/submit` | **Sends a `draft`.** The route that spends money, and calling it is the decision — see below |
| `POST /api/runs/<id>/reconcile` | Ask the provider what happened and close the run on the answer |
| `GET /api/runs/<id>` | Gains `plan`, `fingerprint` and `sends` (expanded, with role and source) |
| `GET /api/runs` | Gains `?include=drafts`; drafts and discards hidden otherwise |

### Submission is a route, and the run closes itself

**The API does the spending.** A generation is not attached to a terminal (a
15-second Kling shot is minutes of wall clock, and a `Ctrl-C` must not strand a
billing prediction), the SPA can submit what a person is looking at on the page
in front of them, and the output travels provider → S3 without passing through
a developer's connection.

So `POST /api/runs/<id>/submit` does the spending, and **the run is closed by
Replicate calling back** rather than by whatever asked for it:

```
   CLI or SPA                 API                    Replicate
       │                       │                         │
       ├── submit ────────────►│                         │
       │                       ├─ a draft? (409 if sent) │
       │                       ├─ preflight              │   ← still `draft`
       │                       ├─ status = pending       │   ← now it has gone out
       │                       ├─ presign the sends      │
       │                       ├─ create prediction ────►│
       │◄── running, pred id ──┤                         │
       │                       │                         │
       │                       │◄──── callback ──────────┤   (minutes later)
       │                       ├─ verify, download, store
       │                       └─ status = succeeded
```

**The status moves to `pending` before the provider is called**, exactly as it
did in the CLI, which is what makes a submission that dies in flight legible as
"went out and never answered" rather than as a draft nobody sent.

**Preflight runs before `pending`**, which is the one ordering that changed
meaning. A payload the model will refuse leaves the run a `draft`, editable and
submittable again; only a payload that has actually gone out reaches a state
that implies money.

### Receiving a callback and processing one are separate, and that is about dev

The callback lands on a small **receiver** that enqueues it verbatim and answers
in milliseconds. A **consumer** verifies the signature and closes the run: a
worker Lambda in production, and a process beside `dev-up.sh` on a developer's
machine.

**Receive and process are split because Replicate cannot reach
`http://localhost:8000`.** The consumer is an event consumer draining
completions that are pushed to it, not a poller asking the provider for status
on a timer.

If the close ran inline in the API Lambda, local development would fall back
to polling and the code that closes a run in production would be code no
developer had executed. With the split, the deployed half is a dependency-free
zip Lambda that only enqueues, and the half that changes runs from the working
tree. Three things follow:

* the callback is acknowledged before a 200 MB download rather than after it;
* a failed upload is a redrive and then a dead-letter queue, not a paid-for
  file that is simply gone;
* the three functions size independently — the API Lambda stays at 512 MB and 60
  seconds instead of growing to fit the largest video studio can produce.

`infra/modules/callbacks` carries the rest of the argument.

### The output URL expires, and the queue is spending a budget it does not own

**Replicate deletes an output file about an hour after the prediction
completes.** Everything between the callback firing and the bytes being in S3 is
spending that hour, and the dead-letter queue does **not** preserve them — it
preserves the report. Three things follow, and they are the whole of the answer:

* **The retry ladder is set against the hour**, not against a general idea of
  resilience: three attempts at a 360-second visibility timeout is 18 minutes,
  leaving ~40 in which somebody can still act. It was five, which is 30.
* **An expired URL is refreshed once.** A 403 is an aged signature and a 404 is a
  deleted file, and they are the same at the socket, so the consumer asks
  `GET /v1/predictions/<id>` for a fresh URL before believing the worse one.
* **A file that is genuinely gone closes the run `failed` and says so.** It used
  to raise, which put the message back on the queue to be retried against a URL
  that will never work again — five times, then the DLQ, with the run still
  reading `running` and nobody told anything.

That last one is a real loss, stated rather than engineered away. Guaranteeing
the bytes would mean capturing them in the receiver, which costs the property
that made receive and process separate in the first place: the deployed half
would do the download, so a developer's consumer would stop exercising it.
The window is bounded instead — prod's consumer runs seconds after the callback —
and the DLQ is alarmed.

### Hard rule #3 at the moment the payload comes back

A callback echoes `input` to us — image fields and all — so storing the
provider's response verbatim filed the presigned URLs `submit` had minted, in
the run's own folder. Short-lived, and readable only by somebody who could
already read the run, and still exactly what "a signed URL is never stored"
forbids.

**They are put back as node ids rather than removed.** The run's ordered `SEND#`
rows are the same rows the URLs were minted from, in the same order, so the
mapping is by construction rather than by parsing anything out of a URL — and a
reader of `response.json` gets the thing they actually wanted, which is which
image was in which field and in which position. Anything URL-shaped that cannot
be accounted for is replaced with a marker; the one case where guessing wrong
leaves a live URL is the case that fails toward removal.

`output` is untouched. Those URLs are the provider's, grant nothing here, and are
the only record of what the model returned.

### What if the callback never arrives?

`POST /api/runs/<id>/reconcile` asks the provider directly and closes the run
with **the same code the consumer runs**. It is not a poller and nothing
schedules it; it is called by a caller that is waiting, or by a person who
noticed. Two situations reach it and they are the same situation from this side:
a production callback lost to a deploy landing mid-flight, and a machine where
there was never going to be a callback at all.

A plan is validated as a map and no further: which knobs a model has is registry
data, the registry is the pipeline's, and a copy of it here would be a second
answer to what a model accepts.

---

## CLI

`studio run` is unchanged from the outside — invoking it without `--dry-run` *is*
the request to submit, so it drafts and submits in one act. The person who
typed it is the yes.

```
studio run … --dry-run                      # → a DRAFT, and prints its id
studio runs list <project> --status draft   # what is waiting
studio runs edit run-<uuid>                 # $EDITOR over the payload; read it again after
studio runs show run-<uuid>                 # the payload, as stored
studio runs submit run-<uuid>               # sends a draft — this command IS the act
studio runs reconcile run-<uuid>            # for one that went out and never came back
studio runs discard run-<uuid>              # a draft that will not be submitted
```

- **`--dry-run` persists a draft.** It rendered a payload to a terminal and kept
  nothing, so the thing hard rule #2 asks a person to read had no address. A
  draft costs a row and no bytes, is hidden from every listing, and is what
  `runs submit` acts on.
- **There is no approve subcommand under `studio runs`, and there was one.** It re-rendered the
  payload, asked, and wrote an `approval` row the API checked at submit; a
  `--relayed` flag recorded a yes given elsewhere as the weaker claim it was.
  Decision 2026-09-04 deleted both. The record never outranked the command
  that submitted — an agent told "send it" could type `runs submit` exactly as
  easily as the approve with `--relayed` — and a second gesture over a payload
  already read is what teaches a person to wave through the first. What no
  flag can enforce is that a person really said to send it; that is the rule,
  and it is carried by who runs the command rather than by a row.
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
- `scenes board` needed no change: its single terminal confirm still stands in
  front of the batch, and each submission is a run like any other.

---

## The web app

`RunPage` gained a **Plan** section above Outputs, built from the storyboard's own
components — `Frame`, `SendRow` and `Slot` from `components/scene/Sends.tsx` — on
the grounds that a shot and a run are the same object at two tiers and drawing
them differently is what would need justifying.

- **The sends draw as a filmstrip**, numbered in bind order, each captioned with
  where it came from: `character · face`, `earlier run · #2`, `input 4`.
- **Running a draft is ONE armed press — `Run — this spends` — and that press is
  the act.**

  **This bullet has been rewritten twice, and the history is kept.** It first
  described a two-step approve bar — an approve dialog, a Revoke button and a
  separate Submit, with three digest sentences: "nobody has approved this / this
  exact payload is cleared / the payload changed after it was approved". The
  second gesture went next: `RunBar` wrote the approval and submitted in one
  press, so the compare-and-swap still held. Decision 2026-09-04 then removed
  the approval itself, everywhere: `RunBar` calls `POST /submit` and nothing
  before it, and the API records no yes because the submit is the yes.

  The separate approve step was redundant in a UI where the payload is on
  screen: the page renders the plan, the ordered images and the exact payload a
  draft would send. Asking for a yes over that and then asking again under a
  different word is what teaches somebody to click through the first one. The
  bar still sits **below** the plan — the control that spends should not be the
  first thing on the screen.
- **An image output can be promoted into a character from here**, inline: pick a
  character and a group, and the output is **copied** into
  `reference/` and the copy gets the `default` tag. That is what promoting has
  always been, performed step for step, and hard rule #2b is
  satisfied by the press — a person choosing the character and the group is the
  separate decision the rule asks for. The run keeps its own output; the two are
  independent blobs from then on.
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
  it is written, and the plan is the thing a person is about to send — a prompt
  sitting in a text box invites a keystroke into the document somebody is about
  to say yes to. The run bar is hidden while the editor is open for the same
  reason: an armed spend button beside unsaved words is a yes to whichever of
  the two you were not looking at.
- **Two writes, and only the half that moved.** Each `PATCH` replaces its half
  whole, so sending both every time would rewrite the send rows of a run whose
  prompt was the only thing touched.
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

## What is left

1. **Run the backfill against production.** Everything else has landed.
2. **Should a send get an edge row?** `RUN#<run>` / `NODE#<node>` would make
   "which runs sent this image" answerable through `by-sk` — useful before
   deleting a reference. The entity model's rule says an ordered child pointing
   at an *entity* gets an edge, and a node is not one. Worth doing anyway.
3. **Retire the stored `bindings` attribute** once every run has sends.
4. **Do drafts expire?** Proposed: no. A draft costs a row and no bytes.
5. **Does a scene learn about drafts?** `scenes render` could draft every shot and
   submit the board in one pass, on one yes. Same mechanism, one tier up.
