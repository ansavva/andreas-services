"""The one authenticated route that is not about the contents of a library.

`GET /api/libraries` answers "which libraries am I in", and every other route in
this service needs that answer before it can be asked: a client names a library
in `X-Studio-Library`, and this is where the id it names comes from. So the
route is **authenticated and not library-scoped**, and that shape is the whole
point of it rather than an implementation detail — a route that required a
library to be chosen before it would say which ones exist could never be
reached first.

**That shape is one `app_factory`'s hook cannot currently express.** #351 adds a
`before_request` that resolves the caller *and* their library together, and
skips both halves for the paths in `UNAUTHENTICATED_PATHS`. This route needs
exactly one half skipped, and neither option in that set is it: listing the path
there would make it reachable with no token at all, and leaving it out would
refuse a caller who is in no library with the 403 `_resolve_library` raises —
whose remedy is to read the empty list this route exists to return. The hook
needs a second set, of paths that are authenticated but resolve no library, and
this path is its first member. Until that lands, the route identifies the caller
itself, which is also what keeps it working under `dev-up.sh` today.

**An empty list is a real answer, and always a 200.** A caller in no library is
an account somebody created and never added to one — the pool is
admin-create-only, so this is a provisioning gap rather than a mistake the
caller made. The way it gets diagnosed is by asking this route and being told
"none", which a 403 indistinguishable from "you asked for a library you are not
in" would prevent.
"""

import logging

from flask import Blueprint, jsonify, request

from studio_core.errors import NotFoundError
from studio_core.services import catalog, identity

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
    # Resolved here rather than read off `g`: the hook that will put it there
    # does not exist yet, and this is the route it must not run its library half
    # for. `caller_sub` raises `AuthError` — 401 — on a missing, malformed or
    # unverifiable token, so there is no unauthenticated path through this
    # function to leave an empty list on.
    sub = identity.caller_sub(request.headers.get("Authorization"))
    summaries = [_summary(membership) for membership in catalog.libraries_for(sub)]
    return jsonify(sorted(summaries, key=lambda entry: (entry["name"], entry["id"]))), 200


def _summary(membership: dict) -> dict:
    """One membership as this route reports it.

    `id` rather than the `lib` the catalog returns: outside `services.catalog` a
    library is a thing with an id, and the attribute name the table partitions
    on is not part of the API. `created_at` is dropped for the same reason it is
    not in #291's shape — the date a membership was granted is not something a
    picker shows.
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
