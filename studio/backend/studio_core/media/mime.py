"""What content type a stored file is given.

## Why this exists

`content_type` on a file's row is what the app decides by: the run feed
offers *Copy into a character or location…* only on an `image/*`, the CLI's
`--from-run` resolves images by extension, and a tile draws whatever the
browser sniffs. Three places wrote that value with
`mimetypes.guess_type(name)[0] or "application/octet-stream"`, and on the
Lambda that line types every `.webp` as `application/octet-stream`.

**Python 3.11's built-in table has no `.webp`.** It has `.avif`, and it has
`.webp` from 3.13 — but not here. On a developer's Mac the gap is invisible,
because `mimetypes` also reads `/etc/apache2/mime.types` at import and that
file lists it; the Lambda image reads nothing of the kind. Measured: 47
gpt-image-2.5 outputs in prod stored `application/octet-stream` between
2026-09-08 and 2026-09-21, and the copy-into button gone from every one.

## The rule

1. **What the provider served, when it names a media type.** Replicate,
   fal and OpenRouter send `image/webp`, `video/mp4` and so on with the
   bytes, and that is the type *measured when the bytes landed* — the
   promise `isPromotable` makes in the frontend. Trusted only for `image/`,
   `video/` and `audio/`: a bucket behind a Runpod worker answers
   `application/octet-stream` or S3's own `binary/octet-stream`, and an
   expired-link interstitial answers `text/html`, and neither is the file.
2. **Else the extension**, with `.webp` registered so the table is the same
   on every machine.
3. **Else `application/octet-stream`** — a `.safetensors` is not a media
   file and is stored as one.
"""

from __future__ import annotations

import mimetypes

#: Registered once, at import, on top of whatever the platform's table holds.
#: `add_type` is idempotent, and a platform that already knows `.webp` maps
#: it the same way.
mimetypes.add_type("image/webp", ".webp")

#: **Audio, for the same reason and with one difference.** A voice sample is
#: a stored file like any other and its type decides whether a browser will
#: play it: an `<audio>` element handed `application/octet-stream` shows a
#: dead control. The Lambda's table knows `.mp3` and nothing else here, so the
#: rest would each be an octet-stream — the `.webp` failure, one media type
#: over.
#:
#: The difference is that two of these OVERRIDE a platform answer rather than
#: filling a hole. A Mac's `/etc/apache2/mime.types` calls a `.wav`
#: `audio/x-wav` and an `.m4a` `audio/mp4a-latm`, both of them the pre-standard
#: spellings, and Safari will not play the second. Registering the current
#: names means a file uploaded on a laptop and the same file uploaded through
#: the deployed API are stored under one type.
for _suffix, _type in (
    (".mp3", "audio/mpeg"),
    (".wav", "audio/wav"),
    (".m4a", "audio/mp4"),
    (".aac", "audio/aac"),
    (".flac", "audio/flac"),
    (".ogg", "audio/ogg"),
    (".opus", "audio/ogg"),
):
    mimetypes.add_type(_type, _suffix)

OCTET_STREAM = "application/octet-stream"

#: The top-level types a provider's `Content-Type` is believed for.
MEDIA = frozenset({"image", "video", "audio"})


def served_type(header: str | None) -> str | None:
    """The bare media type in a `Content-Type` header, or None when it names
    none: parameters dropped, lower-cased, refused unless its top level is a
    media type — see the module docstring for what the refused ones are."""
    if not header:
        return None
    bare = header.split(";", 1)[0].strip().lower()
    if bare.split("/", 1)[0] not in MEDIA:
        return None
    return bare


def content_type_of(name: str, served: str | None = None) -> str:
    """The content type a file called `name` is stored under. `served` is the
    `Content-Type` the bytes arrived with, when they arrived over HTTP."""
    return served_type(served) or mimetypes.guess_type(name)[0] or OCTET_STREAM
