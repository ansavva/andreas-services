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
    nothing) means the root. Anything else is returned slash-terminated so it
    can be handed straight to `ListObjectsV2`.
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

    `DeleteObjects` takes 1000 keys per call, so this is one round trip. A
    larger selection is refused rather than silently split: a partially applied
    bulk delete is the worst possible outcome to report back to a UI.
    """
    return int(os.environ.get("STUDIO_MAX_BULK_KEYS", "1000"))


def max_folder_objects():
    """How many nodes one subtree operation will touch, and now also the reel's.

    A folder rename or delete is a CopyObject or a transaction per node and the
    Lambda has a wall clock, so this guards a request that would time out halfway
    through and leave the tree in two places at once. For those it is a
    **refusal** — half a move reported as a whole one is the outcome there is no
    recovering from.

    The reel reads the same number and **truncates** instead, saying so in
    `truncated`: a page of a library is allowed to be shorter than the library.
    That is what retires `STUDIO_MAX_WALK_OBJECTS` (20,000), which bounded a walk
    over S3 *objects* — the reel enumerates rows now (#310), so there is one
    number for how much of a subtree this service will hold in memory rather than
    two that had drifted an order of magnitude apart.
    """
    return int(os.environ.get("STUDIO_MAX_FOLDER_OBJECTS", "2000"))


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
