import time

import pytest

from studio_core import config
from studio_core.errors import ValidationError
from studio_core.services import browse


def test_root_lists_subjects(media_bucket):
    result = browse.list_folder(None)
    assert result["prefix"] == "media/"
    # Newest-first is the default, and a folder has no LastModified to sort by —
    # so folders fall back to the name, descending. For x-harness run folders,
    # whose names begin with a timestamp, that *is* newest-first.
    assert [f["name"] for f in result["folders"]] == ["mr-p", "misc", "fred"]
    assert result["sort"] == "newest"
    # `media/` itself is a zero-byte marker, not a file.
    assert result["files"] == []


def test_folder_markers_never_appear_as_files(media_bucket):
    result = browse.list_folder("media/fred/")
    names = [f["name"] for f in result["files"]]
    assert names == ["profile.md"]
    assert "originals" in [f["name"] for f in result["folders"]]


def test_listing_presigns_every_file(media_bucket):
    result = browse.list_folder("media/fred/originals/")
    assert [f["name"] for f in result["files"]] == ["fred_1.webp", "fred_2.webp"]
    assert all(f["kind"] == "image" for f in result["files"])
    assert all("X-Amz-Signature" in f["url"] for f in result["files"])


def test_run_folder_mixes_media_and_metadata(media_bucket):
    result = browse.list_folder("media/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/")
    kinds = {f["name"]: f["kind"] for f in result["files"]}
    assert kinds == {"request.json": "text", "result.json": "text"}
    assert [f["name"] for f in result["folders"]] == ["output"]
    # Text files carry a highlighting hint for the read-only viewer.
    assert all(f["language"] == "json" for f in result["files"])


def test_breadcrumbs_and_counts(media_bucket):
    result = browse.list_folder("media/mr-p/")
    assert [b["name"] for b in result["breadcrumbs"]] == ["media", "mr-p"]
    assert result["counts"]["folders"] == 2
    assert result["counts"]["media"] == 0


def test_reel_walks_recursively(media_bucket):
    result = browse.reel_items("media/fred/", None, None)
    names = [item["name"] for item in result["items"]]
    # Two originals, one reference image and the run output — the .txt caption
    # and the two run JSON files are excluded. Every fixture object is written
    # inside the same second, so the date sort ties throughout and the key
    # tie-break decides: originals/, then reference/, then runs/.
    assert names == ["fred_1.webp", "fred_2.webp", "fred_1.webp", "wave-porch.jpeg"]
    assert result["next_cursor"] is None
    assert result["total"] == 4
    assert result["truncated"] is False


def test_reel_from_root_spans_every_subject(media_bucket):
    result = browse.reel_items(None, None, None)
    kinds = [item["kind"] for item in result["items"]]
    assert set(kinds) == {"image", "video"}
    assert any(item["name"] == "standing-flex.mp4" for item in result["items"])
    assert any(item["name"] == "IMG_1966_Original.JPG" for item in result["items"])


def test_reel_paginates(media_bucket):
    first = browse.reel_items("media/", None, 1)
    assert len(first["items"]) >= 1
    assert first["next_cursor"]

    second = browse.reel_items("media/", first["next_cursor"], 1)
    assert second["items"][0]["key"] != first["items"][0]["key"]


def test_asset_url_inline_and_attachment(media_bucket):
    key = "media/mr-p/runs/2026-08-14_21-47-05_standing-flex/output/standing-flex.mp4"

    inline = browse.asset_url(key, "inline")
    assert inline["kind"] == "video"
    assert inline["size"] == len(b"mp4-bytes")
    assert "response-content-disposition" not in inline["url"]

    attachment = browse.asset_url(key, "attachment")
    assert "response-content-disposition" in attachment["url"]
    assert "standing-flex.mp4" in attachment["url"]


def test_text_object(media_bucket):
    result = browse.text_object("media/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/request.json")
    assert result["language"] == "json"
    assert result["content"] == '{"model": "x"}'
    assert result["truncated"] is False


def test_text_object_truncates(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_text_bytes", lambda: 4)
    result = browse.text_object("media/fred/profile.md")
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
    ascending = browse.list_folder("media/fred/originals/", "name")
    descending = browse.list_folder("media/fred/originals/", "name_desc")

    assert [f["name"] for f in ascending["files"]] == ["fred_1.webp", "fred_2.webp"]
    assert [f["name"] for f in descending["files"]] == ["fred_2.webp", "fred_1.webp"]
    assert [f["name"] for f in ascending["folders"]] == []


def test_folders_follow_the_sort(media_bucket):
    assert [f["name"] for f in browse.list_folder(None, "name")["folders"]] == [
        "fred",
        "misc",
        "mr-p",
    ]
    assert [f["name"] for f in browse.list_folder(None, "oldest")["folders"]] == [
        "fred",
        "misc",
        "mr-p",
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
        Key="media/fred/originals/fred_0_written_last.webp",
        Body=b"webp-bytes",
    )

    newest = [f["name"] for f in browse.list_folder("media/fred/originals/", "newest")["files"]]
    oldest = [f["name"] for f in browse.list_folder("media/fred/originals/", "oldest")["files"]]

    # Name-ascending would have put it first anyway, so the assertion that
    # carries weight is the *oldest* one: it sorts last there despite its name.
    assert newest[0] == "fred_0_written_last.webp"
    assert oldest[-1] == "fred_0_written_last.webp"


def test_reel_ties_break_on_the_key_not_the_basename(media_bucket):
    """Two `fred_1.webp` in different folders must not sort next to each other."""
    names = [item["name"] for item in browse.reel_items("media/fred/", None, None)["items"]]
    assert names.index("fred_2.webp") < names.index("fred_1.webp", 1)


def test_reel_cursor_is_an_offset(media_bucket):
    first = browse.reel_items("media/", None, 2)
    assert len(first["items"]) == 2
    assert first["next_cursor"] == "2"

    second = browse.reel_items("media/", "2", 2)
    assert first["total"] == second["total"]
    # No overlap: the window moved rather than being re-cut from the start.
    assert not {i["key"] for i in first["items"]} & {i["key"] for i in second["items"]}


def test_reel_presigns_only_the_page_it_returns(media_bucket):
    page = browse.reel_items("media/", None, 1)
    assert len(page["items"]) == 1
    assert "X-Amz-Signature" in page["items"][0]["url"]


def test_reel_rejects_a_bad_cursor(media_bucket):
    with pytest.raises(ValidationError):
        browse.reel_items("media/", "not-a-number", None)


def test_reel_reports_a_truncated_walk(media_bucket, monkeypatch):
    monkeypatch.setattr("studio_core.config.max_walk_objects", lambda: 2)
    result = browse.reel_items("media/", None, None)
    assert result["truncated"] is True
