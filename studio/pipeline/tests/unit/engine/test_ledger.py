"""The local submission ledger — the guard against paying for the same thing twice.

A batch of 72 upscales was driven by a shell script; the harness reported it
finished when it had not, a second pass ran over the same list, and ~46 images
were generated twice for about $2.30. Nothing noticed, because every submission
is the first one as far as `run` is concerned.
"""

from __future__ import annotations

import json

import pytest

from studio_pipeline.engine import ledger as LEDGER


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """The suite's own autouse fixture already redirects `auth.CONFIG_DIR`, so
    the ledger follows it. Pinned again here so these tests do not depend on
    which profile happens to be current."""
    monkeypatch.setattr(LEDGER.auth, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(LEDGER, "path", lambda: tmp_path / "submissions-test.json")


PAYLOAD = {"upscale_factor": "4x", "enhance_model": "High Fidelity V2"}
BOUND = {"image": "node-abc"}


def test_the_same_payload_fingerprints_the_same_whatever_the_key_order():
    """A dict's order is not part of what was asked for, so two payloads built
    by different code paths must not read as different requests."""
    a = LEDGER.fingerprint("vendor/m", {"b": 2, "a": 1}, BOUND)
    b = LEDGER.fingerprint("vendor/m", {"a": 1, "b": 2}, BOUND)

    assert a == b


def test_a_different_binding_is_a_different_submission():
    """The commonest near-miss in a batch: same settings, next image."""
    one = LEDGER.fingerprint("vendor/m", PAYLOAD, {"image": "node-abc"})
    two = LEDGER.fingerprint("vendor/m", PAYLOAD, {"image": "node-def"})

    assert one != two


def test_a_different_model_is_a_different_submission():
    assert (LEDGER.fingerprint("vendor/m", PAYLOAD, BOUND)
            != LEDGER.fingerprint("vendor/other", PAYLOAD, BOUND))


def test_nothing_is_seen_until_it_is_recorded():
    digest = LEDGER.fingerprint("vendor/m", PAYLOAD, BOUND)

    assert LEDGER.seen("proj-1", digest) is None
    LEDGER.record("proj-1", digest, run="p/shot", name="shot")
    assert LEDGER.seen("proj-1", digest)["name"] == "shot"


def test_the_same_payload_against_another_project_is_not_a_duplicate():
    """The project is in the lookup key rather than the fingerprint, so the same
    work in a second project reads as the new submission it is."""
    digest = LEDGER.fingerprint("vendor/m", PAYLOAD, BOUND)
    LEDGER.record("proj-1", digest, run="p/shot", name="shot")

    assert LEDGER.seen("proj-2", digest) is None


def test_stale_entries_are_dropped_on_the_next_write(tmp_path):
    old = LEDGER.fingerprint("vendor/m", {"old": True}, BOUND)
    fresh = LEDGER.fingerprint("vendor/m", {"fresh": True}, BOUND)
    LEDGER.record("proj-1", old, run="p/old", name="old")
    # age it past the window by hand, then write again
    data = json.loads(LEDGER.path().read_text())
    data[f"proj-1:{old}"]["at"] -= LEDGER.MAX_AGE_SECONDS + 1
    LEDGER.path().write_text(json.dumps(data))

    LEDGER.record("proj-1", fresh, run="p/fresh", name="fresh")

    assert LEDGER.seen("proj-1", old) is None
    assert LEDGER.seen("proj-1", fresh) is not None


def test_an_unwritable_ledger_does_not_stop_the_work(monkeypatch):
    """It is a guard rail. Losing it costs a duplicate; refusing to generate
    because a cache file will not open costs the whole command."""
    def _boom(entries):
        raise OSError("read-only")
    monkeypatch.setattr(LEDGER, "_write", _boom)

    LEDGER.record("proj-1", "deadbeef", run="p/x", name="x")  # must not raise
