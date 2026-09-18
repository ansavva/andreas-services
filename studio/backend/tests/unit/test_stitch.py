"""`media/ffmpeg.stitch`: the encode itself, on synthetic clips.

`test_render.py` patches `stitch` and checks its report reaches the record.
This is the other half — what the binary is actually told, and what comes out
— because a cut that froze for twelve seconds in prod on 2026-09-18 had a
report saying `re-encoded to 1280x720 @ 24.0fps (shots differed)` and a file
that played. Nothing had run the encode on inputs that disagree.

Two layers, so the graph is checked on every PR whether or not a binary is
around:

* **The filter graph as a string** — no ffmpeg needed. Every input gets its own
  conform chain, the odd frame rate gets `fps=`, and the join is the concat
  FILTER, never the demuxer.
* **The encode** — skipped where `imageio-ffmpeg` is not installed. The render
  group is optional in `pyproject.toml` and `studio-pr.yml` installs it for
  this. Clips are `testsrc2` (it moves every frame, so a held frame is a
  detectable freeze) at 24 and 30 fps on DIFFERENT track timescales, which is
  the shape of a Kling clip beside a Wan clip and the shape that froze.
"""

import os
import subprocess

import pytest

from studio_core.media import ffmpeg

P24 = {"duration": 4.0, "video": {"codec": "h264", "width": 1280, "height": 720, "fps": 24.0},
       "audio": {"codec": "aac", "sample_rate": 44100, "layout": "stereo"}}
P30 = {"duration": 4.0, "video": {"codec": "h264", "width": 1280, "height": 720, "fps": 30.0},
       "audio": {"codec": "aac", "sample_rate": 44100, "layout": "stereo"}}
P30_SMALL = {"duration": 4.0,
             "video": {"codec": "h264", "width": 1284, "height": 716, "fps": 30.0},
             "audio": {"codec": "aac", "sample_rate": 44100, "layout": "stereo"}}


# --- the graph, as a string ------------------------------------------------


def test_every_input_is_conformed_on_its_own_branch_before_the_concat_filter():
    graph = ffmpeg.conform_filter([P24, P30, P24], have_audio=True)
    chains = graph.split(";")
    # Three video branches, three audio branches, one join.
    assert [c[:5] for c in chains] == ["[0:v]", "[0:a]", "[1:v]", "[1:a]", "[2:v]", "[2:a]",
                                       "[v0]["]
    assert chains[-1] == "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]"
    for c in chains[::2][:3]:
        assert "scale=1280:720" in c and "setsar=1" in c and "format=yuv420p" in c
    for c in chains[1::2][:3]:
        assert c.endswith("aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"
                          f"[a{chains.index(c) // 2}]")


def test_the_target_frame_rate_is_the_first_inputs_and_only_the_odd_one_is_resampled():
    graph = ffmpeg.conform_filter([P24, P30, P24], have_audio=True)
    chains = graph.split(";")
    assert "fps=" not in chains[0]      # already 24
    assert "fps=24," in chains[2]       # the 30 fps clip, brought to 24
    assert "fps=" not in chains[4]
    # And the other way round: a cut led by a 30 fps clip goes to 30.
    graph = ffmpeg.conform_filter([P30, P24], have_audio=True)
    assert "fps=30," in graph.split(";")[2] and "fps=" not in graph.split(";")[0]


def test_a_size_mismatch_is_padded_to_the_first_inputs_frame():
    graph = ffmpeg.conform_filter([P24, P30_SMALL], have_audio=True)
    assert "scale=1280:720:force_original_aspect_ratio=decrease" in graph.split(";")[2]
    assert "pad=1280:720:-1:-1" in graph.split(";")[2]


def test_without_audio_the_join_carries_video_only():
    graph = ffmpeg.conform_filter([P24, P30], have_audio=False)
    assert ":a]" not in graph
    assert graph.endswith("[v0][v1]concat=n=2:v=1:a=0[v]")


def test_the_report_says_what_the_inputs_disagreed_on():
    assert ffmpeg._differs([P24, P30, P24]) == ["fps 24/30"]
    assert ffmpeg._differs([P24, P30_SMALL]) == ["size 1280x720/1284x716", "fps 24/30"]
    assert ffmpeg._differs([P24, {**P24, "audio": None}]) == ["audio aac 44100Hz stereo/none"]
    assert ffmpeg._differs([P24, P24]) == []


def test_a_mixed_cut_is_joined_by_the_concat_filter_not_the_demuxer(monkeypatch, tmp_path):
    """The command `stitch` builds for a mixed cut, with the binary stood in for."""
    ran: list[list[str]] = []
    monkeypatch.setattr(ffmpeg, "ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg, "probe", lambda p: P30 if "b" in os.path.basename(p) else P24)
    monkeypatch.setattr(ffmpeg, "_run", lambda cmd, what: ran.append(cmd))

    report = ffmpeg.stitch(["/x/a.mp4", "/x/b.mp4"], str(tmp_path / "out.mp4"), label="shots")

    cmd = ran[0]
    assert "concat" not in cmd[:cmd.index("-filter_complex")], "the demuxer is the bug"
    assert cmd[cmd.index("-i") + 1] == "/x/a.mp4"
    assert cmd[cmd.index("-filter_complex") + 1] == ffmpeg.conform_filter([P24, P30],
                                                                          have_audio=True)
    assert cmd[cmd.index("-map") + 1] == "[v]"
    assert "-b:a" in cmd and "-movflags" in cmd
    assert report["uniform_shots"] is False
    assert report["method"] == ("re-encoded to 1280x720 @ 24fps (the first shot's), each shot "
                                "conformed before the join (shots differed: fps 24/30)")
    assert not (tmp_path / "_concat.txt").exists()


def test_a_uniform_cut_still_stream_copies_through_the_demuxer(monkeypatch, tmp_path):
    ran: list[list[str]] = []
    monkeypatch.setattr(ffmpeg, "ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg, "probe", lambda p: P24)
    monkeypatch.setattr(ffmpeg, "_run", lambda cmd, what: ran.append(cmd))

    report = ffmpeg.stitch(["/x/a.mp4", "/x/b.mp4"], str(tmp_path / "out.mp4"), label="scenes")

    assert ran[0][ran[0].index("-f") + 1] == "concat"
    assert ran[0][ran[0].index("-c") + 1] == "copy"
    assert "-filter_complex" not in ran[0]
    assert report["method"] == "concat demuxer, stream copy (no re-encode)"
    assert report["uniform_scenes"] is True


# --- the encode ------------------------------------------------------------


@pytest.fixture
def exe():
    pytest.importorskip("imageio_ffmpeg",
                        reason="the render group is not installed: "
                               "`poetry install --with render`")
    return ffmpeg.ffmpeg_exe()


def clip(exe, dest, *, fps, size="640x360", seconds=2, timescale=None, audio=True):
    """A moving test pattern with a tone, encoded the way a provider clip is."""
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if timescale:
        cmd += ["-video_track_timescale", str(timescale)]
    cmd += (["-c:a", "aac", "-ar", "44100", "-ac", "2"] if audio else ["-an"])
    cmd += [str(dest)]
    subprocess.run(cmd, check=True)
    return str(dest)


def freezes(exe, path, *, at_least=0.5) -> list[str]:
    """`freezedetect` marks, as ffmpeg prints them. Empty is the healthy answer."""
    err = subprocess.run(
        [exe, "-hide_banner", "-i", path, "-vf", f"freezedetect=n=0.003:d={at_least}",
         "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return [line for line in err.splitlines() if "freeze_start" in line]


def test_a_24_and_30_fps_cut_on_different_timescales_plays_through(exe, tmp_path):
    """The prod shape: 24 fps clips around a 30 fps one whose track timescale
    differs. Through the demuxer this froze on the 30 fps clip's first frame
    for its whole length; through the filter it plays."""
    parts = [clip(exe, tmp_path / "a.mp4", fps=24, timescale=12288),
             clip(exe, tmp_path / "b.mp4", fps=30, timescale=90000),
             clip(exe, tmp_path / "c.mp4", fps=24, timescale=12288)]
    out = str(tmp_path / "out.mp4")

    report = ffmpeg.stitch(parts, out, label="shots")

    assert freezes(exe, out) == []
    probe = ffmpeg.probe(out)
    assert abs(probe["duration"] - 6.0) < 0.3
    assert report["uniform_shots"] is False
    assert report["method"].startswith("re-encoded to 640x360 @ 24fps (the first shot's)")
    assert "fps 24/30" in report["method"]
    assert (probe["video"]["width"], probe["video"]["height"]) == (640, 360)
    assert probe["audio"]["layout"] == "stereo"


def test_a_size_and_rate_mismatch_lands_on_the_first_clips_frame(exe, tmp_path):
    parts = [clip(exe, tmp_path / "a.mp4", fps=24),
             clip(exe, tmp_path / "b.mp4", fps=30, size="644x356", timescale=15360)]
    out = str(tmp_path / "out.mp4")

    report = ffmpeg.stitch(parts, out, label="shots")

    assert freezes(exe, out) == []
    probe = ffmpeg.probe(out)
    assert (probe["video"]["width"], probe["video"]["height"]) == (640, 360)
    assert abs(probe["duration"] - 4.0) < 0.3
    assert "size 640x360/644x356" in report["method"] and "fps 24/30" in report["method"]


def test_a_silent_clip_beside_a_voiced_one_re_encodes_without_audio(exe, tmp_path):
    parts = [clip(exe, tmp_path / "a.mp4", fps=24),
             clip(exe, tmp_path / "b.mp4", fps=24, audio=False)]
    out = str(tmp_path / "out.mp4")

    report = ffmpeg.stitch(parts, out, label="shots")

    assert report["uniform_shots"] is False
    assert "audio aac 44100Hz stereo/none" in report["method"]
    assert freezes(exe, out) == []
    assert ffmpeg.probe(out)["audio"] is None


def test_clips_that_agree_are_stream_copied(exe, tmp_path):
    parts = [clip(exe, tmp_path / "a.mp4", fps=24), clip(exe, tmp_path / "b.mp4", fps=24)]
    out = str(tmp_path / "out.mp4")

    report = ffmpeg.stitch(parts, out, label="shots")

    assert report["method"] == "concat demuxer, stream copy (no re-encode)"
    assert report["uniform_shots"] is True
    assert abs(ffmpeg.probe(out)["duration"] - 4.0) < 0.1
