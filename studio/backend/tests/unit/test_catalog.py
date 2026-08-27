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

    #294 added the upload routes, and a client cannot name the key at create time
    because it does not know the node id yet — so the only way to have an
    id-derived key is for both to be minted here. The node is a placeholder until
    the bytes land: a key, and nothing behind it.

    The entity model changed the *shape* of what is minted, not the rule.
    `blobs/<node_id>` became `<owner_kind>/<owner_id>/<node_id>.<ext>`, so a
    bucket listing is per-entity — Storage Lens cost, lifecycle rules, a bulk
    delete that is one prefix — and carries no name, which is hard rule #1
    enforced in the one place nobody was reading it. Still true with the rule
    env-scoped: this bucket holds production characters.
    """
    created = catalog.create_node(CATALOG_ROOT, "clip.mp4", catalog.KIND_FILE)

    assert created["blob_key"] == catalog.blob_key_for(
        created["node_id"], "clip.mp4", None, CATALOG_LIBRARY
    )
    assert "size" not in created


def test_a_node_owned_by_nobody_is_filed_under_the_library(catalog_table):
    """A folder somebody made by hand belongs to no entity, and that is a real answer.

    Three prefixes exist in the bucket and no more: `characters/`, `projects/`
    and `libraries/`. The third is not a fallback nobody reaches — the library
    root is where every hand-made folder starts, and material that belongs to
    neither a character nor a project has to live somewhere that is still one
    prefix a `gc` can scope itself to.
    """
    created = catalog.create_node(CATALOG_ROOT, "plate.png", catalog.KIND_FILE)

    assert created["blob_key"] == (
        f"libraries/{CATALOG_LIBRARY}/{created['node_id']}.png"
    )


def test_a_blob_key_carries_the_extension_and_nothing_else_of_the_name(catalog_table):
    """The extension is decoration for a human reading the S3 console.

    `content_type` on the row is authoritative and the API sets it on every
    presigned response, so nothing reads meaning back out of a key. What the
    extension must NOT do is bring the rest of the name with it — the old layout
    wrote `<slug>_face_1.png` into the key, which made a bucket listing a list of
    character names.
    """
    created = catalog.create_node(CATALOG_ROOT, "three quarter left.PNG", catalog.KIND_FILE)

    assert created["blob_key"].endswith(f"/{created['node_id']}.png")
    assert "three" not in created["blob_key"]


def test_is_api_blob_reads_the_key_shape_and_never_its_values(catalog_table):
    """**`<owner_prefix>/<id>/…` — the shape, not who owns it.**

    This is what the two upload routes ask before they will sign for a node, so
    getting it wrong in either direction is expensive. Read the owner ID and a
    file dragged from a character into a project stops being uploadable, because
    its key still says the old owner. Read only the shape and the answer stays
    true for the life of the node.
    """
    minted = catalog.create_node(CATALOG_ROOT, "clip.mp4", catalog.KIND_FILE)
    legacy = catalog.create_node(
        CATALOG_ROOT, "old.webp", catalog.KIND_FILE,
        blob_key="characters/subject-a/seed/subject-a_1.webp",
    )

    assert catalog.is_api_blob(minted) is True
    assert catalog.is_api_blob(legacy) is False
    # A drifted prefix is still this API's key: the node moved, the bytes did not.
    assert catalog.is_api_blob(
        {**minted, "blob_key": f"projects/proj-0001/{minted['node_id']}.mp4"})


def test_is_api_blob_accepts_a_descriptive_key(catalog_table):
    """**The regression that took production's whole library out.**

    The check used to read the tail as `/<node_id>.<ext>`, which was every key
    this API had written — until the key became descriptive and its last segment
    became the file's own name. `reseat --apply` rewrote prod to the new shape
    and all 186 of its file nodes stopped matching, so both upload routes
    refused to overwrite anything in the library.

    Both shapes are live at once — this API still stamps the flat one at
    creation and `reseat` produces the other — so both have to pass.
    """
    node = catalog.create_node(CATALOG_ROOT, "IMG_4580.png", catalog.KIND_FILE)

    flat = f"characters/char-0001/{node['node_id']}.png"
    descriptive = "characters/char-0001/reference/face/IMG_4580.png"

    assert catalog.is_api_blob({**node, "blob_key": flat}) is True
    assert catalog.is_api_blob({**node, "blob_key": descriptive}) is True


@pytest.mark.parametrize(
    "key",
    [
        "characters/subject-a/reference/face/x.png",   # the legacy slug layout
        "blobs/node-0001",                             # the flat pre-owner scheme
        "config/pose/face/front.png",                  # shared material, never ours
        "phrasebook/wording.yaml",
        "characters/char-0001",                        # a prefix with no file under it
    ],
)
def test_is_api_blob_still_rejects_everything_that_predates_the_catalog(catalog_table, key):
    """The half the loosening must not give away — #309 is why this exists."""
    node = catalog.create_node(CATALOG_ROOT, "x.png", catalog.KIND_FILE)

    assert catalog.is_api_blob({**node, "blob_key": key}) is False


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


def test_recent_returns_only_media_newest_first(catalog_table):
    """`by-recent` is the one read here whose order the table chose — and it is sparse.

    **This test used to expect the folders and the library root back**, and the
    change is the point rather than a relaxation. The index is hashed on `reel`
    now, whose value *is* the library id: same string as `lib`, different
    attribute name, and a DynamoDB item enters a GSI only when it carries both of
    that index's key attributes. `reel` is written onto file nodes whose
    extension reads as an image or a video and onto nothing else, so folders,
    entity records, membership rows and slug claims are absent from the index
    rather than read and discarded.

    That fixed a real cost as well as making room for the entity rows: hashed on
    `lib`, every folder in the library entered the reel's enumeration and was
    filtered out in memory by `browse.reel_items` — **after** it had already been
    counted against `config.max_folder_objects`.
    """
    folder = _folder("characters")
    picture = _file("front.png", parent=folder["node_id"])
    clip = _file("clip.mp4", parent=folder["node_id"])
    _file("notes.txt", parent=folder["node_id"])

    records, truncated = catalog.recent(CATALOG_LIBRARY, 10)

    assert truncated is False
    assert [entry["node_id"] for entry in records] == [clip["node_id"], picture["node_id"]]


def test_recent_leaves_folders_and_the_library_root_out_of_the_index(catalog_table):
    """The half of the sparseness that is about the cap rather than the answer.

    Asserted separately from the ordering above because the two would drift: a
    reader fixing an order assertion would happily add a folder back to the
    expected list, and this one says the folder must not be in the enumeration at
    all — which is where the `max_folder_objects` budget goes.
    """
    _folder("projects")
    _folder("characters")

    records, _ = catalog.recent(CATALOG_LIBRARY, 10)

    assert records == []


def test_recent_drops_the_oldest_when_it_truncates(catalog_table):
    """What makes cutting this query safe, where cutting `branch` is arbitrary."""
    _file("first.png")
    newest = _file("second.png")

    records, truncated = catalog.recent(CATALOG_LIBRARY, 1)

    assert truncated is True
    assert [entry["node_id"] for entry in records] == [newest["node_id"]]


def test_renaming_a_file_out_of_a_media_extension_removes_it_from_the_reel(catalog_table):
    """`reel` is written from the extension, so a rename can change what a file *is*.

    A `SET reel = NULL` would leave the row in the index advertising a file the
    reel cannot draw, which is why `catalog._update` treats a `None` as a REMOVE
    rather than as a NULL. That rule has exactly one caller that depends on it,
    and this is the test of it.
    """
    picture = _file("front.png")
    assert [entry["node_id"] for entry in catalog.recent(CATALOG_LIBRARY, 10)[0]] == [
        picture["node_id"]
    ]

    catalog.rename_node(picture["node_id"], "front.txt")

    assert catalog.recent(CATALOG_LIBRARY, 10)[0] == []


def test_renaming_a_file_into_a_media_extension_adds_it_to_the_reel(catalog_table):
    """The other direction, which a REMOVE-only implementation would fail silently.

    A file uploaded as `blob` and renamed to `blob.png` afterwards is ordinary,
    and a reel that never showed it would look like a caching bug rather than a
    missing attribute.
    """
    note = _file("notes.txt")
    assert catalog.recent(CATALOG_LIBRARY, 10)[0] == []

    catalog.rename_node(note["node_id"], "notes.png")

    assert [entry["node_id"] for entry in catalog.recent(CATALOG_LIBRARY, 10)[0]] == [
        note["node_id"]
    ]


def test_renaming_a_folder_never_puts_it_in_the_reel(catalog_table):
    """A folder called `archive.png` is still a folder.

    The rename path only assigns `reel` for a file, and this is the assertion
    that keeps it that way — the attribute is derived from the extension, and a
    folder's name is allowed to look like anything.
    """
    folder = _folder("plates")

    catalog.rename_node(folder["node_id"], "plates.png")

    assert catalog.recent(CATALOG_LIBRARY, 10)[0] == []


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


# ──────────────────────────── transfer ────────────────────────────
#
# A transfer is the one write that touches two libraries, so these need a second
# one. It is written literally, for the reason `conftest` gives about every
# fixture item: `catalog` is the only module allowed to know these shapes, and a
# destination built out of its own helpers would agree with any drift in them.
# It is also the only way to have one — nothing in this module creates a library.

OTHER_LIBRARY = "lib-0002"
OTHER_ROOT = "node-root-0002"


def _other_library(client):
    """A second library and the root node it opens on."""
    for item in (
        {
            "pk": {"S": f"LIB#{OTHER_LIBRARY}"},
            "sk": {"S": "META"},
            "name": {"S": "Archive"},
            "root_node": {"S": OTHER_ROOT},
            "created_at": {"S": "2026-08-19T12:00:00.000000+00:00"},
        },
        {
            "pk": {"S": f"NODE#{OTHER_ROOT}"},
            "sk": {"S": "META"},
            "node_id": {"S": OTHER_ROOT},
            "lib": {"S": OTHER_LIBRARY},
            "name": {"S": "Archive"},
            "kind": {"S": "folder"},
            "path": {"S": "/"},
            "created_at": {"S": "2026-08-19T12:00:00.000000+00:00"},
            "updated_at": {"S": "2026-08-19T12:00:00.000000+00:00"},
        },
    ):
        client.put_item(TableName=config.catalog_table(), Item=item)


def test_transfer_node_rewrites_lib_on_the_node_and_every_descendant(catalog_table):
    _other_library(catalog_table)
    _projects, _archive, project, output, clip = _tree(catalog_table)

    result = catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    assert result["descendants"] == 2
    # Every node beneath and including the target, not just the one named.
    for node_id in (project["node_id"], output["node_id"], clip["node_id"]):
        assert catalog.node(node_id)["lib"] == OTHER_LIBRARY


def test_transfer_node_rewrites_the_by_parent_half_too(catalog_table):
    """Both halves carry `lib`, and `by-path` is hashed on it.

    A descendant rewritten on the record half alone would still be indexed under
    the library it left — reachable by id and listed by its parent, but returned
    by a subtree query on the wrong library. Asserted against the raw item, not
    against the record, which would agree with it while both were stale.
    """
    _other_library(catalog_table)
    _projects, _archive, project, _output, _clip = _tree(catalog_table)

    catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    by_parent = _item(catalog_table, f"NODE#{project['node_id']}", "NAME#output")
    assert by_parent["lib"]["S"] == OTHER_LIBRARY
    assert by_parent["path"]["S"] == f"/{OTHER_ROOT}/{project['node_id']}/"


def test_transfer_node_reparents_onto_the_destination_root(catalog_table):
    """The subtree lands at the top of the destination, and leaves its old parent."""
    _other_library(catalog_table)
    projects, _archive, project, _output, _clip = _tree(catalog_table)

    catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    moved = catalog.node(project["node_id"])
    assert moved["parent_id"] == OTHER_ROOT
    assert moved["path"] == f"/{OTHER_ROOT}/"
    assert catalog.children(projects["node_id"]) == []
    assert [entry["name"] for entry in catalog.children(OTHER_ROOT)] == ["<project>"]


def test_transfer_node_moves_the_branch_between_the_two_subtree_queries(catalog_table):
    """The whole point of rewriting `lib` on both halves, asserted as a query.

    Three nodes appear under the destination's branch and none of them is left
    in the source library's — which is what a reel, a listing and every bounded
    write read.
    """
    _other_library(catalog_table)
    _projects, _archive, project, output, clip = _tree(catalog_table)

    catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    branch = {project["node_id"], output["node_id"], clip["node_id"]}
    destination = {
        entry["node_id"] for entry in catalog.subtree(OTHER_LIBRARY, f"/{OTHER_ROOT}/")
    }
    source = {
        entry["node_id"] for entry in catalog.subtree(CATALOG_LIBRARY, f"/{CATALOG_ROOT}/")
    }
    assert branch <= destination
    assert branch & source == set()


def test_transfer_node_leaves_every_blob_key_where_it_was(catalog_table):
    """A transfer carries blob keys; it does not rewrite them.

    The key is opaque and the bytes are not involved — which is the claim
    `tests/test_manage.py` and the integration suite make against a bucket. This
    is the row-level half of it.
    """
    _other_library(catalog_table)
    _projects, _archive, project, _output, clip = _tree(catalog_table)
    before = catalog.node(clip["node_id"])["blob_key"]

    catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    assert catalog.node(clip["node_id"])["blob_key"] == before


def test_transfer_node_restamps_reel_across_the_branch(catalog_table):
    """**`reel` holds the library id, so a transfer has to carry it too.**

    Miss it and every image in the branch stays in the *source* library's reel
    while its own row says it belongs to another — a member of the source
    library, browsing Recent, is shown thumbnails of media they are no longer
    entitled to. That is the leak the membership checks exist to prevent, and no
    folder listing anywhere would show it: `by-path` and `children` both read
    `lib`, which the transfer does rewrite.

    Asserted through the index rather than through the record for that reason
    exactly — a record that agrees with itself proves nothing about the GSI.
    """
    _other_library(catalog_table)
    _projects, _archive, project, _output, clip = _tree(catalog_table)

    catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    source, _ = catalog.recent(CATALOG_LIBRARY, 10)
    destination, _ = catalog.recent(OTHER_LIBRARY, 10)

    assert [entry["node_id"] for entry in source] == []
    assert [entry["node_id"] for entry in destination] == [clip["node_id"]]


def test_transfer_node_writes_reel_on_the_record_half_only(catalog_table):
    """The by-parent item carries neither of `by-recent`'s keys and must not start.

    `_put_name`'s projection is `node_id, lib, kind, path, created_at` — no
    `reel`, no `created_at` conflict — so a descendant rewritten with `reel` on
    both halves would put a **second** copy of every image in the reel, and the
    grid would draw each of them twice. Cheap to state here; expensive to
    diagnose from a duplicated tile.
    """
    _other_library(catalog_table)
    _projects, _archive, project, output, clip = _tree(catalog_table)

    catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    by_parent = _item(catalog_table, f"NODE#{output['node_id']}", f"NAME#{clip['name']}")
    assert "reel" not in by_parent
    assert by_parent["lib"]["S"] == OTHER_LIBRARY


def test_transfer_node_into_a_taken_name_conflicts(catalog_table):
    """A refusal, and one that has written nothing — the collision is checked first."""
    _other_library(catalog_table)
    projects, _archive, project, output, _clip = _tree(catalog_table)
    catalog.create_node(OTHER_ROOT, "<project>", catalog.KIND_FOLDER)

    with pytest.raises(ConflictError):
        catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    # Nothing moved and nothing was half-rewritten: the conditional put is the
    # first write a transfer makes, so a 409 leaves the descendants alone too.
    assert catalog.node(project["node_id"])["parent_id"] == projects["node_id"]
    assert catalog.node(project["node_id"])["lib"] == CATALOG_LIBRARY
    assert catalog.node(output["node_id"])["lib"] == CATALOG_LIBRARY


def test_transfer_node_into_its_own_library_writes_nothing(catalog_table):
    _projects, _archive, project, _output, _clip = _tree(catalog_table)

    result = catalog.transfer_node(project["node_id"], CATALOG_LIBRARY)

    assert result["transferred"] is False
    assert result["updated_at"] == project["updated_at"]


def test_transfer_node_refuses_the_library_root(catalog_table):
    """No `parent_id`, so there is no by-parent item to re-file it under."""
    _other_library(catalog_table)

    with pytest.raises(ValidationError):
        catalog.transfer_node(CATALOG_ROOT, OTHER_LIBRARY)


def test_transfer_node_refuses_a_library_that_does_not_exist(catalog_table):
    _projects, _archive, project, _output, _clip = _tree(catalog_table)

    with pytest.raises(NotFoundError):
        catalog.transfer_node(project["node_id"], "lib-nope")


def test_transfer_node_refuses_past_the_folder_cap(catalog_table, monkeypatch):
    """`subtree`'s refusal, inherited: a partial transfer is the failure to avoid."""
    _other_library(catalog_table)
    _projects, _archive, project, _output, _clip = _tree(catalog_table)
    monkeypatch.setenv("STUDIO_MAX_FOLDER_OBJECTS", "1")

    with pytest.raises(ValidationError):
        catalog.transfer_node(project["node_id"], OTHER_LIBRARY)

    assert catalog.node(project["node_id"])["lib"] == CATALOG_LIBRARY


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
