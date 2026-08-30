"""Runtime configuration helpers.

Tiny env-driven accessors used across handlers, clients and services. Kept pure
(no AWS, no I/O) so it can be imported anywhere, including under tests.
"""

import os


def media_bucket():
    """The S3 bucket the browser reads.

    Declared by studio's own Terraform (`infra/modules/media`) and passed in as
    an environment variable by the deploy workflow. The default matches prod so
    local dev needs no extra configuration.

    Renamed from `xharness-prod-media-us-east-1` in August 2026, which is why
    the default here changed. S3 has no rename, so it was done as a second
    bucket and a verified copy; the old bucket was then deleted. See
    `infra/README.md`.
    """
    return os.environ.get("STUDIO_MEDIA_BUCKET", "studio-prod-media-us-east-1")


def catalog_table():
    """The DynamoDB table that holds the library.

    Every node's identity, name, parent and owner is a row in it; the bucket
    above holds bytes and is never listed to find out what exists. Declared by
    studio's own Terraform and passed in as an environment variable by the
    deploy workflow, exactly like the bucket — and the default matches prod for
    the same reason, because studio has one environment and local development
    points at it.

    **Every listing reads it as of #309.** It used to be inert — listings came
    from S3 and an unset variable was harmless — and it is now the difference
    between a browsable library and an empty one.
    """
    return os.environ.get("STUDIO_CATALOG_TABLE", "studio-prod-catalog")


def media_root_prefix():
    """The prefix inside the bucket this service may read.

    Every key and prefix the API accepts is validated against this, so it is the
    one place the browsable surface is defined.

    **Empty means the whole bucket, and that is what prod runs.** The pipeline used
    to wrap everything in `media/`; it now writes `characters/`, `projects/` and
    `phrasebook/` at the top level, so there is no longer a wrapper to confine
    browsing to. The knob stays because the confinement it drives is real — set
    it to `some/prefix/` and both this API and the Lambda's IAM policy narrow to
    it — but a value of `""` (or `"/"`, which as an S3 prefix would match
    nothing) means the root. Anything else is returned slash-terminated because
    two comparisons expect it that way: `keys.clean_key`'s root check, and the
    prefix the Lambda's IAM policy is scoped to. Nothing lists any more (#316,
    #317), so the termination stopped being about an argument to `ListObjectsV2`
    and is about those two.
    """
    value = os.environ.get("STUDIO_MEDIA_ROOT_PREFIX", "").strip()
    if value in ("", "/"):
        return ""
    return value if value.endswith("/") else value + "/"


def presign_ttl_seconds():
    """How long a presigned URL is requested for.

    Deliberately short. A URL signed with the Lambda role's temporary
    credentials dies when *those* expire regardless of what we ask for here, so
    a long TTL would only be a lie the frontend then has to discover. The
    frontend re-signs through `/api/asset` when a URL stops working.
    """
    return int(os.environ.get("STUDIO_PRESIGN_TTL_SECONDS", "900"))


def max_text_bytes():
    """Size cap for the read-only text/JSON viewer endpoint."""
    return int(os.environ.get("STUDIO_MAX_TEXT_BYTES", str(1024 * 1024)))


def max_upload_bytes():
    """The largest body an upload may declare — 5 GiB, S3's single-PUT ceiling.

    Not a policy number: it is the point past which a single `PutObject` is
    impossible and multipart would be required, and there is deliberately no
    multipart grant. Declaring it at signing time means an oversized upload is
    refused by the signature rather than discovered after the bytes have moved.
    """
    return int(os.environ.get("STUDIO_MAX_UPLOAD_BYTES", str(5 * 1024**3)))


def upload_ttl_seconds():
    """How long an upload URL is signed for. Shorter than a read URL.

    A read URL is handed out by the dozen while a person browses; an upload URL
    is handed out once, immediately before a client that already has the bytes
    sends them. There is no reason for it to outlive that, and every reason for
    a grant that *writes* to be the shortest-lived thing this service issues.
    """
    return int(os.environ.get("STUDIO_UPLOAD_TTL_SECONDS", "300"))


def max_bulk_keys():
    """How many objects one delete request may name.

    1000 because `DeleteObjects` took 1000 keys per call, so a bulk delete was
    one round trip. It is not one any more — against the catalog it is a
    transaction per node with the blobs going in a single call at the end — so
    the number bounds a per-node cost it was never chosen for. `manage._bulk`
    states that arithmetic where the cap is enforced; what the number should be
    is #431, open and undecided, and not a thing to settle in passing here.

    A larger selection is refused rather than silently split: a partially applied
    bulk delete is the worst possible outcome to report back to a UI.
    """
    return int(os.environ.get("STUDIO_MAX_BULK_KEYS", "1000"))


def max_folder_objects():
    """How many nodes one subtree operation will touch, and now also the reel's.

    A folder delete or a subtree move is a transaction per node and the Lambda
    has a wall clock, so this guards a request that would time out halfway
    through and leave the tree in two places at once. For those it is a
    **refusal** — half a move reported as a whole one is the outcome there is no
    recovering from. (A folder *rename* was a `CopyObject` per key once and is
    not bounded by this at all since #316: it rewrites one row and nothing
    beneath it moves.)

    The reel reads the same number and **truncates** instead, saying so in
    `truncated`: a page of a library is allowed to be shorter than the library.
    That is what retires `STUDIO_MAX_WALK_OBJECTS` (20,000), which bounded a walk
    over S3 *objects* — the reel enumerates rows now (#310), so there is one
    number for how much of a subtree this service will hold in memory rather than
    two that had drifted an order of magnitude apart.
    """
    return int(os.environ.get("STUDIO_MAX_FOLDER_OBJECTS", "2000"))


def replicate_token_parameter():
    """The SSM parameter holding the Replicate API token, or `""` for none.

    A **name**, not a value: the parameter is a SecureString and this service
    reads it at call time so the secret never sits in the function's environment,
    where `lambda:GetFunctionConfiguration` would hand it to anyone who can list
    the account. Set by the deploy workflow from the compute module's output.
    """
    return os.environ.get("STUDIO_REPLICATE_TOKEN_PARAMETER", "").strip()


def replicate_token_env():
    """The Replicate token straight from the environment, or `""`.

    **This is how local development and the test suite work**, and it is checked
    before the parameter above. `dev-up.sh` runs this API as an ordinary process
    under a developer's own AWS key, and the token is already in
    `~/.config/andreas-services/studio/dev.env` — so requiring SSM locally would
    mean provisioning a per-machine parameter for a value that is not
    environment-scoped in the first place.

    In prod it is unset. That asymmetry is the point: the deployed function reads
    a SecureString, and nothing in the deploy workflow ever holds the plaintext.
    """
    return os.environ.get("REPLICATE_API_TOKEN", "").strip()


def webhook_base_url():
    """Where Replicate should call back, or `""` when nothing can reach us.

    **Not this API's own origin.** It is the receiver's — a small zip Lambda
    behind its own API Gateway route, which enqueues the callback and answers in
    milliseconds. In prod the two happen to sit on the same gateway; on a
    developer's machine they are nothing alike, because the API is Flask on
    `localhost:8000` and the receiver is a per-machine `execute-api` URL in AWS.
    That asymmetry is the point of the split: a laptop cannot receive a webhook,
    and it can drain a queue.

    **`""` is a supported configuration rather than a misconfiguration.** A
    machine with no dev stack provisioned, and CI, both run with it unset: the
    prediction is created with no webhook at all and the run is closed by
    `POST /api/runs/<id>/reconcile` instead. `services.generate` reports which of
    the two a submission got, in the `callback` field of its response.
    """
    return os.environ.get("STUDIO_WEBHOOK_BASE_URL", "").strip().rstrip("/")


def callback_queue_url():
    """The SQS queue a received callback is enqueued onto, or `""`.

    Read by the local consumer (`handlers/local/consumer`) and by nothing else
    in this process: the receiver Lambda reads its own environment directly
    because it imports none of this, and the prod worker is driven by an event
    source mapping rather than by a poll.
    """
    return os.environ.get("STUDIO_CALLBACK_QUEUE_URL", "").strip()


def webhook_tolerance_seconds():
    """How far out of date a webhook's timestamp may be before it is refused.

    Bounds replay: a captured callback re-sent after this window fails
    verification even though its signature is still valid for its own body. Five
    minutes is the value Replicate's own documentation uses, and it has to
    absorb real clock skew between their sender and this Lambda — too tight and
    a legitimate callback is dropped, which loses an output somebody paid for.
    """
    return int(os.environ.get("STUDIO_WEBHOOK_TOLERANCE_SECONDS", "300"))


def max_output_bytes():
    """The largest model output this service will pull into the bucket.

    The same 5 GiB ceiling `max_upload_bytes` names, and for the same reason: it
    is the point past which a single `PutObject` is impossible. The callback
    streams the download to disk and then sends it in one PUT, so the object's
    ETag stays the MD5 of its bytes and `s3.content_hash` keeps working — a
    multipart upload would produce a hash-of-hashes and every output would lose
    the checksum #535 added.
    """
    return int(os.environ.get("STUDIO_MAX_OUTPUT_BYTES", str(5 * 1024**3)))


def cognito_user_pool_id():
    """The pool whose issuer and signing keys a caller's token is checked against.

    Deliberately without a default, unlike the bucket: there is no value that is
    harmlessly wrong here. A pool id that does not match the token's rejects
    every caller, and one naming a *different* pool would admit that pool's
    users. Unset is a misconfiguration for `services.identity` to report rather
    than something to guess at. Set by the deploy workflow from the auth module's
    output, and by `dev-up.sh` locally.
    """
    return os.environ.get("STUDIO_COGNITO_USER_POOL_ID", "")


def cognito_client_id():
    """The app client an ID token must be addressed to — its `aud` claim.

    One pool can host several clients and only this one is the studio SPA, so
    checking it is what stops a token minted for some other client of the same
    pool from working here. Public by construction — it ships in the frontend
    bundle — so it is an identifier, never a secret. No default, for the reason
    above.
    """
    return os.environ.get("STUDIO_COGNITO_CLIENT_ID", "")


def allowed_origin():
    """Value for Access-Control-Allow-Origin. Defaults to the prod app origin."""
    return os.environ.get("STUDIO_ALLOWED_ORIGIN", "https://studio.andreas.services")


def aws_region():
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def render_queue_url():
    """The SQS queue a render job is enqueued onto, or `""`.

    **Empty is not a misconfiguration in every environment**, which is why it has
    no default and no refusal here: prod sets it, a per-machine dev stack sets it
    (the queue is cheap — it is the *worker* dev declines), and CI leaves it
    unset because nothing there enqueues. `services.render.enqueue` is what
    refuses, at the moment a caller actually asks for work, with a message
    naming this variable — the same shape `webhook_base_url` uses.
    """
    return os.environ.get("STUDIO_RENDER_QUEUE_URL", "").strip()


def max_render_inputs():
    """How many nodes one render job may name.

    A bound on the thing that decides a job's disk and wall clock. It is not the
    real constraint — `media/workspace.reserve` measures bytes, which is what
    actually runs out — but a request naming ten thousand nodes should be
    refused at the route rather than after ten thousand catalog reads.

    Fifty is far above any real cut: the longest scene in the library is a
    handful of shots, and a contact sheet of a character pool is tens of images.
    """
    return int(os.environ.get("STUDIO_MAX_RENDER_INPUTS", "50"))


def max_image_bytes():
    """The largest image `routes/images.py` will pull into the API Lambda's heap.

    **This one is about memory, not about policy.** `convert` and `crop` are
    answered synchronously in the API image, which runs at 512 MB, and Pillow
    decodes to raw pixels: a 32 MB JPEG is a few hundred megabytes decoded and a
    deliberately crafted one is far worse. Pillow's own `MAX_IMAGE_PIXELS` guard
    (~89 megapixels) catches the decompression bomb; this catches the ordinary
    case of somebody pointing `crop` at a video.

    Anything larger belongs on the render queue, where there is a real disk and
    minutes of wall clock — which is the same reason the sheet job is there.
    """
    return int(os.environ.get("STUDIO_MAX_IMAGE_BYTES", str(32 * 1024 * 1024)))
