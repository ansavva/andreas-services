from studio_core.services import browse


def test_root_lists_subjects(media_bucket):
    result = browse.list_folder(None)
    assert result["prefix"] == "media/"
    assert [f["name"] for f in result["folders"]] == ["fred", "misc", "mr-p"]
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
    # and the two run JSON files are excluded.
    assert names == ["fred_1.webp", "fred_2.webp", "fred_1.webp", "wave-porch.jpeg"]
    assert result["next_cursor"] is None


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
