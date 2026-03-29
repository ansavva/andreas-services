---
phase: 01-foundation-scanners
plan: "1.2"
subsystem: photos-scanner
tags: [sqlite, python, takeout, sidecar, live-photo, tdd]

# Dependency graph
requires:
  - "01-1: Installable my-tools package, Typer CLI, Python 3.13 venv"
provides:
  - "SQLite schema (5 tables, 8 indexes) at ~/.photo-migrate/photos.db"
  - "cache.py with 8 exported functions for DB access"
  - "takeout_scanner.py with 5 exported functions"
  - "scan-takeout command fully wired and functional"
  - "18 passing tests (6 schema + 12 scanner)"
affects: [01-3, 02-1]

# Tech tracking
tech-stack:
  added:
    - "sqlite3 stdlib — SQLite schema with 5 tables, 8 indexes, WAL mode"
    - "hashlib stdlib — SHA-256 file hashing (8192-byte chunks)"
    - "rich.progress.track() — progress bar wrapping media file list"
    - "rich.table.Table — scan summary output"
  patterns:
    - "TDD: RED (tests fail on missing module import) → GREEN (implementation passes all tests)"
    - "monkeypatch DB_PATH fixture pattern for test isolation"
    - "Five-stage sidecar cascade: edited-strip → standard → truncated → counter-shift → brute-force prefix"
    - "Live photo pair detection by stem matching with case-preserved path reconstruction"
    - "Incremental scan: is_takeout_file_indexed() short-circuit before hashing"

key-files:
  created:
    - "my-tools/python/my_tools/photos/cache.py — SQLite connection, schema init, 8 helper functions"
    - "my-tools/python/my_tools/tests/test_schema.py — 6 schema tests"
    - "my-tools/python/my_tools/tests/test_takeout_scanner.py — 12 scanner tests"
    - "my-tools/python/my_tools/photos/takeout_scanner.py — 5 exported scanner functions"
  modified:
    - "my-tools/python/my_tools/tests/conftest.py — added tmp_db fixture"
    - "my-tools/python/my_tools/photos/commands.py — wired scan-takeout to run_scan"

key-decisions:
  - "detect_live_photo_pairs() reconstructs paths using original filename case (not lowercased extension) to handle macOS case-sensitive path matching"
  - "Five-stage sidecar cascade copied verbatim from RESEARCH.md to handle both pre/post Oct 2024 Google Takeout formats"
  - "scan_takeout() collects live pairs per-directory with cache dict to avoid repeated os.scandir calls"

# Metrics
duration: ~8min
completed: "2026-03-29"
---

# Phase 1 Plan 2: SQLite Schema + Takeout Scanner Summary

**SQLite cache layer (5 tables, 8 indexes) and Google Takeout scanner with five-stage sidecar cascade, Live Photo pair detection, incremental skip, and Rich progress output**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-03-29
- **Tasks:** 2 (TDD: RED tests then GREEN implementation for each)
- **Files created:** 4, modified: 2
- **Tests:** 18 total (6 schema + 12 scanner) — all pass

## Accomplishments

- SQLite schema with all 5 tables (`google_photos`, `icloud_photos`, `missing_photos`, `import_log`, `scan_state`) and 8 performance indexes
- `cache.py` provides `get_connection()`, `init_schema()`, `upsert_google_photo()`, `upsert_icloud_photo()`, `is_takeout_file_indexed()`, `get_scan_state()`, `set_scan_state()`, `reset_database()`
- `takeout_scanner.py` implements full five-stage sidecar matching cascade (handles old `.json` and new `.supplemental-metadata.json` formats, truncation at 51 chars, counter-shift pattern)
- Live Photo pair detection by stem matching with original case preserved for reliable path resolution
- Incremental scan: second run on same folder yields 0 indexed, N skipped (confirmed by test)
- `my-tools photos scan-takeout /bad/path` exits 1 with clear error message (SETUP-03)
- Schema is idempotent (`CREATE TABLE IF NOT EXISTS`) — never wipes data without `--reset` (SAFE-03)

## SQLite Tables

| Table | Purpose |
|-------|---------|
| `google_photos` | One row per media file in Takeout export (file_path UNIQUE) |
| `icloud_photos` | One row per photo in Photos.app library (uuid PRIMARY KEY) |
| `missing_photos` | Phase 2 output: photos in Google not found in iCloud |
| `import_log` | Phase 3 audit trail for import operations |
| `scan_state` | Key-value store for incremental scan timestamps |

## cache.py Exported Functions

| Function | Purpose |
|----------|---------|
| `get_connection()` | Opens/creates SQLite DB with WAL mode + foreign keys |
| `init_schema(conn)` | Creates all 5 tables + 8 indexes idempotently |
| `upsert_google_photo(conn, data)` | INSERT OR REPLACE into google_photos |
| `upsert_icloud_photo(conn, data)` | INSERT OR REPLACE into icloud_photos |
| `is_takeout_file_indexed(conn, path)` | Returns True if file_path has sha256 in google_photos |
| `get_scan_state(conn, key)` | Retrieves value from scan_state; None if absent |
| `set_scan_state(conn, key, value)` | Upserts key-value in scan_state |
| `reset_database(conn)` | Drops all 5 tables then recreates schema |

## takeout_scanner.py Exported Functions

| Function | Purpose |
|----------|---------|
| `validate_takeout_folder(path)` | Checks for Takeout/Google Photos/ structure; SETUP-03 |
| `find_sidecar(media_path)` | Five-stage sidecar cascade |
| `parse_sidecar(sidecar_path)` | Extracts creation_time, width, height, lat/lon from JSON |
| `detect_live_photo_pairs(directory)` | Maps MOV paths → HEIC/JPG paths for Live Photos |
| `scan_takeout(path, quiet, reset)` | Main scanner: walks tree, indexes, returns stats dict |

## Sidecar Stages Implemented

1. **Stage 1** — Strip `-edited` suffix (`photo-edited.jpg` → look for `photo.jpg.*`)
2. **Stage 2** — Standard: `photo.jpg.supplemental-metadata.json` then `photo.jpg.json`
3. **Stage 3** — Truncated: when sidecar name exceeds 51 chars, try truncated suffix
4. **Stage 4** — Counter-shift: `foo(1).jpg` → `foo.jpg(1).supplemental-metadata.json`
5. **Stage 5** — Brute-force prefix scan of directory (46-char prefix)

## Task Commits

1. **Task 1: cache.py schema + helpers (RED + GREEN)** — `98da9cc`
2. **Task 2: takeout_scanner.py + wire commands.py (RED + GREEN)** — `c0c1df7`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed detect_live_photo_pairs() case-sensitive path reconstruction**
- **Found during:** Task 2 (GREEN test run — test_detect_live_photo_pairs failed)
- **Issue:** Research.md Pattern 6 reconstructs MOV/image paths by appending lowercase extension (e.g., `stem + ".mov"`), but the actual files may have uppercase extensions (`IMG_0001.MOV`). On macOS, the path `IMG_0001.MOV` is different from `IMG_0001.mov` in os.path comparisons within the scan loop.
- **Fix:** Track original filename (with case preserved) per stem alongside the lowercase extension for matching. Reconstruct paths using the original filename, not the lowercased extension.
- **Files modified:** `python/my_tools/photos/takeout_scanner.py`
- **Commit:** `c0c1df7`

## Known Stubs

None — all functionality in this plan is fully implemented and tested.

## Self-Check: PASSED

All created files verified present. All task commits verified in git log.

- FOUND: my-tools/python/my_tools/photos/cache.py
- FOUND: my-tools/python/my_tools/photos/takeout_scanner.py
- FOUND: my-tools/python/my_tools/tests/test_schema.py
- FOUND: my-tools/python/my_tools/tests/test_takeout_scanner.py
- FOUND: 98da9cc (Task 1 test+feat commit)
- FOUND: c0c1df7 (Task 2 feat commit)
