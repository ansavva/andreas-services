# Phase 1: Foundation & Scanners - Research

**Researched:** 2026-03-28
**Domain:** Python CLI tool — Google Takeout scanner + osxphotos iCloud scanner + SQLite schema
**Confidence:** HIGH (osxphotos API, SQLite schema, Typer/Rich); MEDIUM (sidecar naming — Google changes this without notice)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

All implementation details are Claude's discretion. The following decisions were pre-agreed:

- **Database location:** `~/.photo-migrate/photos.db`
- **Scan output:** Rich progress bar during scan; summary table at end; `--quiet` suppresses progress, prints only summary
- **Missing sidecar handling:** Index with filename-derived date (file mtime fallback), mark `sidecar_found = false`, warn once at end — never skip
- **iCloud library path:** Auto-detect `~/Pictures/Photos Library.photoslibrary`; `--library <path>` flag for non-standard
- **Tool structure:** `python/photo-tools/` directory; entry point `photo_migrate.py`; separate venv; modules `cache.py`, `takeout_scanner.py`, `icloud_scanner.py`
- **CLI:** Typer + Rich; commands `scan-takeout <path>`, `scan-icloud [--library <path>]`

### Claude's Discretion

All implementation details not listed above.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETUP-01 | Tool runs with Python 3.10+ in a dedicated venv | Python 3.13 available at `/opt/homebrew/bin/python3.13`; osxphotos 0.75.6 explicitly supports 3.10–3.14 |
| SETUP-02 | Tool provides step-by-step instructions for requesting Google Takeout export | Takeout URL and folder structure documented; instructions can be printed by a `--help` or startup message |
| SETUP-03 | Tool validates Takeout folder structural completeness | Takeout structure: `Takeout/Google Photos/` with year and album subdirs; validation checks for this root path |
| TAKE-01 | `scan-takeout <path>` command indexes all photos/videos | Typer command with Path argument; `os.walk` directory traversal |
| TAKE-02 | Stores filename, path, creation timestamp, width, height, file size, SHA-256 | Sidecar JSON `photoTakenTime.timestamp`; dimensions from sidecar `width`/`height`; SHA-256 via `hashlib` |
| TAKE-03 | Parses `.supplemental-metadata.json` (and legacy `.json`) sidecars | Five-stage matching algorithm documented; handles standard, truncated, counter-shift naming |
| TAKE-04 | Handles Live Photo pairs (HEIC+MOV same timestamp) without double-counting | Detect by filename stem match in same directory; store `live_photo_partner_path` in DB |
| TAKE-05 | Re-runs are incremental — skips already-indexed files using SQLite cache | Check `google_photos` table for `file_path` before hashing; skip if `sha256` already present |
| ICLOUD-01 | `scan-icloud` command scans Photos.app library via osxphotos | `osxphotos.PhotosDB(dbfile=...)` then `.photos()` |
| ICLOUD-02 | Stores filename, creation date, width, height, file size, cloud GUID, fingerprint | All available from `PhotoInfo` attributes without downloading originals |
| ICLOUD-03 | Handles Optimize Mac Storage — reads metadata for cloud-only photos | `PhotoInfo.fingerprint` and metadata are always available regardless of `ismissing` status |
| ICLOUD-04 | Re-runs incremental — only re-scans photos added/modified since last scan | `photosdb.query(QueryOptions(added_after=last_scan_dt))` for new photos; UUID-based upsert for changes |
| SAFE-01 | No write operations to iCloud Photos library except via explicit import command | Phase 1 is read-only; no photoscript calls; no `export` calls |
| SAFE-03 | SQLite database never wiped without explicit `--reset` flag | `cache.py` uses `CREATE TABLE IF NOT EXISTS`; only wipes on `--reset` |
</phase_requirements>

---

## Summary

Phase 1 builds the foundation for the entire migration pipeline: a Python 3.13 environment, SQLite schema, and two scanners. The iCloud scanner uses osxphotos to read the Photos.app SQLite database directly — this gives access to metadata (date, dimensions, fingerprint, cloud_guid) even for cloud-only photos where the local file is absent. The Takeout scanner walks a Google Takeout export directory, pairs each media file with its JSON sidecar (handling three naming patterns plus the newer `.supplemental-metadata.json` format), extracts `photoTakenTime.timestamp` as the authoritative creation date, and computes SHA-256 of the file content.

The primary new discovery since prior research: Python 3.12 is specified in the roadmap, but the Homebrew-installed Python on this machine is 3.13 (at `/opt/homebrew/bin/python3.13`). osxphotos 0.75.6 explicitly supports Python 3.13. The venv should be created with 3.13 rather than trying to install 3.12 separately.

The secondary new discovery: Google silently changed the sidecar naming convention in late 2024 from `photo.jpg.json` to `photo.jpg.supplemental-metadata.json`. The `.supplemental-metadata` portion is then truncated at a 51-character total limit. A Takeout export today may contain old format, new format, or both. All five matching stages must be implemented.

**Critical API correction:** `osxphotos.PhotosDB(library_path=path)` is WRONG. The `library_path` parameter is only for the edge case where the database file has been copied to a different location than the library. For standard usage, pass the library path as `dbfile=path` (or positionally). This was verified against osxphotos source code.

**Primary recommendation:** Use `python3.13 -m venv venv` under `python/photo-tools/`; use `osxphotos.PhotosDB(dbfile=library_path)` for the iCloud scanner; implement the five-stage sidecar matching algorithm; use `photosdb.query(QueryOptions(added_after=...))` for incremental iCloud scanning.

---

## Project Constraints (from CLAUDE.md)

- AWS: Never hardcode access keys — use IAM roles or `aws configure` credentials (not relevant to this tool, but global constraint)
- No project-specific Python version constraint in CLAUDE.md; the my-tools CLAUDE.md specifies Python 3.9 venv for the existing scripts, but explicitly says photo-tools needs a separate venv

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.13 (Homebrew) | Runtime | Already installed at `/opt/homebrew/bin/python3.13`; osxphotos 0.75.6 explicitly supports 3.10–3.14; no need to install 3.12 separately |
| osxphotos | 0.75.6 | Read Photos.app library metadata | Only mature Python library for direct Photos.app DB access; exposes fingerprint, cloud_guid, date_added without downloading originals |
| typer | 0.24.1 | CLI framework | Type-hint driven; `add_typer()` pattern composes subcommands cleanly; active 2025 release |
| rich | 14.3.3 | Terminal output, progress bars | First-class Typer integration; `track()` wraps iterables; `Table` for summary output |
| sqlite3 | stdlib | SQLite database | Zero dependencies; sufficient for single-user schema |
| hashlib | stdlib | SHA-256 hashing | Zero dependencies; deterministic file fingerprinting |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| photoscript | 0.5.3 | Import into Photos.app | Phase 3 only — do NOT install or use in Phase 1 |
| pathlib | stdlib | Path manipulation | Prefer over `os.path` for clean path handling |
| datetime | stdlib | Timezone-aware datetime | Used for `date_added` comparisons in incremental scan |
| pytest | latest | Unit tests | Install as dev dependency; test framework for all scanners |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python 3.13 (installed) | Python 3.12 (requires brew install) | 3.12 is the roadmap spec but 3.13 is already present and fully supported; using 3.13 saves an install step |
| stdlib sqlite3 | SQLAlchemy | SQLAlchemy adds ORM overhead with no benefit for this flat schema |

**Installation:**
```bash
# Python 3.13 is already at /opt/homebrew/bin/python3.13
# No brew install needed

mkdir -p /Users/andreassavva/Repos/andreas-services/my-tools/python/photo-tools
cd /Users/andreassavva/Repos/andreas-services/my-tools/python/photo-tools
/opt/homebrew/bin/python3.13 -m venv venv
source venv/bin/activate
pip install osxphotos==0.75.6 typer==0.24.1 rich==14.3.3 pytest
```

**Note:** photoscript is NOT installed in Phase 1. It is Phase 3 only.

**Version verification (confirmed 2026-03-28 via PyPI API):**
- osxphotos 0.75.6 — latest on PyPI, requires_python>=3.10, classifiers include 3.13
- typer 0.24.1 — latest on PyPI
- rich 14.3.3 — latest on PyPI

---

## Architecture Patterns

### Recommended Project Structure
```
python/photo-tools/
├── venv/                          # Python 3.13 venv (gitignored)
├── requirements.txt               # osxphotos, typer, rich (pinned versions)
├── photo_migrate.py               # Entry point: app = typer.Typer(); imports sub-apps
├── cache.py                       # SQLite connection, schema init, upsert helpers
├── takeout_scanner.py             # scan-takeout command + all sidecar logic
├── icloud_scanner.py              # scan-icloud command + osxphotos iteration
└── tests/
    ├── __init__.py
    ├── conftest.py                # shared tmp_path fixtures, mock PhotoInfo factory
    ├── test_cache.py              # SETUP-03, SAFE-03
    ├── test_takeout_scanner.py    # TAKE-02, TAKE-03, TAKE-04, TAKE-05
    └── test_icloud_scanner.py    # ICLOUD-02, ICLOUD-03, ICLOUD-04 (mocked)
```

### Pattern 1: Typer Multi-Command App

**What:** Each scanner module defines its own `typer.Typer()` app; the entry point composes them with `add_typer()`.

**When to use:** Any CLI with multiple independent subcommands that need separate modules.

```python
# photo_migrate.py
# Source: https://typer.tiangolo.com/tutorial/subcommands/add-typer/
import typer
import takeout_scanner
import icloud_scanner

app = typer.Typer(help="Google Photos -> iCloud migration tool")
app.add_typer(takeout_scanner.app, name="scan-takeout")
app.add_typer(icloud_scanner.app, name="scan-icloud")

# Stub commands for Phase 2/3 subcommands (so --help shows them)
@app.command()
def compare():
    """[Phase 2] Compare Takeout against iCloud to find missing photos."""
    typer.echo("Not yet implemented. Run after Phase 2.")

@app.command()
def report():
    """[Phase 2] Display report of missing photos."""
    typer.echo("Not yet implemented. Run after Phase 2.")

@app.command()
def import_missing():
    """[Phase 3] Download and import missing photos into Photos.app."""
    typer.echo("Not yet implemented. Run after Phase 3.")

if __name__ == "__main__":
    app()
```

**Note on add_typer naming:** When `add_typer(sub_app, name="scan-takeout")` is used and the sub-app has exactly one command, invoking `photo_migrate.py scan-takeout <path>` routes directly to that command. Typer uses the `name` parameter as the top-level token.

### Pattern 2: Rich Progress Bar for Unknown-Length Iterations

**What:** `rich.progress.track()` wraps the file list iterator; `Console().print(table)` renders the summary.

```python
# takeout_scanner.py (excerpt)
# Source: https://rich.readthedocs.io/en/latest/progress.html
from rich.progress import track
from rich.console import Console
from rich.table import Table

console = Console()

def scan(path: str, quiet: bool = False):
    media_files = list_media_files(path)  # collect first, then iterate with count

    iterable = track(media_files, description="Scanning Takeout...") if not quiet else media_files

    stats = {"indexed": 0, "skipped": 0, "errors": 0, "no_sidecar": 0}
    for media_path in iterable:
        # process each file ...
        pass

    if not quiet:
        table = Table(title="Scan Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("Indexed", str(stats["indexed"]))
        table.add_row("Skipped (already cached)", str(stats["skipped"]))
        table.add_row("Errors", str(stats["errors"]), style="red" if stats["errors"] else "")
        table.add_row("No sidecar (date approximate)", str(stats["no_sidecar"]))
        console.print(table)

    if stats["no_sidecar"] > 0:
        console.print(f"[yellow]Warning: {stats['no_sidecar']} photos had no sidecar — dates may be approximate[/yellow]")
```

### Pattern 3: osxphotos Incremental Scan

**What:** On first run, scan all photos. On re-runs, query only photos added since last scan datetime stored in `scan_state` table.

**CRITICAL API DETAIL:** Pass library path using `dbfile=`, NOT `library_path=`. The `library_path` parameter is only for the edge case where a database file has been manually copied to a different location than its library. Verified against osxphotos source at `photosdb/photosdb.py`.

```python
# icloud_scanner.py (excerpt)
# Source: https://rhettbull.github.io/osxphotos/API_README.html
import os
import osxphotos
from osxphotos import QueryOptions
from datetime import datetime, timezone
from rich.progress import track
import cache

def scan_icloud(library_path: str | None = None, quiet: bool = False):
    db_path = library_path or os.path.expanduser("~/Pictures/Photos Library.photoslibrary")
    if not os.path.exists(db_path):
        # Attempt auto-discovery before failing
        libraries = osxphotos.list_photo_libraries()
        if len(libraries) == 1:
            db_path = libraries[0]
        elif len(libraries) > 1:
            raise ValueError(
                f"Multiple Photos libraries found. Use --library <path> to specify one:\n"
                + "\n".join(f"  {lib}" for lib in libraries)
            )
        else:
            raise FileNotFoundError(
                f"Photos library not found at {db_path}. "
                "Use --library <path> to specify a custom location."
            )

    # dbfile= is the correct parameter for the library path
    # library_path= is a different parameter for edge cases only
    photosdb = osxphotos.PhotosDB(dbfile=db_path)  # expensive — do once

    conn = cache.get_connection()
    last_scan = cache.get_scan_state(conn, "icloud_last_scan_at")  # None on first run

    if last_scan:
        last_dt = datetime.fromisoformat(last_scan).replace(tzinfo=timezone.utc)
        photos = photosdb.query(QueryOptions(added_after=last_dt))
    else:
        photos = photosdb.photos()  # full scan on first run

    scan_started_at = datetime.now(tz=timezone.utc).isoformat()

    for photo in (track(photos, description="Scanning iCloud...") if not quiet else photos):
        cache.upsert_icloud_photo(conn, {
            "uuid":              photo.uuid,
            "filename":          photo.filename,
            "original_filename": photo.original_filename,
            "date":              photo.date.isoformat(),
            "date_added":        photo.date_added.isoformat() if photo.date_added else None,
            "width":             photo.width,
            "height":            photo.height,
            "original_filesize": photo.original_filesize,
            "fingerprint":       photo.fingerprint,
            "cloud_guid":        photo.cloud_guid,
            "hexdigest":         photo.hexdigest,   # None for cloud-only photos
            "iscloudasset":      int(photo.iscloudasset),
            "ismissing":         int(photo.ismissing),
        })

    cache.set_scan_state(conn, "icloud_last_scan_at", scan_started_at)
    conn.commit()
    conn.close()
```

**Critical note:** `QueryOptions(added_after=...)` filters by `date_added` (when the photo was added to the library), not when it was modified. This is the right field for "find new photos since last run." There is no `modified_after` field in QueryOptions — to re-index metadata edits, do a full scan or use UUID-based upsert to overwrite existing records.

### Pattern 4: Five-Stage Sidecar Matching

**What:** Given a media file path, find its JSON sidecar through a cascade of candidate filenames.

**When to use:** For every media file discovered in a Takeout export.

```python
# takeout_scanner.py (sidecar matching)
# Based on: https://github.com/DanielBatesUK/google-photos-takeout-metadata-fixer
import os
import re

MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tiff", ".tif",
    ".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv", ".dng", ".cr2",
    ".nef", ".arw", ".raw",
}

def find_sidecar(media_path: str) -> str | None:
    """
    Return path to JSON sidecar for media_path, or None if not found.
    Handles all Google Takeout naming patterns:
      Stage 1: Strip -edited suffix (for edited photos)
      Stage 2: Standard new:   photo.jpg.supplemental-metadata.json  (Oct 2024+)
               Standard old:   photo.jpg.json                         (pre Oct 2024)
      Stage 3: Truncated new:  photo_long.jpg.supplemental-metad.json (total <= 51 chars)
      Stage 4: Counter-shift:  image is foo(1).jpg, sidecar is foo.jpg(1).json
      Stage 5: Brute-force prefix scan of directory
    """
    directory = os.path.dirname(media_path)
    filename = os.path.basename(media_path)

    # Stage 1: strip -edited suffix for edited photos
    base_for_sidecar = re.sub(r'-edited(\.[^.]+)$', r'\1', filename)

    # Stage 2: standard candidates (new format first, then legacy)
    candidates = [
        base_for_sidecar + ".supplemental-metadata.json",
        base_for_sidecar + ".json",
    ]

    for candidate in candidates:
        full_path = os.path.join(directory, candidate)
        if os.path.exists(full_path):
            return full_path

    # Stage 3: truncated new format
    # Google truncates: total sidecar filename length <= 51 chars
    # Source: DanielBatesUK implementation uses 51 as the limit
    max_sidecar_len = 51
    suffix = ".supplemental-metadata.json"
    full_sidecar = base_for_sidecar + suffix
    if len(full_sidecar) > max_sidecar_len:
        base_plus_json = base_for_sidecar + ".json"
        chars_available = max_sidecar_len - len(base_plus_json)
        if chars_available > 0:
            truncated_suffix = ".supplemental-metadata"[:chars_available]
            truncated_candidate = base_for_sidecar + truncated_suffix + ".json"
            full_path = os.path.join(directory, truncated_candidate)
            if os.path.exists(full_path):
                return full_path

    # Stage 4: counter-shift pattern — image is foo(1).jpg, sidecar is foo.jpg(1).json
    counter_match = re.match(r'^(.*?)(\(\d+\))(\.[^.]+)$', filename)
    if counter_match:
        base_name, counter, ext = counter_match.groups()
        shift_candidates = [
            base_name + ext + counter + ".supplemental-metadata.json",
            base_name + ext + counter + ".json",
            base_name + ext + ".supplemental-metadata" + counter + ".json",
        ]
        for candidate in shift_candidates:
            full_path = os.path.join(directory, candidate)
            if os.path.exists(full_path):
                return full_path

    # Stage 5: brute-force prefix scan of directory
    prefix = base_for_sidecar[:46]
    try:
        for entry in os.scandir(directory):
            if entry.name.endswith(".json") and entry.name.startswith(prefix):
                return entry.path
    except PermissionError:
        pass

    return None  # No sidecar found — caller marks sidecar_found = False
```

### Pattern 5: Takeout JSON Field Extraction

**What:** The authoritative fields in a Google Takeout JSON sidecar (content is identical between old and new filename format).

```python
# Standard sidecar JSON structure:
# {
#     "title": "IMG_1234.jpg",
#     "photoTakenTime": {
#         "timestamp": "1609459200",   # Unix epoch seconds — AUTHORITATIVE capture time
#         "formatted": "Jan 1, 2021, 12:00:00 AM UTC"
#     },
#     "creationTime": {
#         "timestamp": "1609459200",   # When added to Google Photos — do NOT use for capture date
#         ...
#     },
#     "geoData": {
#         "latitude": 37.7749,
#         "longitude": -122.4194,
#         ...
#     },
#     "width": "4032",    # NOTE: string, not integer
#     "height": "3024",   # NOTE: string, not integer
# }

import json
from datetime import datetime, timezone

def parse_sidecar(sidecar_path: str) -> dict:
    with open(sidecar_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    taken_ts = data.get("photoTakenTime", {}).get("timestamp")
    creation_dt = (
        datetime.fromtimestamp(int(taken_ts), tz=timezone.utc)
        if taken_ts else None
    )

    return {
        "creation_time": creation_dt.isoformat() if creation_dt else None,
        "width":  int(data.get("width", 0)) or None,   # cast string to int; 0->None
        "height": int(data.get("height", 0)) or None,
        "latitude":  data.get("geoData", {}).get("latitude"),
        "longitude": data.get("geoData", {}).get("longitude"),
    }
```

### Pattern 6: Live Photo Pair Detection

**What:** A Live Photo in Takeout is a HEIC (or JPG) + a MOV file with the same stem in the same directory.

```python
def detect_live_photo_pairs(directory: str) -> dict[str, str]:
    """
    Returns a dict mapping MOV path -> paired image path for Live Photo pairs.
    A pair is: same filename stem, one is MOV, other is an image format.
    Duration check (< 4 sec) is expensive and unnecessary for the scanner.
    """
    by_stem: dict[str, list[str]] = {}
    for entry in os.scandir(directory):
        if not entry.is_file():
            continue
        stem, ext = os.path.splitext(entry.name)
        ext = ext.lower()
        by_stem.setdefault(stem, []).append(ext)

    pairs = {}
    image_exts = {".heic", ".heif", ".jpg", ".jpeg"}
    for stem, exts in by_stem.items():
        if ".mov" in exts and any(e in image_exts for e in exts):
            mov_path = os.path.join(directory, stem + ".mov")
            # Find the image partner (prefer HEIC over JPG)
            for image_ext in [".heic", ".heif", ".jpg", ".jpeg"]:
                if image_ext in exts:
                    image_path = os.path.join(directory, stem + image_ext)
                    pairs[mov_path] = image_path
                    break

    return pairs
```

**Storage:** When indexing a MOV that is part of a Live Photo pair, store `live_photo_partner_path` in the `google_photos` table and set `is_live_photo_video = 1`. The comparison phase uses this to avoid importing the MOV as a standalone video.

### Pattern 7: Takeout Folder Validation (SETUP-03)

```python
from pathlib import Path

def validate_takeout_folder(path: str) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Checks that path contains the expected Google Takeout structure.
    """
    p = Path(path)

    if not p.is_dir():
        return False, f"Path does not exist or is not a directory: {path}"

    # Check for Takeout/Google Photos/ structure
    google_photos = p / "Takeout" / "Google Photos"
    if not google_photos.is_dir():
        # Accept if user passed the inner Google Photos dir directly
        inner = p / "Google Photos"
        if inner.is_dir():
            return True, ""
        return False, (
            f"Expected 'Takeout/Google Photos/' subdirectory not found in {path}.\n"
            "Make sure you've extracted the Takeout ZIP and are pointing to the "
            "folder containing the 'Takeout' directory."
        )

    subdirs = list(google_photos.iterdir())
    if not subdirs:
        return False, "Google Photos folder is empty — export may be incomplete."

    return True, ""
```

### Anti-Patterns to Avoid

- **Using `library_path=` for the normal Photos library path:** The correct parameter is `dbfile=path`. `library_path=` is only for the edge case of a copied database. Verified against osxphotos source.
- **Re-creating PhotosDB per photo:** `osxphotos.PhotosDB()` parses the entire Photos SQLite DB on construction. Create one instance at the start of `scan_icloud()`, never inside a loop.
- **Using `photo.path` for cloud-only photos:** For `ismissing=True` photos, `photo.path` returns a thumbnail proxy path, not the original. Phase 1 does not need the file path — only metadata.
- **Hashing iCloud files via `photo.path`:** Phase 1 stores `fingerprint` and metadata only; no SHA-256 of iCloud files is needed or attempted.
- **Using `hexdigest` as a cross-platform hash:** osxphotos `hexdigest` is a hash of the photo's metadata properties, not a SHA-256 of file content. Store it for metadata-change detection within Photos, never for cross-platform comparison.
- **Checking only the old `.json` sidecar format:** Any implementation that only looks for `filename.json` will miss the new `filename.supplemental-metadata.json` format used in all Takeout exports from Oct 2024 onward.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Photos library DB access | Custom SQLite reader for Photos.app DB | `osxphotos.PhotosDB()` | Photos DB schema changes with every macOS update; osxphotos tracks schema changes across versions |
| Terminal progress display | Custom ANSI progress bar | `rich.progress.track()` | edge cases: TTY detection, Windows compat, elapsed/ETA formatting |
| Terminal table output | Custom column formatter | `rich.table.Table` | Column width calculation, wrapping, color coding |
| SHA-256 file hashing | Custom hash implementation | `hashlib.sha256()` stdlib | Obvious — stdlib is correct and fast |
| CLI argument parsing | `argparse` or `sys.argv` | `typer` | Type hints + auto-generated help text + shell completion |
| Photos library discovery | Custom `mdfind` subprocess | `osxphotos.list_photo_libraries()` | Combines glob + Spotlight; handles deduplication; returns empty list on non-macOS |

---

## Runtime State Inventory

This is a greenfield phase (no existing tool). No runtime state to inventory.

None — verified: `python/photo-tools/` does not exist, no existing SQLite database at `~/.photo-migrate/photos.db`, no existing venv for this tool.

---

## Common Pitfalls

### Pitfall 1: Wrong PhotosDB Parameter Name

**What goes wrong:** Using `osxphotos.PhotosDB(library_path=db_path)` silently fails or opens the wrong database. The `library_path` parameter is for a different edge case: when you have manually copied a `Photos.sqlite` file to a separate location.

**Why it happens:** The parameter name `library_path` sounds like it should take the library path, but it does not — it is a secondary parameter used only alongside `dbfile=` when the db and library are in different locations.

**How to avoid:** Always use `osxphotos.PhotosDB(dbfile=db_path)` or `osxphotos.PhotosDB(db_path)` (positional). The `library_path` parameter should almost never appear in application code.

**Verified by:** osxphotos source `photosdb/photosdb.py` docstring: "In some cases, it may be useful to copy the database to a different location than the library... In that case, set dbfile to the path to the database and set library_path to the path to the library root. In most cases you should not provide the library_path argument."

### Pitfall 2: Python Version — 3.12 vs 3.13

**What goes wrong:** The roadmap specifies Python 3.12. Attempting to use `brew install python@3.12` on a machine that already has Python 3.13 at `/opt/homebrew/bin/python3.13` adds an unnecessary installation step.

**Why it matters:** osxphotos 0.75.6 explicitly supports Python 3.13 (confirmed via PyPI classifiers). Using 3.13 eliminates a brew install with no downside.

**How to avoid:** Use `/opt/homebrew/bin/python3.13 -m venv venv` instead of installing 3.12.

### Pitfall 3: Google Takeout Sidecar Format Changed in Late 2024

**What goes wrong:** Code that only looks for `photo.jpg.json` (the pre-October 2024 format) will fail to find sidecars in any Takeout export from late 2024 or 2025.

**Why it happens:** Google silently renamed sidecars from `photo.jpg.json` to `photo.jpg.supplemental-metadata.json`. The `.supplemental-metadata` portion is then truncated when the total sidecar filename exceeds 51 characters.

**How to avoid:** Implement all five stages of the sidecar matching algorithm. Always check for both `.supplemental-metadata.json` and `.json` forms.

**Warning signs:** Photos are indexed with `sidecar_found = false` at a high rate (>10%) on a fresh Takeout export.

### Pitfall 4: `hexdigest` Is NOT a File Content Hash

**What goes wrong:** osxphotos `PhotoInfo.hexdigest` looks like a SHA-256 but it is a hash of the photo's metadata properties (combination of date, filename, UUID, etc.). Using it as a file content hash produces wrong results.

**How to avoid:** Store `hexdigest` in the `icloud_photos` table (useful for detecting metadata changes on re-scans), but never use it as a cross-platform comparison key against Takeout SHA-256 values.

**Confirmed by:** osxphotos API docs: "Returns a unique digest of the photo's properties and metadata; useful for detecting changes in any property/metadata of the photo."

### Pitfall 5: Width/Height from Sidecar Are Strings, Not Integers

**What goes wrong:** Google Takeout JSON sidecar `"width"` and `"height"` fields are strings (e.g., `"4032"`) not integers. Storing them directly causes type errors in SQL comparisons.

**How to avoid:** Always cast with `int(data.get("width", 0)) or None` — the `or None` converts `0` (field absent or zero) to NULL in SQLite.

### Pitfall 6: `date_added` Timezone Awareness for `QueryOptions`

**What goes wrong:** `QueryOptions(added_after=datetime(2025, 1, 1))` with a naive datetime raises `TypeError: can't compare offset-naive and offset-aware datetimes`.

**How to avoid:** Always pass timezone-aware datetimes:
```python
from datetime import datetime, timezone
last_scan_dt = datetime.fromisoformat(stored_iso_string).replace(tzinfo=timezone.utc)
options = QueryOptions(added_after=last_scan_dt)
```
Store scan timestamps as `datetime.now(tz=timezone.utc).isoformat()`.

### Pitfall 7: Takeout Exports May Span Multiple ZIP Files

**What goes wrong:** Google splits large Takeout exports across multiple ZIPs. If the user provides only one extracted ZIP folder, the scanner will miss photos from the other ZIPs.

**How to avoid:** In SETUP-03 validation, check for `Takeout/Google Photos/` root. Warn: "If your export had multiple ZIP files, ensure all are extracted into the same parent directory."

### Pitfall 8: Photos Library May Have a Non-Standard Name

**What goes wrong:** The auto-detect path `~/Pictures/Photos Library.photoslibrary` fails if the user renamed their library.

**How to avoid:** Use `osxphotos.list_photo_libraries()` to discover all libraries if the default path is absent. Auto-select if exactly one is found; prompt user with `--library` flag if multiple found.

### Pitfall 9: Duplicate Photo Paths Across Year and Album Folders

**What goes wrong:** Google Takeout includes the same photo in both `Photos from YYYY/` and any album folder it belongs to. Two rows are created for the same logical photo.

**How to avoid:** Index all paths (one row per `file_path`, deduped by UNIQUE constraint). The Phase 2 comparison uses `creation_time + width + height` as the match key, which naturally treats both paths as the same photo. Log duplicate count at end of scan.

---

## SQLite Schema

The schema below is definitive for Phase 1 and must not be changed without updating the comparison query in Phase 2.

```sql
-- google_photos: all media items from Google Takeout export
CREATE TABLE IF NOT EXISTS google_photos (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path               TEXT NOT NULL UNIQUE,   -- absolute path in Takeout export
    filename                TEXT NOT NULL,
    creation_time           TEXT,                   -- ISO 8601 UTC from photoTakenTime.timestamp
    width                   INTEGER,                -- from sidecar JSON (NULL if absent)
    height                  INTEGER,                -- from sidecar JSON (NULL if absent)
    file_size               INTEGER,                -- bytes, from os.path.getsize()
    sha256                  TEXT,                   -- hex SHA-256 of file content
    sidecar_found           INTEGER NOT NULL DEFAULT 1,   -- 0 if no sidecar
    media_type              TEXT NOT NULL DEFAULT 'photo', -- 'photo' or 'video'
    is_live_photo_video     INTEGER NOT NULL DEFAULT 0,    -- 1 if MOV partner of a Live Photo
    live_photo_partner_path TEXT,                          -- path to paired HEIC/JPG (if applicable)
    scanned_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_google_creation_time ON google_photos(creation_time);
CREATE INDEX IF NOT EXISTS idx_google_sha256 ON google_photos(sha256);
CREATE INDEX IF NOT EXISTS idx_google_filename ON google_photos(filename);

-- icloud_photos: all photos from Photos.app library via osxphotos
CREATE TABLE IF NOT EXISTS icloud_photos (
    uuid                TEXT PRIMARY KEY,           -- Photos.app UUID (stable per library)
    filename            TEXT NOT NULL,
    original_filename   TEXT,
    date                TEXT NOT NULL,              -- ISO 8601 (timezone-aware from osxphotos)
    date_added          TEXT,                       -- ISO 8601, when added to library
    width               INTEGER,
    height              INTEGER,
    original_filesize   INTEGER,                    -- bytes (PhotoInfo.original_filesize)
    fingerprint         TEXT,                       -- Apple's opaque hash (NOT SHA-256; NOT for cross-platform comparison)
    cloud_guid          TEXT,                       -- iCloud GUID (PhotoInfo.cloud_guid)
    hexdigest           TEXT,                       -- osxphotos metadata hash (NOT file content SHA-256)
    iscloudasset        INTEGER NOT NULL DEFAULT 0, -- 1 if iCloud-managed
    ismissing           INTEGER NOT NULL DEFAULT 0, -- 1 if original not downloaded locally
    scanned_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_icloud_date ON icloud_photos(date);
CREATE INDEX IF NOT EXISTS idx_icloud_fingerprint ON icloud_photos(fingerprint);
CREATE INDEX IF NOT EXISTS idx_icloud_cloud_guid ON icloud_photos(cloud_guid);
CREATE INDEX IF NOT EXISTS idx_icloud_filename_date ON icloud_photos(filename, date);
CREATE INDEX IF NOT EXISTS idx_icloud_dimensions ON icloud_photos(width, height);

-- missing_photos: populated by Phase 2 comparator; empty in Phase 1
CREATE TABLE IF NOT EXISTS missing_photos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id           INTEGER NOT NULL REFERENCES google_photos(id),
    filename            TEXT NOT NULL,
    creation_time       TEXT NOT NULL,
    match_tier          TEXT,                       -- 'none' | 'tier1' | 'tier2' (set by Phase 2)
    status              TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'imported' | 'failed'
    failure_reason      TEXT,
    identified_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- import_log: audit trail for Phase 3 imports; stub table created in Phase 1
CREATE TABLE IF NOT EXISTS import_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id           INTEGER NOT NULL REFERENCES google_photos(id),
    tmp_path            TEXT,
    status              TEXT NOT NULL,              -- 'success' | 'error'
    error_message       TEXT,
    imported_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- scan_state: key-value store for incremental scan state
CREATE TABLE IF NOT EXISTS scan_state (
    key                 TEXT PRIMARY KEY,
    value               TEXT,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Key: 'icloud_last_scan_at'  Value: ISO 8601 UTC timestamp of last iCloud scan start
-- Key: 'takeout_last_scan_at' Value: ISO 8601 UTC timestamp of last Takeout scan start
```

**Index rationale for Phase 2 comparison query:**
- `idx_icloud_filename_date` — used by the Tier 1/Tier 2 compound key join
- `idx_icloud_dimensions` — used by width+height dimension matching
- `idx_google_creation_time` — used in the date window arithmetic
- `idx_google_sha256` — available for future exact-match fallback

---

## cache.py API Contract

The planner must implement exactly this interface. Scanners call these functions; they never write SQL directly.

```python
# cache.py
import sqlite3
import os
from pathlib import Path

DB_PATH = Path.home() / ".photo-migrate" / "photos.db"

def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database, creating parent dir if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safer for long writes
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if not present. Idempotent."""
    # Run the CREATE TABLE IF NOT EXISTS statements above

def upsert_google_photo(conn: sqlite3.Connection, data: dict) -> None:
    """Insert or replace a Google Takeout photo record.
    Key: file_path (UNIQUE constraint handles dedup)."""

def upsert_icloud_photo(conn: sqlite3.Connection, data: dict) -> None:
    """Insert or replace an iCloud photo record.
    Key: uuid (PRIMARY KEY handles dedup)."""

def is_takeout_file_indexed(conn: sqlite3.Connection, file_path: str) -> bool:
    """Return True if file_path already has a sha256 in google_photos."""

def get_scan_state(conn: sqlite3.Connection, key: str) -> str | None:
    """Retrieve a value from scan_state by key. Returns None if not set."""

def set_scan_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a key-value pair in scan_state."""

def reset_database(conn: sqlite3.Connection) -> None:
    """Drop and recreate all tables. Only called when --reset is passed."""
```

---

## Google Takeout Folder Structure

Confirmed structure for a standard export:

```
Takeout/
└── Google Photos/
    ├── Photos from 2018/
    │   ├── IMG_1234.jpg
    │   ├── IMG_1234.jpg.json                              # old format (pre Oct 2024)
    │   ├── IMG_1234.jpg.supplemental-metadata.json        # new format (Oct 2024+)
    │   ├── IMG_5678.HEIC
    │   ├── IMG_5678.HEIC.supplemental-metadata.json
    │   ├── VID_0001.MOV                                   # Live Photo video partner
    │   └── VID_0001.MOV.supplemental-metadata.json
    ├── Photos from 2019/
    │   └── ...
    ├── Vacation Album 2019/                               # custom album as directory
    │   ├── photo.jpg
    │   └── photo.jpg.supplemental-metadata.json
    └── Untitled(1)/
        └── ...
```

**Key observations:**
- The root of a Takeout ZIP is `Takeout/Google Photos/` — SETUP-03 validation must check for this path
- Year-based folders (`Photos from YYYY/`) and album folders are siblings under `Google Photos/`
- The same photo can appear in BOTH a year folder and an album folder — handled by `file_path` UNIQUE constraint
- A multi-ZIP export produces multiple `Takeout/` trees that must all be merged into one scan directory before running

---

## SETUP-02 Takeout Instructions

The `scan-takeout --help` or a dedicated `setup-instructions` command should print:

```
Google Takeout Export Instructions:
  1. Go to https://takeout.google.com
  2. Click "Deselect all", then scroll down and check only "Google Photos"
  3. Choose file type .zip, size 2GB (multiple files for large libraries)
  4. Click "Create export" -- Google will email you when ready (may take hours)
  5. Download ALL zip files (e.g., takeout-20240101-001.zip, takeout-20240101-002.zip, ...)
  6. Create a folder and extract ALL zips into it, so all "Takeout/" contents merge
  7. Run: python photo_migrate.py scan-takeout /path/to/that/folder
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.13 | All modules | YES | 3.13.11 (`/opt/homebrew/bin/python3.13`) | — |
| Python 3.12 | Roadmap spec | NO | — | Use 3.13 (osxphotos explicitly supports it) |
| Photos Library | iCloud scanner | YES | `~/Pictures/Photos Library.photoslibrary` | `--library <path>` flag |
| osxphotos 0.75.6 | iCloud scanner | NO (not yet installed) | — | pip install in new venv |
| typer 0.24.1 | CLI | NO (not yet installed) | — | pip install |
| rich 14.3.3 | CLI output | NO (not yet installed) | — | pip install |
| pytest | Test suite | NO (not yet installed) | — | pip install (dev dependency) |
| exiftool | NOT needed Phase 1 | — | — | Phase 3 only |
| photoscript | NOT needed Phase 1 | — | — | Phase 3 only |

**Missing dependencies with no fallback:** None blocking Phase 1. All will be installed via pip install in the new venv.

**Python version note:** Roadmap says 3.12 but 3.13 is installed. Plan must use `/opt/homebrew/bin/python3.13` for venv creation.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed; add to requirements.txt) |
| Config file | none — see Wave 0 |
| Quick run command | `pytest python/photo-tools/tests/ -x -q` |
| Full suite command | `pytest python/photo-tools/tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SETUP-01 | venv uses Python 3.10+ | smoke | `python --version` in venv | N/A (env check) |
| SETUP-03 | Validates Takeout folder structure | unit | `pytest tests/test_cache.py::test_validate_takeout_folder -x` | Wave 0 |
| TAKE-02 | Stores correct fields from sidecar | unit | `pytest tests/test_takeout_scanner.py::test_sidecar_extraction -x` | Wave 0 |
| TAKE-03 | Finds sidecar in all 5 naming patterns | unit | `pytest tests/test_takeout_scanner.py::test_find_sidecar_all_patterns -x` | Wave 0 |
| TAKE-04 | Detects Live Photo pairs | unit | `pytest tests/test_takeout_scanner.py::test_live_photo_pairs -x` | Wave 0 |
| TAKE-05 | Incremental scan skips already-indexed | unit | `pytest tests/test_takeout_scanner.py::test_incremental_skip -x` | Wave 0 |
| ICLOUD-02 | Stores correct iCloud photo fields | unit | `pytest tests/test_icloud_scanner.py::test_icloud_upsert -x` | Wave 0 |
| ICLOUD-03 | Handles cloud-only photos (ismissing=True) | unit (mock) | `pytest tests/test_icloud_scanner.py::test_cloud_only_photo -x` | Wave 0 |
| ICLOUD-04 | Incremental scan uses QueryOptions(added_after=) | unit (mock) | `pytest tests/test_icloud_scanner.py::test_incremental_scan -x` | Wave 0 |
| SAFE-03 | DB not wiped unless --reset passed | unit | `pytest tests/test_cache.py::test_reset_flag -x` | Wave 0 |

**Note:** ICLOUD-01 through ICLOUD-04 tests that require a real Photos library are integration-level and must be marked `@pytest.mark.integration` — skipped by default, run manually with `pytest -m integration`.

### Sampling Rate
- **Per task commit:** `pytest python/photo-tools/tests/ -x -q`
- **Per wave merge:** `pytest python/photo-tools/tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `python/photo-tools/tests/__init__.py` — empty
- [ ] `python/photo-tools/tests/test_cache.py` — covers SETUP-03, SAFE-03
- [ ] `python/photo-tools/tests/test_takeout_scanner.py` — covers TAKE-02, TAKE-03, TAKE-04, TAKE-05
- [ ] `python/photo-tools/tests/test_icloud_scanner.py` — covers ICLOUD-02, ICLOUD-03, ICLOUD-04 (mocked)
- [ ] `python/photo-tools/tests/conftest.py` — shared tmp_path fixtures, mock PhotoInfo factory
- [ ] Framework install: `pip install pytest` (added to requirements.txt)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sidecar: `photo.jpg.json` | Sidecar: `photo.jpg.supplemental-metadata.json` (with truncation) | Oct 2024 | Must check both formats |
| Google Photos API (photoslibrary.readonly) | Google Takeout files | Apr 2025 | No API auth needed; manual export step added |
| Python 3.9 (existing my-tools venv) | Python 3.13 (separate venv) | This project | osxphotos requires >=3.10; completely separate venv |

---

## Open Questions

1. **Duplicate photo paths across year/album folders**
   - What we know: Google Takeout includes the same photo in both `Photos from YYYY/` and its album folder
   - What's unclear: Should the scanner index only one instance, or both?
   - Recommendation: Index all paths (one row per path, file_path UNIQUE). Phase 2 comparison by `creation_time + width + height` naturally deduplicates. Log duplicate count at end of scan.

2. **osxphotos attribute availability across macOS versions**
   - What we know: osxphotos tracks schema changes across macOS versions; `fingerprint`, `cloud_guid`, `date_added` are documented in 0.75.6
   - What's unclear: Whether these attributes return None vs raise AttributeError on older macOS versions (Ventura vs Sonoma vs Sequoia)
   - Recommendation: Wrap attribute access in try/except AttributeError and store NULL. The phase is read-only so any AttributeError means a field is absent in this library version.

3. **Takeout export completeness validation (SETUP-03)**
   - What we know: Large exports span multiple ZIPs; no known manifest file in Takeout
   - What's unclear: Is there a photo count in the Takeout that can be verified?
   - Recommendation: Basic structural validation only (`Takeout/Google Photos/` root check). Print a warning advising users with large libraries to verify they extracted all ZIP files.

4. **Exact truncation limit: 46 vs 51 characters**
   - What we know: DanielBatesUK implementation uses 51; ente-io discussion mentions 46
   - What's unclear: Which is authoritative? Google has no public docs.
   - Recommendation: Use 51 (from code implementation); the Stage 5 brute-force scan catches anything that slips through.

---

## Sources

### Primary (HIGH confidence)
- osxphotos API_README.html (rhettbull.github.io) — PhotosDB constructor, photos(), query(), QueryOptions fields (added_after confirmed; no modified_after field), PhotoInfo attributes (fingerprint, cloud_guid, hexdigest, date_added, width, height, original_filesize, iscloudasset, ismissing), list_photo_libraries()
- osxphotos photosdb.py source (GitHub) — confirmed `dbfile=` is the correct parameter for library path; `library_path=` is a secondary edge-case parameter
- osxphotos PyPI page — version 0.75.6, requires_python>=3.10, Python 3.10–3.14 classifiers confirmed
- typer documentation (typer.tiangolo.com) — add_typer() pattern, name parameter behavior
- rich documentation — Table, Console, track() APIs
- PyPI API (pypi.org/pypi/{package}/json) — confirmed versions: osxphotos 0.75.6, typer 0.24.1, rich 14.3.3 as of 2026-03-28

### Secondary (MEDIUM confidence)
- DanielBatesUK/google-photos-takeout-metadata-fixer source — five-stage sidecar matching algorithm; 51-char truncation limit; counter-shift pattern
- GitHub issue TheLastGimbus/GooglePhotosTakeoutHelper — supplemental-metadata.json rollout, Oct 2024 timeline, confirmed both formats may appear in same export
- ente-io/ente issue — 46-char clipping limit mentioned; confirms new format details
- osxphotos utils.py source — list_photo_libraries() confirmed: glob + Spotlight + dedup

### Tertiary (LOW confidence — flag for validation)
- Truncation limit 51 vs 46 chars: DanielBatesUK code uses 51 (higher confidence), ente-io mentions 46 (lower confidence). Stage 5 brute-force is the fallback regardless.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified via PyPI API on 2026-03-28
- osxphotos API (PhotosDB, PhotoInfo, QueryOptions): HIGH — verified via source code and official API docs
- PhotosDB parameter name (`dbfile=`): HIGH — verified against photosdb.py source docstring
- Sidecar naming algorithm: MEDIUM — algorithm from open-source implementation confirmed by multiple community sources; exact truncation limit from code, not Google docs
- SQLite schema: HIGH — derived directly from requirements and verified attribute names
- Architecture patterns: HIGH — standard Typer/Rich patterns from official docs

**Research date:** 2026-03-28
**Valid until:** 2026-06-28 (stable domain; sidecar format changes sooner if Google modifies again)
