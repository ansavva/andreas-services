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
from studio_core.services import keys as _keys  # noqa: E402
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
                {"AttributeName": "reel", "AttributeType": "S"},
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
                # **Hashed on `reel`, not on `lib`**, and the two hold the same
                # string — which is exactly why the distinction has to be in the
                # fixture rather than assumed. A DynamoDB item enters a GSI only
                # when it carries both key attributes, so what the attribute is
                # *named* decides who is in the index: `reel` is written onto
                # image and video file nodes and onto nothing else, so folders,
                # entity records, slug claims and reference rows stay out. A
                # fixture keyed on `lib` would let the sparse-index tests pass
                # against a dense index.
                {
                    "IndexName": "by-recent",
                    "KeySchema": [
                        {"AttributeName": "reel", "KeyType": "HASH"},
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


# ─────────────────────── the same tree, as catalog rows ───────────────────────
#
# **Derived from `FIXTURE_OBJECTS` rather than written out beside it**, and that
# is the whole point of it. The bucket and the catalog are two descriptions of
# one library, and a hand-maintained second list would drift from the first on
# the day somebody added a file to one of them. Deriving means the two agree by
# construction — which is the same reason `pipeline/tests/conftest.py` mirrors
# this file rather than inventing its own tree.
#
# Three properties of the real thing are reproduced deliberately:
#
# * **A key ending in `/` becomes a folder, never a file.** That is the fixture's
#   zero-byte marker, and it is the demonstration that a marker cannot exist in
#   a catalog — there is nothing for it to be but the folder it was faking.
# * **`blob_key` is the object's own key**, not `blobs/<node_id>`. Prod is full
#   of keys written years before this table existed and they stay where they are,
#   so the fixture holds the legacy shape rather than the one #294 mints.
# * **`created_at` increases by one microsecond per node, in declaration order.**
#   Sub-second resolution is the point: it is what retires the key tie-break in
#   `browse._sort_records`, and a fixture stamped to the second would let the
#   retired workaround pass unnoticed.
# * **`reel` is written only onto image and video files**, from the extension,
#   exactly as `catalog._reel_value` does. It is the sparse `by-recent` key, so a
#   fixture that put it on every row would make the reel tests pass against a
#   dense index — the thing the entity model changed.

CATALOG_TREE_START = "2026-08-19T12:30:00.{:06d}+00:00"


# Every node in the fixture tree, keyed by the slash-joined name path that used
# to be its address. **Filled in by `_tree_items` rather than written out**, for
# the reason the tree itself is derived: a hand-kept second list drifts.
#
# It exists because the API stopped taking name paths. A test that wants "the
# `seed` folder" used to say `?prefix=characters/subject-a/seed/` and now says
# `?node=<id>`, and the id is a UUID minted by the fixture — so the readable
# name has to live somewhere, and here is the one place that knows both.
CATALOG_NODE_IDS: dict[str, str] = {}


def _tree_items(objects: dict) -> list[dict]:
    """Every node the object map implies, ancestors first."""
    items: list[dict] = []
    folders = {(): CATALOG_ROOT}
    minted = 0

    def _node(name: str, parent: tuple, kind: str, key: str | None) -> str:
        nonlocal minted
        minted += 1
        node_id = f"node-{minted:03d}"
        stamp = CATALOG_TREE_START.format(minted)
        parent_id = folders[parent]
        # `path` is the ancestor ids, root first and the node's own id absent —
        # the same string `catalog.child_path` builds for a node's children.
        ancestors = [folders[parent[:depth]] for depth in range(len(parent) + 1)]
        path = "".join(f"/{ancestor}" for ancestor in ancestors)
        record = {
            "node_id": {"S": node_id},
            "parent_id": {"S": parent_id},
            "lib": {"S": CATALOG_LIBRARY},
            "name": {"S": name},
            "kind": {"S": kind},
            "path": {"S": f"{path}/"},
            "created_at": {"S": stamp},
            "updated_at": {"S": stamp},
        }
        if key is not None:
            record["blob_key"] = {"S": key}
            record["size"] = {"N": str(len(objects[key]))}
            record["content_type"] = {"S": "application/octet-stream"}
            if _keys.kind(name) in ("image", "video"):
                record["reel"] = {"S": CATALOG_LIBRARY}
        CATALOG_NODE_IDS["/".join([*parent, name])] = node_id
        items.append({"pk": {"S": f"NODE#{node_id}"}, "sk": {"S": "META"}, **record})
        items.append(
            {
                "pk": {"S": f"NODE#{parent_id}"},
                "sk": {"S": f"NAME#{name}"},
                "node_id": {"S": node_id},
                "lib": {"S": CATALOG_LIBRARY},
                "kind": {"S": kind},
                "path": {"S": f"{path}/"},
                "created_at": {"S": stamp},
            }
        )
        return node_id

    for key in objects:
        segments = key.split("/")
        # A trailing slash leaves an empty last segment: the key is a folder
        # marker, so every segment of it is a folder and there is no file.
        names, leaf = segments[:-1], segments[-1] or None
        for depth, name in enumerate(names):
            branch = tuple(names[: depth + 1])
            if branch not in folders:
                folders[branch] = _node(name, branch[:-1], "folder", None)
        if leaf is not None:
            _node(leaf, tuple(names), "file", key)

    return items


CATALOG_TREE_ITEMS = _tree_items(FIXTURE_OBJECTS)


@pytest.fixture
def catalog_tree(media_bucket, catalog_table):
    """The fixture bucket *and* the catalog rows that describe it.

    Every browse test wants both: the rows say what exists, and the objects are
    what `presign` signs for. Hands back both clients so a test can add to either
    — and a test that adds to only one is testing the disagreement, which is
    occasionally the point.
    """
    for item in CATALOG_TREE_ITEMS:
        catalog_table.put_item(TableName=config.catalog_table(), Item=item)
    return media_bucket, catalog_table


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


def node_id_at(path: str) -> str:
    """The fixture node id at one name path, for a test that wants to read well.

    `node_id_at("characters/subject-a/seed")` rather than a UUID literal. Raises
    a `KeyError` naming the path, which is a better failure than a request
    against `None` that comes back 400.
    """
    return CATALOG_NODE_IDS[path.strip("/")]


@pytest.fixture
def api(catalog_tree):
    """A signed-in test client over the fixture bucket and its catalog rows.

    The two fixtures are almost always wanted together — the rows say what
    exists and the objects are what `presign` signs for — and every route test
    then opens with the same two lines. This is those two lines.
    """
    return app_factory.create_app().test_client()


@pytest.fixture
def empty_api(catalog_table, media_bucket):
    """A signed-in client over a library holding nothing but its root.

    The entity tests want this rather than `api`: the fixture tree is a
    *pre-catalog* library — folders named `characters/` and `projects/` with no
    entity rows behind them — and creating a character called `subject-a` in it
    would collide with a folder of that name for reasons that have nothing to do
    with what is being tested.
    """
    return app_factory.create_app().test_client()
