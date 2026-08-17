"""The write half of the API.

These lean on `browse` to assert outcomes rather than on boto3 directly: what
matters about a rename is that the browser now shows the file under its new name
and no longer under the old one, which is exactly what a listing answers.
"""

import pytest

from studio_core import config
from studio_core.errors import ConflictError, NotFoundError, ValidationError
from studio_core.services import browse, manage

RUN = "media/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/"
OUTPUT = f"{RUN}output/wave-porch.jpeg"
VIDEO = "media/mr-p/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"


def _names(prefix):
    return [f["name"] for f in browse.list_folder(prefix)["files"]]


def _folders(prefix):
    return [f["name"] for f in browse.list_folder(prefix)["folders"]]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_folder(media_bucket):
    result = manage.create_folder("media/fred/", "keepers")

    assert result["prefix"] == "media/fred/keepers/"
    assert "keepers" in _folders("media/fred/")
    # The marker object that makes the folder visible must not read as a file.
    assert _names("media/fred/keepers/") == []


def test_create_folder_refuses_a_duplicate(media_bucket):
    with pytest.raises(ConflictError):
        manage.create_folder("media/fred/", "originals")


def test_create_folder_refuses_a_path(media_bucket):
    with pytest.raises(ValidationError):
        manage.create_folder("media/fred/", "a/b")


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
        manage.rename_object("media/fred/originals/fred_1.webp", "fred_2.webp")
    # Nothing moved, and in particular nothing was overwritten.
    assert _names("media/fred/originals/") == ["fred_1.webp", "fred_2.webp"]


def test_rename_object_to_its_own_name_is_a_no_op(media_bucket):
    result = manage.rename_object(OUTPUT, "wave-porch.jpeg")
    assert result["renamed"] is False
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_rename_missing_object_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.rename_object("media/fred/originals/nope.webp", "yes.webp")


def test_rename_object_rejects_a_control_character(media_bucket):
    with pytest.raises(ValidationError):
        manage.rename_object(OUTPUT, "keeper\n.jpeg")


def test_rename_folder_moves_the_whole_subtree(media_bucket):
    result = manage.rename_folder(RUN, "wave-porch-final")

    assert result["objects"] == 3
    assert "wave-porch-final" in _folders("media/fred/runs/")
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("media/fred/runs/")

    moved = "media/fred/runs/wave-porch-final/"
    assert sorted(_names(moved)) == ["request.json", "result.json"]
    assert _names(f"{moved}output/") == ["wave-porch.jpeg"]


def test_rename_folder_refuses_an_occupied_name(media_bucket):
    manage.create_folder("media/fred/runs/", "taken")
    with pytest.raises(ConflictError):
        manage.rename_folder(RUN, "taken")


def test_rename_folder_refuses_the_library_root(media_bucket):
    with pytest.raises(ValidationError):
        manage.rename_folder("media/", "everything")
    with pytest.raises(ValidationError):
        manage.rename_folder(None, "everything")


def test_rename_folder_refuses_an_oversized_subtree(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.rename_folder(RUN, "too-big")
    # Refused before it started, so the original is intact.
    assert "2026-08-04_21-30-54_wave-porch-1x1" in _folders("media/fred/runs/")


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_one_object(media_bucket):
    result = manage.delete_objects([OUTPUT])
    assert result["deleted"] == 1
    assert _names(f"{RUN}output/") == []


def test_delete_many_objects(media_bucket):
    manage.delete_objects(
        ["media/fred/originals/fred_1.webp", "media/fred/originals/fred_2.webp"]
    )
    assert _names("media/fred/originals/") == []


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
    assert "2026-08-04_21-30-54_wave-porch-1x1" not in _folders("media/fred/runs/")


def test_delete_folder_refuses_the_library_root(media_bucket):
    with pytest.raises(ValidationError):
        manage.delete_folder("media/")
    with pytest.raises(ValidationError):
        manage.delete_folder(None)
    assert _folders("media/") != []


def test_delete_missing_folder_is_404(media_bucket):
    with pytest.raises(NotFoundError):
        manage.delete_folder("media/fred/nowhere/")


def test_delete_folder_refuses_an_oversized_subtree(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_folder_objects", lambda: 1)
    with pytest.raises(ValidationError):
        manage.delete_folder(RUN)
    assert _names(f"{RUN}output/") == ["wave-porch.jpeg"]


def test_nothing_reaches_outside_the_media_root(media_bucket):
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key="secrets/keys.txt", Body=b"do not touch"
    )

    for call in (
        lambda: manage.delete_objects(["secrets/keys.txt"]),
        lambda: manage.delete_folder("secrets/"),
        lambda: manage.rename_folder("secrets/", "gone"),
        lambda: manage.rename_object("secrets/keys.txt", "gone.txt"),
        lambda: manage.create_folder("secrets/", "new"),
    ):
        with pytest.raises(ValidationError):
            call()

    body = media_bucket.get_object(Bucket=config.media_bucket(), Key="secrets/keys.txt")
    assert body["Body"].read() == b"do not touch"
