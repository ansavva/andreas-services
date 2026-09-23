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
from studio_core.media import imaging, mime, sheet, workspace


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


# ── the plate ──────────────────────────────────────────────────────────────


def test_a_row_is_the_panels_plus_the_gutters_plus_the_margins():
    """The whole arithmetic, stated once: three 400x600 panels at the default
    6% of 600 is a 36px gutter twice over and a 36px margin twice over."""
    plate, report = imaging.composite([_png(), _png(), _png()], ".png")

    assert report["gap"] == 36 and report["margin"] == 36
    assert report["width"] == 400 * 3 + 36 * 2 + 36 * 2
    assert report["height"] == 600 + 36 * 2
    assert Image.open(io.BytesIO(plate)).size == (report["width"], report["height"])


def test_panels_are_normalised_DOWN_to_the_shortest_never_up():
    """A genuine render beside an upscaled one reads as two subjects, so the
    smallest panel sets the edge and everything else shrinks to meet it."""
    _plate, report = imaging.composite(
        [_png(400, 600), _png(800, 1200), _png(200, 300)], ".png")

    assert [p["height"] for p in report["panels"]] == [300, 300, 300]
    assert [p["width"] for p in report["panels"]] == [200, 200, 200]
    assert report["scaled"] is True
    assert report["panels"][1]["source"] == {"width": 800, "height": 1200}


def test_panels_that_already_match_are_not_reported_as_scaled():
    _plate, report = imaging.composite([_png(), _png()], ".png")

    assert report["scaled"] is False


def test_a_column_lays_them_down_and_takes_its_edge_from_the_narrowest():
    _plate, report = imaging.composite(
        [_png(400, 600), _png(200, 300)], ".png", direction="column")

    assert [p["width"] for p in report["panels"]] == [200, 200]
    assert report["height"] == 300 + 300 + report["gap"] + report["margin"] * 2
    assert report["width"] == 200 + report["margin"] * 2


def test_the_gutter_is_a_percentage_so_it_survives_a_change_of_resolution():
    """The reason it is not a pixel count: the same 6 lays the same-looking
    sheet out of 600px panels and out of 1536px ones."""
    _plate, small = imaging.composite([_png(400, 600), _png(400, 600)], ".png")
    _plate, large = imaging.composite([_png(1024, 1536), _png(1024, 1536)], ".png")

    assert small["gap"] == 36 and large["gap"] == 92


def test_a_zero_gutter_is_allowed_because_someone_may_want_a_contact_strip():
    _plate, report = imaging.composite([_png(), _png()], ".png", gap_percent=0)

    assert report["gap"] == 0 and report["margin"] == 0
    assert report["width"] == 800


def test_one_image_composited_with_nothing_is_the_image_and_is_refused():
    with pytest.raises(ValidationError) as refusal:
        imaging.composite([_png()], ".png")

    assert "at least two" in str(refusal.value)


def test_more_panels_than_a_plate_holds_is_refused_as_a_contact_sheet():
    with pytest.raises(ValidationError) as refusal:
        imaging.composite([_png(20, 20)] * (imaging.MAX_PANELS + 1), ".png")

    assert "contact sheet" in str(refusal.value)


def test_the_ground_is_painted_where_the_gutter_is():
    """A gutter the colour of the backdrop is invisible on a white plate and is
    exactly what a coloured one is for — so the pixel between two panels is
    asserted rather than assumed."""
    plate, report = imaging.composite(
        [_png(100, 100), _png(100, 100)], ".png", background="#ff0000")

    drawn = Image.open(io.BytesIO(plate))
    assert drawn.getpixel((report["margin"] + 100 + report["gap"] // 2,
                           report["height"] // 2)) == (255, 0, 0)
    assert drawn.getpixel((0, 0)) == (255, 0, 0), "the margin too"


def test_a_background_that_is_not_a_colour_says_so():
    with pytest.raises(ValidationError) as refusal:
        imaging.composite([_png(), _png()], ".png", background="whiteish")

    assert "hex colour" in str(refusal.value)


def test_a_three_digit_hex_is_the_same_colour_as_its_six_digit_form():
    assert imaging.parse_colour("#fff") == imaging.parse_colour("#ffffff")
    assert imaging.parse_colour("abc") == (0xAA, 0xBB, 0xCC)


def test_a_gap_outside_the_range_is_refused_rather_than_clamped():
    """Unlike a crop's box, which is clamped: a box past the edge is what
    padding a detection produces, and a 900% gutter is a typo."""
    with pytest.raises(ValidationError):
        imaging.composite([_png(), _png()], ".png", gap_percent=900)


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


# ── mime ───────────────────────────────────────────────────────────────────


def test_a_webp_is_an_image_on_every_platform():
    """Python 3.11's built-in table has no `.webp`; a Mac's `/etc/apache2/
    mime.types` hides that and the Lambda has no such file. 47 outputs in
    prod were stored `application/octet-stream` before the type was
    registered here."""
    assert mime.content_type_of("image.webp") == "image/webp"
    assert mime.content_type_of("clip.mp4") == "video/mp4"
    assert mime.content_type_of("weights.safetensors") == "application/octet-stream"


def test_an_audio_file_is_typed_so_a_browser_will_play_it():
    """The `.webp` failure, one media type over — and two of these OVERRIDE
    the platform rather than filling a hole.

    A Mac reads `/etc/apache2/mime.types` at import and calls a `.wav`
    `audio/x-wav` and an `.m4a` `audio/mp4a-latm`, both pre-standard, the
    second of which Safari will not play. The Lambda's table knows `.mp3` and
    none of the rest, so without these a voice sample uploaded through the
    deployed API would be stored `application/octet-stream` and the page
    would draw a dead control over it.
    """
    assert mime.content_type_of("take.mp3") == "audio/mpeg"
    assert mime.content_type_of("take.wav") == "audio/wav"
    assert mime.content_type_of("take.m4a") == "audio/mp4"
    assert mime.content_type_of("take.flac") == "audio/flac"


def test_what_the_provider_served_wins_when_it_names_a_media_type():
    assert mime.content_type_of("image.webp", "image/webp") == "image/webp"
    assert mime.content_type_of("tmpabc.jpg", "image/png") == "image/png", \
        "the header is what was measured; the name is a label"
    assert mime.content_type_of("clip.mp4", "Video/MP4; charset=binary") == "video/mp4"


def test_a_served_type_that_is_not_media_falls_back_to_the_extension():
    """A bucket behind a worker says `application/octet-stream` or S3's
    `binary/octet-stream`, an expired-link page says `text/html` — none of
    them is the file."""
    assert mime.content_type_of("image.webp", "application/octet-stream") == "image/webp"
    assert mime.content_type_of("clip.mp4", "binary/octet-stream") == "video/mp4"
    assert mime.content_type_of("image.png", "text/html; charset=utf-8") == "image/png"
    assert mime.content_type_of("image.png", "") == "image/png"
    assert mime.content_type_of("image.png", None) == "image/png"
    assert mime.content_type_of("blob", "application/octet-stream") == "application/octet-stream"
