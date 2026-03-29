---
plan: 1.1
phase: 1
wave: 1
depends_on: []
files_modified:
  - python/my_tools/__init__.py
  - python/my_tools/cli.py
  - python/my_tools/photos/__init__.py
  - python/my_tools/photos/commands.py
  - python/my_tools/media/__init__.py
  - python/my_tools/media/commands.py
  - python/my_tools/qr/__init__.py
  - python/my_tools/qr/commands.py
  - python/my_tools/tests/__init__.py
  - python/my_tools/tests/conftest.py
  - python/my_tools/tests/test_cli_smoke.py
  - python/requirements.txt
  - pyproject.toml
autonomous: true
requirements:
  - CLI-01
  - CLI-02
  - CLI-03
  - CLI-04
  - CLI-05
  - CLI-06
  - SETUP-01

must_haves:
  truths:
    - "`my-tools --help` exits 0 and lists the groups photos, media, qr with one-line descriptions"
    - "`my-tools photos --help` lists scan-takeout, scan-icloud, setup as subcommands"
    - "`my-tools media kindle --help` exits 0 and shows the same parameters as the original kindle_formatter CLI"
    - "`my-tools qr generate --help` exits 0 and shows url, --output, --box-size, --border parameters"
    - "All three CLI groups are registered via a single `app.add_typer()` call per group in cli.py — adding a new group requires only creating a module + one registration line"
    - "Venv is Python 3.13 created with `/opt/homebrew/bin/python3.13`"
  artifacts:
    - path: "python/my_tools/cli.py"
      provides: "Main Typer app that registers all groups"
      exports: ["app"]
    - path: "python/my_tools/media/commands.py"
      provides: "kindle subcommand wrapping kindle_formatter logic"
    - path: "python/my_tools/qr/commands.py"
      provides: "generate subcommand wrapping url_to_qr logic"
    - path: "python/my_tools/photos/commands.py"
      provides: "photos group stub with scan-takeout, scan-icloud, setup stubs"
    - path: "python/requirements.txt"
      provides: "Pinned Python 3.13 dependencies for all groups"
      contains: "typer==0.24.1"
    - path: "pyproject.toml"
      provides: "Entry point: my-tools = my_tools.cli:app"
  key_links:
    - from: "python/my_tools/cli.py"
      to: "python/my_tools/photos/commands.py"
      via: "app.add_typer(photos_app, name='photos')"
    - from: "python/my_tools/cli.py"
      to: "python/my_tools/media/commands.py"
      via: "app.add_typer(media_app, name='media')"
    - from: "python/my_tools/cli.py"
      to: "python/my_tools/qr/commands.py"
      via: "app.add_typer(qr_app, name='qr')"
    - from: "pyproject.toml"
      to: "python/my_tools/cli.py"
      via: "[project.scripts] my-tools = 'my_tools.cli:app'"
---

<objective>
Build the unified `my-tools` CLI package: a Typer multi-group app installed as a single entry point that wraps all personal tools. Existing standalone scripts (kindle_formatter.py, url_to_qr.py) are migrated into the package as `media kindle` and `qr generate` commands. The photos group is stubbed for Plan 1.2/1.3 to flesh out.

Purpose: All personal tools reachable from one `my-tools` command; new groups added with minimal ceremony (one directory + one registration line in cli.py).

Output: Installable `my-tools` package under `python/`, Python 3.13 venv, unified requirements.txt, test scaffold.
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
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Bootstrap package structure, venv, and test scaffold</name>

  <read_first>
    - .planning/phases/01-foundation-scanners/01-CONTEXT.md — file structure diagram and decisions
    - .planning/phases/01-foundation-scanners/01-RESEARCH.md — standard stack (typer 0.24.1, rich 14.3.3, Python 3.13 path)
  </read_first>

  <files>
    python/my_tools/__init__.py
    python/my_tools/photos/__init__.py
    python/my_tools/media/__init__.py
    python/my_tools/qr/__init__.py
    python/my_tools/tests/__init__.py
    python/my_tools/tests/conftest.py
    python/my_tools/tests/test_cli_smoke.py
    python/requirements.txt
    pyproject.toml
  </files>

  <behavior>
    - test_cli_help: invoking `my-tools --help` via subprocess exits 0 and stdout contains "photos", "media", "qr"
    - test_photos_help: invoking `my-tools photos --help` exits 0 and stdout contains "scan-takeout", "scan-icloud", "setup"
    - test_media_help: invoking `my-tools media --help` exits 0 and stdout contains "kindle"
    - test_qr_help: invoking `my-tools qr --help` exits 0 and stdout contains "generate"
  </behavior>

  <action>
    1. Create the venv (run once, not idempotent — skip if venv/ exists):
       ```
       cd /Users/andreassavva/Repos/andreas-services/my-tools/python
       /opt/homebrew/bin/python3.13 -m venv venv
       source venv/bin/activate
       ```

    2. Write `python/requirements.txt` with exact pinned versions:
       ```
       # Core CLI
       typer==0.24.1
       rich==14.3.3

       # iCloud scanner (Plan 1.3)
       osxphotos==0.75.6

       # Existing tools deps (merged from old requirements)
       qrcode[pil]==8.0
       Pillow>=10.0,<12
       pymupdf>=1.24,<2

       # Dev
       pytest>=8.0
       ```

    3. Install: `pip install -r requirements.txt`

    4. Write `pyproject.toml` in the repo root (my-tools/):
       ```toml
       [build-system]
       requires = ["setuptools>=70"]
       build-backend = "setuptools.backends.legacy:build"

       [project]
       name = "my-tools"
       version = "0.1.0"
       requires-python = ">=3.13"
       dependencies = [
           "typer==0.24.1",
           "rich==14.3.3",
           "osxphotos==0.75.6",
           "qrcode[pil]==8.0",
           "Pillow>=10.0,<12",
           "pymupdf>=1.24,<2",
       ]

       [project.scripts]
       my-tools = "my_tools.cli:app"

       [tool.setuptools.packages.find]
       where = ["python"]
       ```

    5. Install the package in editable mode:
       `pip install -e .`

    6. Create all `__init__.py` files as empty.

    7. Write `python/my_tools/tests/conftest.py`:
       ```python
       import subprocess, sys
       from pathlib import Path

       PYTHON = sys.executable  # venv python

       def run_cli(*args):
           """Run my-tools CLI via subprocess. Returns (returncode, stdout, stderr)."""
           result = subprocess.run(
               ["my-tools", *args],
               capture_output=True, text=True
           )
           return result.returncode, result.stdout, result.stderr
       ```

    8. Write `python/my_tools/tests/test_cli_smoke.py` with the four RED tests (they will fail until Task 2 creates cli.py and commands.py files):
       ```python
       from conftest import run_cli

       def test_cli_help():
           rc, out, _ = run_cli("--help")
           assert rc == 0
           assert "photos" in out
           assert "media" in out
           assert "qr" in out

       def test_photos_help():
           rc, out, _ = run_cli("photos", "--help")
           assert rc == 0
           assert "scan-takeout" in out
           assert "scan-icloud" in out
           assert "setup" in out

       def test_media_help():
           rc, out, _ = run_cli("media", "--help")
           assert rc == 0
           assert "kindle" in out

       def test_qr_help():
           rc, out, _ = run_cli("qr", "--help")
           assert rc == 0
           assert "generate" in out
       ```
  </action>

  <verify>
    <automated>cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/test_cli_smoke.py -x -q 2>&1 | head -20</automated>
  </verify>

  <done>
    venv exists at python/venv/ using Python 3.13; requirements.txt pinned; pyproject.toml has entry point; test scaffold created; tests are RED (my-tools command not found or fails) — this is correct at this stage.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement CLI groups — cli.py, media kindle, qr generate, photos stubs</name>

  <read_first>
    - python/my_tools/tests/test_cli_smoke.py — the tests that must go GREEN
    - .planning/phases/01-foundation-scanners/01-RESEARCH.md — Pattern 1 (Typer multi-command), Pattern 7 (validate_takeout_folder stub)
    - .planning/phases/01-foundation-scanners/01-CONTEXT.md — file structure diagram, existing tools to wrap
  </read_first>

  <files>
    python/my_tools/cli.py
    python/my_tools/photos/commands.py
    python/my_tools/media/commands.py
    python/my_tools/qr/commands.py
  </files>

  <behavior>
    - All four smoke tests from Task 1 pass (GREEN)
    - `my-tools media kindle --help` shows: INPUT_PDF (positional), --output-dir, same behavior description as original kindle_formatter
    - `my-tools qr generate --help` shows: URL (positional), --output / -o, --box-size, --border
    - `my-tools photos scan-takeout --help` shows: PATH (positional), --quiet / -q, --reset
    - `my-tools photos setup` prints Takeout export instructions (no crash)
  </behavior>

  <action>
    ### python/my_tools/cli.py
    ```python
    """my-tools — unified personal toolbox CLI."""
    import typer
    from my_tools.photos import commands as photos_commands
    from my_tools.media import commands as media_commands
    from my_tools.qr import commands as qr_commands

    app = typer.Typer(
        name="my-tools",
        help="Unified personal toolbox. Run `my-tools <group> --help` for details.",
        no_args_is_help=True,
    )

    # Register groups — adding a new group: create my_tools/<group>/commands.py with a
    # `app = typer.Typer(...)`, then add one app.add_typer() line below.
    app.add_typer(photos_commands.app, name="photos")
    app.add_typer(media_commands.app, name="media")
    app.add_typer(qr_commands.app, name="qr")

    if __name__ == "__main__":
        app()
    ```

    ### python/my_tools/photos/commands.py
    ```python
    """Photos group — Google Takeout → iCloud migration commands."""
    from pathlib import Path
    import typer
    from typing import Optional

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
        # Implemented in Plan 1.2
        typer.echo("[Plan 1.2] scan-takeout not yet implemented.")
        raise typer.Exit(code=1)

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
    ```

    ### python/my_tools/media/commands.py
    Migrate all logic from the original kindle_formatter.py into this file. Import
    the same third-party libraries (pymupdf as fitz, Pillow, subprocess for Calibre and
    Kindle Previewer). The Typer command `kindle` must accept the same inputs as the
    original argparse CLI and call the same pipeline functions:
    `analyze_pdf_images`, `clean_pdf`, `extract_cover`, `pdf_to_epub`,
    `preview_in_kindle_previewer`.

    ```python
    """Media group — tools for books and documents."""
    from pathlib import Path
    import typer

    app = typer.Typer(
        help="Media tools (Kindle formatting, etc.).",
        no_args_is_help=True,
    )

    # --- Kindle formatter (migrated from python/kindle_formatter.py) ---
    # Copy all helper functions (analyze_pdf_images, clean_pdf, extract_cover,
    # pdf_to_epub, preview_in_kindle_previewer) verbatim from kindle_formatter.py.
    # Replace the argparse main() with the Typer command below.

    @app.command("kindle")
    def kindle(
        input_pdf: Path = typer.Argument(..., help="Path to the PDF file to prepare for Kindle"),
    ):
        """Prepare a PDF for Kindle: clean, convert to EPUB, open in Kindle Previewer."""
        # Call the migrated pipeline functions in order:
        # analyze_pdf_images(input_pdf)
        # cleaned = clean_pdf(input_pdf)
        # extract_cover(input_pdf)
        # epub = pdf_to_epub(cleaned)
        # preview_in_kindle_previewer(epub)
        pass  # Replace with actual calls after copying logic
    ```

    After writing the stub, copy the full implementation from
    `python/kindle_formatter.py` into the helper function section. The original file
    does not exist yet in this greenfield repo — implement the logic directly in
    commands.py using the docstring in CLAUDE.md as the spec:
    pipeline: analyze_pdf_images → clean_pdf (crop 10% top/bottom) → extract_cover →
    pdf_to_epub (Calibre, Kindle output profile) → preview_in_kindle_previewer (macOS open).
    Output goes to a timestamped directory next to the source PDF.

    ### python/my_tools/qr/commands.py
    Migrate all logic from the original url_to_qr.py:

    ```python
    """QR group — QR code generation."""
    from pathlib import Path
    import typer

    app = typer.Typer(
        help="QR code tools.",
        no_args_is_help=True,
    )

    @app.command("generate")
    def generate(
        url: str = typer.Argument(..., help="URL to encode as a QR code"),
        output: Path = typer.Option(Path("qr_code.png"), "--output", "-o", help="Output PNG file path"),
        box_size: int = typer.Option(10, "--box-size", help="Pixel size per QR module"),
        border: int = typer.Option(4, "--border", help="Border width in QR modules"),
    ):
        """Convert a URL to a QR code PNG image."""
        import qrcode
        from PIL import Image

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=box_size,
            border=border,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(output))
        typer.echo(f"QR code saved to {output}")
    ```
  </action>

  <verify>
    <automated>cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/test_cli_smoke.py -v 2>&1</automated>
  </verify>

  <done>
    All four smoke tests pass (GREEN). `my-tools --help` shows photos/media/qr groups. `my-tools qr generate https://example.com` creates qr_code.png in cwd. `my-tools media kindle --help` shows input_pdf argument. `my-tools photos --help` shows three subcommands.
  </done>
</task>

</tasks>

## Verification

### must_haves
- `my-tools --help` exits 0 and output contains "photos", "media", "qr"
- `my-tools photos --help` output contains "scan-takeout", "scan-icloud", "setup"
- `my-tools media kindle --help` exits 0
- `my-tools qr generate --help` exits 0 and output contains "--output", "--box-size", "--border"
- `python/venv/` uses Python 3.13 (`python/venv/bin/python --version` → Python 3.13.x)
- `python/requirements.txt` contains `typer==0.24.1`
- `pyproject.toml` contains `my-tools = "my_tools.cli:app"` under `[project.scripts]`
- cli.py registers groups via `app.add_typer()` — adding a new group requires only a new module + one line

### automated
- `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python -m pytest my_tools/tests/test_cli_smoke.py -v` — all 4 smoke tests pass
- `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && my-tools --help` — exits 0, output contains photos/media/qr
- `cd /Users/andreassavva/Repos/andreas-services/my-tools/python && source venv/bin/activate && python/venv/bin/python --version` — outputs "Python 3.13.x"
- `grep -n "add_typer" /Users/andreassavva/Repos/andreas-services/my-tools/python/my_tools/cli.py` — exits 0, shows 3 add_typer calls

<output>
After completion, create `.planning/phases/01-foundation-scanners/01-1-SUMMARY.md` with:
- What was built (package structure, commands available)
- Python version and venv location
- How to activate: `cd python && source venv/bin/activate`
- How to add a new group (one-liner)
- Any deviations from this plan
</output>
