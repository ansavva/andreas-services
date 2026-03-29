# Roadmap: my-tools CLI + Photo Library Migration

**Project:** Unified my-tools CLI with Google Photos → iCloud migration as first feature group
**Core Value:** Find every photo in Google Photos that isn't in iPhotos and import it — never lose a single photo.
**Granularity:** Coarse (3 phases)
**Coverage:** 41/41 v1 requirements mapped

---

## Key Decisions (Embedded)

| Decision | Detail |
|----------|--------|
| Unified my-tools CLI | Single Typer app with command groups; `my-tools <group> <command>`; adding new groups requires only creating a new module |
| Existing tools wrapped | `kindle_formatter.py` → `my-tools media kindle`; `url_to_qr.py` → `my-tools qr generate` |
| Python 3.13 venv | Research confirmed Python 3.13 is installed at `/opt/homebrew/bin/python3.13`; osxphotos 0.75.6 explicitly supports 3.13; no need to install 3.12 |
| Google Takeout (not API) | `photoslibrary.readonly` scope removed April 2025; user does one-time export at takeout.google.com |
| Compound key matching | Timestamp ±60s + dimensions + filename stem; NOT hash-only (HEIC/JPEG cross-format breaks SHA-256) |
| exiftool CLI required | Metadata embedding uses `exiftool` binary; must be installed separately (`brew install exiftool`) |
| photoscript for import | `photoscript.import_photos()` via AppleScript bridge; `photokit` is WIP and must not be used |
| No deletions ever | Tool never deletes from Google Takeout or iCloud Photos — read/import only |

---

## Phases

- [ ] **Phase 1: Foundation & Scanners** — CLI framework, Python environment, SQLite schema, Takeout scanner, iCloud scanner
- [ ] **Phase 2: Compare & Report** — Compound key comparator, missing photo identification, human-readable report
- [ ] **Phase 3: Metadata & Import** — exiftool metadata embedding, download-embed-import loop, dry-run, crash recovery

---

## Phase Details

### Phase 1: Foundation & Scanners

**Goal:** Unified my-tools CLI is invokable, both photo libraries are indexed in SQLite, existing tools are wrapped.

**Depends on:** Nothing (first phase)

**Requirements:** CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, SETUP-01, SETUP-02, SETUP-03, TAKE-01, TAKE-02, TAKE-03, TAKE-04, TAKE-05, ICLOUD-01, ICLOUD-02, ICLOUD-03, ICLOUD-04, SAFE-01, SAFE-03

**Success Criteria:**
1. `my-tools --help` lists all groups (photos, media, qr) with descriptions; `my-tools photos --help` lists all photo subcommands.
2. `my-tools media kindle <pdf>` and `my-tools qr generate <url>` work identically to the original standalone scripts.
3. `my-tools photos scan-takeout <path>` populates the `google_photos` SQLite table with filename, creation timestamp (from JSON sidecar), width, height, SHA-256 for every media item.
4. `my-tools photos scan-icloud` populates the `icloud_photos` table including cloud-only stubs (Optimize Mac Storage).
5. Re-running either scan skips already-indexed items (faster than initial run, observable via output).
6. SQLite DB is not wiped on re-run unless `--reset` is passed.

**Plans:** 2/3 plans executed
- [x] 01-1-PLAN.md — CLI framework: `python/my_tools/` package, Typer multi-group app, `my-tools` entry point, `media kindle`, `qr generate`, `photos` group stub, Python 3.13 venv
- [x] 01-2-PLAN.md — SQLite schema + Takeout scanner: `cache.py`, all 5 tables, `scan-takeout` command with five-stage sidecar pairing, Live Photo detection, incremental skip
- [ ] 01-3-PLAN.md — iCloud scanner + setup: `scan-icloud` via osxphotos.PhotosDB(dbfile=...), Optimize Mac Storage handling, incremental re-scan, `setup` command with Takeout instructions

---

### Phase 2: Compare & Report

**Goal:** User can see exactly which photos are in Google Takeout but missing from iCloud, with enough detail to trust the result before any import.

**Depends on:** Phase 1

**Requirements:** COMP-01, COMP-02, COMP-03, COMP-04, COMP-05, COMP-06, RPT-01, RPT-02, RPT-03, RPT-04

**Success Criteria:**
1. `my-tools photos compare` produces a `missing_photos` table — Tier 1 (±60s + dimensions), Tier 2 (±3600s for DST), filename stem tiebreaker applied.
2. `my-tools photos report` prints summary: total Takeout count, total iCloud count, missing count, Tier 1/2 match counts, sample table of missing photos.
3. `my-tools photos report` writes a timestamped file to disk for diff across runs.
4. DST-matched photos (Tier 2) do not appear as missing.
5. Running `compare` twice produces identical output (idempotent).

**Plans:**
- Plan 2.1: Comparator — pure SQL compound-key join (Tier 1: ±60s + width + height; Tier 2: ±3600s + dimensions; filename stem tiebreaker), `missing_photos` table with confidence tier, idempotent on re-run
- Plan 2.2: Report Command — `my-tools photos report` subcommand, grouped summary by tier and year-month, sample table of missing items, timestamped output file

---

### Phase 3: Metadata & Import

**Goal:** Every missing photo identified in Phase 2 is imported into Photos.app with original date and GPS preserved.

**Depends on:** Phase 2

**Requirements:** META-01, META-02, META-03, META-04, META-05, IMP-01, IMP-02, IMP-03, IMP-04, IMP-05, IMP-06, IMP-07, SAFE-02, SAFE-04

**Success Criteria:**
1. `my-tools photos import-missing --dry-run` prints what would be imported with zero side effects.
2. `my-tools photos import-missing` without `--confirm` is refused with an explanatory message.
3. Import loop: download → exiftool embed (date + GPS) → photoscript import → delete temp file — at most one temp file on disk at any time.
4. Interrupted import resumes from `import_log` on re-run (no duplicates).
5. Missing exiftool produces a clear warning with installation instructions; import is blocked.
6. After each batch, a log file records every attempted photo with outcome.

**Plans:**
- Plan 3.1: Metadata Embedding — exiftool detection and version check, extract `photoTakenTime` and GPS from JSON sidecar, `exiftool` subprocess call to write DateTimeOriginal + GPS coords, post-write verification
- Plan 3.2: Import Engine — `my-tools photos import-missing` with `--dry-run` and `--confirm`, download-embed-import-delete loop, photoscript import, SQLite import_log, crash recovery, pre-batch summary, disk log

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Scanners | 2/3 | In Progress|  |
| 2. Compare & Report | 0/2 | Not started | - |
| 3. Metadata & Import | 0/2 | Not started | - |

---

## Milestone: v1.0

v1.0 is complete when:
- `my-tools` CLI works for all groups (photos, media, qr)
- All missing photos identified by `compare` and reviewed via `report`
- All missing photos imported into Photos.app with original dates and GPS coordinates
- Import log confirms zero failures (or all failures accounted for)
- No photo deleted from Google Takeout or iCloud Photos at any point
- User can run `scan-icloud` again and confirm previously-missing photos now appear in iCloud

---

*Roadmap created: 2026-03-28*
*Last updated: 2026-03-28 — Phase 1 plans written (01-1, 01-2, 01-3)*
