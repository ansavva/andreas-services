"""The ffmpeg layer shared by scenes, movies and frame extraction.

Moved verbatim in behaviour from `pipeline/src/studio_pipeline/adapters/ffmpeg.py`,
which said this about itself and still applies:

    `probe`/`stitch` lived in `scenes.py` and `duration`/`grab` lived in
    `frames.py`, each with its own copy of the duration regex. A **movie**
    stitches scenes exactly the way a scene stitches shots, so the joining rules
    belong in one place rather than being reimplemented one tier up.

ffmpeg comes from the `imageio-ffmpeg` wheel, so no system install is required —
which is what makes the render image a `pip install` rather than a build of
ffmpeg from source. It is in the `render` dependency group, so **the API image
does not have it**: importing this module there raises, and that is the intended
shape rather than an accident. `services/render.py` imports it lazily for the
same reason.

STITCHING RULE — THE ONE THING THAT MUST NOT BE LOST IN THE MOVE
----------------------------------------------------------------
When every input already agrees on codec, dimensions, frame rate and audio
layout, the concat demuxer runs with `-c copy`: no re-encode, so the cut is
bit-for-bit the sources joined end to end. When they differ, inputs are
normalised to the FIRST input's video geometry and a common audio layout — **and
the caller records that it happened**, rather than doing it silently.

That last clause is the reason `stitch` returns a report instead of a path.
`services/render.py` writes it onto the scene or movie record as `stitch`, so a
person looking at a cut can see whether it was joined or re-encoded and to what.
A worker that re-encoded silently would be a quality regression nobody could
see, and nobody would think to look for it because the file plays.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile

#: What a scene or a movie may be cut from. Shared with `services/render.py`
#: rather than restated, so a new container format is legal in both at once.
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")


class MediaError(RuntimeError):
    """This file cannot be processed, and trying again will not change that.

    Distinct from a transient failure on purpose: `services/render.py` closes a
    job `failed` on one of these and lets everything else raise, so SQS redrives
    a throttled DynamoDB write and does **not** redrive a clip with no video
    stream in it. The CLI's `die()` occupied this position and could only exit a
    process, which is exactly the thing that does not translate to a worker.
    """


def ffmpeg_exe() -> str:
    """Path to the bundled binary. Imported here so the API image can import this
    module's *name* without holding the wheel — see the note above."""
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


_DUR = re.compile(r"Duration: (\d+):(\d+):([\d.]+)")
_VID = re.compile(r"Video: (\w+).*?, (\d+)x(\d+).*?, ([\d.]+) (?:fps|tbr)")
_AUD = re.compile(r"Audio: (\w+).*?, (\d+) Hz, (\w+)")


def _report(path: str) -> str:
    return subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True
    ).stderr


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
        raise MediaError(f"{os.path.basename(path)}: no video stream found")
    return out


def duration(path: str) -> float:
    txt = _report(path)
    m = _DUR.search(txt)
    if not m:
        raise MediaError(f"{os.path.basename(path)}: could not read duration")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def _shape(p: dict) -> tuple:
    v, a = p["video"], p["audio"]
    return (
        v["codec"], v["width"], v["height"], round(v["fps"], 3),
        (a or {}).get("codec"), (a or {}).get("sample_rate"), (a or {}).get("layout"),
    )


def _run(cmd: list[str], what: str) -> None:
    """One ffmpeg invocation, with its stderr carried into the failure.

    **`check=True` alone loses the only useful thing.** In the CLI a failed
    encode printed ffmpeg's own diagnosis to the terminal the person was already
    looking at; in a worker it goes to a subprocess nobody sees, and
    `CalledProcessError: returned non-zero exit status 1` is what lands on the
    render row. So stderr is captured and its tail becomes the message.
    """
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        tail = (done.stderr or "").strip().splitlines()[-6:]
        raise MediaError(f"{what} failed: " + " / ".join(tail) if tail else f"{what} failed")


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

    _run(cmd, "stitch")
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
    _run(cmd, "frame grab")
    if not os.path.exists(dest) or not os.path.getsize(dest):
        # ffmpeg exits 0 having written nothing when the seek lands past the end
        # of the clip, which is what `--time` beyond the duration does. In the
        # CLI the empty file was visible in the directory the person named; here
        # it would be uploaded as a zero-byte node.
        raise MediaError("no frame at that position — the clip is shorter than the seek")
    return dest


def contact_grid(src: str, count: int, dest: str, width: int = 900) -> list[float]:
    """Sample `count` frames across the clip and tile them into one image."""
    dur = duration(src)
    # Inset from both ends: the very first and last frames are the least
    # informative part of a clip.
    times = [dur * (i + 0.5) / count for i in range(count)]
    tmp = tempfile.mkdtemp(prefix="grid-", dir=os.path.dirname(dest))
    for i, t in enumerate(times, 1):
        grab(src, t, os.path.join(tmp, f"f{i:02d}.png"))
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    _run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
          "-i", os.path.join(tmp, "f%02d.png"),
          "-vf", f"tile={cols}x{rows},scale={width}:-1",
          "-frames:v", "1", "-q:v", "3", dest, "-y"], "contact grid")
    return times
