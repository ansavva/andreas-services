"""
S3 artifact storage for source runs.

Root bodies/HTML, fetched linked pages, and agent transcripts are stored in a
private bucket (SCOUT_ARTIFACTS_BUCKET) under runs/<source_id>/<run_id>/. Helpers
return an s3://bucket/key reference that is recorded on the run item; objects are
never purged (soft-delete only).
"""

import os

import boto3

_s3 = None


def _region():
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def _client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=_region())
    return _s3


def _bucket():
    bucket = os.environ.get("SCOUT_ARTIFACTS_BUCKET", "")
    if not bucket:
        raise RuntimeError("SCOUT_ARTIFACTS_BUCKET is not configured")
    return bucket


def _prefix(source_id, run_id):
    return f"runs/{source_id}/{run_id}/"


def root_html_key(source_id, run_id):
    return _prefix(source_id, run_id) + "root.html"


def root_body_key(source_id, run_id):
    return _prefix(source_id, run_id) + "root-body.txt"


def linked_page_key(source_id, run_id, index):
    return _prefix(source_id, run_id) + f"linked/{index}.html"


def transcript_key(source_id, run_id):
    return _prefix(source_id, run_id) + "transcript.json"


def put_text(key, text, content_type="text/plain"):
    bucket = _bucket()
    _client().put_object(
        Bucket=bucket, Key=key,
        Body=(text or "").encode("utf-8"),
        ContentType=content_type,
    )
    return f"s3://{bucket}/{key}"


def get_text(ref):
    """Read an artifact back, accepting an s3://bucket/key ref or a bare key."""
    if ref.startswith("s3://"):
        bucket, key = ref[len("s3://"):].split("/", 1)
    else:
        bucket, key = _bucket(), ref
    resp = _client().get_object(Bucket=bucket, Key=key)
    return resp["Body"].read().decode("utf-8")


def _trim_to_utf8_boundary(raw):
    """Return the longest prefix of `raw` that's a complete UTF-8 sequence.

    Range GET cuts on bytes, but artifacts are text — splitting a multi-byte
    character across chunks would corrupt the boundary char and break decode.
    We walk back to the last lead byte and, if its expected continuations are
    incomplete, drop the whole partial char so each chunk decodes cleanly and
    the next chunk resumes at exactly the byte we stopped on.
    """
    n = len(raw)
    if n == 0:
        return raw
    # Walk back over continuation bytes (10xxxxxx) to the lead. UTF-8 is at
    # most 4 bytes, so a valid sequence has ≤3 trailing continuations.
    i = n - 1
    while i >= 0 and (raw[i] & 0b11000000) == 0b10000000 and (n - 1 - i) < 3:
        i -= 1
    if i < 0:
        return raw  # all continuations: not valid UTF-8 by itself; let caller decide
    b = raw[i]
    if (b & 0b10000000) == 0:
        expected = 1
    elif (b & 0b11100000) == 0b11000000:
        expected = 2
    elif (b & 0b11110000) == 0b11100000:
        expected = 3
    elif (b & 0b11111000) == 0b11110000:
        expected = 4
    else:
        return raw[:i]  # invalid lead — drop it
    have = n - i
    return raw if have >= expected else raw[:i]


def get_range(ref, offset, length):
    """Read up to `length` bytes from `ref` starting at `offset`, trim to the
    last complete UTF-8 character, and return (text, next_offset, total).

    `next_offset` is the byte index the next chunk should start at, or None
    when the end of the object has been reached. `total` is the object's full
    size (in bytes) as reported by S3.
    """
    if ref.startswith("s3://"):
        bucket, key = ref[len("s3://"):].split("/", 1)
    else:
        bucket, key = _bucket(), ref
    end = offset + length - 1
    resp = _client().get_object(Bucket=bucket, Key=key, Range=f"bytes={offset}-{end}")
    raw = resp["Body"].read()
    content_range = resp.get("ContentRange", "")
    total = int(content_range.rsplit("/", 1)[1]) if "/" in content_range else len(raw)
    decoded_bytes = _trim_to_utf8_boundary(raw)
    text = decoded_bytes.decode("utf-8")
    consumed = offset + len(decoded_bytes)
    next_offset = consumed if consumed < total else None
    return text, next_offset, total


def store_root_html(source_id, run_id, html):
    return put_text(root_html_key(source_id, run_id), html, "text/html")


def store_root_body(source_id, run_id, text):
    return put_text(root_body_key(source_id, run_id), text, "text/plain")


def store_linked_page(source_id, run_id, index, html):
    return put_text(linked_page_key(source_id, run_id, index), html, "text/html")


def store_transcript(source_id, run_id, transcript_json):
    return put_text(transcript_key(source_id, run_id), transcript_json,
                    "application/json")
