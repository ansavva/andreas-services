"""The ffmpeg layer shared by scenes, movies and frame extraction.

`probe`/`stitch` lived in `scenes.py` and `duration`/`grab` lived in
`frames.py`, each with its own copy of the duration regex. A **movie** stitches
scenes exactly the way a scene stitches shots, so the joining rules belong in
one place rather than being reimplemented one tier up.

ffmpeg comes from the `imageio-ffmpeg` wheel, so no system install is required.
Any entry script importing this must declare `imageio-ffmpeg` in its PEP 723
block.

STITCHING RULE
--------------
When every input already agrees on codec, dimensions, frame rate and audio
layout, the concat demuxer runs with `-c copy`: no re-encode, so the cut is
bit-for-bit the sources joined end to end. When they differ, inputs are
normalised to the FIRST input's video geometry and a common audio layout — and
the caller records that it happened, rather than doing it silently.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile

from studio_pipeline.errors import die

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


_DUR = re.compile(r"Duration: (\d+):(\d+):([\d.]+)")
_VID = re.compile(r"Video: (\w+).*?, (\d+)x(\d+).*?, ([\d.]+) (?:fps|tbr)")
_AUD = re.compile(r"Audio: (\w+).*?, (\d+) Hz, (\w+)")


def _report(path: str) -> str:
    return subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path],
                          capture_output=True, text=True).stderr


def probe(path: str) -> dict:
    """Codec / geometry / audio layout, read off ffmpeg's own report."""
    txt = _report(path)
    out: dict = {"duration": None, "video": None, "audio": None}
    if (m := _DUR.search(txt)):
        h, mi, s = m.groups()
        out["duration"] = round(int(h) * 3600 + int(mi) * 60 + float(s), 2)
    if (m := _VID.search(txt)):
        c, w, h, fps = m.groups()
        out["video"] = {"codec": c, "width": int(w), "height": int(h), "fps": float(fps)}
    if (m := _AUD.search(txt)):
        c, rate, layout = m.groups()
        out["audio"] = {"codec": c, "sample_rate": int(rate), "layout": layout}
    if not out["video"]:
        die(f"{path}: no video stream found")
    return out


def duration(path: str) -> float:
    txt = _report(path)
    m = _DUR.search(txt)
    if not m:
        die(f"{path}: could not read duration")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _shape(p: dict) -> tuple:
    v, a = p["video"], p["audio"]
    return (v["codec"], v["width"], v["height"], round(v["fps"], 3),
            (a or {}).get("codec"), (a or {}).get("sample_rate"), (a or {}).get("layout"))


def stitch(paths: list[str], dest: str, *, label: str = "parts") -> dict:
    """Join clips end to end. Stream-copies when the inputs already agree.

    `label` names the inputs in the returned method string and in the
    `uniform_<label>` flag, so a scene says "shots" and a movie says "scenes".
    """
    probes = [probe(p) for p in paths]
    uniform = len({_shape(p) for p in probes}) == 1
    have_audio = all(p["audio"] for p in probes)
    if not have_audio and any(p["audio"] for p in probes):
        # Mixed audio/no-audio cannot stream-copy through the concat demuxer.
        uniform = False

    listfile = os.path.join(os.path.dirname(dest), "_concat.txt")
    with open(listfile, "w") as fh:
        for p in paths:
            fh.write(f"file '{os.path.abspath(p)}'\n")

    base = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", listfile]
    if uniform:
        cmd = base + ["-c", "copy", dest, "-y"]
        method = "concat demuxer, stream copy (no re-encode)"
    else:
        v = probes[0]["video"]
        cmd = base + [
            "-vf", f"scale={v['width']}:{v['height']}:force_original_aspect_ratio=decrease,"
                   f"pad={v['width']}:{v['height']}:-1:-1,fps={v['fps']}",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        ]
        cmd += (["-c:a", "aac", "-ar", "44100", "-ac", "2"] if have_audio else ["-an"])
        cmd += [dest, "-y"]
        method = (f"re-encoded to {v['width']}x{v['height']} @ {v['fps']}fps "
                  f"({label} differed)")

    subprocess.run(cmd, check=True)
    os.remove(listfile)
    return {"method": method, f"uniform_{label}": uniform, "probes": probes}


def grab(src: str, when: float | None, dest: str, from_end: float | None = None) -> str:
    """One frame, either at an absolute time or measured back from the end."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error"]
    if from_end is not None:
        cmd += ["-sseof", f"-{from_end}"]
    elif when is not None:
        cmd += ["-ss", f"{when}"]
    cmd += ["-i", src, "-frames:v", "1", "-update", "1", "-q:v", "2", dest, "-y"]
    subprocess.run(cmd, check=True)
    return dest


def contact_grid(src: str, count: int, dest: str, width: int = 900) -> list[float]:
    """Sample `count` frames across the clip and tile them into one image."""
    dur = duration(src)
    # Inset from both ends: the very first and last frames are the least
    # informative part of a clip.
    times = [dur * (i + 0.5) / count for i in range(count)]
    tmp = tempfile.mkdtemp(prefix="grid-")
    for i, t in enumerate(times, 1):
        grab(src, t, os.path.join(tmp, f"f{i:02d}.png"))
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                    "-i", os.path.join(tmp, "f%02d.png"),
                    "-vf", f"tile={cols}x{rows},scale={width}:-1",
                    "-frames:v", "1", "-q:v", "3", dest, "-y"], check=True)
    return times
