"""Photos group — Google Takeout → iCloud migration commands."""
from pathlib import Path
import typer
from typing import Optional

from my_tools.photos.takeout_scanner import scan_takeout as run_scan

app = typer.Typer(
    help="Scan and migrate photos between Google Takeout and iCloud.",
    no_args_is_help=True,
)


@app.command("scan-takeout")
def scan_takeout(
    path: Path = typer.Argument(..., help="Path to extracted Google Takeout folder"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress bar; print summary only"),
    reset: bool = typer.Option(False, "--reset", help="Wipe and recreate the SQLite database before scanning"),
):
    """Scan a Google Takeout export and index all media into SQLite."""
    run_scan(str(path), quiet=quiet, reset=reset)


@app.command("scan-icloud")
def scan_icloud(
    library: Optional[Path] = typer.Option(None, "--library", help="Path to Photos Library. Default: ~/Pictures/Photos Library.photoslibrary"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress bar; print summary only"),
):
    """Scan Photos.app library and index all photos into SQLite."""
    # Implemented in Plan 1.3
    typer.echo("[Plan 1.3] scan-icloud not yet implemented.")
    raise typer.Exit(code=1)


@app.command("setup")
def setup():
    """Print Google Takeout export instructions and check system requirements."""
    # Implemented in Plan 1.3
    typer.echo("[Plan 1.3] setup not yet implemented.")
    raise typer.Exit(code=1)
