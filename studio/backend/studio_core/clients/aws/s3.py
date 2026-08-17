"""Thin boto3 wrapper over the media bucket.

**This module can write, and that is a recent and deliberate change.** Studio was
built as a reader of a bucket the x-harness pipeline owns, and for most of its
life the Lambda role carried `ListBucket` and `GetObject` and nothing else. It
now also carries `PutObject` and `DeleteObject` on `media/*`, because studio is
where the library actually gets tidied — a run that produced nothing worth
keeping is noticed in the browser, not in the pipeline.

Three things keep that from being a licence to do anything:

* Every key still goes through `services.keys`, so nothing outside `media/` is
  reachable whatever the caller sends.
* There is no multipart upload and no `put_object` with a caller-supplied body.
  The only `PutObject` here writes a zero-byte folder marker, and the only other
  write is `CopyObject` within the same bucket — which is what a rename is.
* Deletes are explicit and bounded (`config.max_bulk_keys`,
  `config.max_folder_objects`); nothing in this service deletes by wildcard.

Data that matters is still the pipeline's to produce. Adding an upload path here
would be the change that makes studio a writer in the real sense, and it should
be argued for on its own rather than arriving as a side effect of this one.
"""

import logging

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from studio_core import config
from studio_core.errors import NotFoundError, UpstreamError

logger = logging.getLogger(__name__)

_client = None


def client():
    """Lazily built, module-cached S3 client.

    SigV4 is pinned explicitly because presigned URLs for a bucket in a region
    the client guessed wrong come back signed but unusable, and the failure only
    shows up in the browser as an opaque 403.
    """
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            region_name=config.aws_region(),
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
    return _client


def reset_client():
    """Drop the cached client. Tests use this between moto mocks."""
    global _client
    _client = None


def list_folder(prefix: str) -> tuple[list[str], list[dict]]:
    """One delimited listing: immediate subfolders and immediate objects."""
    folders: list[str] = []
    objects: list[dict] = []
    paginator = client().get_paginator("list_objects_v2")

    try:
        for page in paginator.paginate(
            Bucket=config.media_bucket(), Prefix=prefix, Delimiter="/"
        ):
            folders.extend(cp["Prefix"] for cp in page.get("CommonPrefixes", []))
            objects.extend(page.get("Contents", []))
    except ClientError as exc:
        logger.warning("ListObjectsV2 failed for %s: %s", prefix, exc)
        raise UpstreamError("Could not list the media bucket") from exc

    return folders, objects


def walk_all(prefix: str, limit: int) -> tuple[list[dict], bool]:
    """Every object beneath a prefix, up to `limit`.

    Returns the objects and whether the listing was cut short. Used wherever a
    whole subtree has to be known before anything can be decided about it —
    sorting the reel by date, and counting a folder before renaming or deleting
    it — none of which can be answered from one page.
    """
    objects: list[dict] = []
    truncated = False
    paginator = client().get_paginator("list_objects_v2")

    try:
        for page in paginator.paginate(Bucket=config.media_bucket(), Prefix=prefix):
            for obj in page.get("Contents", []):
                if len(objects) >= limit:
                    return objects, True
                objects.append(obj)
    except ClientError as exc:
        logger.warning("ListObjectsV2 walk_all failed for %s: %s", prefix, exc)
        raise UpstreamError("Could not list the media bucket") from exc

    return objects, truncated


def exists(key: str) -> bool:
    """Whether one object is there. The pre-check every rename and create makes."""
    try:
        client().head_object(Bucket=config.media_bucket(), Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        logger.warning("HeadObject failed for %s: %s", key, exc)
        raise UpstreamError("Could not read the object") from exc


def prefix_exists(prefix: str) -> bool:
    """Whether anything at all lives under a prefix.

    A folder is not a thing in S3, so "does this folder exist" can only be asked
    as "is there a key that starts with it". One key is enough to answer it.
    """
    try:
        response = client().list_objects_v2(
            Bucket=config.media_bucket(), Prefix=prefix, MaxKeys=1
        )
    except ClientError as exc:
        logger.warning("ListObjectsV2 failed for %s: %s", prefix, exc)
        raise UpstreamError("Could not list the media bucket") from exc

    return response.get("KeyCount", 0) > 0


def copy(source_key: str, dest_key: str) -> None:
    """Server-side copy within the media bucket. The first half of a rename.

    Server-side, so a 200 MB video never travels through the Lambda — which is
    what makes renaming a run folder of finished output affordable at all.
    """
    try:
        client().copy_object(
            Bucket=config.media_bucket(),
            Key=dest_key,
            CopySource={"Bucket": config.media_bucket(), "Key": source_key},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NoSuchKeyError"):
            raise NotFoundError(source_key) from exc
        logger.warning("CopyObject %s -> %s failed: %s", source_key, dest_key, exc)
        raise UpstreamError("Could not copy the object") from exc


def delete(keys: list[str]) -> None:
    """Delete objects, in batches of the 1000 `DeleteObjects` accepts.

    S3 reports per-key failures in the response body rather than by raising, so
    the errors it returns are read and turned into one — a delete that silently
    left half its keys behind is exactly the outcome a UI cannot recover from.
    """
    if not keys:
        return

    for start in range(0, len(keys), 1000):
        batch = keys[start : start + 1000]
        try:
            response = client().delete_objects(
                Bucket=config.media_bucket(),
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )
        except ClientError as exc:
            logger.warning("DeleteObjects failed (%d keys): %s", len(batch), exc)
            raise UpstreamError("Could not delete the objects") from exc

        failures = response.get("Errors", [])
        if failures:
            logger.warning("DeleteObjects reported %d failures: %s", len(failures), failures[:5])
            raise UpstreamError(
                f"Could not delete {len(failures)} of {len(batch)} objects"
            )


def put_folder_marker(prefix: str) -> None:
    """Write the zero-byte object that makes an empty folder visible.

    The console's own convention, and the only way a new folder can exist before
    anything is in it — S3 has no directories to create. `services.browse`
    filters these back out of every listing, so the marker is never a file.
    """
    try:
        client().put_object(Bucket=config.media_bucket(), Key=prefix, Body=b"")
    except ClientError as exc:
        logger.warning("PutObject failed for %s: %s", prefix, exc)
        raise UpstreamError("Could not create the folder") from exc


def presign(key: str, *, disposition: str = "inline", filename: str | None = None) -> str:
    """A presigned GET URL for one object.

    Purely local signing — no network call — so presigning every file in a
    listing costs nothing.

    `disposition="attachment"` is what makes a download actually download: the
    URL points at S3, so it is cross-origin to the app, and a cross-origin
    `<a download>` is ignored by browsers. Signing `response-content-disposition`
    into the URL is the only thing that works.
    """
    params = {"Bucket": config.media_bucket(), "Key": key}
    if disposition == "attachment":
        name = (filename or key.rsplit("/", 1)[-1]).replace('"', "")
        params["ResponseContentDisposition"] = f'attachment; filename="{name}"'

    try:
        return client().generate_presigned_url(
            "get_object", Params=params, ExpiresIn=config.presign_ttl_seconds()
        )
    except ClientError as exc:
        logger.warning("Presign failed for %s: %s", key, exc)
        raise UpstreamError("Could not sign a media URL") from exc


def head(key: str) -> dict:
    try:
        return client().head_object(Bucket=config.media_bucket(), Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            raise NotFoundError(key) from exc
        logger.warning("HeadObject failed for %s: %s", key, exc)
        raise UpstreamError("Could not read the object") from exc


def get_body(key: str, max_bytes: int) -> bytes:
    """Fetch an object's bytes, reading at most `max_bytes` of them."""
    try:
        response = client().get_object(Bucket=config.media_bucket(), Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            raise NotFoundError(key) from exc
        logger.warning("GetObject failed for %s: %s", key, exc)
        raise UpstreamError("Could not read the object") from exc

    return response["Body"].read(max_bytes)
