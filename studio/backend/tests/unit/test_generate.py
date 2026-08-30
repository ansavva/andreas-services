"""Submitting a run, and closing one. **The half of studio that spends money.**

This is `engine/submit.py`'s billing half, which lived in the CLI until
generation moved here. What that move bought, and what these tests are about:

* a generation is no longer attached to a terminal — a 15-minute video does not
  need a window left open, and `Ctrl-C` abandons a wait rather than a prediction;
* the SPA can submit at all, which it could not, having no provider credential
  and nowhere to poll from;
* the run is closed by a callback, in one place, whether that callback reaches a
  worker Lambda or a process on a developer's laptop.

**Nothing here bills.** `conftest.py` sets `STUDIO_REPLICATE_MODE=fake`, so
`clients/replicate.py` answers every call locally with a deterministic prediction
id and a real decodable PNG; a dud token and an autouse socket guard sit behind
it. See that file for why there are three guards and how they fail differently.

The gate itself — approved, and the digest still matching — is tested in
`test_runs.py`, where the state machine lives. What is tested here is that the
submit route stands behind it rather than beside it.
"""

import json

import pytest

from studio_core import config
from studio_core.clients import replicate
from studio_core.services import catalog, generate


def _project(api, slug="rooftop-teaser"):
    return api.post("/api/projects", json={"slug": slug}).get_json()


def _draft(api, project, **body):
    """A run drafted against a model the shipped registry really carries.

    `google/nano-banana-pro` rather than an invented id, because `submit` looks
    the entry up by model id and a fake one is a 404 that says nothing about the
    route under test.
    """
    resp = api.post("/api/runs", json={
        "project": project["id"],
        "kind": "image",
        "engine": "nano-banana-pro",
        "model": "google/nano-banana-pro",
        "plan": {"version": 1, "origin": "authored", "prompt": "a porch at dusk",
                 "params": {}},
        "input": {"prompt": "a porch at dusk"},
        **body,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _approved(api, project, **body):
    run = _draft(api, project, **body)
    resp = api.post(f"/api/runs/{run['id']}/approve", json={"digest": run["plan_digest"]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return run


# ── the gate stands in front of the money ───────────────────────────────────


def test_an_unapproved_run_cannot_be_submitted(empty_api):
    """**Hard rule #2, at the route that spends.**

    The refusal is the same `_refuse_submission` that guards `PATCH /api/runs/
    <id>`, called from here rather than copied — so there is one answer to "may
    this be sent" instead of two that have to agree.
    """
    project = _project(empty_api)
    run = _draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "not_approved"
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "draft", (
        "a refused submission leaves the run exactly as it was"
    )


def test_a_payload_edited_after_approval_cannot_be_submitted(empty_api):
    """Approve, reword, submit — the failure the digest exists to catch.

    It has actually happened in this repository, which is why hard rule #2 says
    re-approve after *any* edit and why that sentence is now a check.
    """
    project = _project(empty_api)
    run = _approved(empty_api, project)

    empty_api.patch(f"/api/runs/{run['id']}/plan", json={
        "plan": {"version": 1, "origin": "authored", "prompt": "a porch at DAWN",
                 "params": {}}})

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    # An edit returns the run to `draft` and drops the approval, so this reports
    # the state it is actually in rather than a stale digest.
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "not_approved"


def test_a_run_cannot_be_submitted_twice(empty_api):
    """**The cheapest way to buy the same prediction twice**, refused first.

    Checked before the approval is even looked at: a second POST to this route is
    a duplicate submission whatever the run's approval says.
    """
    project = _project(empty_api)
    run = _approved(empty_api, project)
    assert empty_api.post(f"/api/runs/{run['id']}/submit").status_code == 200

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 409
    assert "already been sent" in resp.get_json()["error"]


def test_a_payload_the_model_refuses_leaves_the_run_approved(empty_api, monkeypatch):
    """**Preflight runs BEFORE `pending`, and that is the whole of this test.**

    A run moved to `pending` and then refused would read as "went out and never
    answered" — the one state that means a prediction may be billing somewhere.
    A payload the model will not accept has to leave the run exactly as it was:
    approved, editable, and submittable again once it is fixed.
    """
    monkeypatch.setattr(
        "studio_core.services.schema.fetch",
        lambda model: ({"prompt": {"type": "string"}}, {}),
    )
    project = _project(empty_api)
    run = _approved(empty_api, project, plan={
        "version": 1, "origin": "authored", "prompt": "a porch",
        "params": {"no_such_knob": True},
    })

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 400
    assert "no_such_knob" in resp.get_json()["error"]
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "approved", "refused before anything was declared"
    # `.get`, because an attribute cleared to `None` is REMOVEd from the row —
    # a record read back has no key at all rather than a null one.
    assert record.get("prediction_id") is None


# ── what a submission does ──────────────────────────────────────────────────


def test_submitting_declares_the_run_then_calls_the_provider(empty_api):
    """`pending` before the provider, `running` with the prediction id after.

    The order is the safety: the transition the approval gate guards happens
    first, so a process that dies in between leaves a row that says a submission
    went out — rather than a draft that says nothing happened.
    """
    project = _project(empty_api)
    run = _approved(empty_api, project)

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert body["status"] == "running"
    assert body["prediction_id"].startswith("fake")
    assert body["submitted"], "a submitted run says when"


def test_a_submitted_run_is_counted_once(empty_api):
    """A draft is not a run the project made. The transition out of it is."""
    project = _project(empty_api)
    before = empty_api.get(f"/api/projects/{project['id']}").get_json()
    run = _approved(empty_api, project)

    mid = empty_api.get(f"/api/projects/{project['id']}").get_json()
    assert mid["counts"]["runs"] == before["counts"]["runs"], "a draft counts for nothing"

    empty_api.post(f"/api/runs/{run['id']}/submit")

    after = empty_api.get(f"/api/projects/{project['id']}").get_json()
    assert after["counts"]["runs"] == before["counts"]["runs"] + 1


def test_the_response_says_how_this_run_will_be_closed(empty_api, monkeypatch):
    """`callback` is reported rather than guessed, and a caller depends on it.

    `poll` means nothing on the internet can reach this API — a machine with no
    receiver provisioned — so the caller has to drive `reconcile` itself. A CLI
    that assumed `webhook` there would wait forever on a row nothing will write.
    """
    project = _project(empty_api)

    run = _approved(empty_api, project)
    assert empty_api.post(f"/api/runs/{run['id']}/submit").get_json()["callback"] == "poll"

    monkeypatch.setenv("STUDIO_WEBHOOK_BASE_URL", "https://callbacks.example")
    other = _approved(empty_api, project, plan={
        "version": 1, "origin": "authored", "prompt": "a different porch",
        "params": {}})
    assert empty_api.post(f"/api/runs/{other['id']}/submit").get_json()["callback"] == "webhook"


def test_a_webhook_url_is_never_part_of_the_payload(empty_api, monkeypatch):
    """**It is a sibling of `input`, not a field in it**, and both halves matter.

    Inside `input` it would be a field the model's schema rejects, and — worse —
    a change to the payload after somebody approved it, which is precisely what
    `plan_digest` exists to make impossible.
    """
    monkeypatch.setenv("STUDIO_WEBHOOK_BASE_URL", "https://callbacks.example")
    sent = {}

    def capture(model, payload, *, webhook=None):
        sent["payload"], sent["webhook"] = payload, webhook
        return {"id": "pred-1", "status": "starting"}

    monkeypatch.setattr(replicate, "create_prediction", capture)
    project = _project(empty_api)
    run = _approved(empty_api, project)

    empty_api.post(f"/api/runs/{run['id']}/submit")

    assert sent["webhook"] == f"https://callbacks.example/api/hooks/replicate/{run['id']}"
    assert "webhook" not in sent["payload"]
    assert sent["payload"] == {"prompt": "a porch at dusk"}


# ── closing ────────────────────────────────────────────────────────────────


def _running(empty_api, project, **body):
    run = _approved(empty_api, project, **body)
    empty_api.post(f"/api/runs/{run['id']}/submit")
    return catalog.entity(catalog.ENTITY_RUN, run["id"])


def test_closing_stores_the_output_and_records_its_checksum(empty_api, media_bucket):
    """The output lands as a node with bytes, a size and an MD5 behind it.

    **The checksum is why the upload is a single `PutObject`.** boto3's managed
    transfer would switch to multipart above 8 MB, and a multipart ETag is a hash
    of part hashes rather than the object's MD5 — so every video output would
    land with no checksum at all, silently.
    """
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"],
        "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"],
        "metrics": {"predict_time": 4.5},
    })

    assert closed["status"] == "succeeded"
    assert len(closed["outputs"]) == 1
    node = catalog.node(closed["outputs"][0])
    assert node["name"] == "image.png", "named from the run, extension from the URL"
    assert node["size"] > 0
    assert node["checksum"], "a single PUT, so the ETag is the content MD5"


def test_the_output_is_named_from_the_name_the_draft_recorded(empty_api, media_bucket):
    """`--name` is a filename and it has to survive to the callback.

    It used to be an argument to the download, because the download happened in
    the process that had it. The thing that downloads now arrives with no request
    body at all, so a name that is not on the row before the submission is a name
    nothing can recover.
    """
    project = _project(empty_api)
    record = _running(empty_api, project, name="porch-wide")

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"],
    })

    assert catalog.node(closed["outputs"][0])["name"] == "porch-wide.png"


def test_several_outputs_are_numbered_in_order(empty_api, media_bucket):
    project = _project(empty_api)
    record = _running(empty_api, project, name="sheet")

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png", "https://fake.invalid/x/1.png"],
    })

    assert [catalog.node(n)["name"] for n in closed["outputs"]] == [
        "sheet-1.png", "sheet-2.png"]


def test_closing_is_idempotent(empty_api, media_bucket):
    """**SQS is at-least-once and the receiver acks before verifying anything.**

    So a duplicate callback is ordinary traffic rather than an incident, and it
    must not upload the output a second time — which would double the run's
    `outputs` list and leave two copies of a video in the bucket.
    """
    project = _project(empty_api)
    record = _running(empty_api, project)
    prediction = {"id": record["prediction_id"], "status": "succeeded",
                  "output": ["https://fake.invalid/x/0.png"]}

    first = generate.close_from_prediction(record, prediction)
    again = generate.close_from_prediction(first, prediction)

    assert again["outputs"] == first["outputs"]
    assert len(again["outputs"]) == 1


def test_a_failed_prediction_records_the_error(empty_api, media_bucket):
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "failed",
        "error": "E006: the shot durations do not sum to duration",
    })

    assert closed["status"] == "failed"
    assert "E006" in closed["error"]
    assert closed["outputs"] == []


def test_a_success_with_no_output_is_a_failure(empty_api, media_bucket):
    """Paid for, and produced nothing. Calling that a success puts an empty run
    in the grid with a thumbnail that never loads."""
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded", "output": []})

    assert closed["status"] == "failed"
    assert "no output" in closed["error"]


def test_the_providers_response_is_stored_verbatim_and_never_decoded(
        empty_api, media_bucket):
    """The half of a run this service is forbidden to have an opinion about."""
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"],
        "logs": "a line the provider wrote",
    })

    node = closed["payload"]["response"]
    assert node.startswith("node-")
    stored = json.loads(
        empty_api.get(f"/api/nodes/{node}/text").get_json()["content"])
    assert stored["logs"] == "a line the provider wrote"


def test_a_cost_is_recorded_as_what_the_provider_actually_reports(
        empty_api, media_bucket):
    """**Replicate's prediction body carries no money in it.**

    Billing is per second of the model's hardware and the rate lives on the
    account, so an `amount` computed here would be a number this service made up.
    `predict_time` is real and is what a price would be derived from.
    """
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"],
        "metrics": {"predict_time": 12.25},
    })

    assert closed["cost"] == {"amount": None, "currency": None, "predict_time": 12.25}


# ── reconcile ──────────────────────────────────────────────────────────────


def test_reconcile_closes_a_run_whose_callback_never_arrived(empty_api, media_bucket):
    """The answer to "what happens to a prediction whose webhook never arrives".

    Also the whole story on a machine with no receiver provisioned, where there
    was never going to be a callback. The two are the same situation from this
    side, which is why they share a route.
    """
    project = _project(empty_api)
    record = _running(empty_api, project)
    assert record["status"] == "running"

    body = empty_api.post(f"/api/runs/{record['id']}/reconcile").get_json()

    assert body["status"] == "succeeded"
    assert len(body["outputs"]) == 1


def test_reconciling_a_run_that_never_went_out_is_a_conflict(empty_api):
    """Nothing to ask the provider about. The fix is to submit it, and saying so
    beats reporting a missing prediction."""
    project = _project(empty_api)
    run = _approved(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/reconcile")

    assert resp.status_code == 409
    assert "nothing was ever sent" in resp.get_json()["error"]


# ── the payload is rebuilt, never re-assembled ──────────────────────────────


def test_the_payload_comes_from_the_plan_and_nothing_else(empty_api):
    """**A payload assembled a second time would be a second opinion.**

    Approving one thing and sending another is the exact gap the digest exists to
    close, so `payload_of` is an allowlist of the plan's two halves rather than a
    denylist of the rest: a field added to the plan later cannot silently become
    part of a payload somebody approved as something else.
    """
    payload = generate.payload_of({"plan": {
        "version": 1,
        "origin": "authored",
        "note": "for the teaser",
        "prompt": "a porch",
        "params": {"aspect_ratio": "3:2"},
    }})

    assert payload == {"prompt": "a porch", "aspect_ratio": "3:2"}


def test_a_start_frame_binds_as_a_scalar_and_references_as_a_list(empty_api):
    """The asymmetry is the provider's, and getting it wrong wedges a draft.

    `reference_images` is an array while `start_image` is a string. Sending a
    one-item list for the latter is a `422 Invalid type` from Replicate — after
    the run has been moved to `pending`, so it wedges rather than failing
    cleanly. Which fields are scalar is registry data, not a guess from the name.
    """
    entry = {"images": {"refs": "reference_images", "start": "start_image"}}
    bindings = generate.bindings_of([
        {"field": "start_image", "node": "node-a", "role": "start"},
        {"field": "reference_images", "node": "node-b", "role": "reference"},
        {"field": "reference_images", "node": "node-c", "role": "reference"},
    ], entry)

    assert bindings == {
        "start_image": "node-a",
        "reference_images": ["node-b", "node-c"],
    }


def test_a_model_the_deployed_registry_does_not_carry_is_a_404(empty_api):
    """A draft written against a newer checkout, submitted against an older
    deploy. The fix is a deploy, which the message should not hide behind
    "internal error"."""
    with pytest.raises(Exception) as raised:
        generate.entry_for({"id": "run-x", "model": "vendor/not-registered"})
    assert "registry" in str(raised.value)


# ── failures, which is the case the reporting has to be good in ─────────────


def test_a_failed_render_keeps_the_tail_of_its_logs(empty_api, media_bucket,
                                                    monkeypatch):
    """**An oversized response used to be dropped whole, and a failure is
    exactly when it is oversized.**

    A video render's `logs` run to megabytes precisely when it went wrong, so the
    old rule discarded the provider's account of the failure in the one case
    somebody needs it — leaving `error[:2000]` as the entire record. The tail is
    kept rather than the head: a render's logs end with the reason it stopped.
    """
    monkeypatch.setattr(config, "max_text_bytes", lambda: 4096)
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "failed",
        "error": "E006: the shot durations do not sum to duration",
        "logs": ("boot " * 5000) + "FINAL LINE: out of memory",
    })

    assert closed["status"] == "failed"
    stored = json.loads(
        empty_api.get(f"/api/nodes/{closed['payload']['response']}/text")
        .get_json()["content"])
    assert "FINAL LINE: out of memory" in stored["logs"]
    assert "dropped by studio" in stored["logs"], "it says it was cut"


def test_a_cancelled_prediction_is_recorded_as_cancelled(empty_api, media_bucket):
    """`canceled` is Replicate's spelling and `cancelled` is studio's. The
    callback filter asks for `completed`, which fires for this too."""
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "canceled"})

    assert closed["status"] == "cancelled"


def test_a_status_the_provider_invents_is_treated_as_a_failure(
        empty_api, media_bucket):
    """**Fail closed.** An unmapped provider word reaching `PATCH /api/runs/<id>`
    would be a 400 on the one call that has to succeed — the only report a paid
    prediction will ever make."""
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "exploded"})

    assert closed["status"] == "failed"


def test_a_close_that_failed_part_way_can_be_retried(empty_api, media_bucket,
                                                     monkeypatch):
    """**A name clash used to make the redrive fail identically, forever.**

    `create_node` refuses a taken name, so a close that stored output 1 and then
    died on output 2 left the run `running` with `image.png` already in the
    folder — and every retry hit the clash and marched a paid generation to the
    dead-letter queue over a filename. Numbering means the retry lands beside the
    stray: one orphan file, which is tidyable, rather than a run that can never
    close.
    """
    project = _project(empty_api)
    record = _running(empty_api, project, name="frame")
    prediction = {"id": record["prediction_id"], "status": "succeeded",
                  "output": ["https://fake.invalid/x/0.png",
                             "https://fake.invalid/x/1.png"]}

    calls = {"n": 0}
    real = generate.replicate.download

    def fail_on_the_second(url, path, *, max_bytes):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("the network went away")
        return real(url, path, max_bytes=max_bytes)

    monkeypatch.setattr(generate.replicate, "download", fail_on_the_second)
    with pytest.raises(RuntimeError):
        generate.close_from_prediction(record, prediction)

    # The run never closed, so a redrive delivers the same callback again.
    monkeypatch.setattr(generate.replicate, "download", real)
    closed = generate.close_from_prediction(
        catalog.entity(catalog.ENTITY_RUN, record["id"]), prediction)

    assert closed["status"] == "succeeded"
    assert len(closed["outputs"]) == 2


# ── the output URL expires, and that is a race the queue can lose ───────────


def test_an_expired_signature_is_retried_against_a_fresh_url(
        empty_api, media_bucket, monkeypatch):
    """**A 403 is an aged signature, not a deleted file**, and they are the same
    at the socket. One more request re-signs the same object, so it is worth
    asking before declaring a paid generation lost."""
    project = _project(empty_api)
    record = _running(empty_api, project)

    calls = {"n": 0}
    real = generate.replicate.download

    def expired_once(url, path, *, max_bytes):
        calls["n"] += 1
        if calls["n"] == 1:
            raise generate.replicate.OutputGone("GET … -> 403")
        return real(url, path, max_bytes=max_bytes)

    monkeypatch.setattr(generate.replicate, "download", expired_once)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"]})

    assert closed["status"] == "succeeded"
    assert len(closed["outputs"]) == 1


def test_an_output_that_is_really_gone_closes_the_run_failed(
        empty_api, media_bucket, monkeypatch):
    """**The run says why, instead of redriving into a dead-letter queue.**

    This used to propagate, so the message went back on the queue to be tried
    against a URL that will never work again — five times, then the DLQ, with the
    run still reading `running` and nobody told anything. A `failed` run naming
    the reason is the outcome somebody can act on.
    """
    def always_gone(*_a, **_kw):
        raise generate.replicate.OutputGone("GET … -> 404")

    monkeypatch.setattr(generate.replicate, "download", always_gone)
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"]})

    assert closed["status"] == "failed"
    assert "no longer available" in closed["error"]
    assert closed["outputs"] == []


def test_a_provider_that_is_merely_unreachable_is_still_retried(
        empty_api, media_bucket, monkeypatch):
    """**Do not confuse "gone" with "cannot ask".** A bad round trip while
    checking for a fresh URL is transient, so it raises and the queue tries
    again — declaring a paid generation lost on one failed request would be the
    expensive mistake."""
    monkeypatch.setattr(generate.replicate, "download",
                        lambda *a, **k: (_ for _ in ()).throw(
                            generate.replicate.OutputGone("GET … -> 403")))
    monkeypatch.setattr(generate.replicate, "get_prediction",
                        lambda _p: (_ for _ in ()).throw(
                            generate.replicate.ReplicateError("connection reset")))
    project = _project(empty_api)
    record = _running(empty_api, project)

    with pytest.raises(generate.replicate.ReplicateError):
        generate.close_from_prediction(record, {
            "id": record["prediction_id"], "status": "succeeded",
            "output": ["https://fake.invalid/x/0.png"]})

    assert catalog.entity(catalog.ENTITY_RUN, record["id"])["status"] == "running"
