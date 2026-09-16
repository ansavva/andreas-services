"""Move an MP4's `moov` atom in front of its `mdat`, so a browser can start it
without downloading it.

## Why this exists

Every video in the app is a bare `<video>` over a presigned URL, and a
browser can do nothing with an MP4 until it has the index — the `moov` atom,
which says where every frame is. Every provider here (Replicate, Runpod, fal)
writes its MP4 with `mdat` first and `moov` LAST, so nothing could start —
a hover preview, an autoplay slot, the lightbox — until the whole file was
down. Found while measuring the runs wall, where 48 clips in view pulled
~290 MB and every other request on the page queued behind them.

With `moov` first the index is the first thing read, so playback — a hover
preview, an autoplay slot, the lightbox — starts after the first range
rather than after the last. **What this does not do is shrink the poster's
cost in Chrome**, and that was measured too, against a streaming server that
counts what it actually sent: 288 MB for 48 `moov`-last clips, 281 MB for
the same clips `moov`-first. Chrome's `preload="metadata"` reads ahead by
megabytes whatever the atom order, which on a 6 MB clip is the file. The
poster has to come from somewhere other than the clip — a still per clip,
which is the next change; this one is what makes a clip start instantly
once it is asked to play, and it halves the request count on the way.

## Why it is pure Python, and here

`ffmpeg -movflags +faststart` does this, and the API image has no ffmpeg on
purpose (`media/imaging.py` says why: 80 MB for every folder listing). The
operation itself is small — walk the top-level atoms, copy `moov` forward,
add its size to every chunk offset it holds — and it is the same one
`qt-faststart` has performed since 2006. So it runs where the bytes already
are: in the callback consumer, on the file `generate._store_output` has just
downloaded and is about to upload. No second image, no queue, no round trip.

## What it will and will not touch

* An MP4 whose `moov` already precedes `mdat`: untouched, `False`.
* Anything that does not parse as a sequence of MP4 atoms, a `moov` holding a
  compressed `cmov`, a 32-bit offset table that would overflow once shifted:
  untouched, `False`. **A refusal is not a failure** — the clip plays either
  way, it just costs more to draw; and this runs inside a callback that has
  just spent money, where an exception would redrive a paid generation to the
  dead-letter queue over an index.
* The file is rewritten in place through a sibling temp file and an atomic
  rename; a crash leaves the original.

Streaming throughout: `moov` is read whole (it is kilobytes), everything else
is copied in chunks, so a 200 MB clip does not need 200 MB of Lambda memory.
"""
from __future__ import annotations

import logging
import os
import struct
import tempfile

logger = logging.getLogger(__name__)

# Containers whose children may hold chunk-offset tables. `qt-faststart` walks
# the same four; anything else inside `moov` is copied as opaque bytes.
_CONTAINERS = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl"})
_COPY_CHUNK = 1 << 20


class _Atom:
    __slots__ = ("kind", "offset", "size", "header")

    def __init__(self, kind: bytes, offset: int, size: int, header: int) -> None:
        self.kind = kind
        self.offset = offset  # where the atom starts, header included
        self.size = size  # whole atom, header included
        self.header = header  # 8, or 16 for a 64-bit size


def _top_level(path: str) -> list[_Atom] | None:
    """The file's top-level atoms in order, or `None` if it is not an MP4."""
    atoms: list[_Atom] = []
    total = os.path.getsize(path)
    with open(path, "rb") as fh:
        offset = 0
        while offset < total:
            fh.seek(offset)
            head = fh.read(8)
            if len(head) < 8:
                return None
            size, kind = struct.unpack(">I4s", head)
            header = 8
            if size == 1:
                large = fh.read(8)
                if len(large) < 8:
                    return None
                size = struct.unpack(">Q", large)[0]
                header = 16
            elif size == 0:
                size = total - offset  # "to the end of the file"
            if size < header or offset + size > total:
                return None
            atoms.append(_Atom(kind, offset, size, header))
            offset += size
    return atoms if atoms else None


def _shift_offsets(moov: bytearray, start: int, end: int, delta: int) -> bool:
    """Add `delta` to every `stco`/`co64` entry under `moov[start:end]`, in
    place. `False` if a 32-bit table would overflow, or the atom does not
    parse — the caller then leaves the file alone."""
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack_from(">I4s", moov, pos)
        header = 8
        if size == 1:
            if pos + 16 > end:
                return False
            size = struct.unpack_from(">Q", moov, pos + 8)[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return False
        body = pos + header
        if kind == b"cmov":
            return False
        if kind in _CONTAINERS:
            if not _shift_offsets(moov, body, pos + size, delta):
                return False
        elif kind in (b"stco", b"co64"):
            # version(1) flags(3) count(4), then the table.
            if body + 8 > pos + size:
                return False
            count = struct.unpack_from(">I", moov, body + 4)[0]
            width = 4 if kind == b"stco" else 8
            table = body + 8
            if table + count * width > pos + size:
                return False
            fmt = ">I" if width == 4 else ">Q"
            for i in range(count):
                at = table + i * width
                value = struct.unpack_from(fmt, moov, at)[0] + delta
                if width == 4 and value > 0xFFFFFFFF:
                    return False
                struct.pack_into(fmt, moov, at, value)
        pos += size
    return True


def needs_faststart(path: str) -> bool:
    """Whether `moov` sits after `mdat` — the shape every provider writes."""
    atoms = _top_level(path)
    if not atoms:
        return False
    kinds = [atom.kind for atom in atoms]
    if b"moov" not in kinds or b"mdat" not in kinds:
        return False
    return kinds.index(b"moov") > kinds.index(b"mdat")


def faststart(path: str) -> bool:
    """Rewrite `path` in place with `moov` before `mdat`. `True` if it did.

    The new order is: everything that preceded `mdat` in the original
    (`ftyp`, a stray `free`), then `moov`, then the rest with `moov` taken
    out. Every atom from `mdat` on moves forward by exactly `moov`'s size,
    which is the number added to every chunk offset.
    """
    atoms = _top_level(path)
    if not atoms:
        return False
    kinds = [atom.kind for atom in atoms]
    if b"moov" not in kinds or b"mdat" not in kinds:
        return False
    moov_at = kinds.index(b"moov")
    mdat_at = kinds.index(b"mdat")
    if moov_at < mdat_at:
        return False
    moov = atoms[moov_at]

    with open(path, "rb") as fh:
        fh.seek(moov.offset)
        body = bytearray(fh.read(moov.size))
    if len(body) != moov.size:
        return False
    if not _shift_offsets(body, moov.header, moov.size, moov.size):
        logger.info("faststart: leaving %s alone (offsets would not shift cleanly)", path)
        return False

    # Everything before `mdat` keeps its place; `moov` goes in just ahead of
    # `mdat`; then everything from `mdat` on, minus the old `moov`.
    order = [a for a in atoms[:mdat_at] if a.kind != b"moov"]
    tail = [a for a in atoms[mdat_at:] if a.kind != b"moov"]

    directory = os.path.dirname(path) or "."
    handle, staged = tempfile.mkstemp(prefix="faststart-", dir=directory)
    try:
        with os.fdopen(handle, "wb") as out, open(path, "rb") as src:
            for atom in order:
                _copy(src, out, atom.offset, atom.size)
            out.write(body)
            for atom in tail:
                _copy(src, out, atom.offset, atom.size)
        os.replace(staged, path)
    except BaseException:
        if os.path.exists(staged):
            os.remove(staged)
        raise
    return True


def _copy(src, out, offset: int, size: int) -> None:
    src.seek(offset)
    remaining = size
    while remaining > 0:
        chunk = src.read(min(_COPY_CHUNK, remaining))
        if not chunk:
            raise OSError("file shrank while it was being rewritten")
        out.write(chunk)
        remaining -= len(chunk)


def is_mp4_name(name: str) -> bool:
    """Whether a filename says MP4-family — the containers this applies to."""
    return name.lower().endswith((".mp4", ".m4v", ".mov"))
