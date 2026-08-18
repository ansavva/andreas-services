"""Fixtures for the pipeline suite.

Mirrors `studio/backend/tests/conftest.py` deliberately: same moto-backed
miniature of the real bucket, same neutral subject tokens. The two halves of
studio read the same tree, so their fixtures agreeing is what makes a
disagreement between them meaningful.
"""

import json
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


def _json(doc: dict) -> bytes:
    """A fixture record, built rather than hand-concatenated.

    The scene manifests started life as strings of `b'…'` fragments, which read
    badly and broke silently on a missing comma — a malformed fixture makes every
    test built on it hollow rather than red.
    """
    return json.dumps(doc).encode()


def _panel(n: int, prompt: str, **over) -> dict:
    panel = {"n": n, "role": None, "prompt": prompt, "model": "nano-banana-pro",
             "extra": {"output_format": "png"}, "references": {},
             "run": None, "source_key": None, "key": None, "boarded": None,
             "stale": False}
    panel.update(over)
    return panel


def _motion(prompt: str, **over) -> dict:
    motion = {"prompt": prompt, "prompt_json": None, "model": "kling", "duration": 5,
              "references": {"max_scene_frames": None, "characters": [], "keys": []}}
    motion.update(over)
    return motion


#: The fields a shot only gets once it has been rendered and cut.
_UNRENDERED = {"run": None, "runref": None, "key": None, "shot_key": None,
               "duration": None, "rendered": None}

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
    # stands in for a real seed or handoff frame has to be one.
    "projects/subject-a/input/subject-a_3.png": b"png-bytes",
    # A scene from before scenes were planned: keyed by <timestamp>_<slug>, no
    # plan behind it, and already cut. It is here so back-compat is tested
    # rather than assumed — these still exist in the real bucket.
    "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/scene.json": _json({
        "scene": "subject-a/2026-08-16_07-40-22_old-cut",
        "project": "subject-a",
        "slug": "old-cut",
        # DELIBERATELY newer than the planned scene below, so a test of `latest`
        # proves the manifests are being read rather than the ids sorted.
        "created": "2026-12-31T00:00:00+00:00",
        "characters": ["subject-a"],
        "shots": [{
            "n": 1,
            "run": "subject-a/2026-08-04_21-30-54_wave-porch",
            "shot_key": "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut"
                        "/shots/shot-01.mp4",
        }],
        "stitch": {"method": "concat demuxer, stream copy (no re-encode)"},
        "output": {"key": "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut"
                          "/output/old-cut.mp4", "duration": 5.0},
    }),
    "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/shots/shot-01.mp4": b"mp4-bytes",
    "projects/subject-a/scenes/2026-08-16_07-40-22_old-cut/output/old-cut.mp4": b"mp4-bytes",
    # A scene as planned today: keyed by slug, two shots, one panel landed, and
    # deliberately `"output": None` — the planned/assembled discriminator.
    "projects/subject-a/scenes/board-test/scene.json": _json({
        "scene": "subject-a/board-test",
        "project": "subject-a",
        "slug": "board-test",
        "version": 2,
        "status": "boarding",
        "created": "2026-01-01T00:00:00+00:00",
        "updated": "2026-01-01T00:00:00+00:00",
        "characters": ["subject-a"],
        "setting": "",
        "defaults": {"model": "kling", "panel_model": "nano-banana-pro",
                     "duration": 5, "panel_extra": {"output_format": "png"}},
        "shots": [
            {
                "n": 1, "id": "shot-01", "beat": "opens", "status": "boarded",
                "panels": [_panel(
                    1, "the opening frame",
                    key="projects/subject-a/scenes/board-test/storyboard/shot-01-p1.png",
                    references={"characters": ["subject-a"]})],
                "motion": _motion("the opening motion"),
                # Nothing precedes shot 1, so its own panel opens it.
                "continues": False,
                "opens_on": {"key": None, "from_run": None},
                **_UNRENDERED,
            },
            {
                "n": 2, "id": "shot-02", "beat": "continues", "status": "planned",
                "panels": [_panel(1, "he turns"), _panel(2, "he lands")],
                "motion": _motion("the second motion"),
                # Expects a handoff and does not have one yet.
                "continues": True,
                "opens_on": {"key": None, "from_run": None},
                **_UNRENDERED,
            },
        ],
        "stitch": None, "output": None, "assembled": None,
    }),
    "projects/subject-a/scenes/board-test/storyboard/shot-01-p1.png": b"png-bytes",
    # A chain with no scene behind it — which is the only way chains were ever
    # actually used. A planned scene derives its own frames from `scene.json`.
    "projects/subject-a/chains/loose-sequence.json": _json({
        "chain": "subject-a/loose-sequence", "project": "subject-a",
        "slug": "loose-sequence",
        "seed": "projects/subject-a/input/subject-a_3.png", "frames": [],
    }),
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
