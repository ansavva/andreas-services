# my-tools

A personal collection of Python utility scripts.

## Structure

```
my-tools/
└── python/
    ├── requirements.txt       — all Python dependencies
    ├── venv/                  — virtual environment (Python 3.9)
    ├── url_to_qr.py           — convert a URL to a QR code image
    └── kindle_formatter.py    — prepare a PDF for Kindle and send it to your device
```

## Setup

```bash
cd my-tools/python
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

External tools required by some scripts:
- **Calibre CLI** (`ebook-convert`): https://calibre-ebook.com
- **Kindle Previewer 3**: https://kdp.amazon.com/en_US/help/topic/G202131170

---

## Scripts

### url_to_qr.py
Converts a URL to a QR code PNG image.

```bash
python url_to_qr.py "https://example.com" --output example.png
```

Options:
- `-o / --output` — output file path (default: `qr_code.png`)
- `--box-size` — pixel size per QR box (default: 10)
- `--border` — border width in boxes (default: 4)

---

### kindle_formatter.py
Prepares a PDF for Kindle: cleans it, converts to EPUB via Calibre, and opens
it in Kindle Previewer 3 for review. EPUB is Amazon's current recommended
format — upload the output file directly via Send to Kindle or KDP.

```bash
python kindle_formatter.py path/to/your/book.pdf
```

All output is written to a timestamped directory next to the source PDF,
e.g. `mybook_20260328_143201/`. Re-runs never overwrite each other.

Pipeline:
1. `analyze_pdf_images(pdf)` — flags low-res images that may look blurry
2. `clean_pdf(pdf)` — crops 10 % top/bottom to remove headers/footers
3. `extract_cover(pdf)` — pulls embedded cover or renders page 1 at 2×
4. `pdf_to_epub(pdf)` — Calibre conversion with Kindle output profile
5. `preview_in_kindle_previewer(file)` — opens EPUB in Kindle Previewer 3 (macOS)

The EPUB path is printed at the end — upload it to your Kindle manually.
