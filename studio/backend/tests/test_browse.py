import time

import pytest

from studio_core import config
from studio_core.errors import ValidationError
from studio_core.services import browse


def test_root_lists_the_top_level(media_bucket):
    result = browse.list_folder(None)
    # The browsable root is the bucket itself — the pipeline no longer wraps
    # anything in `media/`.
    assert result["prefix"] == ""
    # Newest-first is the default, and a folder has no LastModified to sort by —
    # so folders fall back to the name, descending.
    assert [f["name"] for f in result["folders"]] == ["projects", "phrasebook", "characters"]
    assert result["sort"] == "newest"
    assert result["files"] == []


def test_subject_folder_lists_its_profile_and_subfolders(media_bucket):
    result = browse.list_folder("characters/subject-a/")
    assert [f["name"] for f in result["files"]] == ["profile.yaml"]
    assert [f["name"] for f in result["folders"]] == ["seed", "reference"]


def test_folder_markers_never_appear_as_files(media_bucket):
    # `characters/subject-a/seed/` is a zero-byte object as well as a folder, so it
    # comes back in its own listing. It is not a file.
    result = browse.list_folder("characters/subject-a/seed/")
    assert [f["name"] for f in result["files"]] == ["subject-a_1.webp", "subject-a_2.webp"]


def test_listing_presigns_every_file(media_bucket):
    result = browse.list_folder("characters/subject-a/seed/")
    assert all(f["kind"] == "image" for f in result["files"])
    assert all("X-Amz-Signature" in f["url"] for f in result["files"])


def test_run_folder_mixes_media_and_metadata(media_bucket):
    result = browse.list_folder("projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/")
    kinds = {f["name"]: f["kind"] for f in result["files"]}
    assert kinds == {"request.json": "text", "result.json": "text"}
    assert [f["name"] for f in result["folders"]] == ["output"]
    # Text files carry a highlighting hint for the read-only viewer.
    assert all(f["language"] == "json" for f in result["files"])


def test_breadcrumbs_and_counts(media_bucket):
    result = browse.list_folder("projects/subject-b/")
    assert [b["name"] for b in result["breadcrumbs"]] == ["/", "projects", "subject-b"]
    assert result["counts"]["folders"] == 2
    assert result["counts"]["media"] == 0


def test_reel_walks_recursively(media_bucket):
    result = browse.reel_items("characters/subject-a/", None, None)
    names = [item["name"] for item in result["items"]]
    # One reference image and two seeds — the .txt caption, the profile YAML and
    # the folder marker are all excluded. Every fixture object is written inside
    # the same second, so the date sort ties throughout and the key tie-break
    # decides: reference/, then seed/.
    assert names == ["subject-a_1.webp", "subject-a_1.webp", "subject-a_2.webp"]
    assert result["next_cursor"] is None
    assert result["total"] == 3
    assert result["truncated"] is False


def test_reel_from_root_spans_characters_and_projects(media_bucket):
    result = browse.reel_items(None, None, None)
    kinds = [item["kind"] for item in result["items"]]
    assert set(kinds) == {"image", "video"}
    assert any(item["name"] == "IMG_1966_Original.JPG" for item in result["items"])
    assert any(item["name"] == "standing-flex.mp4" for item in result["items"])
    assert any(item["name"] == "shot-01.mp4" for item in result["items"])


def test_asset_url_inline_and_attachment(media_bucket):
    key = "projects/subject-b/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"

    inline = browse.asset_url(key, "inline")
    assert inline["kind"] == "video"
    assert inline["size"] == len(b"mp4-bytes")
    assert "response-content-disposition" not in inline["url"]

    attachment = browse.asset_url(key, "attachment")
    assert "response-content-disposition" in attachment["url"]
    assert "standing-flex.mp4" in attachment["url"]


def test_text_object(media_bucket):
    result = browse.text_object("projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/request.json")
    assert result["language"] == "json"
    assert result["content"] == '{"model": "x"}'
    assert result["truncated"] is False


def test_text_object_reads_yaml(media_bucket):
    """Profiles and the phrasebook are YAML now, where they used to be markdown."""
    result = browse.text_object("phrasebook/wording.yaml")
    assert result["language"] == "yaml"
    assert result["content"] == "greeting: hello\n"


def test_text_object_truncates(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 4)
    result = browse.text_object("characters/subject-a/profile.yaml")
    assert result["truncated"] is True
    assert len(result["content"]) == 4


# ---------------------------------------------------------------------------
# Ordering
#
# Every fixture object is written inside one second and S3's LastModified has
# one-second resolution, so the date orders tie across the whole fixture. That
# is not a weakness of the fixture — it is the real bucket's normal case, since
# a run writes all of its output at once — so the tie-break is what these
# assert, and the date ordering itself is proved separately below.
# ---------------------------------------------------------------------------


def test_sort_by_name_and_name_desc(media_bucket):
    ascending = browse.list_folder("characters/subject-a/seed/", "name")
    descending = browse.list_folder("characters/subject-a/seed/", "name_desc")

    assert [f["name"] for f in ascending["files"]] == ["subject-a_1.webp", "subject-a_2.webp"]
    assert [f["name"] for f in descending["files"]] == ["subject-a_2.webp", "subject-a_1.webp"]
    assert [f["name"] for f in ascending["folders"]] == []


def test_folders_follow_the_sort(media_bucket):
    assert [f["name"] for f in browse.list_folder(None, "name")["folders"]] == [
        "characters",
        "phrasebook",
        "projects",
    ]
    assert [f["name"] for f in browse.list_folder(None, "oldest")["folders"]] == [
        "characters",
        "phrasebook",
        "projects",
    ]


def test_sort_rejects_anything_else(media_bucket):
    with pytest.raises(ValidationError):
        browse.list_folder(None, "sideways")


def test_newest_first_puts_a_later_write_first(media_bucket):
    # A second write, deliberately in a later second, is the only way to get two
    # distinct timestamps out of S3 — LastModified has no sub-second component
    # to distinguish the fixture's own writes with.
    time.sleep(1.05)
    media_bucket.put_object(
        Bucket=config.media_bucket(),
        Key="characters/subject-a/seed/subject-a_0_written_last.webp",
        Body=b"webp-bytes",
    )

    newest = [f["name"] for f in browse.list_folder("characters/subject-a/seed/", "newest")["files"]]
    oldest = [f["name"] for f in browse.list_folder("characters/subject-a/seed/", "oldest")["files"]]

    # Name-ascending would have put it first anyway, so the assertion that
    # carries weight is the *oldest* one: it sorts last there despite its name.
    assert newest[0] == "subject-a_0_written_last.webp"
    assert oldest[-1] == "subject-a_0_written_last.webp"


def test_reel_ties_break_on_the_key_not_the_basename(media_bucket):
    """The dates tie across the fixture, so the full key decides — not the name.

    `IMG_1966_Original.JPG` is the case that tells the two apart: uppercase sorts
    before lowercase, so by basename it would come first, while by key it sits
    under `characters/subject-b/` and belongs after everything of subject-a's.
    """
    items = browse.reel_items("characters/", None, None)["items"]

    assert [i["key"] for i in items] == sorted(i["key"] for i in items)
    names = [i["name"] for i in items]
    assert names.index("IMG_1966_Original.JPG") > names.index("subject-a_1.webp")


def test_reel_cursor_is_an_offset(media_bucket):
    first = browse.reel_items(None, None, 2)
    assert len(first["items"]) == 2
    assert first["next_cursor"] == "2"

    second = browse.reel_items(None, "2", 2)
    assert first["total"] == second["total"]
    # No overlap: the window moved rather than being re-cut from the start.
    assert not {i["key"] for i in first["items"]} & {i["key"] for i in second["items"]}


def test_reel_presigns_only_the_page_it_returns(media_bucket):
    page = browse.reel_items(None, None, 1)
    assert len(page["items"]) == 1
    assert "X-Amz-Signature" in page["items"][0]["url"]


def test_reel_rejects_a_bad_cursor(media_bucket):
    with pytest.raises(ValidationError):
        browse.reel_items(None, "not-a-number", None)


def test_reel_reports_a_truncated_walk(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_walk_objects", lambda: 2)
    result = browse.reel_items(None, None, None)
    assert result["truncated"] is True


# ---------------------------------------------------------------------------
# What a listing carries
#
# A file entry used to answer two favourites questions — where a favourite of
# this would go, and whether one exists. Both are gone: a copy names its own
# destination, so nothing here has to guess one or report on it.
# ---------------------------------------------------------------------------


def _entry(prefix, name):
    return next(f for f in browse.list_folder(prefix)["files"] if f["name"] == name)


def test_a_listing_carries_no_favourites_fields(media_bucket):
    entry = _entry(
        "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/output/", "wave-porch.jpeg"
    )

    assert "favorites_prefix" not in entry
    assert "favorited" not in entry
    # The fields a listing does carry, unchanged.
    assert entry["kind"] == "image"
    assert entry["key"].endswith("wave-porch.jpeg")


def test_the_reel_carries_no_favourites_fields_either(media_bucket):
    """The reel used to list every favourites folder on a page to light stars.

    A page is 200 items across however many projects, so that was one extra S3
    listing per project per page, spent on a question nothing asks any more.
    """
    items = browse.reel_items("projects/subject-a/", None, None)["items"]

    assert items, "the reel still lists the media"
    assert all("favorites_prefix" not in item and "favorited" not in item for item in items)


def test_folder_names_is_just_the_basenames(media_bucket):
    """What `manage.copy_objects` reads to pick a name that overwrites nothing."""
    names = browse.folder_names("projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/output/")

    assert names == {"wave-porch.jpeg"}
    assert browse.folder_names("projects/subject-a/nothing-here/") == set()
