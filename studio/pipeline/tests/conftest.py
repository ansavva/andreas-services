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
os.environ["STUDIO_S3_BUCKET"] = "studio-prod-media-us-east-1"
os.environ["STUDIO_S3_PREFIX"] = ""
# Never let a test reach the real API, whatever is in studio/.env.
os.environ["REPLICATE_API_TOKEN"] = "r8_test_token"

from moto import mock_dynamodb, mock_s3

from studio_pipeline.adapters import api as _api

BUCKET = "studio-prod-media-us-east-1"


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
def media_bucket(monkeypatch):
    """A moto S3 bucket seeded with the miniature tree, with `store` aimed at it.

    **The shim is the point of this fixture now, not a detail.** `adapters/store`
    reaches the API, and these tests are not about the transport — they are about
    what `shoot`, `board` and `curate` *do*: which references they pick, in what
    order, what they write and where. Pointing `store` at the same moto bucket
    keeps every one of those assertions meaning exactly what it meant before the
    migration, against the same fixture tree.

    What is deliberately *not* covered here: that `store` can talk to the API at
    all. `test_store_adapter` and `test_api_client` own that, and the first real
    end-to-end exercise is the integration suite. Splitting it this way is what
    stops a moto shim from quietly becoming the only thing that is ever tested —
    which is the trap that let `store.resolve` ship broken.
    """
    with mock_s3():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        for key, body in FIXTURE_OBJECTS.items():
            s3.put_object(Bucket=BUCKET, Key=key, Body=body)
        _aim_store_at(s3, monkeypatch)
        yield s3


def _aim_store_at(s3, monkeypatch):
    """Redirect `adapters/store` onto a moto bucket, one operation at a time.

    A node's "id" here is its key. That is a fiction the real API does not share,
    and it is safe only because nothing in these tests reads an id for anything
    but handing it straight back — asserted by the fact that no test inspects
    one.
    """
    import pathlib

    from studio_pipeline.adapters import store as _store

    def _head(path):
        return s3.head_object(Bucket=BUCKET, Key=path)

    def _folder_node(clean):
        """A folder node if anything lives under this prefix, else None.

        **The real API resolves a folder; S3 has none to resolve.** `_resolve`
        used to `head_object` and give up, so every caller that named a folder
        got a 404 from the fixture and a node from production. It went unnoticed
        while nothing resolved one — `store.folder` is stubbed and `store.files`
        goes straight to a listing. `character rename` resolves the character's
        own folder, and that is what found it.
        """
        prefix = clean + "/" if clean else ""
        listed = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, Delimiter="/", MaxKeys=1)
        if not listed.get("Contents") and not listed.get("CommonPrefixes"):
            return None
        return {"id": clean, "name": clean.rsplit("/", 1)[-1], "kind": "folder"}

    def _resolve(path):
        clean = path.strip("/")
        try:
            meta = _head(clean)
        except Exception as error:  # noqa: BLE001
            node = _folder_node(clean)
            if node is not None:
                return node
            raise _api.NotFound(f"No such object: {clean}", 404) from error
        return {
            "id": clean,
            "name": clean.rsplit("/", 1)[-1],
            "size": meta["ContentLength"],
            "kind": "file",
            # **`updated_at` is not optional here.** It is the optimistic-concurrency
            # token `characters.profile` replaced the S3 ETag with, and the check
            # that uses it is written `if recorded and current and ...` — so a shim
            # that omitted it did not fail, it turned the guard OFF, and
            # `test_pushing_a_stale_bible_is_refused` passed while asserting
            # nothing. Caught by that test failing the other way once the real code
            # started reading the field.
            #
            # `LastModified` has one-second resolution where the catalog's is
            # microseconds. That is a fixture being coarser than the thing it
            # stands in for, not a behaviour difference: nothing asks whether two
            # writes a millisecond apart differ, only whether a recorded value
            # still matches.
            "updated_at": meta["LastModified"].isoformat(),
        }

    def _children(path):
        """Files AND folders, as `GET /api/nodes?parent=` returns them.

        The delimiter is what makes folders appear: `list_objects_v2` reports
        them as `CommonPrefixes`, separately from the objects, where the catalog
        returns both kinds in one list distinguished by `kind`. Returning only
        the files here made this fixture agree with a bug — `paths.list_projects`
        would have seen an empty tree and every scene test would have passed by
        asserting on nothing.
        """
        prefix = path.strip("/") + "/" if path.strip("/") else ""
        found = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix, Delimiter="/")
        contents = found.get("Contents", [])
        folders = found.get("CommonPrefixes", []) or []
        if not contents and not folders:
            raise _api.NotFound(f"No such object: {path}", 404)
        entries = [
            {
                "id": item["Key"],
                "name": item["Key"][len(prefix):],
                "kind": "file",
                "size": item["Size"],
            }
            for item in contents
            if not item["Key"].endswith("/") and "/" not in item["Key"][len(prefix):]
        ]
        entries += [
            {
                "id": cp["Prefix"].rstrip("/"),
                "name": cp["Prefix"][len(prefix):].rstrip("/"),
                "kind": "folder",
            }
            for cp in folders
            if cp["Prefix"][len(prefix):].rstrip("/")
        ]
        return entries

    def _read(path):
        """Bytes, or `api.NotFound` — the failure the real store raises.

        moto answers a missing key with botocore's `NoSuchKey`, which no caller
        of `store` catches. `read_json` returns None on `api.NotFound` and lets
        anything else through, so a shim that leaked `NoSuchKey` would turn
        "this run has no result.json yet" into a traceback in the tests and
        nowhere else.
        """
        clean = path.strip("/")
        try:
            return s3.get_object(Bucket=BUCKET, Key=clean)["Body"].read()
        except Exception as error:  # noqa: BLE001 - moto raises a generated class
            raise _api.NotFound(f"No such object: {clean}", 404) from error

    def _download(path, destination):
        destination = pathlib.Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_read(path))
        return destination

    def _write(path, body, *, content_type):
        s3.put_object(Bucket=BUCKET, Key=path.strip("/"), Body=body, ContentType=content_type)
        return {"id": path.strip("/"), "size": len(body), "content_type": content_type}

    def _upload(path, source, *, content_type):
        return _write(path, pathlib.Path(source).read_bytes(), content_type=content_type)

    def _copy(source, destination, *, content_type):
        return _write(destination, _read(source), content_type=content_type)

    def _folder(path):
        """A no-op that answers, because S3 has no folders to create.

        `store.folder` exists so a run can be told to exist before a document is
        written inside it — a catalog row that S3 never needed, because a key
        with slashes in it produced the appearance of a folder. Against moto the
        honest shim is therefore to report success without writing anything: the
        folder is there the moment its first object is.

        The id is the path, as everywhere else in this shim.
        """
        clean = path.strip("/")
        return {"id": clean, "name": clean.rsplit("/", 1)[-1], "kind": "folder"}

    def _exists(path):
        """`_resolve`, not `_head` — a folder is a node and answers here too.

        It was a bare head, which is every object and no folder. `character
        rename` asks whether the destination character exists, and against a
        head that question answered "no" for a character that plainly did,
        letting the rename run onto a live record.
        """
        try:
            _resolve(path)
        except _api.NotFound:
            return False
        return True

    def _size(path):
        return _resolve(path)["size"]

    def _presign(path, *, disposition="inline"):
        params = {"Bucket": BUCKET, "Key": path.strip("/")}
        if disposition == "attachment":
            params["ResponseContentDisposition"] = "attachment"
        return s3.generate_presigned_url("get_object", Params=params, ExpiresIn=3600)

    def _move_or_rename(route, payload):
        """`PATCH /api/nodes/<id>` against moto, where a node id IS its key.

        **A copy and a delete, standing in for a row update.** That is the one
        place this shim is structurally unlike the thing it imitates: production
        renames a node and the blob never moves, which is the whole point of
        #306. So the tests built on this fixture can assert the RESULT of a
        rename — where the file ended up, which records followed — and cannot
        assert that no object was written. `test_curate` does that separately,
        against `api` itself.
        """
        src = route.removeprefix("/api/nodes/")
        if "name" in payload:
            head, _, _base = src.rpartition("/")
            dst = f"{head}/{payload['name']}" if head else payload["name"]
        else:
            dst = f"{payload['parent'].rstrip('/')}/{src.rsplit('/', 1)[-1]}"
        if dst == src:
            return {"id": src}
        # A folder id is its prefix, so renaming one moves everything beneath it.
        moved = False
        for item in s3.list_objects_v2(Bucket=BUCKET, Prefix=src).get("Contents", []):
            key = item["Key"]
            if key != src and not key.startswith(src + "/"):
                continue
            target = dst + key[len(src):]
            s3.copy_object(Bucket=BUCKET, CopySource={"Bucket": BUCKET, "Key": key},
                           Key=target, MetadataDirective="COPY")
            s3.delete_object(Bucket=BUCKET, Key=key)
            moved = True
        if not moved:
            raise _api.NotFound(f"No such node: {src}", 404)
        return {"id": dst}

    def _delete(route, **_params):
        node = route.removeprefix("/api/nodes/")
        for item in s3.list_objects_v2(Bucket=BUCKET, Prefix=node).get("Contents", []):
            if item["Key"] == node or item["Key"].startswith(node + "/"):
                s3.delete_object(Bucket=BUCKET, Key=item["Key"])
        return {"id": node, "deleted": 1}

    monkeypatch.setattr(_api, "patch", _move_or_rename)
    monkeypatch.setattr(_api, "delete", _delete)
    def _shared_read(key):
        """Shared material, addressed by key.

        Identical to `_read` here and NOT the same thing: the phrasebook and the
        pose plates have no catalog node, so the real store reaches them over
        `GET /api/asset` rather than resolving a path. This fixture's ids are
        keys, which collapses the difference — the tests that care that the two
        routes stay apart stub `api` itself (`test_paths`, `test_phrasebook`).
        """
        return _read(key)

    def _shared_presign(key, *, disposition="inline"):
        return _presign(key, disposition=disposition)

    for name, value in [
        ("resolve", _resolve), ("children", _children), ("read", _read),
        ("download", _download), ("write", _write), ("upload", _upload),
        ("copy", _copy), ("exists", _exists), ("size", _size), ("presign", _presign),
        ("folder", _folder), ("shared_read", _shared_read),
        ("shared_presign", _shared_presign),
    ]:
        monkeypatch.setattr(_store, name, value)
