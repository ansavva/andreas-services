"""Runtime configuration helpers.

Tiny env-driven accessors used across handlers, clients and services. Kept pure
(no AWS, no I/O) so it can be imported anywhere, including under tests.
"""

import os


def media_bucket():
    """The S3 bucket the browser reads.

    Owned by the x-harness pipeline, not by this service — Terraform passes the
    name in but never manages the bucket itself. The default matches prod so
    local dev needs no extra configuration.
    """
    return os.environ.get("STUDIO_MEDIA_BUCKET", "xharness-prod-media-us-east-1")


def media_root_prefix():
    """The prefix inside the bucket this service may read.

    Every key and prefix the API accepts is validated against this, so it is the
    one place the browsable surface is defined.

    **Empty means the whole bucket, and that is what prod runs.** x-harness used
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


def projects_prefix():
    """Where the per-subject project trees live, relative to the media root.

    **The only place in this service that names a folder x-harness owns**, and it
    is here rather than inline because favourites are a *project* idea:
    `projects/mr-p/favorites/` holds the picks from `projects/mr-p/`, while
    `characters/mr-p/` has no such thing — that tree holds who the subject is
    rather than what was generated of them, and there is nothing there to pick
    between.

    Empty turns favourites off entirely rather than making every top-level folder
    a project. If x-harness reshapes the bucket again, a missing button is a much
    better failure than a copy landing somewhere invented — which is the same
    argument `media_root_prefix` makes and the reason both are knobs.
    """
    value = os.environ.get("STUDIO_PROJECTS_PREFIX", "projects").strip().strip("/")
    return f"{value}/" if value else ""


def favorites_folder():
    """The folder inside a project that holds its picks. Empty turns them off."""
    return os.environ.get("STUDIO_FAVORITES_FOLDER", "favorites").strip().strip("/")


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


def max_bulk_keys():
    """How many objects one delete request may name.

    `DeleteObjects` takes 1000 keys per call, so this is one round trip. A
    larger selection is refused rather than silently split: a partially applied
    bulk delete is the worst possible outcome to report back to a UI.
    """
    return int(os.environ.get("STUDIO_MAX_BULK_KEYS", "1000"))


def max_folder_objects():
    """How many objects a folder rename or delete will touch before refusing.

    A folder rename is a CopyObject per key and the Lambda has a wall clock, so
    this is a guard against a request that would time out halfway through and
    leave the tree in two places at once.
    """
    return int(os.environ.get("STUDIO_MAX_FOLDER_OBJECTS", "2000"))


def max_walk_objects():
    """How many objects the recursive reel walk will enumerate.

    Sorting by date means the whole prefix has to be listed before any page can
    be cut from it, so the walk is bounded and reports when it stopped early
    rather than pretending the tail does not exist.
    """
    return int(os.environ.get("STUDIO_MAX_WALK_OBJECTS", "20000"))


def allowed_origin():
    """Value for Access-Control-Allow-Origin. Defaults to the prod app origin."""
    return os.environ.get("STUDIO_ALLOWED_ORIGIN", "https://studio.andreas.services")


def aws_region():
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
