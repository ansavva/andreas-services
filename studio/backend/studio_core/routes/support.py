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

from studio_core.errors import ForbiddenError, ValidationError
from studio_core.services import catalog

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
    "entity",
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


def structured(code: str, message: str, status: int, **extra):
    """A failure a client has to branch on, rather than one it only shows.

    Returned rather than raised, because the body carries fields no exception
    type has room for — `over_cap` sends the whole index back so the UI can show
    what it would have had to drop.
    """
    return jsonify({"error": code, "message": message, **extra}), status


def entity_at(kind: str, lib: str, addressed: str, held: dict[str, str]) -> dict:
    """One entity by id, or by `slug:<slug>` — membership-checked either way.

    **`slug:` addressing exists for the CLI**, where a person types a name and
    the alternative is asking them to paste a UUID. The SPA always holds an id.
    Prefixing rather than a separate route keeps `<id>` one path segment, so
    every entity route reads the same and none of them has a second handler that
    could drift.

    A slug is resolved inside the library the request already resolved, which is
    the only library it could mean; an id is resolved globally and then checked,
    because an id is shareable and a caller may hold one that is not theirs.
    """
    if addressed and addressed.startswith("slug:"):
        record = catalog.entity_by_slug(lib, kind, addressed[len("slug:") :])
    else:
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
