"""Media group — tools for books and documents."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import typer

app = typer.Typer(
    help="Media tools (Kindle formatting, etc.).",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Kindle formatter helpers (migrated from savva-tools/kindle_formatter.py)
# ---------------------------------------------------------------------------

def analyze_pdf_images(pdf_path: Path) -> list[dict]:
    """
    Inspect every image in the PDF.

    Returns a list of dicts with keys:
        page         — 0-based page index
        index        — image index on the page
        width/height — pixel dimensions
        colorspace   — e.g. "DeviceRGB"
        low_res      — True if shorter side < 150 px (likely blurry on Kindle)
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        typer.echo("PyMuPDF is required. Install with: pip install pymupdf", err=True)
        raise typer.Exit(code=1)

    doc = fitz.open(str(pdf_path))
    results = []

    for page_num, page in enumerate(doc):
        for img_index, img_info in enumerate(page.get_images(full=True)):
            xref = img_info[0]
            base_image = doc.extract_image(xref)
            w, h = base_image["width"], base_image["height"]
            results.append(
                {
                    "page": page_num,
                    "index": img_index,
                    "width": w,
                    "height": h,
                    "colorspace": str(base_image.get("colorspace", "unknown")),
                    "low_res": min(w, h) < 150,
                }
            )

    doc.close()
    low_res_count = sum(1 for r in results if r["low_res"])
    typer.echo(f"[analyze] Found {len(results)} images ({low_res_count} low-res) across PDF.")
    return results


def clean_pdf(pdf_path: Path, out_dir: Path) -> Path:
    """
    Crop 10 % from the top and bottom of every page to remove headers/footers.
    Saves the cleaned PDF into out_dir.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        typer.echo("PyMuPDF is required. Install with: pip install pymupdf", err=True)
        raise typer.Exit(code=1)

    output_path = out_dir / (pdf_path.stem + "_cleaned.pdf")

    doc = fitz.open(str(pdf_path))
    for page in doc:
        rect = page.rect
        page.set_cropbox(fitz.Rect(
            rect.x0,
            rect.y0 + rect.height * 0.10,
            rect.x1,
            rect.y1 - rect.height * 0.10,
        ))

    doc.save(str(output_path))
    doc.close()
    typer.echo(f"[clean] Cleaned PDF → {output_path.name}")
    return output_path


def extract_cover(pdf_path: Path, out_dir: Path) -> Path:
    """
    Extract the cover image from the PDF into out_dir.

    Strategy:
    1. Pull the largest embedded image from page 0.
    2. Fall back to rendering page 0 at 2× resolution.
    """
    import io

    try:
        import fitz  # PyMuPDF
        from PIL import Image
    except ImportError as exc:
        typer.echo(f"Missing dependency: {exc}. Install with: pip install pymupdf pillow", err=True)
        raise typer.Exit(code=1)

    output_path = out_dir / (pdf_path.stem + "_cover.png")

    doc = fitz.open(str(pdf_path))
    page = doc[0]
    images = page.get_images(full=True)

    if images:
        largest = max(
            images,
            key=lambda info: doc.extract_image(info[0])["width"]
                             * doc.extract_image(info[0])["height"],
        )
        base_image = doc.extract_image(largest[0])
        img = Image.open(io.BytesIO(base_image["image"]))
        img.save(str(output_path), "PNG")
        typer.echo(f"[cover] Extracted embedded cover → {output_path.name}")
    else:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(str(output_path))
        typer.echo(f"[cover] Rendered page 1 as cover → {output_path.name}")

    doc.close()
    return output_path


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr.strip()}")


def pdf_to_epub(pdf_path: Path, cover_path: Path, out_dir: Path) -> Path:
    """
    Convert a cleaned PDF to EPUB using Calibre.

    EPUB is Amazon's current recommended format for Kindle uploads and
    is accepted directly by Send to Kindle and Kindle Previewer 3.
    No secondary AZW3/MOBI conversion is needed.
    """
    output_path = out_dir / (pdf_path.stem.removesuffix("_cleaned") + ".epub")

    _run([
        "ebook-convert",
        str(pdf_path),
        str(output_path),
        "--output-profile", "kindle",
        "--cover", str(cover_path),
        "--margin-top", "10",
        "--margin-bottom", "10",
        "--margin-left", "10",
        "--margin-right", "10",
        # Flatten the TOC to avoid E24011 scope errors from nested nav points
        "--level1-toc", "//h:h1",
        "--level2-toc", "//h:h2",
        "--no-chapters-in-toc",
    ])
    typer.echo(f"[convert] EPUB → {output_path.name}")
    return output_path


def preview_in_kindle_previewer(epub_path: Path) -> None:
    """Open the EPUB in Kindle Previewer 3 on macOS."""
    subprocess.run(["open", "-a", "Kindle Previewer 3", str(epub_path)])


# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------

@app.command("kindle")
def kindle(
    input_pdf: Path = typer.Argument(..., help="Path to the PDF file to prepare for Kindle"),
):
    """Prepare a PDF for Kindle: clean, convert to EPUB, open in Kindle Previewer."""
    input_pdf = input_pdf.expanduser().resolve()
    if not input_pdf.exists():
        typer.echo(f"Error: PDF not found: {input_pdf}", err=True)
        raise typer.Exit(code=1)

    # Create a timestamped output directory next to the source PDF
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = input_pdf.parent / f"{input_pdf.stem}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    typer.echo(f"\n=== Kindle Formatter: {input_pdf.name} ===")
    typer.echo(f"    Output dir: {out_dir}\n")

    # Step 1 — analyze
    image_report = analyze_pdf_images(input_pdf)
    low_res = [r for r in image_report if r["low_res"]]
    if low_res:
        typer.echo(f"  Warning: {len(low_res)} low-resolution image(s) — may appear blurry on Kindle.")

    # Step 2 — clean
    cleaned_pdf = clean_pdf(input_pdf, out_dir)

    # Step 3 — extract cover (used by Calibre during conversion)
    cover_path = extract_cover(input_pdf, out_dir)

    # Step 4 — PDF → EPUB
    epub_path = pdf_to_epub(cleaned_pdf, cover_path, out_dir)

    # Step 5 — open in Kindle Previewer
    preview_in_kindle_previewer(epub_path)

    typer.echo(f"\n[done] EPUB ready for upload: {epub_path}")
