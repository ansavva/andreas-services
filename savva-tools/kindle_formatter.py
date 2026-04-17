#!/usr/bin/env python3
"""
Kindle PDF Formatter

Takes a PDF and prepares it for Kindle:
1. Analyzes images/diagrams in the PDF
2. Cleans margins and removes headers/footers
3. Extracts and validates the cover image
4. Converts to EPUB using Calibre (EPUB is the current Amazon-recommended format)
5. Opens in Kindle Previewer 3 for review

All output is written to a timestamped directory next to the source PDF.

Usage:
    python kindle_formatter.py path/to/your/book.pdf

Dependencies:
    pip install pymupdf pillow
    Calibre CLI (ebook-convert): https://calibre-ebook.com
    Kindle Previewer 3: https://kdp.amazon.com/en_US/help/topic/G202131170
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.stderr.write("PyMuPDF is required. Install with: pip install pymupdf\n")
    raise SystemExit(1)

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("Pillow is required. Install with: pip install pillow\n")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Image analysis
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
    print(f"[analyze] Found {len(results)} images ({low_res_count} low-res) across PDF.")
    return results


# ---------------------------------------------------------------------------
# PDF cleaning
# ---------------------------------------------------------------------------

def clean_pdf(pdf_path: Path, out_dir: Path) -> Path:
    """
    Crop 10 % from the top and bottom of every page to remove headers/footers.
    Saves the cleaned PDF into out_dir.
    """
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
    print(f"[clean] Cleaned PDF → {output_path.name}")
    return output_path


# ---------------------------------------------------------------------------
# Cover extraction
# ---------------------------------------------------------------------------

def extract_cover(pdf_path: Path, out_dir: Path) -> Path:
    """
    Extract the cover image from the PDF into out_dir.

    Strategy:
    1. Pull the largest embedded image from page 0.
    2. Fall back to rendering page 0 at 2× resolution.
    """
    import io
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
        print(f"[cover] Extracted embedded cover → {output_path.name}")
    else:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pix.save(str(output_path))
        print(f"[cover] Rendered page 1 as cover → {output_path.name}")

    doc.close()
    return output_path


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

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
    print(f"[convert] EPUB → {output_path.name}")
    return output_path


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def pdf_to_kindle(pdf_path: str | Path) -> None:
    """
    Full pipeline: analyze → clean → convert to EPUB → preview.
    """
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Create a timestamped output directory next to the source PDF
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = pdf_path.parent / f"{pdf_path.stem}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Kindle Formatter: {pdf_path.name} ===")
    print(f"    Output dir: {out_dir}\n")

    # Step 1 — analyze
    image_report = analyze_pdf_images(pdf_path)
    low_res = [r for r in image_report if r["low_res"]]
    if low_res:
        print(f"  Warning: {len(low_res)} low-resolution image(s) — may appear blurry on Kindle.")

    # Step 2 — clean
    cleaned_pdf = clean_pdf(pdf_path, out_dir)

    # Step 3 — extract cover (used by Calibre during conversion)
    cover_path = extract_cover(pdf_path, out_dir)

    # Step 4 — PDF → EPUB
    epub_path = pdf_to_epub(cleaned_pdf, cover_path, out_dir)

    print(f"\n[done] EPUB ready for upload: {epub_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python kindle_formatter.py <path_to_pdf>")
        sys.exit(1)

    pdf_to_kindle(sys.argv[1])
