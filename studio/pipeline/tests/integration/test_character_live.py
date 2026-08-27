"""A character through the real API: create, fill, read back, delete.

Every one of these passes against `fake_api.py` already. The point is that they
now also pass against the Flask app and a real DynamoDB table — which is a
different claim, and the one nothing in this repo had ever made.
"""
from __future__ import annotations

import pytest

#: A slug from `DEV_SUBJECTS`, deliberately. A leftover from a failed teardown is
#: then still a name the fixture publisher accepts, so a crashed run cannot
#: quietly block the next `dev-seed publish` on a stack-wide name check.
SUBJECT = "subject-b"


@pytest.fixture(scope="module")
def subject(studio):
    """`subject-b`, created fresh and removed afterwards.

    Deleted FIRST as well as last: a previous run that died between create and
    teardown would otherwise fail every test here on a slug conflict, which is a
    confusing way to be told about an old crash.
    """
    studio("character", "delete", SUBJECT, "--files", "delete", check=False)
    studio("character", "create", SUBJECT)
    yield SUBJECT
    studio("character", "delete", SUBJECT, "--files", "delete", check=False)


def test_a_created_character_is_readable_through_the_api(studio, subject):
    """`create` writes a record, a slug claim, a root and four pool folders in
    one transaction — and this is the first test that watches DynamoDB accept
    that transaction rather than a dict in memory."""
    shown = studio("character", "show", subject).stdout

    assert subject in shown
    for pool in ("archive", "corpus", "reference", "seed"):
        assert f"{pool}/" in shown


def test_a_character_appears_in_the_listing(studio, subject):
    """The listing is a `CHARSLUG#` query plus a batched read. `counts.files`
    comes back from the route that was sending it to nobody until this branch."""
    listed = studio("character", "list").stdout

    assert subject in listed
    assert "files" in listed


def test_seed_material_uploads_and_reads_back(studio, subject, tmp_path_factory):
    """An upload is create-node -> sign -> PUT -> confirm, four round trips the
    fake collapses into a dict write. Here every one of them is real, and the
    bytes land in a real bucket."""
    local = tmp_path_factory.mktemp("seed") / "seed-01.png"
    local.write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"0" * 128)  # not decoded; only its bytes travel

    studio("character", "add-to", subject, "seed", str(local))
    pool = studio("character", "pool", subject, "seed").stdout

    assert "seed-01.png" in pool
    assert "node-" in pool


def test_reference_is_refused_as_a_destination(studio, subject):
    """Hard rule #2b, enforced by the CLI rather than by the API.

    `add-to` takes corpus/seed/archive and nothing else: promoting an image into
    `reference/` is a separate decision from having agreed to spend money.
    """
    result = studio("character", "add-to", subject, "reference", "/dev/null",
                    check=False)

    assert result.returncode != 0
    assert "reference" in (result.stdout + result.stderr)


def test_a_slug_that_is_taken_is_a_conflict_not_a_second_character(studio, subject):
    """The slug claim row is the uniqueness mechanism — DynamoDB enforces it on
    a primary key and on nothing else. The fake reproduces the 409; this is the
    table actually refusing the transaction."""
    result = studio("character", "create", subject, check=False)

    assert result.returncode != 0
    assert "exists" in (result.stdout + result.stderr).lower()
