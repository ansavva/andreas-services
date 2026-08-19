import os

import boto3
import pytest

# Credentials/region must exist before boto3/moto import time.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("STUDIO_MEDIA_BUCKET", "studio-prod-media-us-east-1")
os.environ.setdefault("STUDIO_CATALOG_TABLE", "studio-prod-catalog")
# Assigned rather than defaulted: the browsable root is the whole bucket, and a
# stale `STUDIO_MEDIA_ROOT_PREFIX` left in a shell would otherwise silently
# rewrite what every test in the suite is asserting about.
os.environ["STUDIO_MEDIA_ROOT_PREFIX"] = ""

from moto import mock_dynamodb, mock_s3  # noqa: E402

from studio_core import app_factory, config  # noqa: E402
from studio_core.clients.aws import dynamodb, s3  # noqa: E402
from studio_core.errors import AuthError  # noqa: E402

# A miniature of the real bucket, which no longer wraps anything in `media/`:
# `characters/` holds who a subject is, `projects/` holds what was generated of
# them, and `phrasebook/` sits alongside both. Two subjects, a run folder with
# output and metadata, a scene with its shots, a video run under misc, and one
# zero-byte folder marker.
FIXTURE_OBJECTS = {
    "characters/subject-a/profile.yaml": b"name: Subject A\n",
    # The pipeline writes real keys, but a folder made in the console is a
    # zero-byte object and a listing must never show it as a file.
    "characters/subject-a/seed/": b"",
    "characters/subject-a/seed/subject-a_1.webp": b"webp-bytes",
    "characters/subject-a/seed/subject-a_2.webp": b"webp-bytes",
    "characters/subject-a/reference/subject-a_1.txt": b"a caption",
    "characters/subject-a/reference/subject-a_1.webp": b"webp-bytes",
    # Uppercase extension: characters/subject-b/corpus really does contain .JPG files.
    "characters/subject-b/corpus/IMG_1966_Original.JPG": b"jpg-bytes",
    "characters/subject-b/reference/face/subject-b_face_1.jpeg": b"jpeg-bytes",
    "phrasebook/wording.yaml": b"greeting: hello\n",
    "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/request.json": b'{"model": "x"}',
    "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/result.json": b'{"status": "succeeded"}',
    "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/output/wave-porch.jpeg": b"jpeg-bytes",
    "projects/misc/runs/2026-08-14_16-32-11_kling-yqp1jqf5/output/kling.mp4": b"mp4-bytes",
    "projects/misc/runs/2026-08-14_16-32-11_kling-yqp1jqf5/request.json": b'{"kind": "video"}',
    "projects/subject-b/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4": b"mp4-bytes",
    "projects/subject-b/scenes/2026-08-16_07-40-22_stadium-encounter/scene.json": b'{"shots": 1}',
    "projects/subject-b/scenes/2026-08-16_07-40-22_stadium-encounter/shots/shot-01.mp4": b"mp4-bytes",
    "projects/subject-b/scenes/2026-08-16_07-40-22_stadium-encounter/output/stadium.mp4": b"mp4-bytes",
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


# A miniature of the catalog table. Unlike the bucket above there is nothing
# real to copy yet — nothing writes to this table in prod — so what it holds is
# the smallest arrangement every catalog test needs: one library, two members,
# and the root node the library points at.
#
# **The seed items below are written literally rather than through
# `services.catalog`**, and that is the point of them. `catalog` is the only
# module allowed to know these shapes, so a test that built its fixture with
# `catalog`'s own key helpers would agree with any drift in them. Spelling the
# items out means the schema is asserted from outside the module that
# implements it.
CATALOG_LIBRARY = "lib-0001"
CATALOG_ROOT = "node-root"
CATALOG_OWNER = "sub-owner"
CATALOG_MEMBER = "sub-member"

_SEED_TIME = "2026-08-19T12:00:00.000000+00:00"

CATALOG_ITEMS = [
    {
        "pk": {"S": f"LIB#{CATALOG_LIBRARY}"},
        "sk": {"S": "META"},
        "name": {"S": "Library"},
        "root_node": {"S": CATALOG_ROOT},
        "created_at": {"S": _SEED_TIME},
    },
    {
        "pk": {"S": f"USER#{CATALOG_OWNER}"},
        "sk": {"S": f"LIB#{CATALOG_LIBRARY}"},
        "role": {"S": "owner"},
        "created_at": {"S": _SEED_TIME},
    },
    {
        "pk": {"S": f"USER#{CATALOG_MEMBER}"},
        "sk": {"S": f"LIB#{CATALOG_LIBRARY}"},
        "role": {"S": "member"},
        "created_at": {"S": _SEED_TIME},
    },
    # The root node: a real record with `path` "/" and no `parent_id`, which is
    # what makes it unrenamable, unmovable and undeletable. It has no `NAME#`
    # item because nothing lists it as a child of anything.
    {
        "pk": {"S": f"NODE#{CATALOG_ROOT}"},
        "sk": {"S": "META"},
        "node_id": {"S": CATALOG_ROOT},
        "lib": {"S": CATALOG_LIBRARY},
        "name": {"S": "Library"},
        "kind": {"S": "folder"},
        "path": {"S": "/"},
        "created_at": {"S": _SEED_TIME},
        "updated_at": {"S": _SEED_TIME},
    },
]


@pytest.fixture
def catalog_table():
    """A live (moto-backed) copy of the catalog table, isolated per test."""
    with mock_dynamodb():
        dynamodb.reset_client()
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=config.catalog_table(),
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            # Only the attributes an index is keyed on are declared. Everything
            # else about an item is schemaless, which is what lets one table
            # hold libraries, memberships and both halves of a node.
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "lib", "AttributeType": "S"},
                {"AttributeName": "path", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "by-sk",
                    "KeySchema": [
                        {"AttributeName": "sk", "KeyType": "HASH"},
                        {"AttributeName": "pk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "by-path",
                    "KeySchema": [
                        {"AttributeName": "lib", "KeyType": "HASH"},
                        {"AttributeName": "path", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                # Unused by `services.catalog` today — the reel is what will
                # query it. Created anyway, so the fixture is the table rather
                # than the subset one module happens to need.
                {
                    "IndexName": "by-recent",
                    "KeySchema": [
                        {"AttributeName": "lib", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        )
        for item in CATALOG_ITEMS:
            client.put_item(TableName=config.catalog_table(), Item=item)
        yield client
        dynamodb.reset_client()


# ─────────────────────────── the signed-in caller ───────────────────────────
#
# `app_factory`'s `before_request` hook identifies the caller and resolves their
# library on every request that is not `OPTIONS` or `/api/health`. Neither half
# can run for real in a test: `identity.caller_sub` verifies an RS256 signature
# against a live Cognito pool's JWKS endpoint, and `catalog.libraries_for` reads
# DynamoDB. So every route test in the suite would 401 or 502 before reaching the
# route it is about.
#
# **This fixture is autouse, and that is the decision.** The alternative is a
# header and a stub in each of the thirty-seven tests in `test_api.py`, none of
# which is about authentication — they are about listings, moves and body
# lengths, and they were written before there was a caller to have. Signing them
# all in by default keeps each of them asserting the one thing it names.
#
# What it deliberately does *not* do is weaken the hook. The hook is unchanged
# and fully exercised, by `test_before_request.py`, which reconfigures this same
# object rather than opting out of it — so there is one description of "who is
# calling" in the suite and it is this one.
#
# One object stands in for both modules because the hook uses exactly one
# function from each, and patching `app_factory`'s *references* rather than the
# modules themselves is what keeps `test_identity.py` testing the real
# `caller_sub`.


class SignedIn:
    """The caller `before_request` will find, and the libraries they are in."""

    def __init__(self):
        self.sub = CATALOG_OWNER
        self.libraries = [{"lib": CATALOG_LIBRARY, "role": "owner"}]
        self.authenticated = True

    # Stands in for `services.identity`.
    def caller_sub(self, authorization_header):
        if not self.authenticated:
            raise AuthError("An Authorization header is required.")
        return self.sub

    # Stands in for `services.catalog`. Only the membership rows, which is all
    # `_resolve_library` asks for.
    def libraries_for(self, sub):
        return [dict(library) for library in self.libraries]


@pytest.fixture(autouse=True)
def signed_in(monkeypatch):
    """Sign every request in as the library's owner, unless a test says otherwise."""
    caller = SignedIn()
    monkeypatch.setattr(app_factory, "identity", caller)
    monkeypatch.setattr(app_factory, "catalog", caller)
    return caller
