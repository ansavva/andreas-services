"""iCloud Photos library scanner via osxphotos."""
import osxphotos
from osxphotos import QueryOptions
from osxphotos.utils import list_photo_libraries
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import track
from rich.table import Table

from my_tools.photos import cache

console = Console()


def scan_icloud(library_path: str | None = None, quiet: bool = False) -> dict:
    """Scan Photos.app library and index all photos into SQLite.

    Args:
        library_path: Path to Photos Library .photoslibrary. If None, auto-detects.
        quiet: Suppress progress bar and summary table.

    Returns:
        dict with keys: indexed, errors
    """
    # 1. Resolve library path
    default = Path.home() / "Pictures" / "Photos Library.photoslibrary"
    db_path = Path(library_path) if library_path else default

    if not db_path.exists():
        libraries = list_photo_libraries()
        if len(libraries) == 1:
            db_path = libraries[0]
        elif len(libraries) > 1:
            names = "\n".join(f"  {lib}" for lib in libraries)
            raise ValueError(
                f"Multiple Photos libraries found. Use --library <path> to specify one:\n{names}"
            )
        else:
            raise FileNotFoundError(
                f"Photos library not found at {db_path}. "
                "Use --library <path> to specify a custom location."
            )

    # 2. Open Photos DB — use dbfile= (NOT library_path=)
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

    photos_list = list(photos)  # materialise for progress bar count

    # 5. Iterate and upsert
    stats = {"indexed": 0, "errors": 0}
    iterable = (
        track(photos_list, description="Scanning iCloud...") if not quiet else photos_list
    )

    for photo in iterable:
        try:
            cache.upsert_icloud_photo(
                conn,
                {
                    "uuid": photo.uuid,
                    "filename": photo.filename,
                    "original_filename": photo.original_filename,
                    "date": photo.date.isoformat() if photo.date else None,
                    "date_added": (
                        photo.date_added.isoformat() if photo.date_added else None
                    ),
                    "width": photo.width,
                    "height": photo.height,
                    "original_filesize": photo.original_filesize,
                    "fingerprint": photo.fingerprint,
                    "cloud_guid": photo.cloud_guid,
                    "hexdigest": photo.hexdigest,
                    "iscloudasset": int(photo.iscloudasset),
                    "ismissing": int(photo.ismissing),
                },
            )
            stats["indexed"] += 1
        except Exception as e:
            stats["errors"] += 1
            if not quiet:
                console.print(f"[red]Error indexing {photo.uuid}: {e}[/red]")

    # 6. Persist scan state and commit
    cache.set_scan_state(conn, "icloud_last_scan_at", scan_started_at)
    conn.commit()
    conn.close()

    # 7. Summary output
    if not quiet:
        table = Table(title="iCloud Scan Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("Indexed", str(stats["indexed"]))
        table.add_row(
            "Errors",
            str(stats["errors"]),
            style="red" if stats["errors"] else "",
        )
        console.print(table)

    return stats
