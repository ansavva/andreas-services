"""The write half of the API — still key-addressed, still writing to S3.

These used to assert outcomes through `browse.list_folder`, on the reasoning
that what matters about a rename is that the browser now shows the file under
its new name. **That stopped being available in #309**: a listing reads the
catalog, and nothing in this module writes a row, so a listing would report the
tree these writes have just stopped describing. The helpers below read the
bucket directly instead, which is the only thing these functions change.

That gap is the migration, not a hole in the tests. #316 and #317 move these
verbs onto the catalog, at which point both halves are one write again.
"""

import pytest

from studio_core import config
from studio_core.clients.aws import s3
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import browse, manage

RUN = "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/"
OUTPUT = f"{RUN}output/wave-porch.jpeg"
VIDEO = "projects/subject-b/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"


def _names(prefix):
    """The file basenames one prefix holds, straight off a delimited listing."""
    _, objects = s3.list_folder(prefix)
    return [
        obj["Key"][len(prefix) :]
        for obj in objects
        # The prefix itself and any folder marker come back as zero-byte
        # objects. `manage._folder_names` skips them for the same reason.
        if obj["Key"] != prefix and not obj["Key"].endswith("/")
    ]


def _folders(prefix):
    folders, _ = s3.list_folder(prefix)
    return [folder[len(prefix) :].rstrip("/") for folder in folders]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_folder(media_bucket):
    result = manage.create_folder("characters/subject-a/", "keepers")

    assert result["prefix"] == "characters/subject-a/keepers/"
    assert "keepers" in _folders("characters/subject-a/")
    # The marker object that makes the folder visible must not read as a file.
    assert _names("characters/subject-a/keepers/") == []


def test_create_folder_refuses_a_duplicate(media_bucket):
    with pytest.raises(ConflictError):
        manage.create_folder("characters/subject-a/", "seed")


def test_create_folder_refuses_a_path(media_bucket):
    with pytest.raises(ValidationError):
        manage.create_folder("characters/subject-a/", "a/b")


# ---------------------------------------------------------------------------
# Rename
# ---------------------------------------------------------------------------


def test_rename_object(media_bucket):
    result = manage.rename_object(OUTPUT, "keeper.jpeg")

    assert result["key"] == f"{RUN}output/keeper.jpeg"
    assert _names(f"{RUN}output/") == ["keeper.jpeg"]


def test_rename_object_cannot_leave_its_folder(media_bucket):
    with pytest.raises(ValidationError):
        manage.rename_object(OUTPUT, "../escaped.jpeg")
    with pytest.raises(ValidationError):
        manage.rename_object(OUTPUT, "sub/escaped.jpeg")
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_rename_object_refuses_an_occupied_name(media_bucket):
    with pytest.raises(ConflictError):
        manage.rename_object("characters/subject-a/seed/subject-a_1.webp", "subject-a_2.webp")
    # Nothing moved, and in particular nothing was overwritten.
    assert _names("characters/subject-a/seed/") == ["subject-a_1.webp", "subject-a_2.webp"]


def test_rename_object_to_its_own_name_is_a_no_op(media_bucket):
    result = manage.rename_object(OUTPUT, "wave-porch.jpeg")
    assert result["renamed"] is False
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_rename_missing_object_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.rename_object("characters/subject-a/seed/nope.webp", "yes.webp")


def test_rename_object_rejects_a_control_character(media_bucket):
    with pytest.raises(ValidationError):
        manage.rename_object(OUTPUT, "keeper\n.jpeg")


def test_rename_folder_moves_the_whole_subtree(media_bucket):
    result = manage.rename_folder(RUN, "wave-porch-final")

    assert result["objects"] == 3
    assert "wave-porch-final" in _folders("projects/subject-a/runs/")
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("projects/subject-a/runs/")

    moved = "projects/subject-a/runs/wave-porch-final/"
    assert sorted(_names(moved)) == ["request.json", "result.json"]
    assert _names(f"{moved}output/") == ["wave-porch.jpeg"]


def test_rename_folder_refuses_an_occupied_name(media_bucket):
    manage.create_folder("projects/subject-a/runs/", "taken")
    with pytest.raises(ConflictError):
        manage.rename_folder(RUN, "taken")


def test_rename_folder_refuses_the_library_root(media_bucket):
    with pytest.raises(ValidationError):
        manage.rename_folder("", "everything")
    with pytest.raises(ValidationError):
        manage.rename_folder(None, "everything")


def test_rename_folder_refuses_an_oversized_subtree(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.rename_folder(RUN, "too-big")
    # Refused before it started, so the original is intact.
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/subject-a/runs/")


# ---------------------------------------------------------------------------
# Move
#
# The pairing to keep in mind while reading these: a rename changes the last
# segment and keeps the folder, a move changes the folder and keeps the last
# segment. Neither is reachable from the other, and the first two tests here are
# what hold that line.
# ---------------------------------------------------------------------------


def test_move_objects_keeps_their_names(media_bucket):
    result = manage.move_objects([OUTPUT], "characters/subject-a/")

    assert result["moved"] == 1
    assert result["keys"] == ["characters/subject-a/wave-porch.jpeg"]
    assert "wave-porch.jpeg" in _names("characters/subject-a/")
    assert _names(f"{RUN}output/") == []


def test_move_objects_cannot_rename_on_the_way(media_bucket):
    """A destination is a folder, so there is nowhere to put a new name.

    `characters/subject-a/renamed.jpeg` is read as a *prefix* — the file lands inside
    a folder of that name rather than becoming a file of that name — which is
    the behaviour that keeps move from being a second, sloppier rename.
    """
    manage.move_objects([OUTPUT], "characters/subject-a/renamed.jpeg")

    assert _names("characters/subject-a/renamed.jpeg/") == ["wave-porch.jpeg"]


def test_move_many_objects(media_bucket):
    result = manage.move_objects(
        ["characters/subject-a/seed/subject-a_1.webp", "characters/subject-a/seed/subject-a_2.webp"],
        "characters/subject-b/corpus/",
    )

    assert result["moved"] == 2
    assert _names("characters/subject-a/seed/") == []
    assert sorted(_names("characters/subject-b/corpus/")) == [
        "IMG_1966_Original.JPG",
        "subject-a_1.webp",
        "subject-a_2.webp",
    ]


def test_move_objects_skips_ones_already_there(media_bucket):
    result = manage.move_objects(["characters/subject-a/profile.yaml"], "characters/subject-a/")

    assert result == {
        "destination": "characters/subject-a/",
        "moved": 0,
        "skipped": 1,
        "keys": [],
    }
    assert "profile.yaml" in _names("characters/subject-a/")


def test_move_objects_refuses_an_occupied_destination(media_bucket):
    with pytest.raises(ConflictError):
        manage.move_objects(
            ["characters/subject-a/reference/subject-a_1.webp"], "characters/subject-a/seed/"
        )
    # Refused whole, so neither end moved.
    assert "subject-a_1.webp" in _names("characters/subject-a/reference/")
    assert sorted(_names("characters/subject-a/seed/")) == ["subject-a_1.webp", "subject-a_2.webp"]


def test_move_objects_refuses_two_sources_of_the_same_name(media_bucket):
    """Different folders, same basename — one would land on top of the other."""
    with pytest.raises(ConflictError):
        manage.move_objects(
            [
                "characters/subject-a/reference/subject-a_1.webp",
                "characters/subject-b/reference/face/subject-b_face_1.jpeg",
                "characters/subject-a/seed/subject-a_1.webp",
            ],
            "characters/subject-b/corpus/",
        )
    assert _names("characters/subject-b/corpus/") == ["IMG_1966_Original.JPG"]


def test_move_objects_validates_every_key_before_moving_any(media_bucket):
    with pytest.raises(ValidationError):
        manage.move_objects([OUTPUT, "../outside.jpeg"], "characters/subject-a/")
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_move_objects_refuses_more_than_the_cap(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.move_objects([OUTPUT, VIDEO], "characters/subject-a/")


def test_move_objects_rejects_an_empty_list(media_bucket):
    with pytest.raises(ValidationError):
        manage.move_objects([], "characters/subject-a/")
    with pytest.raises(ValidationError):
        manage.move_objects(None, "characters/subject-a/")


def test_move_folder_carries_the_whole_subtree(media_bucket):
    result = manage.move_folder(RUN, "projects/misc/runs/")

    assert result["objects"] == 3
    assert result["prefix"] == "projects/misc/runs/2026-08-04_21-30-54_wave-porch-1x1/"
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("projects/subject-a/runs/")

    moved = "projects/misc/runs/2026-08-04_21-30-54_wave-porch-1x1/"
    assert sorted(_names(moved)) == ["request.json", "result.json"]
    assert _names(f"{moved}output/") == ["wave-porch.jpeg"]


def test_move_folder_to_the_library_root(media_bucket):
    result = manage.move_folder(RUN, "")

    assert result["prefix"] == "2026-08-04_21-30-54_wave-porch-1x1/"
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("")


def test_move_folder_into_itself_is_refused(media_bucket):
    """The copy loop this prevents would read its own output as it wrote it."""
    with pytest.raises(ValidationError):
        manage.move_folder(RUN, RUN)
    with pytest.raises(ValidationError):
        manage.move_folder("characters/subject-a/", "characters/subject-a/seed/")
    assert sorted(_names("characters/subject-a/seed/")) == ["subject-a_1.webp", "subject-a_2.webp"]


def test_move_folder_beside_a_similarly_named_sibling_is_allowed(media_bucket):
    """`subject-a-2/` does not sit inside `subject-a/`, and the slash is what says so."""
    manage.create_folder("characters/", "subject-a-2")
    result = manage.move_folder("characters/subject-a/reference/", "characters/subject-a-2/")

    assert result["moved"] is True
    assert "reference" in _folders("characters/subject-a-2/")


def test_move_folder_to_its_own_parent_is_a_no_op(media_bucket):
    result = manage.move_folder(RUN, "projects/subject-a/runs/")

    assert result["moved"] is False
    assert result["objects"] == 0
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/subject-a/runs/")


def test_move_folder_refuses_an_occupied_destination(media_bucket):
    manage.create_folder("projects/misc/runs/", "2026-08-04_21-30-54_wave-porch-1x1")
    with pytest.raises(ConflictError):
        manage.move_folder(RUN, "projects/misc/runs/")
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/subject-a/runs/")


def test_move_folder_refuses_the_library_root(media_bucket):
    with pytest.raises(ValidationError):
        manage.move_folder("", "projects/")
    with pytest.raises(ValidationError):
        manage.move_folder(None, "projects/")


def test_move_folder_refuses_an_oversized_subtree(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.move_folder(RUN, "projects/misc/runs/")
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/subject-a/runs/")


def test_move_missing_folder_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.move_folder("characters/subject-a/nowhere/", "characters/")


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

PROFILE = "characters/subject-a/profile.yaml"


def test_update_text_overwrites_the_file(media_bucket):
    result = manage.update_text(PROFILE, "name: Subject A\nage: 41\n")

    assert result["language"] == "yaml"
    assert result["bytes"] == len(b"name: Subject A\nage: 41\n")
    assert browse.text_object(PROFILE)["content"] == "name: Subject A\nage: 41\n"


def test_update_text_writes_a_content_type(media_bucket):
    manage.update_text(PROFILE, "name: Subject A\n")

    head = media_bucket.head_object(Bucket=config.media_bucket(), Key=PROFILE)
    assert head["ContentType"] == "application/yaml"


def test_update_text_accepts_an_empty_file(media_bucket):
    """Emptying a file is an edit, not a missing field — only `None` is missing."""
    result = manage.update_text(PROFILE, "")

    assert result["bytes"] == 0
    assert browse.text_object(PROFILE)["content"] == ""


def test_update_text_refuses_a_binary_key(media_bucket):
    with pytest.raises(ValidationError):
        manage.update_text(OUTPUT, "not a jpeg any more")


def test_update_text_refuses_a_non_string_body(media_bucket):
    for body in (None, 42, {"name": "Subject A"}):
        with pytest.raises(ValidationError):
            manage.update_text(PROFILE, body)
    assert browse.text_object(PROFILE)["content"] == "name: Subject A\n"


def test_update_text_refuses_a_body_over_the_cap(media_bucket, monkeypatch):
    """The same cap the read endpoint truncates at.

    That pairing is the point: a file the reader had to truncate must not be
    savable, or the save would delete everything past the cut.
    """
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 8)
    with pytest.raises(ValidationError):
        manage.update_text(PROFILE, "far too long to fit")
    # Read through boto3 rather than `browse.text_object`, which is capped by the
    # same patched value and would hand back a truncated copy of an intact file.
    stored = media_bucket.get_object(Bucket=config.media_bucket(), Key=PROFILE)
    assert stored["Body"].read() == b"name: Subject A\n"


def test_update_text_counts_bytes_not_characters(media_bucket, monkeypatch):
    """A cap measured in characters would let a UTF-8 file through at 3× it."""
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 4)
    with pytest.raises(ValidationError):
        manage.update_text(PROFILE, "héllo")


def test_update_text_cannot_create_a_file(media_bucket):
    """Studio still has no upload, and this is the route that would be it."""
    with pytest.raises(NotFoundError):
        manage.update_text("characters/subject-a/notes.md", "# new")
    assert "notes.md" not in _names("characters/subject-a/")


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_one_object(media_bucket):
    result = manage.delete_objects([OUTPUT])
    assert result["deleted"] == 1
    assert _names(f"{RUN}output/") == []


def test_delete_many_objects(media_bucket):
    manage.delete_objects(
        ["characters/subject-a/seed/subject-a_1.webp", "characters/subject-a/seed/subject-a_2.webp"]
    )
    assert _names("characters/subject-a/seed/") == []


def test_delete_rejects_an_empty_list(media_bucket):
    with pytest.raises(ValidationError):
        manage.delete_objects([])
    with pytest.raises(ValidationError):
        manage.delete_objects(None)


def test_delete_validates_every_key_before_deleting_any(media_bucket):
    with pytest.raises(ValidationError):
        manage.delete_objects([OUTPUT, "../outside.jpeg"])
    # The valid key in the same request survived, because nothing ran.
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_delete_refuses_more_than_the_cap(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.delete_objects([OUTPUT, VIDEO])


def test_delete_folder_removes_everything_beneath_it(media_bucket):
    result = manage.delete_folder(RUN)

    assert result["deleted"] == 3
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("projects/subject-a/runs/")


def test_delete_folder_refuses_the_library_root(media_bucket):
    with pytest.raises(ValidationError):
        manage.delete_folder("")
    with pytest.raises(ValidationError):
        manage.delete_folder(None)
    assert _folders("") != []


def test_delete_missing_folder_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.delete_folder("characters/subject-a/nowhere/")


def test_delete_folder_refuses_an_oversized_subtree(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.delete_folder(RUN)
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_nothing_reaches_outside_a_configured_root(media_bucket, monkeypatch):
    """Every write path refuses a key outside the browsable root.

    **This is worth reading carefully, because prod does not run this way.** The
    root prefix is empty there — the pipeline dropped the `media/` wrapper, so the
    whole bucket is the library — and with an empty root nothing is "outside" it,
    which is why this test has to configure one to have anything to assert. The
    confinement machinery is intact and this proves it; what is gone in prod is
    something for it to exclude. What still holds unconditionally is that the
    root itself cannot be renamed or deleted — see the two tests above.
    """
    monkeypatch.setattr("studio_core.config.media_root_prefix", lambda: "characters/")
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key="secrets/keys.txt", Body=b"do not touch"
    )

    for call in (
        lambda: manage.delete_objects(["secrets/keys.txt"]),
        lambda: manage.delete_folder("secrets/"),
        lambda: manage.rename_folder("secrets/", "gone"),
        lambda: manage.rename_object("secrets/keys.txt", "gone.txt"),
        lambda: manage.create_folder("secrets/", "new"),
        # Both ends of a move are checked, so neither a source outside the root
        # nor a destination outside it is reachable.
        lambda: manage.move_objects(["secrets/keys.txt"], "characters/subject-a/"),
        lambda: manage.move_objects(["characters/subject-a/profile.yaml"], "secrets/"),
        lambda: manage.move_folder("secrets/", "characters/"),
        lambda: manage.move_folder("characters/subject-a/", "secrets/"),
        lambda: manage.update_text("secrets/keys.txt", "emptied"),
        # Both ends of a copy are confined too, for the same reasons as a move.
        lambda: manage.copy_objects(["secrets/keys.txt"], "characters/subject-a/"),
        lambda: manage.copy_objects(["characters/subject-a/profile.yaml"], "secrets/"),
    ):
        with pytest.raises(ValidationError):
            call()

    body = media_bucket.get_object(Bucket=config.media_bucket(), Key="secrets/keys.txt")
    assert body["Body"].read() == b"do not touch"


# ---------------------------------------------------------------------------
# Copy
#
# The only write here that copies without deleting, so the source surviving is
# asserted directly. Its one real difference from a move is what happens to a
# name already taken at the destination: numbered, never refused and never
# overwritten.
# ---------------------------------------------------------------------------

SCENE = "projects/subject-b/scenes/2026-08-16_07-40-22_stadium-encounter/"
SHOT = f"{SCENE}shots/shot-01.mp4"
INPUT_POOL = "projects/subject-a/input/"


def test_copy_leaves_the_source_where_it_was(media_bucket):
    result = manage.copy_objects([OUTPUT], INPUT_POOL)

    assert result == {
        "destination": INPUT_POOL,
        "copied": 1,
        "keys": [f"{INPUT_POOL}wave-porch.jpeg"],
    }
    assert "wave-porch.jpeg" in _names(INPUT_POOL)
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"], "the source is still there"


def test_copy_takes_many_at_once_from_anywhere(media_bucket):
    """Sources may span projects and trees — only the destination is one folder.

    Favouriting could not do this: it derived a destination per key, so it was
    confined to media inside a project. A copy names its destination, so what a
    source *is* stops mattering.
    """
    result = manage.copy_objects([OUTPUT, VIDEO, "characters/subject-a/profile.yaml"], INPUT_POOL)

    assert result["copied"] == 3
    assert set(_names(INPUT_POOL)) >= {"wave-porch.jpeg", "standing-flex.mp4", "profile.yaml"}


def test_copying_the_same_file_twice_makes_a_second_copy(media_bucket):
    """Ask for a copy, get a copy.

    An earlier version of this compared byte sizes and skipped an identical
    file — a copy quietly deciding not to copy, which is the same "has this been
    done already" bookkeeping favourites was removed for.
    """
    manage.copy_objects([OUTPUT], INPUT_POOL)
    result = manage.copy_objects([OUTPUT], INPUT_POOL)

    assert result["keys"] == [f"{INPUT_POOL}wave-porch (2).jpeg"]
    assert sorted(_names(INPUT_POOL)) == ["wave-porch (2).jpeg", "wave-porch.jpeg"]


def test_copy_numbers_a_name_the_destination_already_holds(media_bucket):
    """Every scene calls its first shot `shot-01.mp4`, so this is the normal case."""
    media_bucket.put_object(Bucket=config.media_bucket(), Key=f"{INPUT_POOL}shot-01.mp4", Body=b"other")

    result = manage.copy_objects([SHOT], INPUT_POOL)

    assert result["keys"] == [f"{INPUT_POOL}shot-01 (2).mp4"]
    assert sorted(_names(INPUT_POOL)) == ["shot-01 (2).mp4", "shot-01.mp4"]


def test_copy_numbers_two_sources_of_one_name_in_a_single_request(media_bucket):
    """The in-memory name set has to be updated as the batch is planned.

    Otherwise both files see the same empty folder, both claim `shot-01.mp4`,
    and the second copy silently overwrites the first — the one outcome nothing
    in this module is allowed to produce.
    """
    other = "projects/subject-b/scenes/2026-08-16_09-12-00_stadium-exit/shots/shot-01.mp4"
    media_bucket.put_object(Bucket=config.media_bucket(), Key=other, Body=b"a-different-mp4")

    result = manage.copy_objects([SHOT, other], INPUT_POOL)

    assert result["copied"] == 2
    assert sorted(_names(INPUT_POOL)) == ["shot-01 (2).mp4", "shot-01.mp4"]


def test_copy_into_the_folder_a_file_is_already_in_duplicates_it(media_bucket):
    """A move treats this as a no-op; for a copy it is how you duplicate a file."""
    result = manage.copy_objects([OUTPUT], f"{RUN}output/")

    assert result["keys"] == [f"{RUN}output/wave-porch (2).jpeg"]
    assert sorted(_names(f"{RUN}output/")) == ["wave-porch (2).jpeg", "wave-porch.jpeg"]


def test_copy_of_a_missing_key_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.copy_objects([f"{RUN}output/never-existed.jpeg"], INPUT_POOL)


def test_copy_refuses_more_than_the_bulk_cap(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.copy_objects([OUTPUT, VIDEO], INPUT_POOL)


def test_copy_refuses_an_empty_key_list(media_bucket):
    with pytest.raises(ValidationError):
        manage.copy_objects([], INPUT_POOL)


def test_folder_names_is_just_the_basenames(media_bucket):
    """What `copy_objects` reads to pick a name that overwrites nothing.

    Lived in `test_browse.py` until #309, beside the helper it covers. The helper
    moved to `manage` when `browse` stopped listing S3; the test moved with it.
    """
    names = manage._folder_names(f"{RUN}output/")

    assert names == {"wave-porch.jpeg"}
    assert manage._folder_names("projects/subject-a/nothing-here/") == set()


def test_folder_names_skips_a_folder_marker(media_bucket):
    """The last reader in the service that still has to know what one is.

    `characters/subject-a/seed/` is a zero-byte object as well as a folder, so a
    delimited listing of its parent returns it among the objects. It is not a
    name a copy would collide with.
    """
    assert manage._folder_names("characters/subject-a/") == {"profile.yaml"}
