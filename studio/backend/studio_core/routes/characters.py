"""Characters: who a subject is, and which images say so.

A character is a row — `CHAR#<char_id>` / `META`, with a `LIB#<lib>` /
`CHAR#<char_id>` index row beside it — and four things follow from that:

* **A rename is one field on one row.** The name is a free-text label, the index
  row is keyed on the id, and the root folder is named by the id.
* **What a picture is and what it is for are tags on the file**, so nothing has
  to be renumbered or regrouped and no bytes move.
* **A description is on the file's row**, so writing twelve of them is twelve
  row writes rather than twelve rewrites of one document racing each other.
* **"Which projects involve this character" has an answer**, and "every run that
  used it" is one query.

## The two things this module decides rather than stores

**The profile schema.** `profile` is the bible: seven sections and one
paragraph. Which of a character's pictures a generation is shown is not in it —
that is the `default` tag and a group tag on the node. The sections are
validated here — nowhere else in the service has an opinion about the shape of
a bible.

**What a model will actually be shown.** `GET /api/characters/<id>/selection` is
a route rather than a function in each half of studio precisely so the CLI and
the SPA cannot disagree about it, and so the over-cap refusal happens in one
place. Slot N means "position N in the resolved selection".

## Hard rule #1 lives here too

No production character is named anywhere in this repository, and that includes
the S3 keys this module's uploads produce: an identity image is
`characters/<char_id>/<node_id>.<ext>`, so a listing of the media bucket is a
list of UUIDs. **The catalog's folder tree says nothing either**: a character's
root folder is named by its id, so the name lives on one row.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from studio_core.routes import projects as project_routes
from studio_core.routes import support
from studio_core import config
from studio_core.services import browse, catalog, keys, layout, manage, registry

logger = logging.getLogger(__name__)

bp = Blueprint("characters", __name__, url_prefix="/api")

KIND = catalog.ENTITY_CHARACTER

# The bible's sections, as the API validates them. Seven maps and one paragraph.
#
# Validated as *sections* and not field by field, deliberately. What goes inside
# `face` is a description a person writes for a model to read, and a service that
# enforced its keys would be a service that refuses a character somebody wanted to
# describe differently. What is enforced is the thing a client can get wrong
# without noticing: a section that is a string where a map belongs, which would
# make `PATCH .../profile` merge a paragraph over a structure.
PROFILE_SECTIONS = (
    "identity",
    "face",
    "body",
    "wardrobe",
    "voice",
    "rendering",
    "consistency",
)
TEXT_BLOCK = "text_identity_block"

# What `GET .../textblock` hands back when nobody has authored the paragraph yet.
#
# **The raw material, not an apology.** The block is a 50-70 word compression of
# these five sections, written by hand because nothing in this service can write
# it — the backend makes no model calls, so there is no compressor to invoke. The
# route's job is to put the source in front of whoever is doing the compressing.
#
# `rendering` and `voice` are absent deliberately: a text-only engine is being
# told what the character LOOKS like, and a medium or an accent spends words on
# something the paragraph is not for.
IDENTITY_BEARING = ("identity", "face", "body", "wardrobe", "consistency")

# **There is no cap table here.** `services/registry.py` is the registry, served
# at `GET /api/models`, and a second copy here would be a second answer to what
# a model accepts — one that drifts the moment a model is added.
#
# **A cap is refused rather than applied**: silently handing a model the first
# seven of eighteen references is a shoot whose result nobody can explain, so
# the request fails and the whole index comes back in the body so the caller
# can choose.


def clean_profile(raw) -> dict:
    """A bible, validated by section.

    An absent profile is `{}` and not an error: `POST /api/characters` takes one
    optionally, because a character is created before anybody has written a word
    about it and `studio character edit` is the next command either way.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("profile must be an object")

    unknown = sorted(set(raw) - set(PROFILE_SECTIONS) - {TEXT_BLOCK})
    if unknown:
        raise ValidationError(f"profile has no section called {unknown[0]!r}")
    for section in PROFILE_SECTIONS:
        if section in raw and not isinstance(raw[section], dict):
            raise ValidationError(f"profile.{section} must be an object")
    if TEXT_BLOCK in raw and not isinstance(raw[TEXT_BLOCK], str):
        raise ValidationError(f"profile.{TEXT_BLOCK} must be a string")
    return raw


def _character(addressed: str, held: dict) -> dict:
    return support.entity_at(KIND, g.library, addressed, held)


def _node_in(record: dict, node_id: str, label: str) -> dict:
    """One node the request names, proved to be in the character's own library.

    **Checked against the character rather than against the caller**, and the
    difference matters: the caller may be in two libraries, and a `hero` or a
    reference pointing at a node in the *other* one would be a record that
    presigns bytes its own library does not hold.
    """
    node = catalog.node(node_id)
    if node["lib"] != record["lib"]:
        raise ValidationError(f"{label} names a node in another library")
    return node


def _hero(record: dict, nodes: dict[str, dict]) -> dict | None:
    """The card image, presigned, or nothing.

    Signed from a record already in hand rather than fetched per character: the
    listing batches every hero in one read and signs locally, so a library of
    twenty characters is one extra round trip rather than twenty.
    """
    node = nodes.get(record.get("hero") or "")
    if not node or not node.get("blob_key"):
        return None
    return {"node": node["node_id"], "url": s3.presign(node["blob_key"])}


def _file_counts(records: list[dict]) -> dict[str, dict[str, int]]:
    """`entity id -> {files, default}`, batched then one branch query each.

    **Both numbers come out of one walk.** `counts.default` is the files under
    this character carrying `default`, which the walk that counts files already
    has in hand.

    One `BatchGetItem` for the roots and then one `branch` query per character,
    which is defensible for the reason a counter on the record is not: a library
    holds tens of characters, not thousands, and a stored number is a second
    thing for every upload, move, delete and re-tag to keep in step.

    **A truncated branch is counted as what was read, not refused.** `subtree`
    turns the cap into a `ValidationError` because both its callers are writes
    and a half-finished move is worse than none; this is a number next to a name
    in a list, and refusing to draw the list because one character has a lot of
    files in it would be the wrong trade.
    """
    roots = catalog.records([record["root"] for record in records if record.get("root")])
    cap = config.max_folder_objects()
    counts = {}
    for record in records:
        root = roots.get(record.get("root"))
        if not root:
            counts[record["id"]] = {"files": 0, "default": 0}
            continue
        nodes, _truncated = catalog.branch(g.library, catalog.child_path(root), cap)
        files = [node for node in nodes if node.get("kind") == catalog.KIND_FILE]
        counts[record["id"]] = {
            "files": len(files),
            "default": sum(1 for node in files if DEFAULT_TAG in (node.get("tags") or [])),
        }
    return counts


@bp.get("/characters")
def list_characters():
    """Every character in the library, newest edit first when `?q=` is absent.

    **One query for the index rows, one batched read for the records, one batched
    read for the heroes and one for the roots.** Both counts come out of ONE
    branch query per character — `counts.default` is the files under it carrying
    the `default` tag, which the walk that counts files already has in hand.

    `?q=` filters on the name, in memory. A library holds tens of characters, not
    thousands; an index for this would be a second thing to keep correct for a
    substring match a client could do itself.
    """
    held = support.memberships()
    support.member_of(g.library, held)

    records = catalog.entities_in(g.library, KIND)
    query = (request.args.get("q") or "").strip().lower()
    if query:
        records = [record for record in records
                   if query in (record.get("name") or "").lower()]

    heroes = catalog.records([record["hero"] for record in records if record.get("hero")])
    files = _file_counts(records)
    listed = [
        {
            "id": record["id"],
            "name": record.get("name"),
            "hero": _hero(record, heroes),
            "counts": files.get(record["id"], {"files": 0, "default": 0}),
            "updated": record.get("updated"),
        }
        for record in records
    ]
    # By name, then by id — which is what makes the order STABLE now that two
    # characters may share a name. A sort on the name alone would let two rows
    # swap places between reads for no reason a person could see.
    listed.sort(key=lambda entry: ((entry["name"] or "").lower(), entry["id"]))
    return jsonify(listed), 200


@bp.post("/characters")
def create_character():
    """A character, its index row, its root folder and its four pools — one write.

    **201, and the whole of it exists or none of it does.** Twelve items in one
    `TransactWriteItems`; a create that timed out is a create a person can simply
    repeat.

    **There is no 409.** A name is a free-text label and both keys are minted
    UUIDs, so nothing here can collide and there is nothing for a client to
    recover from.
    """
    body = support.body()
    held = support.memberships()
    support.member_of(g.library, held)

    root = catalog.library(g.library)["root_node"]
    record = catalog.create_character(
        g.library,
        root,
        name=keys.clean_label(body.get("name")),
        profile=clean_profile(body.get("profile")),
        layout=layout.CHARACTER_LAYOUT,
    )
    return jsonify(record), 201, {"Location": f"/api/characters/{record['id']}"}


@bp.get("/characters/<addressed>")
def get_character(addressed: str):
    """The full record, `profile` included. Addressed by id."""
    held = support.memberships()
    record = _character(addressed, held)
    heroes = catalog.records([record["hero"]] if record.get("hero") else [])
    return jsonify(
        {
            **record,
            "hero_url": _hero(record, heroes),
            "counts": _file_counts([record]).get(record["id"], {"files": 0, "default": 0}),
        }
    ), 200


@bp.patch("/characters/<addressed>")
def update_character(addressed: str):
    """Rename or re-hero — under a `rev`.

    **A stale `rev` is a 409 and never a silent overwrite**: the condition is
    in the write, so there is no gap between a check and the write it guards.

    **A rename is just one of the assignments.** There is no name claim to
    collide with.
    """
    body = support.body()
    held = support.memberships()
    record = _character(addressed, held)
    rev = support.revision(body, record)

    assignments = {}
    if "name" in body:
        assignments["name"] = keys.clean_label(body["name"])
    if "hero" in body:
        assignments["hero"] = (
            _node_in(record, body["hero"], "hero")["node_id"] if body["hero"] else None
        )

    try:
        updated = catalog.update_entity(KIND, record, rev, assignments)
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)
    return jsonify(updated), 200


@bp.patch("/characters/<addressed>/profile")
def write_profile(addressed: str):
    """Replace the whole bible, or merge one section onto it.

    **Two operations on one address, told apart by which key the body carries** —
    `{profile, rev}` replaces wholesale and `{patch, rev}` merges. That is how
    `docs/ENTITY_MODEL.md` already distinguishes them, so nothing about the wire
    is invented here; what it replaces is a `PUT` and a `PATCH` on the same path,
    which cannot both be PATCH. See `app_factory.CORS_METHODS` for why the verb
    is not available.

    **Sending both is a 400 rather than a guess**, the same refusal
    `PATCH /api/nodes/<id>` makes about `name` with `parent`: the two have
    different outcomes and picking one silently is how somebody's paragraph
    disappears.

    **The merge is section-level, not deep.** Sending `{"patch": {"face": {...}}}`
    replaces the whole of `face` and touches nothing else. A deep merge would make
    *removing* a field impossible without a whole-document replace, which is the
    other half of this same route — so the shallow one is the useful half of the
    pair rather than a simplification of it.
    """
    body = support.body()
    held = support.memberships()
    record = _character(addressed, held)
    rev = support.revision(body, record)

    replacing = "profile" in body
    merging = "patch" in body
    if replacing and merging:
        raise ValidationError("send profile to replace, or patch to merge, not both")
    if not replacing and not merging:
        raise ValidationError("send profile to replace, or patch to merge")

    if replacing:
        assignments = {"profile": clean_profile(body.get("profile"))}
    else:
        patch = clean_profile(body.get("patch"))
        assignments = {"profile": {**(record.get("profile") or {}), **patch}}

    try:
        updated = catalog.update_entity(KIND, record, rev, assignments)
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)
    return jsonify(updated), 200


@bp.delete("/characters/<addressed>")
def delete_character(addressed: str):
    """Remove a character. `?files=keep|delete`, and refuses while anything links it.

    **Files are kept by default and the folder is orphaned into the library
    root.** The reverse default loses media to a typo, and nothing this service
    can do to S3 is undoable.

    **The refusal is the interesting half.** A project involving this character
    and a run that used it both hold rows pointing at it, and those rows are what
    make "every run of this subject" answerable — deleting the character out from
    under them leaves two questions with wrong answers. `?force=1` is the explicit
    "yes, and drop the links".
    """
    held = support.memberships()
    record = _character(addressed, held)

    files = request.args.get("files") or "keep"
    if files not in ("keep", "delete"):
        raise ValidationError("files must be 'keep' or 'delete'")

    if request.args.get("force") not in ("1", "true"):
        projects = catalog.linked(record["id"], catalog.ENTITY_PROJECT)
        runs = catalog.linked(record["id"], catalog.ENTITY_RUN)
        if projects or runs:
            return support.structured(
                "conflict",
                f"{len(projects)} project(s) and {len(runs)} run(s) still name this "
                "character — pass ?force=1 to delete it and its links anyway",
                409,
                projects=projects,
                runs=runs,
            )

    manage.drain(g.library)
    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    manage.release(g.library, result["blob_keys"], result["sweeps"])
    return jsonify({"id": record["id"], "files": files}), 200


# ─────────────────────────── identity ───────────────────────────
#
# **There is no reference index and no `default_set`.** Which of a character's
# many pictures a generation gets shown is answered on the picture: `default` is
# the handful, a group tag like `face` narrows it, and both travel with the
# picture through a move, a copy or a rename because they are attributes of the
# node. Nothing can drift from anything, because there is only one copy.

#: What a selection asks for when nobody says otherwise.
DEFAULT_TAG = "default"

#: A selection is images. A `.json` beside them in the same folder carrying the
#: same tag is not something to hand a model.
SELECTABLE = "image"


def _identity(record: dict, tags: list[str]) -> list[dict]:
    """The character's images carrying EVERY one of `tags`, by name.

    One branch query under the character's root — the same read `counts` makes —
    filtered on tags by the listing itself.

    **Ordered by name, and that is a decision rather than a leftover.** Order
    means nothing about a character's pictures, but a payload hands
    a model `[Image1]` and `[Image2]`, so the selection needs *an* order and it
    has to be the same one twice. Name is the only property of a file that does
    not change when somebody re-uploads or re-tags it; `newest` would reshuffle a
    shoot for a reason that has nothing to do with the shoot.
    """
    listed = browse.entries(
        record["lib"],
        under=record["root"],
        depth=browse.DEPTH_ALL,
        kinds=SELECTABLE,
        tags=",".join(tags),
        raw_sort="name",
        page_size=str(browse.MAX_PAGE_SIZE),
    )
    return listed["entries"]


def _picked(record: dict, tokens: list[str]) -> list[dict]:
    """Exactly the images named, in the order they were named.

    A token is a node id or a filename, with or without its extension — the three
    things somebody has in hand when they are looking at a listing.

    **A token matching nothing is a refusal.** Asking for pictures by name and
    being handed fewer is not a selection, it is a typo, and the next thing down
    the pipe spends money on it.
    """
    listed = browse.entries(
        record["lib"], under=record["root"], depth=browse.DEPTH_ALL,
        kinds=SELECTABLE, raw_sort="name", page_size=str(browse.MAX_PAGE_SIZE),
    )["entries"]
    by_id = {entry["id"]: entry for entry in listed}
    by_name: dict[str, dict] = {}
    for entry in listed:
        by_name.setdefault(entry["name"], entry)
        by_name.setdefault(_stem(entry["name"]), entry)

    chosen, missing = [], []
    for token in tokens:
        found = by_id.get(token) or by_name.get(token) or by_name.get(_stem(token))
        if found is None:
            missing.append(token)
        else:
            chosen.append(found)
    if missing:
        raise ValidationError(
            f"{record['name']} has no image called {missing[0]!r}. "
            f"See what it has: studio character images {record['id']}")
    return chosen


def _csv(raw: str | None) -> list[str]:
    """A comma-separated query parameter as a list, blanks dropped.

    Every filter on `GET /selection` takes a list; a bare `request.args.get`
    compared whole would make `?tag=a,b` ask for a tag literally named `a,b`.
    """
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _must_match(chosen: list, record: dict, asked: str) -> None:
    """A filter that selected nothing is a refusal, not an empty selection.

    Being handed no images is not a selection, and what runs next spends money
    on it.
    """
    if not chosen:
        raise ValidationError(
            f"no image of {record['name']} carries {asked}. "
            f"See what it has: studio character images {record['id']}"
        )


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0]


def reference_nodes(refs: dict, held: dict) -> list[str]:
    """The node ids a plan's `references` block resolves to, for DISPLAY.

    A storyboard names its images the way a person writes them — a character and
    a picked list or a tag — and a board has to draw them. Resolution lives here
    because this module owns what a character's identity images are; `scenes.py`
    may not grow a second copy of the pick rules.

    **Tolerant, unlike the selection route.** That one refuses a filter matching
    nothing, because a generation must never go out with silently fewer images
    than were asked for. This one is a picture on a page: an image renamed or
    re-tagged since the plan was written should leave a gap on the board, not 500
    the scene it is part of.
    """
    found: list[str] = []
    for named in refs.get("characters") or []:
        # **A plan names a character by ID**, and nothing else: a name is a
        # label two characters may share.
        try:
            record = _character(str(named), held)
            pick, tags = _csv(refs.get("pick")), _csv(refs.get("pick_tag"))
            # The same two sources the selection route resolves, in the same
            # order, so a board draws what a submission would send.
            chosen = _picked(record, pick) if pick else _identity(record, tags or [DEFAULT_TAG])
            found += [entry["id"] for entry in chosen]
        except (ValidationError, NotFoundError, ForbiddenError) as exc:
            # Tolerated, but never in silence: a gap on the board is a thing
            # somebody has to be able to explain, and an empty list that logged
            # nothing cannot be.
            logger.warning("could not resolve references for %s: %s", named, exc)
            continue
    return found


@bp.get("/characters/<addressed>/selection")
def selection(addressed: str):
    """The ordered images a model would actually be shown, and the cap they face.

    **The one route both halves of studio must agree on**, which is why it is a
    route rather than a function in each. Slot N means "position N in the
    resolved selection"; the resolving happens here, so the CLI and the SPA
    cannot disagree about what a model was given.

    Two sources. `pick` names images; anything else is tags, and no tags at all
    means `default`. A group is a tag: `?tag=default,face` is the face images
    this character sends.

    **A filter that matches nothing is refused, never answered with an empty
    list.** Asking for images and being handed none is a typo, not a selection,
    and the next thing down the pipe spends money on it.

    **Over-cap is refused with the candidates in the body, never truncated.**
    Handing a model the first seven of eighteen silently is a shoot whose result
    nobody can explain afterwards. The refusal carries every candidate so the
    caller can choose rather than guess.
    """
    held = support.memberships()
    record = _character(addressed, held)

    tags = _csv(request.args.get("tag"))
    pick = _csv(request.args.get("pick"))

    if pick:
        source = "pick"
        chosen = _picked(record, pick)
    else:
        source = "tag" if tags else "default"
        asked = tags or [DEFAULT_TAG]
        chosen = _identity(record, asked)
        _must_match(chosen, record, " + ".join(asked))

    cap = _cap(request.args)
    if cap is not None and len(chosen) > cap:
        return support.structured(
            "over_cap",
            f"{len(chosen)} images match; the cap is {cap}",
            409,
            index=[
                {
                    "node": entry["id"],
                    "name": entry["name"],
                    "tags": entry.get("tags") or [],
                    "description": entry.get("description"),
                }
                for entry in chosen
            ],
        )

    return jsonify(
        {
            "selection": [
                {
                    "slot": slot,
                    "node": entry["id"],
                    # A person reviewing a payload has to know which picture is
                    # `[Image3]`, and a node id does not say.
                    "name": entry["name"],
                    "tags": entry.get("tags") or [],
                    "description": entry.get("description"),
                    "url": entry.get("url"),
                }
                for slot, entry in enumerate(chosen, start=1)
            ],
            "cap": cap,
            "source": source,
        }
    ), 200


def _cap(args) -> int | None:
    """The ceiling this selection is measured against, or none at all.

    `?limit=` is explicit and wins. `?engine=` is resolved against the registry,
    a real lookup rather than a prefix match: two members of one family may
    legitimately differ, and an alias resolves properly. Neither given means no
    cap, and no refusal — a caller that did
    not say what it was feeding cannot be told it fed too much, and an unknown
    engine name is the same case.
    """
    raw = args.get("limit")
    if raw not in (None, ""):
        try:
            limit = int(raw)
        except (TypeError, ValueError):
            raise ValidationError("limit must be an integer") from None
        if limit < 1:
            raise ValidationError("limit must be positive")
        return limit

    engine = args.get("engine") or ""
    return registry.reference_cap(engine) if engine else None


@bp.get("/characters/<addressed>/textblock")
def textblock(addressed: str):
    """The pasteable identity paragraph, on its own so a prompt can fetch it.

    Both keys are always present. A caller branches on `text` being empty, which
    is one rule; `raw` appearing only sometimes would be a second one.

    **The template's unfilled `<>` counts as absent**, and that decision is made
    here rather than in each client. Otherwise a character created from the
    blank template and never written up hands one caller the raw sections and
    another a literal `<>` — which is the paragraph landing in a prompt.
    """
    held = support.memberships()
    record = _character(addressed, held)
    profile = record.get("profile") or {}
    authored = (profile.get(TEXT_BLOCK) or "").strip()
    if authored.startswith("<"):
        authored = ""
    raw = {} if authored else {
        section: profile[section] for section in IDENTITY_BEARING if profile.get(section)
    }
    return jsonify({"id": record["id"], "text": authored, "raw": raw}), 200


@bp.get("/characters/<addressed>/runs")
def character_runs(addressed: str):
    """Every run that used this character, newest first.

    One `by-sk` query for the ids and one batched read for the envelopes.
    """
    held = support.memberships()
    record = _character(addressed, held)
    return jsonify({"runs": catalog.runs_for_character(record["id"]), "cursor": None}), 200


@bp.get("/characters/<addressed>/projects")
def character_projects(addressed: str):
    """Every project that involves this character.

    **The same rows `GET /api/projects` sends**, from the one builder in
    `routes/projects.py`, so the SPA draws them with the card it draws every
    other project list with.
    """
    held = support.memberships()
    record = _character(addressed, held)

    project_ids = catalog.linked(record["id"], catalog.ENTITY_PROJECT)
    found = catalog.entities_by_id(catalog.ENTITY_PROJECT, project_ids)
    return jsonify(project_routes.summary_rows(list(found.values()))), 200
