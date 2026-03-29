"""Tests for takeout_scanner.py — sidecar matching, live photo detection, incremental scan."""
import json
import os
import pytest

from my_tools.photos.takeout_scanner import (
    validate_takeout_folder,
    find_sidecar,
    parse_sidecar,
    detect_live_photo_pairs,
    scan_takeout,
)


SAMPLE_SIDECAR_JSON = json.dumps({
    "title": "photo.jpg",
    "photoTakenTime": {"timestamp": "1609459200", "formatted": "Jan 1, 2021"},
    "creationTime": {"timestamp": "1609459200"},
    "geoData": {"latitude": 37.7749, "longitude": -122.4194},
    "width": "4032",
    "height": "3024",
})


def make_takeout(tmp_path, files):
    """
    files: list of (relative_path, content_bytes_or_str)
    Creates them under tmp_path/Takeout/Google Photos/Photos from 2021/
    Returns the root path (tmp_path).
    """
    base = tmp_path / "Takeout" / "Google Photos" / "Photos from 2021"
    base.mkdir(parents=True)
    for rel, content in files:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content)
        else:
            p.write_bytes(content)
    return tmp_path


# ---------------------------------------------------------------------------
# validate_takeout_folder tests
# ---------------------------------------------------------------------------

def test_validate_takeout_folder_valid(tmp_path):
    """Path containing Takeout/Google Photos/<subdir>/ is valid."""
    gp = tmp_path / "Takeout" / "Google Photos" / "Photos from 2021"
    gp.mkdir(parents=True)
    valid, msg = validate_takeout_folder(str(tmp_path))
    assert valid is True
    assert msg == ""


def test_validate_takeout_folder_inner(tmp_path):
    """User passed the inner Google Photos dir directly — also valid."""
    gp = tmp_path / "Google Photos" / "Photos from 2021"
    gp.mkdir(parents=True)
    valid, msg = validate_takeout_folder(str(tmp_path))
    assert valid is True
    assert msg == ""


def test_validate_takeout_folder_invalid(tmp_path):
    """Non-existent path returns (False, error_message)."""
    nonexistent = str(tmp_path / "does_not_exist")
    valid, msg = validate_takeout_folder(nonexistent)
    assert valid is False
    assert len(msg) > 0


# ---------------------------------------------------------------------------
# find_sidecar tests
# ---------------------------------------------------------------------------

def test_find_sidecar_stage1_edited(tmp_path):
    """Stage 1: photo-edited.jpg finds photo.jpg.supplemental-metadata.json."""
    d = tmp_path
    media = d / "photo-edited.jpg"
    sidecar = d / "photo.jpg.supplemental-metadata.json"
    media.write_bytes(b"data")
    sidecar.write_text(SAMPLE_SIDECAR_JSON)
    result = find_sidecar(str(media))
    assert result == str(sidecar)


def test_find_sidecar_stage2_new(tmp_path):
    """Stage 2: photo.jpg finds photo.jpg.supplemental-metadata.json (new format)."""
    d = tmp_path
    media = d / "photo.jpg"
    sidecar = d / "photo.jpg.supplemental-metadata.json"
    media.write_bytes(b"data")
    sidecar.write_text(SAMPLE_SIDECAR_JSON)
    result = find_sidecar(str(media))
    assert result == str(sidecar)


def test_find_sidecar_stage2_legacy(tmp_path):
    """Stage 2 legacy: photo.jpg finds photo.jpg.json (old format)."""
    d = tmp_path
    media = d / "photo.jpg"
    sidecar = d / "photo.jpg.json"
    media.write_bytes(b"data")
    sidecar.write_text(SAMPLE_SIDECAR_JSON)
    result = find_sidecar(str(media))
    assert result == str(sidecar)


def test_find_sidecar_stage3_truncated(tmp_path):
    """Stage 3: truncated sidecar when full name exceeds 51 chars."""
    d = tmp_path
    # Use a filename such that base_for_sidecar + ".supplemental-metadata.json" > 51 chars
    # "a_very_long_filename_that_ex.jpg" = 32 chars
    # ".supplemental-metadata.json" = 27 chars => total = 59 > 51
    # ".json" = 5 chars, so chars_available = 51 - (32+5) = 14
    # truncated_suffix = ".supplemental-metadata"[:14] = ".supplemental-"
    # truncated_candidate = "a_very_long_filename_that_ex.jpg.supplemental-.json"
    long_name = "a_very_long_filename_that_ex.jpg"  # 32 chars
    sidecar_name = long_name + ".supplemental-metadata.json"  # 59 chars > 51
    assert len(sidecar_name) > 51

    # Compute the truncated sidecar name the algorithm would generate
    suffix = ".supplemental-metadata.json"
    base_plus_json = long_name + ".json"  # 37 chars
    chars_available = 51 - len(base_plus_json)  # 51 - 37 = 14
    truncated_suffix = ".supplemental-metadata"[:chars_available]
    truncated_candidate = long_name + truncated_suffix + ".json"

    media = d / long_name
    sidecar = d / truncated_candidate
    media.write_bytes(b"data")
    sidecar.write_text(SAMPLE_SIDECAR_JSON)
    result = find_sidecar(str(media))
    assert result == str(sidecar)


def test_find_sidecar_stage4_counter(tmp_path):
    """Stage 4: photo(1).jpg finds photo.jpg(1).supplemental-metadata.json."""
    d = tmp_path
    media = d / "photo(1).jpg"
    sidecar = d / "photo.jpg(1).supplemental-metadata.json"
    media.write_bytes(b"data")
    sidecar.write_text(SAMPLE_SIDECAR_JSON)
    result = find_sidecar(str(media))
    assert result == str(sidecar)


def test_find_sidecar_none(tmp_path):
    """File with no matching sidecar returns None."""
    d = tmp_path
    media = d / "orphan.jpg"
    media.write_bytes(b"data")
    result = find_sidecar(str(media))
    assert result is None


# ---------------------------------------------------------------------------
# parse_sidecar tests
# ---------------------------------------------------------------------------

def test_parse_sidecar_extracts_fields(tmp_path):
    """JSON with photoTakenTime.timestamp '1609459200', width '4032', height '3024'."""
    sidecar = tmp_path / "photo.jpg.supplemental-metadata.json"
    sidecar.write_text(SAMPLE_SIDECAR_JSON)
    result = parse_sidecar(str(sidecar))
    assert result["creation_time"] is not None
    assert "2021" in result["creation_time"]  # ISO date includes the year
    assert result["width"] == 4032
    assert result["height"] == 3024


# ---------------------------------------------------------------------------
# detect_live_photo_pairs tests
# ---------------------------------------------------------------------------

def test_detect_live_photo_pairs(tmp_path):
    """IMG_0001.HEIC + IMG_0001.MOV => MOV maps to HEIC."""
    d = tmp_path
    (d / "IMG_0001.HEIC").write_bytes(b"heic data")
    (d / "IMG_0001.MOV").write_bytes(b"mov data")
    (d / "regular.jpg").write_bytes(b"jpg data")
    pairs = detect_live_photo_pairs(str(d))
    mov_path = str(d / "IMG_0001.MOV")
    heic_path = str(d / "IMG_0001.HEIC")
    assert mov_path in pairs
    assert pairs[mov_path] == heic_path


# ---------------------------------------------------------------------------
# incremental skip test
# ---------------------------------------------------------------------------

def test_incremental_skip(tmp_path, monkeypatch):
    """Second scan on same folder: 0 indexed, N skipped."""
    import my_tools.photos.cache as cache_mod
    db_path = tmp_path / "test_photos.db"
    monkeypatch.setattr(cache_mod, "DB_PATH", db_path)

    # Create a minimal Takeout structure with one photo + sidecar
    root = make_takeout(tmp_path, [
        ("photo.jpg", b"jpeg data"),
        ("photo.jpg.supplemental-metadata.json", SAMPLE_SIDECAR_JSON),
    ])

    # First scan
    stats1 = scan_takeout(str(root), quiet=True, reset=False)
    assert stats1["indexed"] >= 1

    # Second scan — everything should be skipped
    stats2 = scan_takeout(str(root), quiet=True, reset=False)
    assert stats2["indexed"] == 0
    assert stats2["skipped"] >= 1
