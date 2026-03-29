# Requirements: my-tools CLI + Photo Library Migration

**Defined:** 2026-03-28
**Core Value:** Find every photo in Google Photos that isn't in iPhotos and import it — never lose a single photo.

## v1 Requirements

### CLI Framework

- [x] **CLI-01**: Single entry point `my-tools` (or `python -m my_tools`) exposes all tools as grouped subcommands
- [x] **CLI-02**: `my-tools --help` lists all available groups with one-line descriptions
- [x] **CLI-03**: `my-tools <group> --help` lists all commands in that group with descriptions and parameters
- [x] **CLI-04**: `my-tools <group> <command> --help` shows full parameter docs for a single command
- [x] **CLI-05**: Adding a new tool group requires only: create a new directory under `my_tools/`, add a Typer app, register it in one place
- [x] **CLI-06**: Existing tools (kindle formatter, QR code generator) are wrapped as CLI groups (`my-tools media kindle`, `my-tools qr generate`)

### Setup

- [x] **SETUP-01**: Tool runs with Python 3.13 in a dedicated venv (`python/venv/`, replacing existing 3.9 venv)
- [ ] **SETUP-02**: Tool provides step-by-step instructions for requesting a Google Takeout export (shown via `my-tools photos setup`)
- [x] **SETUP-03**: Tool validates that a provided Takeout folder is structurally complete

### Takeout Scanner

- [x] **TAKE-01**: CLI command `my-tools photos scan-takeout <path>` scans a Google Takeout export folder and indexes all photos/videos
- [x] **TAKE-02**: For each media item, stores: filename, file path, creation timestamp (from JSON sidecar), width, height, file size, SHA-256 hash in SQLite
- [x] **TAKE-03**: Parses Google's `.supplemental-metadata.json` (and legacy `.json`) sidecars; handles all 3 naming patterns (standard, 51-char truncation, counter-shift)
- [x] **TAKE-04**: Handles Live Photo pairs (HEIC + MOV with same timestamp) without double-counting
- [x] **TAKE-05**: Re-runs are incremental — skips already-indexed files using SQLite cache

### iCloud Scanner

- [ ] **ICLOUD-01**: CLI command `my-tools photos scan-icloud` scans the local Photos.app library via osxphotos
- [ ] **ICLOUD-02**: For each photo, stores: filename, creation date, width, height, file size, cloud GUID, osxphotos fingerprint in SQLite
- [ ] **ICLOUD-03**: Handles Optimize Mac Storage — reads metadata for cloud-only photos without local file
- [ ] **ICLOUD-04**: Re-runs are incremental — only re-scans photos added/modified since last scan

### Comparison

- [ ] **COMP-01**: CLI command `my-tools photos compare` matches Takeout photos against iCloud photos
- [ ] **COMP-02**: Tier 1 match: creation timestamp ±60s + same width + height
- [ ] **COMP-03**: Tier 2 match: creation timestamp ±3600s + same dimensions (catches DST off-by-one)
- [ ] **COMP-04**: Filename stem match as tiebreaker when timestamp windows overlap
- [ ] **COMP-05**: Photos matched by any tier marked as "found"; only unmatched photos are "missing"
- [ ] **COMP-06**: Outputs count of missing, Tier 1 matches, Tier 2 matches

### Report

- [ ] **RPT-01**: CLI command `my-tools photos report` generates a human-readable report of missing photos
- [ ] **RPT-02**: Report shows: total in Takeout, total in iCloud, missing count, sample of missing photos (filename, date, dimensions)
- [ ] **RPT-03**: Report saved to a timestamped file so multiple runs can be compared
- [ ] **RPT-04**: Missing photos listed with enough detail to identify them (date, filename, size)

### Metadata Preservation

- [ ] **META-01**: For each Google Takeout photo, reads original creation date from JSON sidecar and embeds into EXIF before import
- [ ] **META-02**: GPS/geolocation data from Google's JSON sidecar is embedded into EXIF before import
- [ ] **META-03**: Uses `exiftool` CLI to write metadata into photo files before importing
- [ ] **META-04**: If exiftool is not installed, tool warns and provides installation instructions
- [ ] **META-05**: Metadata embedding verified: tool reads back EXIF to confirm date and GPS present

### Import

- [ ] **IMP-01**: CLI command `my-tools photos import-missing` downloads and imports missing photos into Photos.app
- [ ] **IMP-02**: Dry-run mode (`--dry-run`) shows what would be imported without doing anything
- [ ] **IMP-03**: Always requires explicit `--confirm` flag before any import begins
- [ ] **IMP-04**: Downloads one photo at a time to a temp file, embeds metadata, imports via photoscript, deletes temp file
- [ ] **IMP-05**: Progress tracked in SQLite — re-runs skip already-imported photos
- [ ] **IMP-06**: Import log saved: each photo logged with Takeout path, timestamp, GPS coords if present, success/failure
- [ ] **IMP-07**: Never deletes anything from Google Takeout or iCloud Photos

### Safety

- [x] **SAFE-01**: No write operations to iCloud Photos library except via explicit import command
- [ ] **SAFE-02**: All destructive-adjacent operations require `--confirm` flag
- [x] **SAFE-03**: SQLite database is never wiped without explicit `--reset` flag
- [ ] **SAFE-04**: Tool prints a summary of what it intends to do before each import batch

## v2 Requirements

### Quality of Life

- **QOL-01**: HTML report with thumbnail previews of missing photos
- **QOL-02**: Album preservation — import missing photos into matching iCloud albums
- **QOL-03**: Progress bar with estimated time remaining during import

### Cleanup

- **CLEAN-01**: After confirming all photos are in iCloud, generate list of Google Photos that can safely be deleted
- **CLEAN-02**: Script to stop syncing iPhone to Google Photos (instructions only)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Google Photos API access | photoslibrary.readonly scope removed April 2025 |
| Deleting from Google Photos | Out of scope until migration confirmed complete (v2+) |
| Deduplication within iCloud | Not needed — only care about missing photos |
| Cloud/AWS execution | Local Mac tool only |
| Mobile app or web UI | CLI is sufficient |
| Batch download of full Google library | Limited local storage; only download confirmed-missing photos |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CLI-01 | Phase 1 | Pending |
| CLI-02 | Phase 1 | Pending |
| CLI-03 | Phase 1 | Pending |
| CLI-04 | Phase 1 | Pending |
| CLI-05 | Phase 1 | Pending |
| CLI-06 | Phase 1 | Pending |
| SETUP-01 | Phase 1 | Pending |
| SETUP-02 | Phase 1 | Pending |
| SETUP-03 | Phase 1 | Complete |
| TAKE-01 | Phase 1 | Complete |
| TAKE-02 | Phase 1 | Complete |
| TAKE-03 | Phase 1 | Complete |
| TAKE-04 | Phase 1 | Complete |
| TAKE-05 | Phase 1 | Complete |
| ICLOUD-01 | Phase 1 | Pending |
| ICLOUD-02 | Phase 1 | Pending |
| ICLOUD-03 | Phase 1 | Pending |
| ICLOUD-04 | Phase 1 | Pending |
| SAFE-01 | Phase 1 | Complete |
| SAFE-03 | Phase 1 | Complete |
| COMP-01 | Phase 2 | Pending |
| COMP-02 | Phase 2 | Pending |
| COMP-03 | Phase 2 | Pending |
| COMP-04 | Phase 2 | Pending |
| COMP-05 | Phase 2 | Pending |
| COMP-06 | Phase 2 | Pending |
| RPT-01 | Phase 2 | Pending |
| RPT-02 | Phase 2 | Pending |
| RPT-03 | Phase 2 | Pending |
| RPT-04 | Phase 2 | Pending |
| META-01 | Phase 3 | Pending |
| META-02 | Phase 3 | Pending |
| META-03 | Phase 3 | Pending |
| META-04 | Phase 3 | Pending |
| META-05 | Phase 3 | Pending |
| IMP-01 | Phase 3 | Pending |
| IMP-02 | Phase 3 | Pending |
| IMP-03 | Phase 3 | Pending |
| IMP-04 | Phase 3 | Pending |
| IMP-05 | Phase 3 | Pending |
| IMP-06 | Phase 3 | Pending |
| IMP-07 | Phase 3 | Pending |
| SAFE-02 | Phase 3 | Pending |
| SAFE-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 41
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-28 — added CLI framework requirements (CLI-01..06)*
