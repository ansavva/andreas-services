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

## Ids, and the one place a slug is still allowed

Every route below takes an **id**. `slug:<slug>` addressing exists for exactly
one reason — a person types a name on a command line — and it is confined to
`GET /api/characters/<id>` and `GET /api/projects/<id>`. Build one with
`address()`; do not concatenate it by hand, because the prefix is the API's
convention and not a string this package owns.

Resolving a slug is therefore one call, not a listing plus a search. `resolve_*`
returns the record, so a caller that resolved a slug already has everything and
does not go back for it.

## What is deliberately not here

**Bytes.** They travel presigned, and `adapters/store.py` owns that. A route
that hands out an upload URL is here (`add_run_output`, `scene_output`) because
its *request* shape is entity knowledge; what the caller then does with the URL
is the store's business.

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

Untouched. `api.Conflict` is a taken slug or a stale `rev`, `api.NotFound` is a
missing entity, and both are what a caller catches. Nothing here converts an
HTTP failure into a domain one — the domain modules own their own vocabulary
and would each convert it differently.
"""

from __future__ import annotations

from studio_pipeline.adapters import api


def address(slug: str) -> str:
    """`slug:<slug>` — the one id-shaped thing that is not an id.

    The prefix is the API's, so it is spelled once. A caller that has an id
    passes the id; a caller that has what a person typed passes this.
    """
    return f"slug:{slug}"


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
    """Every character in the library: id, slug, display name, hero, counts."""
    found = api.get("/api/characters", q=query)
    return found if isinstance(found, list) else []


def create_character(slug: str, display_name: str = "", fictional: bool = True,
                     profile: dict | None = None) -> dict:
    """Create a character and its starting folder layout in one transaction.

    The four pool folders come back already made — they are part of the create,
    not something the first write lazily discovers. `api.Conflict` means the
    slug is taken.
    """
    body = {"slug": slug, "display_name": display_name, "fictional": fictional}
    if profile is not None:
        body["profile"] = profile
    return api.post("/api/characters", body)


def get_character(char: str) -> dict:
    """One character's full record, `profile` included. `char` may be `slug:…`."""
    return api.get(f"/api/characters/{char}")


def resolve_character(slug: str) -> dict:
    """The record for a slug a person typed. One call, not a listing plus a scan."""
    return get_character(address(slug))


def patch_character(char_id: str, rev: int, *, slug: str | None = None,
                    display_name: str | None = None, fictional: bool | None = None,
                    hero: str | None = None) -> dict:
    """Change the record. **This is what a rename is** — one conditional write.

    `rev` is compare-and-swap, not check-then-write: a stale value is refused by
    the API's condition expression rather than by a read this side of the wire.
    `api.Conflict` is both "someone else wrote" and "that slug is taken", and
    the message distinguishes them.
    """
    body = _clean(slug=slug, display_name=display_name, fictional=fictional, hero=hero)
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


# ── references ──────────────────────────────────────────────────────────────

def references(char_id: str, group: str | None = None) -> dict:
    """The described index: `{"groups": {<group>: [entry, …]}, "counts": {…}}`.

    Entries arrive in `(group, order)` order with their file and a presigned
    URL, so a caller never sorts and never presigns a second time.
    """
    return api.get(f"/api/characters/{char_id}/references", group=group)


def reference_entries(char_id: str, group: str | None = None) -> list[dict]:
    """`references()` flattened, order preserved, each entry carrying its group.

    Almost every caller wants one list — the grouping is a presentation fact and
    the API returns it because the SPA draws sections. Flattening here rather
    than in five domain modules keeps the group key's spelling in one file.
    """
    found = references(char_id, group)
    out: list[dict] = []
    for name, entries in (found.get("groups") or {}).items():
        for entry in entries:
            out.append({**entry, "group": entry.get("group") or name})
    return out


def add_reference(char_id: str, node: str, group: str, *,
                  description: str | None = None, tags: list[str] | None = None,
                  after: str | None = None) -> dict:
    """Attach an existing node as a reference. **The bytes are already there.**

    Two steps and always have been: the image arrives, then a person decides it
    is identity (hard rule #2b). `after` places the entry between two existing
    ones by taking the midpoint of their `order`, so a reorder is one write and
    never touches a neighbour.
    """
    body = {"node": node, "group": group}
    body.update(_clean(description=description, tags=tags, after=after))
    return api.post(f"/api/characters/{char_id}/references", body)


def patch_reference(char_id: str, node: str, *, group: str | None = None,
                    description: str | None = None, tags: list[str] | None = None,
                    after: str | None = None) -> dict:
    """One row's write. `group` here is `regroup`; `after` here is `order`.

    Both used to move objects — a regroup was a reparent plus a records sweep, a
    reorder was a rename per file. Neither writes a byte now, because both are
    attributes of a row that names a node id.
    """
    return api.patch(f"/api/characters/{char_id}/references/{node}",
                     _clean(group=group, description=description, tags=tags, after=after))


def put_references(char_id: str, entries: list[dict]) -> dict:
    """Describe or reorder many references in ONE transaction.

    `describe-refs` is this call. Describing a forty-image library one write at a
    time is forty round trips and forty chances to stop halfway with the index
    half-written; the whole pass lands or none of it does.
    """
    return api.request("PATCH", f"/api/characters/{char_id}/references",
                       {"entries": entries})


def delete_reference(char_id: str, node: str) -> dict:
    """Detach a reference. **The file stays exactly where it is.**"""
    return api.delete(f"/api/characters/{char_id}/references/{node}")


def put_default_set(char_id: str, nodes: list[str], rev: int) -> dict:
    """Name the nodes sent when `--character` is given with no selector.

    **`rev` is required and was not being sent.** The route compare-and-swaps it
    like every other write on the record, so this failed `rev is required — the
    record is at rev N`. It never surfaced because the request died one layer
    earlier on an unregistered verb until #479 — the same way `edit --push`
    hid a `schema_version` it should not have sent.
    """
    return api.request("PATCH", f"/api/characters/{char_id}/default-set",
                       {"nodes": list(nodes), "rev": rev})


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


def create_project(slug: str, *, title: str = "", description: str = "",
                   characters: list[str] | None = None) -> dict:
    """Create a project, its root and its five starting subfolders."""
    body = {"slug": slug, "title": title, "description": description}
    if characters:
        body["characters"] = list(characters)
    return api.post("/api/projects", body)


def get_project(project: str) -> dict:
    """One project's record. `project` may be `slug:…`."""
    return api.get(f"/api/projects/{project}")


def resolve_project(slug: str) -> dict:
    return get_project(address(slug))


def patch_project(proj_id: str, rev: int, *, slug: str | None = None,
                  title: str | None = None, description: str | None = None,
                  hero: str | None = None) -> dict:
    body = _clean(slug=slug, title=title, description=description, hero=hero)
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
               prompt: dict | None = None) -> dict:
    """Record a run BEFORE the submission, and get back its folder and payload.

    The ordering is the whole point and predates this route: `request.json` was
    written before the submit and `result.json` only after it came back, which
    is what leaves a record behind when a prediction times out. A run that
    recorded nothing until it succeeded would lose exactly the runs worth
    investigating.

    **`bindings` are node ids.** A URL-shaped one is refused by the API with a
    400 — hard rule #3, enforced for the SPA as well as for the CLI rather than
    in `runs.py` where only one caller went through it.
    """
    body = {"project": project, "kind": kind, "engine": engine, "model": model,
            "input": input, "bindings": bindings or {}}
    body.update(_clean(characters=characters, prompt=prompt))
    return api.post("/api/runs", body)


def query_runs(*, project: str | None = None, character: str | None = None,
               model: str | None = None, status: str | None = None,
               since: str | None = None, limit: int | None = None,
               cursor: str | None = None) -> dict:
    """`{"runs": [...], "cursor": …}` — the query that replaces `runs find`.

    `runs find --character` used to list every project, list every run in each,
    read three documents per run and grep. It is one query against a row.
    """
    return api.get("/api/runs", project=project, character=character, model=model,
                   status=status, since=since, limit=limit, cursor=cursor)


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


def add_run_output(run_id: str, name: str, size: int, content_type: str) -> dict:
    """A node under the run's `output/`, plus a presigned PUT for its bytes."""
    return api.post(f"/api/runs/{run_id}/outputs",
                    {"name": name, "size": size, "content_type": content_type})


def put_run_response(run_id: str, body) -> dict:
    """Store the provider's response verbatim as a payload blob.

    `body` is whatever the provider sent. **Studio does not decode it** — it is
    serialised on the way out and read back as text, and the rule that nothing
    parses these documents survives here rather than being restated in `runs.py`.
    """
    return api.post(f"/api/runs/{run_id}/response", {"body": body})


def delete_run(run_id: str, *, files: str = "keep") -> dict:
    return api.delete(f"/api/runs/{run_id}", files=files)


# ── scenes ──────────────────────────────────────────────────────────────────

def create_scene(*, project: str, slug: str, title: str = "",
                 shots: list[dict] | None = None, setting: str = "",
                 defaults: dict | None = None) -> dict:
    body = {"project": project, "slug": slug, "title": title,
            "shots": shots or [], "setting": setting}
    body.update(_clean(defaults=defaults))
    return api.post("/api/scenes", body)


def query_scenes(*, project: str | None = None, cursor: str | None = None) -> dict:
    return api.get("/api/scenes", project=project, cursor=cursor)


def get_scene(scene_id: str) -> dict:
    """The envelope plus its `SHOT#` rows, in `order`."""
    return api.get(f"/api/scenes/{scene_id}")


def patch_scene(scene_id: str, **fields) -> dict:
    """Whatever moved: `title`, `setting`, `status`, `output`, `stitch`, `characters`."""
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


def scene_output(scene_id: str, name: str, size: int, content_type: str) -> dict:
    """An upload URL for the stitched take. **The encode stays local.**

    `ffmpeg` ships in this wheel and the Lambda has none, so `assemble`
    downloads, stitches here, uploads through this URL and then `PATCH`es the
    record. The API owns the record; it does not own the encode.
    """
    return api.post(f"/api/scenes/{scene_id}/output",
                    {"name": name, "size": size, "content_type": content_type})


# ── movies ──────────────────────────────────────────────────────────────────

def create_movie(*, project: str, slug: str, title: str = "",
                 scenes: list[str] | None = None) -> dict:
    return api.post("/api/movies", {"project": project, "slug": slug,
                                    "title": title, "scenes": list(scenes or [])})


def query_movies(*, project: str | None = None, cursor: str | None = None) -> dict:
    return api.get("/api/movies", project=project, cursor=cursor)


def get_movie(movie_id: str) -> dict:
    return api.get(f"/api/movies/{movie_id}")


def patch_movie(movie_id: str, **fields) -> dict:
    return api.patch(f"/api/movies/{movie_id}", _clean(**fields))


def delete_movie(movie_id: str, *, files: str = "keep") -> dict:
    return api.delete(f"/api/movies/{movie_id}", files=files)


def put_movie_scenes(movie_id: str, scenes: list[str]) -> dict:
    """Replace the cut list. **Scene ids** — the route validates every entry.

    Typed `list[dict]` and called with dicts, which the service rejects with a
    500. The answer is the movie in its read shape, so it can be merged.
    """
    return api.request("PATCH", f"/api/movies/{movie_id}/scenes", {"scenes": scenes})


def movie_output(movie_id: str, name: str, size: int, content_type: str) -> dict:
    """An upload URL for the finished cut. See `scene_output` — same arrangement."""
    return api.post(f"/api/movies/{movie_id}/output",
                    {"name": name, "size": size, "content_type": content_type})


# ── phrasebook ──────────────────────────────────────────────────────────────

def phrasebook(model: str | None = None) -> list[dict]:
    """The avoid/use pairs, optionally for one model.

    **There is no document any more**, which removes a whole failure: `add` used
    to write through `PATCH /api/text`, a route that overwrites and cannot
    create, so a library that had never held `phrasebook/wording.yaml` refused
    the first entry anybody tried to record. A row has no such precondition.
    """
    return _as_list(api.get("/api/phrasebook", model=model))


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
