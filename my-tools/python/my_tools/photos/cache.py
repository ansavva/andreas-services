"""SQLite connection, schema init, and upsert helpers for photo migration tool."""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".photo-migrate" / "photos.db"


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database, creating parent dir if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if not present. Idempotent."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS google_photos (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path               TEXT NOT NULL UNIQUE,
            filename                TEXT NOT NULL,
            creation_time           TEXT,
            width                   INTEGER,
            height                  INTEGER,
            file_size               INTEGER,
            sha256                  TEXT,
            sidecar_found           INTEGER NOT NULL DEFAULT 1,
            media_type              TEXT NOT NULL DEFAULT 'photo',
            is_live_photo_video     INTEGER NOT NULL DEFAULT 0,
            live_photo_partner_path TEXT,
            scanned_at              TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_google_creation_time ON google_photos(creation_time);
        CREATE INDEX IF NOT EXISTS idx_google_sha256 ON google_photos(sha256);
        CREATE INDEX IF NOT EXISTS idx_google_filename ON google_photos(filename);

        CREATE TABLE IF NOT EXISTS icloud_photos (
            uuid                TEXT PRIMARY KEY,
            filename            TEXT NOT NULL,
            original_filename   TEXT,
            date                TEXT NOT NULL,
            date_added          TEXT,
            width               INTEGER,
            height              INTEGER,
            original_filesize   INTEGER,
            fingerprint         TEXT,
            cloud_guid          TEXT,
            hexdigest           TEXT,
            iscloudasset        INTEGER NOT NULL DEFAULT 0,
            ismissing           INTEGER NOT NULL DEFAULT 0,
            scanned_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_icloud_date ON icloud_photos(date);
        CREATE INDEX IF NOT EXISTS idx_icloud_fingerprint ON icloud_photos(fingerprint);
        CREATE INDEX IF NOT EXISTS idx_icloud_cloud_guid ON icloud_photos(cloud_guid);
        CREATE INDEX IF NOT EXISTS idx_icloud_filename_date ON icloud_photos(filename, date);
        CREATE INDEX IF NOT EXISTS idx_icloud_dimensions ON icloud_photos(width, height);

        CREATE TABLE IF NOT EXISTS missing_photos (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id           INTEGER NOT NULL REFERENCES google_photos(id),
            filename            TEXT NOT NULL,
            creation_time       TEXT NOT NULL,
            match_tier          TEXT,
            status              TEXT NOT NULL DEFAULT 'pending',
            failure_reason      TEXT,
            identified_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS import_log (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id           INTEGER NOT NULL REFERENCES google_photos(id),
            tmp_path            TEXT,
            status              TEXT NOT NULL,
            error_message       TEXT,
            imported_at         TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS scan_state (
            key                 TEXT PRIMARY KEY,
            value               TEXT,
            updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)


def upsert_google_photo(conn: sqlite3.Connection, data: dict) -> None:
    """Insert or replace a Google Takeout photo record.
    Key: file_path (UNIQUE constraint handles dedup)."""
    conn.execute(
        """INSERT OR REPLACE INTO google_photos
           (file_path, filename, creation_time, width, height, file_size,
            sha256, sidecar_found, media_type, is_live_photo_video, live_photo_partner_path)
           VALUES (:file_path, :filename, :creation_time, :width, :height, :file_size,
                   :sha256, :sidecar_found, :media_type, :is_live_photo_video, :live_photo_partner_path)
        """,
        data,
    )


def upsert_icloud_photo(conn: sqlite3.Connection, data: dict) -> None:
    """Insert or replace an iCloud photo record.
    Key: uuid (PRIMARY KEY handles dedup)."""
    conn.execute(
        """INSERT OR REPLACE INTO icloud_photos
           (uuid, filename, original_filename, date, date_added, width, height,
            original_filesize, fingerprint, cloud_guid, hexdigest, iscloudasset, ismissing)
           VALUES (:uuid, :filename, :original_filename, :date, :date_added, :width, :height,
                   :original_filesize, :fingerprint, :cloud_guid, :hexdigest, :iscloudasset, :ismissing)
        """,
        data,
    )


def is_takeout_file_indexed(conn: sqlite3.Connection, file_path: str) -> bool:
    """Return True if file_path already has a sha256 in google_photos."""
    row = conn.execute(
        "SELECT 1 FROM google_photos WHERE file_path=? AND sha256 IS NOT NULL",
        (file_path,),
    ).fetchone()
    return row is not None


def get_scan_state(conn: sqlite3.Connection, key: str) -> str | None:
    """Retrieve a value from scan_state by key. Returns None if not set."""
    row = conn.execute(
        "SELECT value FROM scan_state WHERE key=?",
        (key,),
    ).fetchone()
    return row["value"] if row else None


def set_scan_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a key-value pair in scan_state."""
    conn.execute(
        "INSERT OR REPLACE INTO scan_state(key, value) VALUES (?, ?)",
        (key, value),
    )


def reset_database(conn: sqlite3.Connection) -> None:
    """Drop and recreate all tables. Only called when --reset is passed."""
    conn.executescript("""
        DROP TABLE IF EXISTS import_log;
        DROP TABLE IF EXISTS missing_photos;
        DROP TABLE IF EXISTS google_photos;
        DROP TABLE IF EXISTS icloud_photos;
        DROP TABLE IF EXISTS scan_state;
    """)
    init_schema(conn)
