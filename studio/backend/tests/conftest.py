import os

import boto3
import pytest

# Credentials/region must exist before boto3/moto import time.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("STUDIO_MEDIA_BUCKET", "xharness-prod-media-us-east-1")
os.environ.setdefault("STUDIO_MEDIA_ROOT_PREFIX", "media/")

from moto import mock_s3  # noqa: E402

from studio_core import config  # noqa: E402
from studio_core.clients.aws import s3  # noqa: E402

# A miniature of the real bucket: two subjects, a run folder with output and
# metadata, a video run under misc, and the zero-byte folder markers the console
# leaves behind (the real bucket has several).
FIXTURE_OBJECTS = {
    "media/": b"",
    "media/fred/profile.md": b"# Fred\n\nA profile.\n",
    "media/fred/originals/": b"",
    "media/fred/originals/fred_1.webp": b"webp-bytes",
    "media/fred/originals/fred_2.webp": b"webp-bytes",
    "media/fred/reference/fred_1.txt": b"a caption",
    "media/fred/reference/fred_1.webp": b"webp-bytes",
    "media/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/request.json": b'{"model": "x"}',
    "media/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/result.json": b'{"status": "succeeded"}',
    "media/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/output/wave-porch.jpeg": b"jpeg-bytes",
    # Uppercase extension: mr-p/originals really does contain .JPG files.
    "media/mr-p/originals/IMG_1966_Original.JPG": b"jpg-bytes",
    "media/mr-p/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4": b"mp4-bytes",
    "media/misc/runs/2026-08-14_16-32-11_kling-yqp1jqf5/output/kling.mp4": b"mp4-bytes",
    "media/misc/runs/2026-08-14_16-32-11_kling-yqp1jqf5/request.json": b'{"kind": "video"}',
}


@pytest.fixture
def media_bucket():
    """A live (moto-backed) copy of the media bucket, isolated per test."""
    with mock_s3():
        s3.reset_client()
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=config.media_bucket())
        for key, body in FIXTURE_OBJECTS.items():
            client.put_object(Bucket=config.media_bucket(), Key=key, Body=body)
        yield client
        s3.reset_client()
