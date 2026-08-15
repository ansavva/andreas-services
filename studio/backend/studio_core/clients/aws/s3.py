"""Thin boto3 wrapper over the media bucket. Read operations only.

Nothing in this module can write: there is no `put_object`, no `delete_object`
and no multipart call, which mirrors the IAM policy Terraform attaches to the
Lambda role. The bucket belongs to the x-harness pipeline and this service is
strictly a reader of it.
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


def walk(prefix: str, continuation_token: str | None, page_size: int):
    """One undelimited page of every object beneath a prefix.

    Undelimited so subfolders come back flattened — this is what reel mode walks.
    Returns the raw page plus the token for the next one.
    """
    kwargs = {
        "Bucket": config.media_bucket(),
        "Prefix": prefix,
        "MaxKeys": page_size,
    }
    if continuation_token:
        kwargs["ContinuationToken"] = continuation_token

    try:
        response = client().list_objects_v2(**kwargs)
    except ClientError as exc:
        logger.warning("ListObjectsV2 walk failed for %s: %s", prefix, exc)
        raise UpstreamError("Could not list the media bucket") from exc

    return response.get("Contents", []), response.get("NextContinuationToken")


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
