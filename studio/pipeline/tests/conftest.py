"""Fixtures for the pipeline suite.

**The moto-keyed shim is gone.** Until the entity model landed, this file
redirected `adapters/store` onto a moto bucket in which a node's id was its S3
key. That was a fiction the API never shared, and it hid the only thing these
tests exist to check: a restructure breaks *wiring*, and a suite that stubs the
store one function at a time asserts nothing about the route, the body or the
field names the CLI actually puts on the wire.

So the seam moved down to `adapters.api.request`, and `tests/fake_api.py` answers
it with an in-memory library keyed on real UUIDs. `adapters/entities.py` and
`adapters/store.py` now run for real in every test that touches storage, which
means a route renamed on one side and not the other fails here rather than in
production.

Bytes stay real, on the same moto bucket as before: presigned URLs are
`memory://<blob_key>` and `store._put` / `store._fetch` are pointed at moto, so
`curate dedupe` still hashes genuine bytes and `frames` still runs ffmpeg over a
genuine file.

Fixture subjects are `subject-a` / `subject-b`, per hard rule #1, and the project
is `porch-teaser` — deliberately **not** a character's slug. Entity roots are
children of the library root now, so a project sharing a character's slug would
be a name collision in the tree; the old fixture had `characters/subject-a` and
`projects/subject-a` and could not have shown that.
"""

import copy
import json
import os
import pathlib

import boto3
import pytest

# Credentials/region must exist before boto3/moto import time.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
# Explicit rather than defaulted: the pipeline's bucket comes from
# STUDIO_S3_BUCKET, and a stale value in a shell would silently move every
# assertion in the suite onto a different tree.
os.environ["STUDIO_S3_BUCKET"] = "studio-prod-media-us-east-1"
# The catalog table has no default either, for the reason `adapters/ddb.py`
# gives, so the suite has to name one — `catalog gc` and `catalog migrate`
# refuse before they reach moto otherwise.
os.environ["STUDIO_CATALOG_TABLE"] = "studio-prod-catalog"
# Never let a test reach the real API, whatever is in studio/.env.
os.environ["REPLICATE_API_TOKEN"] = "r8_test_token"

from moto import mock_dynamodb, mock_s3  # noqa: E402

from studio_pipeline.adapters import api as _api  # noqa: E402
from studio_pipeline.adapters import ddb as ddbc  # noqa: E402
from studio_pipeline.adapters import s3 as s3c  # noqa: E402
from studio_pipeline.adapters import store as _store  # noqa: E402

from tests.fake_api import BUCKET, FakeApi  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_dynamodb():
    """No test may reach a real catalog table — including by accident.

    Autouse rather than opt-in because of `test_every_subcommand_dispatches`,
    which invokes every leaf command in the tree. `studio catalog verify` gets
    far enough to ask whether the table exists, and without this that question
    goes to AWS over the network with the fake credentials above. The table
    itself is NOT created here: a command meeting a table that does not exist
    is a case worth exercising, and the tests that want one build it.
    """
    with mock_dynamodb():
        yield


@pytest.fixture
def fake_api(monkeypatch):
    """An empty library, with the whole adapter stack aimed at it.

    Yields the `FakeApi` so a test can inspect the rows the CLI wrote — which is
    the assertion the old shim could not offer, because there were no rows.
    """
    with mock_s3():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        fake = FakeApi(s3)
        _aim_at(fake, monkeypatch)
        yield fake


def _aim_at(fake, monkeypatch):
    """Route every API call into the fake, and every presigned URL into moto.

    `api.request` is the only function replaced. `api.get`/`post`/`patch`/
    `delete` are thin wrappers over it and are left alone deliberately: they
    carry the parameter-name collision `test_api_client` guards
    (`/api/resolve?path=` against a positional called `path`), and stubbing them
    would put that back out of reach.
    """
    monkeypatch.setattr(_api, "request", fake.request)

    def _fetch(url):
        key = url.removeprefix("memory://")
        try:
            return fake.s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        except Exception as error:  # noqa: BLE001 — moto raises a generated class
            raise _store.StoreError(f"Could not fetch the object ({key}).") from error

    def _put(url, body, headers):
        fake.s3.put_object(Bucket=BUCKET, Key=url.removeprefix("memory://"), Body=body,
                           ContentType=headers.get("Content-Type",
                                                   "application/octet-stream"))

    monkeypatch.setattr(_store, "_fetch", _fetch)
    monkeypatch.setattr(_store, "_put", _put)


# ── the seeded library ──────────────────────────────────────────────────────
#
# Built through the fake's own create paths rather than by poking its dicts, so
# the fixture cannot describe a library the API could not have produced. The one
# exception is `put_file`, which stands in for the bytes arriving — a test that
# wanted to exercise the upload dance would do it itself.

#: The bible the fixture character carries. Shaped like `templates/profile.yaml`
#: with every identity-bearing section present, because `check_profile` refuses
#: one that has drifted off the schema and half these tests go through it.
#:
#: **Handed out with `deepcopy`, never `dict()`.** A shallow copy shares every
#: nested section, so one test editing `rendering.default_style` — which
#: `test_characters` does, by design — rewrote this constant for every test that
#: ran after it. It surfaced as `test_pushing_a_stale_bible_is_refused` failing
#: in a full run and passing alone, which is the shape of a leak rather than a
#: bug in the thing under test.
PROFILE = {
    "schema_version": 2,
    "identity": {"apparent_age": "late 30s", "build": "<one line>",
                 "signature_features": ["<cue>"]},
    "face": {"structure": "<…>", "eyes": "<…>", "hair": "<…>"},
    "body": {"silhouette": "<…>", "posture": "<…>"},
    "wardrobe": {"always_dressed": True, "palette": "<…>"},
    "voice": {"language": "<…>", "accent": "<…>"},
    "rendering": {"default_style": "Realistic", "optional_styles": []},
    "consistency": {"must": ["<…>"], "never": ["<…>"], "drift_modes": []},
    "text_identity_block": "A neutral placeholder identity paragraph.",
}


class Library:
    """Handles onto the seeded library, so a test names things rather than ids.

    Every attribute is a real id. Nothing in the suite may reconstruct one from
    a slug or a path — that habit is what the entity model exists to end, and a
    fixture that offered a shortcut would keep it alive.
    """

    def __init__(self, fake):
        self.fake = fake
        self.s3 = fake.s3


@pytest.fixture
def library(fake_api):
    """One character with a described reference index, one project, one run.

    Deliberately small. The old fixture was a wall of S3 keys because the tree
    *was* the model; the model is rows now, and a test that needs a second
    character or a fifth reference builds it in three lines through the API it
    is testing.
    """
    from studio_pipeline.adapters import entities as E

    lib = Library(fake_api)

    subject_a = E.create_character("subject-a", display_name="Subject A",
                                   profile=copy.deepcopy(PROFILE))
    lib.character = subject_a["id"]
    root = subject_a["root"]
    lib.character_root = root
    reference = fake_api._child(root, "reference")
    lib.reference = reference["id"]

    face = fake_api._create_node(reference["id"], "face", "folder")
    body = fake_api._create_node(reference["id"], "body", "folder")
    lib.face_folder, lib.body_folder = face["id"], body["id"]

    # Deliberately DIFFERENT lengths. `curate dedupe` checks size before it reads
    # a byte, so three same-length markers would make every image a duplicate
    # candidate and the cheap-test-first property untestable. A test that wants
    # two candidates makes them itself.
    lib.face_1 = fake_api.put_file(face["id"], "front-neutral.webp", b"webp-1")["id"]
    lib.face_2 = fake_api.put_file(face["id"], "three-quarter.webp", b"webp-22")["id"]
    lib.body_1 = fake_api.put_file(body["id"], "full-length.webp", b"webp-333")["id"]

    E.add_reference(lib.character, lib.face_1, "face",
                    description="front, neutral", tags=["face"])
    E.add_reference(lib.character, lib.face_2, "face",
                    description="three-quarter", tags=["face", "profile"])
    E.add_reference(lib.character, lib.body_1, "body",
                    description="full length", tags=["body"])
    E.put_default_set(lib.character, [lib.face_1, lib.face_2])

    # A second character, so "the wrong one" is a real possibility in any test
    # about selection, linking or listing.
    subject_b = E.create_character("subject-b", display_name="Subject B",
                                   profile=copy.deepcopy(PROFILE))
    lib.character_b = subject_b["id"]
    b_face = fake_api._create_node(
        fake_api._child(subject_b["root"], "reference")["id"], "face", "folder")
    lib.b_face_1 = fake_api.put_file(b_face["id"], "front.jpeg", b"jpeg-b")["id"]
    E.add_reference(lib.character_b, lib.b_face_1, "face", description="front")

    project = E.create_project("porch-teaser", title="Porch teaser",
                               characters=[lib.character])
    lib.project = project["id"]
    lib.project_root = project["root"]
    pool = fake_api._child(project["root"], "input")
    lib.input_pool = pool["id"]
    lib.input_1 = fake_api.put_file(pool["id"], "street-plate.webp", b"webp-in-1")["id"]
    lib.input_2 = fake_api.put_file(pool["id"], "porch-plate.webp", b"webp-in-2")["id"]
    # A PNG in the pool: the video engines reject `.webp`, so anything standing
    # in for a real seed or handoff frame has to be one.
    lib.input_3 = fake_api.put_file(pool["id"], "porch-plate.png", b"png-in-3")["id"]

    run = E.create_run(project=lib.project, kind="image", engine="nano-banana-pro",
                       model="google/nano-banana-pro", slug="porch-portrait",
                       input={"prompt": "a porch"},
                       bindings={"image_input": [lib.face_1, lib.face_2]},
                       characters=[lib.character])
    lib.run = run["id"]
    signed = E.add_run_output(lib.run, "output-1.jpeg", 9, "image/jpeg")
    _confirm(fake_api, signed, b"jpeg-out")
    E.patch_run(lib.run, status="succeeded", prediction_id="s7k2m9x4qwe1",
                completed="2026-08-19T09:41:02.883740+00:00",
                cost={"currency": "USD", "amount": 0.032})
    lib.run_output = signed["node"]

    return lib


def _confirm(fake, signed: dict, body: bytes) -> None:
    """Put bytes at a signed URL and mark the node confirmed.

    The two-step the API demands — a row promising bytes that are not there is
    the failure the confirm exists to prevent — done by hand because the fixture
    is standing in for a caller that already has the file.
    """
    fake.s3.put_object(Bucket=BUCKET, Key=signed["url"].removeprefix("memory://"),
                       Body=body)
    node = fake.nodes[signed["node"]]
    pending = node.pop("pending", None) or {}
    node["size"] = pending.get("size", len(body))
    node["content_type"] = pending.get("content_type")
    if str(node["content_type"] or "").startswith(("image/", "video/")):
        node["reel"] = fake.lib


@pytest.fixture
def bucket():
    """An empty moto bucket, with no API in front of it.

    For the two maintenance commands that reconcile the bucket against the
    table and therefore have to see both — `catalog gc` and `catalog migrate`.
    Everything else in the suite goes through `fake_api`, because everything
    else in the pipeline goes through the API.
    """
    with mock_s3() as _:
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=s3c.BUCKET)
        yield client


@pytest.fixture
def shared_bucket(bucket):
    """The bucket plus material no row will ever name.

    The pose plates, which sit outside the catalog by design, and a
    `phrasebook/wording.yaml` — which is now HISTORY rather than live data. The
    phrasebook became `TERM#` rows, so nothing writes that key any more; the
    objects prod already holds do not disappear because the model changed, and
    `catalog gc` must go on refusing to collect them.
    """
    for key in ("config/pose/body/standing.png",
                "config/pose/face/three-quarter.png",
                "phrasebook/wording.yaml"):
        bucket.put_object(Bucket=s3c.BUCKET, Key=key, Body=b"png-bytes")
    return bucket


@pytest.fixture
def shared_objects(fake_api):
    """The pose plates: shared material with no node, reached by key.

    The phrasebook used to be here too and is not — it is `TERM#` rows now, so
    there is no document to seed.
    """
    for key in ("config/pose/body/standing.png", "config/pose/face/three-quarter.png"):
        fake_api.put_shared(key, b"png-bytes")
    return fake_api


# ── the catalog table, shared by every suite that needs one ──────────────────
#
# These lived in `test_catalog_seed.py` and `test_catalog_gc.py` imported them,
# which is what `gc`'s own comment wanted — the two must not drift into testing
# different schemas, because an index that drops a row is exactly the corruption
# `gc` must not read as "unreferenced". Importing a fixture across test modules
# makes ruff read every use as a redefinition (F811), so they live here instead:
# same guarantee, and pytest resolves them without an import at all.

_KEY_SCHEMA = [{"AttributeName": "pk", "KeyType": "HASH"},
               {"AttributeName": "sk", "KeyType": "RANGE"}]


def _index(name, hash_key, range_key):
    return {"IndexName": name,
            "KeySchema": [{"AttributeName": hash_key, "KeyType": "HASH"},
                          {"AttributeName": range_key, "KeyType": "RANGE"}],
            "Projection": {"ProjectionType": "ALL"}}


@pytest.fixture
def catalog_table():
    """`studio-<env>-catalog` as the schema describes it.

    `by-recent` is hashed on `reel` rather than on `lib` — the sparse index of
    D5. An entity row and a folder node carry no `reel`, so neither lands in the
    reel's enumeration, which is the folder pollution the re-key fixed on the
    way past.
    """
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName=ddbc.table(),
        BillingMode="PAY_PER_REQUEST",
        KeySchema=_KEY_SCHEMA,
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"}
                              for n in ("pk", "sk", "lib", "path", "reel", "created_at")],
        GlobalSecondaryIndexes=[_index("by-sk", "sk", "pk"),
                                _index("by-path", "lib", "path"),
                                _index("by-recent", "reel", "created_at")],
    )
    return ddb


@pytest.fixture
def legacy_bucket():
    """The pre-entity tree, as `catalog migrate` finds it in production.

    Name paths with a slug in every key, `profile.yaml` as a document, and run
    metadata as three JSON files per run. It exists in exactly one place now —
    here — because the migrator is the only code left that may read it.
    """
    with mock_s3():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=s3c.BUCKET)
        for key, payload in _LEGACY.items():
            s3.put_object(Bucket=s3c.BUCKET, Key=key,
                          Body=payload if isinstance(payload, bytes)
                          else json.dumps(payload).encode())
        yield s3


_LEGACY = {
    "characters/subject-a/profile.yaml": (
        b"schema_version: 2\n"
        b"name: subject-a\n"
        b"display_name: Subject A\n"
        b"fictional: true\n"
        b"identity: {build: '<one line>'}\n"
        b"face: {eyes: '<...>'}\n"
        b"body: {posture: '<...>'}\n"
        b"wardrobe: {always_dressed: true}\n"
        b"voice: {language: '<...>'}\n"
        b"rendering: {default_style: Realistic}\n"
        b"consistency: {must: ['<...>'], never: []}\n"
        b"text_identity_block: A neutral placeholder identity paragraph.\n"
        b"references:\n"
        b"  - file: face/subject-a_face_1.webp\n"
        b"    description: front, neutral\n"
        b"    tags: [face]\n"
        b"  - file: body/subject-a_body_1.webp\n"
        b"    description: full length\n"
        b"    tags: [body]\n"
        b"default_set: [face/subject-a_face_1.webp]\n"
    ),
    "characters/subject-a/reference/face/subject-a_face_1.webp": b"webp-bytes",
    "characters/subject-a/reference/body/subject-a_body_1.webp": b"webp-bytes",
    "characters/subject-a/seed/source.jpg": b"jpg-bytes",
    "projects/porch-teaser/project.json": {
        "name": "porch-teaser", "description": "a teaser",
        "characters": ["subject-a"], "created": "2026-07-11T08:15:02+00:00"},
    "projects/porch-teaser/runs/2026-08-04_21-30-54_wave-porch/request.json": {
        "run_id": "2026-08-04_21-30-54_wave-porch", "project": "porch-teaser",
        "characters": ["subject-a"], "kind": "image", "engine": "nano-banana-pro",
        "model": "google/nano-banana-pro", "created_at": "2026-08-04T21:30:54+00:00",
        "input": {"prompt": "a porch"},
        "bindings": {"image_input":
                     ["characters/subject-a/reference/face/subject-a_face_1.webp"]}},
    "projects/porch-teaser/runs/2026-08-04_21-30-54_wave-porch/result.json": {
        "run_id": "2026-08-04_21-30-54_wave-porch", "status": "succeeded",
        "prediction_id": "s7k2m9x4qwe1",
        "outputs": ["projects/porch-teaser/runs/2026-08-04_21-30-54_wave-porch"
                    "/output/wave-porch.jpeg"]},
    "projects/porch-teaser/runs/2026-08-04_21-30-54_wave-porch/output/wave-porch.jpeg":
        b"jpeg-bytes",
    "projects/porch-teaser/input/porch-teaser_in_1.webp": b"webp-bytes",
    "phrasebook/wording.yaml": (
        b"models:\n"
        b"  kling:\n"
        b"    replicate: kwaivgi/kling-v3-omni-video\n"
        b"    entries:\n"
        b"      - avoid: bare chest\n"
        b"        use: chest\n"
    ),
}


@pytest.fixture
def tmp_image(tmp_path) -> pathlib.Path:
    """One tiny local file, for the commands that upload from disk."""
    path = tmp_path / "plate.png"
    path.write_bytes(b"png-bytes")
    return path
