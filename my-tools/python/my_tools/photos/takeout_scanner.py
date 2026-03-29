"""Google Takeout scanner — walks export, pairs sidecars, detects Live Photos, indexes to SQLite."""
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import track
from rich.table import Table

from my_tools.photos import cache

console = Console()

MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tiff", ".tif",
    ".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv", ".dng", ".cr2",
    ".nef", ".arw", ".raw",
}


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


def parse_sidecar(sidecar_path: str) -> dict:
    """Extract metadata fields from a Google Takeout JSON sidecar."""
    with open(sidecar_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    taken_ts = data.get("photoTakenTime", {}).get("timestamp")
    creation_dt = (
        datetime.fromtimestamp(int(taken_ts), tz=timezone.utc)
        if taken_ts else None
    )

    return {
        "creation_time": creation_dt.isoformat() if creation_dt else None,
        "width": int(data.get("width", 0)) or None,   # cast string to int; 0->None
        "height": int(data.get("height", 0)) or None,
        "latitude": data.get("geoData", {}).get("latitude"),
        "longitude": data.get("geoData", {}).get("longitude"),
    }


def detect_live_photo_pairs(directory: str) -> dict[str, str]:
    """
    Returns a dict mapping MOV path -> paired image path for Live Photo pairs.
    A pair is: same filename stem, one is MOV, other is an image format.
    """
    # Map lowercase stem -> list of (original_filename, lowercase_ext)
    by_stem: dict[str, list[tuple[str, str]]] = {}
    try:
        for entry in os.scandir(directory):
            if not entry.is_file():
                continue
            stem, ext = os.path.splitext(entry.name)
            ext_lower = ext.lower()
            by_stem.setdefault(stem, []).append((entry.name, ext_lower))
    except PermissionError:
        return {}

    pairs = {}
    image_exts = {".heic", ".heif", ".jpg", ".jpeg"}
    for stem, name_ext_pairs in by_stem.items():
        ext_lower_list = [e for _, e in name_ext_pairs]
        if ".mov" in ext_lower_list and any(e in image_exts for e in ext_lower_list):
            # Find the original MOV filename (preserving case)
            mov_name = next(n for n, e in name_ext_pairs if e == ".mov")
            mov_path = os.path.join(directory, mov_name)
            # Find the image partner (prefer HEIC over JPG, preserving original case)
            for image_ext in [".heic", ".heif", ".jpg", ".jpeg"]:
                if image_ext in ext_lower_list:
                    image_name = next(n for n, e in name_ext_pairs if e == image_ext)
                    image_path = os.path.join(directory, image_name)
                    pairs[mov_path] = image_path
                    break

    return pairs


def scan_takeout(path: str, quiet: bool = False, reset: bool = False) -> dict:
    """
    Walk a Google Takeout export, pair sidecars, detect Live Photos, and write
    one row per media file to google_photos table. Re-runs are incremental.

    Returns stats dict: {"indexed": int, "skipped": int, "no_sidecar": int, "errors": int}
    """
    valid, error_msg = validate_takeout_folder(path)
    if not valid:
        console.print(f"[red]Error:[/red] {error_msg}")
        raise typer.Exit(code=1)

    conn = cache.get_connection()
    cache.init_schema(conn)

    if reset:
        cache.reset_database(conn)
        # reset_database calls init_schema internally, so schema is ready

    scan_started_at = datetime.now(tz=timezone.utc).isoformat()

    # Collect all media files from the Takeout tree
    media_files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext.lower() in MEDIA_EXTENSIONS:
                media_files.append(os.path.join(dirpath, filename))

    stats = {"indexed": 0, "skipped": 0, "no_sidecar": 0, "errors": 0}

    # Collect Live Photo pairs per directory (cache by directory)
    live_pairs_cache: dict[str, dict[str, str]] = {}

    def get_live_pairs(directory: str) -> dict[str, str]:
        if directory not in live_pairs_cache:
            live_pairs_cache[directory] = detect_live_photo_pairs(directory)
        return live_pairs_cache[directory]

    iterable = (
        track(media_files, description="Scanning Takeout...", console=console)
        if not quiet
        else media_files
    )

    for media_path in iterable:
        try:
            # Incremental skip: check if already indexed
            if cache.is_takeout_file_indexed(conn, media_path):
                stats["skipped"] += 1
                continue

            # Compute SHA-256
            sha256 = hashlib.sha256()
            with open(media_path, "rb") as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            sha256_hex = sha256.hexdigest()

            # Find and parse sidecar
            sidecar_path = find_sidecar(media_path)
            if sidecar_path:
                sidecar_data = parse_sidecar(sidecar_path)
                creation_time = sidecar_data["creation_time"]
                width = sidecar_data["width"]
                height = sidecar_data["height"]
                sidecar_found = 1
            else:
                creation_time = datetime.fromtimestamp(
                    os.path.getmtime(media_path), tz=timezone.utc
                ).isoformat()
                width = None
                height = None
                sidecar_found = 0
                stats["no_sidecar"] += 1

            # Determine media type
            _, ext = os.path.splitext(media_path)
            video_exts = {".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v", ".wmv"}
            media_type = "video" if ext.lower() in video_exts else "photo"

            # Check for Live Photo pair
            directory = os.path.dirname(media_path)
            live_pairs = get_live_pairs(directory)
            is_live_photo_video = 0
            live_photo_partner_path = None
            if media_path in live_pairs:
                is_live_photo_video = 1
                live_photo_partner_path = live_pairs[media_path]

            # Build and upsert record
            data = {
                "file_path": media_path,
                "filename": os.path.basename(media_path),
                "creation_time": creation_time,
                "width": width,
                "height": height,
                "file_size": os.path.getsize(media_path),
                "sha256": sha256_hex,
                "sidecar_found": sidecar_found,
                "media_type": media_type,
                "is_live_photo_video": is_live_photo_video,
                "live_photo_partner_path": live_photo_partner_path,
            }
            cache.upsert_google_photo(conn, data)
            stats["indexed"] += 1

        except Exception as e:
            stats["errors"] += 1
            if not quiet:
                console.print(f"[red]Error processing {media_path}:[/red] {e}")

    # Update scan state and commit
    cache.set_scan_state(conn, "takeout_last_scan_at", scan_started_at)
    conn.commit()
    conn.close()

    # Print summary table
    if not quiet:
        table = Table(title="Scan Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("Indexed", str(stats["indexed"]))
        table.add_row("Skipped (already cached)", str(stats["skipped"]))
        table.add_row("No sidecar (date approximate)", str(stats["no_sidecar"]))
        table.add_row(
            "Errors",
            str(stats["errors"]),
            style="red" if stats["errors"] else "",
        )
        console.print(table)

        if stats["no_sidecar"] > 0:
            console.print(
                f"[yellow]Warning: {stats['no_sidecar']} photos had no sidecar "
                "— dates may be approximate[/yellow]"
            )

    return stats
