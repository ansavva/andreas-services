"""`studio catalog gc` — what it collects, and everything it must not.

Almost every test here is a test of the second kind, because the failure mode is
not "an orphan was missed" but "media was deleted". The first three are the ones
the command exists to be safe about:

* a **legacy `characters/…` / `projects/…` key that a row names** is live, and
  is the case a prefix test would destroy — prod holds thousands of them;
* a **`config/`** object, which no row will ever name because the pose plates a
  reference shoot binds sit outside the catalog by design;
* a **`phrasebook/`** object, unreferenced for the same reason.

The fourth is the one that keeps the other two true tomorrow: an object under a
prefix nobody has heard of is refused as well, because the gate is an allowlist
of what MAY be collected rather than a list of what may not.

The rows are written out here rather than produced by another command, and that
is a change worth stating. They used to come from `catalog_seed`, which
inventoried a bucket into a table — so "no row names it" meant what it meant in
production because the same code put the rows there. That command is gone: every
library has rows now, and what replaced it (`catalog migrate`) raises ENTITY rows
over a library whose nodes already exist. It writes no `blob_key` at all, so it
cannot stand in.

`_rows` below is therefore the schema, spelled out. It is deliberately literal —
a `blob_key` of each shape prod actually holds, and nothing derived — because
the property under test is "this key is named by a row", and a helper that
derived the key from the object would make every assertion circular.
"""

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.maintenance import catalog_gc as cg
from studio_pipeline.maintenance import catalog_migrate as cm


LIB = "lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44"
CHAR = "char-9f3c1e57-2a44-4d81-b6e0-77c21f8a4d15"

# THREE shapes of `blob_key`, all live in prod at once, and nothing may tell
# them apart:
#
#   ENTITY_KEY  what the API writes today — `<owner kind>/<owner id>/<node id>`
#   MODERN_KEY  what it wrote before keys carried an owner
#   LEGACY_KEY  a name path, from before the table existed
#
# The third is the one a prefix-based rule would destroy, and it is why the gate
# is an allowlist of first segments rather than anything that reads further.
ENTITY_KEY = f"characters/{CHAR}/node-9a06d3c5-7b81-4f09-92ea-4c15b8d70f3e.webp"
MODERN_KEY = "blobs/node-99999999-8888-7777-6666-555555555555"
LEGACY_KEY = "characters/subject-a/reference/face/subject-a_1.webp"

#: Objects every test starts from: one of each key shape, each named by a row.
SEEDED = (ENTITY_KEY, MODERN_KEY, LEGACY_KEY)

#: An object no row names — residue from a confirm that never came. Collectable,
#: and the only thing in these tests that is.
ORPHAN_KEY = "blobs/node-00000000-0000-0000-0000-000000000000"


def _rows(ddb, *blob_keys):
    """Write one file-node row per key, plus the library and a membership row.

    The whole schema this command reads: `referenced_keys` scans for `blob_key`
    and nothing else, so a row that carries one is a row that keeps an object
    alive, whatever its `pk` or its library.
    """
    ddb.put_item(TableName=ddbc.table(),
                 Item=ddbc.to_item({"pk": f"LIB#{LIB}", "sk": "META",
                                    "name": "Studio", "root_node": "node-root"}))
    for n, key in enumerate(blob_keys):
        ddb.put_item(TableName=ddbc.table(), Item=ddbc.to_item({
            "pk": f"NODE#node-seeded-{n}", "sk": "META",
            "node_id": f"node-seeded-{n}", "lib": LIB, "kind": "file",
            "name": key.rsplit("/", 1)[-1], "blob_key": key,
            "size": 9, "content_type": "image/webp",
            # The sparse reel key (D5). Present here because these stand in for
            # images; a row without it is simply not in `by-recent`, which is
            # the pollution the re-key fixed. `referenced_keys` scans rather
            # than querying an index precisely so that absence is invisible to
            # it — see its docstring.
            "reel": LIB,
        }))


def _seeded(s3, ddb, *extra):
    """The bucket and the table agreeing: every object named by a row."""
    for key in SEEDED:
        _put(s3, key)
    _rows(ddb, *SEEDED, *extra)


def _survey(s3, ddb):
    return cg.survey(s3, cg.referenced_keys(ddb))


def _put(s3, key, body=b"png-bytes"):
    s3.put_object(Bucket=s3c.BUCKET, Key=key, Body=body)


# ── what must never be collected ────────────────────────────────────────────

def test_a_legacy_blob_key_target_is_never_listed(bucket, catalog_table):
    """The test that matters most: a row's key is live whatever its shape.

    `characters/<slug>/…` and `projects/<slug>/…` keys were written years before
    the catalog and are what most rows in prod still name. A `gc` that decided
    garbage by prefix — "anything not under `blobs/`" — would propose the whole
    library on its first run.
    """
    _seeded(bucket, catalog_table)
    found = _survey(bucket, catalog_table)

    assert LEGACY_KEY in found["referenced"]
    assert LEGACY_KEY not in found["orphans"]
    # Not one of them, not just this one.
    assert not [k for k in found["orphans"] if k.startswith("characters/")]
    assert not [k for k in found["orphans"] if k.startswith("projects/")]


def test_a_config_object_is_never_listed(shared_bucket, catalog_table):
    """`config/pose/` plates are the framing guides a reference shoot binds.

    Nothing records them — `catalog_seed` gives them no node — so the only thing
    keeping them is that they are outside the allowlist.
    """
    _seeded(shared_bucket, catalog_table)
    plate = "config/pose/body/standing.png"
    found = _survey(shared_bucket, catalog_table)

    assert plate not in cg.referenced_keys(catalog_table)   # no row names it
    assert plate in found["shared"]
    assert plate not in found["orphans"]


def test_a_phrasebook_object_is_never_listed(shared_bucket, catalog_table):
    _seeded(shared_bucket, catalog_table)
    found = _survey(shared_bucket, catalog_table)

    assert "phrasebook/wording.yaml" not in cg.referenced_keys(catalog_table)
    assert "phrasebook/wording.yaml" in found["shared"]
    assert not [k for k in found["orphans"] if k.startswith("phrasebook/")]


def test_an_unknown_prefix_is_refused_rather_than_collected(bucket, catalog_table):
    """The allowlist's whole point: a fourth kind of shared material is safe.

    A denylist of `config/` + `phrasebook/` would pass the two tests above and
    delete this the day someone adds one.
    """
    _seeded(bucket, catalog_table)
    _put(bucket, "lookbook/2026/plate.png")
    found = _survey(bucket, catalog_table)

    assert "lookbook/2026/plate.png" in found["outside"]
    assert found["orphans"] == []


def test_a_folder_marker_is_never_listed(bucket, catalog_table):
    """No row names a marker, and deleting one destroys an empty folder."""
    _seeded(bucket, catalog_table)
    _put(bucket, "projects/subject-a/empty/", b"")
    found = _survey(bucket, catalog_table)

    assert found["markers"] == ["projects/subject-a/empty/"]
    assert found["orphans"] == []


def test_a_reference_from_any_row_counts(bucket, catalog_table):
    """Not scoped to a library, an `sk`, or the tree the key sits in.

    A blob referenced from somewhere this command was not thinking about is
    still referenced. Every ambiguity here has to resolve towards keeping it.
    """
    _put(bucket, MODERN_KEY)
    catalog_table.put_item(
        TableName=ddbc.table(),
        Item=ddbc.to_item({"pk": "NODE#node-elsewhere", "sk": "META",
                           "lib": "lib-some-other-library", "kind": "file",
                           "blob_key": MODERN_KEY}))

    assert MODERN_KEY in cg.referenced_keys(catalog_table)
    assert MODERN_KEY not in _survey(bucket, catalog_table)["orphans"]


# ── what is collected ───────────────────────────────────────────────────────

def test_a_healthy_bucket_reports_zero(shared_bucket, catalog_table):
    """Every object either has a row or is deliberately outside the catalog."""
    _seeded(shared_bucket, catalog_table)
    found = _survey(shared_bucket, catalog_table)

    assert found["orphans"] == []
    assert cg.orphan_bytes(found) == 0
    assert len(found["shared"]) == 3            # two pose plates + the phrasebook


@pytest.mark.parametrize("key", [
    # A confirm that never came, under each key shape the API has ever written.
    "blobs/node-00000000-0000-0000-0000-000000000000",
    "projects/proj-4a10b8d2-5c93-47ae-8f61-0d51e6b7c2a9/"
    "node-00000000-0000-0000-0000-000000000001.png",
    "libraries/lib-6c2f4a91-8e3d-4b17-9f02-1a5c7d3e9b44/"
    "node-00000000-0000-0000-0000-000000000002.png",
    # A delete that half ran, under a name path from before the table existed.
    "projects/porch-teaser/input/porch-teaser_in_9.webp",
])
def test_a_seeded_orphan_is_found(bucket, catalog_table, key):
    """Every shape of residue, because `delete_node` returns keys of all of them.

    Three eras of `blob_key` are live in one bucket — `blobs/`, the id-prefixed
    `<owner kind>/<owner id>/`, and the name paths that predate the table — and
    an unreferenced object is collectable under all three. The allowlist is
    about the FIRST segment for exactly this reason: a rule that read further
    would have to know which era a key came from.
    """
    _seeded(bucket, catalog_table)
    _put(bucket, key, b"orphan-bytes")

    found = _survey(bucket, catalog_table)
    assert found["orphans"] == [key]
    assert cg.orphan_bytes(found) == len(b"orphan-bytes")


def test_a_row_whose_blob_is_gone_is_not_an_orphan(bucket, catalog_table):
    """The other direction is `catalog verify`'s, and this command ignores it."""
    _seeded(bucket, catalog_table)
    bucket.delete_object(Bucket=s3c.BUCKET, Key=LEGACY_KEY)

    assert _survey(bucket, catalog_table)["orphans"] == []


# ── deleting ────────────────────────────────────────────────────────────────

def test_a_delete_never_names_a_version(bucket):
    """A `VersionId` is what turns a recoverable tombstone into a real removal."""
    sent = []

    class _Spy:
        def delete_objects(self, **kwargs):
            sent.append(kwargs)
            return {"Deleted": [{"Key": o["Key"]}
                                for o in kwargs["Delete"]["Objects"]]}

    res = cg.collect(_Spy(), [MODERN_KEY])
    assert res["deleted"] == [MODERN_KEY]
    assert sent[0]["Delete"]["Objects"] == [{"Key": MODERN_KEY}]


def test_more_keys_than_one_batch_are_all_deleted(bucket, monkeypatch):
    """`DeleteObjects` takes a thousand; a bucket's residue can exceed one page."""
    monkeypatch.setattr(cg, "BATCH", 2)
    keys = [f"blobs/node-{n}" for n in range(5)]
    for key in keys:
        _put(bucket, key)

    res = cg.collect(bucket, keys)
    assert sorted(res["deleted"]) == sorted(keys)
    assert res["failed"] == []
    assert "Contents" not in bucket.list_objects_v2(Bucket=s3c.BUCKET,
                                                          Prefix="blobs/")


# ── the CLI, and the two invocations ────────────────────────────────────────

@pytest.fixture
def journalled(tmp_path, monkeypatch):
    """The journal, redirected out of `studio/local/migrations/`.

    Patched on `catalog_migrate`, which is where the constant lives now that the
    catalog seed is gone — `gc` imports the journal helpers from it, so the two
    commands go on sharing one journal directory and one file format.
    """
    monkeypatch.setattr(cm, "JOURNAL_DIR", str(tmp_path))
    monkeypatch.setattr(cg, "JOURNAL_DIR", str(tmp_path), raising=False)
    return tmp_path


def _run(*args):
    return CliRunner().invoke(cli.main, ["catalog", "gc", *args])


def test_a_dry_run_lists_the_orphan_and_deletes_nothing(bucket, catalog_table,
                                                        journalled):
    _seeded(bucket, catalog_table)
    _put(bucket, ORPHAN_KEY)

    result = _run()
    assert result.exit_code == 0, result.output
    assert ORPHAN_KEY in result.output
    assert "nothing deleted" in result.output
    assert bucket.head_object(Bucket=s3c.BUCKET, Key=ORPHAN_KEY)


def test_apply_deletes_what_the_dry_run_journalled(bucket, catalog_table,
                                                   journalled):
    _seeded(bucket, catalog_table)
    _put(bucket, ORPHAN_KEY)

    assert _run().exit_code == 0
    applied = _run("--apply")
    assert applied.exit_code == 0, applied.output

    with pytest.raises(Exception):
        bucket.head_object(Bucket=s3c.BUCKET, Key=ORPHAN_KEY)
    # And nothing else went with it.
    assert bucket.head_object(Bucket=s3c.BUCKET, Key=LEGACY_KEY)


def test_apply_leaves_an_orphan_the_dry_run_never_showed(bucket, catalog_table,
                                                         journalled):
    """The reason the journal is the input rather than a log.

    A person read a report and said yes to it. Anything orphaned after that
    moment was not in what they read, so it survives to be shown in the next
    one.
    """
    _seeded(bucket, catalog_table)
    _put(bucket, ORPHAN_KEY)
    assert _run().exit_code == 0

    latecomer = "projects/subject-a/input/subject-a_9.webp"
    _put(bucket, latecomer)

    applied = _run("--apply")
    assert applied.exit_code == 0, applied.output
    assert bucket.head_object(Bucket=s3c.BUCKET, Key=latecomer)
    assert "unconfirmed    1" in " ".join(applied.output.split("  "))


def test_apply_refuses_without_a_dry_run(bucket, catalog_table, journalled):
    """The dangerous direction is the one that takes two invocations."""
    _seeded(bucket, catalog_table)
    _put(bucket, ORPHAN_KEY)

    result = _run("--apply")
    assert result.exit_code == 1
    assert "records no dry run" in result.output
    assert bucket.head_object(Bucket=s3c.BUCKET, Key=ORPHAN_KEY)


def test_it_refuses_when_no_row_names_a_blob(bucket, catalog_table, journalled):
    """The input that would otherwise propose the entire bucket.

    An unseeded table, or the wrong one in `STUDIO_CATALOG_TABLE`, makes every
    object look unreferenced. There is no report worth printing from that.
    """
    result = _run()
    assert result.exit_code == 1
    assert ddbc.table() in result.output
    assert "names a blob" in result.output


def test_it_refuses_when_the_table_does_not_exist(bucket, journalled):
    result = _run()
    assert result.exit_code == 1
    assert ddbc.table() in result.output


def test_gc_refuses_when_the_bucket_is_unset(monkeypatch):
    """**`STUDIO_S3_BUCKET` used to default to the production bucket.**

    Three maintenance commands read it and one of them deletes objects, so a
    shell that had not loaded `studio/.env` would dry-run against prod, list
    prod's orphans, and let an `--apply` remove them. There is no default now,
    and unset is a refusal rather than a redirection.
    """
    import importlib

    from studio_pipeline.adapters import s3 as s3c

    # Reloaded with the variable ABSENT, which is the only way to see the
    # default. Patching `BUCKET` to "" tests the refusal and not the fallback —
    # the first version of this test did exactly that, and restoring the prod
    # default left it green.
    monkeypatch.delenv("STUDIO_S3_BUCKET", raising=False)
    reloaded = importlib.reload(s3c)
    try:
        assert not reloaded.BUCKET, (
            f"STUDIO_S3_BUCKET fell back to {reloaded.BUCKET!r}. There is no default "
            "on purpose — three maintenance commands read it and one deletes."
        )
        with pytest.raises(SystemExit):
            reloaded.bucket()
    finally:
        monkeypatch.setenv("STUDIO_S3_BUCKET", "studio-prod-media-us-east-1")
        importlib.reload(s3c)
