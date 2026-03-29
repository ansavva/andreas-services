---
plan: 1.3
phase: 1
wave: 2
depends_on:
  - "1.1"
  - "1.2"
files_modified:
  - python/my_tools/photos/icloud_scanner.py
  - python/my_tools/photos/commands.py
  - python/my_tools/tests/test_icloud_scanner.py
autonomous: true
requirements:
  - ICLOUD-01
  - ICLOUD-02
  - ICLOUD-03
  - ICLOUD-04
  - SETUP-02

must_haves:
  truths:
    - "`my-tools photos scan-icloud` reads the Photos.app library via osxphotos and writes rows to `icloud_photos` table with uuid, filename, original_filename, date, date_added, width, height, original_filesize, fingerprint, cloud_guid, hexdigest, iscloudasset, ismissing"
    - "Photos with `ismissing=True` (Optimize Mac Storage cloud-only) are indexed — `fingerprint` is non-null even when the local file is absent"
    - "Re-running `scan-icloud` on a library that has not changed shows 0 new photos (incremental via `QueryOptions(added_after=last_dt)`)"
    - "`my-tools photos setup` prints step-by-step Google Takeout export instructions and exits 0"
    - "Auto-detection: if `~/Pictures/Photos Library.photoslibrary` does not exist, `osxphotos.list_photo_libraries()` is called; single result is used automatically; multiple results print an error with `--library` guidance"
    - "osxphotos.PhotosDB is constructed with `dbfile=path`, never `library_path=path`"
    - "No write operations to Photos.app at any point during scan-icloud (SAFE-01)"
  artifacts:
    - path: "python/my_tools/photos/icloud_scanner.py"
      provides: "scan_icloud() function with osxphotos integration and incremental scanning"
      exports: ["scan_icloud"]
    - path: "python/my_tools/tests/test_icloud_scanner.py"
      provides: "Unit tests using a mock PhotoInfo factory to test all icloud_scanner logic without a real Photos library"
  key_links:
    - from: "python/my_tools/photos/commands.py (scan_icloud command)"
      to: "python/my_tools/photos/icloud_scanner.py"
      via: "from my_tools.photos.icloud_scanner import scan_icloud as run_scan"
    - from: "python/my_tools/photos/icloud_scanner.py"
      to: "python/my_tools/photos/cache.py"
      via: "from my_tools.photos.cache import get_connection, init_schema, upsert_icloud_photo, get_scan_state, set_scan_state"
    - from: "icloud_scanner.scan_icloud()"
      to: "osxphotos.PhotosDB"
      via: "osxphotos.PhotosDB(dbfile=library_path) — dbfile= parameter, never library_path="
---

<objective>
Implement the iCloud Photos library scanner and the `setup` command. After this plan, `my-tools photos scan-icloud` populates the `icloud_photos` table with full metadata for every photo including cloud-only stubs. Re-runs are incremental. `my-tools photos setup` prints Takeout export instructions.

Purpose: Ground truth for every photo in iCloud is stored locally in SQLite. The combination of Plans 1.2 and 1.3 enables Phase 2 comparison.

Output: icloud_scanner.py, updated commands.py (scan-icloud and setup wired), test suite with mocked PhotoInfo.
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
@.planning/phases/01-foundation-scanners/01-2-SUMMARY.md

<interfaces>
<!-- From Plan 1.1 — commands.py stubs that this plan replaces -->
From python/my_tools/photos/commands.py (Plan 1.1 stubs):
```python
@app.command("scan-icloud")
def scan_icloud(
    library: Optional[Path] = typer.Option(None, "--library", ...),
    quiet: bool = typer.Option(False, "--quiet", "-q", ...),
):
    """Scan Photos.app library and index all photos into SQLite."""
    typer.echo("[Plan 1.3] scan-icloud not yet implemented.")
    raise typer.Exit(code=1)

@app.command("setup")
def setup():
    """Print Google Takeout export instructions and check system requirements."""
    typer.echo("[Plan 1.3] setup not yet implemented.")
    raise typer.Exit(code=1)
```

<!-- From Plan 1.2 — cache.py functions available to the icloud scanner -->
From python/my_tools/photos/cache.py:
```python
def get_connection() -> sqlite3.Connection: ...
def init_schema(conn: sqlite3.Connection) -> None: ...
def upsert_icloud_photo(conn: sqlite3.Connection, data: dict) -> None: ...
def get_scan_state(conn: sqlite3.Connection, key: str) -> str | None: ...
def set_scan_state(conn: sqlite3.Connection, key: str, value: str) -> None: ...
```

<!-- osxphotos API used in this plan — from RESEARCH.md Pattern 3 -->
osxphotos API (critical details):
```python
# CORRECT: use dbfile= for the library path
photosdb = osxphotos.PhotosDB(dbfile=library_path)

# WRONG: do not use library_path= for the library path
# photosdb = osxphotos.PhotosDB(library_path=library_path)  # NEVER

# Incremental scan
photos = photosdb.query(QueryOptions(added_after=last_dt))  # last_dt must be timezone-aware

# Full scan (first run)
photos = photosdb.photos()

# PhotoInfo attributes used:
photo.uuid              # str — stable Photos.app identifier
photo.filename          # str
photo.original_filename # str
photo.date              # datetime (timezone-aware)
photo.date_added        # datetime | None
photo.width             # int
photo.height            # int
photo.original_filesize # int — bytes; available even for ismissing photos
photo.fingerprint       # str | None — Apple opaque hash; available for ismissing photos
photo.cloud_guid        # str | None
photo.hexdigest         # str | None — osxphotos metadata hash (NOT file content SHA-256)
photo.iscloudasset      # bool
photo.ismissing         # bool — True when local file not downloaded (Optimize Mac Storage)
```

<!-- Library discovery -->
```python
import osxphotos
libraries = osxphotos.list_photo_libraries()  # returns list of Path objects
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write failing tests using mock PhotoInfo, then implement icloud_scanner.py</name>

  <read_first>
    - .planning/phases/01-foundation-scanners/01-RESEARCH.md — Pattern 3 (osxphotos incremental scan, copy verbatim), §Pitfall 1 (dbfile= vs library_path=), §Pitfall 6 (timezone-aware datetimes for QueryOptions), §Pitfall 8 (non-standard library name)
    - python/my_tools/photos/cache.py — upsert_icloud_photo signature
    - .planning/phases/01-foundation-scanners/01-VALIDATION.md — test_icloud_scanner.py stubs
  </read_first>

  <files>
    python/my_tools/tests/test_icloud_scanner.py
    python/my_tools/photos/icloud_scanner.py
  </files>

  <behavior>
    - test_upserts_regular_photo: a mock photo with ismissing=False is upserted into icloud_photos with correct uuid, filename, date, width, height
    - test_upserts_missing_photo: a mock photo with ismissing=True and fingerprint="fp123" is upserted — fingerprint is non-null (Optimize Mac Storage support, ICLOUD-03)
    - test_incremental_uses_query_options: when scan_state has "icloud_last_scan_at", the scanner calls photosdb.query(QueryOptions(...)) not photosdb.photos()
    - test_full_scan_on_first_run: when scan_state has no "icloud_last_scan_at", the scanner calls photosdb.photos()
    - test_library_not_found_error: if default path absent and list_photo_libraries() returns [], raises FileNotFoundError with clear message
    - test_multiple_libraries_error: if list_photo_libraries() returns 2 libraries, raises ValueError with --library guidance
  </behavior>

  <action>
    ### Step 1 — Write RED tests in test_icloud_scanner.py:

    Create a `MockPhotoInfo` dataclass that mimics the osxphotos `PhotoInfo` attribute set:
    ```python
    from dataclasses import dataclass, field
    from datetime import datetime, timezone
    from unittest.mock import MagicMock, patch
    import pytest

    @dataclass
    class MockPhotoInfo:
        uuid: str = "test-uuid-001"
        filename: str = "IMG_0001.HEIC"
        original_filename: str = "IMG_0001.HEIC"
        date: datetime = field(default_factory=lambda: datetime(2021, 1, 1, 12, 0, 0, tzinfo=timezone.utc))
        date_added: datetime = field(default_factory=lambda: datetime(2021, 1, 2, tzinfo=timezone.utc))
        width: int = 4032
        height: int = 3024
        original_filesize: int = 5_000_000
        fingerprint: str = "fp_abc123"
        cloud_guid: str = "cloud-guid-001"
        hexdigest: str = "hex_abc123"
        iscloudasset: bool = True
        ismissing: bool = False
    ```

    Patch strategy: use `unittest.mock.patch` to replace `osxphotos.PhotosDB` and
    `osxphotos.list_photo_libraries` with mocks. The mock PhotosDB instance's `.photos()`
    returns a list of `MockPhotoInfo`. Use `tmp_db` fixture from conftest to avoid
    writing to the real database.

    Key test structure:
    ```python
    def test_upserts_regular_photo(tmp_db, monkeypatch):
        mock_photo = MockPhotoInfo()
        mock_db_instance = MagicMock()
        mock_db_instance.photos.return_value = [mock_photo]
        mock_db_instance.query.return_value = []

        with patch("my_tools.photos.icloud_scanner.osxphotos.PhotosDB", return_value=mock_db_instance), \
             patch("my_tools.photos.icloud_scanner.osxphotos.list_photo_libraries", return_value=[]), \
             patch("pathlib.Path.exists", return_value=True):
            from my_tools.photos.icloud_scanner import scan_icloud
            stats = scan_icloud(library_path="/fake/library.photoslibrary", quiet=True)

        import my_tools.photos.cache as cache_mod
        conn = cache_mod.get_connection()
        rows = conn.execute("SELECT * FROM icloud_photos WHERE uuid=?", ("test-uuid-001",)).fetchall()
        assert len(rows) == 1
        assert rows[0]["fingerprint"] == "fp_abc123"
        conn.close()
    ```

    For `test_upserts_missing_photo`: set `ismissing=True` in MockPhotoInfo, assert fingerprint non-null.
    For incremental tests: pre-seed scan_state with "icloud_last_scan_at" and assert
    `mock_db_instance.query` was called (not `mock_db_instance.photos`).

    ### Step 2 — Implement icloud_scanner.py (GREEN):

    Implement `scan_icloud(library_path: str | None = None, quiet: bool = False) -> dict`:

    ```python
    import os
    import osxphotos
    from osxphotos import QueryOptions
    from datetime import datetime, timezone
    from pathlib import Path
    from rich.progress import track
    from rich.console import Console
    from rich.table import Table
    from my_tools.photos import cache

    console = Console()

    def scan_icloud(library_path: str | None = None, quiet: bool = False) -> dict:
        # 1. Resolve library path
        default = Path.home() / "Pictures" / "Photos Library.photoslibrary"
        db_path = Path(library_path) if library_path else default

        if not db_path.exists():
            libraries = osxphotos.list_photo_libraries()
            if len(libraries) == 1:
                db_path = libraries[0]
            elif len(libraries) > 1:
                names = "\n".join(f"  {lib}" for lib in libraries)
                raise ValueError(
                    f"Multiple Photos libraries found. Use --library <path> to specify:\n{names}"
                )
            else:
                raise FileNotFoundError(
                    f"Photos library not found at {db_path}. "
                    "Use --library <path> to specify a custom location."
                )

        # 2. Open DB — use dbfile= (NOT library_path=)
        photosdb = osxphotos.PhotosDB(dbfile=str(db_path))

        # 3. Get SQLite connection and init schema
        conn = cache.get_connection()
        cache.init_schema(conn)

        # 4. Incremental or full scan
        last_scan = cache.get_scan_state(conn, "icloud_last_scan_at")
        scan_started_at = datetime.now(tz=timezone.utc).isoformat()

        if last_scan:
            last_dt = datetime.fromisoformat(last_scan).replace(tzinfo=timezone.utc)
            photos = photosdb.query(QueryOptions(added_after=last_dt))
        else:
            photos = photosdb.photos()

        photos_list = list(photos)  # materialize for count in progress bar

        # 5. Iterate and upsert
        stats = {"indexed": 0, "skipped": 0, "errors": 0}
        iterable = track(photos_list, description="Scanning iCloud...") if not quiet else photos_list

        for photo in iterable:
            try:
                cache.upsert_icloud_photo(conn, {
                    "uuid":              photo.uuid,
                    "filename":          photo.filename,
                    "original_filename": photo.original_filename,
                    "date":              photo.date.isoformat() if photo.date else None,
                    "date_added":        photo.date_added.isoformat() if photo.date_added else None,
                    "width":             photo.width,
                    "height":            photo.height,
                    "original_filesize": photo.original_filesize,
                    "fingerprint":       photo.fingerprint,
                    "cloud_guid":        photo.cloud_guid,
                    "hexdigest":         photo.hexdigest,
                    "iscloudasset":      int(photo.iscloudasset),
                    "ismissing":         int(photo.ismissing),
                })
                stats["indexed"] += 1
            except Exception as e:
                stats["errors"] += 1
                if not quiet:
                    console.print(f"[red]Error indexing {photo.uuid}: {e}[/red]")

        # 6. Persist scan state and commit
        cache.set_scan_state(conn, "icloud_last_scan_at", scan_started_at)
        conn.commit()
        conn.close()

        # 7. Summary
        if not quiet:
            table = Table(title="iCloud Scan Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", justify="right")
            table.add_row("Indexed", str(stats["indexed"]))
            table.add_row("Errors", str(stats["errors"]), style="red" if stats["errors"] else "")
            console.print(table)

        return stats
    ```
  </action>

  <verify>
    <automated>cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/test_icloud_scanner.py -v 2>&1</automated>
  </verify>

  <done>
    All 6 icloud scanner tests pass GREEN. `icloud_scanner.py` uses `dbfile=` parameter. Cloud-only photos (ismissing=True) are indexed with non-null fingerprint. Incremental re-scan path uses QueryOptions.
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire scan-icloud and setup commands, run full test suite</name>

  <read_first>
    - python/my_tools/photos/commands.py — stubs from Plan 1.1 to replace
    - python/my_tools/photos/icloud_scanner.py — scan_icloud() just implemented
    - .planning/phases/01-foundation-scanners/01-RESEARCH.md — §SETUP-02 Takeout Instructions (copy text verbatim), §Environment Availability (exiftool check)
  </read_first>

  <files>
    python/my_tools/photos/commands.py
  </files>

  <action>
    ### Replace the scan_icloud stub:
    ```python
    from my_tools.photos.icloud_scanner import scan_icloud as run_icloud_scan
    import typer

    @app.command("scan-icloud")
    def scan_icloud(
        library: Optional[Path] = typer.Option(None, "--library", help="Path to Photos Library. Default: ~/Pictures/Photos Library.photoslibrary"),
        quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress bar; print summary only"),
    ):
        """Scan Photos.app library and index all photos into SQLite."""
        try:
            run_icloud_scan(
                library_path=str(library) if library else None,
                quiet=quiet,
            )
        except (FileNotFoundError, ValueError) as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
    ```

    ### Replace the setup stub:
    Print the SETUP-02 Takeout instructions verbatim from RESEARCH.md §SETUP-02:

    ```python
    @app.command("setup")
    def setup():
        """Print Google Takeout export instructions and check system requirements."""
        from rich.console import Console
        import shutil

        console = Console()

        console.print("[bold cyan]Google Takeout Export Instructions[/bold cyan]\n")
        console.print(
            "  1. Go to [link]https://takeout.google.com[/link]\n"
            "  2. Click 'Deselect all', then scroll down and check only 'Google Photos'\n"
            "  3. Choose file type .zip, size 2GB (multiple files for large libraries)\n"
            "  4. Click 'Create export' -- Google will email you when ready (may take hours)\n"
            "  5. Download ALL zip files (e.g., takeout-20240101-001.zip, ...)\n"
            "  6. Create a folder and extract ALL zips into it, so all 'Takeout/' contents merge\n"
            "  7. Run: my-tools photos scan-takeout /path/to/that/folder\n"
        )

        console.print("[bold cyan]System Requirement Checks[/bold cyan]\n")

        # Check exiftool (required for Phase 3)
        exiftool = shutil.which("exiftool")
        if exiftool:
            console.print(f"[green]✓[/green] exiftool found at {exiftool}")
        else:
            console.print("[yellow]⚠[/yellow] exiftool not found — required for Phase 3 (metadata embedding).")
            console.print("  Install with: [bold]brew install exiftool[/bold]")

        # Check Photos library
        import osxphotos
        from pathlib import Path
        default_lib = Path.home() / "Pictures" / "Photos Library.photoslibrary"
        if default_lib.exists():
            console.print(f"[green]✓[/green] Photos library found at {default_lib}")
        else:
            libraries = osxphotos.list_photo_libraries()
            if libraries:
                console.print(f"[yellow]⚠[/yellow] Default Photos library not at expected path.")
                console.print(f"  Found {len(libraries)} library/libraries via Spotlight:")
                for lib in libraries:
                    console.print(f"    {lib}")
                console.print("  Use --library <path> with scan-icloud if needed.")
            else:
                console.print("[red]✗[/red] No Photos library found. Is Photos.app installed?")

        # Multi-ZIP warning
        console.print(
            "\n[yellow]Note:[/yellow] If your export had multiple ZIP files, "
            "ensure ALL are extracted into the same parent directory before running scan-takeout."
        )
    ```

    After wiring commands, run the full test suite to confirm no regressions:
    ```bash
    cd /Users/andreassavva/Repos/andreas-services/my-tools/python
    source venv/bin/activate
    python -m pytest my_tools/tests/ -v
    ```
  </action>

  <acceptance_criteria>
    - `grep -n "run_icloud_scan\|from my_tools.photos.icloud_scanner" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/commands.py` exits 0
    - `grep -n "takeout.google.com" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/commands.py` exits 0
    - `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/ -v` all tests pass
    - `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && my-tools photos setup` exits 0 and prints Takeout instructions
    - `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && my-tools photos scan-icloud --help` exits 0 and shows --library option
  </acceptance_criteria>

  <verify>
    <automated>cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/ -v 2>&1</automated>
  </verify>

  <done>
    Full test suite passes. `my-tools photos setup` prints Takeout instructions and system checks. `my-tools photos scan-icloud --help` shows --library option. No stubs remain in commands.py for scan-icloud or setup.
  </done>
</task>

</tasks>

## Verification

### must_haves
- `my-tools photos scan-icloud --help` exits 0 and shows `--library` option (ICLOUD-01)
- `icloud_scanner.py` contains `PhotosDB(dbfile=` — never `library_path=` (critical anti-pattern avoided)
- `icloud_scanner.py` handles `ismissing=True` photos — upsert does not skip them (ICLOUD-03)
- `icloud_scanner.py` uses `QueryOptions(added_after=last_dt)` for incremental re-scan (ICLOUD-04)
- `my-tools photos setup` prints step-by-step Takeout instructions and system checks (SETUP-02)
- Full test suite passes: schema tests + takeout scanner tests + icloud scanner tests (no regressions)

### automated
- `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/ -v` — all tests pass
- `grep -n "dbfile=" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/icloud_scanner.py` — exits 0
- `grep -n "library_path=" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/icloud_scanner.py` — exits 1 (must NOT appear)
- `grep -n "QueryOptions" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/icloud_scanner.py` — exits 0
- `grep -n "ismissing" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/photos/icloud_scanner.py` — exits 0
- `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && my-tools photos setup` — exits 0, stdout contains "takeout.google.com"

<output>
After completion, create `.planning/phases/01-foundation-scanners/01-3-SUMMARY.md` with:
- icloud_scanner.py behavior: full scan vs incremental, cloud-only photo handling
- setup command: what it checks and prints
- Test mock strategy (MockPhotoInfo)
- Any deviations from this plan

Also update `.planning/STATE.md`:
- Change Phase 1 status from "Planning" to "Complete"
- Update progress table: Phase 1 plans complete = 3/3
</output>
