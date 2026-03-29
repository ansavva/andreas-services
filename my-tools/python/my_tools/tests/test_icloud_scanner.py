"""
Tests for icloud_scanner.py — all photos mocked via MockPhotoInfo.
No real Photos library required.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@dataclass
class MockPhotoInfo:
    uuid: str = "test-uuid-001"
    filename: str = "IMG_0001.HEIC"
    original_filename: str = "IMG_0001.HEIC"
    date: datetime = field(
        default_factory=lambda: datetime(2021, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    )
    date_added: datetime = field(
        default_factory=lambda: datetime(2021, 1, 2, tzinfo=timezone.utc)
    )
    width: int = 4032
    height: int = 3024
    original_filesize: int = 5_000_000
    fingerprint: str = "fp_abc123"
    cloud_guid: str = "cloud-guid-001"
    hexdigest: str = "hex_abc123"
    iscloudasset: bool = True
    ismissing: bool = False


def test_upserts_regular_photo(tmp_db, monkeypatch):
    """A photo with ismissing=False is indexed into icloud_photos with correct fields."""
    mock_photo = MockPhotoInfo()
    mock_db_instance = MagicMock()
    mock_db_instance.photos.return_value = [mock_photo]
    mock_db_instance.query.return_value = []

    with patch(
        "my_tools.photos.icloud_scanner.osxphotos.PhotosDB",
        return_value=mock_db_instance,
    ), patch(
        "my_tools.photos.icloud_scanner.list_photo_libraries",
        return_value=[],
    ), patch(
        "pathlib.Path.exists", return_value=True
    ):
        from my_tools.photos.icloud_scanner import scan_icloud

        stats = scan_icloud(library_path="/fake/library.photoslibrary", quiet=True)

    import my_tools.photos.cache as cache_mod

    conn = cache_mod.get_connection()
    rows = conn.execute(
        "SELECT * FROM icloud_photos WHERE uuid=?", ("test-uuid-001",)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["fingerprint"] == "fp_abc123"
    assert stats["indexed"] == 1
    assert stats["errors"] == 0
    conn.close()


def test_upserts_missing_photo(tmp_db, monkeypatch):
    """A cloud-only photo (ismissing=True) is indexed with non-null fingerprint (ICLOUD-03)."""
    mock_photo = MockPhotoInfo(
        uuid="cloud-only-uuid",
        ismissing=True,
        fingerprint="fp123",
        hexdigest=None,
    )
    mock_db_instance = MagicMock()
    mock_db_instance.photos.return_value = [mock_photo]
    mock_db_instance.query.return_value = []

    with patch(
        "my_tools.photos.icloud_scanner.osxphotos.PhotosDB",
        return_value=mock_db_instance,
    ), patch(
        "my_tools.photos.icloud_scanner.list_photo_libraries",
        return_value=[],
    ), patch(
        "pathlib.Path.exists", return_value=True
    ):
        from my_tools.photos import icloud_scanner
        import importlib
        importlib.reload(icloud_scanner)
        stats = icloud_scanner.scan_icloud(
            library_path="/fake/library.photoslibrary", quiet=True
        )

    import my_tools.photos.cache as cache_mod

    conn = cache_mod.get_connection()
    rows = conn.execute(
        "SELECT * FROM icloud_photos WHERE uuid=?", ("cloud-only-uuid",)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["fingerprint"] == "fp123"
    assert rows[0]["ismissing"] == 1
    conn.close()


def test_incremental_uses_query_options(tmp_db, monkeypatch):
    """When scan_state has 'icloud_last_scan_at', scanner calls photosdb.query(), not .photos()."""
    mock_db_instance = MagicMock()
    mock_db_instance.query.return_value = []

    with patch(
        "my_tools.photos.icloud_scanner.osxphotos.PhotosDB",
        return_value=mock_db_instance,
    ), patch(
        "my_tools.photos.icloud_scanner.list_photo_libraries",
        return_value=[],
    ), patch(
        "pathlib.Path.exists", return_value=True
    ):
        from my_tools.photos import icloud_scanner, cache
        import importlib
        importlib.reload(icloud_scanner)

        # Pre-seed scan state with a previous scan timestamp
        conn = cache.get_connection()
        cache.init_schema(conn)
        cache.set_scan_state(conn, "icloud_last_scan_at", "2021-01-01T00:00:00+00:00")
        conn.commit()
        conn.close()

        icloud_scanner.scan_icloud(
            library_path="/fake/library.photoslibrary", quiet=True
        )

    mock_db_instance.query.assert_called_once()
    mock_db_instance.photos.assert_not_called()


def test_full_scan_on_first_run(tmp_db, monkeypatch):
    """When no 'icloud_last_scan_at' in scan_state, scanner calls photosdb.photos()."""
    mock_db_instance = MagicMock()
    mock_db_instance.photos.return_value = []

    with patch(
        "my_tools.photos.icloud_scanner.osxphotos.PhotosDB",
        return_value=mock_db_instance,
    ), patch(
        "my_tools.photos.icloud_scanner.list_photo_libraries",
        return_value=[],
    ), patch(
        "pathlib.Path.exists", return_value=True
    ):
        from my_tools.photos import icloud_scanner
        import importlib
        importlib.reload(icloud_scanner)
        icloud_scanner.scan_icloud(
            library_path="/fake/library.photoslibrary", quiet=True
        )

    mock_db_instance.photos.assert_called_once()
    mock_db_instance.query.assert_not_called()


def test_library_not_found_error(tmp_db, monkeypatch):
    """If default path absent and list_photo_libraries() returns [], raises FileNotFoundError."""
    from my_tools.photos import icloud_scanner
    import importlib
    importlib.reload(icloud_scanner)

    with patch.object(icloud_scanner, "list_photo_libraries", return_value=[]), patch(
        "pathlib.Path.exists", return_value=False
    ):
        with pytest.raises(FileNotFoundError, match="Photos library not found"):
            icloud_scanner.scan_icloud(quiet=True)


def test_multiple_libraries_error(tmp_db, monkeypatch):
    """If list_photo_libraries() returns 2 libraries, raises ValueError with --library guidance."""
    from pathlib import Path
    from my_tools.photos import icloud_scanner
    import importlib
    importlib.reload(icloud_scanner)

    with patch.object(
        icloud_scanner,
        "list_photo_libraries",
        return_value=[Path("/lib/A.photoslibrary"), Path("/lib/B.photoslibrary")],
    ), patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(ValueError, match="--library"):
            icloud_scanner.scan_icloud(quiet=True)
