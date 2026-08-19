"""`GET /api/libraries` — the route a client reads before it can name a library.

Every test drives a real request through `create_app()` over the moto-backed
catalog table, because the statuses are half of what is under test: "you are in
none" and "you may not have that one" are different answers, and only a response
distinguishes them.

`identity.caller_sub` is stubbed on the module the route resolves through, since
verifying a real RS256 signature needs a live Cognito pool and `test_identity.py`
already covers the four checks token by token. The unauthenticated test is the
one that does **not** stub it: a request with no `Authorization` header is
refused by header parsing, before any key is fetched, so that path is exercised
end to end for free.

The extra rows are written literally rather than through `services.catalog`, for
the reason `conftest` gives — `catalog` is the only module allowed to know these
shapes, so a fixture built from its helpers would agree with any drift in them.
"""

import pytest

from studio_core import config
from studio_core.app_factory import create_app
from studio_core.services import identity
from tests.conftest import CATALOG_LIBRARY, CATALOG_MEMBER, CATALOG_OWNER

# Second in the table, first in the response: the route sorts by name, and
# "Archive" sorting before the seeded library's "Library" is what makes that
# assertable without a third row.
OTHER_LIBRARY = "lib-0002"
OTHER_NAME = "Archive"
STRANGER = "sub-stranger"

_SEED_TIME = "2026-08-19T12:00:00.000000+00:00"


@pytest.fixture
def signed_in(monkeypatch):
    """Whoever the next request is from. Defaults to the seeded library's owner."""

    class Caller:
        sub = CATALOG_OWNER

    caller = Caller()
    monkeypatch.setattr(identity, "caller_sub", lambda header: caller.sub)
    return caller


def _client():
    return create_app().test_client()


def _get(client=None):
    """The route, with a header that the stub ignores and the real code needs."""
    return (client or _client()).get("/api/libraries", headers={"Authorization": "Bearer t"})


def _add_library(client, lib, name):
    client.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": f"LIB#{lib}"},
            "sk": {"S": "META"},
            "name": {"S": name},
            "root_node": {"S": f"node-root-{lib}"},
            "created_at": {"S": _SEED_TIME},
        },
    )


def _add_membership(client, sub, lib, role="member"):
    client.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": f"USER#{sub}"},
            "sk": {"S": f"LIB#{lib}"},
            "role": {"S": role},
            "created_at": {"S": _SEED_TIME},
        },
    )


def test_a_caller_in_two_libraries_gets_both(catalog_table, signed_in):
    """Names and roles come from two different rows, and both must arrive.

    **No `X-Studio-Library` is sent**, and that is the case to keep passing: a
    caller in more than one library and no header is exactly what #351's hook
    answers 400 to, so this test fails the day `/api/libraries` is left inside
    the library-resolving half of it.
    """
    _add_library(catalog_table, OTHER_LIBRARY, OTHER_NAME)
    _add_membership(catalog_table, CATALOG_OWNER, OTHER_LIBRARY)

    resp = _get()

    assert resp.status_code == 200
    assert resp.get_json() == [
        {"id": OTHER_LIBRARY, "name": OTHER_NAME, "role": "member"},
        {"id": CATALOG_LIBRARY, "name": "Library", "role": "owner"},
    ]


def test_a_caller_in_no_library_gets_an_empty_list(catalog_table, signed_in):
    """200 and `[]`, never 403 — this route is how you find out you have none."""
    signed_in.sub = STRANGER

    resp = _get()

    assert resp.status_code == 200
    assert resp.get_json() == []


def test_a_library_the_caller_is_not_in_is_not_listed(catalog_table, signed_in):
    """The listing is built from the caller's own memberships, not from the table."""
    signed_in.sub = CATALOG_MEMBER
    _add_library(catalog_table, OTHER_LIBRARY, OTHER_NAME)
    _add_membership(catalog_table, CATALOG_OWNER, OTHER_LIBRARY)

    resp = _get()

    assert resp.status_code == 200
    assert [entry["id"] for entry in resp.get_json()] == [CATALOG_LIBRARY]


def test_no_authorization_header_is_401(catalog_table):
    """Unstubbed, and refused before a key is ever fetched."""
    resp = _client().get("/api/libraries")

    assert resp.status_code == 401
    assert "error" in resp.get_json()


def test_a_bearerless_authorization_header_is_401(catalog_table):
    resp = _client().get("/api/libraries", headers={"Authorization": "Basic bm9wZQ=="})

    assert resp.status_code == 401


def test_a_membership_with_no_library_record_still_names_the_id(catalog_table, signed_in):
    """A membership row and no library row: listed under its id, not dropped.

    Dropping it would hide a library that every other route still authorises
    against — usable and unfindable — and 404ing the whole request would hide
    the caller's real libraries behind one hand-written row.
    """
    _add_membership(catalog_table, CATALOG_OWNER, "lib-dangling")

    resp = _get()

    assert resp.status_code == 200
    assert {"id": "lib-dangling", "name": "lib-dangling", "role": "member"} in resp.get_json()
