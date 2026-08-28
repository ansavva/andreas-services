#!/usr/bin/env python3
"""Split a contact-sheet of poses into one image per pose.

A pose sheet — several figures laid out in a grid on a flat background — is
useless as a model input whole: passing it asks the model to match ten poses at
once. This cuts it into one plate per figure, which is what a turnaround
binds per slot.

The cut is measured, not hand-tuned. Figures are found by projecting "pixels
that differ from the background" onto each axis: bands of non-empty rows are the
sheet's rows, and within each row band, bands of non-empty columns are the
figures. So the same sheet always yields the same boxes, and a differently-laid-
out sheet still works — nothing here assumes a count, an even spacing, or which
of the subject and the background is the darker. Captioned sheets work too: a
label forms its own row band and is discarded for being far too short to be a
figure.

    uv run python scripts/split_pose_sheet.py sheet.jpg --out /tmp/plates
    uv run python scripts/split_pose_sheet.py sheet.jpg --out /tmp/plates --report

Output is `<row>-<n>.png`, numbered left to right, top row first. Naming them for
what they SHOW is a judgement call made by eye afterwards — the point of this
script is the geometry.

Naming the output is a judgement call made by eye against the sheet's own
captions, which is why this writes `<row>-<n>.png` and stops there. Where the
plates end up, and under what names, is a separate and gated step — see
studio/config/README.md.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

from PIL import Image

# How far from the background a pixel must sit to count as subject. Measured as
# an ABSOLUTE difference, so the same code reads light figures on a dark ground
# and dark figures on a light one — the two sheets in use are one of each, and
# hard-coding the polarity would mean a second script.
THRESHOLD_MARGIN = 25
# A caption strip is non-background too, so it forms its own row band. It is an
# order of magnitude shorter than a figure, which is what tells them apart:
# anything under this fraction of the tallest band is a label, not a subject.
MIN_ROW_FRACTION = 0.4
# Ignore bands thinner than this: a stray highlight is not a figure.
MIN_BAND = 10
# Breathing room around each figure, so a plate is not cropped tight to the skin.
PAD = 8


def _bands(counts: list[int], min_len: int = MIN_BAND, floor: int = 1) -> list[tuple[int, int]]:
    """Runs of indices whose count is at or above `floor`, longer than `min_len`."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, n in enumerate(counts):
        if n >= floor and start is None:
            start = i
        elif n < floor and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    if start is not None and len(counts) - start >= min_len:
        out.append((start, len(counts)))
    return out


def find_figures(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of every figure on the sheet, reading order."""
    grey = image.convert("L")
    width, height = grey.size
    px = grey.load()

    sample = [px[x, y] for y in range(0, height, 7) for x in range(0, width, 7)]
    background = statistics.median(sample)

    def subject(x: int, y: int) -> bool:
        return abs(px[x, y] - background) > THRESHOLD_MARGIN

    rows = [sum(1 for x in range(width) if subject(x, y)) for y in range(height)]
    bands = _bands(rows)
    if bands:
        tallest = max(b - a for a, b in bands)
        bands = [(a, b) for a, b in bands if (b - a) >= tallest * MIN_ROW_FRACTION]
    boxes: list[tuple[int, int, int, int]] = []
    for top, bottom in bands:
        cols = [sum(1 for y in range(top, bottom) if subject(x, y))
                for x in range(width)]
        for left, right in _bands(cols):
            boxes.append((
                max(0, left - PAD), max(0, top - PAD),
                min(width, right + PAD), min(height, bottom + PAD),
            ))
    return boxes


def split(path: str, out_dir: str, report: bool = False) -> list[str]:
    image = Image.open(path)
    boxes = find_figures(image)
    if not boxes:
        print(f"error: found no figures in {path} — is it a pose sheet?", file=sys.stderr)
        raise SystemExit(1)

    os.makedirs(out_dir, exist_ok=True)
    # Group boxes back into rows so the filenames say which row a plate came from.
    # Tops within a tolerance are the same row; a bigger jump starts the next one.
    ROW_TOLERANCE = 40
    rows: dict[int, int] = {}
    row_no, previous = 0, None
    for top in sorted({box[1] for box in boxes}):
        if previous is None or top - previous > ROW_TOLERANCE:
            row_no += 1
        rows[top] = row_no
        previous = top

    written = []
    seen: dict[int, int] = {}
    for box in boxes:
        row = rows[box[1]]
        seen[row] = seen.get(row, 0) + 1
        dest = os.path.join(out_dir, f"{row}-{seen[row]}.png")
        image.crop(box).save(dest)
        written.append(dest)
        if report:
            print(f"{os.path.basename(dest)}  box={box}  "
                  f"size={box[2] - box[0]}x{box[3] - box[1]}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet", help="The pose sheet image.")
    ap.add_argument("--out", required=True, help="Directory to write the plates into.")
    ap.add_argument("--report", action="store_true", help="Print each box as it is written.")
    args = ap.parse_args()

    written = split(args.sheet, args.out, args.report)
    print(f"{len(written)} plate(s) -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
