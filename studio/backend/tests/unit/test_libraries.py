"""`GET /api/libraries` — the route a client reads before it can name a library.

Every test drives a real request through `create_app()` over the moto-backed
catalog table, because the statuses are half of what is under test: "you are in
none" and "you may not have that one" are different answers, and only a response
distinguishes them.

`identity.caller_sub` is stubbed, since verifying a real RS256 signature needs a
live Cognito pool and `test_identity.py` already covers the four checks token by
token. It is `before_request` that calls it now rather than the route — see the
`signed_in` fixture below for why this module overrides `conftest`'s. The two
401 tests hand the header back to the real parsing, which refuses it before any
key is fetched.

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


@pytest.fixture(autouse=True)
def signed_in(monkeypatch):
    """Whoever the next request is from. Defaults to the seeded library's owner.

    **Overrides `conftest`'s fixture of the same name**, and the difference is
    the membership read. `conftest.SignedIn` stands in for `identity` *and*
    `catalog` on `app_factory`, which is right for a suite whose tests are not
    about who is in what — they are about listings and moves, and a static
    membership keeps them saying so. Every test in this module is about exactly
    that question: it writes rows and asserts what the hook and the route make of
    them. So only the token half is stubbed here, and `before_request` reads its
    memberships from the moto-backed table like the route does.

    `authenticated = False` hands the header back to the real `caller_sub`
    rather than raising a canned `AuthError`, so the 401 tests still exercise the
    parsing that refuses a missing or bearerless header before a key is fetched.
    """
    real_caller_sub = identity.caller_sub

    class Caller:
        sub = CATALOG_OWNER
        authenticated = True

    caller = Caller()
    monkeypatch.setattr(
        identity,
        "caller_sub",
        lambda header: caller.sub if caller.authenticated else real_caller_sub(header),
    )
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
    caller in more than one library and no header is exactly what
    `before_request` answers 400 to, so this test fails the day `/api/libraries`
    leaves `LIBRARY_UNSCOPED_PATHS`.
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


def test_no_authorization_header_is_401(catalog_table, signed_in):
    """Unstubbed, and refused before a key is ever fetched."""
    signed_in.authenticated = False

    resp = _client().get("/api/libraries")

    assert resp.status_code == 401
    assert "error" in resp.get_json()


def test_a_bearerless_authorization_header_is_401(catalog_table, signed_in):
    signed_in.authenticated = False

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


# ---------------------------------------------------------------------------
# POST /api/libraries — a fresh account making its first library
# ---------------------------------------------------------------------------


def _post(body, client=None):
    return (client or _client()).post(
        "/api/libraries", json=body, headers={"Authorization": "Bearer t"}
    )


def test_a_caller_in_no_library_can_create_one(catalog_table, signed_in):
    """The whole point: no membership, no header, and the request goes through.

    A caller in no library is refused 403 by `_resolve_library` on every scoped
    path, so this passing is what proves the POST shares the unscoped path with
    the GET. Afterwards the same caller lists exactly the library they made, as
    its owner, and its root node opens as an empty folder at `/`.
    """
    signed_in.sub = STRANGER

    resp = _post({"name": "Mine"})

    assert resp.status_code == 201
    created = resp.get_json()
    assert created["name"] == "Mine"
    assert created["role"] == "owner"
    assert created["id"].startswith("lib-")
    assert created["root"].startswith("node-")

    listed = _get().get_json()
    assert listed == [{"id": created["id"], "name": "Mine", "role": "owner"}]

    root = catalog_table.get_item(
        TableName=config.catalog_table(),
        Key={"pk": {"S": f"NODE#{created['root']}"}, "sk": {"S": "META"}},
    )["Item"]
    assert root["lib"]["S"] == created["id"]
    assert root["kind"]["S"] == "folder"
    assert root["path"]["S"] == "/"
    assert "parent_id" not in root


def test_creating_a_library_grants_nobody_else(catalog_table, signed_in):
    """The only membership written is the caller's own.

    This is the property that makes the route safe to expose where
    `add-member.sh` is not: a stranger's partition is untouched, and the seeded
    owner's list does not grow.
    """
    signed_in.sub = STRANGER
    created = _post({"name": "Mine"}).get_json()

    signed_in.sub = CATALOG_OWNER
    assert created["id"] not in [entry["id"] for entry in _get().get_json()]

    rows = catalog_table.query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": f"USER#{STRANGER}"}},
    )["Items"]
    assert [row["sk"]["S"] for row in rows] == [f"LIB#{created['id']}"]


def test_a_caller_already_in_a_library_gets_a_second(catalog_table, signed_in):
    """Nothing caps it at one. Two memberships means the header is now required
    on scoped routes — which is the existing rule, not a new one."""
    resp = _post({"name": "Another"})

    assert resp.status_code == 201
    assert len(_get().get_json()) == 2


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}, {"name": 7}, None])
def test_a_library_needs_a_name(catalog_table, signed_in, body):
    resp = _post(body)

    assert resp.status_code == 400
    assert "name" in resp.get_json()["error"]


def test_a_library_name_is_trimmed_and_bounded(catalog_table, signed_in):
    assert _post({"name": "  Padded  "}).get_json()["name"] == "Padded"
    assert _post({"name": "x" * 121}).status_code == 400
