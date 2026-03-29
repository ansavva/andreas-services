import sqlite3
import pytest
from my_tools.photos.cache import (
    get_connection, init_schema, reset_database,
    get_scan_state, set_scan_state, is_takeout_file_indexed,
    upsert_google_photo,
)

EXPECTED_TABLES = {"google_photos", "icloud_photos", "missing_photos", "import_log", "scan_state"}


def test_schema_created(tmp_db):
    conn = get_connection()
    init_schema(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert EXPECTED_TABLES.issubset(tables)
    conn.close()


def test_schema_idempotent(tmp_db):
    conn = get_connection()
    init_schema(conn)
    init_schema(conn)  # second call must not raise
    conn.close()


def test_safe03_no_wipe(tmp_db):
    conn = get_connection()
    init_schema(conn)
    conn.execute(
        "INSERT INTO google_photos (file_path, filename, sha256, sidecar_found) "
        "VALUES (?, ?, ?, ?)", ("/a/b.jpg", "b.jpg", "abc123", 1)
    )
    conn.commit()
    init_schema(conn)  # must not drop data
    count = conn.execute("SELECT COUNT(*) FROM google_photos").fetchone()[0]
    assert count == 1
    conn.close()


def test_reset_database(tmp_db):
    conn = get_connection()
    init_schema(conn)
    conn.execute(
        "INSERT INTO google_photos (file_path, filename, sha256, sidecar_found) "
        "VALUES (?, ?, ?, ?)", ("/a/b.jpg", "b.jpg", "abc123", 1)
    )
    conn.commit()
    reset_database(conn)
    count = conn.execute("SELECT COUNT(*) FROM google_photos").fetchone()[0]
    assert count == 0
    conn.close()


def test_scan_state_roundtrip(tmp_db):
    conn = get_connection()
    init_schema(conn)
    assert get_scan_state(conn, "missing_key") is None
    set_scan_state(conn, "k", "v")
    conn.commit()
    assert get_scan_state(conn, "k") == "v"
    conn.close()


def test_is_takeout_indexed(tmp_db):
    conn = get_connection()
    init_schema(conn)
    assert not is_takeout_file_indexed(conn, "/a/b.jpg")
    upsert_google_photo(conn, {
        "file_path": "/a/b.jpg", "filename": "b.jpg",
        "creation_time": None, "width": None, "height": None,
        "file_size": 100, "sha256": "deadbeef",
        "sidecar_found": 1, "media_type": "photo",
        "is_live_photo_video": 0, "live_photo_partner_path": None,
    })
    conn.commit()
    assert is_takeout_file_indexed(conn, "/a/b.jpg")
    conn.close()
