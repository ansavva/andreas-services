import os

import boto3
import pytest

# Credentials/region must exist before boto3/moto import time.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("STUDIO_MEDIA_BUCKET", "xharness-prod-media-us-east-1")
# Assigned rather than defaulted: the browsable root is the whole bucket, and a
# stale `STUDIO_MEDIA_ROOT_PREFIX` left in a shell would otherwise silently
# rewrite what every test in the suite is asserting about.
os.environ["STUDIO_MEDIA_ROOT_PREFIX"] = ""

from moto import mock_s3  # noqa: E402

from studio_core import config  # noqa: E402
from studio_core.clients.aws import s3  # noqa: E402

# A miniature of the real bucket, which no longer wraps anything in `media/`:
# `characters/` holds who a subject is, `projects/` holds what was generated of
# them, and `phrasebook/` sits alongside both. Two subjects, a run folder with
# output and metadata, a scene with its shots, a video run under misc, and one
# zero-byte folder marker.
FIXTURE_OBJECTS = {
    "characters/fred/profile.yaml": b"name: Fred\n",
    # The pipeline writes real keys, but a folder made in the console is a
    # zero-byte object and a listing must never show it as a file.
    "characters/fred/seed/": b"",
    "characters/fred/seed/fred_1.webp": b"webp-bytes",
    "characters/fred/seed/fred_2.webp": b"webp-bytes",
    "characters/fred/reference/fred_1.txt": b"a caption",
    "characters/fred/reference/fred_1.webp": b"webp-bytes",
    # Uppercase extension: characters/mr-p/corpus really does contain .JPG files.
    "characters/mr-p/corpus/IMG_1966_Original.JPG": b"jpg-bytes",
    "characters/mr-p/reference/face/mr-p_face_1.jpeg": b"jpeg-bytes",
    "phrasebook/wording.yaml": b"greeting: hello\n",
    "projects/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/request.json": b'{"model": "x"}',
    "projects/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/result.json": b'{"status": "succeeded"}',
    "projects/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/output/wave-porch.jpeg": b"jpeg-bytes",
    "projects/misc/runs/2026-08-14_16-32-11_kling-yqp1jqf5/output/kling.mp4": b"mp4-bytes",
    "projects/misc/runs/2026-08-14_16-32-11_kling-yqp1jqf5/request.json": b'{"kind": "video"}',
    "projects/mr-p/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4": b"mp4-bytes",
    "projects/mr-p/scenes/2026-08-16_07-40-22_stadium-encounter/scene.json": b'{"shots": 1}',
    "projects/mr-p/scenes/2026-08-16_07-40-22_stadium-encounter/shots/shot-01.mp4": b"mp4-bytes",
    "projects/mr-p/scenes/2026-08-16_07-40-22_stadium-encounter/output/stadium.mp4": b"mp4-bytes",
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
