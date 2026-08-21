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

The catalog is seeded from the same moto bucket by `catalog_seed`, so "no row
names it" means what it means in production rather than what a hand-written row
would have made it mean.
"""

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import ddb as ddbc
from studio_pipeline.adapters import s3 as s3c
from studio_pipeline.maintenance import catalog_gc as cg
from studio_pipeline.maintenance import catalog_seed as cs


OWNER_SUB = "11111111-2222-3333-4444-555555555555"

# A key of the shape the API writes today, and one of the shape prod has held
# since before the table existed. Both are `blob_key` values; nothing may tell
# them apart.
MODERN_KEY = "blobs/node-99999999-8888-7777-6666-555555555555"
LEGACY_KEY = "characters/subject-a/reference/face/subject-a_1.webp"


def _seeded(s3, ddb):
    """The bucket recorded as rows, exactly as `studio catalog seed` records it."""
    plan = cs.build_plan(s3)
    cs.phase_seed(ddb, plan, owner_sub=OWNER_SUB, library_name="Studio", apply=True)
    return plan


def _survey(s3, ddb):
    return cg.survey(s3, cg.referenced_keys(ddb))


def _put(s3, key, body=b"png-bytes"):
    s3.put_object(Bucket=s3c.BUCKET, Key=key, Body=body)


# ── what must never be collected ────────────────────────────────────────────

def test_a_legacy_blob_key_target_is_never_listed(media_bucket, catalog_table):
    """The test that matters most: a row's key is live whatever its shape.

    `characters/<slug>/…` and `projects/<slug>/…` keys were written years before
    the catalog and are what most rows in prod still name. A `gc` that decided
    garbage by prefix — "anything not under `blobs/`" — would propose the whole
    library on its first run.
    """
    _seeded(media_bucket, catalog_table)
    found = _survey(media_bucket, catalog_table)

    assert LEGACY_KEY in found["referenced"]
    assert LEGACY_KEY not in found["orphans"]
    # Not one of them, not just this one.
    assert not [k for k in found["orphans"] if k.startswith("characters/")]
    assert not [k for k in found["orphans"] if k.startswith("projects/")]


def test_a_config_object_is_never_listed(shared_objects, catalog_table):
    """`config/pose/` plates are the framing guides a reference shoot binds.

    Nothing records them — `catalog_seed` gives them no node — so the only thing
    keeping them is that they are outside the allowlist.
    """
    _seeded(shared_objects, catalog_table)
    plate = "config/pose/body/standing.png"
    found = _survey(shared_objects, catalog_table)

    assert plate not in cg.referenced_keys(catalog_table)   # no row names it
    assert plate in found["shared"]
    assert plate not in found["orphans"]


def test_a_phrasebook_object_is_never_listed(shared_objects, catalog_table):
    _seeded(shared_objects, catalog_table)
    found = _survey(shared_objects, catalog_table)

    assert "phrasebook/wording.yaml" not in cg.referenced_keys(catalog_table)
    assert "phrasebook/wording.yaml" in found["shared"]
    assert not [k for k in found["orphans"] if k.startswith("phrasebook/")]


def test_an_unknown_prefix_is_refused_rather_than_collected(media_bucket, catalog_table):
    """The allowlist's whole point: a fourth kind of shared material is safe.

    A denylist of `config/` + `phrasebook/` would pass the two tests above and
    delete this the day someone adds one.
    """
    _seeded(media_bucket, catalog_table)
    _put(media_bucket, "lookbook/2026/plate.png")
    found = _survey(media_bucket, catalog_table)

    assert "lookbook/2026/plate.png" in found["outside"]
    assert found["orphans"] == []


def test_a_folder_marker_is_never_listed(media_bucket, catalog_table):
    """No row names a marker, and deleting one destroys an empty folder."""
    _seeded(media_bucket, catalog_table)
    _put(media_bucket, "projects/subject-a/empty/", b"")
    found = _survey(media_bucket, catalog_table)

    assert found["markers"] == ["projects/subject-a/empty/"]
    assert found["orphans"] == []


def test_a_reference_from_any_row_counts(media_bucket, catalog_table):
    """Not scoped to a library, an `sk`, or the tree the key sits in.

    A blob referenced from somewhere this command was not thinking about is
    still referenced. Every ambiguity here has to resolve towards keeping it.
    """
    _put(media_bucket, MODERN_KEY)
    catalog_table.put_item(
        TableName=ddbc.TABLE,
        Item=ddbc.to_item({"pk": "NODE#node-elsewhere", "sk": "META",
                           "lib": "lib-some-other-library", "kind": "file",
                           "blob_key": MODERN_KEY}))

    assert MODERN_KEY in cg.referenced_keys(catalog_table)
    assert MODERN_KEY not in _survey(media_bucket, catalog_table)["orphans"]


# ── what is collected ───────────────────────────────────────────────────────

def test_a_healthy_bucket_reports_zero(shared_objects, catalog_table):
    """Every object either has a row or is deliberately outside the catalog."""
    _seeded(shared_objects, catalog_table)
    found = _survey(shared_objects, catalog_table)

    assert found["orphans"] == []
    assert cg.orphan_bytes(found) == 0
    assert len(found["shared"]) == 3            # two pose plates + the phrasebook


@pytest.mark.parametrize("key", [
    MODERN_KEY,                                          # a confirm that never came
    "projects/subject-a/input/subject-a_9.webp",         # a delete that half ran
])
def test_a_seeded_orphan_is_found(media_bucket, catalog_table, key):
    """Both shapes of residue, because `delete_node` returns keys of both."""
    _seeded(media_bucket, catalog_table)
    _put(media_bucket, key, b"orphan-bytes")

    found = _survey(media_bucket, catalog_table)
    assert found["orphans"] == [key]
    assert cg.orphan_bytes(found) == len(b"orphan-bytes")


def test_a_row_whose_blob_is_gone_is_not_an_orphan(media_bucket, catalog_table):
    """The other direction is `catalog verify`'s, and this command ignores it."""
    _seeded(media_bucket, catalog_table)
    media_bucket.delete_object(Bucket=s3c.BUCKET, Key=LEGACY_KEY)

    assert _survey(media_bucket, catalog_table)["orphans"] == []


# ── deleting ────────────────────────────────────────────────────────────────

def test_a_delete_never_names_a_version(media_bucket):
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


def test_more_keys_than_one_batch_are_all_deleted(media_bucket, monkeypatch):
    """`DeleteObjects` takes a thousand; a bucket's residue can exceed one page."""
    monkeypatch.setattr(cg, "BATCH", 2)
    keys = [f"blobs/node-{n}" for n in range(5)]
    for key in keys:
        _put(media_bucket, key)

    res = cg.collect(media_bucket, keys)
    assert sorted(res["deleted"]) == sorted(keys)
    assert res["failed"] == []
    assert "Contents" not in media_bucket.list_objects_v2(Bucket=s3c.BUCKET,
                                                          Prefix="blobs/")


# ── the CLI, and the two invocations ────────────────────────────────────────

@pytest.fixture
def journalled(tmp_path, monkeypatch):
    """The journal, redirected out of `studio/local/migrations/`."""
    monkeypatch.setattr(cs, "JOURNAL_DIR", str(tmp_path))
    return tmp_path


def _run(*args):
    return CliRunner().invoke(cli.main, ["catalog", "gc", *args])


def test_a_dry_run_lists_the_orphan_and_deletes_nothing(media_bucket, catalog_table,
                                                        journalled):
    _seeded(media_bucket, catalog_table)
    _put(media_bucket, MODERN_KEY)

    result = _run()
    assert result.exit_code == 0, result.output
    assert MODERN_KEY in result.output
    assert "nothing deleted" in result.output
    assert media_bucket.head_object(Bucket=s3c.BUCKET, Key=MODERN_KEY)


def test_apply_deletes_what_the_dry_run_journalled(media_bucket, catalog_table,
                                                   journalled):
    _seeded(media_bucket, catalog_table)
    _put(media_bucket, MODERN_KEY)

    assert _run().exit_code == 0
    applied = _run("--apply")
    assert applied.exit_code == 0, applied.output

    with pytest.raises(Exception):
        media_bucket.head_object(Bucket=s3c.BUCKET, Key=MODERN_KEY)
    # And nothing else went with it.
    assert media_bucket.head_object(Bucket=s3c.BUCKET, Key=LEGACY_KEY)


def test_apply_leaves_an_orphan_the_dry_run_never_showed(media_bucket, catalog_table,
                                                         journalled):
    """The reason the journal is the input rather than a log.

    A person read a report and said yes to it. Anything orphaned after that
    moment was not in what they read, so it survives to be shown in the next
    one.
    """
    _seeded(media_bucket, catalog_table)
    _put(media_bucket, MODERN_KEY)
    assert _run().exit_code == 0

    latecomer = "projects/subject-a/input/subject-a_9.webp"
    _put(media_bucket, latecomer)

    applied = _run("--apply")
    assert applied.exit_code == 0, applied.output
    assert media_bucket.head_object(Bucket=s3c.BUCKET, Key=latecomer)
    assert "unconfirmed    1" in " ".join(applied.output.split("  "))


def test_apply_refuses_without_a_dry_run(media_bucket, catalog_table, journalled):
    """The dangerous direction is the one that takes two invocations."""
    _seeded(media_bucket, catalog_table)
    _put(media_bucket, MODERN_KEY)

    result = _run("--apply")
    assert result.exit_code == 1
    assert "records no dry run" in result.output
    assert media_bucket.head_object(Bucket=s3c.BUCKET, Key=MODERN_KEY)


def test_it_refuses_when_no_row_names_a_blob(media_bucket, catalog_table, journalled):
    """The input that would otherwise propose the entire bucket.

    An unseeded table, or the wrong one in `STUDIO_CATALOG_TABLE`, makes every
    object look unreferenced. There is no report worth printing from that.
    """
    result = _run()
    assert result.exit_code == 1
    assert ddbc.TABLE in result.output
    assert "names a blob" in result.output


def test_it_refuses_when_the_table_does_not_exist(media_bucket, journalled):
    result = _run()
    assert result.exit_code == 1
    assert ddbc.TABLE in result.output
