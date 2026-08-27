"""The smoke fixture, checked on every PR — the isolation rule as a test.

`seeds/smoke.json` decides what the post-deploy smoke account can reach. The
suite that uses it never runs on a PR (it writes to production), and the seeder
that reads it only runs on a deploy, so an edit that widened the account's reach
would land unchallenged and be discovered by a prod job — after the row was
written.

**The rule these pin: the smoke account is a member of exactly one library.**
That is not politeness about test data. `app_factory`'s `before_request`
resolves the library a request is about from the caller's own membership rows,
and every route then checks the node's own `lib` against those rows — so one
membership is the mechanism that makes the account structurally unable to
address anyone else's library. A second entry in this file is a second library
the smoke run can create in, upload to and DELETE from.

The seeder enforces the same thing at run time and refuses to continue if it
finds an extra membership. This is the half that fails *before* a merge.
"""

from __future__ import annotations

import json

from tests.paths import STUDIO_DIR

STUDIO = STUDIO_DIR
FIXTURE_FILE = STUDIO / "seeds" / "smoke.json"

PASSWORD_PLACEHOLDER = "${SMOKE_TEST_USER_PASSWORD}"
EMAIL_PLACEHOLDER = "${SMOKE_TEST_USER_EMAIL}"


def _fixture() -> dict:
    return json.loads(FIXTURE_FILE.read_text())


def test_the_fixture_is_where_both_readers_look():
    """A guard on the guards.

    Everything below reads one path, and so do `scripts/prod-seed-smoke.py` and
    `tests/smoke/conftest.py` — by their own `parents[…]` arithmetic, which is
    what breaks when a file moves. A test asserting things about a file nobody
    loads is worse than no test, because it reads like coverage.
    """
    assert FIXTURE_FILE.is_file()

    # Each reader's own `parents[…]` arithmetic, restated from where it lives.
    # That arithmetic is what breaks when a file moves, and all three have to
    # land on one file or the seeder provisions an identity the suite does not
    # sign in as.
    readers = {
        STUDIO / "scripts" / "prod-seed-smoke.py": 1,
        STUDIO / "backend" / "tests" / "smoke" / "conftest.py": 3,
        STUDIO / "backend" / "tests" / "smoke" / "sign_in.py": 3,
    }
    for reader, depth in readers.items():
        assert reader.is_file(), reader
        assert reader.resolve().parents[depth] / "seeds" / "smoke.json" == FIXTURE_FILE


def test_the_fixture_grants_exactly_one_library():
    """One library, one user, one membership — the whole isolation story."""
    fixture = _fixture()

    assert set(fixture) == {"//", "library", "user"}, (
        "A new top-level key is a new thing the seeder would have to grant. "
        "Adding one means revisiting docs/PROD_SMOKE.md, not widening this test."
    )
    assert set(fixture["library"]) == {"id", "name", "root_node"}
    assert fixture["user"]["role"] in ("owner", "member")


def test_the_address_is_never_stored_here_either():
    """A placeholder, like the password — no account address is committed.

    It used to be the literal `smoke@studio.test`, and the argument for that was
    sound as far as it went: `.test` is reserved (RFC 2606) and resolves
    nowhere, so a leak of this file could not reach a person. What it left was
    one account described in two kinds of place — a secret for one half and a
    repository for the other.

    **The `.test` rule did not go away, it moved to where the value now comes
    from.** `scripts/prod-seed-smoke.py` refuses any `SMOKE_TEST_USER_EMAIL`
    outside the reserved TLD, which is the more useful place for the check: a
    fixture is reviewed once at merge, and an environment variable is set by
    whoever is holding the console that day.
    """
    assert _fixture()["user"]["email"] == EMAIL_PLACEHOLDER


def test_the_password_is_never_stored_here():
    """A placeholder, expanded from the environment at seed time.

    A literal would be a credential in the repository, and this file is the only
    thing that would ever read it.
    """
    assert _fixture()["user"]["password"] == PASSWORD_PLACEHOLDER


def test_the_ids_are_fixed_rather_than_generated():
    """Stable ids are what make the seeder converge instead of accumulating.

    A fresh library id per run would leave the account holding a new membership
    every deploy, which breaks the one-membership rule within a week — so the
    ids being literal strings is load-bearing, not cosmetic.
    """
    library = _fixture()["library"]

    assert library["id"] and not library["id"].startswith("$")
    assert library["root_node"] and not library["root_node"].startswith("$")


# The ids are pinned to their literal values, not merely asserted to be literal.
#
# `test_the_ids_are_fixed_rather_than_generated` above checks the shape and not
# the value, and that is not enough for the one rule this fixture exists to
# hold. Repointing `library.id` at another library's id is a one-line edit, it
# is still a fixed literal, and it passes every other check here — while the
# seeder would then put the smoke account in THAT library and both remaining
# guards would agree, because the seed check and the runtime check both compare
# against this file. The fixture is the thing they trust, so the fixture is
# where the value has to be nailed down.
#
# Measured, not assumed: pointing `library.id` at `lib-0001` passed all five
# tests before this one existed.
SMOKE_LIBRARY_ID = "lib-smoke"
SMOKE_ROOT_NODE_ID = "node-smoke-root"


def test_the_library_id_is_the_smoke_library_and_no_other():
    """**The owner's library is private. This is what keeps it that way.**

    Changing the fixture's library id must require changing this line too — a
    deliberate edit in two places rather than a typo in one.
    """
    library = _fixture()["library"]

    assert library["id"] == SMOKE_LIBRARY_ID, (
        f"the smoke fixture names library {library['id']!r}, not "
        f"{SMOKE_LIBRARY_ID!r}. The seeder puts the smoke account in whatever "
        f"this file names, and every other guard compares against this file — "
        f"so pointing it at a real library would seed an account into it and "
        f"report success. If this change is intended, change this test too."
    )
    assert library["root_node"] == SMOKE_ROOT_NODE_ID
