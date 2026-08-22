import pytest

from studio_core import config
from studio_core.errors import ForbiddenError, NotFoundError, ValidationError
from studio_core.services import browse, catalog, manage
from tests.conftest import CATALOG_LIBRARY

# Every listing test drives `catalog_tree`: the rows say what exists and the
# bucket holds the bytes `presign` signs for. Before #309 these ran on
# `media_bucket` alone, because a listing *was* a bucket listing.


def _node_id(prefix):
    """The node one fixture path names, resolved without going through `browse`.

    A test that took the id out of a `browse` response would let a listing agree
    with its own mistake about which folder it was showing.
    """
    node_id = catalog.library(CATALOG_LIBRARY)["root_node"]
    for name in [segment for segment in prefix.split("/") if segment]:
        node_id = catalog.child_by_name(node_id, name)["node_id"]
    return node_id


def _unsigned(value):
    """A response with its presigned URLs dropped.

    Two calls sign two different URLs — the signature covers a timestamp — so
    comparing whole responses has to leave them out. Everything else is
    compared, which is the point.
    """
    if isinstance(value, dict):
        return {key: _unsigned(item) for key, item in value.items() if key != "url"}
    if isinstance(value, list):
        return [_unsigned(item) for item in value]
    return value


def test_root_lists_the_top_level(catalog_tree):
    result = browse.list_folder(CATALOG_LIBRARY)
    # The browsable root is the library's root node. It answers to the empty
    # prefix, which is what the SPA opens on.
    assert result["prefix"] == ""
    # Newest-first, and a folder now has a real timestamp to sort by: these were
    # created in fixture order, so newest is the reverse of it.
    assert [f["name"] for f in result["folders"]] == ["projects", "phrasebook", "characters"]
    assert result["sort"] == "newest"
    assert result["files"] == []


def test_subject_folder_lists_its_profile_and_subfolders(catalog_tree):
    result = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/")
    assert [f["name"] for f in result["files"]] == ["profile.yaml"]
    # **`reference` first, where the old listing put `seed` first.** A folder used
    # to have no date at all, so `newest` fell back to the name descending; the
    # fixture creates `seed` before `reference`, so a real timestamp reverses
    # them. This is the change #311 asks for, seen from the outside.
    assert [f["name"] for f in result["folders"]] == ["reference", "seed"]


def test_a_folder_marker_is_a_folder_and_never_a_file(catalog_tree):
    """`characters/subject-a/seed/` is a zero-byte object in the bucket.

    It was a file in every S3 listing that returned it and had to be filtered
    out by size. In the catalog there is nothing for it to be but the folder it
    was faking, so the filter — and `keys.is_folder_marker` with it — is gone.
    """
    parent = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/")
    assert "seed" in [f["name"] for f in parent["folders"]]

    result = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/", "name")
    assert [f["name"] for f in result["files"]] == ["subject-a_1.webp", "subject-a_2.webp"]


def test_a_listing_carries_the_size_off_the_record(catalog_tree):
    """The `BatchGetItem` is not optional, and this is what proves it happened.

    `catalog.children` returns the by-parent projection — `node_id`, `lib`,
    `kind`, `path`, `created_at` — which has no `size`, no `content_type` and no
    `blob_key`. A listing built from it alone would report every file as 0 B and
    could not sign a URL at all. Widening that projection is the tempting fix and
    the wrong one (#280): it puts a mutable copy of a file's metadata on a second
    item that every rename and every text edit then has to keep in step.
    """
    entry = _entry("characters/subject-a/seed/", "subject-a_1.webp")

    assert entry["size"] == len(b"webp-bytes")
    assert entry["content_type"] == "application/octet-stream"
    assert "X-Amz-Signature" in entry["url"]


def test_listing_presigns_every_file(catalog_tree):
    result = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/")
    assert all(f["kind"] == "image" for f in result["files"])
    assert all("X-Amz-Signature" in f["url"] for f in result["files"])


def test_a_file_row_with_no_blob_lists_without_a_url(catalog_tree, catalog_table):
    """A row pointing at nothing lists, and signs nothing.

    `create_node` cannot make one — it mints `blobs/<node_id>` for a file given
    no key — so this is written by hand, which is also the only way one exists.
    Signing for a key that is not there would put a broken tile in the grid where
    an item with no preview belongs.
    """
    parent = _node_id("characters/subject-a/seed/")
    for item in (
        {"pk": {"S": "NODE#node-keyless"}, "sk": {"S": "META"}},
        {"pk": {"S": f"NODE#{parent}"}, "sk": {"S": "NAME#keyless.webp"}},
    ):
        catalog_table.put_item(
            TableName=config.catalog_table(),
            Item={
                **item,
                "node_id": {"S": "node-keyless"},
                "parent_id": {"S": parent},
                "lib": {"S": CATALOG_LIBRARY},
                "name": {"S": "keyless.webp"},
                "kind": {"S": "file"},
                "path": {"S": "/whatever/"},
                "created_at": {"S": "2026-08-19T13:00:00.000000+00:00"},
                "updated_at": {"S": "2026-08-19T13:00:00.000000+00:00"},
            },
        )

    entry = next(
        f
        for f in browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/")["files"]
        if f["name"] == "keyless.webp"
    )
    assert "url" not in entry
    assert entry["size"] == 0


def test_run_folder_mixes_media_and_metadata(catalog_tree):
    result = browse.list_folder(
        CATALOG_LIBRARY, "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/"
    )
    kinds = {f["name"]: f["kind"] for f in result["files"]}
    assert kinds == {"request.json": "text", "result.json": "text"}
    assert [f["name"] for f in result["folders"]] == ["output"]
    # Text files carry a highlighting hint for the read-only viewer.
    assert all(f["language"] == "json" for f in result["files"])


def test_breadcrumbs_and_counts(catalog_tree):
    result = browse.list_folder(CATALOG_LIBRARY, "projects/subject-b/")
    assert [b["name"] for b in result["breadcrumbs"]] == ["/", "projects", "subject-b"]
    assert [b["prefix"] for b in result["breadcrumbs"]] == [
        "",
        "projects/",
        "projects/subject-b/",
    ]
    assert result["counts"]["folders"] == 2
    assert result["counts"]["media"] == 0


def test_breadcrumbs_are_walked_from_the_node_not_the_request(catalog_tree):
    """The same trail comes back when the caller sent no path at all.

    Which is the whole reason `_breadcrumbs` walks `parent_id`: under `?node=`
    there is no string to split.
    """
    scene = "projects/subject-b/scenes/2026-08-16_07-40-22_stadium-encounter/"
    by_path = browse.list_folder(CATALOG_LIBRARY, scene)
    by_id = browse.list_folder(CATALOG_LIBRARY, node_id=_node_id(scene))

    # The whole body, not just the crumbs: `?node=` and `?prefix=` are two
    # addresses for one folder and must not be two answers.
    assert _unsigned(by_id) == _unsigned(by_path)
    assert [b["name"] for b in by_id["breadcrumbs"]] == [
        "/",
        "projects",
        "subject-b",
        "scenes",
        "2026-08-16_07-40-22_stadium-encounter",
    ]
    assert by_id["prefix"] == scene


def test_the_reel_answers_to_either_address_too(catalog_tree):
    prefix = "characters/subject-a/"
    assert _unsigned(browse.reel_items(CATALOG_LIBRARY, prefix)) == _unsigned(
        browse.reel_items(CATALOG_LIBRARY, node_id=_node_id(prefix))
    )


def test_an_unknown_path_segment_is_a_404(catalog_tree):
    with pytest.raises(NotFoundError):
        browse.list_folder(CATALOG_LIBRARY, "characters/nobody/")


def test_a_traversal_segment_is_just_a_name_nothing_is_called(catalog_tree):
    """`..` used to be refused by `keys.clean_prefix` before it could be looked up.

    It is now looked up, and finds nothing — `keys.clean_name` refuses a `..` on
    the way in, so no stored name can be one. The refusal moved from a string
    rule to the data.
    """
    with pytest.raises(NotFoundError):
        browse.list_folder(CATALOG_LIBRARY, "../elsewhere")


def test_a_node_in_another_library_is_refused(catalog_tree, catalog_table):
    """The guard `?node=` needs and `?prefix=` never did.

    A path walk starts at this library's root and cannot leave it. An id is
    shareable, so the node's own `lib` is what is checked — the rule
    `routes/nodes` states, applied to the one route that can now be handed a
    foreign id.
    """
    catalog_table.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": "NODE#node-elsewhere"},
            "sk": {"S": "META"},
            "node_id": {"S": "node-elsewhere"},
            "lib": {"S": "lib-0002"},
            "name": {"S": "borrowed"},
            "kind": {"S": "folder"},
            "path": {"S": "/node-other-root/"},
            "created_at": {"S": "2026-08-19T13:00:00.000000+00:00"},
            "updated_at": {"S": "2026-08-19T13:00:00.000000+00:00"},
        },
    )

    with pytest.raises(ForbiddenError):
        browse.list_folder(CATALOG_LIBRARY, node_id="node-elsewhere")


def test_prefix_and_node_together_is_refused(catalog_tree):
    """Two addresses that can disagree, so neither is guessed at."""
    with pytest.raises(ValidationError):
        browse.list_folder(
            CATALOG_LIBRARY,
            "characters/subject-a/",
            node_id=_node_id("characters/subject-a/"),
        )


def test_reel_walks_recursively(catalog_tree):
    result = browse.reel_items(CATALOG_LIBRARY, "characters/subject-a/")
    # One reference image and two seeds — the .txt caption, the profile YAML and
    # the folder marker's row are all excluded. Newest first, and the fixture
    # creates the seeds before the reference image, so the reference leads.
    assert [item["key"] for item in result["items"]] == [
        "characters/subject-a/reference/subject-a_1.webp",
        "characters/subject-a/seed/subject-a_2.webp",
        "characters/subject-a/seed/subject-a_1.webp",
    ]
    assert result["next_cursor"] is None
    assert result["total"] == 3
    assert result["truncated"] is False


def test_reel_from_root_spans_characters_and_projects(catalog_tree):
    result = browse.reel_items(CATALOG_LIBRARY)
    kinds = [item["kind"] for item in result["items"]]
    assert set(kinds) == {"image", "video"}
    assert any(item["name"] == "IMG_1966_Original.JPG" for item in result["items"])
    assert any(item["name"] == "standing-flex.mp4" for item in result["items"])
    assert any(item["name"] == "shot-01.mp4" for item in result["items"])


def test_reel_items_carry_their_full_name_path(catalog_tree):
    """A reel row's `key` names where it lives, composed from the rows read.

    The row itself carries ancestor *ids*; a client is owed names, and the
    enumeration already read every folder in the branch.
    """
    item = next(
        i
        for i in browse.reel_items(CATALOG_LIBRARY)["items"]
        if i["name"] == "shot-01.mp4"
    )
    assert item["key"] == (
        "projects/subject-b/scenes/2026-08-16_07-40-22_stadium-encounter/shots/shot-01.mp4"
    )


# ---------------------------------------------------------------------------
# The two file-at-a-time reads
#
# `/api/asset` and `/api/text` took `?node=` in #432 and stopped being the last
# path between a query string and `GetObject` — with one exception these tests
# pin down deliberately, because it is the reason `keys.clean_key` survived
# #312: `/api/asset?key=` is still a raw S3 key, and shared material with no
# catalog node is why.
# ---------------------------------------------------------------------------


def _minted(media_bucket, parent, name, body, *, content_type=None):
    """A file written the way #294 writes one: a `blobs/<node-id>` key.

    The shape the whole of #432 is about. Everything in `catalog_tree` carries a
    pre-catalog `blob_key` that happens to equal its name path, so a route
    reading the name path off the wire agrees with it by accident — a fixture
    that could not tell the bug from correct behaviour.
    """
    record = catalog.create_node(_node_id(parent), name, catalog.KIND_FILE)
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=record["blob_key"], Body=body
    )
    catalog.set_blob(
        record["node_id"], record["blob_key"], size=len(body), content_type=content_type
    )
    assert record["blob_key"].startswith("blobs/")
    return record


def test_asset_url_by_node_inline_and_attachment(catalog_tree):
    node_id = _node_id(
        "projects/subject-b/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"
    )

    inline = browse.asset_url(CATALOG_LIBRARY, None, "inline", node_id=node_id)
    assert inline["kind"] == "video"
    assert inline["size"] == len(b"mp4-bytes")
    assert "response-content-disposition" not in inline["url"]
    # The name path, never `blob_key`, and never the id it was addressed by.
    assert inline["key"] == (
        "projects/subject-b/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"
    )
    assert inline["name"] == "standing-flex.mp4"

    attachment = browse.asset_url(CATALOG_LIBRARY, None, "attachment", node_id=node_id)
    assert "response-content-disposition" in attachment["url"]
    assert "standing-flex.mp4" in attachment["url"]


def test_asset_url_by_node_reaches_a_blob_a_name_path_cannot(catalog_tree):
    """#432, stated as the thing that was broken.

    A row minted by the upload routes keeps its bytes at `blobs/<node-id>`. The
    old `?key=` read signed the string a listing called `key`, which for this row
    names no object at all — so the download button on anything uploaded since
    #294 signed a URL onto nothing.
    """
    media_bucket, _ = catalog_tree
    record = _minted(media_bucket, "characters/subject-a/seed/", "minted.webp", b"webp")

    signed = browse.asset_url(CATALOG_LIBRARY, None, None, node_id=record["node_id"])
    assert signed["key"] == "characters/subject-a/seed/minted.webp"
    assert signed["size"] == len(b"webp")
    # The blob key is what got signed, and it never appears in the answer.
    assert "blobs/" in signed["url"]
    assert "blobs/" not in signed["key"]

    # The same request addressed the old way finds nothing, which is the bug.
    with pytest.raises(NotFoundError):
        browse.asset_url(CATALOG_LIBRARY, "characters/subject-a/seed/minted.webp", None)


def test_asset_url_by_key_signs_material_that_has_no_node(catalog_tree, media_bucket):
    """The one raw S3 key left, and the reason it is left.

    `phrasebook/wording.yaml` and the `config/pose/` plates belong to no character
    and no project, `catalog_seed` records no node for them, and the pipeline
    reads them over this route. An object with no row is exactly that case, and
    it must still sign — which is what keeps `keys.clean_key` alive.
    """
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key="config/pose/body/stand.png", Body=b"plate"
    )
    signed = browse.asset_url(CATALOG_LIBRARY, "config/pose/body/stand.png", None)

    assert signed["key"] == "config/pose/body/stand.png"
    assert signed["name"] == "stand.png"
    assert signed["kind"] == "image"
    assert signed["size"] == len(b"plate")


def test_asset_url_refuses_a_key_and_a_node_together(catalog_tree):
    with pytest.raises(ValidationError):
        browse.asset_url(
            CATALOG_LIBRARY,
            "characters/subject-a/profile.yaml",
            None,
            node_id=_node_id("characters/subject-a/profile.yaml"),
        )


def test_asset_url_rejects_a_bad_disposition_before_it_reads_anything(catalog_tree):
    """Checked first, so a bad disposition is a 400 even on a key that is a 404."""
    with pytest.raises(ValidationError):
        browse.asset_url(CATALOG_LIBRARY, "nothing/at/all.png", "evil")


def test_asset_url_on_a_folder_is_a_validation_error(catalog_tree):
    """The node is there; the request does not apply to it.

    Same answer `GET /api/nodes/<id>/download-url` gives, deliberately — two
    routes signing one node's bytes must not disagree about what a folder is.
    """
    with pytest.raises(ValidationError):
        browse.asset_url(
            CATALOG_LIBRARY, None, None, node_id=_node_id("characters/subject-a/seed/")
        )


def test_asset_url_on_a_placeholder_is_not_found(catalog_tree, catalog_table):
    """A row #294 minted whose upload never landed. There is nothing to sign."""
    parent = _node_id("characters/subject-a/seed/")
    record = catalog.create_node(parent, "pending.webp", catalog.KIND_FILE)
    catalog_table.update_item(
        TableName=config.catalog_table(),
        Key={"pk": {"S": f"NODE#{record['node_id']}"}, "sk": {"S": "META"}},
        UpdateExpression="REMOVE blob_key",
    )

    with pytest.raises(NotFoundError):
        browse.asset_url(CATALOG_LIBRARY, None, None, node_id=record["node_id"])


def test_asset_url_on_another_librarys_node_is_forbidden(catalog_tree):
    """The node's own `lib` is the guard, because a node id is shareable."""
    node_id = _node_id("characters/subject-a/profile.yaml")
    with pytest.raises(ForbiddenError):
        browse.asset_url("lib-someone-else", None, None, node_id=node_id)


def test_text_object_by_name_path(catalog_tree):
    result = browse.text_object(
        CATALOG_LIBRARY,
        "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/request.json",
    )
    assert result["language"] == "json"
    assert result["content"] == '{"model": "x"}'
    assert result["truncated"] is False


def test_text_object_by_node_answers_identically(catalog_tree):
    """Same body either way, which is the contract `?node=` was added under."""
    path = "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/request.json"
    assert browse.text_object(CATALOG_LIBRARY, path) == browse.text_object(
        CATALOG_LIBRARY, None, node_id=_node_id(path)
    )


def test_text_object_reads_yaml(catalog_tree):
    """Profiles and the phrasebook are YAML now, where they used to be markdown."""
    result = browse.text_object(CATALOG_LIBRARY, "phrasebook/wording.yaml")
    assert result["language"] == "yaml"
    assert result["content"] == "greeting: hello\n"


def test_text_object_truncates(catalog_tree, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 4)
    result = browse.text_object(CATALOG_LIBRARY, "characters/subject-a/profile.yaml")
    assert result["truncated"] is True
    assert len(result["content"]) == 4


def test_text_object_refuses_a_key_and_a_node_together(catalog_tree):
    with pytest.raises(ValidationError):
        browse.text_object(
            CATALOG_LIBRARY,
            "characters/subject-a/profile.yaml",
            node_id=_node_id("characters/subject-a/profile.yaml"),
        )


def test_text_object_refuses_a_binary_file(catalog_tree):
    with pytest.raises(ValidationError):
        browse.text_object(CATALOG_LIBRARY, "characters/subject-a/seed/subject-a_1.webp")


def test_text_object_refuses_a_folder(catalog_tree):
    with pytest.raises(ValidationError):
        browse.text_object(CATALOG_LIBRARY, "characters/subject-a/seed/")


def test_reading_text_finds_what_saving_text_wrote(catalog_tree):
    """#432 in one assertion: the read and the write address the same node.

    Both take a name path; before this the save resolved it against the catalog
    and the read `GetObject`d it, so on a `blobs/<node-id>` file the editor could
    save a file it could not then re-open. Reaching into `manage` is the point —
    the pair is what was broken, so the test has to exercise the pair.
    """
    media_bucket, _ = catalog_tree
    record = _minted(
        media_bucket,
        "characters/subject-a/",
        "notes.md",
        b"# before\n",
        content_type="text/markdown",
    )

    manage.update_text(CATALOG_LIBRARY, "characters/subject-a/notes.md", "# after\n")
    reread = browse.text_object(CATALOG_LIBRARY, "characters/subject-a/notes.md")

    assert reread["content"] == "# after\n"
    assert reread["key"] == "characters/subject-a/notes.md"
    assert reread["name"] == "notes.md"
    assert browse.text_object(
        CATALOG_LIBRARY, None, node_id=record["node_id"]
    ) == reread


# ---------------------------------------------------------------------------
# Ordering
#
# The date orders used to tie across the whole fixture: S3's LastModified has
# one-second resolution and every object was written inside one second, so
# `_sort_files` broke ties on the full key in a second pass. `created_at` is a
# microsecond timestamp, so there is nothing left to tie and the tie-break is
# gone. What these assert is that the date orders are now genuinely dates.
# ---------------------------------------------------------------------------


def test_sort_by_name_and_name_desc(catalog_tree):
    ascending = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/", "name")
    descending = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/", "name_desc")

    assert [f["name"] for f in ascending["files"]] == ["subject-a_1.webp", "subject-a_2.webp"]
    assert [f["name"] for f in descending["files"]] == ["subject-a_2.webp", "subject-a_1.webp"]
    assert [f["name"] for f in ascending["folders"]] == []


def test_folders_follow_the_sort(catalog_tree):
    assert [f["name"] for f in browse.list_folder(CATALOG_LIBRARY, None, "name")["folders"]] == [
        "characters",
        "phrasebook",
        "projects",
    ]
    assert [f["name"] for f in browse.list_folder(CATALOG_LIBRARY, None, "oldest")["folders"]] == [
        "characters",
        "phrasebook",
        "projects",
    ]


def test_a_folder_date_sort_is_a_date_and_not_the_name(catalog_tree):
    """The retirement of "a folder has no LastModified", asserted directly.

    A folder created last but named first sorts first under `name` and last under
    `oldest`. Under the old name-fallback the two were the same answer.
    """
    catalog.create_node(
        catalog.library(CATALOG_LIBRARY)["root_node"], "aaa-newest", catalog.KIND_FOLDER
    )

    newest = [f["name"] for f in browse.list_folder(CATALOG_LIBRARY, None, "newest")["folders"]]
    by_name = [f["name"] for f in browse.list_folder(CATALOG_LIBRARY, None, "name")["folders"]]

    assert newest[0] == "aaa-newest"
    assert by_name[0] == "aaa-newest"
    assert by_name[-1] == "projects"
    # And the one that carries the weight: oldest-first puts it last, despite the
    # name that would have put it first.
    oldest = [f["name"] for f in browse.list_folder(CATALOG_LIBRARY, None, "oldest")["folders"]]
    assert oldest[-1] == "aaa-newest"


def test_sort_rejects_anything_else(catalog_tree):
    with pytest.raises(ValidationError):
        browse.list_folder(CATALOG_LIBRARY, None, "sideways")


def test_newest_first_puts_a_later_write_first(catalog_tree):
    """No `sleep` any more, and that is the point.

    This test used to wait 1.05 seconds before writing, because S3's
    LastModified had no sub-second component and a second write inside the same
    second was indistinguishable from the first. `catalog._now` stamps
    microseconds.
    """
    seed = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/", "name")
    seed_id = next(f["id"] for f in seed["folders"] if f["name"] == "seed")
    catalog.create_node(seed_id, "subject-a_0_written_last.webp", catalog.KIND_FILE)

    newest = [
        f["name"]
        for f in browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/", "newest")["files"]
    ]
    oldest = [
        f["name"]
        for f in browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/", "oldest")["files"]
    ]

    # Name-ascending would have put it first anyway, so the assertion that
    # carries weight is the *oldest* one: it sorts last there despite its name.
    assert newest[0] == "subject-a_0_written_last.webp"
    assert oldest[-1] == "subject-a_0_written_last.webp"


def test_the_reel_orders_by_the_timestamp_it_reports(catalog_tree):
    """What replaced the key tie-break.

    The fixture's objects are all written inside one second, so under S3 this
    order was decided entirely by the full key and `IMG_1966_Original.JPG` was
    the case that told a key from a basename. There are no ties now: every row
    is a distinct instant, and the order is the one the entries display.
    """
    items = browse.reel_items(CATALOG_LIBRARY, "characters/")["items"]

    stamps = [item["last_modified"] for item in items]
    assert stamps == sorted(stamps, reverse=True)
    assert len(set(stamps)) == len(stamps)


def test_reel_cursor_is_an_offset(catalog_tree):
    first = browse.reel_items(CATALOG_LIBRARY, None, None, 2)
    assert len(first["items"]) == 2
    assert first["next_cursor"] == "2"

    second = browse.reel_items(CATALOG_LIBRARY, None, "2", 2)
    assert first["total"] == second["total"]
    # No overlap: the window moved rather than being re-cut from the start.
    assert not {i["key"] for i in first["items"]} & {i["key"] for i in second["items"]}


def test_reel_presigns_only_the_page_it_returns(catalog_tree):
    page = browse.reel_items(CATALOG_LIBRARY, None, None, 1)
    assert len(page["items"]) == 1
    assert "X-Amz-Signature" in page["items"][0]["url"]


def test_reel_rejects_a_bad_cursor(catalog_tree):
    with pytest.raises(ValidationError):
        browse.reel_items(CATALOG_LIBRARY, None, "not-a-number")


def test_reel_reports_a_truncated_enumeration(catalog_tree, monkeypatch):
    """The reel truncates where a move or a delete refuses, on the same number."""
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 2)
    assert browse.reel_items(CATALOG_LIBRARY)["truncated"] is True


def test_a_truncated_reel_keeps_the_newest(catalog_tree, monkeypatch):
    """Why `by-recent` is read descending rather than in tree order.

    A cut has to drop *something*, and the only safe something for a reel is the
    tail it was never going to scroll to. A `by-path` query cut at the same
    number drops an arbitrary branch instead, which is why the library root does
    not use one.
    """
    newest = browse.reel_items(CATALOG_LIBRARY)["items"][0]

    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 4)
    cut = browse.reel_items(CATALOG_LIBRARY)

    assert cut["truncated"] is True
    assert cut["items"][0]["key"] == newest["key"]


def test_a_truncated_reel_still_names_its_folders(catalog_tree, monkeypatch):
    """A row can survive a cut its ancestors did not — `by-recent` keeps the newest.

    The name path is then composed from a batched read rather than from the
    enumeration, and this is the only case that reaches it.
    """
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 3)
    items = browse.reel_items(CATALOG_LIBRARY)["items"]

    assert items
    for item in items:
        assert "node-" not in item["key"], item["key"]


# ---------------------------------------------------------------------------
# What a listing carries, and what it must never carry
# ---------------------------------------------------------------------------


def _entry(prefix, name):
    return next(
        f for f in browse.list_folder(CATALOG_LIBRARY, prefix)["files"] if f["name"] == name
    )


def test_a_listing_carries_no_favourites_fields(catalog_tree):
    entry = _entry(
        "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/output/", "wave-porch.jpeg"
    )

    assert "favorites_prefix" not in entry
    assert "favorited" not in entry
    # The fields a listing does carry, unchanged.
    assert entry["kind"] == "image"
    assert entry["key"].endswith("wave-porch.jpeg")


def test_the_reel_carries_no_favourites_fields_either(catalog_tree):
    """The reel used to list every favourites folder on a page to light stars.

    A page is 200 items across however many projects, so that was one extra S3
    listing per project per page, spent on a question nothing asks any more.
    """
    items = browse.reel_items(CATALOG_LIBRARY, "projects/subject-a/")["items"]

    assert items, "the reel still lists the media"
    assert all("favorites_prefix" not in item and "favorited" not in item for item in items)


def test_every_row_carries_its_node_id(catalog_tree):
    """What a client needs to address a node without resolving a path (#313).

    Files, folders and reel items alike — a listing that carried ids for two of
    the three would send the SPA back to `/api/resolve` for the third.
    """
    listing = browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/")
    reel = browse.reel_items(CATALOG_LIBRARY)

    rows = listing["files"] + listing["folders"] + reel["items"]
    assert rows
    for row in rows:
        assert row["id"].startswith("node-"), row


def _keys_in(value):
    """Every attribute name anywhere in a response, however deeply nested."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys_in(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys_in(item)}
    return set()


def test_no_browse_response_carries_a_blob_key_or_a_path(catalog_tree):
    """The rule `routes/nodes._view` states, asserted over `browse`'s responses.

    `blob_key` is withheld because prod holds pre-catalog keys beside
    `blobs/<node_id>` keys, and both stay correct forever only while nothing
    outside `services.catalog` parses one. `path` is withheld for the weaker
    reason: it is a materialised index of ancestor ids that a move rebuilds, and
    a client consuming it would depend on an index this service reserves the
    right to rewrite.

    Both leak the same way — somebody spreads a whole record into an entry — so
    this asserts over every shape `browse` returns rather than over one.
    """
    responses = [
        browse.list_folder(CATALOG_LIBRARY),
        browse.list_folder(CATALOG_LIBRARY, "characters/subject-a/seed/"),
        browse.list_folder(CATALOG_LIBRARY, node_id=_node_id("projects/subject-b/")),
        browse.reel_items(CATALOG_LIBRARY),
        browse.reel_items(CATALOG_LIBRARY, "characters/"),
    ]

    for response in responses:
        found = _keys_in(response)
        assert "blob_key" not in found
        assert "path" not in found
        # Present, so the test is looking at populated responses rather than
        # passing on three empty dicts.
        assert "id" in found
