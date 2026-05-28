"""S3 storage and HTTP download for event images.

Mirrors `artifacts.py` but for binary image bytes in the images bucket
(`SCOUT_IMAGES_BUCKET`). Image bytes live under a flat `images/<image_id>` key,
so the public image-serving route only needs an `image_id` to stream the bytes
back — no DynamoDB lookup at serve time. Content-Type is stored as S3 object
metadata so the route can echo it on the response.

Agent-extracted images come in as external source URLs; `download` fetches the
bytes with guardrails (http(s) only, public hosts only, image/* content-type,
size cap) so we own the bytes from then on, served via our API domain.
"""

import ipaddress
import os
import socket
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import boto3

_s3 = None

# Cap stored images at ~5 MB so the base64-encoded response stays under the
# Lambda response cap (~6 MB), and oversize sources can't poison the bucket.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_PREFIXES = ("image/",)
_FETCH_TIMEOUT = 8


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
    bucket = os.environ.get("SCOUT_IMAGES_BUCKET", "")
    if not bucket:
        raise RuntimeError("SCOUT_IMAGES_BUCKET is not configured")
    return bucket


def image_key(image_id):
    return f"images/{image_id}"


def put_bytes(image_id, data, content_type):
    bucket = _bucket()
    key = image_key(image_id)
    _client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    return f"s3://{bucket}/{key}"


def get_bytes(image_id):
    """Return (bytes, content_type) for a stored image, or (None, None) if absent."""
    bucket = _bucket()
    try:
        resp = _client().get_object(Bucket=bucket, Key=image_key(image_id))
    except _client().exceptions.NoSuchKey:
        return None, None
    return resp["Body"].read(), resp.get("ContentType") or "application/octet-stream"


class DownloadError(Exception):
    """Raised when an image URL can't be safely fetched."""


def _safe_host(host):
    """Reject loopback/private/link-local hosts to block SSRF to internal nets."""
    try:
        # Resolve all A/AAAA records and reject if any is non-public.
        for family, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            addr = sockaddr[0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
                return False
        return True
    except OSError:
        return False


def download(url):
    """Fetch an image URL with guardrails. Returns (bytes, content_type).

    Raises DownloadError on any guard violation (non-http(s), private host,
    wrong content-type, oversized, network failure). Callers treat failures
    as non-fatal and fall back to keeping the external URL.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise DownloadError(f"unsupported scheme: {parsed.scheme!r}")
    if not parsed.hostname or not _safe_host(parsed.hostname):
        raise DownloadError(f"host not allowed: {parsed.hostname!r}")
    req = Request(url, headers={"User-Agent": "scout-image-fetcher/1.0"})
    try:
        with urlopen(req, timeout=_FETCH_TIMEOUT) as resp:  # noqa: S310
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            if not any(content_type.startswith(p) for p in _ALLOWED_PREFIXES):
                raise DownloadError(f"unexpected content-type: {content_type!r}")
            # Read up to the cap + 1 so we can detect oversize without buffering more.
            data = resp.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise DownloadError("image exceeds size cap")
            return data, content_type
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"fetch failed: {exc}") from exc
