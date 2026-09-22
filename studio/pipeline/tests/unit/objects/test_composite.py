"""`studio composite` — the multi-angle plate, and the two things it must state.

Several engines take ONE image where identity wants several, so a front, a
three-quarter and a back laid out as one sheet is how a turnaround reaches a
single reference slot. The command is worth having over doing it on a laptop for
`crop`'s reasons: the layout is stated and printed, and the panels survive it.

The geometry itself lives in the service — `media/imaging.composite`, covered in
`backend/tests/unit/test_media.py` — and the fake calls that module rather than
restating it, so what is asserted here is this package's half: the order, the
destination, the refusals, and that the rescale is reported.
"""

from __future__ import annotations

import io

from click.testing import CliRunner
from PIL import Image

from studio_pipeline import cli
from studio_pipeline.adapters import store
from studio_pipeline.domain import characters as CHARACTER


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def _image(width: int, height: int, colour=(10, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, "PNG")
    return buf.getvalue()


def _panels(library, *sizes):
    record = CHARACTER.resolve("subject-a")
    seed = CHARACTER.pool_folder(record, "seed")
    return [library.fake.put_file(seed["id"], f"angle-{n}.png", _image(*size))
            for n, size in enumerate(sizes)]


def test_a_plate_is_written_and_every_panel_survives_it(library):
    panels = _panels(library, (400, 600), (400, 600), (400, 600))
    before = [store.read_node(p["id"]) for p in panels]

    result = _run("composite", *[a for p in panels for a in ("--key", p["id"])],
                  "--dest-key", f"{library.character}/seed/current/plate.png")

    assert result.exit_code == 0, result.output
    assert [store.read_node(p["id"]) for p in panels] == before, "panels untouched"
    written = store.resolve(f"{library.character}/seed/current/plate.png")
    # 400*3 panels + two 36px gutters + two 36px margins; 600 + two margins.
    assert Image.open(io.BytesIO(store.read_node(written["id"]))).size == (1344, 672)


def test_the_option_order_is_the_layout_order(library):
    """There is no sorting here, and there must not be: which angle goes where
    is the caller's judgement, and a plate in the wrong order is a subject
    turning the wrong way."""
    record = CHARACTER.resolve("subject-a")
    seed = CHARACTER.pool_folder(record, "seed")
    left = library.fake.put_file(seed["id"], "red.png", _image(100, 100, (255, 0, 0)))
    right = library.fake.put_file(seed["id"], "blue.png", _image(100, 100, (0, 0, 255)))

    result = _run("composite", "--key", right["id"], "--key", left["id"], "--gap", "0",
                  "--dest-key", f"{library.character}/seed/current/plate.png")

    assert result.exit_code == 0, result.output
    written = store.resolve(f"{library.character}/seed/current/plate.png")
    plate = Image.open(io.BytesIO(store.read_node(written["id"])))
    assert plate.getpixel((50, 50)) == (0, 0, 255), "the first --key is leftmost"
    assert plate.getpixel((150, 50)) == (255, 0, 0)


def test_the_gutter_and_the_sizes_are_printed(library):
    panels = _panels(library, (400, 600), (400, 600))

    result = _run("composite", *[a for p in panels for a in ("--key", p["id"])],
                  "--dest-key", f"{library.character}/seed/current/plate.png")

    assert "400x600 + 400x600 -> 908x672" in result.output
    assert "gutter 36px" in result.output


def test_a_rescale_is_reported_because_the_sheet_does_not_show_it(library):
    """A panel that came in at another size and went out matching its
    neighbours is a thing that happened to somebody's image unasked."""
    panels = _panels(library, (400, 600), (800, 1200))

    result = _run("composite", *[a for p in panels for a in ("--key", p["id"])],
                  "--dest-key", f"{library.character}/seed/current/plate.png")

    assert result.exit_code == 0, result.output
    assert "panels rescaled to a common edge" in result.output


def test_panels_that_already_match_are_not_reported_as_rescaled(library):
    panels = _panels(library, (400, 600), (400, 600))

    result = _run("composite", *[a for p in panels for a in ("--key", p["id"])],
                  "--dest-key", f"{library.character}/seed/current/plate.png")

    assert "rescaled" not in result.output


def test_a_panel_may_be_named_by_path_as_well_as_by_node(library):
    """A name path is walked from the library root, and a subject's root folder
    is named by its ID — so this is the spelling `studio download --folder`
    documents, not `<name>/seed`."""
    _panels(library, (400, 600), (400, 600))

    result = _run("composite",
                  "--key", f"{library.character}/seed/angle-0.png",
                  "--key", f"{library.character}/seed/angle-1.png",
                  "--dest-key", f"{library.character}/seed/current/plate.png")

    assert result.exit_code == 0, result.output


def test_composite_needs_a_destination_and_two_panels(library):
    no_dest = _run("composite", "--key", "node-a", "--key", "node-b")
    one = _run("composite", "--key", "node-a", "--add-input", "p")

    assert no_dest.exit_code != 0 and "choose a destination" in no_dest.output
    assert one.exit_code != 0 and "at least two panels" in one.output


def test_a_plate_wider_than_the_cap_is_refused_by_the_service(library):
    """The count is the service's rule, not this command's — so the refusal is
    the route's sentence, reported rather than raised."""
    panels = _panels(library, *([(40, 40)] * 8))

    result = _run("composite", *[a for p in panels + panels for a in ("--key", p["id"])],
                  "--dest-key", f"{library.character}/seed/current/plate.png")

    assert result.exit_code != 0
    assert "contact sheet" in result.output
