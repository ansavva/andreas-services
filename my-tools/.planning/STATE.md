---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: "v1.0 is complete when:"
status: in-progress
last_updated: "2026-03-29T15:16:32Z"
progress:
  total_phases: 3
  completed_phases: 0
  total_plans: 3
  completed_plans: 1
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-28)

**Core value:** Find every photo in Google Photos that isn't in iPhotos and import it — never lose a single photo.
**Current focus:** Phase 01 — foundation-scanners

## Current Phase

Phase 1: Foundation & Scanners — in progress (Plan 1.1 complete, Plans 1.2 and 1.3 remaining).

## Current Plan

Phase 1, Plan 2 of 3 (01-2-PLAN.md)

## Phase Summary

| Phase | Name | Status |
|-------|------|--------|
| 1 | Foundation & Scanners | In progress (1/3 plans complete) |
| 2 | Compare & Report | Not started |
| 3 | Metadata & Import | Not started |

## Key Context

- **Input:** Google Takeout export folder (user downloads from takeout.google.com)
- **Target:** macOS Photos.app with iCloud sync enabled
- **Tool location:** `python/my_tools/` — unified CLI package (replaces standalone scripts)
- **CLI:** `my-tools <group> <command>` — Typer multi-group app
- **Groups:** `photos` (migration), `media` (kindle), `qr` (url to qr)
- **Matching strategy:** Compound key — timestamp ±60s + dimensions + filename stem (NOT hash)
- **Metadata:** exiftool embeds date + GPS from Google JSON sidecars before import
- **Safety:** Never deletes anything; imports require explicit `--confirm`
- **DB:** `~/.photo-migrate/photos.db` — persists across sessions
- **Venv:** `python/venv/` — Python 3.13 at `/opt/homebrew/bin/python3.13`
- **Entry point:** `python/venv/bin/my-tools` or `pip install -e .` from my-tools/

## Decisions Log

| Date | Decision | Reason |
|------|----------|--------|
| 2026-03-28 | Google Takeout (not API) | photoslibrary.readonly scope removed April 2025 |
| 2026-03-28 | Compound key matching | Apple fingerprint proprietary; HEIC vs JPEG cross-format |
| 2026-03-28 | Python 3.13 new venv | osxphotos requires 3.10+; existing my-tools venv is 3.9 |
| 2026-03-28 | exiftool for metadata | Most reliable EXIF writer; required for GPS from Google sidecars |
| 2026-03-28 | Unified my-tools CLI | All personal tools in one place; Typer groups; easy to extend |
| 2026-03-29 | rich>=13.5.2,<14.0.0 | osxphotos 0.75.6 requires rich<14.0.0; plan specified 14.3.3 which conflicts |
| 2026-03-29 | setuptools.build_meta build backend | Plan specified setuptools.backends.legacy:build which does not support editable installs |
| 2026-03-29 | Resolve my-tools binary via sys.executable parent | Subprocess cannot find 'my-tools' by name in tests unless PATH is set; venv path is reliable |

## Performance Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01 | 1.1 | 4 min | 2 | 9 |

## Stopped At

Completed 01-1-PLAN.md (Plan 1.1 of Phase 1). Next: 01-2-PLAN.md.

---
*Last updated: 2026-03-29 — Plan 1.1 complete*
