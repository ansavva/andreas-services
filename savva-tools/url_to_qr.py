#!/usr/bin/env python3
"""
Utility script to turn a URL into a QR code image.

Usage:
    python url_to_qr.py "https://example.com" --output example.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import qrcode
except ImportError as exc:  # pragma: no cover - dependency gate
    sys.stderr.write(
        "The 'qrcode' package is required. Install it with 'pip install qrcode[pil]'.\n"
    )
    raise SystemExit(1) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a QR code image for a given URL."
    )
    parser.add_argument("url", help="The URL to encode into the QR code.")
    parser.add_argument(
        "-o",
        "--output",
        default="qr_code.png",
        help="Output image path (default: %(default)s).",
    )
    parser.add_argument(
        "--box-size",
        type=int,
        default=10,
        help="Pixel size for each QR box (default: %(default)s).",
    )
    parser.add_argument(
        "--border",
        type=int,
        default=4,
        help="Border width measured in boxes (default: %(default)s).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    qr = qrcode.QRCode(box_size=args.box_size, border=args.border)
    qr.add_data(args.url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)
    print(f"QR code saved to {output_path}")


if __name__ == "__main__":
    main()
