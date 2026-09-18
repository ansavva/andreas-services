"""The provider's callback lands here, and this file does one thing: enqueue it.

**It imports nothing from `studio_core` and that is the entire design.** Every
other handler in this tree runs the Docker image the API is built from; this one
is packaged by Terraform as a plain zip from this single file, straight out of
the repo, with no ECR repository and no build step. That is what makes it cheap
enough to exist in the **per-machine dev environment** as well as in prod —
`infra/envs/dev` declines to declare a Lambda, an API Gateway or an ECR
repository, and it would have gone on declining if the callback needed a
container.

## Why the callback is received here and processed somewhere else

Replicate cannot reach `http://localhost:8000`, so a developer running the API
under `dev-up.sh` had no way to exercise a webhook at all. The first answer was
to close the run inline in the API Lambda and let local development fall back to
polling — which worked, and meant the webhook code path never ran locally, so it
first ran for real in production.

Splitting receive from process fixes that, and pays for itself three more times:

* **The callback is acknowledged in milliseconds.** Downloading a 200 MB clip
  inside the webhook request holds an HTTP connection open for the length of the
  transfer, against a sender with its own timeout.
* **A failed upload retries.** An exception while storing an output used to lose
  a file somebody had already paid for. It is a queue redrive now, and then a
  dead-letter queue somebody can read.
* **The three functions size independently.** This one is 256 MB and seconds;
  the worker that downloads video is 2 GB with a real ephemeral disk; the API
  Lambda is untouched at 512 MB.

**In dev the consumer is a process on the laptop**, long-polling this machine's
own queue and closing the run with the working tree — so the code being edited is
the code that runs. In prod it is a Lambda on an event source mapping. One
implementation either way: `services/callbacks.py`.

## Four providers, one route

The route is `POST /api/hooks/{provider}/{run_id}` and this file forwards the
provider's name and, for Runpod and OpenRouter, the `sig` query parameter its
callback URL was minted with — `services/generate.callback_url` says why their
proof is in the URL and Replicate's and fal's are in the headers. None is
checked here; all are checked by the consumer.

## This handler does NOT verify the signature, deliberately

Verification has to be byte-exact over the raw body — Replicate signs
`<id>.<timestamp>.<body>` — so this base64s the bytes that arrived rather than
re-serialising anything, and the consumer checks them. Two reasons that is the
right side of the wire:

* **One implementation, in the code that actually runs.** The check lives in
  `clients/replicate.py` and is executed by the local consumer and by the worker
  alike. A copy here would be a second implementation, in the one file that is
  deployed without being built or tested with the rest.
* **This file must stay dependency-free.** An HMAC over a secret fetched from
  Replicate means an HTTP client and a credential in a Lambda whose whole point
  is that it needs neither.

What that costs is an unauthenticated endpoint anyone can push a message into.
It is bounded rather than ignored: API Gateway throttles the route, the body is
size-capped below, and a forged message costs exactly one consumer invocation
that refuses it and deletes it. Nothing downstream acts on an unverified body.
"""

import base64
import json
import os

import boto3

#: Headers the consumer needs and the only ones carried through. An allowlist,
#: not the whole map: everything here is written into a queue message that will
#: be read by a laptop, and API Gateway forwards a great deal that has no
#: business being copied — cookies, forwarded IPs, the gateway's own tracing.
SIGNATURE_HEADERS = (
    # Replicate, Standard Webhooks
    "webhook-id", "webhook-timestamp", "webhook-signature",
    # fal — `clients/fal.py` repeats these; that module is not importable here
    "x-fal-webhook-request-id", "x-fal-webhook-user-id",
    "x-fal-webhook-timestamp", "x-fal-webhook-signature",
)

#: The providers a callback may claim to be from. A literal here rather than an
#: import from `services/registry.py`, because this file imports nothing from
#: `studio_core` — see the module docstring — and the consumer re-checks it.
PROVIDERS = ("replicate", "runpod", "fal", "openrouter", "runpod-pod")

#: SQS refuses a message body over 256 KiB, and a callback is a JSON envelope
#: with metrics and logs in it — a failed video's `logs` can be large. The cap is
#: below the SQS limit so the refusal happens here, where it can be logged
#: against a run id, rather than as a `SendMessage` failure with no context.
MAX_BODY_BYTES = 192 * 1024

_sqs = None


def _client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


def handler(event, _context):
    """Enqueue the callback verbatim and answer 200.

    **Always 200 on a message that was queued**, whatever it contains. The sender
    is Replicate, retrying is its only response to anything else, and a retry
    delivers the identical body — so a 4xx here would turn one unreadable
    callback into several. Everything this can actually refuse is refused before
    the queue: a path with no run id, and a body too large to hold.
    """
    parameters = event.get("pathParameters") or {}
    path = parameters.get("run_id") or ""
    if not path.startswith("run-"):
        # Not a run id. Nothing downstream could act on this and nothing should
        # be queued for it.
        return {"statusCode": 404, "body": json.dumps({"error": "no such run"})}
    provider = parameters.get("provider") or ""
    if provider not in PROVIDERS:
        return {"statusCode": 404, "body": json.dumps({"error": "no such provider"})}

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(body)
    else:
        raw = body.encode()

    if len(raw) > MAX_BODY_BYTES:
        print(f"callback for {path} is {len(raw)} bytes; refusing to queue it")
        return {"statusCode": 413, "body": json.dumps({"error": "callback too large"})}

    headers = {
        name: value
        for name, value in (event.get("headers") or {}).items()
        if name.lower() in SIGNATURE_HEADERS
    }

    _client().send_message(
        QueueUrl=os.environ["STUDIO_CALLBACK_QUEUE_URL"],
        MessageBody=json.dumps({
            "run": path,
            "provider": provider,
            # Runpod's and OpenRouter's proof travels in the URL rather than a
            # header. Forwarded as-is; the consumer is what recomputes it.
            "sig": (event.get("queryStringParameters") or {}).get("sig") or "",
            "headers": {name.lower(): value for name, value in headers.items()},
            # Base64 because the signature is over these exact bytes and a JSON
            # round trip of the decoded string is not guaranteed to reproduce
            # them — key order and whitespace are exactly what an HMAC notices.
            "body_b64": base64.b64encode(raw).decode(),
        }),
    )
    print(f"queued a callback for {path} ({len(raw)} bytes)")
    # **200, not 202.** Replicate takes any 2xx; Runpod's documentation says
    # `200` and, measured on 2026-09-14, it re-delivered a callback answered
    # 202 five seconds later. The consumer is idempotent so the repeat cost one
    # invocation and nothing else — but it was ours to cause.
    return {"statusCode": 200, "body": json.dumps({"queued": True})}
