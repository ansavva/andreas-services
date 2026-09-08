"""A lesson's uploaded files, in S3.

A page is a DIRECTORY here, not a column in a table. The teacher uploads
whatever her authoring tool produced — ``index.html`` and the images,
stylesheets, fonts and scripts beside it — and CloudFront serves it back byte
for byte. Nothing here rewrites her markup and nothing sanitizes it.

## Two prefixes, and the difference between them IS publication

    draft/<page-id>/...    what she has uploaded. Never served.
    lesson/<page-id>/...   what students can open. Served, and only this.

Publishing copies the first onto the second; withdrawing deletes the second.
That is deliberate, and it is the only honest way to gate static hosting: there
is no request for the application to intercept, so an unpublished lesson must
not EXIST at a servable key. The CloudFront function in
``modules/lesson_hosting`` refuses anything outside ``/lesson/``, which is what
keeps ``draft/`` unreachable even though both live in one bucket.

## Why the browser uploads directly

The API signs a PUT and the teacher's browser sends the bytes straight to S3. A
zip of a worksheet with its images runs to tens of megabytes and API Gateway
stops at 10MB, so routing uploads through the Lambda would fail on exactly the
files she cares about most.
"""

import mimetypes
import os

import boto3
from botocore.config import Config

_client = None

# Enough for a worksheet with images and a video poster; small enough that one
# upload cannot quietly become a hosting bill.
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES_PER_LESSON = 200

# A presigned PUT is a bearer token in a URL. Fifteen minutes is long enough for
# a slow upload on a school connection and short enough that a leaked link in a
# browser history is not a standing write grant.
UPLOAD_URL_TTL_SECONDS = 15 * 60

# WHAT MAY NOT APPEAR IN A PATH, rather than what may.
#
# An allow-list was tried first and was wrong for the person this is built for:
# it refused `pie chart.png`, `Worksheet (final).html` and `Café/menu.png` —
# ordinary names a teacher gives a file, and names her HTML then references, so
# renaming them for her would break the lesson. S3 keys are UTF-8 and accept all
# of these happily.
#
# So only what genuinely breaks something is refused:
#
#   # ?      terminate a path in a URL, so the file could never be fetched
#   %        collides with percent-encoding between CloudFront and S3
#   \ : * " < > |   illegal or reserved on Windows, where her files came from
#   control characters, which have no business in a filename at all
_FORBIDDEN_CHARS = set('#?%\\:*"<>|') | {chr(c) for c in range(0x20)} | {chr(0x7F)}

INDEX_FILE = "index.html"


def bucket() -> str:
    name = os.environ.get("CLASSROOM_LESSONS_BUCKET", "")
    if not name:
        raise RuntimeError("CLASSROOM_LESSONS_BUCKET is not set")
    return name


def client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
            # SigV4 so presigned URLs are valid in every region, and the virtual
            # host style S3 now requires.
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
    return _client


def clean_path(raw: str) -> str:
    """Validate one uploaded file's relative path, or raise ``ValueError``.

    **This is the security boundary of the upload API.** The path arrives from
    the browser and becomes part of an S3 key that a presigned URL then grants
    write access to, so an unchecked one writes wherever the caller likes —
    including over another teacher's published lesson via ``../``.

    Rejects: absolute paths, any ``..`` segment, backslashes, leading dots,
    empty segments, and anything outside a conservative character set. Windows
    exports produce backslashes, so those are normalised before the check
    rather than after, and a path that still fails is refused rather than
    guessed at.
    """
    path = (raw or "").strip().replace("\\", "/")
    # Some browsers prefix a chosen folder's own name; a leading "./" is common
    # from zip tools. Neither changes where the file belongs.
    while path.startswith("./"):
        path = path[2:]

    if not path:
        raise ValueError("a file path is required")
    # **Refused, not stripped.** Quietly turning `/etc/passwd` into
    # `etc/passwd` would accept a path the caller plainly did not mean and put
    # the file somewhere the teacher never chose. Neither a zip entry nor a
    # browser folder upload produces a leading slash, so one means something is
    # wrong — a malformed archive, or someone probing.
    if path.startswith("/"):
        raise ValueError(f"path must be relative, not absolute: {path}")
    if len(path) > 400:
        raise ValueError(f"path is too long: {path[:60]}…")
    if ".." in path.split("/"):
        raise ValueError(f"path may not contain '..': {path}")
    segments = path.split("/")
    if any(segment == "" for segment in segments):
        raise ValueError(f"path has an empty folder name: {path}")

    bad = sorted({c for c in path if c in _FORBIDDEN_CHARS and c.isprintable()})
    if bad:
        raise ValueError(
            f"“{path}” contains {' and '.join(repr(c) for c in bad)}, which cannot be used in a "
            "web address. Rename the file (and any link to it) and upload again."
        )
    if any(c in _FORBIDDEN_CHARS for c in path):
        raise ValueError(f"path contains a control character: {path!r}")

    # A segment that is only dots, or that starts or ends with a space, is
    # either a traversal attempt or an artefact of a bad export — and both
    # resolve unpredictably once they are S3 keys.
    for segment in segments:
        if segment.strip(".") == "":
            raise ValueError(f"path has a dots-only folder or file name: {path}")
        if segment != segment.strip():
            raise ValueError(f"“{path}” has a name padded with spaces. Rename it and try again.")
    return path


def content_type_for(path: str) -> str:
    """The type CloudFront will serve the object as.

    Set at PUT time because S3 stores whatever it is told and serves it back
    verbatim: an ``index.html`` uploaded as ``application/octet-stream``
    downloads instead of rendering. Guessed from the extension rather than
    trusted from the browser, which reports nothing at all for many types.
    """
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def draft_prefix(page_id: str) -> str:
    return f"draft/{page_id}/"


def live_prefix(page_id: str) -> str:
    return f"lesson/{page_id}/"


def presign_upload(page_id: str, path: str) -> dict:
    """A URL the browser can PUT one file to, and the key it will land on."""
    safe = clean_path(path)
    key = f"{draft_prefix(page_id)}{safe}"
    content_type = content_type_for(safe)
    url = client().generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket(), "Key": key, "ContentType": content_type},
        ExpiresIn=UPLOAD_URL_TTL_SECONDS,
        HttpMethod="PUT",
    )
    # `content_type` is returned because the browser MUST send the same value as
    # a `Content-Type` header — a presigned URL signs the header, so a mismatch
    # is rejected by S3 with a signature error that reads like a bug.
    return {"path": safe, "key": key, "url": url, "content_type": content_type}


def _list_keys(prefix: str) -> list[str]:
    paginator = client().get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket(), Prefix=prefix):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return keys


def list_draft_files(page_id: str) -> list[str]:
    """Relative paths currently uploaded for this lesson."""
    prefix = draft_prefix(page_id)
    return sorted(key[len(prefix):] for key in _list_keys(prefix))


def has_index(page_id: str) -> bool:
    """Whether the draft has the one file a lesson cannot be served without."""
    return INDEX_FILE in list_draft_files(page_id)


def _delete_prefix(prefix: str) -> int:
    keys = _list_keys(prefix)
    for batch_start in range(0, len(keys), 1000):
        batch = keys[batch_start : batch_start + 1000]
        client().delete_objects(
            Bucket=bucket(), Delete={"Objects": [{"Key": k} for k in batch]}
        )
    return len(keys)


def clear_draft(page_id: str) -> int:
    """Empty the draft prefix.

    Called before a fresh upload so a re-upload REPLACES the lesson rather than
    merging into it. Without this, a file she renamed or removed in her
    authoring tool would linger and, worse, still be reachable once published.
    """
    return _delete_prefix(draft_prefix(page_id))


def publish(page_id: str) -> int:
    """Copy the draft onto the live prefix. Returns the number of files served.

    The live prefix is emptied first rather than copied over: a lesson that
    loses a file between uploads must lose it for students too, and a merge
    would leave the old one served alongside the new.
    """
    draft = draft_prefix(page_id)
    live = live_prefix(page_id)
    keys = _list_keys(draft)
    if not keys:
        raise ValueError("nothing has been uploaded for this page yet")
    if f"{draft}{INDEX_FILE}" not in keys:
        raise ValueError(
            f"a lesson needs an {INDEX_FILE} at the top level; upload one and try again"
        )

    _delete_prefix(live)
    for key in keys:
        relative = key[len(draft):]
        client().copy_object(
            Bucket=bucket(),
            Key=f"{live}{relative}",
            CopySource={"Bucket": bucket(), "Key": key},
            # The copy keeps the source's content type; stated rather than
            # assumed, because a copy that lost it would serve every page as a
            # download.
            MetadataDirective="COPY",
        )
    return len(keys)


def withdraw(page_id: str) -> int:
    """Remove the served copy. The draft is untouched, so publishing restores it."""
    return _delete_prefix(live_prefix(page_id))


def delete_everything(page_id: str) -> int:
    """Both prefixes, for a page being deleted outright."""
    return _delete_prefix(draft_prefix(page_id)) + _delete_prefix(live_prefix(page_id))
