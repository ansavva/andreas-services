"""Photos group — Google Takeout → iCloud migration commands."""
from pathlib import Path
import typer
from typing import Optional

from my_tools.photos.takeout_scanner import scan_takeout as run_scan
from my_tools.photos.icloud_scanner import scan_icloud as run_icloud_scan

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
    library: Optional[Path] = typer.Option(
        None,
        "--library",
        help="Path to Photos Library. Default: ~/Pictures/Photos Library.photoslibrary",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress progress bar; print summary only"
    ),
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
        console.print(f"[green]checkmark[/green] exiftool found at {exiftool}")
    else:
        console.print("[yellow]warning[/yellow] exiftool not found -- required for Phase 3 (metadata embedding).")
        console.print("  Install with: [bold]brew install exiftool[/bold]")

    # Check Photos library
    import osxphotos
    from osxphotos.utils import list_photo_libraries

    default_lib = Path.home() / "Pictures" / "Photos Library.photoslibrary"
    if default_lib.exists():
        console.print(f"[green]checkmark[/green] Photos library found at {default_lib}")
    else:
        libraries = list_photo_libraries()
        if libraries:
            console.print("[yellow]warning[/yellow] Default Photos library not at expected path.")
            console.print(f"  Found {len(libraries)} library/libraries via Spotlight:")
            for lib in libraries:
                console.print(f"    {lib}")
            console.print("  Use --library <path> with scan-icloud if needed.")
        else:
            console.print("[red]x[/red] No Photos library found. Is Photos.app installed?")

    # Multi-ZIP warning
    console.print(
        "\n[yellow]Note:[/yellow] If your export had multiple ZIP files, "
        "ensure ALL are extracted into the same parent directory before running scan-takeout."
    )
