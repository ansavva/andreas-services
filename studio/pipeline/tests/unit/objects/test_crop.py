"""`studio crop` — the framing verb the pipeline had no command for.

Framing is neither a generation nor a re-encode, so it fell between every
command in the package: the images were cut on a laptop, uploaded, and the box
that produced them thrown away. These assert the two things that make the
command worth having over doing it by hand — the cut is stated and printed, and
the source survives it.
"""

from __future__ import annotations

import io

import pytest
from click.testing import CliRunner
from PIL import Image

from studio_pipeline import cli
from studio_pipeline.adapters import store
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.objects import crop as CROP


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def _image(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


# ── the box parser, where every error message is the point ─────────────────

def test_a_box_of_the_wrong_length_says_how_many_it_got():
    with pytest.raises(SystemExit):
        CROP.parse_box("1,2,3")


def test_width_and_height_instead_of_right_and_bottom_is_named_as_such(capsys):
    """The commonest way to get it wrong, because half the world's crop APIs
    take LEFT,TOP,WIDTH,HEIGHT and this one does not."""
    with pytest.raises(SystemExit):
        CROP.parse_box("100,100,50,50")
    assert "not LEFT,TOP,WIDTH,HEIGHT" in capsys.readouterr().err


def test_a_box_over_the_edge_is_clamped_not_refused(library):
    """Padding a detection puts the box past the edge routinely; refusing would
    make every caller implement the clamp.

    **Asserted through the command, because the clamp moved.** It was
    `CROP.clamp`, a pure function next to the Pillow that used it; the image is
    read and cut by the API now, so the only side that knows the image's
    dimensions is the one that decides the clamp. What this package is still
    responsible for is reporting it — see `media/imaging.clamp` and
    `backend/tests/unit/test_images.py` for the arithmetic itself.
    """
    record = CHARACTER.resolve("subject-a")
    source = library.fake.put_file(
        CHARACTER.pool_folder(record, "seed")["id"], "wide.png", _image(400, 600))

    result = _run("crop", "--key", source["id"], "--box", "-20,-20,500,5000",
                  "--dest-key", "characters/subject-a/seed/current/cut.png")

    assert result.exit_code == 0, result.output
    assert "400x600 -> 400x600" in result.output
    assert "at 0,0,400,600" in result.output


def test_a_box_that_misses_the_image_entirely_is_refused(library):
    """A mistake, not a rounding — so it is the one box that is not clamped."""
    record = CHARACTER.resolve("subject-a")
    source = library.fake.put_file(
        CHARACTER.pool_folder(record, "seed")["id"], "wide.png", _image(400, 600))

    result = _run("crop", "--key", source["id"], "--box", "900,900,1000,1000",
                  "--dest-key", "characters/subject-a/seed/current/cut.png")

    assert result.exit_code != 0
    assert "entirely outside" in result.output


# ── the command ────────────────────────────────────────────────────────────

def test_crop_writes_the_cut_and_leaves_the_source_alone(library):
    record = CHARACTER.resolve("subject-a")
    seed = CHARACTER.pool_folder(record, "seed")
    source = library.fake.put_file(seed["id"], "wide.png", _image(400, 600))
    before = store.read_node(source["id"])

    result = _run("crop", "--key", source["id"], "--box", "100,50,300,550",
                  "--dest-key", "characters/subject-a/seed/current/cut.png")

    assert result.exit_code == 0, result.output
    assert "400x600 -> 200x500" in result.output
    assert store.read_node(source["id"]) == before, "source untouched"
    written = store.resolve("characters/subject-a/seed/current/cut.png")
    assert Image.open(io.BytesIO(store.read_node(written["id"]))).size == (200, 500)


def test_crop_reports_when_it_clamped(library):
    record = CHARACTER.resolve("subject-a")
    seed = CHARACTER.pool_folder(record, "seed")
    source = library.fake.put_file(seed["id"], "wide.png", _image(400, 600))

    result = _run("crop", "--key", source["id"], "--box", "-10,0,4000,600",
                  "--dest-key", "characters/subject-a/seed/current/cut.png")

    assert result.exit_code == 0, result.output
    assert "clamped from -10,0,4000,600" in result.output


def test_crop_needs_a_destination_and_exactly_one_source(library):
    no_dest = _run("crop", "--key", "node-x", "--box", "0,0,1,1")
    both = _run("crop", "--key", "node-x", "--run", "p/latest#1",
                "--box", "0,0,1,1", "--add-input", "p")

    assert no_dest.exit_code != 0 and "choose a destination" in no_dest.output
    assert both.exit_code != 0 and "exactly one source" in both.output
