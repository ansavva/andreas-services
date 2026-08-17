"""The write half of the API.

These lean on `browse` to assert outcomes rather than on boto3 directly: what
matters about a rename is that the browser now shows the file under its new name
and no longer under the old one, which is exactly what a listing answers.
"""

import pytest

from studio_core import config
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import browse, manage

RUN = "projects/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/"
OUTPUT = f"{RUN}output/wave-porch.jpeg"
VIDEO = "projects/mr-p/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"


def _names(prefix):
    return [f["name"] for f in browse.list_folder(prefix)["files"]]


def _folders(prefix):
    return [f["name"] for f in browse.list_folder(prefix)["folders"]]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_folder(media_bucket):
    result = manage.create_folder("characters/fred/", "keepers")

    assert result["prefix"] == "characters/fred/keepers/"
    assert "keepers" in _folders("characters/fred/")
    # The marker object that makes the folder visible must not read as a file.
    assert _names("characters/fred/keepers/") == []


def test_create_folder_refuses_a_duplicate(media_bucket):
    with pytest.raises(ConflictError):
        manage.create_folder("characters/fred/", "seed")


def test_create_folder_refuses_a_path(media_bucket):
    with pytest.raises(ValidationError):
        manage.create_folder("characters/fred/", "a/b")


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
        manage.rename_object("characters/fred/seed/fred_1.webp", "fred_2.webp")
    # Nothing moved, and in particular nothing was overwritten.
    assert _names("characters/fred/seed/") == ["fred_1.webp", "fred_2.webp"]


def test_rename_object_to_its_own_name_is_a_no_op(media_bucket):
    result = manage.rename_object(OUTPUT, "wave-porch.jpeg")
    assert result["renamed"] is False
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_rename_missing_object_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.rename_object("characters/fred/seed/nope.webp", "yes.webp")


def test_rename_object_rejects_a_control_character(media_bucket):
    with pytest.raises(ValidationError):
        manage.rename_object(OUTPUT, "keeper\n.jpeg")


def test_rename_folder_moves_the_whole_subtree(media_bucket):
    result = manage.rename_folder(RUN, "wave-porch-final")

    assert result["objects"] == 3
    assert "wave-porch-final" in _folders("projects/fred/runs/")
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("projects/fred/runs/")

    moved = "projects/fred/runs/wave-porch-final/"
    assert sorted(_names(moved)) == ["request.json", "result.json"]
    assert _names(f"{moved}output/") == ["wave-porch.jpeg"]


def test_rename_folder_refuses_an_occupied_name(media_bucket):
    manage.create_folder("projects/fred/runs/", "taken")
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
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/fred/runs/")


# ---------------------------------------------------------------------------
# Move
#
# The pairing to keep in mind while reading these: a rename changes the last
# segment and keeps the folder, a move changes the folder and keeps the last
# segment. Neither is reachable from the other, and the first two tests here are
# what hold that line.
# ---------------------------------------------------------------------------


def test_move_objects_keeps_their_names(media_bucket):
    result = manage.move_objects([OUTPUT], "characters/fred/")

    assert result["moved"] == 1
    assert result["keys"] == ["characters/fred/wave-porch.jpeg"]
    assert "wave-porch.jpeg" in _names("characters/fred/")
    assert _names(f"{RUN}output/") == []


def test_move_objects_cannot_rename_on_the_way(media_bucket):
    """A destination is a folder, so there is nowhere to put a new name.

    `characters/fred/renamed.jpeg` is read as a *prefix* — the file lands inside
    a folder of that name rather than becoming a file of that name — which is
    the behaviour that keeps move from being a second, sloppier rename.
    """
    manage.move_objects([OUTPUT], "characters/fred/renamed.jpeg")

    assert _names("characters/fred/renamed.jpeg/") == ["wave-porch.jpeg"]


def test_move_many_objects(media_bucket):
    result = manage.move_objects(
        ["characters/fred/seed/fred_1.webp", "characters/fred/seed/fred_2.webp"],
        "characters/mr-p/corpus/",
    )

    assert result["moved"] == 2
    assert _names("characters/fred/seed/") == []
    assert sorted(_names("characters/mr-p/corpus/")) == [
        "IMG_1966_Original.JPG",
        "fred_1.webp",
        "fred_2.webp",
    ]


def test_move_objects_skips_ones_already_there(media_bucket):
    result = manage.move_objects(["characters/fred/profile.yaml"], "characters/fred/")

    assert result == {
        "destination": "characters/fred/",
        "moved": 0,
        "skipped": 1,
        "keys": [],
    }
    assert "profile.yaml" in _names("characters/fred/")


def test_move_objects_refuses_an_occupied_destination(media_bucket):
    with pytest.raises(ConflictError):
        manage.move_objects(
            ["characters/fred/reference/fred_1.webp"], "characters/fred/seed/"
        )
    # Refused whole, so neither end moved.
    assert "fred_1.webp" in _names("characters/fred/reference/")
    assert sorted(_names("characters/fred/seed/")) == ["fred_1.webp", "fred_2.webp"]


def test_move_objects_refuses_two_sources_of_the_same_name(media_bucket):
    """Different folders, same basename — one would land on top of the other."""
    with pytest.raises(ConflictError):
        manage.move_objects(
            [
                "characters/fred/reference/fred_1.webp",
                "characters/mr-p/reference/face/mr-p_face_1.jpeg",
                "characters/fred/seed/fred_1.webp",
            ],
            "characters/mr-p/corpus/",
        )
    assert _names("characters/mr-p/corpus/") == ["IMG_1966_Original.JPG"]


def test_move_objects_validates_every_key_before_moving_any(media_bucket):
    with pytest.raises(ValidationError):
        manage.move_objects([OUTPUT, "../outside.jpeg"], "characters/fred/")
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_move_objects_refuses_more_than_the_cap(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.move_objects([OUTPUT, VIDEO], "characters/fred/")


def test_move_objects_rejects_an_empty_list(media_bucket):
    with pytest.raises(ValidationError):
        manage.move_objects([], "characters/fred/")
    with pytest.raises(ValidationError):
        manage.move_objects(None, "characters/fred/")


def test_move_folder_carries_the_whole_subtree(media_bucket):
    result = manage.move_folder(RUN, "projects/misc/runs/")

    assert result["objects"] == 3
    assert result["prefix"] == "projects/misc/runs/2026-08-04_21-30-54_wave-porch-1x1/"
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("projects/fred/runs/")

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
        manage.move_folder("characters/fred/", "characters/fred/seed/")
    assert sorted(_names("characters/fred/seed/")) == ["fred_1.webp", "fred_2.webp"]


def test_move_folder_beside_a_similarly_named_sibling_is_allowed(media_bucket):
    """`fred-2/` does not sit inside `fred/`, and the slash is what says so."""
    manage.create_folder("characters/", "fred-2")
    result = manage.move_folder("characters/fred/reference/", "characters/fred-2/")

    assert result["moved"] is True
    assert "reference" in _folders("characters/fred-2/")


def test_move_folder_to_its_own_parent_is_a_no_op(media_bucket):
    result = manage.move_folder(RUN, "projects/fred/runs/")

    assert result["moved"] is False
    assert result["objects"] == 0
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/fred/runs/")


def test_move_folder_refuses_an_occupied_destination(media_bucket):
    manage.create_folder("projects/misc/runs/", "2026-08-04_21-30-54_wave-porch-1x1")
    with pytest.raises(ConflictError):
        manage.move_folder(RUN, "projects/misc/runs/")
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/fred/runs/")


def test_move_folder_refuses_the_library_root(media_bucket):
    with pytest.raises(ValidationError):
        manage.move_folder("", "projects/")
    with pytest.raises(ValidationError):
        manage.move_folder(None, "projects/")


def test_move_folder_refuses_an_oversized_subtree(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.move_folder(RUN, "projects/misc/runs/")
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("projects/fred/runs/")


def test_move_missing_folder_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.move_folder("characters/fred/nowhere/", "characters/")


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

PROFILE = "characters/fred/profile.yaml"


def test_update_text_overwrites_the_file(media_bucket):
    result = manage.update_text(PROFILE, "name: Fred\nage: 41\n")

    assert result["language"] == "yaml"
    assert result["bytes"] == len(b"name: Fred\nage: 41\n")
    assert browse.text_object(PROFILE)["content"] == "name: Fred\nage: 41\n"


def test_update_text_writes_a_content_type(media_bucket):
    manage.update_text(PROFILE, "name: Fred\n")

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
    for body in (None, 42, {"name": "Fred"}):
        with pytest.raises(ValidationError):
            manage.update_text(PROFILE, body)
    assert browse.text_object(PROFILE)["content"] == "name: Fred\n"


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
    assert stored["Body"].read() == b"name: Fred\n"


def test_update_text_counts_bytes_not_characters(media_bucket, monkeypatch):
    """A cap measured in characters would let a UTF-8 file through at 3× it."""
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 4)
    with pytest.raises(ValidationError):
        manage.update_text(PROFILE, "héllo")


def test_update_text_cannot_create_a_file(media_bucket):
    """Studio still has no upload, and this is the route that would be it."""
    with pytest.raises(NotFoundError):
        manage.update_text("characters/fred/notes.md", "# new")
    assert "notes.md" not in _names("characters/fred/")


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_one_object(media_bucket):
    result = manage.delete_objects([OUTPUT])
    assert result["deleted"] == 1
    assert _names(f"{RUN}output/") == []


def test_delete_many_objects(media_bucket):
    manage.delete_objects(
        ["characters/fred/seed/fred_1.webp", "characters/fred/seed/fred_2.webp"]
    )
    assert _names("characters/fred/seed/") == []


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
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("projects/fred/runs/")


def test_delete_folder_refuses_the_library_root(media_bucket):
    with pytest.raises(ValidationError):
        manage.delete_folder("")
    with pytest.raises(ValidationError):
        manage.delete_folder(None)
    assert _folders("") != []


def test_delete_missing_folder_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.delete_folder("characters/fred/nowhere/")


def test_delete_folder_refuses_an_oversized_subtree(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.delete_folder(RUN)
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_nothing_reaches_outside_a_configured_root(media_bucket, monkeypatch):
    """Every write path refuses a key outside the browsable root.

    **This is worth reading carefully, because prod does not run this way.** The
    root prefix is empty there — x-harness dropped the `media/` wrapper, so the
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
        lambda: manage.move_objects(["secrets/keys.txt"], "characters/fred/"),
        lambda: manage.move_objects(["characters/fred/profile.yaml"], "secrets/"),
        lambda: manage.move_folder("secrets/", "characters/"),
        lambda: manage.move_folder("characters/fred/", "secrets/"),
        lambda: manage.update_text("secrets/keys.txt", "emptied"),
        # Favouriting names no destination, so the only thing to confine is its
        # source — and a source outside the root never reaches the copy.
        lambda: manage.favorite_objects(["secrets/keys.txt"]),
    ):
        with pytest.raises(ValidationError):
            call()

    body = media_bucket.get_object(Bucket=config.media_bucket(), Key="secrets/keys.txt")
    assert body["Body"].read() == b"do not touch"


# ---------------------------------------------------------------------------
# Favorite
#
# The only write here that copies without deleting, and the only one whose
# destination is derived rather than supplied. Both properties are asserted
# directly: the source must survive, and no argument may aim the copy elsewhere.
# ---------------------------------------------------------------------------

FRED_FAVORITES = "projects/fred/favorites/"
MR_P_FAVORITES = "projects/mr-p/favorites/"
SCENE = "projects/mr-p/scenes/2026-08-16_07-40-22_stadium-encounter/"
SHOT = f"{SCENE}shots/shot-01.mp4"


def test_favorite_copies_into_its_own_projects_favorites(media_bucket):
    result = manage.favorite_objects([OUTPUT])

    assert result == {
        "favorited": 1,
        "skipped": 0,
        "keys": [f"{FRED_FAVORITES}wave-porch.jpeg"],
    }
    assert _names(FRED_FAVORITES) == ["wave-porch.jpeg"]
    # A favourite is a copy. The original stays exactly where the pipeline put it
    # — this is the one write in the module that leaves its source alone.
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_favorite_takes_many_at_once_and_splits_them_by_project(media_bucket):
    """One request, three files, two projects — and nobody named a destination.

    This is what makes favouriting different from moving: the reel walks across
    subjects, so a selection can span projects, and each file has exactly one
    folder it belongs in. A move would need one request per destination.
    """
    result = manage.favorite_objects([OUTPUT, VIDEO, SHOT])

    assert result["favorited"] == 3
    assert _names(FRED_FAVORITES) == ["wave-porch.jpeg"]
    assert sorted(_names(MR_P_FAVORITES)) == ["shot-01.mp4", "standing-flex.mp4"]


def test_favoriting_twice_is_a_no_op(media_bucket):
    manage.favorite_objects([OUTPUT])
    result = manage.favorite_objects([OUTPUT])

    assert result["favorited"] == 0
    assert result["skipped"] == 1
    # Not `wave-porch (2).jpeg`: same name and same size is the same file.
    assert _names(FRED_FAVORITES) == ["wave-porch.jpeg"]


def test_favorite_numbers_a_name_a_different_file_already_holds(media_bucket):
    """Every scene calls its first shot `shot-01.mp4`, so this is the normal case."""
    manage.favorite_objects([SHOT])
    other = "projects/mr-p/scenes/2026-08-16_09-12-00_stadium-exit/shots/shot-01.mp4"
    media_bucket.put_object(Bucket=config.media_bucket(), Key=other, Body=b"a-different-mp4")

    result = manage.favorite_objects([other])

    assert result["keys"] == [f"{MR_P_FAVORITES}shot-01 (2).mp4"]
    assert sorted(_names(MR_P_FAVORITES)) == ["shot-01 (2).mp4", "shot-01.mp4"]


def test_favorite_numbers_two_sources_of_one_name_in_a_single_request(media_bucket):
    """The in-memory index has to be updated as the batch is planned.

    Otherwise both files see the same empty folder, both claim `shot-01.mp4`,
    and the second copy silently overwrites the first — the one outcome nothing
    in this module is allowed to produce.
    """
    other = "projects/mr-p/scenes/2026-08-16_09-12-00_stadium-exit/shots/shot-01.mp4"
    media_bucket.put_object(Bucket=config.media_bucket(), Key=other, Body=b"a-different-mp4")

    result = manage.favorite_objects([SHOT, other])

    assert result["favorited"] == 2
    assert sorted(_names(MR_P_FAVORITES)) == ["shot-01 (2).mp4", "shot-01.mp4"]


def test_favorite_refuses_a_character_photo(media_bucket):
    """`characters/` holds who a subject is. There is nothing to pick between."""
    with pytest.raises(ValidationError):
        manage.favorite_objects(["characters/fred/seed/fred_1.webp"])
    assert "favorites" not in _folders("characters/fred/")


def test_favorite_refuses_run_metadata(media_bucket):
    with pytest.raises(ValidationError):
        manage.favorite_objects([f"{RUN}request.json"])
    assert "favorites" not in _folders("projects/fred/")


def test_favorite_refuses_something_that_is_already_a_favorite(media_bucket):
    manage.favorite_objects([OUTPUT])
    with pytest.raises(ValidationError):
        manage.favorite_objects([f"{FRED_FAVORITES}wave-porch.jpeg"])
    assert _names(FRED_FAVORITES) == ["wave-porch.jpeg"]


def test_favorite_refuses_a_key_directly_under_projects(media_bucket):
    """`projects/fred/project.json` belongs to no run and is not media either."""
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key="projects/loose.mp4", Body=b"mp4-bytes"
    )
    with pytest.raises(ValidationError):
        manage.favorite_objects(["projects/loose.mp4"])


def test_favorite_of_a_missing_key_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.favorite_objects([f"{RUN}output/never-existed.jpeg"])


def test_favorite_copies_nothing_when_one_key_in_the_batch_is_refused(media_bucket):
    """The whole batch is planned before anything is copied.

    Same bargain `move_objects` makes: a selection half-favourited, with nothing
    to say where the boundary fell, is worse than a request that did nothing.
    """
    with pytest.raises(ValidationError):
        manage.favorite_objects([OUTPUT, "characters/fred/seed/fred_1.webp"])
    assert "favorites" not in _folders("projects/fred/")


def test_favorite_refuses_more_than_the_bulk_cap(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_bulk_keys", lambda: 1)
    with pytest.raises(ValidationError):
        manage.favorite_objects([OUTPUT, VIDEO])


def test_favorite_is_off_when_no_projects_prefix_is_configured(media_bucket, monkeypatch):
    """The knob that survives x-harness reshaping the bucket again.

    With nowhere identified as a project there is no derivable destination, so
    every key is refused rather than copied somewhere invented.
    """
    monkeypatch.setattr("studio_core.config.projects_prefix", lambda: "")
    with pytest.raises(ValidationError):
        manage.favorite_objects([OUTPUT])
