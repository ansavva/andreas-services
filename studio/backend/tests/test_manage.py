"""The write half of the API, now that it writes the catalog (#316, #317, #319).

**These assert against rows, and against the bucket only where bytes are the
point.** Between #309 and here the two disagreed: listings came from the catalog
while the writes copied objects, so these tests had to read S3 directly to see
anything at all — the header of this file used to say so and call it the
migration. Both halves are one write again, so the assertions are back on the
thing a user sees, which is the tree.

What is asserted about S3 is now the opposite question: for a create, a rename
and a move, that **nothing at all** was called on it. That is checked with a stub
client rather than by comparing bucket listings either side, because a listing
that matches is also what a copy followed by a delete produces — the outcome
these three operations are supposed to have stopped costing.
"""

import pytest

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, UpstreamError, ValidationError
from studio_core.services import catalog, manage
from tests.conftest import CATALOG_LIBRARY

LIB = CATALOG_LIBRARY

RUN = "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/"
OUTPUT = f"{RUN}output/wave-porch.jpeg"
VIDEO = "projects/subject-b/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"
SEED = "characters/subject-a/seed/"


# ---------------------------------------------------------------------------
# Reading the tree back, without going through the code under test
#
# Resolved the long way — root node, then one `child_by_name` per segment — for
# `test_browse._node_id`'s reason: a test that took its ids out of a `manage`
# response would let a write agree with its own mistake about where it wrote.
# ---------------------------------------------------------------------------


def _node(path):
    """The record a name path names."""
    node_id = catalog.library(LIB)["root_node"]
    for name in [segment for segment in path.split("/") if segment]:
        node_id = catalog.child_by_name(node_id, name)["node_id"]
    return catalog.node(node_id)


def _children(prefix, kind):
    return sorted(
        entry["name"]
        for entry in catalog.children(_node(prefix)["node_id"])
        if entry["kind"] == kind
    )


def _names(prefix):
    """The file names one folder holds."""
    return _children(prefix, catalog.KIND_FILE)


def _folders(prefix):
    """The folder names one folder holds."""
    return _children(prefix, catalog.KIND_FOLDER)


def _missing(path):
    """Whether a name path resolves to nothing."""
    try:
        _node(path)
    except NotFoundError:
        return True
    return False


def _objects(client):
    """Every key in the bucket."""
    listing = client.list_objects_v2(Bucket=config.media_bucket())
    return {obj["Key"] for obj in listing.get("Contents", [])}


# ---------------------------------------------------------------------------
# The stub that proves an operation touched no bytes
# ---------------------------------------------------------------------------


class _S3Spy:
    """Stands in for the boto3 S3 client and records every call by name.

    A stub rather than a bucket listing taken either side, because a listing is
    the one thing that cannot tell these apart: copy-then-delete leaves the same
    objects behind as doing nothing, and copy-then-delete is exactly what a
    rename and a move used to be. Recording the call names asserts the *absence
    of the work*, not the sameness of the result.
    """

    def __init__(self):
        self.calls: list[str] = []

    def __getattr__(self, name):
        def record(**_kwargs):
            self.calls.append(name)
            return {}

        return record


@pytest.fixture
def s3_calls(monkeypatch):
    """Every S3 API call the service makes while this is in force."""
    spy = _S3Spy()
    monkeypatch.setattr(s3, "client", lambda: spy)
    return spy


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_folder(catalog_tree):
    result = manage.create_folder(LIB, "characters/subject-a/", "keepers")

    assert result == {"prefix": "characters/subject-a/keepers/", "name": "keepers"}
    assert "keepers" in _folders("characters/subject-a/")
    assert _node("characters/subject-a/keepers/")["kind"] == catalog.KIND_FOLDER


def test_create_folder_writes_no_object(catalog_tree, s3_calls):
    """The zero-byte marker is gone, and a folder is visible without one (#316)."""
    manage.create_folder(LIB, "characters/subject-a/", "keepers")

    assert s3_calls.calls == []
    assert "keepers" in _folders("characters/subject-a/")


def test_created_folder_carries_no_blob(catalog_tree):
    """#280's definition of a folder, asserted at the one place that mints one."""
    manage.create_folder(LIB, "characters/subject-a/", "keepers")

    assert "blob_key" not in _node("characters/subject-a/keepers/")


def test_create_folder_refuses_a_duplicate(catalog_tree):
    with pytest.raises(ConflictError):
        manage.create_folder(LIB, "characters/subject-a/", "seed")


def test_create_folder_refuses_a_path(catalog_tree):
    """`clean_name` refusing a slash is what keeps create from reaching sideways."""
    with pytest.raises(ValidationError):
        manage.create_folder(LIB, "characters/subject-a/", "a/b")


def test_create_folder_under_nothing_is_404(catalog_tree):
    with pytest.raises(NotFoundError):
        manage.create_folder(LIB, "characters/nobody/", "keepers")


def test_create_folder_inside_a_file_is_refused(catalog_tree):
    """A parent must be a folder. Nothing in the key layout says so — this does."""
    with pytest.raises(ValidationError):
        manage.create_folder(LIB, OUTPUT, "keepers")


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_rename_object(catalog_tree):
    result = manage.rename_object(LIB, OUTPUT, "keeper.jpeg")

    assert result == {"key": f"{RUN}output/keeper.jpeg", "name": "keeper.jpeg", "renamed": True}
    assert _names(f"{RUN}output/") == ["keeper.jpeg"]


def test_rename_object_writes_no_object(catalog_tree, s3_calls):
    """A rename is three items in one transaction and no `CopyObject` (#316)."""
    manage.rename_object(LIB, OUTPUT, "keeper.jpeg")

    assert s3_calls.calls == []


def test_rename_object_does_not_move_its_bytes(catalog_tree):
    """The blob key is untouched, which is why the rename costs nothing.

    `catalog.blob_key_for` is deliberately not derived from the name for exactly
    this reason, and prod is full of keys that predate the table besides.
    """
    before = _node(OUTPUT)["blob_key"]
    manage.rename_object(LIB, OUTPUT, "keeper.jpeg")

    assert _node(f"{RUN}output/keeper.jpeg")["blob_key"] == before


def test_rename_object_cannot_leave_its_folder(catalog_tree):
    """A rename takes a name, and a name is one segment. This is the whole line."""
    with pytest.raises(ValidationError):
        manage.rename_object(LIB, OUTPUT, "../escaped.jpeg")
    with pytest.raises(ValidationError):
        manage.rename_object(LIB, OUTPUT, "sub/escaped.jpeg")
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_rename_object_refuses_an_occupied_name(catalog_tree):
    with pytest.raises(ConflictError):
        manage.rename_object(LIB, f"{SEED}subject-a_1.webp", "subject-a_2.webp")
    # Nothing moved, and in particular nothing was overwritten.
    assert _names(SEED) == ["subject-a_1.webp", "subject-a_2.webp"]


def test_rename_object_to_its_own_name_is_a_no_op(catalog_tree):
    result = manage.rename_object(LIB, OUTPUT, "wave-porch.jpeg")

    assert result["renamed"] is False
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_rename_missing_object_is_404(catalog_tree):
    with pytest.raises(NotFoundError):
        manage.rename_object(LIB, f"{SEED}nope.webp", "yes.webp")


def test_rename_object_refuses_a_folder(catalog_tree):
    """`PATCH /api/object` and `PATCH /api/folder` stay two operations."""
    with pytest.raises(ValidationError):
        manage.rename_object(LIB, SEED, "seeds")


def test_rename_object_rejects_a_control_character(catalog_tree):
    with pytest.raises(ValidationError):
        manage.rename_object(LIB, OUTPUT, "keeper\n.jpeg")


def test_rename_folder_leaves_its_subtree_where_it_is(catalog_tree):
    """Renaming a folder rewrites one name and nothing else.

    The old `objects` count is gone from the response rather than reported as
    zero: `path` names ancestors by *id*, a rename changes none of them, and
    there was never a number here worth carrying.
    """
    before = _node(f"{RUN}output/")

    result = manage.rename_folder(LIB, RUN, "wave-porch-final")

    assert result == {
        "prefix": "projects/subject-a/runs/wave-porch-final/",
        "name": "wave-porch-final",
        "renamed": True,
    }
    renamed = "projects/subject-a/runs/wave-porch-final/"
    assert _folders("projects/subject-a/runs/") == ["wave-porch-final"]
    assert _names(renamed) == ["request.json", "result.json"]
    assert _names(f"{renamed}output/") == ["wave-porch.jpeg"]
    # The descendant is the same row, not a rewritten one.
    after = _node(f"{renamed}output/")
    assert after["node_id"] == before["node_id"]
    assert after["path"] == before["path"]


def test_rename_folder_writes_no_object(catalog_tree, s3_calls):
    manage.rename_folder(LIB, RUN, "wave-porch-final")

    assert s3_calls.calls == []


def test_rename_folder_refuses_an_occupied_name(catalog_tree):
    manage.create_folder(LIB, "projects/subject-a/runs/", "taken")
    with pytest.raises(ConflictError):
        manage.rename_folder(LIB, RUN, "taken")
    assert not _missing(RUN)


def test_rename_folder_refuses_the_library_root(catalog_tree):
    """The root has no `parent_id`, so there is no by-parent item to rewrite.

    That is the same refusal `keys.assert_inside_root` made from a string
    comparison, arrived at from the data instead — and it is why the root cannot
    be reached by sending nothing either.
    """
    with pytest.raises(ValidationError):
        manage.rename_folder(LIB, "", "everything")
    with pytest.raises(ValidationError):
        manage.rename_folder(LIB, None, "everything")


def test_rename_folder_refuses_a_file(catalog_tree):
    with pytest.raises(ValidationError):
        manage.rename_folder(LIB, OUTPUT, "keeper")


# ---------------------------------------------------------------------------
# Move
#
# The pairing to keep in mind while reading these: a rename changes the last
# segment and keeps the folder, a move changes the folder and keeps the last
# segment. Neither is reachable from the other, and the first two tests here are
# what hold that line.
# ---------------------------------------------------------------------------


def test_move_objects_keeps_their_names(catalog_tree):
    result = manage.move_objects(LIB, [OUTPUT], "characters/subject-a/")

    assert result == {
        "destination": "characters/subject-a/",
        "moved": 1,
        "skipped": 0,
        "keys": ["characters/subject-a/wave-porch.jpeg"],
    }
    assert "wave-porch.jpeg" in _names("characters/subject-a/")
    assert _names(f"{RUN}output/") == []


def test_move_objects_writes_no_object(catalog_tree, s3_calls):
    """One `parent_id` changes. Zero bytes move (#316)."""
    manage.move_objects(LIB, [OUTPUT], "characters/subject-a/")

    assert s3_calls.calls == []


def test_move_folder_writes_no_object(catalog_tree, s3_calls):
    """The one that used to be a `CopyObject` per key plus a bulk delete."""
    manage.move_folder(LIB, RUN, "projects/misc/runs/")

    assert s3_calls.calls == []


def test_move_objects_cannot_rename_on_the_way(catalog_tree):
    """A destination is a folder that exists, so there is nowhere to put a name.

    Under S3 this was true by construction — `characters/subject-a/renamed.jpeg`
    was read as a *prefix* and the file landed inside a folder of that name,
    which S3 conjured out of the key. A destination is a node now, so the same
    request is a 404: there is no folder called that. The rule is unchanged and
    the refusal is louder.
    """
    with pytest.raises(NotFoundError):
        manage.move_objects(LIB, [OUTPUT], "characters/subject-a/renamed.jpeg")
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_move_objects_refuses_a_file_as_a_destination(catalog_tree):
    """The other half of the same rule: a destination names a folder, or nothing."""
    with pytest.raises(ValidationError):
        manage.move_objects(LIB, [OUTPUT], f"{SEED}subject-a_1.webp")


def test_move_many_objects(catalog_tree):
    result = manage.move_objects(
        LIB,
        [f"{SEED}subject-a_1.webp", f"{SEED}subject-a_2.webp"],
        "characters/subject-b/corpus/",
    )

    assert result["moved"] == 2
    assert _names(SEED) == []
    assert _names("characters/subject-b/corpus/") == [
        "IMG_1966_Original.JPG",
        "subject-a_1.webp",
        "subject-a_2.webp",
    ]


def test_move_objects_skips_ones_already_there(catalog_tree):
    result = manage.move_objects(LIB, ["characters/subject-a/profile.yaml"], "characters/subject-a/")

    assert result == {
        "destination": "characters/subject-a/",
        "moved": 0,
        "skipped": 1,
        "keys": [],
    }
    assert "profile.yaml" in _names("characters/subject-a/")


def test_move_objects_refuses_an_occupied_destination(catalog_tree):
    """The whole request, not the offending file.

    A bulk move that stopped halfway would leave a selection split across two
    folders with nothing to say where the boundary fell.
    """
    with pytest.raises(ConflictError):
        manage.move_objects(
            LIB,
            [OUTPUT, "characters/subject-a/reference/subject-a_1.webp"],
            SEED,
        )
    # Refused whole: neither the conflicting file nor the innocent one moved.
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]
    assert "subject-a_1.webp" in _names("characters/subject-a/reference/")
    assert _names(SEED) == ["subject-a_1.webp", "subject-a_2.webp"]


def test_move_objects_refuses_two_sources_of_the_same_name(catalog_tree):
    """Different folders, same name — one would collide with the other, half-way."""
    with pytest.raises(ConflictError):
        manage.move_objects(
            LIB,
            [
                "characters/subject-a/reference/subject-a_1.webp",
                "characters/subject-b/reference/face/subject-b_face_1.jpeg",
                f"{SEED}subject-a_1.webp",
            ],
            "characters/subject-b/corpus/",
        )
    assert _names("characters/subject-b/corpus/") == ["IMG_1966_Original.JPG"]


def test_move_objects_resolves_every_key_before_moving_any(catalog_tree):
    """A request naming one bad key does nothing at all.

    The refusal is a 404 rather than the 400 the key normaliser used to raise:
    `..` is not traversal to reject any more, it is a name nothing is called.
    """
    with pytest.raises(NotFoundError):
        manage.move_objects(LIB, [OUTPUT, "../outside.jpeg"], "characters/subject-a/")
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_move_objects_refuses_more_than_the_cap(catalog_tree, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.move_objects(LIB, [OUTPUT, VIDEO], "characters/subject-a/")


def test_move_objects_rejects_an_empty_list(catalog_tree):
    with pytest.raises(ValidationError):
        manage.move_objects(LIB, [], "characters/subject-a/")
    with pytest.raises(ValidationError):
        manage.move_objects(LIB, None, "characters/subject-a/")


def test_move_folder_carries_the_whole_subtree(catalog_tree):
    result = manage.move_folder(LIB, RUN, "projects/misc/runs/")

    assert result == {
        "prefix": "projects/misc/runs/2026-08-04_21-30-54_wave-porch-1x1/",
        "name": "2026-08-04_21-30-54_wave-porch-1x1",
        "moved": True,
        # Four rows beneath it: `output`, its jpeg, and the two documents.
        "descendants": 4,
    }
    assert _folders("projects/subject-a/runs/") == []

    moved = "projects/misc/runs/2026-08-04_21-30-54_wave-porch-1x1/"
    assert _names(moved) == ["request.json", "result.json"]
    assert _names(f"{moved}output/") == ["wave-porch.jpeg"]


def test_move_folder_rewrites_descendant_paths(catalog_tree):
    """`path` is the subtree index, and a move is the only thing that rebuilds it.

    Asserted on the deepest node rather than the moved one, because that is the
    row `catalog._rewrite_paths` touches in its second, batched, interruptible
    half — the one an interrupted move would leave behind.
    """
    manage.move_folder(LIB, RUN, "projects/misc/runs/")

    moved = "projects/misc/runs/2026-08-04_21-30-54_wave-porch-1x1/"
    parent = _node(f"{moved}output/")
    leaf = _node(f"{moved}output/wave-porch.jpeg")

    assert leaf["path"] == catalog.child_path(parent)
    # Reachable by the index a reel would use, not merely by walking names.
    branch, _ = catalog.branch(LIB, catalog.child_path(_node(moved)), 100)
    assert leaf["node_id"] in {record["node_id"] for record in branch}


def test_move_folder_to_the_library_root(catalog_tree):
    result = manage.move_folder(LIB, RUN, "")

    assert result["prefix"] == "2026-08-04_21-30-54_wave-porch-1x1/"
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("")


def test_move_folder_into_itself_is_refused(catalog_tree):
    """The subtree would contain its own ancestor.

    Under S3 the same request was a copy loop reading its own output as it wrote
    it. The reason changed; the refusal did not.
    """
    with pytest.raises(ValidationError):
        manage.move_folder(LIB, RUN, RUN)
    with pytest.raises(ValidationError):
        manage.move_folder(LIB, "characters/subject-a/", SEED)
    assert _names(SEED) == ["subject-a_1.webp", "subject-a_2.webp"]


def test_move_folder_beside_a_similarly_named_sibling_is_allowed(catalog_tree):
    """`subject-a-2` is not inside `subject-a`, and a parent pointer is what says so.

    This used to turn on a trailing slash in a `startswith`. It turns on ids now,
    which is one fewer way for a string to be nearly right.
    """
    manage.create_folder(LIB, "characters/", "subject-a-2")
    result = manage.move_folder(LIB, "characters/subject-a/reference/", "characters/subject-a-2/")

    assert result["moved"] is True
    assert "reference" in _folders("characters/subject-a-2/")


def test_move_folder_to_its_own_parent_is_a_no_op(catalog_tree):
    result = manage.move_folder(LIB, RUN, "projects/subject-a/runs/")

    assert result["moved"] is False
    assert result["descendants"] == 0
    assert result["prefix"] == RUN
    assert not _missing(RUN)


def test_move_folder_refuses_an_occupied_destination(catalog_tree):
    manage.create_folder(LIB, "projects/misc/runs/", "2026-08-04_21-30-54_wave-porch-1x1")
    with pytest.raises(ConflictError):
        manage.move_folder(LIB, RUN, "projects/misc/runs/")
    assert not _missing(RUN)


def test_move_folder_refuses_the_library_root(catalog_tree):
    with pytest.raises(ValidationError):
        manage.move_folder(LIB, "", "projects/")
    with pytest.raises(ValidationError):
        manage.move_folder(LIB, None, "projects/")


def test_move_folder_refuses_an_oversized_subtree(catalog_tree, monkeypatch):
    """Bounded before it is applied, and refused rather than truncated.

    `catalog.subtree` counts rows where `manage._subtree` counted objects. The
    number and the reason are the same: a move that ran out of clock half-way
    would leave the tree in two places with nothing to say where the cut fell.
    """
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.move_folder(LIB, RUN, "projects/misc/runs/")
    assert not _missing(RUN)


def test_move_missing_folder_is_404(catalog_tree):
    with pytest.raises(NotFoundError):
        manage.move_folder(LIB, "characters/subject-a/nowhere/", "characters/")


def test_move_names_the_first_missing_segment(catalog_tree):
    """The 404 says which segment was absent, not merely that something was."""
    with pytest.raises(NotFoundError) as raised:
        manage.move_folder(LIB, "characters/nobody/deeper/", "characters/")
    assert str(raised.value) == "characters/nobody"


# ---------------------------------------------------------------------------
# Confinement
# ---------------------------------------------------------------------------


def test_nothing_reaches_outside_the_library(catalog_tree):
    """Every write refuses a path that names something outside the library.

    **The mechanism changed and is stronger.** It used to be
    `config.media_root_prefix` and a `startswith`, which in prod guarded nothing
    at all because the root is the whole bucket — the old version of this test
    had to configure a root to have anything to exclude. Confinement is now
    structural: every walk starts at `catalog.library(lib)["root_node"]` and each
    step is an exact `NAME#` child, so a name path cannot name a node that is not
    beneath that root. There is no prefix to escape.

    The object below is in the bucket and in no library. Nothing here can see it,
    and after all of this it is still there.
    """
    media_bucket, _ = catalog_tree
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key="secrets/keys.txt", Body=b"do not touch"
    )

    for call in (
        lambda: manage.delete_objects(LIB, ["secrets/keys.txt"]),
        lambda: manage.delete_folder(LIB, "secrets/"),
        lambda: manage.rename_folder(LIB, "secrets/", "gone"),
        lambda: manage.rename_object(LIB, "secrets/keys.txt", "gone.txt"),
        lambda: manage.create_folder(LIB, "secrets/", "new"),
        # Both ends of a move are resolved, so neither a source outside the
        # library nor a destination outside it is reachable.
        lambda: manage.move_objects(LIB, ["secrets/keys.txt"], "characters/subject-a/"),
        lambda: manage.move_objects(LIB, ["characters/subject-a/profile.yaml"], "secrets/"),
        lambda: manage.move_folder(LIB, "secrets/", "characters/"),
        lambda: manage.move_folder(LIB, "characters/subject-a/", "secrets/"),
        lambda: manage.update_text(LIB, "secrets/keys.txt", "emptied"),
        # Both ends of a copy too, for the same reasons as a move.
        lambda: manage.copy_objects(LIB, ["secrets/keys.txt"], "characters/subject-a/"),
        lambda: manage.copy_objects(LIB, ["characters/subject-a/profile.yaml"], "secrets/"),
    ):
        with pytest.raises(NotFoundError):
            call()

    body = media_bucket.get_object(Bucket=config.media_bucket(), Key="secrets/keys.txt")
    assert body["Body"].read() == b"do not touch"


def test_a_traversal_segment_is_a_name_nothing_is_called(catalog_tree):
    """`..` is not rejected, it simply resolves to nothing — and that is enough.

    `keys.clean_name` refuses a `..` on the way *in*, so no stored name can be
    one; a lookup for it is an exact sort key that matches no item. Same rule as
    `browse._segments`, same reason.
    """
    for path in ("../outside.jpeg", "characters/../../etc/passwd", "/absolute.jpeg"):
        with pytest.raises(NotFoundError):
            manage.rename_object(LIB, path, "renamed.jpeg")


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

PROFILE = "characters/subject-a/profile.yaml"


def test_update_text_overwrites_the_file(catalog_tree, media_bucket):
    result = manage.update_text(LIB, PROFILE, "name: Subject A\nage: 41\n")

    assert result["language"] == "yaml"
    assert result["bytes"] == len(b"name: Subject A\nage: 41\n")
    stored = media_bucket.get_object(Bucket=config.media_bucket(), Key=_node(PROFILE)["blob_key"])
    assert stored["Body"].read() == b"name: Subject A\nage: 41\n"


def test_update_text_restamps_the_row(catalog_tree):
    """#319: the row's `size` and `updated_at` describe the bytes that were stored.

    A listing reports `size` off the row without re-reading S3, so a save that
    left it alone would put the old length under the new contents — and
    `updated_at` is what every date sort in `browse` orders on.
    """
    before = _node(PROFILE)

    manage.update_text(LIB, PROFILE, "name: Subject A\nage: 41\n")

    after = _node(PROFILE)
    assert after["size"] == len(b"name: Subject A\nage: 41\n")
    assert after["size"] != before["size"]
    assert after["updated_at"] > before["updated_at"]


def test_update_text_writes_a_content_type(catalog_tree, media_bucket):
    manage.update_text(LIB, PROFILE, "name: Subject A\n")

    head = media_bucket.head_object(Bucket=config.media_bucket(), Key=_node(PROFILE)["blob_key"])
    assert head["ContentType"] == "application/yaml"
    assert _node(PROFILE)["content_type"] == "application/yaml"


def test_update_text_accepts_an_empty_file(catalog_tree):
    """Emptying a file is an edit, not a missing field — only `None` is missing."""
    result = manage.update_text(LIB, PROFILE, "")

    assert result["bytes"] == 0
    assert _node(PROFILE)["size"] == 0


def test_update_text_refuses_a_binary_file(catalog_tree):
    with pytest.raises(ValidationError):
        manage.update_text(LIB, OUTPUT, "not a jpeg any more")


def test_update_text_refuses_a_non_string_body(catalog_tree):
    for body in (None, 42, {"name": "Subject A"}):
        with pytest.raises(ValidationError):
            manage.update_text(LIB, PROFILE, body)
    assert _node(PROFILE)["size"] == len(b"name: Subject A\n")


def test_update_text_refuses_a_body_over_the_cap(catalog_tree, media_bucket, monkeypatch):
    """The same cap the read endpoint truncates at.

    That pairing is the point: a file the reader had to truncate must not be
    savable, or the save would delete everything past the cut.
    """
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 8)
    with pytest.raises(ValidationError):
        manage.update_text(LIB, PROFILE, "far too long to fit")

    stored = media_bucket.get_object(Bucket=config.media_bucket(), Key=_node(PROFILE)["blob_key"])
    assert stored["Body"].read() == b"name: Subject A\n"


def test_update_text_counts_bytes_not_characters(catalog_tree, monkeypatch):
    """A cap measured in characters would let a UTF-8 file through at 3× it."""
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 4)
    with pytest.raises(ValidationError):
        manage.update_text(LIB, PROFILE, "héllo")


def test_update_text_cannot_create_a_file(catalog_tree):
    """Studio's only upload is the presigned PUT in `routes/nodes`, not this."""
    with pytest.raises(NotFoundError):
        manage.update_text(LIB, "characters/subject-a/notes.md", "# new")
    assert "notes.md" not in _names("characters/subject-a/")


def test_update_text_refuses_a_node_with_no_blob(catalog_tree):
    """#319: the refusal that keeps "edit" from becoming "upload" moved intact.

    It used to be `s3.exists` on the key. It is now a row that must be a file and
    must carry a blob — a state the key-addressed version could not represent and
    so never had to refuse.

    The row is written straight to the table rather than through `catalog`,
    because `create_node` mints a derived key for every file and there is no
    supported way to make one without: this is the shape of a row written before
    #294, and the point is that this function refuses it rather than uploading
    over it.
    """
    _, catalog_table = catalog_tree
    parent = _node("characters/subject-a/")["node_id"]
    for item in (
        {"pk": {"S": f"NODE#{parent}"}, "sk": {"S": "NAME#notes.md"}},
        {"pk": {"S": "NODE#node-blobless"}, "sk": {"S": "META"}},
    ):
        catalog_table.put_item(
            TableName=config.catalog_table(),
            Item={
                **item,
                "node_id": {"S": "node-blobless"},
                "parent_id": {"S": parent},
                "lib": {"S": LIB},
                "name": {"S": "notes.md"},
                "kind": {"S": "file"},
                "path": {"S": "/"},
                "created_at": {"S": "2026-08-20T00:00:00.000000+00:00"},
            },
        )

    with pytest.raises(NotFoundError):
        manage.update_text(LIB, "characters/subject-a/notes.md", "# new")


def test_update_text_refuses_a_folder(catalog_tree):
    with pytest.raises(ValidationError):
        manage.update_text(LIB, SEED, "# new")


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_one_object(catalog_tree, media_bucket):
    blob_key = _node(OUTPUT)["blob_key"]

    result = manage.delete_objects(LIB, [OUTPUT])

    assert result["deleted"] == 1
    assert _names(f"{RUN}output/") == []
    assert blob_key not in _objects(media_bucket), "no reachable blob is left behind"


def test_delete_removes_the_row_before_the_blob(catalog_tree, media_bucket, monkeypatch):
    """An interrupted delete leaves an orphan blob and no broken row (#317).

    That ordering is the whole design and it is the one half worth testing for
    real: an orphan blob is invisible to every reader and `studio catalog gc`
    (#318) collects it, while a row pointing at a blob that is gone is a broken
    tile in the grid — the failure a person sees.
    """
    blob_key = _node(OUTPUT)["blob_key"]
    monkeypatch.setattr(s3, "delete", _raise)

    with pytest.raises(UpstreamError):
        manage.delete_objects(LIB, [OUTPUT])

    assert _missing(OUTPUT), "the row went first, so nothing points at the orphan"
    assert blob_key in _objects(media_bucket), "the bytes survive, collectable later"


def _raise(*_args, **_kwargs):
    raise UpstreamError("Could not delete the objects")


def test_delete_many_objects(catalog_tree):
    manage.delete_objects(LIB, [f"{SEED}subject-a_1.webp", f"{SEED}subject-a_2.webp"])

    assert _names(SEED) == []


def test_delete_names_one_file_twice(catalog_tree):
    """A row deleted twice is a 404 raised after half the request applied."""
    result = manage.delete_objects(LIB, [OUTPUT, OUTPUT])

    assert result["deleted"] == 1
    assert _names(f"{RUN}output/") == []


def test_delete_rejects_an_empty_list(catalog_tree):
    with pytest.raises(ValidationError):
        manage.delete_objects(LIB, [])
    with pytest.raises(ValidationError):
        manage.delete_objects(LIB, None)


def test_delete_resolves_every_key_before_deleting_any(catalog_tree):
    with pytest.raises(NotFoundError):
        manage.delete_objects(LIB, [OUTPUT, "../outside.jpeg"])
    # The valid key in the same request survived, because nothing ran.
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_delete_refuses_more_than_the_cap(catalog_tree, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.delete_objects(LIB, [OUTPUT, VIDEO])


def test_delete_refuses_a_folder(catalog_tree):
    with pytest.raises(ValidationError):
        manage.delete_objects(LIB, [SEED])
    assert not _missing(SEED)


def test_delete_folder_removes_everything_beneath_it(catalog_tree, media_bucket):
    """`deleted` counts **nodes** now, and folders are among them.

    The run reported three objects and is five rows: itself, `output`, and the
    three files. Both numbers are right about different things, and the row count
    is the one a catalog can state.
    """
    blobs = {
        _node(f"{RUN}{name}")["blob_key"]
        for name in ("request.json", "result.json", "output/wave-porch.jpeg")
    }

    result = manage.delete_folder(LIB, RUN)

    assert result == {"prefix": RUN, "deleted": 5}
    assert _folders("projects/subject-a/runs/") == []
    assert not (blobs & _objects(media_bucket))


def test_delete_folder_refuses_the_library_root(catalog_tree):
    with pytest.raises(ValidationError):
        manage.delete_folder(LIB, "")
    with pytest.raises(ValidationError):
        manage.delete_folder(LIB, None)
    assert _folders("") != []


def test_delete_missing_folder_is_404(catalog_tree):
    with pytest.raises(NotFoundError):
        manage.delete_folder(LIB, "characters/subject-a/nowhere/")


def test_delete_folder_refuses_an_oversized_subtree(catalog_tree, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.delete_folder(LIB, RUN)
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


# ---------------------------------------------------------------------------
# Copy
#
# The only write here that copies bytes, so the source surviving is asserted
# directly. Its one real difference from a move is what happens to a name
# already taken at the destination: numbered, never refused and never
# overwritten.
# ---------------------------------------------------------------------------

SCENE = "projects/subject-b/scenes/2026-08-16_07-40-22_stadium-encounter/"
SHOT = f"{SCENE}shots/shot-01.mp4"
INPUT_POOL = "projects/subject-a/input/"


@pytest.fixture
def input_pool(catalog_tree):
    """A destination folder for the copy tests, and the tree they run against.

    Made rather than assumed, because a folder is a row and there is no longer
    any such thing as a prefix that exists because something was written under
    it.
    """
    manage.create_folder(LIB, "projects/subject-a/", "input")
    return catalog_tree


def test_copy_leaves_the_source_where_it_was(input_pool):
    result = manage.copy_objects(LIB, [OUTPUT], INPUT_POOL)

    assert result == {
        "destination": INPUT_POOL,
        "copied": 1,
        "keys": [f"{INPUT_POOL}wave-porch.jpeg"],
    }
    assert "wave-porch.jpeg" in _names(INPUT_POOL)
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"], "the source is still there"


def test_a_copy_gets_its_own_blob(input_pool):
    """**Load-bearing, not incidental** — `catalog.delete_node` depends on it.

    A second row on one `blob_key` would be cheaper, and copy-on-write is #334.
    Until it lands, `delete_node` reports the keys it removed rows for without
    asking whether anything else still points at them — there is no index on
    `blob_key` — so a shared key means deleting one copy destroys the other's
    bytes. Deleting the copy below and re-reading the source is that failure,
    inverted into a test.
    """
    media_bucket, _ = input_pool
    manage.copy_objects(LIB, [OUTPUT], INPUT_POOL)

    source = _node(OUTPUT)["blob_key"]
    copy = _node(f"{INPUT_POOL}wave-porch.jpeg")["blob_key"]
    assert copy != source

    manage.delete_objects(LIB, [f"{INPUT_POOL}wave-porch.jpeg"])
    assert source in _objects(media_bucket), "deleting the copy kept the original's bytes"


def test_a_copy_carries_the_bytes(input_pool):
    media_bucket, _ = input_pool
    manage.copy_objects(LIB, [OUTPUT], INPUT_POOL)

    stored = media_bucket.get_object(
        Bucket=config.media_bucket(), Key=_node(f"{INPUT_POOL}wave-porch.jpeg")["blob_key"]
    )
    assert stored["Body"].read() == b"jpeg-bytes"
    assert _node(f"{INPUT_POOL}wave-porch.jpeg")["size"] == len(b"jpeg-bytes")


def test_copy_takes_many_at_once_from_anywhere(input_pool):
    """Sources may span projects and trees — only the destination is one folder.

    Favouriting could not do this: it derived a destination per key, so it was
    confined to media inside a project. A copy names its destination, so what a
    source *is* stops mattering.
    """
    result = manage.copy_objects(LIB, [OUTPUT, VIDEO, "characters/subject-a/profile.yaml"], INPUT_POOL)

    assert result["copied"] == 3
    assert _names(INPUT_POOL) == ["profile.yaml", "standing-flex.mp4", "wave-porch.jpeg"]


def test_copying_the_same_file_twice_makes_a_second_copy(input_pool):
    """Ask for a copy, get a copy.

    An earlier version compared byte sizes and skipped an identical file — a copy
    quietly deciding not to copy, which is the same "has this been done already"
    bookkeeping favourites was removed for. Nothing here looks at bytes.
    """
    manage.copy_objects(LIB, [OUTPUT], INPUT_POOL)
    result = manage.copy_objects(LIB, [OUTPUT], INPUT_POOL)

    assert result["keys"] == [f"{INPUT_POOL}wave-porch (2).jpeg"]
    assert _names(INPUT_POOL) == ["wave-porch (2).jpeg", "wave-porch.jpeg"]


def test_copy_numbers_a_name_the_destination_already_holds(input_pool):
    """Every scene calls its first shot `shot-01.mp4`, so this is the normal case."""
    manage.create_folder(LIB, "projects/subject-b/", "spare")
    manage.copy_objects(LIB, [SHOT], "projects/subject-b/spare/")
    manage.copy_objects(LIB, ["projects/subject-b/spare/shot-01.mp4"], INPUT_POOL)

    result = manage.copy_objects(LIB, [SHOT], INPUT_POOL)

    assert result["keys"] == [f"{INPUT_POOL}shot-01 (2).mp4"]
    assert _names(INPUT_POOL) == ["shot-01 (2).mp4", "shot-01.mp4"]


def test_copy_numbers_two_sources_of_one_name_in_a_single_request(input_pool):
    """The in-memory name set has to be updated as the batch is planned.

    Otherwise both files see the same empty folder, both claim `shot-01.mp4`,
    and the second copy silently overwrites the first — the one outcome nothing
    in this module is allowed to produce.
    """
    manage.create_folder(LIB, "projects/subject-b/", "spare")
    manage.copy_objects(LIB, [SHOT], "projects/subject-b/spare/")

    result = manage.copy_objects(
        LIB, [SHOT, "projects/subject-b/spare/shot-01.mp4"], INPUT_POOL
    )

    assert result["copied"] == 2
    assert _names(INPUT_POOL) == ["shot-01 (2).mp4", "shot-01.mp4"]


def test_copy_into_the_folder_a_file_is_already_in_duplicates_it(catalog_tree):
    """A move treats this as a no-op; for a copy it is how you duplicate a file."""
    result = manage.copy_objects(LIB, [OUTPUT], f"{RUN}output/")

    assert result["keys"] == [f"{RUN}output/wave-porch (2).jpeg"]
    assert _names(f"{RUN}output/") == ["wave-porch (2).jpeg", "wave-porch.jpeg"]


def test_copy_of_a_missing_key_is_404(input_pool):
    with pytest.raises(NotFoundError):
        manage.copy_objects(LIB, [f"{RUN}output/never-existed.jpeg"], INPUT_POOL)


def test_copy_of_a_placeholder_is_404(input_pool):
    """A row whose upload never landed has nothing to copy (#294)."""
    placeholder = catalog.create_node(
        _node("characters/subject-a/")["node_id"], "pending.mp4", catalog.KIND_FILE
    )
    assert placeholder["blob_key"], "the row has a key; the object behind it does not exist"

    with pytest.raises(NotFoundError):
        manage.copy_objects(LIB, ["characters/subject-a/pending.mp4"], INPUT_POOL)
    assert _names(INPUT_POOL) == [], "nothing was written before the unreadable source"


def test_copy_refuses_more_than_the_bulk_cap(input_pool, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.copy_objects(LIB, [OUTPUT, VIDEO], INPUT_POOL)


def test_copy_refuses_an_empty_key_list(input_pool):
    with pytest.raises(ValidationError):
        manage.copy_objects(LIB, [], INPUT_POOL)


def test_copy_refuses_a_folder_as_a_source(input_pool):
    """There is still no folder-copy endpoint (#317).

    A subtree copy can be arbitrarily large with no progress to report, so it is
    argued separately rather than reached by passing a folder to this.
    """
    with pytest.raises(ValidationError):
        manage.copy_objects(LIB, [SEED], INPUT_POOL)
