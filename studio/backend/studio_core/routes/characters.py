"""Characters: who a subject is, and which images say so.

A character used to be a folder with a YAML file in it. It is a row now — `CHAR#
<char_id>` / `META`, with a `LIB#<lib>` / `CHARSLUG#<slug>` claim beside it — and
the four consequences of that are the whole reason this module exists:

* **A rename is one `PATCH`.** Four writes in one transaction: drop the old
  claim, take the new one, bump the record, rename the root folder. Zero objects
  copied, zero records rewritten, every reference untouched. It used to be a
  `PATCH` per slugged basename across four pools plus a rewrite pass over every
  run document that had cited the old path.
* **Reference order and group are attributes**, so `curate renumber` has nothing
  to maintain and `curate regroup` moves no bytes.
* **Descriptions are rows**, so writing twelve of them is one transaction rather
  than twelve rewrites of one document racing each other's `updated_at`.
* **"Which projects involve this character" has an answer**, and "every run that
  used it" is one query rather than a walk over every run folder in the library.

## The two things this module decides rather than stores

**The profile schema.** `profile` is the whole of the old `profile.yaml` minus
the three fields promoted to real columns (`name` → `slug`, `display_name`,
`fictional`) and the two that became rows (`references:`, and `default_set`,
which stays on the record as a short ordered list of node ids because it is read
on every generation). The sections are validated here — nowhere else in the
service has an opinion about the shape of a bible.

**What a model will actually be shown.** `GET /api/characters/<id>/selection` is
a route rather than a function in each half of studio precisely so the CLI and
the SPA cannot disagree about it, and so the over-cap refusal happens in one
place. Slot N still means "position N in the resolved selection"; what moved is
where the resolving happens.

## Hard rule #1 lives here too

No character is named anywhere in this repository, and that includes the S3 keys
this module's uploads produce: a reference image is
`characters/<char_id>/<node_id>.<ext>`, so a listing of the media bucket is a
list of UUIDs. The old layout wrote the slug into every key, which made a bucket
listing a list of character names — the rule broken in the one place nobody was
reading.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, ValidationError
from studio_core.routes import support
from studio_core.services import catalog, keys, layout

logger = logging.getLogger(__name__)

bp = Blueprint("characters", __name__, url_prefix="/api")

KIND = catalog.ENTITY_CHARACTER

# The bible's sections, as the API validates them. Seven maps and one paragraph
# — the shape `profile.yaml` already had, minus what was promoted to a column.
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

# The reference caps the engines impose, by engine name. Consulted only when a
# request names one; `?limit=` is the explicit form and wins.
#
# **A cap is refused rather than applied**, which is the behaviour being moved
# here rather than invented: silently handing a model the first seven of
# eighteen references is a shoot whose result nobody can explain, so the request
# fails and the whole index comes back in the body so the caller can choose.
ENGINE_CAPS = {"kling": 7, "seedance": 9, "nano-banana": 14}


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


@bp.get("/characters")
def list_characters():
    """Every character in the library, newest edit first when `?q=` is absent.

    **One query for the claims, one batched read for the records, one batched
    read for the heroes.** `counts.references` is one query per character, and
    that is the honest cost of showing it — the alternative is a counter on the
    record that every attach and detach has to keep in step, which is the class of
    drift the claim rows deliberately avoid.

    `?q=` filters on slug and display name, in memory. A library holds tens of
    characters, not thousands; an index for this would be a second thing to keep
    correct for a substring match a client could do itself.
    """
    held = support.memberships()
    support.member_of(g.library, held)

    records = catalog.entities_in(g.library, KIND)
    query = (request.args.get("q") or "").strip().lower()
    if query:
        records = [
            record
            for record in records
            if query in record["slug"].lower()
            or query in (record.get("display_name") or "").lower()
        ]

    heroes = catalog.records([record["hero"] for record in records if record.get("hero")])
    listed = [
        {
            "id": record["id"],
            "slug": record["slug"],
            "display_name": record.get("display_name"),
            "fictional": record.get("fictional"),
            "hero": _hero(record, heroes),
            "counts": {"references": len(catalog.references(record["id"]))},
            "updated": record.get("updated"),
        }
        for record in records
    ]
    listed.sort(key=lambda entry: entry["slug"])
    return jsonify(listed), 200


@bp.post("/characters")
def create_character():
    """A character, its claim, its root folder and its four pools — one write.

    **201, and the whole of it exists or none of it does.** Twelve items in one
    `TransactWriteItems`; a create that timed out is a create a person can simply
    repeat.

    A slug already claimed is **409** carrying the machine-readable code, because
    the client has to act on it — offer a different slug — and matching on prose
    is how that stops working.
    """
    body = support.body()
    held = support.memberships()
    support.member_of(g.library, held)

    slug = keys.clean_slug(body.get("slug"))
    display_name = body.get("display_name")
    if display_name is not None and not isinstance(display_name, str):
        raise ValidationError("display_name must be a string")
    fictional = body.get("fictional")
    if not isinstance(fictional, bool):
        raise ValidationError("fictional is required and must be true or false")

    root = catalog.library(g.library)["root_node"]
    try:
        record = catalog.create_character(
            g.library,
            root,
            slug=slug,
            display_name=display_name,
            fictional=fictional,
            profile=clean_profile(body.get("profile")),
            layout=layout.CHARACTER_LAYOUT,
        )
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)

    return jsonify(record), 201, {"Location": f"/api/characters/{record['id']}"}


@bp.get("/characters/<addressed>")
def get_character(addressed: str):
    """The full record, `profile` included. `<id>` may be `slug:<slug>`."""
    held = support.memberships()
    record = _character(addressed, held)
    heroes = catalog.records([record["hero"]] if record.get("hero") else [])
    return jsonify(
        {
            **record,
            "hero_url": _hero(record, heroes),
            "counts": {"references": len(catalog.references(record["id"]))},
        }
    ), 200


@bp.patch("/characters/<addressed>")
def update_character(addressed: str):
    """Rename, retitle, re-hero — under a `rev`.

    **A stale `rev` is a 409 and never a silent overwrite**, which closes a window
    that was genuinely open: the old `write_profile` re-read the node's
    `updated_at` and refused if it had moved, and that is a check and a write with
    a gap between them.

    A slug change is four more writes in the same transaction, so a rename that
    collides leaves the display name unchanged too — the request either happened
    or did not.
    """
    body = support.body()
    held = support.memberships()
    record = _character(addressed, held)
    rev = support.revision(body, record)

    assignments = {}
    if "display_name" in body:
        if not isinstance(body["display_name"], str) or not body["display_name"]:
            raise ValidationError("display_name must be a non-empty string")
        assignments["display_name"] = body["display_name"]
    if "fictional" in body:
        if not isinstance(body["fictional"], bool):
            raise ValidationError("fictional must be true or false")
        assignments["fictional"] = body["fictional"]
    if "hero" in body:
        assignments["hero"] = (
            _node_in(record, body["hero"], "hero")["node_id"] if body["hero"] else None
        )

    slug = keys.clean_slug(body["slug"]) if body.get("slug") else None
    try:
        updated = catalog.update_entity(KIND, record, rev, assignments, slug=slug)
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
        assignments = {
            "profile": clean_profile(body.get("profile")),
            "schema_version": catalog.PROFILE_SCHEMA_VERSION,
        }
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

    result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
    if result["blob_keys"]:
        s3.delete(result["blob_keys"])
    return jsonify({"id": record["id"], "files": files}), 200


# ─────────────────────────── references ───────────────────────────


def _with_files(entries: list[dict]) -> tuple[list[dict], dict]:
    """Reference rows with their file's own description and tags folded in.

    **Read before the filtering rather than after it**, which is the one thing
    that had to move: `?tag=` selects on tags, tags are the file's now, so the
    files have to be in hand before a subset can be chosen. It costs the same
    round trip the route already spent on the chosen subset — a `BatchGetItem`
    over one character's references, tens of items.
    """
    nodes = catalog.records([entry["node"] for entry in entries])
    folded = [
        {
            **entry,
            "description": nodes.get(entry["node"], {}).get("description"),
            "tags": nodes.get(entry["node"], {}).get("tags") or [],
        }
        for entry in entries
    ]
    return folded, nodes


def _reference_view(entry: dict, nodes: dict[str, dict], default_set: list) -> dict:
    """One entry, with what the set knows about it and what the file knows.

    **`description` and `tags` come off the NODE; `group` and `order` off the
    row.** The split is the difference between a fact about the picture and a
    fact about this character's set of them: "head and shoulders in full profile"
    is true of the file wherever it sits, while "this is a face reference, third"
    only means anything inside one character's index.

    They were both on the row until now, which cost exactly what it sounds like:
    an image described as a reference had a description, the same image sitting
    in `corpus/` had none, and twelve files in this library's `reference/`
    folders with no row had none either.
    """
    node = nodes.get(entry["node"]) or {}
    view = {
        "node": entry["node"],
        "group": entry.get("group"),
        "order": entry.get("order"),
        "description": node.get("description"),
        "tags": node.get("tags") or [],
        "default": entry["node"] in default_set,
    }
    if node:
        view["file"] = {
            "name": node["name"],
            "size": node.get("size"),
            "content_type": node.get("content_type"),
            "url": s3.presign(node["blob_key"]) if node.get("blob_key") else None,
        }
    return view


@bp.get("/characters/<addressed>/references")
def list_references(addressed: str):
    """The reference index, grouped and ordered, each entry with its file.

    **One query on `CHAR#<id>` is the whole index**, where it used to be a listing
    of four folders plus a parse of the bible's `references:` map — two
    descriptions of one thing, keyed on the very basename `curate renumber` kept
    changing, which is why they went out of step.

    A node a `REF#` row names that no longer exists is reported without a `file`
    rather than dropped: the row is the attachment and losing it silently is how
    an index quietly shrinks.
    """
    held = support.memberships()
    record = _character(addressed, held)

    entries = catalog.references(record["id"])
    group = request.args.get("group")
    if group:
        entries = [entry for entry in entries if entry.get("group") == group]

    nodes = catalog.records([entry["node"] for entry in entries])
    default_set = record.get("default_set") or []

    grouped: dict[str, list] = {}
    for entry in entries:
        grouped.setdefault(entry.get("group") or "", []).append(
            _reference_view(entry, nodes, default_set)
        )

    counts: dict[str, int] = {}
    for entry in catalog.references(record["id"]):
        counts[entry.get("group") or ""] = counts.get(entry.get("group") or "", 0) + 1

    return jsonify({"groups": grouped, "counts": counts}), 200


@bp.post("/characters/<addressed>/references")
def attach_reference(addressed: str):
    """Mark an existing node as identity. **No bytes move and nothing is copied.**

    Two steps, and always were: the bytes arrive, then a person decides they are
    identity (hard rule #2b). What changed is that the second step is a row rather
    than a file move plus a renumbering plus a document rewrite.

    `after` places the entry between two existing ones by taking the midpoint of
    their `order` values, so one write inserts and the neighbours are untouched.
    """
    body = support.body()
    held = support.memberships()
    record = _character(addressed, held)

    node_id = body.get("node")
    if not node_id:
        raise ValidationError("node is required")
    node = _node_in(record, node_id, "node")
    if node["kind"] != catalog.KIND_FILE:
        raise ValidationError("a folder cannot be a reference")

    group = body.get("group")
    if not isinstance(group, str) or not group:
        raise ValidationError("group is required")
    tags = body.get("tags")
    if tags is not None and not isinstance(tags, list):
        raise ValidationError("tags must be a list")

    try:
        entry = catalog.attach_reference(
            record["id"],
            record["lib"],
            node_id,
            group=group,
            description=body.get("description"),
            tags=tags,
            after=body.get("after"),
        )
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)

    return jsonify(
        _reference_view(entry, {node_id: node}, record.get("default_set") or [])
    ), 201


@bp.patch("/characters/<addressed>/references/<node_id>")
def update_reference(addressed: str, node_id: str):
    """Regroup, redescribe, retag or reorder one entry. One row, no objects."""
    body = support.body()
    held = support.memberships()
    record = _character(addressed, held)

    changes = {field: body[field] for field in ("group", "description", "tags", "order")
               if field in body}
    if "after" in body:
        changes["after"] = body["after"]
    entry = catalog.update_reference(record["id"], record["lib"], node_id, changes)

    nodes = catalog.records([node_id])
    return jsonify(_reference_view(entry, nodes, record.get("default_set") or [])), 200


@bp.patch("/characters/<addressed>/references")
def replace_references(addressed: str):
    """Describe or reorder many entries in one transaction.

    This is `describe-refs` and `sync-refs`. Twelve descriptions used to be twelve
    rewrites of one YAML document, each re-reading an `updated_at` and refusing if
    it had moved — writing them concurrently was a conflict dance rather than a
    write.
    """
    body = support.body()
    held = support.memberships()
    record = _character(addressed, held)

    entries = body.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValidationError("entries must be a non-empty list")
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("node"):
            raise ValidationError("every entry needs a node")
        _node_in(record, entry["node"], "node")

    written = catalog.put_references(record["id"], record["lib"], entries)
    nodes = catalog.records([entry["node"] for entry in written])
    default_set = record.get("default_set") or []
    return jsonify(
        {"entries": [_reference_view(entry, nodes, default_set) for entry in written]}
    ), 200


@bp.delete("/characters/<addressed>/references/<node_id>")
def detach_reference(addressed: str, node_id: str):
    """Stop calling a node identity. **The file stays exactly where it is.**"""
    held = support.memberships()
    record = _character(addressed, held)
    catalog.detach_reference(record["id"], node_id)
    return jsonify({"node": node_id, "detached": True}), 200


@bp.patch("/characters/<addressed>/default-set")
def set_default_set(addressed: str):
    """The ordered handful a generation reaches for when nothing else is asked.

    On the record rather than as a flag on the `REF#` rows, because it is small,
    **ordered**, and read on every generation — three properties a set of flags
    spread over forty rows has none of.
    """
    body = support.body()
    held = support.memberships()
    record = _character(addressed, held)
    rev = support.revision(body, record)

    nodes = body.get("nodes")
    if not isinstance(nodes, list):
        raise ValidationError("nodes must be a list")
    for node_id in nodes:
        _node_in(record, node_id, "nodes")

    try:
        updated = catalog.update_entity(KIND, record, rev, {"default_set": nodes})
    except ConflictError as conflict:
        return support.structured("conflict", str(conflict), 409)
    return jsonify({"id": record["id"], "default_set": nodes, "rev": updated["rev"]}), 200


@bp.get("/characters/<addressed>/selection")
def selection(addressed: str):
    """The ordered nodes a model would actually be shown, and the cap they face.

    **The one route both halves of studio must agree on**, which is why it is a
    route rather than a function in each. Slot N means "position N in the
    resolved selection" exactly as it always did; what moved is where the
    resolving happens, so the CLI and the SPA cannot disagree about what a model
    was given.

    Three sources, in the order they are asked for: an explicit `tag`, an
    explicit `pick` (a group), and otherwise the `default_set`. A character with
    no default set and no filter falls through to every reference it has, which
    is what makes the cap refusal below reachable rather than theoretical.

    **Over-cap is refused with the index in the body, never truncated.** Handing a
    model the first seven of eighteen references silently is a shoot whose result
    nobody can explain afterwards. The refusal carries every candidate so the
    caller can choose rather than guess.
    """
    held = support.memberships()
    record = _character(addressed, held)
    entries, nodes = _with_files(catalog.references(record["id"]))

    tag = request.args.get("tag")
    pick = request.args.get("pick") or request.args.get("group")
    if tag:
        source = "tag"
        chosen = [entry for entry in entries if tag in (entry.get("tags") or [])]
    elif pick:
        source = "group"
        chosen = [entry for entry in entries if entry.get("group") == pick]
    elif record.get("default_set"):
        source = "default"
        order = {node_id: index for index, node_id in enumerate(record["default_set"])}
        chosen = sorted(
            [entry for entry in entries if entry["node"] in order],
            key=lambda entry: order[entry["node"]],
        )
    else:
        source = "all"
        chosen = entries

    cap = _cap(request.args)
    if cap is not None and len(chosen) > cap:
        return support.structured(
            "over_cap",
            f"{len(chosen)} references match; the cap is {cap}",
            409,
            index=[
                {
                    "node": entry["node"],
                    "group": entry.get("group"),
                    "description": entry.get("description"),
                    "name": nodes.get(entry["node"], {}).get("name"),
                }
                for entry in chosen
            ],
        )

    return jsonify(
        {
            "selection": [
                {
                    "slot": slot,
                    "node": entry["node"],
                    "group": entry.get("group"),
                    "description": entry.get("description"),
                    "url": (
                        s3.presign(nodes[entry["node"]]["blob_key"])
                        if nodes.get(entry["node"], {}).get("blob_key")
                        else None
                    ),
                }
                for slot, entry in enumerate(chosen, start=1)
            ],
            "cap": cap,
            "source": source,
        }
    ), 200


def _cap(args) -> int | None:
    """The ceiling this selection is measured against, or none at all.

    `?limit=` is explicit and wins. `?engine=` looks the engine up, matching on a
    prefix because the registry spells a family several ways (`nano-banana-pro`,
    `nano-banana-2`) and the cap is a property of the family. Neither given means
    no cap, and no refusal — a caller that did not say what it was feeding cannot
    be told it fed too much.
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
    for family, cap in ENGINE_CAPS.items():
        if engine.startswith(family):
            return cap
    return None


@bp.get("/characters/<addressed>/textblock")
def textblock(addressed: str):
    """The pasteable identity paragraph, on its own so a prompt can fetch it.

    **`raw` is the half that was documented and never built.** The CLI has always
    read `found["raw"]` for the un-authored case and this route has always sent
    `{id, text}` alone, so `studio character textblock` on a character without a
    block printed `{}` followed by instructions to compress it. Only the authored
    path had a test.

    Both keys are always present. A caller branches on `text` being empty, which
    is one rule; `raw` appearing only sometimes would be a second one, and the
    client that got it wrong is the reason this route now states both.

    **The template's unfilled `<>` counts as absent**, and that decision is made
    here rather than in each client. The CLI already skipped a block starting
    `<`; the SPA does not, so a character created from the blank template and
    never written up would have handed one caller the raw sections and the other
    a literal `<>` — which is the paragraph landing in a prompt.
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

    `runs find --character` was a walk over every project, every run folder and
    three JSON documents each. It is one `by-sk` query for the ids and one batched
    read for the envelopes.
    """
    held = support.memberships()
    record = _character(addressed, held)
    return jsonify({"runs": catalog.runs_for_character(record["id"]), "cursor": None}), 200


@bp.get("/characters/<addressed>/projects")
def character_projects(addressed: str):
    """Every project that involves this character — a question with no answer before."""
    held = support.memberships()
    record = _character(addressed, held)

    project_ids = catalog.linked(record["id"], catalog.ENTITY_PROJECT)
    found = catalog.entities_by_id(catalog.ENTITY_PROJECT, project_ids)
    return jsonify(
        [
            {"id": project["id"], "slug": project["slug"], "title": project.get("title")}
            for project in found.values()
        ]
    ), 200
