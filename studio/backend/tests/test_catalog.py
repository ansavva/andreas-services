"""Tests for `services.catalog`, against a moto-backed copy of the table.

The two things worth testing here are the two things a bucket could not do, and
they are the reason the catalog exists at all: a **name collision decided by a
condition expression** rather than by a read, and a **move that costs no bytes**
and rewrites a derived index instead. Both get their own tests below, and the
move test builds a tree three deep so that the descendant rewrite has something
to get wrong.

Every assertion about a stored item is made through `client.get_item` or
`client.query` rather than through `catalog`, so a test cannot pass because the
reader and the writer share a mistake.
"""

import pytest

from studio_core import config
from studio_core.errors import ConflictError, NotFoundError, UpstreamError, ValidationError
from studio_core.services import catalog
from tests.conftest import (
    CATALOG_LIBRARY,
    CATALOG_MEMBER,
    CATALOG_OWNER,
    CATALOG_ROOT,
)


def _item(client, pk, sk):
    """One raw item, or None. The catalog's own reads are not trusted here."""
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _folder(name, parent=CATALOG_ROOT):
    return catalog.create_node(parent, name, catalog.KIND_FOLDER)


def _file(name, parent=CATALOG_ROOT, blob_key="characters/<slug>/reference/1.webp"):
    return catalog.create_node(parent, name, catalog.KIND_FILE, blob_key=blob_key)


# ──────────────────────────── reads ────────────────────────────


def test_libraries_for_returns_the_membership_row(catalog_table):
    assert catalog.libraries_for(CATALOG_OWNER) == [
        {"lib": CATALOG_LIBRARY, "role": "owner", "created_at": "2026-08-19T12:00:00.000000+00:00"}
    ]


def test_libraries_for_a_stranger_is_empty(catalog_table):
    # Not an error: "you are in no libraries" is a real answer, and the caller
    # that turns it into a 403 is the one with the request in front of it.
    assert catalog.libraries_for("sub-nobody") == []


def test_members_of_lists_everyone(catalog_table):
    members = catalog.members_of(CATALOG_LIBRARY)
    assert sorted((member["sub"], member["role"]) for member in members) == [
        (CATALOG_MEMBER, "member"),
        (CATALOG_OWNER, "owner"),
    ]


def test_members_of_does_not_return_the_library_item(catalog_table):
    # `by-sk` is hashed on the sort key, and the library's own item shares the
    # `META` sort key with every node. Querying `LIB#<id>` must reach only the
    # memberships.
    assert all("role" in member for member in catalog.members_of(CATALOG_LIBRARY))


def test_library_returns_the_name_and_the_root(catalog_table):
    # The two attributes a membership row does not carry, which is the whole
    # reason this read exists beside `libraries_for`.
    record = catalog.library(CATALOG_LIBRARY)
    assert record["name"] == "Library"
    assert record["root_node"] == CATALOG_ROOT
    # The layout does not leave the module, exactly as for a node record.
    assert "pk" not in record and "sk" not in record


def test_library_raises_for_a_missing_id(catalog_table):
    with pytest.raises(NotFoundError):
        catalog.library("lib-gone")


def test_node_raises_for_a_missing_id(catalog_table):
    with pytest.raises(NotFoundError):
        catalog.node("node-gone")


# ──────────────────────────── create ────────────────────────────


def test_create_node_writes_both_halves(catalog_table):
    created = _folder("projects")

    record = _item(catalog_table, f"NODE#{created['node_id']}", "META")
    by_parent = _item(catalog_table, f"NODE#{CATALOG_ROOT}", "NAME#projects")

    assert record["name"]["S"] == "projects"
    assert record["parent_id"]["S"] == CATALOG_ROOT
    assert record["lib"]["S"] == CATALOG_LIBRARY
    assert by_parent["node_id"]["S"] == created["node_id"]
    # Both halves carry `path`, which is what puts both of them in `by-path`.
    assert record["path"]["S"] == by_parent["path"]["S"] == f"/{CATALOG_ROOT}/"


def test_create_node_takes_its_library_from_the_parent(catalog_table):
    parent = _folder("projects")
    child = _folder("<project>", parent=parent["node_id"])

    assert child["lib"] == CATALOG_LIBRARY
    assert child["path"] == f"/{CATALOG_ROOT}/{parent['node_id']}/"


def test_create_node_refuses_a_name_already_taken(catalog_table):
    _folder("projects")
    # The refusal comes from the condition expression on the `NAME#` put, not
    # from a read — nothing in `catalog` looks the name up first.
    with pytest.raises(ConflictError):
        _folder("projects")


def test_create_node_allows_the_same_name_in_a_different_folder(catalog_table):
    first = _folder("projects")
    second = _folder("characters")
    _folder("output", parent=first["node_id"])
    _folder("output", parent=second["node_id"])

    assert [entry["name"] for entry in catalog.children(first["node_id"])] == ["output"]


def test_create_node_stores_a_blob_key_verbatim(catalog_table):
    # A legacy key from before the table existed. Nothing may parse, shorten or
    # re-derive it — it round-trips exactly.
    key = "projects/<project>/runs/2026-08-14_16-32-11_kling-yqp1jqf5/output/clip.mp4"
    created = _file("clip.mp4", blob_key=key)

    assert catalog.node(created["node_id"])["blob_key"] == key


def test_create_node_derives_a_blob_key_for_a_file_that_omits_one(catalog_table):
    """**Reverses this test's own previous assertion**, which was a ValidationError.

    #294 added the upload routes, and a client cannot name `blobs/<node_id>` at
    create time because it does not know the id yet — so the only way to have an
    id-derived key is for both to be minted here. The node is a placeholder until
    the bytes land: a key, and nothing behind it.
    """
    created = catalog.create_node(CATALOG_ROOT, "clip.mp4", catalog.KIND_FILE)

    assert created["blob_key"] == catalog.blob_key_for(created["node_id"])
    assert "size" not in created


def test_create_node_keeps_an_explicit_blob_key_verbatim(catalog_table):
    """Prod holds keys written long before this table, and they stay where they are."""
    legacy = "characters/subject-a/seed/subject-a_1.webp"

    created = catalog.create_node(CATALOG_ROOT, "old.webp", catalog.KIND_FILE, blob_key=legacy)

    assert catalog.node(created["node_id"])["blob_key"] == legacy


def test_create_node_refuses_a_blob_key_on_a_folder(catalog_table):
    with pytest.raises(ValidationError):
        catalog.create_node(CATALOG_ROOT, "projects", catalog.KIND_FOLDER, blob_key="blobs/x")


def test_create_node_refuses_an_unknown_kind(catalog_table):
    with pytest.raises(ValidationError):
        catalog.create_node(CATALOG_ROOT, "projects", "symlink")


def test_create_node_validates_the_name(catalog_table):
    # `keys.clean_name` refuses a slash rather than escaping it, so a create
    # cannot be talked into naming a path.
    with pytest.raises(ValidationError):
        _folder("projects/<project>")


def test_create_node_refuses_a_missing_parent(catalog_table):
    with pytest.raises(NotFoundError):
        _folder("projects", parent="node-gone")


def test_create_node_refuses_a_file_as_a_parent(catalog_table):
    # Nothing in the key layout prevents it — a `NAME#` item under a file's id
    # is a well-formed row — so the refusal has to be made here.
    clip = _file("clip.mp4")

    with pytest.raises(ValidationError):
        _folder("output", parent=clip["node_id"])


# ──────────────────────────── children ────────────────────────────


def test_children_are_name_sorted(catalog_table):
    for name in ("phrasebook", "characters", "projects"):
        _folder(name)

    assert [entry["name"] for entry in catalog.children(CATALOG_ROOT)] == [
        "characters",
        "phrasebook",
        "projects",
    ]


def test_children_of_an_empty_folder_is_empty(catalog_table):
    folder = _folder("projects")
    assert catalog.children(folder["node_id"]) == []


def test_children_carry_the_index_projection_only(catalog_table):
    _file("clip.mp4", blob_key="blobs/node-x")
    entry = catalog.children(CATALOG_ROOT)[0]

    assert entry["kind"] == "file"
    # `blob_key` is not projected onto the by-parent item, by schema. A caller
    # that needs it fetches the record.
    assert "blob_key" not in entry
    assert catalog.node(entry["node_id"])["blob_key"] == "blobs/node-x"


def test_child_by_name_finds_one_child(catalog_table):
    folder = _folder("characters")
    assert catalog.child_by_name(CATALOG_ROOT, "characters")["node_id"] == folder["node_id"]


def test_child_by_name_raises_for_a_name_that_is_not_there(catalog_table):
    _folder("characters")
    with pytest.raises(NotFoundError):
        catalog.child_by_name(CATALOG_ROOT, "projects")


def test_child_by_name_does_not_reach_into_another_folder(catalog_table):
    # The key is (parent, name), so the same name in a sibling folder is a
    # different item and must not answer for this one.
    other = _folder("projects")
    _folder("runs", parent=other["node_id"])
    with pytest.raises(NotFoundError):
        catalog.child_by_name(CATALOG_ROOT, "runs")


# ──────────────────────────── records ────────────────────────────


def _count_batch_gets(monkeypatch):
    """Count `BatchGetItem` calls without changing what any of them return."""
    real = catalog.dynamodb.client()
    calls = {"count": 0}

    class Counting:
        def __getattr__(self, name):
            return getattr(real, name)

        def batch_get_item(self, **kwargs):
            calls["count"] += 1
            return real.batch_get_item(**kwargs)

    monkeypatch.setattr(catalog.dynamodb, "client", Counting)
    return calls


def test_records_returns_the_full_record_for_each_id(catalog_table):
    # The point of the batch: `size` and `blob_key` live on the record half
    # only, so this is what a listing has to call to report either.
    clip = catalog.create_node(
        CATALOG_ROOT, "clip.mp4", catalog.KIND_FILE, blob_key="blobs/node-x", size=17
    )
    folder = _folder("characters")

    found = catalog.records([clip["node_id"], folder["node_id"]])

    assert found[clip["node_id"]]["size"] == 17
    assert found[clip["node_id"]]["blob_key"] == "blobs/node-x"
    assert found[folder["node_id"]]["kind"] == "folder"


def test_records_omits_an_id_that_is_not_there(catalog_table):
    # Missing rather than raising: the caller holds the list it asked for and
    # decides what an absent record means. `routes/nodes` logs it.
    folder = _folder("characters")
    found = catalog.records([folder["node_id"], "node-nope"])

    assert set(found) == {folder["node_id"]}


def test_records_collapses_a_repeated_id(catalog_table):
    # `BatchGetItem` rejects a request naming one key twice, and a caller
    # merging two listings has no reason to know that.
    folder = _folder("characters")
    assert set(catalog.records([folder["node_id"]] * 3)) == {folder["node_id"]}


def test_records_of_nothing_reads_nothing(catalog_table):
    # An empty folder listing must not send a `BatchGetItem` with no keys, which
    # DynamoDB rejects.
    assert catalog.records([]) == {}


def test_records_chunks_past_the_batch_ceiling(catalog_table, monkeypatch):
    """More ids than one `BatchGetItem` takes, and every one comes back.

    The call count is asserted as well as the result, because moto is more
    forgiving than DynamoDB about an oversized batch — a `records` that never
    chunked could pass on the result alone here and fail in prod.
    """
    folder = _folder("corpus")
    made = [_file(f"frame_{index:03d}.webp", parent=folder["node_id"]) for index in range(101)]

    calls = _count_batch_gets(monkeypatch)
    found = catalog.records([node["node_id"] for node in made])

    assert set(found) == {node["node_id"] for node in made}
    assert calls["count"] == 2


def test_records_asks_again_for_unprocessed_keys(catalog_table, monkeypatch):
    """`UnprocessedKeys` arrives on a **200**, so nothing below `records` retries it.

    botocore retries error codes, and a throttled batch is not one — DynamoDB
    answers with the items it managed and the keys it did not. A `records` that
    read `Responses` and moved on would drop nodes from a listing precisely when
    the table was busiest, and would do it without a log line.
    """
    ids = [_folder("characters")["node_id"], _folder("projects")["node_id"]]
    real = catalog.dynamodb.client()
    table = config.catalog_table()
    withheld = {"done": False}

    class Halving:
        """Answers the first batch with one item and the rest unprocessed."""

        def batch_get_item(self, RequestItems):  # noqa: N803 — boto3's own spelling
            keys = RequestItems[table]["Keys"]
            if withheld["done"] or len(keys) < 2:
                return real.batch_get_item(RequestItems=RequestItems)
            withheld["done"] = True
            response = real.batch_get_item(RequestItems={table: {"Keys": keys[:1]}})
            return {**response, "UnprocessedKeys": {table: {"Keys": keys[1:]}}}

    monkeypatch.setattr(catalog.dynamodb, "client", Halving)
    monkeypatch.setattr(catalog, "BATCH_GET_BACKOFF", 0)

    assert set(catalog.records(ids)) == set(ids)


def test_records_gives_up_rather_than_answering_short(catalog_table, monkeypatch):
    """A batch that never clears is a 502, not a listing missing half its files."""
    folder = _folder("characters")
    table = config.catalog_table()

    class Stalled:
        def batch_get_item(self, RequestItems):  # noqa: N803 — boto3's own spelling
            return {"Responses": {table: []}, "UnprocessedKeys": RequestItems}

    monkeypatch.setattr(catalog.dynamodb, "client", Stalled)
    monkeypatch.setattr(catalog, "BATCH_GET_BACKOFF", 0)

    with pytest.raises(UpstreamError):
        catalog.records([folder["node_id"]])


# ──────────────────────────── subtree ────────────────────────────


def test_subtree_returns_descendants_and_not_the_node_itself(catalog_table):
    parent = _folder("projects")
    child = _folder("<project>", parent=parent["node_id"])
    grandchild = _file("clip.mp4", parent=child["node_id"])

    found = catalog.subtree(CATALOG_LIBRARY, catalog.child_path(parent))

    assert sorted(entry["node_id"] for entry in found) == sorted(
        [child["node_id"], grandchild["node_id"]]
    )


def test_subtree_returns_records_not_index_projections(catalog_table):
    # Both halves of a node sit in `by-path`; only the record half comes back,
    # so a node appears once and with its `blob_key`.
    parent = _folder("projects")
    _file("clip.mp4", parent=parent["node_id"], blob_key="blobs/node-x")

    found = catalog.subtree(CATALOG_LIBRARY, catalog.child_path(parent))

    assert len(found) == 1
    assert found[0]["blob_key"] == "blobs/node-x"


def test_branch_truncates_where_subtree_refuses(catalog_table, monkeypatch):
    """The same query, and the caller decides what a short answer means.

    `subtree`'s two callers are writes, where half a job reported as a whole one
    is unrecoverable. The reel's is a page of a library, which is allowed to be
    shorter than the library — so `branch` reports the cut and lets the caller
    choose. One function rather than two nearly identical ones.
    """
    parent = _folder("projects")
    for index in range(3):
        _folder(f"run-{index}", parent=parent["node_id"])

    records, truncated = catalog.branch(CATALOG_LIBRARY, catalog.child_path(parent), 2)

    assert len(records) == 2
    assert truncated is True


def test_recent_returns_the_library_newest_first(catalog_table):
    """`by-recent` is the one read here whose order the table chose."""
    first = _folder("projects")
    second = _folder("characters")
    third = _file("clip.mp4", parent=second["node_id"])

    records, truncated = catalog.recent(CATALOG_LIBRARY, 10)

    assert truncated is False
    # The root is in the library too, and is the oldest row in it.
    assert [entry["node_id"] for entry in records] == [
        third["node_id"],
        second["node_id"],
        first["node_id"],
        CATALOG_ROOT,
    ]


def test_recent_drops_the_oldest_when_it_truncates(catalog_table):
    """What makes cutting this query safe, where cutting `branch` is arbitrary."""
    _folder("projects")
    newest = _folder("characters")

    records, truncated = catalog.recent(CATALOG_LIBRARY, 1)

    assert truncated is True
    assert [entry["node_id"] for entry in records] == [newest["node_id"]]


def test_recent_returns_records_not_index_projections(catalog_table):
    # Both halves of a node sit in `by-recent` as well — #280 puts `lib` and
    # `created_at` on the by-parent item — so an unfiltered query would return
    # every node twice and half of them without a `blob_key`.
    _file("clip.mp4", blob_key="blobs/node-x")

    records, _ = catalog.recent(CATALOG_LIBRARY, 10)
    files = [entry for entry in records if entry["kind"] == catalog.KIND_FILE]

    assert len(files) == 1
    assert files[0]["blob_key"] == "blobs/node-x"


def test_subtree_refuses_past_the_folder_cap(catalog_table, monkeypatch):
    monkeypatch.setenv("STUDIO_MAX_FOLDER_OBJECTS", "2")
    parent = _folder("projects")
    for index in range(3):
        _folder(f"run-{index}", parent=parent["node_id"])

    # A refusal, not a truncated list — both callers of `subtree` are writes,
    # and half a move is worse than no move.
    with pytest.raises(ValidationError):
        catalog.subtree(CATALOG_LIBRARY, catalog.child_path(parent))


# ──────────────────────────── rename ────────────────────────────


def test_rename_node_moves_the_by_parent_item(catalog_table):
    created = _folder("projects")
    catalog.rename_node(created["node_id"], "archive")

    assert _item(catalog_table, f"NODE#{CATALOG_ROOT}", "NAME#projects") is None
    assert _item(catalog_table, f"NODE#{CATALOG_ROOT}", "NAME#archive") is not None
    assert catalog.node(created["node_id"])["name"] == "archive"


def test_rename_node_leaves_path_alone(catalog_table):
    # `path` names ancestors, and a rename changes none of them.
    parent = _folder("projects")
    child = _folder("<project>", parent=parent["node_id"])
    catalog.rename_node(parent["node_id"], "archive")

    assert catalog.node(child["node_id"])["path"] == f"/{CATALOG_ROOT}/{parent['node_id']}/"


def test_rename_node_to_a_taken_name_conflicts(catalog_table):
    _folder("characters")
    created = _folder("projects")

    with pytest.raises(ConflictError):
        catalog.rename_node(created["node_id"], "characters")

    # The transaction is all-or-nothing, so the losing rename left nothing behind.
    assert catalog.node(created["node_id"])["name"] == "projects"
    assert _item(catalog_table, f"NODE#{CATALOG_ROOT}", "NAME#projects") is not None


def test_rename_node_to_its_own_name_writes_nothing(catalog_table):
    created = _folder("projects")
    result = catalog.rename_node(created["node_id"], "projects")

    assert result["renamed"] is False
    assert result["updated_at"] == created["updated_at"]


def test_rename_node_refuses_the_library_root(catalog_table):
    with pytest.raises(ValidationError):
        catalog.rename_node(CATALOG_ROOT, "elsewhere")


# ──────────────────────────── move ────────────────────────────


def _tree(catalog_table):
    """`projects/<project>/output/clip.mp4`, plus an empty `archive/` beside it."""
    projects = _folder("projects")
    archive = _folder("archive")
    project = _folder("<project>", parent=projects["node_id"])
    output = _folder("output", parent=project["node_id"])
    clip = _file("clip.mp4", parent=output["node_id"])
    return projects, archive, project, output, clip


def test_move_node_rewrites_every_descendant_path(catalog_table):
    projects, archive, project, output, clip = _tree(catalog_table)

    result = catalog.move_node(project["node_id"], archive["node_id"])

    assert result["descendants"] == 2
    moved = catalog.node(project["node_id"])
    assert moved["parent_id"] == archive["node_id"]
    assert moved["path"] == f"/{CATALOG_ROOT}/{archive['node_id']}/"
    # Two levels down, and the segment below the moved node is untouched.
    assert catalog.node(output["node_id"])["path"] == (
        f"/{CATALOG_ROOT}/{archive['node_id']}/{project['node_id']}/"
    )
    assert catalog.node(clip["node_id"])["path"] == (
        f"/{CATALOG_ROOT}/{archive['node_id']}/{project['node_id']}/{output['node_id']}/"
    )
    # The old parent no longer lists it, the new one does.
    assert catalog.children(projects["node_id"]) == []
    assert [entry["name"] for entry in catalog.children(archive["node_id"])] == ["<project>"]


def test_move_node_rewrites_the_by_parent_half_too(catalog_table):
    _projects, archive, project, output, _clip = _tree(catalog_table)
    catalog.move_node(project["node_id"], archive["node_id"])

    # Both halves are in `by-path`; a stale one on the index half would leave
    # the same node reachable under two branches. Asserted against the expected
    # string rather than against the record half, which would agree with it
    # while both were stale.
    by_parent = _item(catalog_table, f"NODE#{project['node_id']}", "NAME#output")
    assert by_parent["path"]["S"] == (
        f"/{CATALOG_ROOT}/{archive['node_id']}/{project['node_id']}/"
    )
    assert by_parent["path"]["S"] == catalog.node(output["node_id"])["path"]


def test_move_node_keeps_the_subtree_queryable_under_its_new_branch(catalog_table):
    _projects, archive, project, _output, _clip = _tree(catalog_table)
    catalog.move_node(project["node_id"], archive["node_id"])

    assert len(catalog.subtree(CATALOG_LIBRARY, catalog.child_path(archive))) == 3


def test_move_node_into_a_taken_name_conflicts(catalog_table):
    projects, archive, project, _output, _clip = _tree(catalog_table)
    _folder("<project>", parent=archive["node_id"])

    with pytest.raises(ConflictError):
        catalog.move_node(project["node_id"], archive["node_id"])

    # Nothing moved: the by-parent swap and the parent pointer are one transaction.
    assert catalog.node(project["node_id"])["parent_id"] == projects["node_id"]


def test_move_node_refuses_its_own_subtree(catalog_table):
    _projects, _archive, project, output, _clip = _tree(catalog_table)

    with pytest.raises(ValidationError):
        catalog.move_node(project["node_id"], output["node_id"])


def test_move_node_refuses_itself(catalog_table):
    _projects, _archive, project, _output, _clip = _tree(catalog_table)

    with pytest.raises(ValidationError):
        catalog.move_node(project["node_id"], project["node_id"])


def test_move_node_to_the_same_parent_writes_nothing(catalog_table):
    projects, _archive, project, _output, _clip = _tree(catalog_table)
    result = catalog.move_node(project["node_id"], projects["node_id"])

    assert result["moved"] is False
    assert result["updated_at"] == project["updated_at"]


def test_move_node_refuses_a_file_as_a_destination(catalog_table):
    _projects, _archive, project, _output, clip = _tree(catalog_table)

    with pytest.raises(ValidationError):
        catalog.move_node(project["node_id"], clip["node_id"])


def test_move_node_refuses_the_library_root(catalog_table):
    _projects, archive, _project, _output, _clip = _tree(catalog_table)

    with pytest.raises(ValidationError):
        catalog.move_node(CATALOG_ROOT, archive["node_id"])


# ──────────────────────────── delete ────────────────────────────


def test_delete_node_removes_the_whole_subtree(catalog_table):
    projects, _archive, project, output, clip = _tree(catalog_table)

    result = catalog.delete_node(project["node_id"])

    assert result["deleted"] == 3
    for node_id in (project["node_id"], output["node_id"], clip["node_id"]):
        with pytest.raises(NotFoundError):
            catalog.node(node_id)
    assert catalog.children(projects["node_id"]) == []
    assert _item(catalog_table, f"NODE#{output['node_id']}", "NAME#clip.mp4") is None


def test_delete_node_reports_the_blobs_it_orphaned(catalog_table):
    folder = _folder("projects")
    _file("clip.mp4", parent=folder["node_id"], blob_key="blobs/node-a")
    _file("still.webp", parent=folder["node_id"], blob_key="blobs/node-b")

    result = catalog.delete_node(folder["node_id"])

    # Reported, not deleted — this module never touches S3, and whether a blob
    # is now unreferenced is not a question one delete can answer.
    assert sorted(result["blob_keys"]) == ["blobs/node-a", "blobs/node-b"]


def test_delete_node_leaves_siblings_alone(catalog_table):
    _folder("projects")
    keep = _folder("characters")
    catalog.delete_node(catalog.children(CATALOG_ROOT)[1]["node_id"])

    assert [entry["name"] for entry in catalog.children(CATALOG_ROOT)] == ["characters"]
    assert catalog.node(keep["node_id"])["name"] == "characters"


def test_delete_node_refuses_the_library_root(catalog_table):
    with pytest.raises(ValidationError):
        catalog.delete_node(CATALOG_ROOT)


# ──────────────────────────── set_blob ────────────────────────────


def test_set_blob_points_a_file_at_its_bytes(catalog_table):
    created = _file("clip.mp4", blob_key="blobs/placeholder")

    catalog.set_blob(created["node_id"], "blobs/node-a", size=1234, content_type="video/mp4")

    record = catalog.node(created["node_id"])
    assert record["blob_key"] == "blobs/node-a"
    assert record["size"] == 1234
    assert record["content_type"] == "video/mp4"
    assert record["updated_at"] > created["updated_at"]


def test_set_blob_leaves_the_by_parent_item_alone(catalog_table):
    created = _file("clip.mp4")
    catalog.set_blob(created["node_id"], "blobs/node-a")

    # Nothing it writes is projected onto that half, so there is nothing to sync.
    by_parent = _item(catalog_table, f"NODE#{CATALOG_ROOT}", "NAME#clip.mp4")
    assert "blob_key" not in by_parent


def test_set_blob_refuses_a_folder(catalog_table):
    folder = _folder("projects")

    with pytest.raises(ValidationError):
        catalog.set_blob(folder["node_id"], "blobs/node-a")


def test_set_blob_refuses_an_empty_key(catalog_table):
    created = _file("clip.mp4")

    with pytest.raises(ValidationError):
        catalog.set_blob(created["node_id"], "")


def test_set_blob_refuses_a_missing_node(catalog_table):
    with pytest.raises(NotFoundError):
        catalog.set_blob("node-gone", "blobs/node-a")
