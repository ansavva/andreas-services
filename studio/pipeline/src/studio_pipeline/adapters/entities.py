"""The entity routes: characters, projects, runs, scenes, movies, phrasebook.

**This module is the only place in the pipeline that knows an entity route's
spelling.** Not a style preference — a coordination requirement. The API half of
studio is written against the same spec by different hands, so the two agree or
they do not, and the cheapest place to find out is one file that can be read
top to bottom against `docs/ENTITY_MODEL_EXAMPLE.md` §2. A domain module calls
`entities.create_character(...)`; it never types `/api/characters`, never picks a
query parameter's name, and never learns that `rev` is spelled `rev`. When the
backend moves a field, this file changes and nothing else does.

That is the lesson `adapters/store.py` already carries from #302, applied one
layer up: the pipeline held seventy-one boto3 calls before that module existed,
and the migration was only reviewable because the vocabulary stayed put while
the thing underneath it moved.

## Ids, and nothing but ids

Every route below takes an **id**. There used to be a second address,
`slug:<slug>`, for exactly one reason — a person types a name on a command
line — confined to `GET /api/characters/<id>` and `GET /api/projects/<id>`, with
`address()` to build it and `resolve_*` to turn one into a record in a single
call.

**It went with slugs.** A name is a free-text label now: two characters may be
called the same thing, so resolving one would mean picking between them, which
is not something an address may do. `list_characters` is how a person finds an
id; every wrapper here takes one.

## What is deliberately not here

**Bytes.** They travel presigned, and `adapters/store.py` owns that. The one
route left here that hands out an upload URL is `add_run_output`, because its
*request* shape is entity knowledge; what the caller then does with the URL is
the store's business.

**And there are fewer of those than there were.** `scene_output` and
`movie_output` minted upload URLs for a stitched take that this process had just
encoded; a worker encodes it and files it now, so both went with the encoder
(#537). `put_run_response` stored a provider's reply that this process had just
received; the callback consumer receives it now (#536). `revoke_run_approval`
and `patch_movie` were never reached from a command at all. **A wrapper with no
caller is a claim about the wire surface that nothing checks**, and
`test_the_wire_surface_is_the_table` reads this file to build that claim — so a
route the CLI does not call must not be spelled here, however faithfully the
backend still serves it for the SPA.

**Node routes.** `POST /api/nodes`, the move/copy/delete verbs and the text
routes live in `adapters/store.py`, beside the path resolution they share. The
split is by subject: this file is about records, that one is about the tree.

## Every write is POST, PATCH or DELETE. **Never PUT.**

Six routes here replace a whole collection and `docs/ENTITY_MODEL.md` spells all
six as `PUT`, which is what PUT is for. The API registers none of them: it uses
`PATCH` throughout, because a verb has to be added to the CORS list, the MOCK
integration response and two gateway responses at once, and one omission is a
browser failure with no status attached (`backend/studio_core/app_factory.py`).

Every one of the six sent `PUT` from here anyway, and none of them had ever
reached the API. `tests/support/fake_api.py` answered PUT, so the suite agreed with the
adapter rather than with the service — which is why it refuses the verb outright
now. If the API adopts PUT, this file changes with it and nothing else does.

## Errors

Untouched. `api.Conflict` is a stale `rev`, `api.NotFound` is a
missing entity, and both are what a caller catches. Nothing here converts an
HTTP failure into a domain one — the domain modules own their own vocabulary
and would each convert it differently.
"""

from __future__ import annotations

import uuid

from studio_pipeline.adapters import api


def _clean(**fields) -> dict:
    """Drop the keys a caller left as None.

    A `PATCH` body says what changes, so `None` has to mean "not mentioned"
    rather than "set to null" — otherwise every optional keyword on every
    wrapper below would blank a field nobody asked about. The routes that
    genuinely need to clear a value (`hero`, `error`) pass it positionally in a
    dict of their own.
    """
    return {name: value for name, value in fields.items() if value is not None}


# ── characters ──────────────────────────────────────────────────────────────

def list_characters(query: str | None = None) -> list[dict]:
    """Every character in the library: id, name, hero, counts."""
    found = api.get("/api/characters", q=query)
    return found if isinstance(found, list) else []


def create_character(name: str, profile: dict | None = None) -> dict:
    """Create a character and its starting folder layout in one transaction.

    The four pool folders come back already made — they are part of the create,
    not something the first write lazily discovers. **There is no conflict to
    raise**: a name is a label, so two characters may share one.
    """
    body = {"name": name}
    if profile is not None:
        body["profile"] = profile
    return api.post("/api/characters", body)


def get_character(char_id: str) -> dict:
    """One character's full record, `profile` included."""
    return api.get(f"/api/characters/{char_id}")


def patch_character(char_id: str, rev: int, *, name: str | None = None,
                    hero: str | None = None) -> dict:
    """Change the record. **This is what a rename is** — one conditional write.

    `rev` is compare-and-swap, not check-then-write: a stale value is refused by
    the API's condition expression rather than by a read this side of the wire.
    `api.Conflict` means somebody else wrote — it used to mean "that slug is
    taken" as well, and there is no claim left to take.
    """
    body = _clean(name=name, hero=hero)
    body["rev"] = rev
    return api.patch(f"/api/characters/{char_id}", body)


def put_profile(char_id: str, profile: dict, rev: int) -> dict:
    """Replace the whole bible. The `edit` round trip's write half.

    **`PATCH`, despite replacing.** Replace and merge share one address and are
    told apart by which key the body carries — `{profile}` against `{patch}` —
    so one verb serves both. This sent `PUT`, which the route does not register,
    and `edit --push` has therefore never reached the API.
    """
    return api.request("PATCH", f"/api/characters/{char_id}/profile",
                       {"profile": profile, "rev": rev})


def patch_profile(char_id: str, patch: dict, rev: int) -> dict:
    """Merge one section of the bible, leaving the rest alone."""
    return api.patch(f"/api/characters/{char_id}/profile", {"patch": patch, "rev": rev})


def delete_character(char_id: str, *, files: str = "keep", force: bool = False) -> dict:
    """Delete a character. `files='keep'` orphans the folder rather than the media.

    The default is the safe one on purpose: the reverse default loses media to a
    typo, and a folder left in the library root is visible and recoverable.
    """
    return api.delete(f"/api/characters/{char_id}", files=files,
                      force=1 if force else None)


# ── identity, which is tags on the files ────────────────────────────────────

def character_images(char_id: str, tags: list[str] | None = None) -> list[dict]:
    """Every image under a character, with what each one says about itself.

    **The reference index is gone and this is not a replacement for it.** That
    listed the pictures somebody had filed a `REF#` row for, so an image dropped
    into the tree by hand was invisible — which is how twelve files in this
    library ended up with no description anywhere. This is the character's whole
    branch, filtered to images, and the tags on each say which are identity.

    One listing call: `?under=<root>&depth=all&kind=image`, which is the same
    route the file browser and the picker use.
    """
    record = get_character(char_id)
    found = api.get("/api/nodes", under=record["root"], depth="all", kind="image",
                    sort="name", tag=",".join(tags) if tags else None)
    return found.get("entries") or []


def selection(char_id: str, *, pick: list[str] | None = None,
              tag: list[str] | None = None, limit: int | None = None) -> dict:
    """**The ordered nodes a model would actually be shown.**

    The one route both halves of studio must agree on, which is why it is a
    route rather than a function in each: the CLI and the SPA disagreeing about
    which images a generation saw is a disagreement nobody can audit afterwards.

    Over-cap is refused with the index in the body rather than truncated — the
    behaviour `engine/refs.py` used to implement locally, moved somewhere both
    callers share. That refusal arrives as `api.Conflict`.
    """
    return api.get(f"/api/characters/{char_id}/selection",
                   pick=",".join(pick) if pick else None,
                   tag=",".join(tag) if tag else None,
                   limit=limit)


def textblock(char_id: str) -> dict:
    """The pasteable identity paragraph, for engines driven from a start frame."""
    return api.get(f"/api/characters/{char_id}/textblock")


def character_runs(char_id: str, cursor: str | None = None) -> dict:
    """Runs that used this character, newest first. One query; formerly a walk."""
    return api.get(f"/api/characters/{char_id}/runs", cursor=cursor)


def character_projects(char_id: str) -> list[dict]:
    """Projects that involve this character — a question with no answer before."""
    found = api.get(f"/api/characters/{char_id}/projects")
    return found if isinstance(found, list) else []


# ── projects ────────────────────────────────────────────────────────────────

def list_projects() -> list[dict]:
    return _as_list(api.get("/api/projects"))


def create_project(name: str, *, description: str = "",
                   characters: list[str] | None = None) -> dict:
    """Create a project, its root and its five starting subfolders."""
    body = {"name": name, "description": description}
    if characters:
        body["characters"] = list(characters)
    return api.post("/api/projects", body)


def get_project(project: str) -> dict:
    """One project's record, by id."""
    return api.get(f"/api/projects/{project}")


def patch_project(proj_id: str, rev: int, *, name: str | None = None,
                  description: str | None = None,
                  hero: str | None = None) -> dict:
    body = _clean(name=name, description=description, hero=hero)
    body["rev"] = rev
    return api.patch(f"/api/projects/{proj_id}", body)


def delete_project(proj_id: str, *, files: str = "keep", cascade: bool = False,
                   force: bool = False) -> dict:
    """`cascade` takes the runs, scenes and movies with it. `force` orphans them.

    Both exist because `force` shipped first and does the wrong thing: it leaves
    every child naming a project id that is gone. Prefer `cascade`.
    """
    return api.delete(f"/api/projects/{proj_id}", files=files,
                      cascade=1 if cascade else None, force=1 if force else None)


def put_project_characters(proj_id: str, characters: list[str]) -> dict:
    """Replace the involvement links. `link` and `unlink` are both this call.

    A replace rather than an add/remove pair because the links are a set and a
    set is what the caller has: reading the current list, changing it and
    putting it back is one round trip either way, and a partial verb would need
    its own idempotency story.
    """
    return api.request("PATCH", f"/api/projects/{proj_id}/characters",
                       {"characters": list(characters)})


def project_inputs(proj_id: str) -> list[dict]:
    """The working pool, in the order that defines `--input N`.

    **Position in this list is the whole meaning of `--input N`.** The pool used
    to be numbered into the filenames (`<project>_in_<n>.png`), which meant a
    deletion either renumbered every file or left a hole that silently shifted
    what `--input 3` meant. The API orders it; nothing here re-sorts.

    **Unwrapped from `{folder, inputs}`.** This route is the one listing that
    does not answer with a bare array, and it went through `_as_list`, which
    answers `[]` for anything that is not a list — so the pool read as empty
    every time. Silently: an empty pool is an ordinary state, so `projects
    inputs` printed nothing and `projects show` counted zero, and neither
    looked like a failure.
    """
    found = api.get(f"/api/projects/{proj_id}/inputs")
    return _as_list(found.get("inputs") if isinstance(found, dict) else found)


def project_scenes(proj_id: str) -> list[dict]:
    return _as_list(api.get(f"/api/projects/{proj_id}/scenes"))


def project_movies(proj_id: str) -> list[dict]:
    return _as_list(api.get(f"/api/projects/{proj_id}/movies"))


# ── runs ────────────────────────────────────────────────────────────────────

def create_run(*, project: str, kind: str, engine: str, model: str,
               input: dict, bindings: dict | None = None,
               characters: list[str] | None = None,
               prompt: dict | None = None, plan: dict | None = None,
               sends: list[dict] | None = None, name: str | None = None) -> dict:
    """Create the run as a DRAFT, before the approval and before the submission.

    The ordering is the whole point and predates this route: `request.json` was
    written before the submit and `result.json` only after it came back, which
    is what leaves a record behind when a prediction times out. A run that
    recorded nothing until it succeeded would lose exactly the runs worth
    investigating.

    **`bindings` are node ids.** A URL-shaped one is refused by the API with a
    400 — hard rule #3, enforced for the SPA as well as for the CLI rather than
    in `runs.py` where only one caller went through it.

    **It comes back `draft`, and nothing may be submitted until it is approved.**
    The ordering moved one step earlier than the paragraph above describes: the
    record is written before the *approval* too, which is what gives an approval
    something to attach to. `sends` supersedes `bindings` and carries what the
    map could not — each image's role and where it came from — and either is
    accepted so that a caller can be moved over one at a time.

    **`name` is what the OUTPUT FILE will be called, and it is recorded here
    because nothing else will be in a position to say.** The download used to
    happen in this process, so the filename was an argument to it; it happens in
    the API now, driven by a webhook that arrives with no request body at all. It
    is deliberately not part of `plan`: `plan_digest` hashes the plan, so a
    rename would void an approval over something the provider is never sent.
    """
    body = {"project": project, "kind": kind, "engine": engine, "model": model,
            "input": input, "bindings": bindings or {}}
    body.update(_clean(characters=characters, prompt=prompt, plan=plan, sends=sends,
                       name=name))
    return api.post("/api/runs", body)


def patch_run_plan(run_id: str, plan: dict) -> dict:
    """Rewrite a draft's authored half. **Clears any approval, every time.**

    That is hard rule #2's "re-approve after **any** edit", and it is the API's
    doing rather than this function's — stated here because a caller that edits
    a plan needs to know its approval is gone, and finding out at submit time is
    finding out too late.
    """
    return api.patch(f"/api/runs/{run_id}/plan", {"plan": plan})


def patch_run_sends(run_id: str, sends: list[dict]) -> dict:
    """Replace the ordered images a draft binds. Clears any approval, every time."""
    return api.patch(f"/api/runs/{run_id}/sends", {"sends": sends})


def approve_run(run_id: str, digest: str, via: str = "interactive") -> dict:
    """Record that a person read THIS payload and said yes to it.

    **The digest is what makes it an approval rather than a timestamp.** The API
    recomputes the digest of what is actually on the row and refuses a mismatch,
    so an approval cannot outlive the payload it was given for. A 409 here means
    the plan moved and has to be read again — never that the API is unavailable.

    `via` says how the yes arrived: `interactive` for one typed at this terminal,
    `relayed` for one a person gave elsewhere and an agent passed on. The record
    is weaker in the second case and says so.
    """
    return api.post(f"/api/runs/{run_id}/approve", {"digest": digest, "via": via})


def query_runs(*, project: str | None = None, character: str | None = None,
               model: str | None = None, status: str | None = None,
               since: str | None = None, limit: int | None = None,
               cursor: str | None = None, fingerprint: str | None = None,
               include: str | None = None) -> dict:
    """`{"runs": [...], "cursor": …}` — the query that replaces `runs find`.

    `runs find --character` used to list every project, list every run in each,
    read three documents per run and grep. It is one query against a row.

    `fingerprint` is the duplicate-submission guard: it asks whether this exact
    payload has been submitted to this project before, which used to be a
    per-machine file because the listing rows did not carry enough to answer it.
    `include="drafts"` goes with it — an unsubmitted draft bills nothing and must
    not read as a duplicate, but the caller decides that, not this wrapper.
    """
    return api.get("/api/runs", project=project, character=character, model=model,
                   status=status, since=since, limit=limit, cursor=cursor,
                   fingerprint=fingerprint, include=include)


def resolve_run(ref: str, project: str | None = None,
                include: str | None = None) -> dict:
    """A runref — `<project>/latest#2`, `latest`, `run-<uuid>` — to the run.

    The sibling of `GET /api/resolve?path=`: both turn what a person types into
    the thing it names, so a spelling keeps working as an address without being
    an identity. `#N` narrows `outputs` to the one asked for and leaves the rest
    of the record whole.
    """
    return api.get("/api/runs/resolve", ref=ref, project=project, include=include)


def get_run(run_id: str) -> dict:
    """The envelope, with outputs and bindings expanded and `payload` as node ids."""
    return api.get(f"/api/runs/{run_id}")


def patch_run(run_id: str, *, status: str | None = None,
              prediction_id: str | None = None, error=None,
              cost: dict | None = None, completed: str | None = None,
              outputs: list[str] | None = None) -> dict:
    """Completion. `error` is passed through even when falsy — null clears it.

    `outputs` is here for **adoption only**. Every ordinary output arrives
    through `add_run_output`, which mints the node and appends it in one act;
    an adopted artifact already exists and is reparented into the run's folder,
    so the list has to be set rather than grown. A caller passing it for any
    other reason is fighting the route that maintains it.
    """
    body = _clean(status=status, prediction_id=prediction_id, cost=cost,
                  completed=completed, outputs=outputs)
    if error is not None:
        body["error"] = error
    return api.patch(f"/api/runs/{run_id}", body)


def submit_run(run_id: str) -> dict:
    """Send an approved run to the provider. **The call that spends money.**

    **This replaced the whole billing half of `engine/submit.py`.** The CLI used
    to hold the Replicate token, mint the presigned URLs, create the prediction
    and then sit in a poll loop until it settled — so a 15-minute video meant a
    terminal nobody could close and a killed process left a run wedged. All of
    that is one call now, and what waits for the answer is a webhook.

    The API refuses this unless the run is approved and the approval still
    matches the payload, which is hard rule #2's gate standing in front of the
    money rather than behind it.

    The reply carries the run, and `callback`, which says how this submission
    will be closed:

    * `"webhook"` — Replicate will call the API back. Watch the row.
    * `"poll"` — nothing on the internet can reach that API, which is what local
      development looks like. The caller drives `reconcile_run` itself.

    A caller that ignores `callback` and polls the row would hang forever in the
    second case, which is why `submit.wait_for` reads it rather than assuming.
    """
    return api.post(f"/api/runs/{run_id}/submit", {})


def reconcile_run(run_id: str) -> dict:
    """Ask the API to ask the provider what happened, and close the run on it.

    Two situations, one call. Locally there was never going to be a callback —
    Replicate cannot reach a laptop — and in production one can be lost to a
    deploy landing mid-flight. From here both are "the run says `running` and
    nothing has told us otherwise".

    Idempotent: a run already finished comes back untouched rather than having
    its output uploaded twice.
    """
    return api.post(f"/api/runs/{run_id}/reconcile", {})


def add_run_output(run_id: str, name: str, size: int, content_type: str) -> dict:
    """A node under the run's `output/`, plus a presigned PUT for its bytes."""
    return api.post(f"/api/runs/{run_id}/outputs",
                    {"name": name, "size": size, "content_type": content_type})


def delete_run(run_id: str, *, files: str = "keep") -> dict:
    return api.delete(f"/api/runs/{run_id}", files=files)


# ── scenes ──────────────────────────────────────────────────────────────────

def create_scene(*, project: str, name: str,
                 shots: list[dict] | None = None, setting: str = "",
                 defaults: dict | None = None) -> dict:
    body = {"project": project, "name": name,
            "shots": shots or [], "setting": setting}
    body.update(_clean(defaults=defaults))
    return api.post("/api/scenes", body)


def query_scenes(*, project: str | None = None, cursor: str | None = None) -> dict:
    return api.get("/api/scenes", project=project, cursor=cursor)


def get_scene(scene_id: str) -> dict:
    """The envelope plus its `SHOT#` rows, in `order`."""
    return api.get(f"/api/scenes/{scene_id}")


def patch_scene(scene_id: str, **fields) -> dict:
    """Whatever moved: `name`, `setting`, `status`, `output`, `stitch`, `characters`."""
    return api.patch(f"/api/scenes/{scene_id}", _clean(**fields))


def delete_scene(scene_id: str, *, files: str = "keep") -> dict:
    return api.delete(f"/api/scenes/{scene_id}", files=files)


def put_shots(scene_id: str, shots: list[dict]) -> dict:
    """The plan revision. **Merges onto rendered work rather than replacing it.**

    Re-ingesting a plan is how a plan is revised, and it must not orphan a panel
    somebody already paid to render — so the API merges by shot id and the
    caller does not have to hand-carry the rendered fields across.
    """
    return api.request("PATCH", f"/api/scenes/{scene_id}/shots", {"shots": shots})


def patch_shot(scene_id: str, shot_id: str, **fields) -> dict:
    return api.patch(f"/api/scenes/{scene_id}/shots/{shot_id}", _clean(**fields))


# ── movies ──────────────────────────────────────────────────────────────────

def create_movie(*, project: str, name: str,
                 scenes: list[str] | None = None) -> dict:
    return api.post("/api/movies", {"project": project, "name": name,
                                    "scenes": list(scenes or [])})


def query_movies(*, project: str | None = None, cursor: str | None = None) -> dict:
    return api.get("/api/movies", project=project, cursor=cursor)


def get_movie(movie_id: str) -> dict:
    return api.get(f"/api/movies/{movie_id}")


def delete_movie(movie_id: str, *, files: str = "keep") -> dict:
    return api.delete(f"/api/movies/{movie_id}", files=files)


def put_movie_scenes(movie_id: str, scenes: list[str]) -> dict:
    """Replace the cut list. **Scene ids** — the route validates every entry.

    Typed `list[dict]` and called with dicts, which the service rejects with a
    500. The answer is the movie in its read shape, so it can be merged.
    """
    return api.request("PATCH", f"/api/movies/{movie_id}/scenes", {"scenes": scenes})


# ── the template library ────────────────────────────────────────────────────

def templates() -> dict:
    """The blocks and templates a prompt is built from.

    `{"blocks": {...}, "templates": [...]}`.

    Wrapped, like `/api/phrasebook` and unlike the bare-array listings — and the
    shape is normalised here rather than at the call site, because the last
    module that let a wrapped answer reach `_as_list` reported every library's
    phrasebook as empty for the whole life of a migration.
    """
    found = api.get("/api/templates")
    if not isinstance(found, dict):
        return {"blocks": {}, "templates": []}
    return {"blocks": found.get("blocks") or {},
            "templates": _as_list(found.get("templates"))}


def put_block(name: str, text: str) -> dict:
    """Write one shared block. An overwrite: a block IS its name."""
    return api.patch(f"/api/templates/blocks/{_segment(name)}", {"text": text})


def put_template(template_id: str, fields: dict) -> dict:
    """Write one template, addressed by its id, with its name in the body.

    **A document keyed on names writes rows keyed on ids**, and the resolution is
    the caller's — `domain/templates.py` matches the file against the stack it
    just read, so it knows the id of every name already there and mints one only
    for a name that is new. A block is different and is still keyed on its name:
    prose cites it as `{block.face_only}`, so its name is load-bearing in a way a
    template's is not.
    """
    return api.patch(f"/api/templates/{_segment(template_id)}", fields)


def new_template_id() -> str:
    """A UUID for a template a push is creating.

    Minted here rather than by the API, so a create and an update are one call
    with one shape — the same reason a node id is minted by whoever asks for one.
    """
    return f"template-{uuid.uuid4()}"


# There are deliberately no `delete_*` wrappers, and #553 is why: a wrapper
# with no caller is a claim about the wire surface that nothing checks, and it
# deleted five of them for that reason on the day this was written. `studio spec`
# never removes a row — a push states what a file contains, not that nothing else
# exists — so nothing here would call them. The API serves both DELETEs for the
# app, which is the same footing `/api/runs/<id>/response` is on.


def _segment(value: str) -> str:
    """One path segment, quoted. `safe=''` because the default keeps `/`.

    A block name or an angle id has no reason to hold a slash, and the cost of
    one that did is a 404 nobody can read — the same trap
    `delete_phrasebook_term` documents for a model key that genuinely does.
    """
    import urllib.parse

    return urllib.parse.quote(value, safe="")


# ── phrasebook ──────────────────────────────────────────────────────────────

def phrasebook(model: str | None = None) -> list[dict]:
    """The avoid/use pairs, optionally for one model.

    **There is no document any more**, which removes a whole failure: `add` used
    to write through `PATCH /api/text`, a route that overwrites and cannot
    create, so a library that had never held `phrasebook/wording.yaml` refused
    the first entry anybody tried to record. A row has no such precondition.

    **This route wraps, and `_as_list` alone silently swallowed it.** It answers
    `{"terms": [...]}` where every other listing route here answers a bare
    array, so `_as_list` — which returns `[]` for any shape that is not a list —
    turned every read into an empty phrasebook. Not "the phrasebook is empty",
    which is a legitimate state and reads identically: `show` printed `{}`,
    `models` printed nothing, and `check` reported no wording list, for every
    model, whatever the library held. The claim that reading was never the
    broken half of this migration was wrong.

    Unnoticed because the pipeline's fake API answered this route with a bare
    list, so the suite exercised a shape the service does not return.
    """
    found = api.get("/api/phrasebook", model=model)
    if isinstance(found, dict):
        return _as_list(found.get("terms"))
    return _as_list(found)


def add_phrasebook_term(model: str, avoid: str, use: str, *,
                        note: str | None = None,
                        replicate: str | None = None) -> dict:
    """Record one substitution. `api.Conflict` means that pair is already there."""
    body = {"model": model, "avoid": avoid, "use": use}
    body.update(_clean(note=note, replicate=replicate))
    return api.post("/api/phrasebook", body)


def delete_phrasebook_term(model: str, avoid: str) -> dict:
    import urllib.parse

    # The model key carries a slash (`google/nano-banana-pro`) and the avoid
    # phrase carries spaces, so both are path segments that have to be quoted.
    # `quote` with an empty `safe` — the default keeps `/`, which would split
    # the model into two segments and 404.
    return api.delete("/api/phrasebook/"
                      f"{urllib.parse.quote(model, safe='')}/"
                      f"{urllib.parse.quote(avoid, safe='')}")


def _as_list(found) -> list[dict]:
    """A list, whatever a route answered with.

    Every listing route here returns a JSON array, and `api.request` answers an
    empty body with `{}` rather than `None` so callers need not distinguish "no
    content" from "failed". That leaves exactly one shape to normalise, and
    doing it once is cheaper than each caller guessing.
    """
    return found if isinstance(found, list) else []


# ── the model registry ──────────────────────────────────────────────────────
#
# Not an entity, and here anyway, because this module is where a route string is
# allowed to live — `test_no_route_string_lives_outside_the_adapters` enforces
# that and is right to. The registry moved to the backend so that one copy could
# answer the CLI, the SPA and `GET /api/characters/<id>/selection` at once;
# `engine/registry.py` is the reader that gives it a query surface.


def models() -> dict:
    """Every registry entry, keyed by registry name."""
    found = api.get("/api/models")
    return (found or {}).get("models") or {} if isinstance(found, dict) else {}


def model_schema(model: str) -> dict:
    """A model's LIVE input schema, fetched by the API from the provider.

    `{model, props, schemas, snapshot}`. **The CLI holds no Replicate token**, so
    this is the only way it can see a schema at all — and that is the point
    rather than a limitation: three commands that never spend anything used to be
    the reason a provider credential sat on every developer's machine.

    Registered or not. `studio add-model` and `studio run owner/name` both ask
    about a model precisely because it is not in the registry yet.
    """
    return api.get(f"/api/models/{model}/schema")


def model_readme(model: str) -> str:
    """A model's README as raw markdown, fetched by the API from the provider.

    Read by `studio add-model`, which infers a registry entry from prose the
    schema does not carry. The inference stays here because what it produces is a
    repo file somebody reviews.
    """
    found = api.get(f"/api/models/{model}/readme")
    return (found or {}).get("readme") or "" if isinstance(found, dict) else ""


def build_prompt(obj: dict, engine: str, *, emit: str = "both",
                 compact: bool = False, overrides: dict | None = None) -> dict:
    """Assemble and validate a structured video prompt. Writes nothing.

    The rules live in `services/prompt.py` because they need the registry and the
    phrasebook, both of which are the API's — and because nothing but `studio
    prompt` could reach them while they lived in the pipeline.
    """
    return api.post("/api/prompt", {
        "object": obj, "engine": engine, "emit": emit,
        "compact": compact, "overrides": overrides or {},
    })


# ── renders ─────────────────────────────────────────────────────────────────
#
# **What used to be `adapters/ffmpeg.py` and Pillow in this wheel.** Stitching, a
# frame grab, a contact grid and a contact sheet are done by a worker Lambda with
# ffmpeg in its image; this enqueues one and reads the row back. See
# `domain/renders.py` for the wait, and `backend/studio_core/services/render.py`
# for what the worker does with it.

def create_render(kind: str, params: dict) -> dict:
    """`POST /api/renders` — 202, and the row is what to poll.

    Not 201: nothing the caller asked for exists yet. The response carries the
    `id`, which is the whole handle on the job.
    """
    return api.post("/api/renders", {"kind": kind, "params": params})


def get_render(render_id: str) -> dict:
    """One render job row: `queued` / `running` / `succeeded` / `failed`."""
    return api.get(f"/api/renders/{render_id}")


# ── images ──────────────────────────────────────────────────────────────────
#
# The two operations that are NOT on the queue. Both are sub-second on a single
# image, so a queue round trip would cost more than the work — and the API image
# carries Pillow (3 MB) where the render image carries ffmpeg (80 MB).

def convert_image(node: str, *, to: str | None = None, dest: str | None = None,
                  name: str | None = None, quality: int = 95) -> dict:
    """Re-encode one image into a new node. The source is never modified."""
    return api.post("/api/images/convert", _clean(
        node=node, to=to, dest=dest, name=name, quality=quality))


def crop_image(node: str, box: str, *, to: str | None = None,
               dest: str | None = None, name: str | None = None,
               quality: int = 95) -> dict:
    """Cut `LEFT,TOP,RIGHT,BOTTOM` out of one image into a new node.

    The reply carries the box that was actually cut and whether it was clamped,
    because a silent clamp is a box that is not the box anybody stated.
    """
    return api.post("/api/images/crop", _clean(
        node=node, box=box, to=to, dest=dest, name=name, quality=quality))
