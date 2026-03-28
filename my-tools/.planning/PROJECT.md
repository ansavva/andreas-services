# Photo Library Migration Tool

## What This Is

A local Python CLI tool that compares a Google Photos library against an iCloud Photos library, identifies photos that exist in Google Photos but are missing from iPhotos, and downloads + imports those missing photos into iPhotos. The goal is to ensure zero photo loss during a migration from dual-storage (Google + iCloud) to iCloud-only.

## Core Value

Find every photo in Google Photos that isn't in iPhotos and import it — never lose a single photo.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Authenticate with Google Photos API using OAuth 2.0
- [ ] Scan all Google Photos and compute/store hashes in a local SQLite database
- [ ] Scan iCloud Photos library via osxphotos and store hashes in local SQLite database
- [ ] Identify photos present in Google Photos but missing from iPhotos (by hash)
- [ ] Generate a report of missing photos (count, dates, thumbnails)
- [ ] Download missing photos from Google Photos to a temp location (minimal disk usage)
- [ ] Auto-import missing photos into iPhotos via macOS Photos framework
- [ ] Re-runs are fast: skip already-hashed photos using SQLite cache
- [ ] Never delete anything from any library — read/import only

### Out of Scope

- Deleting photos from Google Photos — user wants zero deletions
- Deduplicating within iPhotos — not needed, only care about missing photos
- Going the other direction (iPhotos → Google Photos) — iCloud is the destination
- Cloud/AWS execution — local Mac only
- Mobile app or web UI — CLI tool only

## Context

- User has photos synced from their iPhone to both iCloud Photos and Google Photos (via iPhone Google Photos app)
- Most photos will already exist in both libraries due to this sync
- Some photos may exist only in Google Photos (e.g., uploaded from other devices, older uploads)
- Machine has limited local storage — tool must avoid downloading the full library
- Photos library is managed by macOS Photos app with iCloud sync enabled
- `osxphotos` Python library can read Photos library metadata (including fingerprints) without downloading full-res images
- Google Photos API (v1) provides photo metadata and download URLs; full download only needed for missing photos
- Hash storage in SQLite allows incremental re-runs without re-scanning everything

## Constraints

- **Platform**: macOS only — uses Photos.app integration and osxphotos
- **Storage**: Minimal disk usage — only download photos confirmed as missing, use temp files
- **Safety**: Read-only operations on both libraries during scan; import-only (no deletes ever)
- **Auth**: Google OAuth 2.0 required — user must authorize the app once
- **Python**: 3.9+ (matches existing my-tools venv)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hash-based deduplication (not filename/date) | Files can be renamed or have metadata drift across platforms; perceptual hash or SHA256 of content is reliable | — Pending |
| SQLite for local hash cache | Avoids re-downloading/re-scanning on subsequent runs; survives crashes | — Pending |
| osxphotos for iCloud Photos access | Direct library access without Photos.app UI; can read cloud-only stubs | — Pending |
| Download only missing photos | Protects limited local storage; avoids unnecessary bandwidth | — Pending |
| No deletions in v1 | Safety first — user wants certainty before any removals | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-28 after initialization*
