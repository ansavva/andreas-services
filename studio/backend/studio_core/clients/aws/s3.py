"""Thin boto3 wrapper over the media bucket.

**This module can write, and that is a recent and deliberate change.** Studio was
built as a reader of a bucket a separate pipeline owned, and for most of its
life the Lambda role carried `ListBucket` and `GetObject` and nothing else. It
now also carries `PutObject` and `DeleteObject`, because studio is where the
library actually gets tidied — a run that produced nothing worth keeping is
noticed in the browser, not in the pipeline.

**Nothing here lists any more.** `list_folder`, `walk_all`, `exists`,
`prefix_exists` and `put_folder_marker` went with #316 and #317: a folder is a
row, a name is unique because a condition expression says so, and "what is in
this folder" is a query on the catalog. That is the point of the milestone
rather than a side effect — the listing was the expensive half of every write,
and the zero-byte marker existed only to make an empty folder visible to one.

What is left is bytes, and four things bound them:

* **A key reaching `CopyObject`, `PutObject` or `DeleteObject` comes off a node
  record**, never off a request. `services.manage` resolves a name path to a node
  and passes that node's `blob_key`; nothing outside `services.catalog` composes
  one. That is what replaced `services.keys` as the line between a query string
  and `GetObject`.
* **`copy` and `put_text` cannot bring an object in from outside.** A copy's
  source is already in this bucket, and `put_text` overwrites a file the caller
  has already proved is a text node with bytes behind it.
* **`presign_put` is the one exception, and it is bounded at signing time** —
  one key, one exact length, one content type, once. See its docstring.
* Deletes are explicit and bounded (`config.max_bulk_keys`,
  `config.max_folder_objects`); nothing in this service deletes by wildcard.

`put_text` is the one that reads like an upload and is not. It exists because
the `.md`, `.yaml` and `.json` files in this bucket are notes and prompts a
person writes, and reading one in the browser and then going elsewhere to fix a
typo in it is the kind of friction that means it never gets fixed. It is
confined to `keys.TEXT_EXTENSIONS`, capped at `config.max_text_bytes`, and
refuses a node with no blob.
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


def copy(source_key: str, dest_key: str) -> None:
    """Server-side copy within the media bucket. The whole of a copy.

    **It used to be the first half of a rename**, and of a move, and of a folder
    rename — one call per key, followed by a delete. Those are transactions now
    (#316), so the one caller left is `services.manage.copy_objects`, which is
    the only operation in the service that is *supposed* to duplicate bytes. Each
    copy gets its own object rather than a second row on one key: `delete_node`
    does not ask whether a blob is still referenced, so a shared key would mean
    deleting one copy destroys the other's. Copy-on-write is #334.

    Server-side, so a 200 MB video never travels through the Lambda.
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


def put_text(key: str, body: bytes, content_type: str) -> None:
    """Overwrite a text object with new contents.

    The only write in this module that carries a caller-supplied body, and the
    caller is `services.manage.update_text`, which has already established that
    the node is a text file carrying a blob, small enough to hold in memory. S3 has
    no partial write and no conditional put, so this is a whole-object replace —
    the previous contents are gone unless the bucket is versioned, which is one
    more reason to turn versioning on.
    """
    try:
        client().put_object(
            Bucket=config.media_bucket(), Key=key, Body=body, ContentType=content_type
        )
    except ClientError as exc:
        logger.warning("PutObject failed for %s: %s", key, exc)
        raise UpstreamError("Could not save the file") from exc


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


def presign_put(key: str, *, content_length: int, content_type: str) -> str:
    """A presigned PUT for exactly one key, length and content type.

    **This is the only path by which bytes from outside the bucket can enter
    it**, and every argument here is a bound on that.

    `content-length` and `content-type` are in `X-Amz-SignedHeaders` — verified
    against botocore rather than assumed — so a client that sends a different
    length or a different type fails signature validation at S3 and writes
    nothing. That is stronger than a POST policy's `content-length-range`: the
    length is not merely bounded, it is fixed at signing time.

    The key is likewise signed, so a URL issued for one object cannot be
    redirected at another. There is no wildcard and no multipart grant; the
    caller gets one object, one size, one type, once.

    Local signing, no network call — the same as `presign`.
    """
    try:
        return client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": config.media_bucket(),
                "Key": key,
                "ContentLength": content_length,
                "ContentType": content_type,
            },
            ExpiresIn=config.upload_ttl_seconds(),
        )
    except ClientError as exc:
        logger.warning("Presign PUT failed for %s: %s", key, exc)
        raise UpstreamError("Could not sign an upload URL") from exc


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


def content_hash(metadata: dict) -> str | None:
    """The MD5 of an object's bytes, off whatever S3 just told us about it.

    **An ETag is the content MD5 only for a single-part upload**, and every
    upload this API signs is one: `max_upload_bytes` is S3's own single-PUT
    ceiling and there is no multipart grant. A multipart ETag is a hash of the
    part hashes with a `-N` suffix, which would compare unequal for two identical
    files uploaded with different part sizes — so the suffix is treated as "no
    usable hash" rather than stored as a lie.
    """
    raw = (metadata or {}).get("ETag") or ""
    cleaned = raw.strip('"')
    return None if not cleaned or "-" in cleaned else cleaned
