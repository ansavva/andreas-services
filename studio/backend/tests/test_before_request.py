"""The hook that decides who is calling and which library they are calling about.

Every test here drives a real request through `create_app()`, because what is
under test is a `before_request` — the ordering, the skips and the statuses are
properties of the request cycle and not of any function called inside it.

Two halves are stubbed, for two different reasons. `identity.caller_sub` is
replaced throughout by the suite-wide `signed_in` fixture: verifying a real
RS256 signature needs a live Cognito pool, and the four checks it performs are
already covered token by token in `test_identity.py`. `catalog.libraries_for` is
**not** stubbed in the membership tests — `real_catalog` puts the real module
back over a moto table, because "is this caller in that library" is the question
the hook exists to ask and a stubbed answer would assert nothing about it.
"""

import pytest
from flask import g, jsonify

from studio_core import app_factory, config
from studio_core.app_factory import create_app
from studio_core.services import catalog
from tests.conftest import CATALOG_LIBRARY, CATALOG_MEMBER, CATALOG_OWNER

OTHER_LIBRARY = "lib-0002"
STRANGER = "sub-stranger"


class Unreadable:
    """A catalog that fails loudly if anything asks it a question.

    Stands in for `services.catalog` on the paths that must not reach it at all.
    Asserting the *absence* of a read is the only way to test a skip: a route
    that resolved a library it did not need would still answer 200, and the cost
    would be a DynamoDB query per health check for as long as nobody noticed.
    """

    def libraries_for(self, sub):
        raise AssertionError("the catalog must not be read on this path")


def _client():
    """A client over an app with one extra route that reports what `g` holds.

    The probe is what makes the happy path assertable: a 200 from `/api/tree`
    would prove the hook did not refuse the request, and nothing at all about
    whether it resolved the right caller into the right library.
    """
    app = create_app()

    @app.get("/api/_probe")
    def _probe():
        return jsonify({"sub": g.caller_sub, "library": g.library}), 200

    return app.test_client()


@pytest.fixture
def real_catalog(monkeypatch, signed_in, catalog_table):
    """The real `services.catalog`, over the moto-backed table.

    Undoes half of the suite-wide `signed_in` stub — the membership half — and
    leaves the identity half in place. Returns the DynamoDB client so a test can
    seed the extra rows its case needs.
    """
    monkeypatch.setattr(app_factory, "catalog", catalog)
    return catalog_table


def _add_membership(client, sub, lib):
    """One `USER#<sub>` / `LIB#<lib>` row, written literally.

    Literally for the same reason `conftest`'s seed items are: `services.catalog`
    is the only module allowed to know these shapes, so building the fixture with
    its own helpers would agree with any drift in them.
    """
    client.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": f"USER#{sub}"},
            "sk": {"S": f"LIB#{lib}"},
            "role": {"S": "member"},
            "created_at": {"S": "2026-08-19T12:00:00.000000+00:00"},
        },
    )


# ───────────────────────── resolving the library ─────────────────────────


def test_one_library_needs_no_header(real_catalog, signed_in):
    """The common case, and the reason the header is optional at all."""
    signed_in.sub = CATALOG_OWNER

    resp = _client().get("/api/_probe")

    assert resp.status_code == 200
    assert resp.get_json() == {"sub": CATALOG_OWNER, "library": CATALOG_LIBRARY}


def test_the_header_selects_a_library_the_caller_is_in(real_catalog, signed_in):
    signed_in.sub = CATALOG_MEMBER

    resp = _client().get("/api/_probe", headers={"X-Studio-Library": CATALOG_LIBRARY})

    assert resp.status_code == 200
    assert resp.get_json() == {"sub": CATALOG_MEMBER, "library": CATALOG_LIBRARY}


def test_two_libraries_and_no_header_is_400_naming_the_choice(real_catalog, signed_in):
    """A refusal, not a guess — and one the caller can act on without a second call."""
    signed_in.sub = CATALOG_OWNER
    _add_membership(real_catalog, CATALOG_OWNER, OTHER_LIBRARY)

    resp = _client().get("/api/_probe")

    assert resp.status_code == 400
    error = resp.get_json()["error"]
    assert "X-Studio-Library" in error
    # Both ids are named. Listing them leaks nothing — they are the caller's own
    # libraries — and it is what makes the message answerable from curl.
    assert CATALOG_LIBRARY in error
    assert OTHER_LIBRARY in error


def test_a_library_the_caller_is_not_in_is_403(real_catalog, signed_in):
    """403 and not 404: see `errors.ForbiddenError` for why they are not the same."""
    signed_in.sub = CATALOG_OWNER
    _add_membership(real_catalog, CATALOG_MEMBER, OTHER_LIBRARY)

    resp = _client().get("/api/_probe", headers={"X-Studio-Library": OTHER_LIBRARY})

    assert resp.status_code == 403
    assert OTHER_LIBRARY in resp.get_json()["error"]


def test_a_library_nobody_is_in_is_403_too(real_catalog, signed_in):
    """An id that names no rows at all still answers 403, never 404.

    The status must not depend on whether the library exists, or the difference
    between the two answers is a probe for which ids are real.
    """
    signed_in.sub = CATALOG_OWNER

    resp = _client().get("/api/_probe", headers={"X-Studio-Library": "lib-nonexistent"})

    assert resp.status_code == 403


def test_a_member_of_nothing_is_403(real_catalog, signed_in):
    """Authenticated and in no library — a provisioning gap, not a bad request.

    400 would tell them to name a library in the header; there is none to name.
    """
    signed_in.sub = STRANGER

    resp = _client().get("/api/_probe")

    assert resp.status_code == 403


# ─────────────────────────── who is calling ───────────────────────────


def test_an_unauthenticated_call_is_401(signed_in):
    signed_in.authenticated = False

    resp = _client().get("/api/_probe")

    assert resp.status_code == 401
    assert "error" in resp.get_json()


def test_an_unauthenticated_call_never_reaches_the_catalog(signed_in, monkeypatch):
    """Identity first, membership second — the hook must not read a row for a stranger."""
    signed_in.authenticated = False
    monkeypatch.setattr(app_factory, "catalog", Unreadable())

    assert _client().get("/api/_probe").status_code == 401


def test_an_unknown_path_is_401_before_it_is_404(signed_in):
    """Flask routes inside `dispatch_request`, so the hook runs first — deliberately.

    A stranger enumerating the route table is not owed the difference between a
    path that exists and one that does not.
    """
    signed_in.authenticated = False

    assert _client().get("/api/nope").status_code == 401


# ─────────────────────────── what is skipped ───────────────────────────


def test_health_is_reachable_with_no_auth(signed_in):
    """The deploy workflow's smoke check. A 401 here fails every deploy."""
    signed_in.authenticated = False

    resp = _client().get("/api/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_health_reads_no_catalog_row(signed_in, monkeypatch):
    """Skipped means skipped: no library is resolved for it either."""
    monkeypatch.setattr(app_factory, "catalog", Unreadable())

    assert _client().get("/api/health").status_code == 200


def test_the_preflight_still_answers_204_with_no_auth(signed_in):
    """A 401 on a preflight reaches the SPA as a network error with no status."""
    signed_in.authenticated = False

    resp = _client().options("/api/tree")

    assert resp.status_code == 204
    assert "Access-Control-Allow-Origin" in resp.headers


def test_the_preflight_allows_the_library_header():
    """The header the hook reads has to survive the browser's preflight.

    Sent as a real preflight — `Origin` plus `Access-Control-Request-Method` —
    because that pair is what makes Flask-CORS answer with `Allow-Headers` at
    all. The deployed API answers its own preflight from an API Gateway MOCK
    integration, so this asserts the Flask half of a contract stated in four
    places; the other three are `cors_headers` in `infra/modules/api_gateway`.
    """
    resp = _client().options(
        "/api/tree",
        headers={
            "Origin": config.allowed_origin(),
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Studio-Library",
        },
    )

    assert "X-Studio-Library" in resp.headers["Access-Control-Allow-Headers"]


# ─────────────────── a known caller, and no library at all ───────────────────
#
# `/api/libraries` takes one of the two skips and not the other, so each test
# below asserts one half of that: it authenticates, and it resolves no library.
#
# **The real route cannot answer these**, because what is under test is what the
# hook left on `g`, and `/api/libraries` reports libraries rather than the caller
# it resolved them for. So the probe below replaces that route's view function.
# The substitution is safe precisely because of what these tests assert: the hook
# decides both skips from `request.path`, before any view function is reached, so
# which function answers is the one detail they must not depend on.


def _libraries_client():
    """A client whose `/api/libraries` reports what `g` holds.

    The view function is *replaced* rather than a second rule added at the same
    path — Werkzeug would keep matching the blueprint's, and the probe would
    silently never run.
    """
    app = create_app()

    def _libraries():
        return jsonify({"sub": g.caller_sub, "library": g.library}), 200

    app.view_functions["libraries.libraries"] = _libraries
    return app.test_client()


def test_libraries_still_requires_authentication(signed_in):
    """Unscoped is not unauthenticated — the answer names a specific person."""
    signed_in.authenticated = False

    resp = _libraries_client().get("/api/libraries")

    assert resp.status_code == 401
    assert "error" in resp.get_json()


def test_libraries_resolves_no_library(signed_in, monkeypatch):
    """No membership row is read for it, and `g.library` is `None` rather than absent.

    Both halves matter. `Unreadable` proves the resolution was skipped and not
    merely tolerated, and the body proves the route can still read `g.library` —
    the attribute the hook promises exists on every path below it.
    """
    monkeypatch.setattr(app_factory, "catalog", Unreadable())

    resp = _libraries_client().get("/api/libraries")

    assert resp.status_code == 200
    assert resp.get_json() == {"sub": CATALOG_OWNER, "library": None}


def test_a_member_of_nothing_reaches_libraries(real_catalog, signed_in):
    """The caller the split exists for, against the real catalog.

    `test_a_member_of_nothing_is_403` is this same caller one path over. They are
    refused everywhere else, which is why the route that would tell them so must
    not be one of the places refusing them.
    """
    signed_in.sub = STRANGER

    resp = _libraries_client().get("/api/libraries")

    assert resp.status_code == 200
    assert resp.get_json() == {"sub": STRANGER, "library": None}


def test_the_library_header_is_ignored_on_libraries(real_catalog, signed_in):
    """Even a header naming a library the caller is not in — nothing checks it.

    The same header on any other path is a 403. Asserted because the skip is on
    the path and not on the absence of the header, and a future reader weighing
    "resolve it if they asked for it" should see that answered here.
    """
    signed_in.sub = STRANGER

    resp = _libraries_client().get(
        "/api/libraries", headers={"X-Studio-Library": CATALOG_LIBRARY}
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"sub": STRANGER, "library": None}
