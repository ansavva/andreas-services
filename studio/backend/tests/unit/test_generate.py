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

The state machine is tested in `test_runs.py`. What is tested here is that the
submit route sends a draft once, preflights before it declares anything, and
closes what comes back.
"""

import json

import pytest

from studio_core import config
from studio_core.clients import replicate
from studio_core.services import catalog, generate


def _project(api, name="rooftop-teaser"):
    return api.post("/api/projects", json={"name": name}).get_json()


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


# ── a draft is sent once ────────────────────────────────────────────────────


def test_a_draft_is_submitted_directly(empty_api, monkeypatch):
    """**No approve step.** A draft goes straight to the provider on POST.

    Hard rule #2 is kept by whoever calls this — the CLI on an explicit
    `studio runs submit`, the SPA on Send — and the route's part is to send
    what it is handed, once. An edit right before is simply what is sent.
    """
    sent = {}

    def capture(model, payload, *, webhook=None):
        sent["payload"] = payload
        return {"id": "pred-1", "status": "starting"}

    monkeypatch.setattr(replicate, "create_prediction", capture)
    project = _project(empty_api)
    run = _draft(empty_api, project)
    assert "approval" not in run and "plan_digest" not in run
    empty_api.patch(f"/api/runs/{run['id']}/plan", json={
        "plan": {"version": 1, "origin": "authored", "prompt": "a porch at DAWN",
                 "params": {}}})

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["status"] == "running"
    assert sent["payload"]["prompt"] == "a porch at DAWN"


def test_a_run_cannot_be_submitted_twice(empty_api):
    """**The cheapest way to buy the same prediction twice**, refused first.

    A second POST to this route is a duplicate submission whatever else is true
    of the run.
    """
    project = _project(empty_api)
    run = _draft(empty_api, project)
    assert empty_api.post(f"/api/runs/{run['id']}/submit").status_code == 200

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 409
    assert "already been sent" in resp.get_json()["error"]


def test_a_payload_the_model_refuses_leaves_the_run_a_draft(empty_api, monkeypatch):
    """**Preflight runs BEFORE `pending`, and that is the whole of this test.**

    A run moved to `pending` and then refused would read as "went out and never
    answered" — the one state that means a prediction may be billing somewhere.
    A payload the model will not accept has to leave the run exactly as it was:
    a draft, editable, and submittable again once it is fixed.
    """
    monkeypatch.setattr(
        "studio_core.services.schema.fetch",
        lambda model: ({"prompt": {"type": "string"}}, {}),
    )
    project = _project(empty_api)
    run = _draft(empty_api, project, plan={
        "version": 1, "origin": "authored", "prompt": "a porch",
        "params": {"no_such_knob": True},
    })

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 400
    assert "no_such_knob" in resp.get_json()["error"]
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft", "refused before anything was declared"
    # `.get`, because an attribute cleared to `None` is REMOVEd from the row —
    # a record read back has no key at all rather than a null one.
    assert record.get("prediction_id") is None


# ── what a submission does ──────────────────────────────────────────────────


def test_submitting_declares_the_run_then_calls_the_provider(empty_api):
    """`pending` before the provider, `running` with the prediction id after.

    The order is the safety: the transition out of `draft` happens first, so a
    process that dies in between leaves a row that says a submission went out —
    rather than a draft that says nothing happened.
    """
    project = _project(empty_api)
    run = _draft(empty_api, project)

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert body["status"] == "running"
    assert body["prediction_id"].startswith("fake")
    assert body["submitted"], "a submitted run says when"


def test_a_submitted_run_is_counted_once(empty_api):
    """A draft is not a run the project made. The transition out of it is."""
    project = _project(empty_api)
    before = empty_api.get(f"/api/projects/{project['id']}").get_json()
    run = _draft(empty_api, project)

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

    run = _draft(empty_api, project)
    assert empty_api.post(f"/api/runs/{run['id']}/submit").get_json()["callback"] == "poll"

    monkeypatch.setenv("STUDIO_WEBHOOK_BASE_URL", "https://callbacks.example")
    other = _draft(empty_api, project, plan={
        "version": 1, "origin": "authored", "prompt": "a different porch",
        "params": {}})
    assert empty_api.post(f"/api/runs/{other['id']}/submit").get_json()["callback"] == "webhook"


def test_a_webhook_url_is_never_part_of_the_payload(empty_api, monkeypatch):
    """**It is a sibling of `input`, not a field in it**, and both halves matter.

    Inside `input` it would be a field the model's schema rejects, and — worse —
    a change to the payload after somebody read it.
    """
    monkeypatch.setenv("STUDIO_WEBHOOK_BASE_URL", "https://callbacks.example")
    sent = {}

    def capture(model, payload, *, webhook=None):
        sent["payload"], sent["webhook"] = payload, webhook
        return {"id": "pred-1", "status": "starting"}

    monkeypatch.setattr(replicate, "create_prediction", capture)
    project = _project(empty_api)
    run = _draft(empty_api, project)

    empty_api.post(f"/api/runs/{run['id']}/submit")

    assert sent["webhook"] == f"https://callbacks.example/api/hooks/replicate/{run['id']}"
    assert "webhook" not in sent["payload"]
    assert sent["payload"] == {"prompt": "a porch at dusk"}


# ── the provider says no, or says nothing ───────────────────────────────────


def test_a_refused_submission_closes_the_run_failed(empty_api, monkeypatch):
    """**A 4xx is an answer, and the answer is no.** Three runs sat at `pending`
    over Runpod's `402 insufficient balance` with nothing in flight, nothing
    the SPA could press, and a spinner where the reason should have been. The
    provider's words land in `error`; the caller still gets the 502.
    """
    def refuse(model, payload, *, webhook=None):
        raise replicate.ReplicateError(
            "POST … -> 402: {…}", status=402, detail="insufficient balance")

    monkeypatch.setattr(replicate, "create_prediction", refuse)
    project = _project(empty_api)
    run = _draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "failed"
    assert record["error"] == (
        "replicate refused the submission (402): insufficient balance")
    assert record["completed"]
    assert record.get("prediction_id") is None
    listing = empty_api.get(f"/api/runs?project={project['id']}").get_json()
    assert [r["status"] for r in listing["runs"]] == ["failed"], \
        "the grid row moved with the envelope"


def test_a_silent_submission_stays_pending(empty_api, monkeypatch):
    """**No status means nothing is known**, and `pending` with no prediction
    id is the honest row: a request that timed out on the way out may still
    have been queued and billed, and `failed` over a live job would be a lie
    the callback later contradicts. A 5xx is the same case — a proxy's 502
    does not say whether the queue behind it took the job."""
    def vanish(model, payload, *, webhook=None):
        raise replicate.ReplicateError("POST … failed: timed out")

    monkeypatch.setattr(replicate, "create_prediction", vanish)
    project = _project(empty_api)
    run = _draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "pending"
    assert "error" not in record

    def broken(model, payload, *, webhook=None):
        raise replicate.ReplicateError("POST … -> 503: {…}", status=503,
                                       detail="try later")

    monkeypatch.setattr(replicate, "create_prediction", broken)
    other = _draft(empty_api, project)
    empty_api.post(f"/api/runs/{other['id']}/submit")
    assert catalog.entity(catalog.ENTITY_RUN, other["id"])["status"] == "pending"


def test_a_refusal_carries_the_providers_own_words(monkeypatch):
    """`_detail` reads the problem document both providers answer with, so a
    run's `error` says `insufficient balance` rather than a URL and a blob."""
    from studio_core.clients import runpod
    assert runpod._detail(
        '{"status":402,"title":"Insufficient Balance","detail":"insufficient balance"}'
    ) == "insufficient balance"
    assert runpod._detail('{"title":"Unauthorized"}') == "Unauthorized"
    assert runpod._detail("<html>gateway</html>") == "<html>gateway</html>"
    assert runpod._detail("") == "no detail"
    assert replicate._detail('{"detail":"Invalid type. Expected: string"}') == (
        "Invalid type. Expected: string")


# ── closing ────────────────────────────────────────────────────────────────


def _running(empty_api, project, **body):
    run = _draft(empty_api, project, **body)
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
    run = _draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/reconcile")

    assert resp.status_code == 409
    assert "nothing was ever sent" in resp.get_json()["error"]


# ── the payload is rebuilt, never re-assembled ──────────────────────────────


def test_the_payload_comes_from_the_plan_and_nothing_else(empty_api):
    """**A payload assembled a second time would be a second opinion.**

    Reading one thing and sending another is the gap this closes, so
    `payload_of` is an allowlist of the plan's two halves rather than a denylist
    of the rest: a field added to the plan later cannot silently become part of
    a payload somebody read as something else.
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
                        lambda _p, **_k: (_ for _ in ()).throw(
                            generate.replicate.ReplicateError("connection reset")))
    project = _project(empty_api)
    record = _running(empty_api, project)

    with pytest.raises(generate.replicate.ReplicateError):
        generate.close_from_prediction(record, {
            "id": record["prediction_id"], "status": "succeeded",
            "output": ["https://fake.invalid/x/0.png"]})

    assert catalog.entity(catalog.ENTITY_RUN, record["id"])["status"] == "running"


# ── hard rule #3, at the one place it had quietly stopped holding ───────────


def _uploaded(api, parent_id, name, body=b"webp-bytes"):
    """A node with bytes behind it, so a send may legitimately name it."""
    node = api.post(
        "/api/nodes", json={"parent": parent_id, "name": name, "kind": "file"}
    ).get_json()
    record = catalog.node(node["id"])
    return catalog.set_blob(
        node["id"], record["blob_key"], size=len(body), content_type="image/webp"
    )


def _with_sends(api, project, nodes):
    run = _draft(api, project, sends=[
        {"field": "image_input", "role": "reference", "node": node}
        for node in nodes
    ])
    api.post(f"/api/runs/{run['id']}/submit")
    return catalog.entity(catalog.ENTITY_RUN, run["id"])


def test_the_stored_response_holds_node_ids_where_signed_urls_were(
        empty_api, media_bucket):
    """**A callback echoes the payload back, presigned URLs and all.**

    Storing it verbatim filed a set of working credentials for the library inside
    the run's own folder — short-lived, and readable by anyone who could already
    read the run, but hard rule #3 says a signed URL is never stored and it was
    being stored.

    Substituted rather than redacted: the node id is what a reader of
    `response.json` actually wants, and the ordered `SEND#` rows are the same
    ones `dispatch` presigned, so position lines up by construction.
    """
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    first = _uploaded(empty_api, root, "one.webp")
    second = _uploaded(empty_api, root, "two.webp")
    record = _with_sends(empty_api, project, [first["node_id"], second["node_id"]])

    generate.close_from_prediction(record, {
        "id": record["prediction_id"],
        "status": "succeeded",
        "output": ["https://replicate.delivery/pbxt/abc/0.png"],
        # What Replicate really sends back: the payload it was given.
        "input": {
            "prompt": "a porch at dusk",
            "image_input": [
                "https://studio-prod-media.s3.amazonaws.com/blobs/x?X-Amz-Signature=deadbeef",
                "https://studio-prod-media.s3.amazonaws.com/blobs/y?X-Amz-Signature=cafe",
            ],
        },
    })

    closed = catalog.entity(catalog.ENTITY_RUN, record["id"])
    stored = json.loads(
        empty_api.get(f"/api/nodes/{closed['payload']['response']}/text")
        .get_json()["content"])

    assert stored["input"]["image_input"] == [first["node_id"], second["node_id"]]
    assert "X-Amz-Signature" not in json.dumps(stored["input"])
    # The prompt is untouched: this rewrites URLs, not the document.
    assert stored["input"]["prompt"] == "a porch at dusk"


def test_the_providers_own_output_urls_are_kept(empty_api, media_bucket):
    """**`output` is not ours and is deliberately left alone.**

    Those URLs grant nothing in this library and are the only record of what the
    model actually returned — which is why the pipeline kept them as debugging
    material before any of this moved. The rule is about *our* signatures.
    """
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"]})

    stored = json.loads(
        empty_api.get(f"/api/nodes/{closed['payload']['response']}/text")
        .get_json()["content"])
    assert stored["output"] == ["https://fake.invalid/x/0.png"]


def test_a_url_that_cannot_be_mapped_is_replaced_rather_than_left(
        empty_api, media_bucket):
    """**Fail toward removal.** A field this service cannot account for is the
    one case where guessing wrong leaves a live URL in the document."""
    project = _project(empty_api)
    record = _running(empty_api, project)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"],
        "input": {"some_field_with_no_send": "https://example.test/signed?sig=abc"},
    })

    stored = json.loads(
        empty_api.get(f"/api/nodes/{closed['payload']['response']}/text")
        .get_json()["content"])
    assert stored["input"]["some_field_with_no_send"] == (
        "[a presigned URL studio did not store]")


# ─────────────── a scalar field named by more than one send ───────────────

VEO = {"model": "google/veo-3.1", "kind": "video",
       "images": {"start": "image", "end": "last_frame",
                  "refs": "reference_images", "max_refs": 3}}


def test_a_scalar_image_field_named_TWICE_is_refused_rather_than_dropped():
    """**It was dropped, silently, and that is the bug this exists for.**

    `bindings_of` keeps the first send for a scalar field and discards the rest,
    because a start frame is a string and a list is a 422 from the provider.
    Right for one send and a lie for several: a run bound a start frame and five
    of a character's reference photographs, every one naming `image` because the
    editor copied the field off the row above, and the payload went out with one
    image and no `reference_images` at all. Six rows on screen, one image sent.
    """
    sends = [{"field": "image", "role": "start", "node": "node-a"}]
    sends += [{"field": "image", "role": "reference", "node": f"node-{n}"}
              for n in "bcde"]

    with pytest.raises(Exception) as refusal:
        generate.preflight(VEO, {"prompt": "x"},
                           generate.bindings_of(sends, VEO), sends)

    said = str(refusal.value)
    assert "'image'" in said and "5 sends" in said
    # And it says where they should have gone.
    assert "reference_images" in said


def test_ONE_send_on_a_scalar_field_is_exactly_right():
    sends = [{"field": "image", "role": "start", "node": "node-a"},
             {"field": "reference_images", "role": "reference", "node": "node-b"}]
    bindings = generate.bindings_of(sends, VEO)
    generate._check_scalar_fields(VEO, sends)
    assert bindings["image"] == "node-a"
    assert bindings["reference_images"] == ["node-b"]


def test_a_model_with_no_reference_input_says_so_instead():
    entry = {"model": "x/y", "kind": "video", "images": {"start": "image"}}
    sends = [{"field": "image", "role": "start", "node": "node-a"},
             {"field": "image", "role": "reference", "node": "node-b"}]
    with pytest.raises(Exception) as refusal:
        generate._check_scalar_fields(entry, sends)
    assert "takes no reference images" in str(refusal.value)


def test_a_start_frame_and_references_TOGETHER_are_refused_when_the_model_says_so():
    """**The registry has said this since it was written and nothing read it.**

    `start_excludes_refs` and `end_excludes_refs` were data with no enforcement
    anywhere, so a Veo run went out carrying both and came back
    `{'code': 3, 'message': 'Image and reference images cannot be both set.'}` —
    a constraint the entry could have stated and the preflight could have caught
    for nothing, after the run had already left `pending`.
    """
    entry = {"model": "google/veo-3.1", "kind": "video",
             "images": {"start": "image", "refs": "reference_images",
                        "start_excludes_refs": True, "max_refs": 3}}
    bindings = {"image": "node-a", "reference_images": ["node-b"]}

    with pytest.raises(Exception) as refusal:
        generate._check_exclusive_images(entry, bindings)
    said = str(refusal.value)
    assert "'image'" in said and "'reference_images'" in said


def test_either_one_ALONE_is_fine():
    entry = {"model": "google/veo-3.1", "kind": "video",
             "images": {"start": "image", "refs": "reference_images",
                        "start_excludes_refs": True}}
    generate._check_exclusive_images(entry, {"image": "node-a"})
    generate._check_exclusive_images(entry, {"reference_images": ["node-b"]})


def test_a_model_that_allows_BOTH_still_does():
    entry = {"model": "x/y", "kind": "video",
             "images": {"start": "start_image", "refs": "reference_images",
                        "start_excludes_refs": False}}
    generate._check_exclusive_images(
        entry, {"start_image": "node-a", "reference_images": ["node-b"]})


# ── the clip: the one video a model works from ──────────────────────────────


MOTION = {"model": "kwaivgi/kling-v3-motion-control", "kind": "video",
          "images": {"start": "image", "refs": None, "max_refs": 0},
          "clips": {"source": "video", "accepts_ext": [".mp4", ".mov"]}}


def test_a_clip_binds_as_a_scalar_like_a_frame():
    """`video` is a string on every model that has one; a one-item list is a 422
    from the provider after `pending`. Which field is the clip is registry data
    (`clips.source`), read by the same helper that collapses the frames."""
    sends = [{"field": "image", "role": "start", "node": "node-a"},
             {"field": "video", "role": "clip", "node": "node-b"}]
    bindings = generate.bindings_of(sends, MOTION)
    generate._check_scalar_fields(MOTION, sends)
    assert bindings == {"image": "node-a", "video": "node-b"}


def test_two_sends_on_the_clip_field_are_refused_rather_than_dropped():
    sends = [{"field": "video", "role": "clip", "node": "node-a"},
             {"field": "video", "role": "clip", "node": "node-b"}]
    with pytest.raises(Exception) as refusal:
        generate._check_scalar_fields(MOTION, sends)
    assert "'video'" in str(refusal.value) and "2 sends" in str(refusal.value)


def test_clip_is_a_role_a_send_may_carry(empty_api):
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    still = _uploaded(empty_api, root, "a.png")
    clip = _uploaded(empty_api, root, "b.mp4")
    run = _draft(empty_api, project, sends=[
        {"field": "image", "role": "start", "node": still["node_id"]},
        {"field": "video", "role": "clip", "node": clip["node_id"]},
    ])
    assert [s["role"] for s in run["sends"]] == ["start", "clip"]


def test_a_missing_required_input_is_refused_before_pending(empty_api, monkeypatch):
    """The provider checks `required` too — after the run has moved to
    `pending`, so a motion-control run drafted without its clip wedged instead
    of failing. The schema's own `required` list is read here, and a required
    field is satisfied by a payload value OR a binding."""
    monkeypatch.setattr(
        "studio_core.services.schema.fetch",
        lambda model: (
            {"prompt": {"type": "string"}, "image": {"type": "string"},
             "video": {"type": "string"}},
            {"Input": {"required": ["image", "video"]}},
        ),
    )
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    still = _uploaded(empty_api, root, "a.png")
    run = _draft(empty_api, project, sends=[
        {"field": "image", "role": "start", "node": still["node_id"]},
    ])

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 400
    assert "requires ['video']" in resp.get_json()["error"]
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "draft"


def test_a_required_input_met_by_a_binding_passes():
    from studio_core.services import schema
    props = {"prompt": {"type": "string"}, "image": {"type": "string"},
             "video": {"type": "string"}}
    schemas = {"Input": {"required": ["image", "video"]}}
    schema.check({"prompt": "x"}, {"image": "node-a", "video": "node-b"},
                 "kwaivgi/kling-v3-motion-control", props, schemas)


# ── the second provider ─────────────────────────────────────────────────────
#
# A run whose registry entry says `provider: runpod` goes to Runpod's public
# endpoint through `clients/runpod.py`, and everything above — the transition,
# the preflight, the one closing implementation — is the same code. What is
# tested here is the seam: the right client is chosen, the run records which,
# and the registry entry stands in for the live schema Runpod does not publish.


def _runpod_draft(api, project, **body):
    resp = api.post("/api/runs", json={
        "project": project["id"],
        "kind": "image",
        "engine": "z-image-turbo",
        "model": "runpod/z-image-turbo",
        "plan": {"version": 1, "origin": "authored", "prompt": "a porch at dusk",
                 "params": {"size": "512*512", "seed": 42}},
        **body,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def test_a_runpod_run_is_submitted_through_the_runpod_client(empty_api, monkeypatch):
    """`dispatch` picks the client off the entry's `provider`, and the route
    records it on the run before anything is sent."""
    from studio_core.clients import runpod
    seen = {}

    def create(model, payload, *, webhook=None):
        seen.update(model=model, payload=payload, webhook=webhook)
        return {"id": "job-1-u1", "status": "IN_QUEUE"}

    monkeypatch.setattr(runpod, "create_prediction", create)
    monkeypatch.setattr(replicate, "create_prediction",
                        lambda *a, **k: pytest.fail("Replicate was called"))
    project = _project(empty_api)
    run = _runpod_draft(empty_api, project)

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert seen["model"] == "runpod/z-image-turbo"
    assert seen["payload"] == {"size": "512*512", "seed": 42, "prompt": "a porch at dusk"}
    assert body["status"] == "running"
    assert body["provider"] == "runpod"
    assert body["prediction_id"] == "job-1-u1"


def test_a_runpod_run_reconciles_through_the_runpod_client(empty_api, media_bucket):
    """The fake answers `COMPLETED` with `output.result`, and the run closes
    with a real price rather than a duration."""
    project = _project(empty_api)
    run = _runpod_draft(empty_api, project)
    empty_api.post(f"/api/runs/{run['id']}/submit")

    body = empty_api.post(f"/api/runs/{run['id']}/reconcile").get_json()

    assert body["status"] == "succeeded"
    assert len(body["outputs"]) == 1
    assert body["cost"]["currency"] == "USD"


def test_a_runpod_payload_is_checked_against_the_entry_before_pending(empty_api):
    """Runpod publishes no schema, so the entry's `input` block is the schema:
    a size not in its enum is refused, and the run stays a draft."""
    project = _project(empty_api)
    run = _runpod_draft(empty_api, project, plan={
        "version": 1, "origin": "authored", "prompt": "a porch",
        "params": {"size": "4096*4096"}})

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 400
    assert "size='4096*4096' is not one of" in resp.get_json()["error"]
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "draft"


def test_a_runpod_run_with_no_prompt_is_refused(empty_api):
    project = _project(empty_api)
    run = _runpod_draft(empty_api, project, plan={
        "version": 1, "origin": "authored", "prompt": None, "params": {}})

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 400
    assert "requires ['prompt']" in resp.get_json()["error"]


def test_the_schema_route_serves_a_runpod_entry_from_the_registry(empty_api):
    """What `studio models show` and `models refresh` read for this model —
    the same document `preflight` validates against."""
    body = empty_api.get("/api/models/z-image-turbo/schema").get_json()

    assert body["model"] == "runpod/z-image-turbo"
    assert "1024*1024" in body["props"]["size"]["enum"]
    assert body["schemas"]["Input"]["required"] == ["prompt"]


def test_the_readme_route_answers_for_a_runpod_entry_without_a_provider_call(empty_api):
    body = empty_api.get("/api/models/z-image-turbo/readme").get_json()

    assert body["readme"].startswith("# runpod/z-image-turbo")
    assert "$0.005" in body["readme"]


def test_a_run_written_before_provider_existed_is_replicates():
    assert generate.provider_of({"model": "google/nano-banana-pro"}) == "replicate"
    assert generate.provider_of({"model": "runpod/z-image-turbo"}) == "runpod"
    assert generate.provider_of({"model": "runpod/x", "provider": "replicate"}) == "replicate"


def test_runpod_output_and_cost_are_read_off_the_public_endpoint_shape():
    from studio_core.clients import runpod
    job = {"id": "j", "status": "COMPLETED", "executionTime": 5706,
           "output": {"cost": 0.005, "result": "https://x.invalid/r.png"}}

    assert runpod.output_urls(job) == ["https://x.invalid/r.png"]
    assert runpod.cost(job) == {"amount": 0.005, "currency": "USD", "predict_time": 5.706}
    assert runpod.output_urls({"output": ["https://x.invalid/a", "https://x.invalid/b"]}) == [
        "https://x.invalid/a", "https://x.invalid/b"]
    assert runpod.cost({"status": "FAILED"}) is None
    # The video endpoints spell it `video_url`. Same document otherwise.
    clip = {"output": {"video_url": "https://x.invalid/out.mp4", "cost": 0.5}}
    assert runpod.output_urls(clip) == ["https://x.invalid/out.mp4"]
    assert runpod.output_urls({"output": {"cost": 0.5}}) == []


def _wan_draft(api, project, **body):
    resp = api.post("/api/runs", json={
        "project": project["id"],
        "kind": "video",
        "engine": "wan-2.6-t2v",
        "model": "runpod/wan-2-6-t2v",
        "plan": {"version": 1, "origin": "authored",
                 "prompt": "a lighthouse on a rocky coast at golden hour, waves breaking",
                 "params": {"duration": 5, "size": "1280*720", "seed": 7}},
        **body,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def test_a_runpod_video_run_submits_imageless_and_closes_on_video_url(
        empty_api, media_bucket, monkeypatch):
    """`wan-2.6-t2v` is the first video entry with no image field at all, and the
    first whose output arrives as `video_url`: the draft is accepted with no
    sends, the payload is the plan and nothing else, and the closing reads the
    clip off the video key, names it by the URL's extension and records the
    price the endpoint quoted."""
    from studio_core.clients import runpod
    from studio_core.services import catalog
    seen = {}

    def create(model, payload, *, webhook=None):
        seen.update(model=model, payload=payload)
        return {"id": "job-wan-u1", "status": "IN_QUEUE"}

    monkeypatch.setattr(runpod, "create_prediction", create)
    project = _project(empty_api)
    run = _wan_draft(empty_api, project)
    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert seen["model"] == "runpod/wan-2-6-t2v"
    assert seen["payload"] == {"duration": 5, "size": "1280*720", "seed": 7,
                               "prompt": "a lighthouse on a rocky coast at golden hour, waves breaking"}
    assert body["provider"] == "runpod"

    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    closed = generate.close_from_prediction(record, {
        "id": "job-wan-u1", "status": "COMPLETED", "executionTime": 85432,
        "output": {"video_url": "https://x.invalid/abc/output.mp4", "cost": 0.5},
    })

    assert closed["status"] == "succeeded"
    assert closed["cost"] == {"amount": 0.5, "currency": "USD", "predict_time": 85.432}
    assert catalog.node(closed["outputs"][0])["name"].endswith(".mp4")


LORA = {"model": "runpod/wan-2-2-t2v-720-lora", "kind": "video", "key": "wan-2.2-i2v-lora",
        "images": {"start": "image", "refs": None, "max_refs": None},
        "loras": {"high": "high_noise_loras", "low": "low_noise_loras",
                  "accepts_ext": [".safetensors"], "scale_param": "lora_scale"}}


def test_a_lora_send_goes_out_as_path_and_scale_and_the_scale_never_by_name(
        empty_api, media_bucket, monkeypatch):
    """The endpoint wants `[{path, scale}]` per stage and has no top-level
    strength field; the plan carries `lora_scale` as one number. `dispatch`
    presigns each bound node into an object with that scale and drops the
    param, so the provider never sees a field it does not have."""
    from studio_core.clients import runpod
    seen = {}
    monkeypatch.setattr(runpod, "create_prediction",
                        lambda model, payload, *, webhook=None:
                        (seen.update(payload=payload) or {"id": "job-lora-u1", "status": "IN_QUEUE"}))
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    still = _uploaded(empty_api, root, "frame.png")
    high = _uploaded(empty_api, root, "orbit_high.safetensors")
    low = _uploaded(empty_api, root, "orbit_low.safetensors")
    resp = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": "wan-2.2-i2v-lora",
        "model": "runpod/wan-2-2-t2v-720-lora",
        "plan": {"version": 1, "origin": "authored", "prompt": "orbit 180 around him",
                 "params": {"duration": 5, "seed": 3, "lora_scale": 0.8}},
        "sends": [
            {"field": "image", "role": "start", "node": still["node_id"]},
            {"field": "high_noise_loras", "role": "lora", "node": high["node_id"]},
            {"field": "low_noise_loras", "role": "lora", "node": low["node_id"]},
        ],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    run = resp.get_json()
    assert [s["role"] for s in run["sends"]] == ["start", "lora", "lora"]

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()
    assert body["status"] == "running", body

    payload = seen["payload"]
    assert "lora_scale" not in payload
    assert payload["duration"] == 5 and payload["seed"] == 3
    assert payload["image"].startswith("http")
    for field in ("high_noise_loras", "low_noise_loras"):
        assert len(payload[field]) == 1
        assert payload[field][0]["scale"] == 0.8
        assert payload[field][0]["path"].startswith("http")

    # The stored echo of `input` names the nodes again, inside the objects.
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    unsigned = generate._unsigned_input(record, {"input": payload})["input"]
    assert unsigned["high_noise_loras"] == [{"path": high["node_id"], "scale": 0.8}]
    assert unsigned["low_noise_loras"] == [{"path": low["node_id"], "scale": 0.8}]
    assert unsigned["image"] == still["node_id"]


def test_the_wan_i2v_entry_speaks_the_workers_schema_not_the_docs():
    """Runpod's page for `wan-2-6-i2v` documents `size` as W*H; the worker's
    pydantic model takes `resolution` in 720p/1080p and requires `shot_type`.
    A prod run sent `size: 1920*1080` off the docs and failed after `pending`.
    The entry is pinned to what the worker said, so the docs cannot creep back."""
    from studio_core.services import registry
    entry = registry.get("wan-2.6-i2v")
    props = entry["input"]["properties"]
    assert "size" not in props
    assert props["resolution"]["enum"] == ["720p", "1080p"]
    assert "shot_type" in entry["input"]["required"]
    assert entry["defaults"] == {"shot_type": "single"}
    # And the sheet seeds it: the snapshot carries the default the worker lacks.
    assert entry["snapshot"]["shot_type"]["default"] == "single"


def test_lora_fields_are_read_off_the_entry_and_nothing_else():
    from studio_core.services import registry
    assert registry.lora_fields(LORA) == {"high_noise_loras", "low_noise_loras"}
    assert registry.lora_scale_param(LORA) == "lora_scale"
    assert registry.lora_fields(MOTION) == set()
    assert registry.lora_scale_param(MOTION) is None


def test_a_runpod_video_payload_is_refused_off_the_entry_before_pending(empty_api):
    """A `duration` the endpoint does not sell is refused against the entry's
    own `input` block — the registry is the schema — and the draft stays a draft."""
    project = _project(empty_api)
    run = _wan_draft(empty_api, project, plan={
        "version": 1, "origin": "authored", "prompt": "x",
        "params": {"duration": 7}})
    resp = empty_api.post(f"/api/runs/{run['id']}/submit")
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["status"] == "draft"


def test_the_stored_runpod_document_carries_no_callback_signature(empty_api, media_bucket):
    """Runpod echoes the webhook URL it was told, `?sig=` included. The stored
    document keeps the URL and drops the proof."""
    from studio_core.clients.aws import s3
    project = _project(empty_api)
    run = _runpod_draft(empty_api, project)
    empty_api.post(f"/api/runs/{run['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "COMPLETED", "executionTime": 10,
        "output": {"cost": 0.005, "result": "https://fake.invalid/r.png"},
        "webhook": "https://hooks.test/api/hooks/runpod/" + run["id"] + "?sig=deadbeef",
    })

    stored = s3.get_body(catalog.node(closed["payload"]["response"])["blob_key"], 1 << 20).decode()
    assert "deadbeef" not in stored
    assert "https://hooks.test/api/hooks/runpod/" in stored


# ── the third provider: fal ─────────────────────────────────────────────────


def _wan3_draft(api, project, **body):
    resp = api.post("/api/runs", json={
        "project": project["id"],
        "kind": "video",
        "engine": "wan-3.0-t2v",
        "model": "fal/alibaba/wan-3.0/text-to-video",
        "plan": {"version": 1, "origin": "authored",
                 "prompt": "a lighthouse on a rocky coast at golden hour, waves breaking",
                 "params": {"duration": 5, "resolution": "720p", "seed": 7}},
        **body,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def test_a_fal_run_is_submitted_through_the_fal_client(empty_api, monkeypatch):
    """`dispatch` picks the client off the entry's `provider`; the route records
    `fal` on the run before anything is sent; the webhook URL is bare, because
    fal signs its callbacks itself."""
    from studio_core.clients import fal, runpod
    seen = {}

    def create(model, payload, *, webhook=None):
        seen.update(model=model, payload=payload, webhook=webhook)
        return {"id": "req-1", "status": "IN_QUEUE"}

    monkeypatch.setattr(fal, "create_prediction", create)
    monkeypatch.setattr(replicate, "create_prediction",
                        lambda *a, **k: pytest.fail("Replicate was called"))
    monkeypatch.setattr(runpod, "create_prediction",
                        lambda *a, **k: pytest.fail("Runpod was called"))
    monkeypatch.setenv("STUDIO_WEBHOOK_BASE_URL", "https://hooks.test")
    project = _project(empty_api)
    run = _wan3_draft(empty_api, project)

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert seen["model"] == "fal/alibaba/wan-3.0/text-to-video"
    assert seen["payload"] == {"duration": 5, "resolution": "720p", "seed": 7,
                               "prompt": "a lighthouse on a rocky coast at golden hour, waves breaking"}
    assert seen["webhook"] == f"https://hooks.test/api/hooks/fal/{run['id']}"
    assert body["status"] == "running"
    assert body["provider"] == "fal"
    assert body["prediction_id"] == "req-1"


def test_a_fal_run_reconciles_through_the_fal_client(empty_api, media_bucket):
    """The fake answers a completed request in fal's own shape — `payload.video.url`
    — and the run closes on it, with no price: fal's body carries none."""
    project = _project(empty_api)
    run = _wan3_draft(empty_api, project)
    empty_api.post(f"/api/runs/{run['id']}/submit")

    body = empty_api.post(f"/api/runs/{run['id']}/reconcile").get_json()

    assert body["status"] == "succeeded"
    assert len(body["outputs"]) == 1
    assert body["outputs"][0]["name"].endswith(".mp4")
    assert body.get("cost") is None


def test_provider_of_infers_fal_from_the_model_id():
    assert generate.provider_of({"model": "fal/alibaba/wan-3.0/text-to-video"}) == "fal"
    assert generate.provider_of({"model": "fal/x", "provider": "replicate"}) == "replicate"


def test_fal_documents_are_normalised_into_the_seams_shape():
    """A webhook body is `request_id` / `status: OK|ERROR` / `payload`; the
    closing code reads `id` / `status` / `output` / `error`. A document already
    in that shape passes through, so the call is safe to repeat."""
    from studio_core.clients import fal

    ok = fal.normalise({"request_id": "r1", "gateway_request_id": "g", "status": "OK",
                        "payload": {"video": {"url": "https://x.invalid/v.mp4"},
                                    "seed": 3, "duration": 5.0}})
    assert ok == {"id": "r1", "status": "OK",
                  "output": {"video": {"url": "https://x.invalid/v.mp4"}, "seed": 3, "duration": 5.0},
                  "error": None}
    assert fal.output_urls(ok) == ["https://x.invalid/v.mp4"]
    assert fal.cost(ok) is None

    failed = fal.normalise({"request_id": "r2", "status": "ERROR", "error": "content policy",
                            "payload": {"detail": "…"}})
    assert failed["status"] == "ERROR" and failed["output"] is None
    assert failed["error"] == "content policy"

    # fal could not serialise the model's answer: nothing to download, so a
    # failure whatever `status` says.
    broken = fal.normalise({"request_id": "r3", "status": "OK", "payload": None,
                            "payload_error": "Response payload is not JSON serializable"})
    assert broken["status"] == "ERROR"
    assert "not JSON serializable" in broken["error"]

    assert fal.normalise(ok) == ok
    # The other shapes an endpoint may answer.
    assert fal.output_urls({"output": {"images": [{"url": "https://x.invalid/a.png"},
                                                  {"url": "https://x.invalid/b.png"}]}}) == [
        "https://x.invalid/a.png", "https://x.invalid/b.png"]
    assert fal.output_urls({"output": {"video": "https://x.invalid/bare.mp4"}}) == [
        "https://x.invalid/bare.mp4"]
    assert fal.output_urls({"output": {"seed": 1}}) == []
    assert fal.cost({"id": "r", "status": "OK", "metrics": {"inference_time": 41.2}}) == {
        "amount": None, "currency": None, "predict_time": 41.2}


def test_a_fal_error_document_closes_the_run_failed(empty_api, media_bucket):
    project = _project(empty_api)
    run = _wan3_draft(empty_api, project)
    empty_api.post(f"/api/runs/{run['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    from studio_core.clients import fal

    closed = generate.close_from_prediction(record, fal.normalise({
        "request_id": record["prediction_id"], "status": "ERROR",
        "error": "Input validation failed: duration must be between 2 and 30",
    }))

    assert closed["status"] == "failed"
    assert "duration" in closed["error"]


def test_the_fal_schema_reader_flattens_nullable_fields_and_names_the_input(monkeypatch):
    """fal's OpenAPI spells every optional field `anyOf: [X, null]`, and
    `services/schema.check` range-checks only a top-level `type`/`minimum`/
    `maximum` — so `duration` 2–30 would go unchecked unflattened. The input
    component is the one the submit route's request body names, returned under
    `Input` too because that is where `check` reads `required`."""
    from studio_core.clients import fal

    document = {
        "paths": {"/alibaba/wan-3.0/text-to-video": {"post": {"requestBody": {"content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Wan30TextToVideoInput"}}}}}}},
        "components": {"schemas": {
            "Wan30TextToVideoInput": {"required": ["prompt"], "properties": {
                "prompt": {"type": "string"},
                "duration": {"anyOf": [{"type": "integer", "minimum": 2, "maximum": 30},
                                       {"type": "null"}], "default": 5},
                "resolution": {"type": "string", "enum": ["480p", "720p", "1080p"]},
            }},
            "Wan30TextToVideoOutput": {"properties": {"video": {}}},
        }},
    }
    monkeypatch.setenv("STUDIO_FAL_MODE", "live")
    monkeypatch.setattr(fal, "_request", lambda *a, **k: (200, document))

    props, schemas = fal.model_schema("fal/alibaba/wan-3.0/text-to-video")

    assert props["duration"] == {"type": "integer", "minimum": 2, "maximum": 30, "default": 5}
    assert schemas["Input"]["required"] == ["prompt"]
    assert schemas["Input"]["properties"] is props
    assert "Wan30TextToVideoOutput" in schemas


def test_the_fal_client_reads_the_result_after_the_status(monkeypatch):
    """Two calls once the queue is done: the status carries no output, the result
    route does — and an HTTP error from the result route is the request's own
    failure, except a bad key or a rate limit, which raise so the queue retries.
    Both calls go to the app's routes, not the endpoint's."""
    from studio_core.clients import fal
    calls = []

    def answer(method, url, **kw):
        calls.append(url)
        if url.endswith("/status"):
            return 200, {"status": "COMPLETED", "metrics": {"inference_time": 12.5}}
        return 200, {"video": {"url": "https://x.invalid/v.mp4"}, "seed": 1, "duration": 5}

    monkeypatch.setenv("STUDIO_FAL_MODE", "live")
    monkeypatch.setattr(fal, "_request", answer)

    got = fal.get_prediction("req-9", model="fal/alibaba/wan-3.0/text-to-video")

    # The APP's request routes, not the endpoint's: the third path segment is
    # a route inside the app, and answers 405 to a status GET.
    assert calls == ["https://queue.fal.run/alibaba/wan-3.0/requests/req-9/status",
                     "https://queue.fal.run/alibaba/wan-3.0/requests/req-9"]
    assert got["id"] == "req-9" and got["status"] == "OK"
    assert fal.output_urls(got) == ["https://x.invalid/v.mp4"]
    assert fal.cost(got) == {"amount": None, "currency": None, "predict_time": 12.5}

    monkeypatch.setattr(fal, "_request", lambda m, u, **k: (200, {"status": "IN_PROGRESS"}))
    assert fal.get_prediction("req-9", model="fal/x")["status"] == "IN_PROGRESS"

    def failed(method, url, **kw):
        if url.endswith("/status"):
            return 200, {"status": "COMPLETED"}
        return 422, {"detail": [{"loc": ["body", "duration"], "msg": "too long"}]}
    monkeypatch.setattr(fal, "_request", failed)
    got = fal.get_prediction("req-9", model="fal/x")
    assert got["status"] == "ERROR" and "body.duration: too long" in got["error"]

    def unauthorised(method, url, **kw):
        if url.endswith("/status"):
            return 200, {"status": "COMPLETED"}
        return 401, {"detail": "Invalid key"}
    monkeypatch.setattr(fal, "_request", unauthorised)
    with pytest.raises(fal.FalError):
        fal.get_prediction("req-9", model="fal/x")


def test_the_fal_submit_puts_the_webhook_in_the_query_and_the_payload_bare(monkeypatch):
    from studio_core.clients import fal
    seen = {}

    def answer(method, url, *, body=None, **kw):
        seen.update(method=method, url=url, body=body)
        return 200, {"request_id": "req-2", "status": "IN_QUEUE", "queue_position": 0}

    monkeypatch.setenv("STUDIO_FAL_MODE", "live")
    monkeypatch.setattr(fal, "_request", answer)

    got = fal.create_prediction("fal/alibaba/wan-3.0/text-to-video", {"prompt": "x"},
                                webhook="https://hooks.test/api/hooks/fal/run-1")

    assert seen["url"] == ("https://queue.fal.run/alibaba/wan-3.0/text-to-video"
                           "?fal_webhook=https%3A%2F%2Fhooks.test%2Fapi%2Fhooks%2Ffal%2Frun-1")
    assert seen["body"] == {"prompt": "x"}
    assert got == {"id": "req-2", "status": "IN_QUEUE", "output": None, "error": None}


def test_a_fal_refusal_closes_the_run_failed_with_fals_words(empty_api, monkeypatch):
    """**The same gap as Runpod's 402, one provider later.** fal's `401
    Authentication is required` wedged a run at `pending` because `FalError`
    carried no status, so `submit_run` could not tell a refusal from a dropped
    socket. It carries one now, and `detail` is fal's sentence."""
    from studio_core.clients import fal

    def answer(method, url, *, body=None, **kw):
        return 401, {"detail": 'Cannot access application "fal-ai/wan-3". '
                               "Authentication is required to access this application."}

    monkeypatch.setenv("STUDIO_FAL_MODE", "live")
    monkeypatch.setattr(fal, "_request", answer)
    project = _project(empty_api)
    run = _wan3_draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "failed"
    assert record["error"] == (
        'fal refused the submission (401): Cannot access application "fal-ai/wan-3". '
        "Authentication is required to access this application.")


def test_a_fal_answer_with_no_request_id_closes_the_run_failed(empty_api, monkeypatch):
    """Accepted and named nothing is knowable too: the route's own "no
    prediction id" branch closes it, rather than a raise that reads as silence."""
    from studio_core.clients import fal

    monkeypatch.setenv("STUDIO_FAL_MODE", "live")
    monkeypatch.setattr(fal, "_request",
                        lambda method, url, *, body=None, **kw: (200, {"status": "IN_QUEUE"}))
    project = _project(empty_api)
    run = _wan3_draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "failed"
    assert record["error"] == "the provider returned no prediction id"


def test_the_readme_route_answers_for_a_fal_entry_without_a_provider_call(empty_api):
    body = empty_api.get("/api/models/wan-3.0-t2v/readme").get_json()

    assert body["readme"].startswith("# fal/alibaba/wan-3.0/text-to-video")
    assert "$0.10/s" in body["readme"]
