"""Sweeps: the row that makes a delete recoverable without scanning the bucket.

**What these tests are actually defending.** Rows are deleted before bytes, so
an interruption between the two leaves an object no reader can reach. That was
never in doubt and is not what changed. What changed is that the leftover is now
*addressed* — a `SWEEP#` row naming the keys, written before the rows go — where
it used to be *searched for*, by listing every object in the bucket and scanning
every row in the table and subtracting. That search was `studio catalog gc`: a
CLI command with its own boto3 clients, a journal, a two-phase dry run, and a
guard against the one input that turned it into a bucket wipe. All of it is
deleted, and these tests are what stand in its place.

Named for the failure each catches, per `tests/contracts/`'s convention, because
two of them are cases where getting it wrong destroys media rather than leaking
it:

  * a sweep opened and then abandoned must be finished by the *next* delete;
  * a sweep whose rows never got deleted must NOT have its bytes collected,
    because those bytes are still referenced — this is the crash-between-open-
    and-delete case, and collecting it is worse than the orphan it replaces;
  * a sweep must not outlive the bytes it names, or the next drain re-reads a
    row describing nothing.
"""

import pytest

from studio_core import config
from studio_core.services import catalog, manage

from tests.conftest import CATALOG_LIBRARY, node_id_at


def _objects(bucket) -> set[str]:
    listing = bucket.list_objects_v2(Bucket=config.media_bucket())
    return {entry["Key"] for entry in listing.get("Contents", [])}


def _sweeps() -> list[dict]:
    return catalog.pending_sweeps(CATALOG_LIBRARY)


# ─────────────────────── the ordinary path leaves nothing ───────────────────


def test_a_completed_delete_leaves_no_sweep_behind(api, catalog_tree):
    """The common case. A sweep is bookkeeping, not a record worth keeping."""
    media, _ = catalog_tree
    node = node_id_at("characters/subject-a/seed/subject-a_1.webp")
    key = catalog.node(node)["blob_key"]
    assert key in _objects(media)

    assert api.delete(f"/api/nodes/{node}").status_code == 200

    assert key not in _objects(media)
    assert _sweeps() == []


def test_deleting_a_folder_with_no_files_writes_no_sweep(api, catalog_tree):
    """Most deletes in this library are folders, and a folder frees no bytes.

    A sweep row per folder delete would be a write nobody reads, on the most
    common delete there is.
    """
    _, table = catalog_tree
    before = len(_sweeps())
    node = node_id_at("characters/subject-b/corpus")
    assert api.delete(f"/api/nodes/{node}").status_code == 200
    assert len(_sweeps()) == before


# ───────────────────────── the interruption it exists for ───────────────────


def test_bytes_abandoned_by_a_crashed_delete_are_collected_by_the_next_one(
    api, catalog_tree, monkeypatch
):
    """THE ORPHAN. Rows gone, `s3.delete` never reached — the gap gc swept.

    The failure is simulated where it actually happens: `manage.release` is the
    line between the row deletions and the byte deletions, and a Lambda dying
    there is exactly this. Afterwards the object is unreachable and the sweep is
    the only thing that knows its key.
    """
    media, _ = catalog_tree
    doomed = node_id_at("characters/subject-a/seed/subject-a_1.webp")
    key = catalog.node(doomed)["blob_key"]

    # A flag rather than `monkeypatch.undo()`: undo would also roll back the
    # autouse `signed_in` fixture's patching and every later call would 401.
    crashing = {"now": True}
    real_release = manage.release
    monkeypatch.setattr(
        manage, "release",
        lambda *a, **k: None if crashing["now"] else real_release(*a, **k),
    )
    assert api.delete(f"/api/nodes/{doomed}").status_code == 200

    # The orphan, precisely: rows gone, bytes still there, nothing naming them.
    with pytest.raises(Exception):
        catalog.node(doomed)
    assert key in _objects(media)
    assert len(_sweeps()) == 1

    # Any later delete finishes it. That is the whole replacement for a
    # scheduled collector: the thing that creates the debt pays it.
    crashing["now"] = False
    other = node_id_at("characters/subject-a/seed/subject-a_2.webp")
    assert api.delete(f"/api/nodes/{other}").status_code == 200

    assert key not in _objects(media)
    assert _sweeps() == []


def test_a_sweep_whose_rows_survived_does_not_collect_their_bytes(
    catalog_tree, monkeypatch
):
    """THE DANGEROUS ONE. Sweep written, rows never deleted — bytes still live.

    A sweep is opened *before* the row deletions, so a crash in between leaves a
    sweep naming keys that are still referenced. Collecting those would destroy
    media a live row points at, which is the exact failure the row-first order
    exists to prevent and is strictly worse than the orphan this mechanism
    replaces. The drain must look each node up and keep anything still there.
    """
    media, _ = catalog_tree
    node = node_id_at("characters/subject-a/seed/subject-a_1.webp")
    key = catalog.node(node)["blob_key"]

    # Open a sweep over a node that is NOT going to be deleted.
    catalog.open_sweep(CATALOG_LIBRARY, [(node, key)])
    assert len(_sweeps()) == 1

    collected = manage.drain(CATALOG_LIBRARY)

    assert collected == 0
    assert key in _objects(media), "drain destroyed bytes a live row still names"
    assert catalog.node(node)["blob_key"] == key
    assert len(_sweeps()) == 1, "an undischarged sweep must stay open"


def test_a_part_live_sweep_collects_only_the_dead_half(catalog_tree):
    """Mixed. The dead bytes go; the live ones stay and the sweep stays open."""
    media, _ = catalog_tree
    live = node_id_at("characters/subject-a/seed/subject-a_1.webp")
    live_key = catalog.node(live)["blob_key"]

    gone = node_id_at("characters/subject-a/seed/subject-a_2.webp")
    gone_key = catalog.node(gone)["blob_key"]
    # Delete the rows for one of the two, leaving its bytes.
    catalog.delete_node(gone)

    catalog.open_sweep(CATALOG_LIBRARY, [(live, live_key), (gone, gone_key)])
    manage.drain(CATALOG_LIBRARY)

    assert live_key in _objects(media)
    assert gone_key not in _objects(media)
    # Two sweeps now — the one `delete_node` opened and the one above — and the
    # part-live one is still open because half of it could not be discharged.
    assert any(len(row.get("blobs") or []) == 2 for row in _sweeps())


def test_draining_twice_is_a_no_op_rather_than_an_error(api, catalog_tree, monkeypatch):
    """Two requests may drain concurrently; every step has to be idempotent."""
    media, _ = catalog_tree
    node = node_id_at("characters/subject-a/seed/subject-a_1.webp")
    key = catalog.node(node)["blob_key"]

    monkeypatch.setattr(manage, "release", lambda *a, **k: None)
    api.delete(f"/api/nodes/{node}")
    monkeypatch.undo()

    assert manage.drain(CATALOG_LIBRARY) == 1
    assert manage.drain(CATALOG_LIBRARY) == 0
    assert key not in _objects(media)
    assert _sweeps() == []


# ───────────────────────────── entity deletes ───────────────────────────────


def test_an_entity_delete_carries_its_sweep_too(empty_api, catalog_table, media_bucket):
    """The five entity routes free bytes through the same path and must sweep.

    They were the five call sites that each wrote `if result["blob_keys"]:
    s3.delete(...)` — the line the sweep replaces — so a fix that only covered
    `/api/nodes` would leave the majority of deletes producing orphans.
    """
    created = empty_api.post("/api/characters", json={"slug": "sweepable"})
    assert created.status_code == 201
    char = created.get_json()

    node = empty_api.post("/api/nodes", json={
        "parent": char["root"], "name": "shot.mp4", "kind": "file",
    }).get_json()
    key = catalog.node(node["id"])["blob_key"]
    # The real upload shape: sign, PUT, confirm. A node with no bytes behind it
    # is a placeholder, and `save_text` refuses one — so this cannot be faked
    # with a text write.
    empty_api.post(f"/api/nodes/{node['id']}/upload-url",
                   json={"size": 5, "content_type": "video/mp4"})
    media_bucket.put_object(Bucket=config.media_bucket(), Key=key,
                            Body=b"bytes", ContentType="video/mp4")
    empty_api.post(f"/api/nodes/{node['id']}/confirm-upload", json={})
    assert key in _objects(media_bucket)

    deleted = empty_api.delete(f"/api/characters/{char['id']}?files=delete")
    assert deleted.status_code == 200

    assert key not in _objects(media_bucket)
    assert catalog.pending_sweeps(CATALOG_LIBRARY) == []


def test_a_drain_failure_does_not_fail_the_delete_that_triggered_it(
    api, catalog_tree, monkeypatch
):
    """Recovery is opportunistic, so it must never be the reason a request 500s.

    The sweep survives a failed drain and the next request tries again, which is
    the property that makes it safe to do this on the hot path at all.
    """
    def explode(*_a, **_k):
        raise RuntimeError("dynamodb is having a day")

    monkeypatch.setattr(catalog, "pending_sweeps", explode)
    node = node_id_at("characters/subject-a/seed/subject-a_1.webp")
    assert api.delete(f"/api/nodes/{node}").status_code == 200
