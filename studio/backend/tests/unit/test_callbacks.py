"""The callback path: receive, queue, verify, close.

Three components and one property holding them together — **the code that closes
a run is written once and reached from three places.** A worker Lambda in prod, a
process on a developer's laptop, and `POST /api/runs/<id>/reconcile` when neither
happened.

The split exists because Replicate cannot reach `http://localhost:8000`. With the
close inline in the API Lambda, the webhook path could not run on a developer's
machine at all: local development polled instead, so the most expensive path in
studio first executed for real in production. Receiving is now a
dependency-free zip Lambda that only enqueues, and processing is the working
tree.

**The receiver deliberately does not verify the signature.** It holds no
credential and no HTTP client — that is what makes it cheap enough to exist in
the per-machine dev environment — so it carries the raw bytes through
base64-encoded and the consumer checks them. Which means the verification tests
below are testing the thing that actually guards the queue, in the module both
consumers share.
"""

import base64
import hashlib
import hmac
import json
import time

import pytest

from studio_core.clients import replicate
from studio_core.handlers.aws.hook import hook_handler
from studio_core.services import callbacks, catalog

SECRET = "whsec_" + base64.b64encode(b"a-test-signing-key").decode()


def _signed(body: bytes, *, webhook_id="msg_1", timestamp=None, secret=SECRET):
    """Headers Replicate would send for this exact body.

    Computed rather than hard-coded, because the thing under test is that the MAC
    is taken over `<id>.<timestamp>.<body>` — a fixture with a frozen signature
    would pass against any implementation that agreed with itself.
    """
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    key = base64.b64decode(secret.split("_", 1)[-1])
    signed = f"{webhook_id}.{stamp}.".encode() + body
    mac = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"webhook-id": webhook_id, "webhook-timestamp": stamp,
            "webhook-signature": f"v1,{mac}"}


def _message(run_id: str, prediction: dict, **kw) -> dict:
    body = json.dumps(prediction).encode()
    return {"run": run_id, "headers": _signed(body, **kw),
            "body_b64": base64.b64encode(body).decode()}


@pytest.fixture(autouse=True)
def _known_secret(monkeypatch):
    monkeypatch.setattr(replicate, "webhook_secret", lambda: SECRET)


# ── verification ────────────────────────────────────────────────────────────


def test_a_correctly_signed_callback_verifies():
    body = b'{"id":"pred-1","status":"succeeded"}'
    replicate.verify_webhook(SECRET, **{
        "webhook_id": "msg_1",
        "timestamp": _signed(body)["webhook-timestamp"],
        "signature_header": _signed(body)["webhook-signature"],
        "body": body,
        "tolerance": 300,
    })


def test_the_signature_is_over_the_EXACT_bytes_that_arrived():
    """**Re-serialising the parsed JSON signs something the sender never did.**

    Key order and whitespace are exactly what an HMAC notices, so a consumer that
    verified `json.dumps(json.loads(body))` would fail every genuine callback —
    which fails closed, and so would present as "everything is forged" rather
    than as a signing bug.
    """
    body = b'{"status":"succeeded","id":"pred-1"}'
    headers = _signed(body)
    reordered = json.dumps(json.loads(body)).encode()
    assert reordered != body

    with pytest.raises(ValueError):
        replicate.verify_webhook(
            SECRET, headers["webhook-id"], headers["webhook-timestamp"],
            headers["webhook-signature"], reordered, 300)


def test_a_stale_callback_is_refused_even_though_its_signature_is_valid():
    """**A signature never expires, so the timestamp is what bounds replay.**

    Without a window, a captured callback could be re-sent forever to re-close a
    run — which is not academic here, because closing a run uploads a file and
    stamps a cost.
    """
    body = b'{"id":"pred-1","status":"succeeded"}'
    headers = _signed(body, timestamp=int(time.time()) - 4000)

    with pytest.raises(ValueError) as raised:
        replicate.verify_webhook(
            SECRET, headers["webhook-id"], headers["webhook-timestamp"],
            headers["webhook-signature"], body, 300)
    assert "window" in str(raised.value)


def test_a_callback_signed_with_another_key_is_refused():
    body = b'{"id":"pred-1","status":"succeeded"}'
    other = "whsec_" + base64.b64encode(b"not-the-right-key").decode()
    headers = _signed(body, secret=other)

    with pytest.raises(ValueError):
        replicate.verify_webhook(
            SECRET, headers["webhook-id"], headers["webhook-timestamp"],
            headers["webhook-signature"], body, 300)


def test_several_signatures_are_offered_and_any_one_may_match():
    """Standard Webhooks sends a space-separated list so a key rotation can
    present two at once. Matching only the first would drop half of a rotation."""
    body = b'{"id":"pred-1","status":"succeeded"}'
    headers = _signed(body)
    both = f"v1,{'A' * 43}= {headers['webhook-signature']}"

    replicate.verify_webhook(
        SECRET, headers["webhook-id"], headers["webhook-timestamp"], both, body, 300)


def test_a_callback_with_no_signature_headers_is_refused():
    with pytest.raises(ValueError):
        replicate.verify_webhook(SECRET, "", "", "", b"{}", 300)


# ── the receiver ────────────────────────────────────────────────────────────


class _Queue:
    def __init__(self):
        self.sent = []

    def send_message(self, **kw):
        self.sent.append(kw)


@pytest.fixture
def queue(monkeypatch):
    q = _Queue()
    monkeypatch.setattr(hook_handler, "_client", lambda: q)
    monkeypatch.setenv("STUDIO_CALLBACK_QUEUE_URL", "https://sqs.test/q")
    return q


def _event(run_id, body: bytes, headers=None, base64_encoded=False):
    return {
        "pathParameters": {"run_id": run_id},
        "headers": headers if headers is not None else _signed(body),
        "body": base64.b64encode(body).decode() if base64_encoded else body.decode(),
        "isBase64Encoded": base64_encoded,
    }


def test_the_receiver_enqueues_the_body_verbatim(queue):
    """**Base64, because the signature is over these exact bytes.**

    A JSON round trip of the decoded string is not guaranteed to reproduce them,
    and the consumer would then refuse every genuine callback.
    """
    body = b'{"status":"succeeded","id":"pred-1"}'

    answer = hook_handler.handler(_event("run-abc", body), None)

    assert answer["statusCode"] == 202
    message = json.loads(queue.sent[0]["MessageBody"])
    assert base64.b64decode(message["body_b64"]) == body
    assert message["run"] == "run-abc"


def test_the_receiver_carries_only_the_signature_headers(queue):
    """An allowlist, not the whole map. API Gateway forwards a great deal that
    has no business being copied into a message a laptop will read."""
    body = b"{}"
    headers = {**_signed(body), "cookie": "session=secret", "x-forwarded-for": "1.2.3.4"}

    hook_handler.handler(_event("run-abc", body, headers=headers), None)

    carried = json.loads(queue.sent[0]["MessageBody"])["headers"]
    assert set(carried) == {"webhook-id", "webhook-timestamp", "webhook-signature"}


def test_the_receiver_decodes_a_base64_body(queue):
    """API Gateway may deliver either shape, and the raw bytes have to survive."""
    body = b'{"id":"pred-1"}'

    hook_handler.handler(_event("run-abc", body, base64_encoded=True), None)

    message = json.loads(queue.sent[0]["MessageBody"])
    assert base64.b64decode(message["body_b64"]) == body


def test_the_receiver_refuses_a_path_that_names_no_run(queue):
    """Nothing downstream could act on it, so nothing is queued for it."""
    answer = hook_handler.handler(_event("../etc/passwd", b"{}"), None)

    assert answer["statusCode"] == 404
    assert queue.sent == []


def test_the_receiver_refuses_an_oversized_body(queue, monkeypatch):
    """SQS refuses a message over 256 KiB, and a failed video's `logs` can be
    large. Capped here, where the refusal can be logged against a run id."""
    monkeypatch.setattr(hook_handler, "MAX_BODY_BYTES", 64)

    answer = hook_handler.handler(_event("run-abc", b"x" * 200), None)

    assert answer["statusCode"] == 413
    assert queue.sent == []


# ── the consumer ────────────────────────────────────────────────────────────


def _running_run(api):
    project = api.post("/api/projects", json={"slug": "rooftop-teaser"}).get_json()
    run = api.post("/api/runs", json={
        "project": project["id"], "kind": "image", "engine": "nano-banana-pro",
        "model": "google/nano-banana-pro",
        "plan": {"version": 1, "origin": "authored", "prompt": "a porch",
                 "params": {}},
    }).get_json()
    api.post(f"/api/runs/{run['id']}/approve", json={"digest": run["plan_digest"]})
    api.post(f"/api/runs/{run['id']}/submit")
    return catalog.entity(catalog.ENTITY_RUN, run["id"])


def test_a_verified_callback_closes_the_run(empty_api, media_bucket):
    """The whole path, end to end, in the module both consumers drive."""
    record = _running_run(empty_api)

    closed = callbacks.process(_message(record["id"], {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"],
    }))

    assert closed["status"] == "succeeded"
    assert len(closed["outputs"]) == 1


def test_an_unverifiable_callback_is_rejected_rather_than_retried(empty_api):
    """**A bad signature is not transient.** The same bytes fail the same way
    forever, so redriving them would fill the dead-letter queue with noise.
    `Rejected` is what tells both consumers to delete rather than redrive."""
    record = _running_run(empty_api)
    message = _message(record["id"], {"id": record["prediction_id"],
                                      "status": "succeeded"})
    message["headers"]["webhook-signature"] = "v1,not-a-signature"

    with pytest.raises(callbacks.Rejected):
        callbacks.process(message)

    assert catalog.entity(catalog.ENTITY_RUN, record["id"])["status"] == "running"


def test_a_callback_naming_another_prediction_is_rejected(empty_api):
    """The signature held, so it really is the provider — and applying it would
    close this run with somebody else's output."""
    record = _running_run(empty_api)

    with pytest.raises(callbacks.Rejected) as raised:
        callbacks.process(_message(record["id"], {
            "id": "pred-belonging-to-another-run", "status": "succeeded",
            "output": ["https://fake.invalid/x/0.png"]}))
    assert "not" in str(raised.value)


def test_a_callback_for_a_deleted_run_is_rejected(empty_api):
    """Verified, and about a run this library no longer has. There is nothing to
    retry toward, so it is dropped rather than redriven."""
    message = _message("run-00000000-0000-4000-8000-000000000000",
                       {"id": "pred-1", "status": "succeeded"})

    with pytest.raises(callbacks.Rejected):
        callbacks.process(message)


def test_a_duplicate_callback_does_not_upload_the_output_twice(
        empty_api, media_bucket):
    """SQS is at-least-once and the receiver acks before verifying anything, so a
    repeat is ordinary traffic."""
    record = _running_run(empty_api)
    message = _message(record["id"], {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png"]})

    first = callbacks.process(message)
    again = callbacks.process(message)

    assert again["outputs"] == first["outputs"]


def test_a_message_that_is_not_json_is_rejected():
    with pytest.raises(callbacks.Rejected):
        callbacks.handle("not json at all")


def test_a_message_naming_no_run_is_rejected():
    with pytest.raises(callbacks.Rejected):
        callbacks.handle(json.dumps({"run": "", "headers": {}, "body_b64": ""}))


# ── the two drivers ─────────────────────────────────────────────────────────
#
# Neither holds any logic; what they hold is a decision about what to do when
# `process` raises, and the two answers differ in a way that matters.


def test_the_worker_reports_only_the_message_that_failed(monkeypatch):
    """**Partial batch response, and without it one bad callback redrives ten.**

    Nine runs that closed correctly would be closed again — harmless, because
    closing is idempotent, and wasteful, because each retry wakes 2 GB of Lambda
    to do nothing.
    """
    from studio_core.handlers.aws.worker import worker_handler

    def handle(body):
        if "boom" in body:
            raise RuntimeError("S3 refused the write")
        return {"id": "run-x", "status": "succeeded"}

    monkeypatch.setattr(callbacks, "handle", handle)

    answer = worker_handler.handler({"Records": [
        {"messageId": "a", "body": "fine"},
        {"messageId": "b", "body": "boom"},
        {"messageId": "c", "body": "fine"},
    ]}, None)

    assert answer["batchItemFailures"] == [{"itemIdentifier": "b"}]


def test_the_worker_drops_a_rejected_message_rather_than_redriving_it(monkeypatch):
    """**A rejection is not a failure**, and reporting it as one fills the
    dead-letter queue with something nobody can act on: a bad signature will fail
    identically forever."""
    from studio_core.handlers.aws.worker import worker_handler

    def handle(_body):
        raise callbacks.Rejected("the signature does not match")

    monkeypatch.setattr(callbacks, "handle", handle)

    answer = worker_handler.handler({"Records": [{"messageId": "a", "body": "{}"}]}, None)

    assert answer["batchItemFailures"] == []


class _Sqs:
    """Just enough SQS for one drain: hand out messages once, record deletes."""

    def __init__(self, messages):
        self.messages = messages
        self.deleted = []

    def receive_message(self, **_kw):
        found, self.messages = self.messages, []
        return {"Messages": found}

    def delete_message(self, *, QueueUrl, ReceiptHandle):
        self.deleted.append(ReceiptHandle)


def test_the_local_consumer_deletes_what_it_handled_and_keeps_what_failed(monkeypatch):
    """**A failure stays on the queue on purpose.**

    The visibility timeout brings it back, so a developer who has just fixed the
    bug in their tree gets the same callback delivered into the fix — which is
    the whole reason the processing half is not deployed.
    """
    import logging

    from studio_core.handlers.local.consumer import poll

    def handle(body):
        if "boom" in body:
            raise RuntimeError("not yet")
        return {"id": "run-x", "status": "succeeded"}

    sqs = _Sqs([
        {"Body": "fine", "ReceiptHandle": "r1"},
        {"Body": "boom", "ReceiptHandle": "r2"},
    ])

    # `poll.drain` rather than `callback_consumer.drain`: the loop is shared with
    # the render consumer now, and this is where it lives.
    handled = poll.drain(sqs, "https://sqs.test/q", batch=10, handle=handle,
                         droppable=callbacks.Rejected,
                         log=logging.getLogger("test"))
    assert handled == 2
    assert sqs.deleted == ["r1"]


def test_the_local_consumer_deletes_a_rejected_message(monkeypatch):
    """Same rule as the worker's: it will never succeed, so it goes."""
    import logging

    from studio_core.handlers.local.consumer import poll

    def handle(_body):
        raise callbacks.Rejected("forged")

    sqs = _Sqs([{"Body": "{}", "ReceiptHandle": "r1"}])

    poll.drain(sqs, "https://sqs.test/q", batch=10, handle=handle,
               droppable=callbacks.Rejected, log=logging.getLogger("test"))

    assert sqs.deleted == ["r1"]


def test_the_local_consumer_says_so_when_no_queue_is_configured(monkeypatch):
    """A machine whose stack predates the callback path. Everything else about
    local development still works, so this reports and exits rather than
    crash-looping beside a working API."""
    from studio_core.handlers.local.consumer import callback_consumer

    monkeypatch.delenv("STUDIO_CALLBACK_QUEUE_URL", raising=False)
    assert callback_consumer.main() == 0
