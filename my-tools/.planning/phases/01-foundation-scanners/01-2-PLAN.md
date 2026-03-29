---
plan: 1.2
phase: 1
wave: 2
depends_on:
  - "1.1"
files_modified:
  - python/my_tools/photos/cache.py
  - python/my_tools/photos/takeout_scanner.py
  - python/my_tools/photos/commands.py
  - python/my_tools/tests/conftest.py
  - python/my_tools/tests/test_schema.py
  - python/my_tools/tests/test_takeout_scanner.py
autonomous: true
requirements:
  - SETUP-03
  - TAKE-01
  - TAKE-02
  - TAKE-03
  - TAKE-04
  - TAKE-05
  - SAFE-01
  - SAFE-03

must_haves:
  truths:
    - "`~/.photo-migrate/photos.db` is created on first `scan-takeout` run and NOT recreated on re-run unless `--reset` is passed"
    - "Every media file in a Takeout export gets one row in `google_photos` with filename, file_path, creation_time, width, height, file_size, sha256, sidecar_found"
    - "The sidecar matcher finds sidecars in all five naming patterns (stage 1-5 from research)"
    - "A Live Photo MOV paired with a HEIC/JPG gets a single row with `is_live_photo_video=1` and `live_photo_partner_path` set — it is NOT counted as a standalone video"
    - "Re-running scan-takeout on an already-scanned folder skips all existing files (output shows 'Skipped' count > 0, 'Indexed' count = 0)"
    - "Passing a path that lacks `Takeout/Google Photos/` subdirectory prints a clear error and exits non-zero (SETUP-03)"
    - "No write operations to iCloud Photos are performed at any point during scan-takeout"
  artifacts:
    - path: "python/my_tools/photos/cache.py"
      provides: "SQLite connection, schema init, upsert helpers, scan state"
      exports: ["get_connection", "init_schema", "upsert_google_photo", "upsert_icloud_photo", "is_takeout_file_indexed", "get_scan_state", "set_scan_state", "reset_database"]
    - path: "python/my_tools/photos/takeout_scanner.py"
      provides: "scan_takeout() function, find_sidecar(), parse_sidecar(), detect_live_photo_pairs(), validate_takeout_folder()"
      exports: ["scan_takeout", "find_sidecar", "parse_sidecar", "detect_live_photo_pairs", "validate_takeout_folder"]
    - path: "python/my_tools/tests/test_schema.py"
      provides: "Tests for schema creation idempotency and SAFE-03 (no wipe without --reset)"
    - path: "python/my_tools/tests/test_takeout_scanner.py"
      provides: "Tests for sidecar matching, sidecar parsing, live photo detection, incremental skip"
  key_links:
    - from: "python/my_tools/photos/commands.py (scan_takeout command)"
      to: "python/my_tools/photos/takeout_scanner.py"
      via: "from my_tools.photos.takeout_scanner import scan_takeout as run_scan"
    - from: "python/my_tools/photos/takeout_scanner.py"
      to: "python/my_tools/photos/cache.py"
      via: "from my_tools.photos.cache import get_connection, init_schema, upsert_google_photo, ..."
    - from: "cache.py init_schema()"
      to: "~/.photo-migrate/photos.db"
      via: "CREATE TABLE IF NOT EXISTS — all 5 tables created on every connection"
---

<objective>
Build the data foundation (SQLite schema + cache.py helpers) and the Google Takeout scanner. After this plan, `my-tools photos scan-takeout <path>` walks a Takeout export, pairs sidecars via the five-stage cascade, detects Live Photo pairs, and writes one row per media file into `google_photos`. Re-runs are incremental.

Purpose: Ground truth for every photo in Google Photos is stored locally in SQLite. Phase 2 comparison reads from this table.

Output: cache.py (schema + helpers), takeout_scanner.py, updated commands.py (scan-takeout wired up), tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-foundation-scanners/01-CONTEXT.md
@.planning/phases/01-foundation-scanners/01-RESEARCH.md
@.planning/phases/01-foundation-scanners/01-1-SUMMARY.md

<interfaces>
<!-- From Plan 1.1: the commands.py stubs that scan-takeout currently bounces with Exit(1) -->
<!-- Plan 1.2 replaces those stubs by wiring scan_takeout() from takeout_scanner.py -->

From python/my_tools/photos/commands.py (Plan 1.1 stub):
```python
@app.command("scan-takeout")
def scan_takeout(
    path: Path = typer.Argument(..., help="Path to extracted Google Takeout folder"),
    quiet: bool = typer.Option(False, "--quiet", "-q", ...),
    reset: bool = typer.Option(False, "--reset", ...),
):
    """Scan a Google Takeout export and index all media into SQLite."""
    # Plan 1.2 replaces the stub body
```

<!-- Full schema SQL is in RESEARCH.md §SQLite Schema — copy verbatim -->
<!-- cache.py API contract is in RESEARCH.md §cache.py API Contract — implement exactly -->
<!-- Sidecar matching algorithm is in RESEARCH.md Pattern 4 — copy verbatim -->
<!-- Live Photo pair detection is in RESEARCH.md Pattern 6 — copy verbatim -->
<!-- Takeout folder validation is in RESEARCH.md Pattern 7 — copy verbatim -->
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write failing tests, then implement cache.py (schema + helpers)</name>

  <read_first>
    - .planning/phases/01-foundation-scanners/01-RESEARCH.md — §SQLite Schema (all 5 CREATE TABLE statements), §cache.py API Contract (function signatures)
    - .planning/phases/01-foundation-scanners/01-VALIDATION.md — Wave 0 requirements (test_schema.py stubs)
    - python/my_tools/tests/conftest.py — existing fixtures from Plan 1.1
  </read_first>

  <files>
    python/my_tools/tests/conftest.py
    python/my_tools/tests/test_schema.py
    python/my_tools/photos/cache.py
  </files>

  <behavior>
    - test_schema_created: After `init_schema(conn)`, all 5 tables exist (google_photos, icloud_photos, missing_photos, import_log, scan_state)
    - test_schema_idempotent: Calling `init_schema(conn)` twice does not raise and tables still exist (CREATE TABLE IF NOT EXISTS)
    - test_safe03_no_wipe: `get_connection()` + `init_schema()` on an existing DB does not drop data; row inserted before second init_schema() call still exists after
    - test_reset_database: `reset_database(conn)` drops and recreates tables; previously inserted row is gone
    - test_scan_state_roundtrip: `set_scan_state(conn, "k", "v")` then `get_scan_state(conn, "k")` returns "v"; missing key returns None
    - test_is_takeout_indexed: `is_takeout_file_indexed()` returns False for unknown path, True after `upsert_google_photo()` with that path and a sha256
  </behavior>

  <action>
    ### Step 1 — Extend conftest.py with shared DB fixture:
    Add to `python/my_tools/tests/conftest.py`:
    ```python
    import pytest, tempfile, os
    from pathlib import Path

    @pytest.fixture
    def tmp_db(tmp_path, monkeypatch):
        """Provide a temporary DB path and monkeypatch cache.DB_PATH."""
        db_path = tmp_path / "test_photos.db"
        import my_tools.photos.cache as cache_mod
        monkeypatch.setattr(cache_mod, "DB_PATH", db_path)
        return db_path
    ```

    ### Step 2 — Write RED tests in test_schema.py (run: all fail — cache.py does not exist yet):
    ```python
    import sqlite3, pytest
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
    ```

    ### Step 3 — Implement cache.py (GREEN):
    Implement the full cache.py with the exact API from RESEARCH.md §cache.py API Contract.
    Key details:
    - `DB_PATH = Path.home() / ".photo-migrate" / "photos.db"` (monkeypatched in tests)
    - `get_connection()`: creates parent dir, connects, sets `row_factory = sqlite3.Row`, enables WAL and foreign_keys
    - `init_schema(conn)`: runs all 5 CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS statements verbatim from RESEARCH.md §SQLite Schema
    - `upsert_google_photo(conn, data)`: `INSERT OR REPLACE INTO google_photos ...` — all columns
    - `upsert_icloud_photo(conn, data)`: `INSERT OR REPLACE INTO icloud_photos ...` — all columns
    - `is_takeout_file_indexed(conn, file_path)`: `SELECT 1 FROM google_photos WHERE file_path=? AND sha256 IS NOT NULL`
    - `get_scan_state(conn, key)`: `SELECT value FROM scan_state WHERE key=?` → str or None
    - `set_scan_state(conn, key, value)`: `INSERT OR REPLACE INTO scan_state(key, value) VALUES (?, ?)`
    - `reset_database(conn)`: DROP TABLE for each of the 5 tables, then call `init_schema(conn)`
  </action>

  <verify>
    <automated>cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/test_schema.py -v 2>&1</automated>
  </verify>

  <done>
    All 6 schema tests pass GREEN. `cache.py` exists with all 7 exported functions. Schema creates all 5 tables idempotently.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Write failing tests, then implement takeout_scanner.py and wire scan-takeout command</name>

  <read_first>
    - python/my_tools/photos/cache.py — functions to call (just implemented in Task 1)
    - .planning/phases/01-foundation-scanners/01-RESEARCH.md — Pattern 4 (five-stage sidecar matching, copy verbatim), Pattern 5 (parse_sidecar, copy verbatim), Pattern 6 (detect_live_photo_pairs, copy verbatim), Pattern 7 (validate_takeout_folder, copy verbatim), Pattern 2 (Rich progress bar), §MEDIA_EXTENSIONS set, §Pitfall 3 (sidecar format), §Pitfall 5 (width/height strings), §Pitfall 9 (duplicate paths across year+album folders)
    - python/my_tools/photos/commands.py — scan_takeout stub to replace
  </read_first>

  <files>
    python/my_tools/tests/test_takeout_scanner.py
    python/my_tools/photos/takeout_scanner.py
    python/my_tools/photos/commands.py
  </files>

  <behavior>
    - test_validate_takeout_folder_valid: path containing `Takeout/Google Photos/<subdir>/` returns (True, "")
    - test_validate_takeout_folder_inner: path containing `Google Photos/<subdir>/` (user passed inner dir) returns (True, "")
    - test_validate_takeout_folder_invalid: non-existent path returns (False, error_message)
    - test_find_sidecar_stage2_new: file `photo.jpg` with `photo.jpg.supplemental-metadata.json` present → returns sidecar path
    - test_find_sidecar_stage2_legacy: file `photo.jpg` with `photo.jpg.json` present (no new format) → returns sidecar path
    - test_find_sidecar_stage4_counter: file `photo(1).jpg` with `photo.jpg(1).supplemental-metadata.json` → returns sidecar path
    - test_find_sidecar_none: file with no matching sidecar → returns None
    - test_parse_sidecar_extracts_fields: JSON with photoTakenTime.timestamp "1609459200", width "4032", height "3024" → creation_time is ISO UTC, width=4032, height=3024 (integers)
    - test_detect_live_photo_pairs: directory with `IMG_0001.HEIC` + `IMG_0001.MOV` → MOV path maps to HEIC path
    - test_incremental_skip: scan same fixture twice → second scan reports 0 indexed, N skipped
  </behavior>

  <action>
    ### Step 1 — Write RED tests in test_takeout_scanner.py:
    Use `tmp_path` and `monkeypatch` (from pytest) to create fixture Takeout directory trees
    and monkeypatch `my_tools.photos.cache.DB_PATH` to a tmp DB.

    Fixture helper for creating Takeout structure:
    ```python
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
    ```

    Sample sidecar JSON content to use in tests:
    ```python
    SAMPLE_SIDECAR_JSON = json.dumps({
        "title": "photo.jpg",
        "photoTakenTime": {"timestamp": "1609459200", "formatted": "Jan 1, 2021"},
        "creationTime": {"timestamp": "1609459200"},
        "geoData": {"latitude": 37.7749, "longitude": -122.4194},
        "width": "4032",
        "height": "3024",
    })
    ```

    ### Step 2 — Implement takeout_scanner.py (GREEN):

    Module-level constants:
    ```python
    MEDIA_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tiff", ".tif",
        ".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv", ".dng", ".cr2",
        ".nef", ".arw", ".raw",
    }
    ```

    Implement these functions in this order (copy from RESEARCH.md patterns verbatim):
    1. `validate_takeout_folder(path: str) -> tuple[bool, str]` — Pattern 7
    2. `find_sidecar(media_path: str) -> str | None` — Pattern 4 (all 5 stages)
    3. `parse_sidecar(sidecar_path: str) -> dict` — Pattern 5
       - Casts width/height via `int(data.get("width", 0)) or None` (Pitfall 5)
    4. `detect_live_photo_pairs(directory: str) -> dict[str, str]` — Pattern 6
    5. `scan_takeout(path: str, quiet: bool = False, reset: bool = False) -> dict` — main scanner:
       - Validates folder with `validate_takeout_folder()`; prints error and `raise typer.Exit(code=1)` if invalid
       - Calls `cache.get_connection()` and `cache.init_schema(conn)`
       - If `reset=True`, calls `cache.reset_database(conn)`
       - Collects all Live Photo pairs by scanning per-directory with `detect_live_photo_pairs()`
       - Walks the Takeout tree with `os.walk()`, collecting all files whose extension is in `MEDIA_EXTENSIONS`
       - For each media file: check `cache.is_takeout_file_indexed()` → skip if True (TAKE-05)
       - Skipped files: increment stats["skipped"], continue
       - Not skipped: compute sha256 via `hashlib.sha256()` reading in chunks (8192 bytes)
       - Call `find_sidecar()` to get sidecar path
       - Call `parse_sidecar()` if sidecar found; else set creation_time = datetime.fromtimestamp(os.path.getmtime(media_path), tz=timezone.utc).isoformat(), mark sidecar_found=0
       - Check if this file is a Live Photo MOV: `mov_path in live_pairs` → set `is_live_photo_video=1`, `live_photo_partner_path=live_pairs[mov_path]`
       - Build data dict and call `cache.upsert_google_photo(conn, data)`
       - Use `rich.progress.track()` unless `quiet=True` (Pattern 2)
       - After loop: `cache.set_scan_state(conn, "takeout_last_scan_at", scan_started_at)`, `conn.commit()`, `conn.close()`
       - Print Rich summary table: Indexed, Skipped, No sidecar, Errors
       - Warn if no_sidecar > 0 with yellow Rich message
       - Return stats dict

    ### Step 3 — Wire scan_takeout command in commands.py:
    Replace the stub body:
    ```python
    from my_tools.photos.takeout_scanner import scan_takeout as run_scan

    @app.command("scan-takeout")
    def scan_takeout(path, quiet, reset):
        run_scan(str(path), quiet=quiet, reset=reset)
    ```
  </action>

  <verify>
    <automated>cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/test_takeout_scanner.py my_tools/tests/test_schema.py -v 2>&1</automated>
  </verify>

  <done>
    All scanner tests pass GREEN. `my-tools photos scan-takeout --help` exits 0. Running `my-tools photos scan-takeout /nonexistent` exits non-zero with error message. All schema tests still pass (no regression).
  </done>
</task>

</tasks>

## Verification

### must_haves
- `~/.photo-migrate/photos.db` is created on first run; re-running does not wipe it (SAFE-03)
- `my-tools photos scan-takeout /bad/path` exits 1 with message mentioning `Takeout/Google Photos/` (SETUP-03)
- All 5 sidecar stages are implemented in `find_sidecar()` — grep confirms `supplemental-metadata` and counter-shift pattern
- Live Photo MOVs have `is_live_photo_video=1` in DB
- Second scan on same folder: 0 indexed, all skipped

### automated
- `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/test_schema.py my_tools/tests/test_takeout_scanner.py -v` — all tests pass
- `grep -n "supplemental-metadata" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/takeout_scanner.py` — exits 0
- `grep -n "is_live_photo_video" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/takeout_scanner.py` — exits 0
- `grep -n "def find_sidecar\|def parse_sidecar\|def detect_live_photo\|def validate_takeout\|def scan_takeout" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/takeout_scanner.py` — exits 0, shows all 5 functions
- `grep -n "def get_connection\|def init_schema\|def upsert_google\|def upsert_icloud\|def is_takeout_file\|def get_scan_state\|def set_scan_state\|def reset_database" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/cache.py` — exits 0, shows all 7 functions

<output>
After completion, create `.planning/phases/01-foundation-scanners/01-2-SUMMARY.md` with:
- SQLite schema tables created and their purpose
- cache.py functions exported
- takeout_scanner.py functions exported and sidecar stages implemented
- Test coverage summary
- Any deviations from this plan
</output>
