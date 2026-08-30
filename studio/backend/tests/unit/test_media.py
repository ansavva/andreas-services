"""`studio_core/media/` — the pure half of what used to be in the CLI's wheel.

Paths and bytes in, paths and bytes and reports out. Nothing here resolves a
node, reads a catalog row or signs a URL, which is what makes it testable without
mocking anything: the suite hands it real PNGs and reads the report back.

`ffmpeg.py` is deliberately **not** exercised here. It shells out to a binary
that only the render image carries, so a test of it would either need
`imageio-ffmpeg` installed in the API's dev environment — undoing the split this
change exists to make — or would assert the argv rather than the encode, which is
a test of a string. What is covered instead is the contract around it: that
`stitch` returns a report at all, and that `services/render.py` writes it onto
the record. See `test_render.py`.
"""

import io

import pytest
from PIL import Image

from studio_core.errors import ValidationError
from studio_core.media import imaging, sheet, workspace


def _png(width=400, height=600, mode="RGB"):
    buffer = io.BytesIO()
    Image.new(mode, (width, height), (10, 120, 200)).save(buffer, "PNG")
    return buffer.getvalue()


# ── imaging ────────────────────────────────────────────────────────────────


def test_a_box_of_the_wrong_length_says_how_many_it_got():
    with pytest.raises(ValidationError) as refusal:
        imaging.parse_box("1,2,3")
    assert "got 3" in str(refusal.value)


def test_width_and_height_instead_of_right_and_bottom_is_named_as_such():
    """The commonest way to get it wrong, because half the world's crop APIs take
    LEFT,TOP,WIDTH,HEIGHT and this one does not."""
    with pytest.raises(ValidationError) as refusal:
        imaging.parse_box("100,100,50,50")
    assert "not LEFT,TOP,WIDTH,HEIGHT" in str(refusal.value)


def test_a_box_over_the_edge_is_clamped_not_refused():
    """Padding a detection puts the box past the edge routinely; refusing would
    make every caller implement the clamp."""
    assert imaging.clamp((-20, -20, 500, 5000), 400, 600) == (0, 0, 400, 600)


def test_a_box_that_misses_the_image_entirely_is_refused():
    """That is a mistake, not a rounding."""
    with pytest.raises(ValidationError) as refusal:
        imaging.clamp((900, 900, 1000, 1000), 400, 600)
    assert "entirely outside" in str(refusal.value)


def test_converting_to_jpeg_drops_an_alpha_channel_rather_than_failing():
    """JPEG has no alpha, and Pillow raises rather than deciding for you.

    An RGBA source is the ordinary case — GPT Image writes transparent PNGs —
    so a conversion that refused them would refuse the thing the command exists
    for.
    """
    out = imaging.convert(_png(mode="RGBA"), ".jpg")
    assert Image.open(io.BytesIO(out)).mode == "RGB"


def test_a_crop_reports_the_box_it_actually_cut():
    """**The clamp is silent unless something says so**, and a box that is not
    the box anybody stated is exactly what a person needs told."""
    out, report = imaging.crop(_png(), (-10, 0, 4000, 600), ".png")

    assert Image.open(io.BytesIO(out)).size == (400, 600)
    assert report["clamped"] is True
    assert report["requested"] == [-10, 0, 4000, 600]
    assert report["box"] == [0, 0, 400, 600]


def test_a_crop_inside_the_image_is_not_reported_as_clamped():
    _out, report = imaging.crop(_png(), (100, 50, 300, 550), ".png")
    assert report["clamped"] is False
    assert (report["width"], report["height"]) == (200, 500)


def test_something_that_is_not_an_image_is_a_400_and_not_a_traceback():
    """`crop --run` against a run whose output is a video is the way here."""
    with pytest.raises(ValidationError):
        imaging.convert(b"\x00\x00\x00\x18ftypmp42", ".png")


# ── the contact sheet ──────────────────────────────────────────────────────


def test_a_sheet_without_captions_is_natural_sorted(tmp_path):
    """`_2` before `_10`. A pool listing's order, which is what browsing wants."""
    paths = []
    for n in (10, 2):
        path = tmp_path / f"subject-a_{n}.png"
        path.write_bytes(_png(30, 30))
        paths.append(str(path))

    report = sheet.build(paths, str(tmp_path / "sheet.png"), cols=2, cell=60)

    assert report["captions"] == ["subject-a_2", "subject-a_10"]


def test_given_captions_are_authoritative_and_the_order_is_left_alone(tmp_path):
    """**Tile N is what a prompt cites as `[ImageN]`.**

    A payload review's order IS its meaning, so natural-sorting it would renumber
    the citations the prompt makes — which is the one way a review sheet can be
    actively misleading rather than merely unhelpful.
    """
    paths = []
    for n in (10, 2):
        path = tmp_path / f"subject-a_{n}.png"
        path.write_bytes(_png(30, 30))
        paths.append(str(path))

    report = sheet.build(paths, str(tmp_path / "sheet.png"), cols=2, cell=60,
                         captions=["[Image1] ten", "[Image2] two"])

    assert report["captions"] == ["[Image1] ten", "[Image2] two"]


def test_one_unreadable_tile_does_not_lose_the_sheet(tmp_path):
    """It is drawn as an error where the image should be — right for somebody
    looking at the sheet — **and named in the report**, which is the half that
    reaches a terminal."""
    good = tmp_path / "good.png"
    good.write_bytes(_png(30, 30))
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png")

    report = sheet.build([str(good), str(bad)], str(tmp_path / "sheet.png"),
                         cols=2, cell=60, captions=["good", "bad"])

    assert report["tiles"] == 2
    assert report["unreadable"] == ["bad"]
    assert (tmp_path / "sheet.png").exists()


def test_a_sheet_of_nothing_is_refused(tmp_path):
    with pytest.raises(ValueError):
        sheet.build([], str(tmp_path / "sheet.png"), cols=2, cell=60)


# ── the workspace ──────────────────────────────────────────────────────────


def test_a_workspace_is_removed_whichever_way_the_job_ends(tmp_path):
    """`/tmp` survives a warm start, so a job that died mid-download would leave
    its half-file for the next invocation to inherit — and the disk fills one
    failure at a time."""
    seen = {}
    with pytest.raises(RuntimeError):
        with workspace.Workspace(root=str(tmp_path)) as space:
            seen["path"] = space.path
            open(space.at("big.mp4"), "wb").write(b"0" * 1024)
            raise RuntimeError("the encode failed")

    assert not (tmp_path / seen["path"].rsplit("/", 1)[-1]).exists()


def test_a_job_too_large_for_the_disk_is_refused_before_anything_is_downloaded(tmp_path):
    """**The message names both numbers**, because the fix is a Terraform change
    and a person needs to know which number to change.

    An `OSError: [Errno 28]` from inside ffmpeg, eight minutes and several
    hundred megabytes into a job, says none of that.
    """
    with workspace.Workspace(root=str(tmp_path)) as space:
        with pytest.raises(workspace.OutOfSpace) as refusal:
            space.reserve(1024 ** 4)  # a terabyte of inputs

    assert "MB of scratch space" in str(refusal.value)
    assert "worker_ephemeral_storage" in str(refusal.value)


def test_a_still_job_reserves_once_over_rather_than_twice(tmp_path):
    """A contact sheet of a 200 MB clip is a JPEG, so doubling would refuse jobs
    that fit."""
    with workspace.Workspace(root=str(tmp_path)) as space:
        free = space.free()
        # Just over half the disk: refused at factor 2, allowed at factor 1.
        want = (free - workspace.HEADROOM) * 6 // 10
        with pytest.raises(workspace.OutOfSpace):
            space.reserve(want)
        space.reserve(want, factor=1)
