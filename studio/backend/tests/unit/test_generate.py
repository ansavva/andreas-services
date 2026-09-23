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

import base64
import json
import pathlib

import pytest
from botocore.exceptions import ClientError

from studio_core import config
from studio_core.clients import replicate
from studio_core.clients.aws import s3
from studio_core.errors import NotFoundError, ValidationError
from studio_core.services import catalog, generate, registry


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


# ── two submits in one project at once ──────────────────────────────────────
#
# Every submission bumps `counts.runs` on the PROJECT row inside its own
# transaction, so two runs in one project submitted within the same second
# touch one item from two transactions. DynamoDB cancels the later one whole —
# `TransactionConflict: Transaction is ongoing for the item` — which is not a
# condition failing and not something botocore retries. Three CLI processes
# submitting three drafts hit it on 2026-09-19: two landed, the third surfaced
# as "Could not write to the catalog", and a retry a minute later succeeded.
# moto serialises writes and never raises the conflict, so it is staged here
# on the counter step, exactly as the prod log showed it.


def _conflict_on(position: int, *, steps: int) -> ClientError:
    """DynamoDB's cancellation, with the conflict on one step and `None` elsewhere.

    The codes are the string `'None'`, not a null — that is what the service
    sends and what the prod log recorded.
    """
    reasons = [{"Code": "None"} for _ in range(steps)]
    reasons[position] = {"Code": "TransactionConflict",
                         "Message": "Transaction is ongoing for the item"}
    return ClientError(
        {"Error": {"Code": "TransactionCanceledException",
                   "Message": "Transaction cancelled, please refer cancellation reasons"},
         "CancellationReasons": reasons},
        "TransactWriteItems",
    )


class _Contended:
    """The real client, with the counter-bumping transaction refused N times first."""

    def __init__(self, real, *, refusals):
        self._real = real
        self.refusals = refusals
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self._real, name)

    def transact_write_items(self, *, TransactItems):
        touches_project_counts = any(
            "#counts" in (item.get("Update") or {}).get("ExpressionAttributeNames", {})
            for item in TransactItems
        )
        if touches_project_counts:
            self.calls += 1
            if self.calls <= self.refusals:
                raise _conflict_on(len(TransactItems) - 1, steps=len(TransactItems))
        return self._real.transact_write_items(TransactItems=TransactItems)


def test_two_drafts_submitted_at_once_both_land_and_are_both_counted(empty_api, monkeypatch):
    """**The contended write is the project row's `counts.runs`, and it retries.**

    Each submit's transaction — run row, listing row, project counter — is
    cancelled once with `TransactionConflict` on the counter step, the way the
    second and third of three simultaneous submits were in prod. Both must
    still go out, both must reach `running`, and the project must count two:
    a cancelled transaction applied nothing, so re-sending lands it once.
    """
    real = catalog.dynamodb.client()
    contended = _Contended(real, refusals=1)
    monkeypatch.setattr(catalog.dynamodb, "client", lambda: contended)
    monkeypatch.setattr(catalog.time, "sleep", lambda seconds: None)
    project = _project(empty_api)
    first = _draft(empty_api, project)
    second = _draft(empty_api, project)
    contended.calls = 0

    resp_first = empty_api.post(f"/api/runs/{first['id']}/submit")
    contended.calls = 0
    resp_second = empty_api.post(f"/api/runs/{second['id']}/submit")

    assert resp_first.status_code == 200, resp_first.get_data(as_text=True)
    assert resp_second.status_code == 200, resp_second.get_data(as_text=True)
    assert resp_first.get_json()["status"] == "running"
    assert resp_second.get_json()["status"] == "running"
    assert catalog.entity(catalog.ENTITY_RUN, first["id"])["status"] == "running"
    assert catalog.entity(catalog.ENTITY_RUN, second["id"])["status"] == "running"
    counts = empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]
    assert counts["runs"] == 2, "a retried bump lands exactly once"


def test_a_conflict_that_outlasts_the_retries_is_the_generic_write_error(empty_api, monkeypatch):
    """Bounded: a row that stays contended is reported, not waited on forever.

    And nothing is declared — the run is still a draft, because the transition
    to `pending` is the transaction that never landed.
    """
    real = catalog.dynamodb.client()
    contended = _Contended(real, refusals=catalog.WRITE_ATTEMPTS)
    monkeypatch.setattr(catalog.dynamodb, "client", lambda: contended)
    monkeypatch.setattr(catalog.time, "sleep", lambda seconds: None)
    project = _project(empty_api)
    run = _draft(empty_api, project)
    contended.calls = 0

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    assert resp.get_json()["error"] == "Could not write to the catalog"
    assert contended.calls == catalog.WRITE_ATTEMPTS
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "draft"
    counts = empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]
    assert counts["runs"] == 0


def test_a_condition_failure_is_never_retried(empty_api, monkeypatch):
    """The retry is for conflicts only; a guard that fired is the answer.

    Re-sending a transaction whose condition failed could only fail it again
    or, worse, land it against a row that changed in between — so
    `ConditionalCheckFailed` raises its step's own error on the first try.
    """
    real = catalog.dynamodb.client()
    sent = []

    class Refusing:
        def __getattr__(self, name):
            return getattr(real, name)

        def transact_write_items(self, *, TransactItems):
            sent.append(TransactItems)
            reasons = [{"Code": "None"} for _ in TransactItems]
            reasons[0] = {"Code": "ConditionalCheckFailed",
                          "Message": "The conditional request failed"}
            raise ClientError(
                {"Error": {"Code": "TransactionCanceledException", "Message": "cancelled"},
                 "CancellationReasons": reasons},
                "TransactWriteItems",
            )

    project = _project(empty_api)
    run = _draft(empty_api, project)
    monkeypatch.setattr(catalog.dynamodb, "client", lambda: Refusing())
    monkeypatch.setattr(catalog.time, "sleep", lambda seconds: None)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 404, "the run step's guard is `attribute_exists`, a 404"
    assert len(sent) == 1


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


# ── the provider says no, or says nothing: the draft comes back ─────────────
#
# A dispatch that raises hands the run back as a draft with the provider's
# words in `error`, whatever raised and whichever provider. Two rules preceded
# this: a 4xx closed the run `failed` (a dead run to re-plan), and a silence
# or a 5xx left it `pending` with no prediction id, which `reconcile` refuses
# — the only exit was `runs delete`. `routes/runs.submit_run` has the trade.


def test_a_refused_submission_hands_the_draft_back_with_the_providers_words(
        empty_api, monkeypatch):
    """**A 4xx is an answer, and the answer is no** — nothing is in flight,
    so the run is a draft again: plan, payload and sends as they were, the
    provider's sentence on it, the grid row moved with the envelope, and the
    caller's 502 carries the same sentence rather than a URL and a blob.
    """
    def refuse(model, payload, *, webhook=None):
        raise replicate.ReplicateError(
            "POST … -> 402: {…}", status=402, detail="insufficient balance")

    monkeypatch.setattr(replicate, "create_prediction", refuse)
    project = _project(empty_api)
    run = _draft(empty_api, project)
    before = empty_api.get(f"/api/runs/{run['id']}").get_json()

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    assert resp.get_json()["error"] == (
        "replicate refused the submission (402): insufficient balance")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft"
    assert record["error"] == "replicate refused the submission (402): insufficient balance"
    assert record.get("prediction_id") is None
    assert record.get("completed") is None
    assert record.get("submitted") is None, "a draft has not been sent"
    again = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert again["plan"] == before["plan"] and again["sends"] == before["sends"]
    assert again["payload"] == before["payload"]
    assert empty_api.get(f"/api/runs?project={project['id']}").get_json()["runs"] == [], \
        "the feed hides drafts, and this is one again"
    listing = empty_api.get(f"/api/runs?project={project['id']}&include=drafts").get_json()
    assert [r["status"] for r in listing["runs"]] == ["draft"], \
        "the grid row moved with the envelope"


def test_a_silent_or_broken_submission_hands_the_draft_back_too(empty_api, monkeypatch):
    """**No status, or a 5xx: the same draft, with the transport's words.**
    A reply lost after the provider took the job can now be sent twice; the
    error on the draft is what a person reads before sending again. What it
    buys is a run that can be moved: `pending` with no prediction id could
    not be reconciled, resubmitted or closed, only deleted."""
    def vanish(model, payload, *, webhook=None):
        raise replicate.ReplicateError("POST … failed: timed out")

    monkeypatch.setattr(replicate, "create_prediction", vanish)
    project = _project(empty_api)
    run = _draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft"
    assert record["error"] == "replicate did not take the submission: POST … failed: timed out"

    def broken(model, payload, *, webhook=None):
        raise replicate.ReplicateError("POST … -> 503: {…}", status=503,
                                       detail="try later")

    monkeypatch.setattr(replicate, "create_prediction", broken)
    other = _draft(empty_api, project)
    empty_api.post(f"/api/runs/{other['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, other["id"])
    assert record["status"] == "draft"
    assert record["error"] == "replicate refused the submission (503): try later"


def test_a_draft_handed_back_is_sent_again_clean_and_counted_once(empty_api, monkeypatch):
    """The second submit is the ordinary one: the error is cleared with the
    transition, the run goes `running` with a prediction id, and the project
    counted it once — on the first attempt, when it left the draft states."""
    def refuse(model, payload, *, webhook=None):
        raise replicate.ReplicateError(
            "POST … -> 402: {…}", status=402, detail="insufficient balance")

    project = _project(empty_api)
    before = empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]["runs"]
    run = _draft(empty_api, project)
    real_create = replicate.create_prediction
    monkeypatch.setattr(replicate, "create_prediction", refuse)
    assert empty_api.post(f"/api/runs/{run['id']}/submit").status_code == 502
    monkeypatch.setattr(replicate, "create_prediction", real_create)

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert body["status"] == "running" and body["prediction_id"].startswith("fake")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert "error" not in record, "cleared with the transition, not left from the last try"
    after = empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]["runs"]
    assert after == before + 1


def test_a_provider_naming_no_prediction_hands_the_draft_back(empty_api, monkeypatch):
    monkeypatch.setattr(replicate, "create_prediction",
                        lambda model, payload, *, webhook=None: {"status": "starting"})
    project = _project(empty_api)
    run = _draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft"
    assert "no prediction id" in record["error"]


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


def test_the_output_is_typed_by_what_the_provider_served(empty_api, media_bucket, monkeypatch):
    """`content_type` is what the app gates *Copy into a character or
    location…* on, and it comes off the download's `Content-Type`, not the
    filename — the filename's table lacked `.webp` on the Lambda, and 47
    outputs lost the button that way. A served type that is not media (a
    bucket's `application/octet-stream`) is passed over for the extension."""
    served = {"https://fake.invalid/x/0.webp": "image/webp",
              "https://fake.invalid/x/1.webp": "application/octet-stream"}
    real = replicate.download

    def download(url, path, *, max_bytes):
        got = real(url, path, max_bytes=max_bytes)
        return replicate.Downloaded(got.written, served[url])
    monkeypatch.setattr(replicate, "download", download)

    project = _project(empty_api)
    record = _running(empty_api, project)
    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": list(served),
    })

    types = [catalog.node(n)["content_type"] for n in closed["outputs"]]
    assert types == ["image/webp", "image/webp"]
    for node_id in closed["outputs"]:
        head = s3.head(catalog.node(node_id)["blob_key"])
        assert head["ContentType"] == "image/webp", "the object says the same as the row"


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
    assert "X-Amz-Expires=900" in payload["image"]   # a public endpoint: the service's TTL
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


STUDIO_WORKER = {"model": "runpod/wan22-test", "kind": "video", "key": "wan-2.2-i2v-studio",
                 "output_grant": {"put": "output_url", "get": "result_url",
                                  "content_type": "video/mp4", "ext": ".mp4"}}


def test_the_output_grant_is_read_off_the_entry_and_defaults_its_names():
    from studio_core.services import registry
    assert registry.output_grant(LORA) is None
    assert registry.output_grant(STUDIO_WORKER) == {
        "put": "output_url", "get": "result_url", "content_type": "video/mp4", "ext": ".mp4"}
    assert registry.output_grant({"output_grant": {}}) is None
    assert registry.output_grant({"output_grant": {"ext": ".mp4"}}) == {
        "put": "output_url", "get": "result_url", "content_type": "application/octet-stream", "ext": ".mp4"}
    # The shipped entry declares one; that is what makes dispatch mint the pair.
    assert registry.output_grant(registry.get("wan-2.2-i2v-studio"))["ext"] == ".mp4"


def test_a_studio_worker_run_gets_a_grant_pair_and_files_the_clip_it_answers(
        empty_api, media_bucket, monkeypatch):
    """`wan-2.2-i2v-studio` is our own endpoint: the same LoRA sends as the
    public one plus an end frame, and — because the worker has nowhere to
    host a file — two presigned URLs on one scratch key minted INTO the
    payload: a PUT it uploads to and a GET it echoes as `output.result`. The
    closing path files that result like any Runpod URL, records the cost the
    worker computed, and the stored response carries neither URL: the inputs
    are marked as unmapped, the output result as our own grant."""
    from studio_core.clients import runpod
    seen = {}
    monkeypatch.setattr(runpod, "create_prediction",
                        lambda model, payload, *, webhook=None:
                        (seen.update(model=model, payload=payload) or {"id": "job-studio-u1", "status": "IN_QUEUE"}))
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    still = _uploaded(empty_api, root, "first.png")
    last = _uploaded(empty_api, root, "last.png")
    high = _uploaded(empty_api, root, "subject-a_high_noise.safetensors")
    low = _uploaded(empty_api, root, "subject-a_low_noise.safetensors")
    from studio_core.services import registry
    entry = registry.get("wan-2.2-i2v-studio")
    resp = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": "wan-2.2-i2v-studio",
        "model": entry["model"],
        "plan": {"version": 1, "origin": "authored", "prompt": "ohwx takes his jacket off",
                 "params": {"num_frames": 121, "seed": 8, "lora_scale": 1.0, "steps": 20}},
        "sends": [
            {"field": "image", "role": "start", "node": still["node_id"]},
            {"field": "end_image", "role": "end", "node": last["node_id"]},
            {"field": "high_noise_loras", "role": "lora", "node": high["node_id"]},
            {"field": "low_noise_loras", "role": "lora", "node": low["node_id"]},
        ],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    run = resp.get_json()

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()
    assert body["status"] == "running", body
    assert seen["model"] == entry["model"]
    payload = seen["payload"]
    assert payload["num_frames"] == 121 and payload["seed"] == 8 and payload["steps"] == 20
    assert "lora_scale" not in payload
    assert payload["image"].startswith("http") and payload["end_image"].startswith("http")
    # The sends outlive a queue: one worker, and the clip ahead can take half
    # an hour. The first proof run fetched a 15-minute URL after 16 minutes.
    for url in (payload["image"], payload["end_image"], payload["high_noise_loras"][0]["path"]):
        assert f"X-Amz-Expires={generate.OUTPUT_GRANT_TTL}" in url
    assert payload["high_noise_loras"][0]["scale"] == 1.0
    assert payload["low_noise_loras"][0]["path"].startswith("http")
    # The grant pair: one scratch key, signed twice, for the worker's mp4.
    key = f"scratch/{run['id']}/result.mp4"
    assert key in payload["output_url"] and "X-Amz-Signature=" in payload["output_url"]
    assert key in payload["result_url"] and "X-Amz-Signature=" in payload["result_url"]
    assert payload["output_url"] != payload["result_url"]

    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    prediction = {
        "id": "job-studio-u1", "status": "COMPLETED", "executionTime": 712000,
        "input": payload,
        "output": {"result": payload["result_url"], "cost": 0.83, "seed": 8,
                   "seconds": 712.4, "frames": 121, "end_frame": True},
    }
    closed = generate.close_from_prediction(record, prediction)
    assert closed["status"] == "succeeded", closed.get("error")
    assert closed["cost"] == {"amount": 0.83, "currency": "USD", "predict_time": 712.0}
    assert catalog.node(closed["outputs"][0])["name"].endswith(".mp4")

    unsigned = generate._unsigned_input(record, prediction)
    assert unsigned["input"]["image"] == still["node_id"]
    assert unsigned["input"]["end_image"] == last["node_id"]
    assert unsigned["input"]["high_noise_loras"] == [{"path": high["node_id"], "scale": 1.0}]
    assert unsigned["input"]["output_url"] == "[a presigned URL studio did not store]"
    assert unsigned["input"]["result_url"] == "[a presigned URL studio did not store]"
    assert "X-Amz-Signature" not in unsigned["output"]["result"]
    assert unsigned["output"]["cost"] == 0.83 and unsigned["output"]["seed"] == 8
    # A provider's own URL is not ours, and stays.
    theirs = generate._unsigned_input(record, {"output": {"result": "https://image.runpod.ai/x.mp4"}})
    assert theirs["output"]["result"] == "https://image.runpod.ai/x.mp4"


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


# ── the third provider: a machine ───────────────────────────────────────────
#
# A `runpod-pod` entry is a trainer. Dispatch rents a pod (faked), writes a job
# manifest to the bucket and pre-makes the output nodes on the character; the
# pod's report closes the run by adopting what it uploaded and releasing the
# machine. Nothing here opens a socket: the pod client answers in FAKE mode.


def _character(api, name="subject-a"):
    return api.post("/api/characters", json={"name": name}).get_json()


def _training_draft(api, project, character, nodes, **params):
    resp = api.post("/api/runs", json={
        "project": project["id"], "kind": "training", "engine": "wan-2.2-lora-train",
        "model": "runpod-pod/ai-toolkit-wan22-14b", "characters": [character["id"]],
        "plan": {"version": 1, "origin": "authored", "prompt": None,
                 "params": {"trigger": "ohwx_sa", "steps": 500, "save_every": 250, **params}},
        "sends": [{"field": "dataset", "role": "reference", "node": n} for n in nodes],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _dataset(api, character, count=5):
    root = api.get(f"/api/characters/{character['id']}").get_json()["root"]
    nodes = []
    for index in range(count):
        node = _uploaded(api, root, f"photo-{index}.png")
        api.patch(f"/api/nodes/{node['node_id']}", json={
            "description": f"grey t-shirt, three-quarter view, scene {index}"})
        nodes.append(node["node_id"])
    return nodes


def test_a_training_run_rents_a_pod_writes_a_manifest_and_pre_makes_its_outputs(
        empty_api, media_bucket):
    from studio_core.services import training
    project = _project(empty_api)
    character = _character(empty_api)
    nodes = _dataset(empty_api, character)
    run = _training_draft(empty_api, project, character, nodes)

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()
    assert body["status"] == "running", body
    assert body["provider"] == "runpod-pod"
    assert body["prediction_id"].startswith("fakepod")

    manifest = json.loads(media_bucket.get_object(
        Bucket=config.media_bucket(), Key=training.MANIFEST_KEY.format(run=run["id"]))["Body"].read())
    assert manifest["trigger"] == "ohwx_sa" and manifest["steps"] == 500
    assert [d["caption"] for d in manifest["dataset"]][0] == "ohwx_sa, grey t-shirt, three-quarter view, scene 0"
    assert all(d["url"].startswith("http") for d in manifest["dataset"])
    # 500 steps saving every 250: one periodic pair (250) and the final pair,
    # and at each of those two save points one sample per default prompt.
    stem = manifest["stem"]
    # The file says whose it is: the character's slug, the trigger, the run.
    assert stem == f"subject-a-ohwx-sa-{run['id'][4:12]}"
    weights = training.expected_files(stem, 500, 250)
    samples = training.expected_samples(stem, 500, 250, training.SAMPLE_PROMPTS)
    assert sorted(manifest["outputs"]) == sorted(weights + samples)
    assert len(weights) == 4 and len(samples) == 8
    assert samples[0] == f"{stem}_000000250_sample_0.jpg" and samples[-1] == f"{stem}_sample_3.jpg"
    assert manifest["pod"]["id"] == body["prediction_id"]
    assert "script" in manifest and "run.py" in manifest["script"]
    # The prompts travel with the trigger already in them, plus the two knobs.
    assert manifest["sample_prompts"][0] == "ohwx_sa, cooking in a bright kitchen, medium shot"
    assert len(manifest["sample_prompts"]) == 4
    assert manifest["sample_seed"] == 42 and manifest["sample_steps"] == 20
    # The default base is i2v, so each sample re-renders a dataset photo,
    # dealt round-robin — four prompts over five photos: the first four.
    assert manifest["samples"] == [
        {"index": i, "prompt": p, "ctrl_img": f"photo-{i}.png"}
        for i, p in enumerate(manifest["sample_prompts"])]

    # The output nodes exist under the character's models/ folder, empty —
    # the weights in models/ itself, the samples in models/samples/.
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    # The manifest dies at close; the run keeps which photo each sample is of.
    assert record["payload"]["training"]["samples"] == manifest["samples"]
    made = record["payload"]["training"]["outputs"]
    assert set(made) == set(manifest["outputs"])
    models = catalog.node(catalog.node(made[weights[0]])["parent_id"])
    assert models["name"] == "models"
    samples_folder = catalog.node(catalog.node(made[samples[0]])["parent_id"])
    assert samples_folder["name"] == "samples" and samples_folder["parent_id"] == models["node_id"]
    assert all("size" not in catalog.node(node_id) for node_id in made.values())


def test_a_training_run_closes_by_adopting_the_checkpoints_the_pod_uploaded(
        empty_api, media_bucket, monkeypatch):
    from studio_core.clients import runpod_pods
    from studio_core.services import training
    project = _project(empty_api)
    character = _character(empty_api)
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character))
    empty_api.post(f"/api/runs/{run['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    made = record["payload"]["training"]["outputs"]

    # The pod uploads the final pair only (a run cut short), then reports.
    uploaded = [n for n in made if "_0000" not in n and n.endswith(".safetensors")]
    for name in uploaded:
        media_bucket.put_object(Bucket=config.media_bucket(),
                                Key=catalog.node(made[name])["blob_key"], Body=b"weights")
    report = {"id": record["prediction_id"], "status": "COMPLETED",
              "output": {"uploaded": uploaded, "cost": 2.41, "seconds": 5460, "rate": 1.59}}
    media_bucket.put_object(Bucket=config.media_bucket(),
                            Key=training.RESULT_KEY.format(run=run["id"]), Body=json.dumps(report).encode())
    released = []
    monkeypatch.setattr(runpod_pods, "terminate", lambda pod_id: released.append(pod_id))

    body = empty_api.post(f"/api/runs/{run['id']}/reconcile").get_json()

    assert body["status"] == "succeeded", body
    assert len(body["outputs"]) == 2
    assert body["cost"] == {"amount": 2.41, "currency": "USD", "predict_time": 5460}
    for name in uploaded:
        assert catalog.node(made[name])["size"] == len(b"weights")
    # The two periodic nodes the pod never filled are gone from models/.
    for name, node_id in made.items():
        if name not in uploaded:
            with pytest.raises(NotFoundError):
                catalog.node(node_id)
    assert released == [record["prediction_id"]]
    # The manifest — the one place presigned URLs lived — is gone with the run.
    with pytest.raises(Exception):
        media_bucket.get_object(Bucket=config.media_bucket(),
                                Key=training.MANIFEST_KEY.format(run=run["id"]))


def test_a_training_run_whose_pod_died_silently_closes_failed_and_releases(
        empty_api, media_bucket, monkeypatch):
    from studio_core.clients import runpod_pods
    project = _project(empty_api)
    character = _character(empty_api)
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character))
    empty_api.post(f"/api/runs/{run['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    runpod_pods._FAKE_PODS.pop(record["prediction_id"], None)  # the machine vanished

    body = empty_api.post(f"/api/runs/{run['id']}/reconcile").get_json()
    assert body["status"] == "failed"
    assert "gone" in body["error"]
    assert body["outputs"] == []


def test_a_training_run_is_refused_before_pending_without_a_trigger_or_enough_images(empty_api):
    project = _project(empty_api)
    character = _character(empty_api)
    nodes = _dataset(empty_api, character, count=3)
    resp = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "training", "engine": "wan-2.2-lora-train",
        "model": "runpod-pod/ai-toolkit-wan22-14b", "characters": [character["id"]],
        "plan": {"version": 1, "origin": "authored", "prompt": None, "params": {"steps": 500}},
        "sends": [{"field": "dataset", "role": "reference", "node": n} for n in nodes],
    })
    run = resp.get_json()
    resp = empty_api.post(f"/api/runs/{run['id']}/submit")
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "trigger" in resp.get_data(as_text=True)
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["status"] == "draft"


def _models_children(character):
    """Everything under the character's `models/`, recursively — or nothing,
    when the folder itself was never made."""
    try:
        models = catalog.child_by_name(character["root"], "models")
    except NotFoundError:
        return []
    found = []
    for child in catalog.children(models["node_id"]):
        found.append(child)
        if child.get("kind") == catalog.KIND_FOLDER:
            found.extend(catalog.children(child["node_id"]))
    return found


def test_a_pod_that_cannot_be_rented_hands_the_draft_back_and_takes_its_nodes_with_it(
        empty_api, media_bucket, monkeypatch):
    """**The 2026-09-20 wedge.** Runpod answered `POST /v1/pods -> 500 create
    pod: This machine does not have the resources to deploy your pod`; the
    run sat `pending` with no prediction id, a second submit was refused as
    `pending, not a draft`, twelve empty nodes sat under the character's
    `models/`, and the way out was `runs delete`. Now: a draft again with
    Runpod's own words on it, the character's tree as it was — no file nodes,
    no `models/` folder this dispatch made — no manifest in the bucket, and
    the same run rents a pod on the next submit once the machine is there.
    """
    from studio_core.clients import runpod_pods
    from studio_core.services import training
    project = _project(empty_api)
    character = _character(empty_api)
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character))
    real_create_pod = runpod_pods.create_pod
    pods_before = set(runpod_pods._FAKE_PODS)

    def no_machine(**kwargs):
        raise runpod_pods.RunpodPodError(
            "POST https://rest.runpod.io/v1/pods -> 500: {…}", status=500,
            detail="create pod: This machine does not have the resources to deploy your pod. "
                   "Please try a different machine")

    monkeypatch.setattr(runpod_pods, "create_pod", no_machine)
    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    assert resp.get_json()["error"] == (
        "runpod-pod refused the submission (500): create pod: This machine does not "
        "have the resources to deploy your pod. Please try a different machine")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft"
    assert record["error"] == resp.get_json()["error"]
    assert record.get("prediction_id") is None
    assert "training" not in (record.get("payload") or {}), "nothing of the failed rent is recorded"
    assert _models_children(character) == [], "the character's tree is as it was"
    with pytest.raises(Exception):
        media_bucket.get_object(Bucket=config.media_bucket(),
                                Key=training.MANIFEST_KEY.format(run=run["id"]))
    assert set(runpod_pods._FAKE_PODS) == pods_before, "no machine is billing"

    monkeypatch.setattr(runpod_pods, "create_pod", real_create_pod)
    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert body["status"] == "running", body
    assert body["prediction_id"].startswith("fakepod")
    assert body.get("error") is None
    made = catalog.entity(catalog.ENTITY_RUN, run["id"])["payload"]["training"]["outputs"]
    assert {n["node_id"] for n in _models_children(character) if n.get("kind") == catalog.KIND_FILE} \
        == set(made.values()), "the second rent's nodes, and only those"
    media_bucket.get_object(Bucket=config.media_bucket(),
                            Key=training.MANIFEST_KEY.format(run=run["id"]))


def test_a_rent_that_fails_after_the_pod_terminates_it_and_drops_the_manifest(
        empty_api, media_bucket, monkeypatch):
    """The pod is rented before the manifest is written, so a write failing
    after it is the one order of failure that would leave a machine billing
    with no run pointing at it. The unwind terminates it first, then takes
    the manifest and the nodes; the weights already in `models/` — another
    training's — are not touched, and neither is the folder."""
    from studio_core.clients import runpod_pods
    from studio_core.services import training
    project = _project(empty_api)
    character = _character(empty_api)
    root = empty_api.get(f"/api/characters/{character['id']}").get_json()["root"]
    models = empty_api.post("/api/nodes", json={"parent": root, "name": "models",
                                                "kind": "folder"}).get_json()
    earlier = _uploaded(empty_api, models["id"], "earlier_high_noise.safetensors")
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character))
    pods_before = set(runpod_pods._FAKE_PODS)
    terminated = []
    real_terminate = runpod_pods.terminate
    monkeypatch.setattr(runpod_pods, "terminate",
                        lambda pod_id: terminated.append(pod_id) or real_terminate(pod_id))
    real_update = catalog.update_project_entity

    def refuse_the_record(kind, record, assignments, *args, **kwargs):
        if "training" in (assignments.get("payload") or {}):
            raise RuntimeError("DynamoDB refused the write")
        return real_update(kind, record, assignments, *args, **kwargs)

    monkeypatch.setattr(catalog, "update_project_entity", refuse_the_record)
    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 500
    monkeypatch.setattr(catalog, "update_project_entity", real_update)
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft"
    assert record["error"] == "DynamoDB refused the write"
    assert len(terminated) == 1, "the meter stopped"
    assert set(runpod_pods._FAKE_PODS) == pods_before, "no machine of this run's is billing"
    with pytest.raises(Exception):
        media_bucket.get_object(Bucket=config.media_bucket(),
                                Key=training.MANIFEST_KEY.format(run=run["id"]))
    left = _models_children(character)
    assert [n["node_id"] for n in left] == [earlier["node_id"]], "the earlier weights, and the folder"


def test_the_pod_callback_is_verified_like_a_public_endpoints(empty_api, media_bucket, monkeypatch):
    """The receiver forwards `?sig=`; the consumer recomputes it under the same
    key the pod's URL was minted with, and routes the body to the closer."""
    from studio_core.clients import runpod, runpod_pods
    from studio_core.services import callbacks
    project = _project(empty_api)
    character = _character(empty_api)
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character))
    empty_api.post(f"/api/runs/{run['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    monkeypatch.setattr(runpod_pods, "terminate", lambda pod_id: None)
    report = {"id": record["prediction_id"], "status": "FAILED", "error": "trainer exited 1",
              "output": {"uploaded": [], "cost": 0.4, "seconds": 900}}
    closed = callbacks.process({
        "run": run["id"], "provider": "runpod-pod",
        "sig": runpod.callback_signature(run["id"]),
        "body_b64": base64.b64encode(json.dumps(report).encode()).decode(),
    })
    assert closed["status"] == "failed" and closed["error"] == "trainer exited 1"
    assert closed["cost"]["amount"] == 0.4


# ── progress: a checkpoint is visible when it lands ─────────────────────────
#
# The pod POSTs `IN_PROGRESS` with the names uploaded so far after each PUT, on
# the same signed URL as the final report. The closer routes a still-running
# status for a pod run to `training.confirm_progress`, which files what has
# landed and leaves the run `running`; the final report then closes it exactly
# as before, and `reconcile` confirms whatever landed while a callback was lost.


def _running_training(api, media_bucket):
    project = _project(api)
    character = _character(api)
    run = _training_draft(api, project, character, _dataset(api, character))
    api.post(f"/api/runs/{run['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    return record, record["payload"]["training"]["outputs"]


def _land(media_bucket, made, names, body=b"weights"):
    # The pod's PUT declares the type the grant signed: a JPEG for a sample.
    for name in names:
        media_bucket.put_object(
            Bucket=config.media_bucket(), Key=catalog.node(made[name])["blob_key"], Body=body,
            ContentType="image/jpeg" if name.endswith(".jpg") else "application/octet-stream")


def _progress(record, uploaded):
    return {"id": record["prediction_id"], "status": "IN_PROGRESS", "output": {"uploaded": uploaded}}


def _pod_message(run_id, document):
    from studio_core.clients import runpod
    return {"run": run_id, "provider": "runpod-pod", "sig": runpod.callback_signature(run_id),
            "body_b64": base64.b64encode(json.dumps(document).encode()).decode()}


def test_a_progress_callback_confirms_only_what_landed_and_keeps_the_run_running(
        empty_api, media_bucket):
    from studio_core.services import callbacks
    record, made = _running_training(empty_api, media_bucket)
    first_pair = sorted(n for n in made if "_000000250_" in n and n.endswith(".safetensors"))
    # The pod says the first pair is up, but only the high-noise half has
    # reached the bucket — the other PUT is still in flight.
    _land(media_bucket, made, first_pair[:1])
    for node_id in made.values():
        assert "size" not in catalog.node(node_id)  # placeholders: hidden from models/

    updated = callbacks.process(_pod_message(record["id"], _progress(record, first_pair)))

    assert updated["status"] == "running"
    assert updated["outputs"] == [made[first_pair[0]]]
    assert catalog.node(made[first_pair[0]])["size"] == len(b"weights")
    assert "size" not in catalog.node(made[first_pair[1]])
    # The API shows the same: outputs on a running run, nothing dropped.
    body = empty_api.get(f"/api/runs/{record['id']}").get_json()
    assert body["status"] == "running"
    assert [asset["node"] for asset in body["outputs"]] == [made[first_pair[0]]]
    assert body["outputs"][0]["name"] == first_pair[0] and body["outputs"][0]["size"] == len(b"weights")
    assert all(catalog.node(node_id) for node_id in made.values())


def test_a_repeated_progress_callback_changes_nothing(empty_api, media_bucket):
    from studio_core.services import callbacks
    record, made = _running_training(empty_api, media_bucket)
    first_pair = sorted(n for n in made if "_000000250_" in n and n.endswith(".safetensors"))
    _land(media_bucket, made, first_pair)

    once = callbacks.process(_pod_message(record["id"], _progress(record, first_pair)))
    twice = callbacks.process(_pod_message(record["id"], _progress(record, first_pair)))

    assert once["outputs"] == [made[n] for n in first_pair]
    assert twice["outputs"] == once["outputs"]
    assert twice["status"] == "running"
    assert catalog.entity(catalog.ENTITY_RUN, record["id"])["outputs"] == once["outputs"]


def test_the_final_report_after_progress_closes_with_every_file_once_and_drops_the_rest(
        empty_api, media_bucket, monkeypatch):
    from studio_core.clients import runpod_pods
    from studio_core.services import callbacks
    record, made = _running_training(empty_api, media_bucket)
    monkeypatch.setattr(runpod_pods, "terminate", lambda pod_id: None)
    first_pair = sorted(n for n in made if "_000000250_" in n and n.endswith(".safetensors"))
    final_pair = sorted(n for n in made if "_0000" not in n and n.endswith(".safetensors"))
    _land(media_bucket, made, first_pair)
    callbacks.process(_pod_message(record["id"], _progress(record, first_pair)))
    # The trainer stops before the final pair's low-noise half is written.
    _land(media_bucket, made, final_pair[:1])
    uploaded = first_pair + final_pair[:1]
    callbacks.process(_pod_message(record["id"], _progress(record, uploaded)))
    report = {"id": record["prediction_id"], "status": "COMPLETED",
              "output": {"uploaded": uploaded, "cost": 2.41, "seconds": 5460, "rate": 1.59}}

    closed = callbacks.process(_pod_message(record["id"], report))

    assert closed["status"] == "succeeded", closed
    assert sorted(closed["outputs"]) == sorted(made[n] for n in uploaded)
    assert len(closed["outputs"]) == len(set(closed["outputs"])) == 3
    for name in uploaded:
        assert catalog.node(made[name])["size"] == len(b"weights")
    with pytest.raises(NotFoundError):
        catalog.node(made[final_pair[1]])
    # A late progress call is a repeat report on a terminal run: ignored.
    again = callbacks.process(_pod_message(record["id"], _progress(record, uploaded)))
    assert again["status"] == "succeeded" and len(again["outputs"]) == 3


def test_reconcile_on_a_running_training_run_confirms_what_landed(empty_api, media_bucket):
    """A lost progress callback is not a lost view: `reconcile` finds no result
    yet and the pod alive, and files whatever is in the bucket."""
    record, made = _running_training(empty_api, media_bucket)
    first_pair = sorted(n for n in made if "_000000250_" in n and n.endswith(".safetensors"))
    _land(media_bucket, made, first_pair)

    body = empty_api.post(f"/api/runs/{record['id']}/reconcile").get_json()

    assert body["status"] == "running", body
    assert sorted(a["node"] for a in body["outputs"]) == sorted(made[n] for n in first_pair)
    for name in first_pair:
        assert catalog.node(made[name])["size"] == len(b"weights")
    # Nothing landed since: the second ask rewrites nothing.
    again = empty_api.post(f"/api/runs/{record['id']}/reconcile").get_json()
    assert [a["node"] for a in again["outputs"]] == [a["node"] for a in body["outputs"]]
    assert again["status"] == "running"


# ── samples: a picture beside every pair ────────────────────────────────────
#
# The trainer renders one still per `sample_prompts` entry at every save
# point, and the pod files it under `<character>/models/samples/` through a
# grant minted at dispatch like a checkpoint's. It is confirmed as an image
# as it lands — content type off the PUT, a poster queued — and a sample
# node the pod never filled goes at close like an unfilled pair.


def test_a_progress_callback_naming_a_sample_confirms_it_as_an_image_and_queues_its_poster(
        empty_api, media_bucket, monkeypatch):
    from studio_core.services import callbacks, render
    record, made = _running_training(empty_api, media_bucket)
    sample = next(n for n in made if n.endswith("_000000250_sample_0.jpg"))
    _land(media_bucket, made, [sample], body=b"\xff\xd8jpeg")
    queued = []
    monkeypatch.setattr(render, "queue_poster", lambda lib, node_id: queued.append((lib, node_id)))

    updated = callbacks.process(_pod_message(record["id"], _progress(record, [sample])))

    assert updated["status"] == "running"
    assert updated["outputs"] == [made[sample]]
    node = catalog.node(made[sample])
    assert node["content_type"] == "image/jpeg" and node["size"] == 6
    assert queued == [(record["lib"], made[sample])]
    body = empty_api.get(f"/api/runs/{record['id']}").get_json()
    assert body["outputs"][0]["name"] == sample
    assert body["outputs"][0]["content_type"] == "image/jpeg"
    assert body["outputs"][0]["url"].startswith("http")


def test_the_first_picture_to_land_becomes_the_listing_thumbnail_over_a_weights_file(
        empty_api, media_bucket):
    from studio_core.services import callbacks
    record, made = _running_training(empty_api, media_bucket)
    weight = next(n for n in made if n.endswith("_000000250_high_noise.safetensors"))
    sample = next(n for n in made if n.endswith("_000000250_sample_0.jpg"))

    def thumb():
        rows = empty_api.get(f"/api/runs?project={record['project']}").get_json()["runs"]
        return next(r for r in rows if r["id"] == record["id"]).get("thumb")

    # A weights file first: the row has a thumbnail, and it is the file.
    _land(media_bucket, made, [weight])
    callbacks.process(_pod_message(record["id"], _progress(record, [weight])))
    assert (thumb() or {}).get("node") == made[weight]
    # Then a sample: the row's thumbnail becomes a picture.
    _land(media_bucket, made, [sample], body=b"\xff\xd8jpeg")
    callbacks.process(_pod_message(record["id"], _progress(record, [weight, sample])))
    assert thumb()["node"] == made[sample]


def test_the_close_keeps_the_samples_that_came_and_drops_the_rest(
        empty_api, media_bucket, monkeypatch):
    from studio_core.clients import runpod_pods
    from studio_core.services import callbacks
    record, made = _running_training(empty_api, media_bucket)
    monkeypatch.setattr(runpod_pods, "terminate", lambda pod_id: None)
    weights = sorted(n for n in made if n.endswith(".safetensors"))
    samples = sorted(n for n in made if n.endswith(".jpg"))
    # The trainer got as far as the first save point and its samples, then died.
    landed = [n for n in weights if "_000000250_" in n] + [n for n in samples if "_000000250_" in n]
    _land(media_bucket, made, landed)
    report = {"id": record["prediction_id"], "status": "COMPLETED",
              "output": {"uploaded": landed, "cost": 1.2, "seconds": 2700, "rate": 1.59}}

    closed = callbacks.process(_pod_message(record["id"], report))

    assert closed["status"] == "succeeded", closed
    assert sorted(closed["outputs"]) == sorted(made[n] for n in landed)
    assert len(landed) == 2 + 4
    for name in samples:
        if name in landed:
            assert catalog.node(made[name])["content_type"] == "image/jpeg"
        else:
            with pytest.raises(NotFoundError):
                catalog.node(made[name])


def test_no_sample_prompts_means_no_sample_nodes_and_sampling_off(empty_api, media_bucket, tmp_path):
    from studio_core.services import training
    project = _project(empty_api)
    character = _character(empty_api)
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character),
                          sample_prompts=[])
    empty_api.post(f"/api/runs/{run['id']}/submit")

    manifest = json.loads(media_bucket.get_object(
        Bucket=config.media_bucket(), Key=training.MANIFEST_KEY.format(run=run["id"]))["Body"].read())
    assert manifest["sample_prompts"] == []
    assert sorted(manifest["outputs"]) == sorted(training.expected_files(manifest["stem"], 500, 250))
    made = catalog.entity(catalog.ENTITY_RUN, run["id"])["payload"]["training"]["outputs"]
    assert not any(n.endswith(".jpg") for n in made)
    # No samples/ folder was made for nothing.
    root = empty_api.get(f"/api/characters/{character['id']}").get_json()["root"]
    models = catalog.child_by_name(root, "models")
    with pytest.raises(NotFoundError):
        catalog.child_by_name(models["node_id"], "samples")
    # And the config the pod writes says so.
    cfg = _written_config(tmp_path, manifest)
    assert cfg["train"]["disable_sampling"] is True
    assert cfg["sample"]["prompts"] == []


def test_a_sample_prompts_value_that_is_not_a_list_of_prompts_is_refused_as_a_draft(empty_api):
    project = _project(empty_api)
    character = _character(empty_api)
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character),
                          sample_prompts="{trigger} on a beach")
    resp = empty_api.post(f"/api/runs/{run['id']}/submit")
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "sample_prompts" in resp.get_data(as_text=True)
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["status"] == "draft"


def _config_source():
    """The first Python pass of the job — the one that writes ai-toolkit's
    config — lifted out of the bash it is embedded in."""
    from studio_core.services import training
    marker = "python3 - <<'PYEOF'\n"
    start = training.JOB_SCRIPT.index(marker) + len(marker)
    return training.JOB_SCRIPT[start:training.JOB_SCRIPT.index("\nPYEOF", start)]


def _written_config(tmp_path, manifest):
    """Execute the config-writing pass against `manifest` and return the one
    process block of the config it wrote. The dataset fetch is stubbed; the
    yaml module is stood in for by JSON when the suite's venv lacks it."""
    import sys
    import types
    import urllib.request
    job = tmp_path / "job.json"
    job.write_text(json.dumps(manifest))
    dataset = tmp_path / "dataset"
    written = tmp_path / "train.yaml"
    fetched = []
    stub = types.ModuleType("yaml")
    stub.safe_dump = lambda data, stream: stream.write(json.dumps(data))
    saved = sys.modules.get("yaml")
    sys.modules["yaml"] = stub
    real = urllib.request.urlretrieve
    urllib.request.urlretrieve = lambda url, path: fetched.append((url, path))
    try:
        source = (_config_source()
                  .replace("/tmp/job.json", str(job))
                  .replace("/workspace/dataset", str(dataset))
                  .replace("/tmp/train.yaml", str(written))
                  .replace("/tmp/uploader.py", str(tmp_path / "uploader.py")))
        dataset.mkdir(exist_ok=True)  # a test may have put real photos there
        exec(compile(source, "job-config.py", "exec"), {"__name__": "__main__"})
    finally:
        urllib.request.urlretrieve = real
        if saved is None:
            del sys.modules["yaml"]
        else:
            sys.modules["yaml"] = saved
    assert [url for url, _ in fetched] == [d["url"] for d in manifest["dataset"]]
    # The pod's dataset path, as the pod would write it — the substitution
    # above undone, so a `--ctrl_img` in a prompt reads as it does on the pod.
    text = written.read_text().replace(str(dataset), "/workspace/dataset")
    return json.loads(text)["config"]["process"][0]


def test_the_job_writes_a_config_that_samples_at_every_save_point(tmp_path):
    """ai-toolkit's `SampleConfig` fields, filled from the manifest: sampling
    on, at the save interval, the trigger already in each prompt, one seed
    held across the run, and no baseline before training."""
    manifest = {
        "stem": "ohwx-sa-1234", "trigger": "ohwx_sa", "steps": 1000, "save_every": 250,
        "rank": 16, "lr": 1e-4, "resolution": 512, "base": "i2v",
        "sample_prompts": ["ohwx_sa, cooking in a bright kitchen, medium shot",
                           "ohwx_sa, sitting on a beach at sunset, full body"],
        "sample_seed": 7, "sample_steps": 12,
        "dataset": [{"name": "a.png", "url": "https://bucket.test/a.png?x", "caption": "ohwx_sa, grey t-shirt"}],
    }

    cfg = _written_config(tmp_path, manifest)

    assert cfg["train"]["disable_sampling"] is False
    assert cfg["train"]["skip_first_sample"] is True
    sample = cfg["sample"]
    assert sample["sample_every"] == 250
    # The i2v base: each prompt as written, then the photo it re-renders.
    # No photo reached the stubbed dataset folder, so no size flags.
    assert sample["prompts"] == [f"{p} --ctrl_img /workspace/dataset/a.png"
                                 for p in manifest["sample_prompts"]]
    assert sample["seed"] == 7 and sample["walk_seed"] is False
    assert sample["sample_steps"] == 12
    assert sample["width"] == 512 and sample["height"] == 512
    assert sample["num_frames"] == 1 and sample["neg"] == "" and sample["format"] == "jpg"
    assert "guidance_scale" not in sample
    assert (tmp_path / "dataset" / "a.txt").read_text() == "ohwx_sa, grey t-shirt"
    assert cfg["save"]["save_every"] == 250 and cfg["network"]["linear"] == 16


def _sample_manifest(base, prompts, dataset):
    return {
        "stem": "ohwx-sa-1234", "trigger": "ohwx_sa", "steps": 500, "save_every": 250,
        "rank": 16, "lr": 1e-4, "resolution": 512, "base": base,
        "sample_prompts": prompts, "sample_seed": 7, "sample_steps": 12,
        "dataset": [{"name": n, "url": f"https://bucket.test/{n}?x", "caption": "ohwx_sa"} for n in dataset],
    }


def test_i2v_sample_prompts_re_render_the_dataset_photos_round_robin_at_their_own_aspect(tmp_path):
    """The I2V base samples from an image or crashes (ai-toolkit's
    wan22_pipeline: 36-channel latents against a 16-channel prediction), so
    on `i2v` every prompt carries `--ctrl_img` naming a dataset photo — dealt
    round-robin over the manifest's dataset, the third prompt wrapping to
    the first photo — and `--w`/`--h` fitting that photo's aspect inside
    `resolution` at multiples of 16. The manifest's `samples` say the same."""
    from PIL import Image
    from studio_core.services import training
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    Image.new("RGB", (640, 480)).save(dataset / "wide.png")
    Image.new("RGB", (300, 600)).save(dataset / "tall.png")
    prompts = ["ohwx_sa, in a kitchen", "ohwx_sa, on a beach", "ohwx_sa, at night"]
    manifest = _sample_manifest("i2v", prompts, ["wide.png", "tall.png"])

    cfg = _written_config(tmp_path, manifest)

    assert cfg["sample"]["prompts"] == [
        "ohwx_sa, in a kitchen --w 512 --h 384 --ctrl_img /workspace/dataset/wide.png",
        "ohwx_sa, on a beach --w 256 --h 512 --ctrl_img /workspace/dataset/tall.png",
        "ohwx_sa, at night --w 512 --h 384 --ctrl_img /workspace/dataset/wide.png",
    ]
    assert cfg["train"]["disable_sampling"] is False
    assert cfg["sample"]["num_frames"] == 1
    assert training.sample_records(prompts, ["wide.png", "tall.png"], "i2v") == [
        {"index": 0, "prompt": prompts[0], "ctrl_img": "wide.png"},
        {"index": 1, "prompt": prompts[1], "ctrl_img": "tall.png"},
        {"index": 2, "prompt": prompts[2], "ctrl_img": "wide.png"},
    ]


def test_t2v_sample_prompts_are_text_only(tmp_path):
    from studio_core.services import training
    prompts = ["ohwx_sa, in a kitchen", "ohwx_sa, on a beach"]
    manifest = _sample_manifest("t2v", prompts, ["a.png", "b.png"])

    cfg = _written_config(tmp_path, manifest)

    assert cfg["sample"]["prompts"] == prompts
    assert not any("--" in p for p in cfg["sample"]["prompts"])
    assert cfg["model"]["arch"] == "wan22_14b"
    assert training.sample_records(prompts, ["a.png", "b.png"], "t2v") == [
        {"index": 0, "prompt": prompts[0], "ctrl_img": None},
        {"index": 1, "prompt": prompts[1], "ctrl_img": None},
    ]


def test_a_sample_prompt_carrying_a_flag_is_refused_as_a_draft(empty_api):
    """ai-toolkit reads `--x` off a prompt as a flag and the job appends its
    own, so a prompt with `--` in it would be cut there."""
    project = _project(empty_api)
    character = _character(empty_api)
    run = _training_draft(empty_api, project, character, _dataset(empty_api, character),
                          sample_prompts=["{trigger} on a beach --w 1024"])
    resp = empty_api.post(f"/api/runs/{run['id']}/submit")
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "--" in resp.get_data(as_text=True)
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["status"] == "draft"


def test_sample_names_are_one_per_prompt_per_save_point_and_the_final_set_is_unnumbered():
    from studio_core.services import training
    names = training.expected_samples("stem", 750, 250, ["a", "b"])
    assert names == [
        "stem_000000250_sample_0.jpg", "stem_000000250_sample_1.jpg",
        "stem_000000500_sample_0.jpg", "stem_000000500_sample_1.jpg",
        "stem_sample_0.jpg", "stem_sample_1.jpg",
    ]
    assert training.expected_samples("stem", 750, 250, []) == []
    # What the trainer itself writes, and what the uploader parses.
    assert training.SAMPLE_FILE.match("1758300000000__000000250_0.jpg").groups() == ("000000250", "0")
    assert training.SAMPLE_FILE.match("stem_000000250_sample_0.jpg") is None


def _uploader_source():
    """The uploader the pod runs, lifted out of the job script it is embedded in."""
    from studio_core.services import training
    start = training.JOB_SCRIPT.index('open("/tmp/uploader.py", "w").write(r"""') + len(
        'open("/tmp/uploader.py", "w").write(r"""')
    return training.JOB_SCRIPT[start:training.JOB_SCRIPT.index('""")', start)]


def test_the_pods_uploader_posts_progress_to_the_callback_after_each_put(tmp_path, monkeypatch):
    """The embedded script, executed: every checkpoint goes through its grant,
    and after each one the callback URL hears what has landed so far. A
    refused progress POST is printed and does not stop the uploads. A sample
    goes up under studio's name — `<stem>_<step>_sample_<i>.jpg`, unnumbered
    at the final step — as a JPEG, and the trainer's scratch under
    `samples/.tmp` is never swept."""
    import urllib.request
    out = tmp_path / "output" / "stem"
    (out / "samples" / ".tmp").mkdir(parents=True)
    weights = ["stem_000000250_high_noise.safetensors", "stem_000000250_low_noise.safetensors",
               "stem_high_noise.safetensors", "stem_low_noise.safetensors"]
    for name in weights:
        (out / name).write_bytes(b"w" * 16)
    (out / "optimizer.pt").write_bytes(b"not a checkpoint")
    # What ai-toolkit writes: `<ms>__<step:09d>_<i>.jpg`, the final step numbered.
    trainer_samples = {"1758300000000__000000250_0.jpg": "stem_000000250_sample_0.jpg",
                       "1758300000000__000000250_1.jpg": "stem_000000250_sample_1.jpg",
                       "1758300099000__000000500_0.jpg": "stem_sample_0.jpg",
                       "1758300099000__000000500_1.jpg": "stem_sample_1.jpg"}
    for name in trainer_samples:
        (out / "samples" / name).write_bytes(b"j" * 16)
    (out / "samples" / ".tmp" / "1758300099000__000000500_2.jpg").write_bytes(b"half")
    (out / "samples" / "config.yaml").write_text("not a sample")
    names = weights + sorted(trainer_samples.values())
    job = tmp_path / "job.json"
    job.write_text(json.dumps({
        "pod": {"id": "pod-1"}, "stem": "stem", "steps": 500,
        "outputs": {name: f"https://bucket.test/{name}?grant" for name in names},
        "callback": "https://hooks.test/api/hooks/runpod-pod/run-x?sig=abc",
    }))
    uploaded_json = tmp_path / "uploaded.json"

    calls = []

    class _Answer:
        def read(self):
            return b""

    def urlopen(req, timeout=None):
        calls.append((req.get_method(), req.full_url, req.data, req.get_header("Content-type")))
        if req.get_method() == "POST" and len(calls) == 2:
            raise OSError("hook down")  # the first progress POST fails
        return _Answer()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr("sys.argv", ["uploader", "final"])
    source = (_uploader_source()
              .replace("/tmp/job.json", str(job))
              .replace("/workspace/output", str(tmp_path / "output"))
              .replace("/tmp/uploaded.json", str(uploaded_json)))
    exec(compile(source, "uploader.py", "exec"), {"__name__": "__main__"})

    puts = [(url, data, kind) for method, url, data, kind in calls if method == "PUT"]
    assert [url for url, _, _ in puts] == [f"https://bucket.test/{n}?grant" for n in names]
    assert all(data == b"w" * 16 for _, data, _ in puts[:4])
    assert all(data == b"j" * 16 and kind == "image/jpeg" for _, data, kind in puts[4:])
    assert all(kind == "application/octet-stream" for _, _, kind in puts[:4])
    posts = [json.loads(data) for method, url, data, kind in calls if method == "POST"]
    assert len(posts) == len(names)
    assert all(p["status"] == "IN_PROGRESS" and p["id"] == "pod-1" for p in posts)
    assert posts[0]["output"]["uploaded"] == names[:1]
    assert posts[-1]["output"]["uploaded"] == sorted(names)
    assert json.loads(uploaded_json.read_text()) == sorted(names)


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
                            "payload": {"detail": "the prompt was refused"}})
    assert failed["status"] == "ERROR" and failed["output"] is None
    assert failed["error"] == "content policy: the prompt was refused"

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


def test_a_fal_refusal_hands_the_draft_back_with_fals_words(empty_api, monkeypatch):
    """**The same gap as Runpod's 402, one provider later.** fal's `401
    Authentication is required` wedged a run at `pending` because `FalError`
    carried no status and no detail. It carries both now, and `detail` is
    fal's sentence — the one on the draft that comes back."""
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
    assert record["status"] == "draft"
    assert record["error"] == (
        'fal refused the submission (401): Cannot access application "fal-ai/wan-3". '
        "Authentication is required to access this application.")


def test_a_fal_answer_with_no_request_id_hands_the_draft_back(empty_api, monkeypatch):
    """Accepted and named nothing is knowable too: the route's own "no
    prediction id" branch hands the draft back, saying so."""
    from studio_core.clients import fal

    monkeypatch.setenv("STUDIO_FAL_MODE", "live")
    monkeypatch.setattr(fal, "_request",
                        lambda method, url, *, body=None, **kw: (200, {"status": "IN_QUEUE"}))
    project = _project(empty_api)
    run = _wan3_draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft"
    assert record["error"] == (
        "fal did not take the submission: fal answered the submission with no prediction id")


def test_a_fal_422_names_the_field_and_drops_the_presigned_echo(empty_api, media_bucket):
    """**"Unexpected status code: 422" is fal's wrapper; the reason is under
    `payload`.** Twelve references to a model that takes ten came back as
    exactly that sentence and nothing else, because `normalise` read `error`
    alone. The detail is folded in — field, then fal's own words — and the
    `input` each item echoes is dropped, because for an image field it is the
    presigned URL list `dispatch` minted (hard rule #3)."""
    from studio_core.clients import fal
    signed = ["https://bucket.s3.amazonaws.com/a.jpeg?X-Amz-Signature=deadbeef"] * 12

    closed_shape = fal.normalise({
        "request_id": "r4", "gateway_request_id": "g", "status": "ERROR",
        "error": "Unexpected status code: 422",
        "payload": {"detail": [{"type": "too_long",
                                "loc": ["body", "reference_image_urls"],
                                "msg": "List should have at most 10 items after validation, not 12",
                                "input": signed}]},
    })

    assert closed_shape["error"] == (
        "Unexpected status code: 422: body.reference_image_urls: "
        "List should have at most 10 items after validation, not 12")
    assert closed_shape["detail"] == {"detail": [{
        "type": "too_long", "loc": ["body", "reference_image_urls"],
        "msg": "List should have at most 10 items after validation, not 12"}]}
    assert "X-Amz-Signature" not in json.dumps(closed_shape)

    project = _project(empty_api)
    run = _wan3_draft(empty_api, project)
    empty_api.post(f"/api/runs/{run['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    closed = generate.close_from_prediction(record, {**closed_shape, "id": record["prediction_id"]})
    assert closed["status"] == "failed"
    assert "at most 10 items" in closed["error"]


def test_more_references_than_the_model_takes_is_refused_while_still_a_draft(
        empty_api, media_bucket):
    """`max_refs` was checked only where a frame counts toward it, so a plain
    over-long list went to the provider and came back as a 422 on a run
    already at `pending`. The cap holds on every model that declares one, and
    the refusal is a 400 that leaves the draft editable."""
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    stills = [_uploaded(empty_api, root, f"ref-{n}.png") for n in range(11)]
    resp = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": "wan-3.0-r2v",
        "model": "fal/alibaba/wan-3.0/reference-to-video",
        "plan": {"version": 1, "origin": "authored", "prompt": "the subject in Image 1 waves",
                 "params": {"duration": 5, "resolution": "480p"}},
        "sends": [{"field": "reference_image_urls", "role": "reference", "node": s["node_id"]}
                  for s in stills],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    run = resp.get_json()

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "at most 10 reference images" in resp.get_json()["error"]
    assert "got 11" in resp.get_json()["error"]
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "draft"


def test_the_readme_route_answers_for_a_fal_entry_without_a_provider_call(empty_api):
    body = empty_api.get("/api/models/wan-3.0-t2v/readme").get_json()

    assert body["readme"].startswith("# fal/alibaba/wan-3.0/text-to-video")
    assert "$0.10/s" in body["readme"]


# ── the fourth provider: OpenRouter ─────────────────────────────────────────


def _wan3_openrouter_draft(api, project, **body):
    resp = api.post("/api/runs", json={
        "project": project["id"],
        "kind": "video",
        "engine": "wan-3.0-openrouter",
        "model": "openrouter/alibaba/wan-3.0",
        "plan": {"version": 1, "origin": "authored",
                 "prompt": "a lighthouse on a rocky coast at golden hour, waves breaking",
                 "params": {"duration": 5, "resolution": "720p", "seed": 7}},
        **body,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def test_an_openrouter_run_is_submitted_through_the_openrouter_client(empty_api, monkeypatch):
    """`dispatch` picks the client off the entry's `provider`; the route records
    `openrouter` on the run before anything is sent; the webhook URL carries
    `?sig=` under the OpenRouter key, as Runpod's does."""
    from studio_core.clients import fal, openrouter, runpod
    seen = {}

    def create(model, payload, *, webhook=None):
        seen.update(model=model, payload=payload, webhook=webhook)
        return {"id": "gen-vid-1", "status": "pending"}

    monkeypatch.setattr(openrouter, "create_prediction", create)
    for other in (replicate, runpod, fal):
        monkeypatch.setattr(other, "create_prediction",
                            lambda *a, **k: pytest.fail("another provider was called"))
    monkeypatch.setenv("STUDIO_WEBHOOK_BASE_URL", "https://hooks.test")
    project = _project(empty_api)
    run = _wan3_openrouter_draft(empty_api, project)

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert seen["model"] == "openrouter/alibaba/wan-3.0"
    assert seen["payload"] == {"duration": 5, "resolution": "720p", "seed": 7,
                               "prompt": "a lighthouse on a rocky coast at golden hour, waves breaking"}
    assert seen["webhook"] == (f"https://hooks.test/api/hooks/openrouter/{run['id']}"
                               f"?sig={openrouter.callback_signature(run['id'])}")
    assert body["status"] == "running"
    assert body["provider"] == "openrouter"
    assert body["prediction_id"] == "gen-vid-1"


def test_an_openrouter_run_reconciles_through_the_openrouter_client(empty_api, media_bucket):
    """The fake answers a completed job in OpenRouter's own shape —
    `unsigned_urls`, `usage.cost` — and the run closes on it WITH a price."""
    project = _project(empty_api)
    run = _wan3_openrouter_draft(empty_api, project)
    empty_api.post(f"/api/runs/{run['id']}/submit")

    body = empty_api.post(f"/api/runs/{run['id']}/reconcile").get_json()

    assert body["status"] == "succeeded"
    assert len(body["outputs"]) == 1
    # The content route has no extension; the run's kind supplies it.
    assert body["outputs"][0]["name"].endswith(".mp4")
    assert body["cost"] == {"amount": 0.0, "currency": "USD", "predict_time": None}


def test_provider_of_infers_openrouter_from_the_model_id():
    assert generate.provider_of({"model": "openrouter/alibaba/wan-3.0"}) == "openrouter"
    assert generate.provider_of({"model": "openrouter/x", "provider": "fal"}) == "fal"


def test_openrouter_documents_are_normalised_into_the_seams_shape():
    """A poll answers the job bare; a webhook wraps it under `data`. Both land
    as `id`, `status`, `output`, `error`, and a document already in that
    shape is returned as it is."""
    from studio_core.clients import openrouter

    polled = openrouter.normalise({
        "id": "gen-vid-1", "generation_id": "gen-1", "status": "completed",
        "polling_url": "https://openrouter.ai/api/v1/videos/gen-vid-1",
        "unsigned_urls": ["https://openrouter.ai/api/v1/videos/gen-vid-1/content?index=0"],
        "usage": {"cost": 0.425, "is_byok": False}})
    assert polled["id"] == "gen-vid-1" and polled["status"] == "completed"
    assert polled["error"] is None
    assert openrouter.output_urls(polled) == [
        "https://openrouter.ai/api/v1/videos/gen-vid-1/content?index=0"]
    assert openrouter.cost(polled) == {"amount": 0.425, "currency": "USD", "predict_time": None}
    assert openrouter.normalise(polled) == polled

    hooked = openrouter.normalise({
        "type": "video.generation.failed", "created_at": "2026-09-18T00:00:00Z",
        "data": {"id": "gen-vid-2", "status": "failed", "error": "content policy",
                 "usage": {"cost": 0, "is_byok": False}}})
    assert hooked["id"] == "gen-vid-2" and hooked["status"] == "failed"
    assert hooked["error"] == "content policy" and hooked["output"] is None
    assert openrouter.output_urls(hooked) == []

    # A job that expired said nothing; the status is the reason.
    expired = openrouter.normalise({"id": "gen-vid-3", "status": "expired"})
    assert expired["error"] == "the job expired"
    assert openrouter.cost({"id": "gen-vid-4", "status": "pending"}) is None


def test_the_openrouter_request_folds_frames_and_references_into_its_shape():
    """`dispatch` writes a presigned URL into the seam's fields; the client
    folds `first_frame` / `last_frame` into `frame_images` and
    `input_references` into image parts, and everything else passes through.
    Pure, so it is tested without a wire."""
    from studio_core.clients import openrouter

    body = openrouter.request_body("openrouter/alibaba/wan-3.0", {
        "prompt": "x", "duration": 5, "resolution": "720p",
        "first_frame": "https://s3.invalid/a.png?sig=1",
        "input_references": ["https://s3.invalid/r1.png", "https://s3.invalid/r2.png"],
    }, webhook="https://hooks.test/api/hooks/openrouter/run-1?sig=abc")

    assert body == {
        "prompt": "x", "duration": 5, "resolution": "720p",
        "model": "alibaba/wan-3.0",
        "callback_url": "https://hooks.test/api/hooks/openrouter/run-1?sig=abc",
        "frame_images": [{"type": "image_url", "frame_type": "first_frame",
                          "image_url": {"url": "https://s3.invalid/a.png?sig=1"}}],
        "input_references": [{"type": "image_url", "image_url": {"url": "https://s3.invalid/r1.png"}},
                             {"type": "image_url", "image_url": {"url": "https://s3.invalid/r2.png"}}],
    }
    # No image, no lists: text-to-video sends neither key.
    bare = openrouter.request_body("openrouter/alibaba/wan-3.0", {"prompt": "x"})
    assert bare == {"prompt": "x", "model": "alibaba/wan-3.0"}


def test_a_bound_first_frame_reaches_openrouter_as_a_frame_image(empty_api, media_bucket, monkeypatch):
    """End to end through the route: a `first_frame` send is presigned by
    `dispatch` and arrives at the wire as a `frame_images` entry."""
    from studio_core.clients import openrouter
    seen = {}

    def answer(method, url, *, body=None, **kw):
        seen.update(method=method, url=url, body=body)
        return 202, {"id": "gen-vid-7", "status": "pending",
                     "polling_url": "https://openrouter.ai/api/v1/videos/gen-vid-7"}

    monkeypatch.setenv("STUDIO_OPENROUTER_MODE", "live")
    monkeypatch.setattr(openrouter, "_request", answer)
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    still = _uploaded(empty_api, root, "frame.png")
    run = _wan3_openrouter_draft(empty_api, project, sends=[
        {"field": "first_frame", "role": "start", "node": still["node_id"]}])

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()

    assert body["status"] == "running" and body["prediction_id"] == "gen-vid-7"
    assert seen["url"] == "https://openrouter.ai/api/v1/videos"
    frames = seen["body"]["frame_images"]
    assert len(frames) == 1 and frames[0]["frame_type"] == "first_frame"
    assert frames[0]["image_url"]["url"].startswith("http")
    assert "first_frame" not in seen["body"]
    assert seen["body"]["model"] == "alibaba/wan-3.0"


def test_an_openrouter_refusal_hands_the_draft_back_with_its_words(empty_api, monkeypatch):
    """A `402 Insufficient credits` is the ordinary refusal here, and it must
    not wedge a draft at `pending` — the draft comes back with OpenRouter's
    sentence on it, as with Runpod's and fal's."""
    from studio_core.clients import openrouter

    monkeypatch.setenv("STUDIO_OPENROUTER_MODE", "live")
    monkeypatch.setattr(openrouter, "_request", lambda method, url, *, body=None, **kw: (
        402, {"error": {"code": 402,
                        "message": "Insufficient credits. Add more using https://openrouter.ai/credits"}}))
    project = _project(empty_api)
    run = _wan3_openrouter_draft(empty_api, project)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")

    assert resp.status_code == 502
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] == "draft"
    assert record["error"] == ("openrouter refused the submission (402): Insufficient "
                               "credits. Add more using https://openrouter.ai/credits")


def test_the_openrouter_schema_is_synthesised_from_the_model_card(monkeypatch):
    """No OpenAPI document per model: the card on `/videos/models` says what
    the model takes, and that is read into the two maps `check` wants —
    `first_frame` only when the card lists it, `required` naming `prompt`."""
    from studio_core.clients import openrouter

    card = {"id": "alibaba/wan-3.0", "supported_resolutions": ["480p", "720p", "1080p"],
            "supported_aspect_ratios": ["16:9", "9:16"], "supported_sizes": None,
            "supported_durations": [2, 3, 4, 5], "supported_frame_images": ["first_frame"],
            "generate_audio": True, "seed": True, "allowed_passthrough_parameters": []}
    monkeypatch.setenv("STUDIO_OPENROUTER_MODE", "live")
    monkeypatch.setattr(openrouter, "_models", {})
    monkeypatch.setattr(openrouter, "_request", lambda *a, **k: (200, {"data": [card]}))

    props, schemas = openrouter.model_schema("openrouter/alibaba/wan-3.0")

    assert schemas["Input"]["required"] == ["prompt"]
    assert props["resolution"]["enum"] == ["480p", "720p", "1080p"]
    assert props["duration"] == {"type": "integer", "title": "Duration", "enum": [2, 3, 4, 5],
                                 "minimum": 2, "maximum": 5}
    assert "first_frame" in props and "last_frame" not in props
    assert props["generate_audio"]["default"] is True and "seed" in props
    assert "negative_prompt" not in props

    with pytest.raises(openrouter.OpenRouterError):
        openrouter.model_schema("openrouter/nobody/nothing")


def test_the_openrouter_download_sends_the_key(monkeypatch, tmp_path):
    """The content route is OpenRouter's own and answers 401 without the
    bearer; a 404 there is the output gone, its own type."""
    import io
    import urllib.error
    import urllib.request
    from studio_core.clients import openrouter
    seen = {}

    class _Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "video/mp4"}
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(request, timeout=None):
        seen["auth"] = request.get_header("Authorization")
        return _Response(b"mp4-bytes")

    monkeypatch.setenv("STUDIO_OPENROUTER_MODE", "live")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    target = tmp_path / "out.mp4"

    got = openrouter.download("https://openrouter.ai/api/v1/videos/g/content?index=0",
                              str(target), max_bytes=1 << 20)

    assert got.written == 9 and target.read_bytes() == b"mp4-bytes"
    assert got.content_type == "video/mp4", "the served type rides back with the bytes"
    assert seen["auth"] == "Bearer dud-key-the-suite-must-never-use"

    def gone(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "gone", {}, io.BytesIO(b""))
    monkeypatch.setattr(urllib.request, "urlopen", gone)
    with pytest.raises(openrouter.OutputGone):
        openrouter.download("https://openrouter.ai/x", str(target), max_bytes=1 << 20)


def test_the_readme_route_answers_for_an_openrouter_entry_without_a_provider_call(empty_api):
    body = empty_api.get("/api/models/wan-3.0-openrouter/readme").get_json()

    assert body["readme"].startswith("# openrouter/alibaba/wan-3.0")
    assert "usage.cost" in body["readme"]


def test_the_job_script_reports_once_and_then_holds_the_container():
    """A pod restarts its command when it exits, on the same disk. Measured on
    the first real run: the finished trainer re-ran, re-reported, and re-billed
    every six minutes until the pod was terminated by hand. The script marks
    the report and holds; a restart finds the mark and holds without running."""
    from studio_core.services import training

    script = training.JOB_SCRIPT
    guard = script.index("if [ -f /workspace/.reported ]")
    assert guard < script.index("python run.py"), "the guard runs before the trainer"
    assert script.rstrip().endswith("exec sleep infinity")
    assert script.index("touch /workspace/.reported") > script.index('m["callback"]'), \
        "the mark is set only after the report and callback"


# ── three trainers, one run shape ───────────────────────────────────────────
#
# `wan-2.2-lora-train` writes a pair per save point; `ltx-2.3-lora-train` and
# `hunyuan-video-lora-train` write one file. The job script reads `arch` off
# the manifest; the Wan config it writes is held to a golden copy captured
# before the switch existed, byte for byte.

GOLDEN = pathlib.Path(__file__).parent / "fixtures" / "wan22-job-config.json"


def test_the_wan_config_the_job_writes_is_byte_for_byte_what_it_was(tmp_path):
    """Captured 2026-09-20 from the single-arch script, for both bases with
    and without sampling. The arch switch may add trainers; it may not move
    a value in the config the Wan run gets."""
    golden = json.loads(GOLDEN.read_text())
    assert len(golden) == 4
    for case, expected in golden.items():
        manifest = dict(expected["manifest"])
        assert "arch" not in manifest, "a manifest from before the switch names no arch"
        (tmp_path / case).mkdir()
        assert _written_config(tmp_path / case, manifest) == expected["process"], case
        # And with the arch spelled out, the same.
        (tmp_path / (case + "-named")).mkdir()
        assert _written_config(tmp_path / (case + "-named"), {**manifest, "arch": "wan22", "experts": ["high", "low"]}) == expected["process"], case


def test_the_job_writes_the_ltx_config_for_the_ltx_arch(tmp_path):
    """One transformer: no expert split, the mono checkpoint ai-toolkit's own
    registry names for `ltx2.3`, quantised the way that registry defaults it,
    latents cached, `weighted` timesteps; samples text-only (no `--ctrl_img`),
    at the guidance the arch's registry names."""
    manifest = {
        "arch": "ltx23", "experts": [], "stem": "subject-a-ohwx-sa-1234", "trigger": "ohwx_sa",
        "steps": 1500, "save_every": 250, "rank": 32, "lr": 1e-4, "resolution": 768, "base": None,
        "sample_prompts": ["ohwx_sa, cooking in a bright kitchen, medium shot"],
        "sample_seed": 42, "sample_steps": 20,
        "dataset": [{"name": "a.png", "url": "https://bucket.test/a.png?x", "caption": "ohwx_sa, grey t-shirt"}],
    }
    cfg = _written_config(tmp_path, manifest)
    assert cfg["model"] == {"name_or_path": "Lightricks/LTX-2.3/ltx-2.3-22b-dev.safetensors",
                            "arch": "ltx2.3", "quantize": True, "quantize_te": True, "low_vram": False}
    assert cfg["network"] == {"type": "lora", "linear": 32, "linear_alpha": 32}
    assert cfg["train"]["timestep_type"] == "weighted"
    assert "switch_boundary_every" not in cfg["train"]
    assert cfg["datasets"][0]["cache_latents_to_disk"] is True
    assert cfg["datasets"][0]["num_frames"] == 1
    assert cfg["sample"]["prompts"] == ["ohwx_sa, cooking in a bright kitchen, medium shot"]
    assert cfg["sample"]["guidance_scale"] == 3.0
    assert cfg["sample"]["num_frames"] == 1
    assert cfg["train"]["disable_sampling"] is False


def test_expected_files_are_one_per_save_point_without_experts():
    from studio_core.services import training
    assert training.expected_files("s", 750, 250, ()) == [
        "s_000000250.safetensors", "s_000000500.safetensors", "s.safetensors"]
    assert training.expected_files("s", 750, 250) == training.expected_files("s", 750, 250, ("high", "low"))
    assert training.trainer_of({"model": training.LTX23})["experts"] == ()
    assert training.trainer_of({"model": training.WAN22})["experts"] == ("high", "low")
    with pytest.raises(ValidationError):
        training.trainer_of({"model": "runpod-pod/nothing-like-this"})


def _ltx_training_draft(api, project, character, nodes, **params):
    resp = api.post("/api/runs", json={
        "project": project["id"], "kind": "training", "engine": "ltx-2.3-lora-train",
        "model": "runpod-pod/ai-toolkit-ltx23-22b", "characters": [character["id"]],
        "plan": {"version": 1, "origin": "authored", "prompt": None,
                 "params": {"trigger": "ohwx_sa", "steps": 500, "save_every": 250,
                            "sample_prompts": [], **params}},
        "sends": [{"field": "dataset", "role": "reference", "node": n} for n in nodes],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def test_an_ltx_training_run_pre_makes_one_file_per_save_point_and_names_its_arch(
        empty_api, media_bucket):
    """Same dispatch, different naming: the manifest says `arch: ltx23` and no
    experts, the script is ai-toolkit's, the outputs are `<stem>_<step>` and
    a bare `<stem>` — three nodes for 500 steps at 250, not six — and the
    pod is rented from the pinned ai-toolkit image."""
    from studio_core.clients import runpod_pods
    from studio_core.services import training
    project = _project(empty_api)
    character = _character(empty_api)
    run = _ltx_training_draft(empty_api, project, character, _dataset(empty_api, character))

    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()
    assert body["status"] == "running", body
    manifest = json.loads(media_bucket.get_object(
        Bucket=config.media_bucket(), Key=training.MANIFEST_KEY.format(run=run["id"]))["Body"].read())
    assert manifest["arch"] == "ltx23" and manifest["experts"] == []
    assert manifest["base"] is None
    assert manifest["script"] == training.JOB_SCRIPT
    stem = manifest["stem"]
    assert sorted(manifest["outputs"]) == sorted([f"{stem}_000000250.safetensors", f"{stem}.safetensors"])
    assert manifest["samples"] == []
    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    made = record["payload"]["training"]["outputs"]
    assert set(made) == set(manifest["outputs"])
    pod = runpod_pods.get_pod(body["prediction_id"])
    assert pod["gpu"]["id"] == "NVIDIA H100 80GB HBM3", "the entry defaults to an H100"


def test_the_pod_is_rented_from_the_trainers_image(monkeypatch):
    """`create_pod` sends the pinned ai-toolkit image unless the trainer names
    its own — the musubi job does."""
    from studio_core.clients import runpod_pods
    sent = {}
    monkeypatch.setenv("STUDIO_RUNPOD_MODE", "live")
    monkeypatch.setattr(runpod_pods, "_request",
                        lambda method, url, body=None: (sent.update(body=body) or {"id": "pod-x"}))
    runpod_pods.create_pod(name="n", gpu="h100", cloud="secure", env={}, start_cmd=["true"])
    assert sent["body"]["imageName"] == runpod_pods.IMAGE
    runpod_pods.create_pod(name="n", gpu="h100", cloud="secure", env={}, start_cmd=["true"],
                           image="runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04")
    assert sent["body"]["imageName"] == "runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04"


def test_a_hunyuan_training_run_gets_the_musubi_job_and_draws_no_samples(empty_api, media_bucket):
    """No ai-toolkit arch for HunyuanVideo: the manifest carries the musubi
    script, single-file outputs, and a sample list is refused before
    `pending` because that job cannot draw one."""
    from studio_core.services import training
    project = _project(empty_api)
    character = _character(empty_api)
    nodes = _dataset(empty_api, character)
    refused = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "training", "engine": "hunyuan-video-lora-train",
        "model": "runpod-pod/musubi-hunyuan-video", "characters": [character["id"]],
        "plan": {"version": 1, "origin": "authored", "prompt": None,
                 "params": {"trigger": "ohwx_sa", "steps": 500, "save_every": 250,
                            "sample_prompts": ["{trigger}, on a beach"]}},
        "sends": [{"field": "dataset", "role": "reference", "node": n} for n in nodes],
    }).get_json()
    resp = empty_api.post(f"/api/runs/{refused['id']}/submit")
    assert resp.status_code == 400 and "sample_prompts" in resp.get_data(as_text=True)
    assert empty_api.get(f"/api/runs/{refused['id']}").get_json()["status"] == "draft"

    run = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "training", "engine": "hunyuan-video-lora-train",
        "model": "runpod-pod/musubi-hunyuan-video", "characters": [character["id"]],
        "plan": {"version": 1, "origin": "authored", "prompt": None,
                 "params": {"trigger": "ohwx_sa", "steps": 500, "save_every": 250}},
        "sends": [{"field": "dataset", "role": "reference", "node": n} for n in nodes],
    }).get_json()
    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()
    assert body["status"] == "running", body
    manifest = json.loads(media_bucket.get_object(
        Bucket=config.media_bucket(), Key=training.MANIFEST_KEY.format(run=run["id"]))["Body"].read())
    assert manifest["arch"] == "hunyuan" and manifest["experts"] == []
    assert manifest["script"] == training.MUSUBI_JOB_SCRIPT
    assert manifest["lr"] == 0.0002, "the entry's own default, not the module's"
    assert manifest["sample_prompts"] == []
    assert sorted(manifest["outputs"]) == sorted([f"{manifest['stem']}_000000250.safetensors",
                                                  f"{manifest['stem']}.safetensors"])
    # The musubi script is bash around the same uploader and the same report.
    assert "hv_train_network.py" in manifest["script"]
    assert training.UPLOADER in manifest["script"] and training.REPORT in manifest["script"]
    assert training.UPLOADER in training.JOB_SCRIPT and training.REPORT in training.JOB_SCRIPT


def test_the_uploader_files_a_single_file_checkpoint_and_renames_musubis(tmp_path, monkeypatch):
    """With no experts the sweep takes every `.safetensors` in the output
    folder; a musubi name (`<stem>-step00000250`) goes up as studio's
    `<stem>_000000250`, the last one as `<stem>`. The conversion step is
    stubbed: it is musubi's own script, not here to test."""
    import subprocess
    import urllib.request
    out = tmp_path / "output" / "stem"
    out.mkdir(parents=True)
    for name in ["stem-step00000250.safetensors", "stem-step00000500.safetensors", "stem.safetensors"]:
        (out / name).write_bytes(b"w" * 16)
    (out / "stem-step00000250-state").mkdir()
    names = ["stem_000000250.safetensors", "stem.safetensors"]
    job = tmp_path / "job.json"
    job.write_text(json.dumps({
        "pod": {"id": "pod-1"}, "stem": "stem", "steps": 500, "arch": "hunyuan", "experts": [],
        "outputs": {name: f"https://bucket.test/{name}?grant" for name in names},
        "callback": None,
    }))
    calls = []
    converted = []

    class _Answer:
        def read(self):
            return b""

    def urlopen(req, timeout=None):
        calls.append((req.get_method(), req.full_url, req.data))
        return _Answer()

    def run(cmd, check):
        converted.append(cmd)
        pathlib.Path(cmd[cmd.index("--output") + 1]).write_bytes(b"c" * 8)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("sys.argv", ["uploader", "final"])
    source = (_uploader_source()
              .replace("/tmp/job.json", str(job))
              .replace("/workspace/output", str(tmp_path / "output"))
              .replace("/tmp/converted", str(tmp_path / "converted"))
              .replace("/tmp/uploaded.json", str(tmp_path / "uploaded.json")))
    exec(compile(source, "uploader.py", "exec"), {"__name__": "__main__"})

    puts = [(url, data) for method, url, data in calls if method == "PUT"]
    # step 500 IS the final step, so `-step00000500` maps onto `stem` too and
    # the first file to claim the name wins; nothing is uploaded twice.
    assert [url for url, _ in puts] == [f"https://bucket.test/{n}?grant" for n in names]
    assert all(data == b"c" * 8 for _, data in puts), "the converted bytes go up, not musubi's"
    assert len(converted) == 2 and all("--target" in cmd and "other" in cmd for cmd in converted)
    assert json.loads((tmp_path / "uploaded.json").read_text()) == sorted(names)


def test_a_fal_entrys_own_fields_overlay_its_live_schema():
    """`lora_scale` is studio's, declared in the entry's `input` block as it
    is on a Runpod entry; on a fal entry the live schema lacks it, and without
    the overlay `check` would refuse the field as unknown."""
    from studio_core.services import registry, schema
    entry = registry.get("ltx-2.3-i2v-lora")
    live = {"prompt": {"type": "string"}, "loras": {"type": "array"}, "image_url": {"type": "string"}}
    props, schemas = schema._with_own_fields(entry, live, {"Input": {"required": ["prompt"]}})
    assert set(props) == {"prompt", "loras", "image_url", "lora_scale"}
    assert props["lora_scale"]["maximum"] == 4
    assert schema.check({"prompt": "x", "lora_scale": 0.9}, {"loras": ["n1"], "image_url": "n2"},
                        entry["model"], props, schemas) == []
    # A fetch that failed stays failed: nothing is overlaid on an empty map.
    assert schema._with_own_fields(entry, {}, {}) == ({}, {})
    assert registry.lora_fields(entry) == {"loras"}
    assert registry.lora_scale_param(entry) == "lora_scale"


def test_a_single_slot_lora_send_goes_out_as_path_and_scale_on_fal(empty_api, monkeypatch):
    """The LTX endpoint has one `loras` list; a LoRA bound to it goes out as
    `[{path, scale}]` with the plan's `lora_scale` folded in, exactly as Wan's
    two slots do."""
    from studio_core.clients import fal
    seen = {}
    monkeypatch.setattr(fal, "create_prediction",
                        lambda model, payload, *, webhook=None:
                        (seen.update(model=model, payload=payload) or {"id": "req-lora", "status": "IN_QUEUE"}))
    project = _project(empty_api)
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    still = _uploaded(empty_api, root, "frame.png")
    lora = _uploaded(empty_api, root, "subject-a-ohwx-sa-1234.safetensors")
    resp = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": "ltx-2.3-i2v-lora",
        "model": "fal/fal-ai/ltx-2.3-22b/image-to-video/lora",
        "plan": {"version": 1, "origin": "authored", "prompt": "ohwx_sa turns to camera",
                 "params": {"num_frames": 121, "seed": 3, "lora_scale": 1.1, "generate_audio": False}},
        "sends": [
            {"field": "image_url", "role": "start", "node": still["node_id"]},
            {"field": "loras", "role": "lora", "node": lora["node_id"]},
        ],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    run = resp.get_json()
    body = empty_api.post(f"/api/runs/{run['id']}/submit").get_json()
    assert body["status"] == "running", body
    payload = seen["payload"]
    assert seen["model"] == "fal/fal-ai/ltx-2.3-22b/image-to-video/lora"
    assert "lora_scale" not in payload
    assert payload["loras"] == [{"path": payload["loras"][0]["path"], "scale": 1.1}]
    assert payload["loras"][0]["path"].startswith("http") and payload["image_url"].startswith("http")
    assert payload["num_frames"] == 121 and payload["generate_audio"] is False


# --------------------------------------------------------------------------
# A multi-shot timeline adds up, whichever way its provider spells a second
# --------------------------------------------------------------------------
#
# `duration` is an INTEGER on the Replicate Kling entry and a STRING enum
# ("3".."15") on the fal ones — the reason the two are registered separately.
# The E006 preflight compared the sum of the shot durations against it with
# `!=`, so on a fal entry `15 != "15"` was true of a timeline that added up
# perfectly, while passing an int to satisfy it failed the live schema. Between
# the two, multi-shot was impossible there.

_FAL_KLING = {"key": "fal-kling-v3-i2v", "model": "fal/kling", "kind": "video",
              "video": {"max_cuts": 6}}
_REPLICATE_KLING = {**_FAL_KLING, "key": "replicate-kling",
                    "model": "kwaivgi/kling-v3-omni-video"}


def _beats(*seconds):
    return [{"prompt": f"beat {n}", "duration": s} for n, s in enumerate(seconds, 1)]


@pytest.mark.parametrize("entry, duration, beats", [
    (_FAL_KLING, "15", (5, 5, 5)),          # the string case that used to refuse
    (_FAL_KLING, "9", ("3", "3", "3")),     # shots spelled fal's way too
    (_REPLICATE_KLING, 10, (6, 4)),         # the int one, unchanged
])
def test_a_timeline_that_adds_up_passes_however_its_seconds_are_spelled(
        entry, duration, beats):
    generate._check_payload_rules(entry, {"duration": duration,
                                          "multi_prompt": _beats(*beats)})


@pytest.mark.parametrize("duration", ["15", 15])
def test_a_timeline_that_does_not_add_up_is_still_E006(duration):
    with pytest.raises(Exception) as refusal:
        generate._check_payload_rules(
            _FAL_KLING, {"duration": duration, "multi_prompt": _beats(5, 5)})
    # The marker and the sentence's shape are referenced by the skills.
    assert "this is E006" in str(refusal.value)


@pytest.mark.parametrize("payload", [
    {"duration": "fifteen", "multi_prompt": [{"prompt": "a", "duration": 15}]},
    {"duration": "", "multi_prompt": [{"prompt": "a", "duration": 15}]},
    {"duration": "15", "multi_prompt": [{"prompt": "a", "duration": "five"}]},
])
def test_a_duration_that_is_no_number_is_refused_not_crashed(payload):
    """A bad value is a refusal with words, never a `ValueError` out of a preflight."""
    with pytest.raises(Exception) as refusal:
        generate._check_payload_rules(_FAL_KLING, payload)
    assert "number of seconds" in str(refusal.value)


def test_no_duration_field_means_there_is_nothing_to_sum_against():
    generate._check_payload_rules(
        _FAL_KLING, {"multi_prompt": _beats(5, 5)})


# --------------------------------------------------------------------------
# On fal, a timeline REPLACES the prompt — the two never go out together
# --------------------------------------------------------------------------
#
# fal's OpenAPI says it on the `prompt` field of both Kling entries:
#
#     "Text prompt for video generation. Either prompt or multi_prompt must be
#      provided, but not both."
#
# and the input schema's `required` array is `["start_image_url"]` alone, so a
# payload with no prompt is a complete one there. Replicate's proxy for the same
# model family requires `prompt`, so the rule is a property of the ENTRY —
# `video.shots_replace_prompt` — and these tests read it off the real registry
# rather than a literal, because a flag that stopped being set would otherwise
# leave both sides passing.
#
# The API REFUSES a payload carrying both rather than repairing it: the CLI
# folds the globals into the first beat while the payload is being built, so
# what a person read under hard rule #2 is what goes out. Rewriting it here,
# after it was read and approved, would make that render a lie.

_FAL_ENTRY = registry.get("fal-kling-v3-i2v")
_REPLICATE_ENTRY = registry.get("replicate-kling")


def test_the_registry_says_which_entries_replace_the_prompt():
    """The flag itself, since every refusal below hangs off it."""
    assert registry.field(_FAL_ENTRY, "video.shots_replace_prompt") is True
    assert registry.field(registry.get("fal-kling-o3-r2v"),
                          "video.shots_replace_prompt") is True
    assert registry.field(_REPLICATE_ENTRY, "video.shots_replace_prompt") is None


def test_a_prompt_beside_a_timeline_is_refused_on_fal():
    with pytest.raises(Exception) as refusal:
        generate._check_payload_rules(
            _FAL_ENTRY, {"duration": "10", "prompt": "the setting, the cast",
                         "multi_prompt": _beats(5, 5)})
    said = str(refusal.value)
    assert "Either prompt or multi_prompt must be provided, but not both" in said
    assert "fal-kling-v3-i2v" in said


def test_a_timeline_alone_is_a_complete_payload_on_fal():
    generate._check_payload_rules(
        _FAL_ENTRY, {"duration": "10", "multi_prompt": _beats(5, 5)})


def test_replicate_still_sends_both_and_is_not_refused():
    """Replicate's proxy REQUIRES `prompt`; the two providers must not drift."""
    generate._check_payload_rules(
        _REPLICATE_ENTRY, {"duration": 10, "prompt": "the setting, the cast",
                           "multi_prompt": json.dumps(_beats(5, 5))})


def test_the_cap_follows_the_text_into_the_first_beat():
    """Folding the globals in can blow the ceiling, and the refusal says why."""
    beats = [{"prompt": "x" * 2600, "duration": 5},
             {"prompt": "the second beat", "duration": 5}]
    with pytest.raises(Exception) as refusal:
        generate._check_payload_rules(
            _FAL_ENTRY, {"duration": "10", "multi_prompt": beats})
    said = str(refusal.value)
    assert "2500" in said and "shot 1" in said and "2600" in said
    assert "globals" in said


def test_a_later_beat_over_the_cap_is_refused_without_blaming_the_fold():
    beats = [{"prompt": "the first beat", "duration": 5},
             {"prompt": "x" * 2600, "duration": 5}]
    with pytest.raises(Exception) as refusal:
        generate._check_payload_rules(
            _FAL_ENTRY, {"duration": "10", "multi_prompt": beats})
    said = str(refusal.value)
    assert "shot 2" in said and "globals" not in said


def test_a_long_beat_on_replicate_is_not_measured_against_the_prompt_cap():
    """There the beats go out BESIDE a prompt that has its own 2500."""
    generate._check_payload_rules(
        _REPLICATE_ENTRY,
        {"duration": 10, "prompt": "the setting",
         "multi_prompt": json.dumps([{"prompt": "x" * 2600, "duration": 5},
                                     {"prompt": "y", "duration": 5}])})
