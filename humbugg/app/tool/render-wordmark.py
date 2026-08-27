#!/usr/bin/env python3
"""Render the Humbugg wordmark as the Cognito Managed Login form logo.

The hosted pages cannot use a webfont and a CSS class the way the marketing
site does — Cognito takes an image asset or nothing. This renders the same
wordmark the site sets in CSS (`.brand-wordmark`: Lily Script One, #1d5545)
into a transparent PNG the branding resource uploads.

Run it only when the wordmark itself changes. The output is committed, so a
normal checkout needs neither the font nor Pillow:

    pip install pillow
    curl -sSLo /tmp/LilyScriptOne-Regular.ttf \
      https://github.com/google/fonts/raw/main/ofl/lilyscriptone/LilyScriptOne-Regular.ttf
    python3 humbugg/app/tool/render-wordmark.py /tmp/LilyScriptOne-Regular.ttf

Lily Script One is OFL-1.1. It is NOT vendored here: the repo needs the
rendered artwork, not the ability to set arbitrary text in the face.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEXT = "Humbugg"
# `primary` from app/src/theme/brand-colors.json. Kept as a literal because
# this runs by hand, and a colour that disagrees with the JSON should be
# visible in the diff rather than resolved silently at render time.
INK = (0x1D, 0x55, 0x45, 255)
# Large enough that the form logo stays crisp on a retina display; Cognito
# renders it a few hundred pixels wide.
SIZE = 400
PAD = 40
OUT = Path(__file__).resolve().parents[2] / "infra/modules/auth/assets/humbugg-wordmark.png"


def main(font_path: str) -> None:
    font = ImageFont.truetype(font_path, SIZE)
    # The INK BOX, not the advance width: a script face overhangs its metrics
    # on both sides, and measuring by advance clips the H's flourish and the
    # final g's descender.
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), TEXT, font=font)

    image = Image.new("RGBA", ((right - left) + PAD * 2, (bottom - top) + PAD * 2), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((PAD - left, PAD - top), TEXT, font=font, fill=INK)
    image.save(OUT)
    print(f"wrote {OUT} ({image.width}x{image.height})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: render-wordmark.py <path-to-LilyScriptOne-Regular.ttf>")
    main(sys.argv[1])
