"""The one authenticated route that is not about the contents of a library.

`GET /api/libraries` answers "which libraries am I in", and every other route in
this service needs that answer before it can be asked: a client names a library
in `X-Studio-Library`, and this is where the id it names comes from. So the
route is **authenticated and not library-scoped**, and that shape is the whole
point of it rather than an implementation detail — a route that required a
library to be chosen before it would say which ones exist could never be
reached first.

**That shape is why `app_factory`'s hook carries two path sets and not one.**
`before_request` resolves the caller *and* their library together, and
`UNAUTHENTICATED_PATHS` skips both halves at once — neither answer suits this
route. Listing the path there would make it reachable with no token at all;
leaving it out would refuse a caller who is in no library with the 403
`_resolve_library` raises, whose remedy is to read the empty list this route
exists to return. So this path is the first member of `LIBRARY_UNSCOPED_PATHS`:
authenticated, about no library in particular, and reached with `g.library` set
to `None`. This route is the reason that attribute is assigned there at all
rather than left unset.

**An empty list is a real answer, and always a 200.** A caller in no library is
a fresh account — one that signed itself up and has not yet made a library, or
one somebody created and never added to one. The way it gets diagnosed is by
asking this route and being told "none", which a 403 indistinguishable from
"you asked for a library you are not in" would prevent. The remedy is the POST
below.

**`POST /api/libraries` is the one write that is not about a library the caller
is already in**, which is why it shares this unscoped path. It creates a library
holding nothing, and makes the caller its owner — and only the caller.
`scripts/add-member.sh` is still the only way into somebody *else's* library,
for the reason given there; this route cannot reach one, because the only
membership it writes names a library that did not exist until it did.
"""

import logging

from flask import Blueprint, g, jsonify

from studio_core.errors import NotFoundError, ValidationError
from studio_core.routes import support
from studio_core.services import catalog

logger = logging.getLogger(__name__)

bp = Blueprint("libraries", __name__, url_prefix="/api")


@bp.get("/libraries")
def libraries():
    """The caller's libraries, as `[{id, name, role}]`.

    One membership query plus a read per library. A `BatchGetItem` would save
    the round trips, at the cost of chunking at a hundred keys and retrying
    `UnprocessedKeys` — machinery for a list that is one entry long in practice
    and will not plausibly reach ten.

    Sorted by name because the only thing that reads this is a picker, and the
    order the table hands back is by library id, which is a UUID and therefore
    arbitrary to a human. The id breaks ties, so the order is total.
    """
    # `g.caller_sub` is `before_request`'s, and it raises `AuthError` — 401 — on
    # a missing, malformed or unverifiable token before any route runs. So there
    # is no unauthenticated path through this function to leave an empty list
    # on, and the token is verified once per request rather than twice.
    summaries = [_summary(membership) for membership in catalog.libraries_for(g.caller_sub)]
    return jsonify(sorted(summaries, key=lambda entry: (entry["name"], entry["id"]))), 200


def _summary(membership: dict) -> dict:
    """One membership as this route reports it.

    `id` rather than the `lib` the catalog returns: outside `services.catalog` a
    library is a thing with an id, and the attribute name the table partitions
    on is not part of the API. `created_at` is dropped because the date a membership
    was granted is not something a picker shows.
    """
    lib = membership["lib"]
    try:
        name = catalog.library(lib)["name"]
    except NotFoundError:
        # A membership pointing at a library record that is not there. Reported
        # rather than skipped, and named by its id: the id is what the caller
        # would put in `X-Studio-Library`, and every route authorises against
        # the same membership rows read above — so dropping the entry here would
        # leave a library that works and cannot be found. Logged because,
        # unlike a 401, this is nobody's normal Tuesday: the catalog has no
        # code that deletes a library, so it means a row was written by hand.
        logger.warning("Membership names a library with no record: %s", lib)
        name = lib
    return {"id": lib, "name": name, "role": membership["role"]}


@bp.post("/libraries")
def create_library():
    """A new, empty library with the caller as its owner. `{name}` in, 201 out.

    The body is the summary `GET /api/libraries` would report for it, plus
    `root` — the node id the library opens on, so a client can navigate
    straight into it without a second call.
    """
    name = support.body().get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("name is required")
    name = name.strip()
    if len(name) > catalog.MAX_LIBRARY_NAME:
        raise ValidationError(f"name must be at most {catalog.MAX_LIBRARY_NAME} characters")
    created = catalog.create_library(name, g.caller_sub)
    logger.info("Library %s created by %s", created["id"], g.caller_sub)
    return jsonify(created), 201
