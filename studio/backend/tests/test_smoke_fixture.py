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
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[2]
FIXTURE_FILE = STUDIO / "seeds" / "smoke.json"

PASSWORD_PLACEHOLDER = "${SMOKE_TEST_USER_PASSWORD}"


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


def test_the_seeded_address_can_never_be_a_real_mailbox():
    """`.test` is reserved (RFC 2606) and resolves nowhere.

    That is the entire reason the address is safe to commit. A real one here
    would make every leak of this file reach a person, and would put a live
    mailbox behind an account the pipeline resets the password of on every
    deploy.
    """
    assert _fixture()["user"]["email"].endswith(".test")


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
