"""Fixtures for the pipeline suite.

**The moto-keyed shim is gone.** Until the entity model landed, this file
redirected `adapters/store` onto a moto bucket in which a node's id was its S3
key. That was a fiction the API never shared, and it hid the only thing these
tests exist to check: a restructure breaks *wiring*, and a suite that stubs the
store one function at a time asserts nothing about the route, the body or the
field names the CLI actually puts on the wire.

So the seam moved down to `adapters.api.request`, and `tests/support/fake_api.py` answers
it with an in-memory library keyed on real UUIDs. `adapters/entities.py` and
`adapters/store.py` now run for real in every test that touches storage, which
means a route renamed on one side and not the other fails here rather than in
production.

Bytes stay real, on the same moto bucket as before: presigned URLs are
`memory://<blob_key>` and `store._put` / `store._fetch` are pointed at moto, so
`curate dedupe` still hashes genuine bytes and `frames` still runs ffmpeg over a
genuine file.

Fixture subjects are `subject-a` / `subject-b` — generic on purpose even now
that hard rule #1 is env-scoped and a dev subject may be named: a unit suite
should not depend on who the seed fixture happens to be about. The project
is `porch-teaser` — deliberately **not** a character's slug. Entity roots are
children of the library root now, so a project sharing a character's slug would
be a name collision in the tree; the old fixture had `characters/subject-a` and
`projects/subject-a` and could not have shown that.
"""

import copy
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
# Never let a test reach the real API, whatever is in studio/.env. TWO
# mechanisms, and they fail differently on purpose:
#
#   * `STUDIO_REPLICATE_MODE=fake` makes `adapters/replicate.py` answer all six
#     of its functions locally. This is the one that tests are meant to rely on
#     — it replaced a monkeypatch per test file, which a new file could forget.
#   * A dud token, so that if the mode is ever unset the live client gets a 401
#     from Replicate instead of a bill from it.
#
# `_no_outbound_sockets` below is the third and the only one that catches a paid
# call reached indirectly, through a module neither of these knows about.
os.environ["STUDIO_REPLICATE_MODE"] = "fake"
os.environ["REPLICATE_API_TOKEN"] = "r8_test_token"

from moto import mock_dynamodb, mock_s3  # noqa: E402

import studio_pipeline as _pipeline  # noqa: E402
from studio_pipeline import profiles as _profiles  # noqa: E402
from studio_pipeline.adapters import api as _api  # noqa: E402
from studio_pipeline.adapters import auth as _auth  # noqa: E402
from studio_pipeline.adapters import ddb as ddbc  # noqa: E402
from studio_pipeline.adapters import s3 as s3c  # noqa: E402
from studio_pipeline.adapters import store as _store  # noqa: E402
from studio_pipeline.engine import registry as _registry  # noqa: E402

from tests.support.fake_api import BUCKET, FakeApi  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_profiles(tmp_path, monkeypatch):
    """No test may read — or write — the developer's real profile config.

    Autouse and unconditional. The environment variables set above are what the
    suite targets, and with no profile selected they win, so this changes
    nothing about resolution; what it prevents is a `~/.config` on the machine
    running the tests deciding a bucket name, and a test that calls `save` or
    `set_current` writing into it.
    """
    monkeypatch.setattr(_profiles, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(_profiles, "CONFIG_FILE", tmp_path / "config" / "config")
    # The two dotenv files `env_value` falls back to, for the same reason. The
    # environment variables above already shadow them, so this changes nothing
    # in the ordinary case — it is what lets a test assert that a value is
    # supplied by NOTHING, which is impossible while a developer's own
    # `studio/.env` is still on the path.
    monkeypatch.setattr(_pipeline, "ENV_FILE", tmp_path / "dot.env")
    monkeypatch.setattr(_pipeline, "DEV_ENV_FILE", tmp_path / "dev.env")
    # **And the stored session, which this suite used to DELETE.**
    #
    # Not a theoretical leak: `test_every_subcommand_dispatches` walks the whole
    # command tree and invokes every leaf with no arguments, and `studio logout`
    # takes no arguments. It ran for real, against
    # `~/.config/andreas-services/studio/credentials`, and unlinked the
    # developer's session on every full run of the suite. It looked like a token
    # that kept expiring.
    #
    # `test_auth_adapter.py` redirects these in its own fixture, which is why
    # the tests that are ABOUT auth were never the ones that did the damage.
    # Autouse and unconditional here, so no test — present or future — can
    # reach the real file by walking into a command that writes it.
    monkeypatch.setattr(_auth, "CONFIG_DIR", tmp_path / "auth")
    monkeypatch.setattr(_auth, "CREDENTIALS_FILE", tmp_path / "auth" / "credentials")
    # `engine/ledger` writes a second file into that directory — the record of
    # what has already been submitted, so a batch is not paid for twice. It
    # reads `auth.CONFIG_DIR` through the module for this reason, so the line
    # above already redirects it; this asserts that rather than trusting it,
    # because the failure mode is silent and lands in a real developer's config.
    assert (tmp_path / "auth") == _auth.CONFIG_DIR
    # Module state, so it survives a test that selected a profile and did not
    # put it back. `select` also clears the warned-once set.
    _profiles.select(None)
    yield
    _profiles.select(None)


#: Loopback only. moto runs in-process and `FakeApi` is a dict, so a unit test
#: has no legitimate reason to open a socket to anything else — which makes an
#: allowlist the right shape here and a denylist the right shape for the
#: integration suite, where real S3, DynamoDB and Cognito are the point.
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _registry_is_a_copy(monkeypatch, tmp_path):
    """No test may write into `engine/models.json`. It is SOURCE.

    **This is a real incident, not a precaution.** `studio models refresh`
    calls `REG.save_snapshot`, which rewrites the committed registry in place,
    and `test_every_subcommand_dispatches` invokes every leaf command in the
    tree — `models refresh` included. It survived only because the fetch it
    makes first went to `api.replicate.com` over the network with the dud token
    above, got a 401, raised `SchemaError` and hit the `continue`. In other
    words the suite was making live calls to a model provider and depending on
    them FAILING.

    The moment `STUDIO_REPLICATE_MODE=fake` made that call succeed with an
    empty body, the refresh wrote an empty snapshot over every model and
    deleted 391 lines of hand-verified schema. Two board tests went red because
    `panel_format` reads `snapshot.output_format.enum` — which is the good news;
    the file had already been corrupted on the run before.

    Same shape as `_auth.CONFIG_DIR` being redirected further up, and the same
    fix: point the writable path somewhere disposable. Copied rather than
    emptied, because the registry is READ constantly and an empty one would
    fail every test for an unrelated reason.
    """
    copy = tmp_path / "models.json"
    copy.write_bytes(pathlib.Path(_registry.PATH).read_bytes())
    monkeypatch.setattr(_registry, "PATH", str(copy))


@pytest.fixture(autouse=True)
def _no_outbound_sockets(monkeypatch):
    """The backstop `STUDIO_REPLICATE_MODE` cannot be.

    A config switch can only fake the calls that go through the module it
    switches. It says nothing about a paid call added to `adapters/s3`, or
    reached through a dependency, or made by a subprocess — and
    `test_dev_seed`'s source scan says the same of itself in its own docstring.
    This closes that by construction: connecting anywhere but loopback raises,
    so the failure is a stack trace naming the caller rather than an invoice.

    Patched on `socket.socket.connect` rather than on a library, because every
    HTTP client in the tree ends up there — urllib in `adapters/replicate.py`,
    urllib3 under botocore — and patching one of them leaves the others open.
    """
    import socket

    real_connect = socket.socket.connect

    def guarded(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in _LOOPBACK:
            raise RuntimeError(
                f"a test tried to open a socket to {host!r}. Nothing in the "
                "unit suite talks to the network: moto is in-process, the API "
                "is a fake, and Replicate answers from "
                "STUDIO_REPLICATE_MODE=fake. If this is a real integration "
                "test it belongs in tests/integration/.")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded)


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
#: **No `schema_version` here.** This is the record's `profile` map, and the API
#: stamps the version onto the record itself — `clean_profile` refuses a bible
#: carrying it, exactly as it refuses any other key that is not a section. It
#: used to be in this constant, which made the fixture a *document* (the shape a
#: person edits, version included) posing as a profile, and hid the fact that
#: `edit --push` sent the key straight back.
PROFILE = {
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
    E.put_default_set(lib.character, [lib.face_1, lib.face_2],
                      E.get_character(lib.character)["rev"])

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
                       model="google/nano-banana-pro",
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
        client.create_bucket(Bucket=s3c.bucket())
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
        bucket.put_object(Bucket=s3c.bucket(), Key=key, Body=b"png-bytes")
    return bucket


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
def tmp_image(tmp_path) -> pathlib.Path:
    """One tiny local file, for the commands that upload from disk."""
    path = tmp_path / "plate.png"
    path.write_bytes(b"png-bytes")
    return path
