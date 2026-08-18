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

from moto import mock_s3

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
    # A PNG in the pool: the video engines reject `.webp`, so anything that
    # stands in for a real chain seed or handoff frame has to be one.
    "projects/subject-a/input/subject-a_3.png": b"png-bytes",
    # A scene from before scenes were planned: keyed by <timestamp>_<slug>, no
    # plan behind it, and already cut. It is here so back-compat is tested
    # rather than assumed — these still exist in the real bucket.
    "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/scene.json": (
        b'{"scene": "subject-a/2026-08-16_07-40-22_old-cut",'
        b' "project": "subject-a", "slug": "old-cut",'
        b' "created": "2026-12-31T00:00:00+00:00", "characters": ["subject-a"],'
        b' "shots": [{"n": 1, "run": "subject-a/2026-08-04_21-30-54_wave-porch",'
        b'   "shot_key": "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/shots/shot-01.mp4"}],'
        b' "stitch": {"method": "concat demuxer, stream copy (no re-encode)"},'
        b' "output": {"key":'
        b'   "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/output/old-cut.mp4",'
        b'   "duration": 5.0}}'
    ),
    "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/shots/shot-01.mp4": b"mp4-bytes",
    "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/output/old-cut.mp4": b"mp4-bytes",
    # A scene as planned today: keyed by slug, two shots, one panel landed, and
    # deliberately `"output": null` — the planned/assembled discriminator.
    # Its `created` is DELIBERATELY older than the legacy scene's, so a test of
    # `latest` proves the manifests are being read rather than the ids sorted.
    "projects/subject-a/scenes/board-test/scene.json": (
        b'{"scene": "subject-a/board-test", "project": "subject-a",'
        b' "slug": "board-test", "version": 2, "status": "boarding",'
        b' "created": "2026-01-01T00:00:00+00:00",'
        b' "updated": "2026-01-01T00:00:00+00:00",'
        b' "characters": ["subject-a"],'
        b' "defaults": {"model": "kling", "panel_model": "nano-banana-pro",'
        b'   "duration": 5, "chain": "board-test",'
        b'   "panel_extra": {"output_format": "png"}},'
        b' "shots": ['
        b'  {"n": 1, "id": "shot-01", "beat": "opens", "status": "boarded",'
        b'   "panels": [{"n": 1, "role": null, "prompt": "the opening frame",'
        b'     "model": "nano-banana-pro", "extra": {"output_format": "png"},'
        b'     "references": {"characters": ["subject-a"]},'
        b'     "run": null, "source_key": null, "stale": false,'
        b'     "key": "projects/subject-a/scenes/board-test/storyboard/shot-01-p1.png"}],'
        b'   "motion": {"prompt": "the opening motion", "model": "kling", "duration": 5,'
        b'     "references": {"chain": "board-test", "characters": [], "keys": []}},'
        b'   "chain": {"slug": "board-test", "use_handoff": false,'
        b'     "start_key": null, "from_run": null},'
        b'   "run": null, "runref": null, "key": null, "shot_key": null,'
        b'   "duration": null, "rendered": null},'
        b'  {"n": 2, "id": "shot-02", "beat": "continues", "status": "planned",'
        b'   "panels": [{"n": 1, "prompt": "he turns", "model": "nano-banana-pro",'
        b'     "extra": {"output_format": "png"}, "references": {},'
        b'     "run": null, "source_key": null, "key": null, "stale": false},'
        b'    {"n": 2, "prompt": "he lands", "model": "nano-banana-pro",'
        b'     "extra": {"output_format": "png"}, "references": {},'
        b'     "run": null, "source_key": null, "key": null, "stale": false}],'
        b'   "motion": {"prompt": "the second motion", "model": "kling", "duration": 5,'
        b'     "references": {"chain": "board-test", "characters": [], "keys": []}},'
        b'   "chain": {"slug": "board-test", "use_handoff": true,'
        b'     "start_key": null, "from_run": null},'
        b'   "run": null, "runref": null, "key": null, "shot_key": null,'
        b'   "duration": null, "rendered": null}],'
        b' "stitch": null, "output": null, "assembled": null}'
    ),
    "projects/subject-a/scenes/board-test/storyboard/shot-01-p1.png": b"png-bytes",
    "projects/subject-a/chains/board-test.json": (
        b'{"chain": "subject-a/board-test", "project": "subject-a",'
        b' "slug": "board-test",'
        b' "seed": "projects/subject-a/input/subject-a_3.png", "frames": []}'
    ),
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
