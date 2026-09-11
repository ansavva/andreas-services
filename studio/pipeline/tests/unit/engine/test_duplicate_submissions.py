"""Paying for the same generation twice — the guard, now that it is a query.

**The incident.** A batch of 72 upscales was driven by a shell script. The
harness reported the job finished when it had not, a second pass was started over
the same list, and both ran to completion — roughly 46 images were generated
twice and about $2.30 was spent on results that overwrote each other. Nothing
noticed, because `run` builds a payload and sends it and every send is the first
one as far as the pipeline is concerned.

`engine/ledger.py` was the answer: a per-profile JSON file of recently submitted
payload hashes. Its own docstring named the better one and declined to build it —
the run store could answer this, but the listing rows did not carry the payload,
so comparing meant a `GET /api/runs/<id>` per candidate, on the order of 1800
requests before that batch's first submit.

The fingerprint is projected onto the listing row now, so it is one query. These
tests are what the file's tests became, plus the two cases the file could not
have: a run submitted from somewhere else, and a fingerprint the CLI never
computes for itself.
"""

from __future__ import annotations

import pytest

from studio_pipeline.adapters import api, entities
from studio_pipeline.engine import submit as SUB


@pytest.fixture
def a_project(library):
    return entities.create_project("dupes")


def _draft(project, *, prompt="a wave", model="openai/gpt-image-2") -> dict:
    """A draft, through the same route `studio run --dry-run` uses."""
    return entities.create_run(
        project=project["id"], kind="image", engine="studio-media-gpt-image-2",
        model=model, input={"prompt": prompt},
        plan={"params": {}, "prompt": prompt}, sends=[], bindings={},
        characters=[],
    )


def test_the_fingerprint_comes_off_the_draft_rather_than_being_computed(a_project):
    """The whole reason the check moved after the draft.

    The hash under the fingerprint has had three implementations in this
    repository and one of them silently disagreed over `Decimal`, reporting 131
    healthy runs as stale.
    A fourth hash on this side of the wire is the failure that keeps happening,
    so the CLI reads the value the API derived.
    """
    record = _draft(a_project)
    assert record["fingerprint"].startswith("sha256:")


def test_two_identical_payloads_share_a_fingerprint(a_project):
    first = _draft(a_project)
    second = _draft(a_project)
    assert first["fingerprint"] == second["fingerprint"]


def test_the_same_payload_on_a_different_model_does_not(a_project):
    """Two identical plans on different engines are different submissions.

    This is the one thing the plan's own hash does not carry, and the only
    reason the fingerprint is a separate value rather than that hash itself.
    """
    assert (_draft(a_project, model="openai/gpt-image-2")["fingerprint"]
            != _draft(a_project, model="google/nano-banana-pro")["fingerprint"])


def test_an_unsubmitted_draft_is_not_a_duplicate(a_project):
    """THE PROPERTY THE LEDGER GOT FOR FREE.

    The file was only ever written after a successful submit, so an abandoned
    attempt could not make the next identical payload look like a duplicate. A
    row exists from the moment a run is planned, so the states that never billed
    have to be excluded explicitly — and a `--dry-run` that a person then repeats
    is the ordinary case, not an edge one.
    """
    _draft(a_project)
    assert SUB.already_submitted(_draft(a_project)) is None


def test_a_submitted_run_is(a_project):
    first = _draft(a_project)
    entities.patch_run(first["id"], status="succeeded")

    found = SUB.already_submitted(_draft(a_project))
    assert found is not None and found["id"] == first["id"]


def test_a_run_never_matches_itself(a_project):
    """The check runs on a draft that is already in the store, so it must skip it."""
    record = _draft(a_project)
    assert SUB.already_submitted(record) is None


def test_the_same_payload_in_another_project_is_not_a_duplicate(a_project, library):
    """The project scopes the question, exactly as the ledger's key did.

    Rendering the same prompt into a second project is a deliberate act, and
    refusing it would make the guard wrong far more often than it is right.
    """
    other = entities.create_project("elsewhere")
    first = _draft(a_project)
    entities.patch_run(first["id"], status="succeeded")

    assert SUB.already_submitted(_draft(other)) is None


def test_an_edit_moves_the_fingerprint(a_project):
    """An edited draft is a different submission.

    A fingerprint left behind would make the *next* identical payload look like a
    duplicate of a payload that no longer exists.
    """
    record = _draft(a_project, prompt="a wave")
    before = record["fingerprint"]
    entities.patch_run_plan(record["id"], {"params": {}, "prompt": "a different wave"})
    assert entities.get_run(record["id"])["fingerprint"] != before


def test_an_unreachable_api_does_not_block_the_submission(a_project, monkeypatch):
    """A guard rail that cannot reach the store must not be what stops the work.

    A false negative costs money once. A false refusal costs somebody their
    afternoon, and teaches them to pass `--again` by reflex — which disables the
    guard permanently and silently.
    """
    def refuse(**_kwargs):
        raise api.ApiError("gateway timeout", 504)

    record = _draft(a_project)
    monkeypatch.setattr(entities, "query_runs", refuse)
    assert SUB.already_submitted(record) is None
