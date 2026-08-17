"""Fixtures for the pipeline suite.

Mirrors `studio/backend/tests/conftest.py` deliberately: same moto-backed
miniature of the real bucket, same neutral subject tokens. The two halves of
studio read the same tree, so their fixtures agreeing is what makes a
disagreement between them meaningful.
"""

import os

import boto3
import pytest

# Credentials/region must exist before boto3/moto import time.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
# Explicit rather than defaulted: the pipeline's bucket and prefix come from
# XHARNESS_S3_* , and a stale value in a shell would silently move every
# assertion in the suite onto a different tree.
os.environ["XHARNESS_S3_BUCKET"] = "xharness-prod-media-us-east-1"
os.environ["XHARNESS_S3_PREFIX"] = ""
# Never let a test reach the real API, whatever is in studio/.env.
os.environ["REPLICATE_API_TOKEN"] = "r8_test_token"

from moto import mock_s3  # noqa: E402

BUCKET = "xharness-prod-media-us-east-1"

# The two trees, as the pipeline writes them.
FIXTURE_OBJECTS = {
    # A character: the bible, a described reference library in purpose
    # subfolders, and the non-reference pools.
    "characters/subject-a/profile.yaml": (
        b"name: Subject A\n"
        b"references:\n"
        b"  - file: face/subject-a_1.webp\n"
        b"    tags: [face]\n"
        b"    description: front, neutral\n"
        b"  - file: face/subject-a_2.webp\n"
        b"    tags: [face, profile]\n"
        b"    description: three-quarter\n"
        b"  - file: body/subject-a_1.webp\n"
        b"    tags: [body]\n"
        b"    description: full length\n"
    ),
    "characters/subject-a/reference/face/subject-a_1.webp": b"webp-bytes",
    "characters/subject-a/reference/face/subject-a_2.webp": b"webp-bytes",
    "characters/subject-a/reference/body/subject-a_1.webp": b"webp-bytes",
    "characters/subject-a/seed/subject-a_1.webp": b"webp-bytes",
    "characters/subject-a/corpus/IMG_1966_Original.JPG": b"jpg-bytes",
    "characters/subject-a/archive/subject-a_9.webp": b"webp-bytes",
    "characters/subject-b/profile.yaml": b"name: Subject B\n",
    "characters/subject-b/reference/face/subject-b_1.jpeg": b"jpeg-bytes",
    # A project: its registry doc, a run with metadata and output, an input pool.
    "projects/subject-a/project.json": b'{"project": "subject-a", "characters": ["subject-a"]}',
    "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch/request.json": b'{"model": "kling"}',
    "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch/result.json": b'{"status": "succeeded"}',
    "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch/output/wave-porch.jpeg": b"jpeg-bytes",
    "projects/subject-a/input/subject-a_1.webp": b"webp-bytes",
    "projects/subject-a/input/subject-a_2.webp": b"webp-bytes",
    # The shared wording list.
    "phrasebook/wording.yaml": (
        b"models:\n"
        b"  kling:\n"
        b"    replicate: kwaivgi/kling-v3-omni-video\n"
        b"    entries:\n"
        b"      - avoid: bare chest\n"
        b"        use: chest\n"
        b"      - avoid: shirtless\n"
        b"        use: omit entirely\n"
    ),
}


@pytest.fixture
def media_bucket():
    """A moto S3 bucket seeded with the miniature tree."""
    with mock_s3():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        for key, body in FIXTURE_OBJECTS.items():
            s3.put_object(Bucket=BUCKET, Key=key, Body=body)
        yield s3
