"""What every route module needs before it can answer: who is calling, and a view.

**One copy, because the alternative is seven.** The entity model added six route
modules beside `nodes.py`, and each of them needs the same four things: the JSON
body, the caller's memberships, the refusal when a record's `lib` is not one of
them, and the node view that keeps `blob_key` and `path` inside the service. An
authorisation check a route can forget is one a route will eventually forget, and
the route that forgets is the one that writes.

## The rules these hold, stated once

**Every response is membership-checked against the record's own `lib`.** Not
against the id the caller named, and not against the library the request
asserted — the record itself says which library it belongs to, and that is the
value checked. A node id and an entity id are both v4 UUIDs, so this is not a
guard against enumeration; it is the guard against a *shared* id, which is the
realistic case the moment a library has more than one member and somebody pastes
a link.

**A missing record is 404 before the membership check can run**, because the
record is what names the library. Deliberate, and cheap: an id nobody was given
cannot be guessed, so the difference between "no such thing" and "not yours" is
information an attacker has no way to reach.

**`blob_key` never leaves, and `_view` is an allowlist rather than a `pop`.** A
denylist would leak the next internal attribute anybody adds to a record, and it
would leak it on the day it was added rather than on the day someone noticed.
Hand a client a blob key and someone will split it on `/`, and the coupling the
catalog was built to remove comes straight back.

## Why two error shapes exist

Almost every failure in this service is `{"error": "<sentence>"}`, raised as a
domain error and turned into a status by `app_factory`. Three are not:
`over_cap`, `invalid_binding` and the entity `conflict` carry a machine-readable
code in `error` and the sentence in `message`, because a client has to *act* on
them — re-read and retry, drop a URL, or show a different form — and matching on
prose is how that stops working. `structured` below is the one place that shape
is built.
"""

import logging

from flask import g, jsonify, request

from studio_core.clients.aws import s3
from studio_core.errors import ForbiddenError, ValidationError
from studio_core.services import catalog, storyboard

logger = logging.getLogger(__name__)

# What a node looks like to a client, and the entire list of it.
#
# `blob_key` is absent for the reason in the module docstring. `path` is absent
# for a different one: it is a materialised list of ancestor ids that exists so a
# subtree can be read with one query, it is rebuilt by a move, and a client that
# consumed it would be depending on an index this service reserves the right to
# rebuild. `parent_id` is the authoritative answer to the same question and is
# here.
#
# `entity` is here and `reel` is not, and the asymmetry is deliberate. `entity`
# is the reverse pointer a listing needs to draw a character card instead of a
# folder icon. `reel` is a GSI key whose value is the library id the row already
# reports as `lib` — a second copy of one string, meaningful only to the index.
VIEW_FIELDS = (
    "lib",
    "parent_id",
    "name",
    "kind",
    "size",
    "content_type",
    # **The MD5 of the bytes, which is what an ETag is here.** Every upload this
    # API signs is a single PUT — `max_upload_bytes` is S3's own ceiling and
    # there is no multipart grant — so the ETag S3 returns is the content hash
    # rather than the hash-of-hashes a multipart upload produces.
    #
    # Served because `studio curate dedupe` was DOWNLOADING every same-size
    # candidate to compute exactly this, over HTTPS, out of the bucket: hashing a
    # forty-image pool to find no duplicates was forty downloads. It is a
    # comparison of two served values now.
    "checksum",
    "entity",
    # What the file shows, and how it is selected. On the node rather than on a
    # `REF#` row: a description is a fact about the picture, true whether or not
    # anybody made it a character's reference. See `catalog.describe_node`.
    "description",
    "tags",
    "created_at",
    "updated_at",
)


def body() -> dict:
    """The JSON body, or an empty dict.

    `silent=True` so a malformed body surfaces as the missing-field
    `ValidationError` a route raises rather than Flask's generic parse failure —
    a 400 naming the field beats a 400 naming nothing.
    """
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def memberships() -> dict[str, str]:
    """The libraries the caller is in, and the role each membership carries.

    `g.caller_sub` is `before_request`'s, which raises `AuthError` — 401 — on a
    missing, malformed or unverifiable token, so there is no unauthenticated path
    past this line and the token is verified once per request.

    A mapping rather than a list of ids, because `transfer` needs the role and
    every other route needs only the key — `lib in memberships()` reads the same
    either way. One read answers both questions.
    """
    return {
        membership["lib"]: membership["role"]
        for membership in catalog.libraries_for(g.caller_sub)
    }


def member_of(lib: str, held: dict[str, str]) -> None:
    """Refuse unless the caller is in the library the record says it belongs to."""
    if lib not in held:
        raise ForbiddenError(f"You are not a member of {lib}.")


def owner_of(lib: str, held: dict[str, str]) -> None:
    """Refuse unless the caller *owns* this library.

    The only place in the API where a role is read at all. Everywhere else
    membership is the whole of authorisation, because a library is a shared
    workspace and its members are its editors. A transfer is the exception on
    purpose: it changes who can reach a subtree, so it is not something one
    library's member gets to do to another library.

    Two messages, because they are two situations. A non-member is told what
    every other route tells them; a member who is not an owner is told the thing
    they could not otherwise work out.
    """
    member_of(lib, held)
    if held[lib] != catalog.ROLE_OWNER:
        raise ForbiddenError(f"You must be an owner of {lib} to transfer in or out of it.")


def view(record: dict, owner: dict | None = None) -> dict:
    """One node record as this API reports it.

    `id` rather than `node_id`, matching `/api/libraries`: outside
    `services.catalog` a node is a thing with an id. Absent attributes are
    dropped rather than sent as null — a folder has no `size` and no
    `content_type`, and "the key is not there" is the same thing the catalog
    stores and one fewer state for a client to handle.

    **`owner` is passed in, never resolved here**, and that is the whole reason
    the parameter exists. Deriving it per row would be a batched read per
    thumbnail; a folder listing resolves it once for the parent and hands the
    same answer to every child, because every child of one folder has the same
    owner unless it is an entity root itself.
    """
    reported = {"id": record["node_id"]}
    reported.update(
        {field: record[field] for field in VIEW_FIELDS if record.get(field) is not None}
    )
    if owner is not None:
        reported["owner"] = owner
    return reported


def assets(node_ids: list[str]) -> list[dict]:
    """The nodes a record *points at*, expanded into what a page can draw.

    **Not `view`, and the difference is the whole reason this is separate.**
    `view` reports a node addressed by its own id — `GET /api/nodes/<id>` — so it
    says `id`. This reports a **pointer** to a node held by some other record: a
    run's output, a run's binding, a scene's cut. Everything that hands out such
    a pointer calls it `node` — `thumb`, a character's references, the reply to
    `POST /api/runs/<id>/outputs` — and both halves of studio read that name.

    They diverged once, in `runs.py`, which said `id`. The cost was not a naming
    quibble: the SPA read `node`, got `undefined`, and every output tile and
    every binding tile on a run page navigated to `/o/undefined`. One expansion,
    here, so there is nothing left to diverge from.

    A node the catalog cannot find is still reported, as its id alone. It is the
    honest answer — the record does point at it — and it keeps a run whose output
    was deleted openable instead of 404.
    """
    found = catalog.records(node_ids)
    return [asset(node_id, found.get(node_id)) for node_id in node_ids]


def asset(node_id: str, record: dict | None = None) -> dict:
    """One such pointer. `record` saves a read when the caller already has it."""
    if record is None:
        record = catalog.records([node_id]).get(node_id)
    if record is None:
        return {"node": node_id}
    return {
        "node": node_id,
        "name": record["name"],
        "size": record.get("size"),
        "content_type": record.get("content_type"),
        "url": s3.presign(record["blob_key"]) if record.get("blob_key") else None,
    }


def output_node(stored) -> str | None:
    """The node id inside a stored `output`, whichever of the two shapes it is.

    A scene and a movie each have exactly one cut, stored as a pointer —
    `{"node": <id>}` — plus whatever the encoder recorded about the file.
    `assemble` writes the probe alongside it; this service stores that and never
    reads it, because how the video was made is the CLI's business.

    **A bare id is still read**, because that is the shape
    `POST /api/{scenes,movies}/<id>/output` wrote before it wrote a pointer, and
    it is what every row created up to then holds. Normalising on the way out
    beats migrating: there was one writer of the old shape and it now writes the
    new one.
    """
    if isinstance(stored, str):
        return stored or None
    if isinstance(stored, dict):
        return stored.get("node")
    return None


def with_output(record: dict) -> dict:
    """One record with its `output` expanded from a stored pointer to a drawable one.

    What is stored says which node; what is reported adds the name, size, content
    type and signed URL, because a page that cannot draw the cut cannot show the
    scene or the movie.

    The API used to report the pointer unexpanded and both readers broke on it,
    differently: the SPA drew a `<video>` with no `src`, and the CLI's
    `scene_output_node` did `(record.get("output") or {}).get("node")` against
    what was then a bare string.
    """
    stored = record.get("output")
    node_id = output_node(stored)
    # `cuts` is expanded whether or not there is a current output: a scene can
    # hold earlier cuts and no current one if the latest assemble failed, and
    # returning early would hide exactly the history somebody is looking for.
    cuts = [{**cut, **asset(cut["node"])}
            for cut in (record.get("cuts") or []) if cut.get("node")]
    if not node_id:
        return {**record, "cuts": cuts} if cuts else record
    stored = {"node": node_id} if isinstance(stored, str) else stored
    out = {**record, "output": {**stored, **asset(node_id)}}
    return {**out, "cuts": cuts} if cuts else out


def keep_cut(record: dict, node_id: str | None) -> list[dict]:
    """The cuts this scene has been assembled into before the current one.

    **The implementation moved to `services/storyboard.py` and the name stayed
    here.** The assemble that displaces a cut runs in the render worker now, and
    a worker has no Flask request — so a pure function it needs could not go on
    living in a route module. Every route that wrote a cut still calls this.
    """
    return storyboard.keep_cut(record, node_id)


def structured(code: str, message: str, status: int, **extra):
    """A failure a client has to branch on, rather than one it only shows.

    Returned rather than raised, because the body carries fields no exception
    type has room for — `over_cap` sends the whole index back so the UI can show
    what it would have had to drop.
    """
    return jsonify({"error": code, "message": message, **extra}), status


def entity_at(kind: str, lib: str, addressed: str, held: dict[str, str]) -> dict:
    """One entity by id, membership-checked.

    **There was a second address, `slug:<slug>`, and it is gone with slugs.** It
    existed for the CLI, where a person typed a name rather than pasting a UUID.
    A name is a free-text label now and two entities may share one, so resolving
    a name would mean picking between them — which is not something an address
    may do.

    An id is resolved globally and then checked, because an id is shareable and a
    caller may hold one that is not theirs. `lib` is what that check is against.
    """
    record = catalog.entity(kind, addressed)
    member_of(record["lib"], held)
    return record


def node_at(node_id: str | None, held: dict[str, str]) -> dict:
    """One node by id, membership-checked against its own library.

    A missing id is a 400 rather than a 404: the request named nothing, which is
    a different mistake from naming something that is not there.
    """
    if not node_id:
        raise ValidationError("node is required")
    record = catalog.node(node_id)
    member_of(record["lib"], held)
    return record


def revision(payload: dict, record: dict) -> int:
    """The `rev` a mutating request must carry.

    **Required rather than defaulted to the current value**, and the refusal is
    the point: a client that omits it is a client that did not read before
    writing, and defaulting would turn every one of those into a silent
    last-writer-wins over somebody else's edit.
    """
    rev = payload.get("rev")
    if not isinstance(rev, int) or isinstance(rev, bool):
        raise ValidationError(f"rev is required — the record is at rev {record['rev']}")
    return rev


def string_list(value, label: str) -> list[str]:
    """A non-empty list of non-empty strings, or a refusal naming the field."""
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{label} must be a non-empty list")
    for entry in value:
        if not isinstance(entry, str) or not entry:
            raise ValidationError(f"every entry in {label} must be a string")
    return value


def holders(entity_id: str, holder_kind: str) -> list[dict]:
    """Everything of one kind that points at this entity — the way back up.

    One `by-sk` query plus a batched read, which is only possible because the
    relationship is an edge row keyed on this entity's id. It is the answer to
    "which scene used this run" and "which movie cuts this scene", and both were
    unanswerable at any price until those edges existed: the run lived in a
    shot's attribute and the scenes lived in a JSON list, and no index can see
    into either.

    Deliberately thin — an id and a name are what a link needs to be drawn. It
    carried a `slug` and a `title`, which were two names for one thing.
    """
    found = catalog.entities_by_id(holder_kind, catalog.linked(entity_id, holder_kind))
    return sorted(
        ({"id": record["id"], "name": record.get("name")} for record in found.values()),
        # By name, then by id — stable, because two may now share a name.
        key=lambda entry: ((entry["name"] or "").lower(), entry["id"]),
    )
