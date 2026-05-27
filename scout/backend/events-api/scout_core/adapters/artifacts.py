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


def store_root_html(source_id, run_id, html):
    return put_text(root_html_key(source_id, run_id), html, "text/html")


def store_root_body(source_id, run_id, text):
    return put_text(root_body_key(source_id, run_id), text, "text/plain")


def store_linked_page(source_id, run_id, index, html):
    return put_text(linked_page_key(source_id, run_id, index), html, "text/html")


def store_transcript(source_id, run_id, transcript_json):
    return put_text(transcript_key(source_id, run_id), transcript_json,
                    "application/json")
