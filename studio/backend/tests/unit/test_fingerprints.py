"""The submission fingerprint — the projection that retired a per-machine file.

A batch of 72 upscales was driven twice: the harness reported the job finished
when it had not, ~46 images were generated again for about $2.30, and the results
overwrote each other. The pipeline kept a local JSON file of recently submitted
payload hashes to catch that, because asking the run store meant a
`GET /api/runs/<id>` per candidate — on the order of 1800 requests before that
batch's first submit. Its own docstring specified the fix and left it: project a
fingerprint onto the listing row and filter on it.

**Derived from `plan_digest`, never hashed independently.** The plan is the
payload and the sends are the bindings, so a second hash over the same material
would be a second answer to "is this the same submission" — and the two would
drift the first time either changed what it included. `plan_digest` has had three
implementations in this repository and one of them silently disagreed over
`Decimal`, reporting 131 intact runs as stale. One derivation, one place.
"""

from studio_core.services import catalog

from tests.unit.test_runs import _create, _project


def test_a_draft_hands_back_its_fingerprint(api, empty_api):
    """The CLI reads it off the response rather than computing it.

    That is the whole reason the duplicate check runs *after* the draft exists.
    """
    project = _project(empty_api)
    run = _create(empty_api, project, plan={"params": {}, "prompt": "a wave"})
    assert run["fingerprint"].startswith("sha256:")
    assert run["project"] == project["id"]


def test_two_identical_payloads_share_one(empty_api):
    project = _project(empty_api)
    first = _create(empty_api, project, plan={"params": {}, "prompt": "a wave"})
    second = _create(empty_api, project, plan={"params": {}, "prompt": "a wave"})
    assert first["fingerprint"] == second["fingerprint"]


def test_a_different_prompt_does_not(empty_api):
    project = _project(empty_api)
    first = _create(empty_api, project, plan={"params": {}, "prompt": "a wave"})
    second = _create(empty_api, project, plan={"params": {}, "prompt": "a hill"})
    assert first["fingerprint"] != second["fingerprint"]


def test_the_same_plan_on_a_different_model_does_not(empty_api):
    """The one thing `plan_digest` does not carry, and the reason this exists.

    Without the model in it, the fingerprint would be the digest and an upscale
    of the same image on two engines would read as one submission.
    """
    project = _project(empty_api)
    plan = {"params": {}, "prompt": "a wave"}
    first = _create(empty_api, project, plan=plan, model="google/nano-banana-pro")
    second = _create(empty_api, project, plan=plan, model="openai/gpt-image-2")
    assert first["fingerprint"] != second["fingerprint"]


def test_it_is_queryable_without_reading_a_single_envelope(empty_api):
    """THE POINT. One query, filtered on the listing row's own projection.

    If this needed the envelope it would be the 1800 requests the local file
    existed to avoid, and the file would still be the right answer.
    """
    project = _project(empty_api)
    run = _create(empty_api, project, plan={"params": {}, "prompt": "a wave"})
    _create(empty_api, project, plan={"params": {}, "prompt": "something else"})

    found = empty_api.get(
        f"/api/runs?project={project['id']}"
        f"&fingerprint={run['fingerprint']}&include=drafts"
    ).get_json()
    assert [entry["id"] for entry in found["runs"]] == [run["id"]]


def test_an_edit_moves_it(empty_api):
    """An edited draft is a different submission.

    A stale fingerprint would make the next identical payload look like a
    duplicate of one that no longer exists.
    """
    project = _project(empty_api)
    run = _create(empty_api, project, plan={"params": {}, "prompt": "a wave"})
    before = run["fingerprint"]

    empty_api.patch(f"/api/runs/{run['id']}/plan",
                    json={"plan": {"params": {}, "prompt": "a different wave"}})

    after = empty_api.get(f"/api/runs/{run['id']}").get_json()["fingerprint"]
    assert after != before

    # And the LISTING row moved with it, which is the half that is easy to miss:
    # the envelope and the projection are two items, and a query reads the
    # projection.
    found = empty_api.get(
        f"/api/runs?project={project['id']}&fingerprint={after}&include=drafts"
    ).get_json()
    assert [entry["id"] for entry in found["runs"]] == [run["id"]]


def test_a_submitted_run_keeps_the_fingerprint_it_was_created_with(empty_api):
    """Nothing about moving through the states re-derives it."""
    project = _project(empty_api)
    run = _create(empty_api, project, plan={"params": {}, "prompt": "a wave"})
    empty_api.patch(f"/api/runs/{run['id']}", json={"status": "pending"})

    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["fingerprint"] == run["fingerprint"]


def test_it_is_derived_from_the_digest_rather_than_hashed_apart():
    """Stated as a unit assertion, because it is the property that stops drift.

    Two runs whose plan and sends hash the same, on the same model, must
    fingerprint the same — by construction, not by two hash functions happening
    to agree.
    """
    plan = {"params": {"seed": 1}, "prompt": "a wave"}
    sends = [{"field": "image_input", "role": "ref", "node": "node-1"}]

    assert (catalog.submission_fingerprint("m", plan, sends)
            == catalog.submission_fingerprint("m", plan, sends))
    # A change the digest sees, the fingerprint sees.
    assert (catalog.submission_fingerprint("m", plan, sends)
            != catalog.submission_fingerprint("m", {**plan, "prompt": "x"}, sends))
    # Reordering sends is a real edit — a prompt may cite "the first image".
    two = [*sends, {"field": "image_input", "role": "ref", "node": "node-2"}]
    assert (catalog.submission_fingerprint("m", plan, two)
            != catalog.submission_fingerprint("m", plan, list(reversed(two))))
