"""What may and may not be a file path in an uploaded lesson.

**This is the security boundary of the upload API.** A path arrives from the
browser and becomes part of an S3 key that a presigned URL then grants write
access to, so an unchecked one writes wherever the caller likes — including over
another teacher's published lesson.

It is also a USABILITY boundary, and the two pull in opposite directions. A
teacher names a file `pie chart.png` and references it from her HTML, so
refusing it (or silently renaming it) breaks her lesson. The rules below are
where that line ended up.
"""

import pytest

from classroom_core.repositories.lessons import clean_path


@pytest.mark.parametrize(
    "path",
    [
        "index.html",
        # Nested folders, to any depth — a `js/` folder is the common case.
        "js/quiz.js",
        "assets/js/vendor/chart.min.js",
        "a/b/c/d/e/f/deep.png",
        # What real authoring tools emit.
        "Fractions_files/image001.png",
        # What a teacher actually calls things.
        "pie chart.png",
        "my js/quiz.js",
        "Worksheet (final).html",
        "Anita's notes.html",
        "Café/menu.png",
        "images/pie&slice.png",
    ],
)
def test_accepts_paths_a_teacher_would_produce(path):
    assert clean_path(path) == path


def test_windows_separators_become_folders():
    """A zip made on Windows uses backslashes; the files still belong in folders."""
    assert clean_path(r"images\diagrams\fig1.png") == "images/diagrams/fig1.png"


def test_leading_dot_slash_is_dropped():
    """Common in zip entries, and means nothing about where the file belongs."""
    assert clean_path("./index.html") == "index.html"


@pytest.mark.parametrize(
    "path",
    [
        "../other/index.html",
        "a/../../b.png",
        "..",
        "/etc/passwd",  # refused, NOT quietly rewritten to a relative path
    ],
)
def test_refuses_escaping_the_lesson(path):
    with pytest.raises(ValueError):
        clean_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "a#b.png",  # '#' ends a URL path — the file could never be fetched
        "q?.png",  # so does '?'
        "100%.png",  # collides with percent-encoding between CloudFront and S3
        "images//pie.png",  # empty segment
        "  spaced /x.png",  # padded name, resolves unpredictably as a key
    ],
)
def test_refuses_paths_that_could_not_be_served(path):
    with pytest.raises(ValueError):
        clean_path(path)


def test_refusal_names_the_file_and_says_what_to_do():
    """A teacher has to be able to act on this without reading the source."""
    with pytest.raises(ValueError) as raised:
        clean_path("pie#chart.png")
    message = str(raised.value)
    assert "pie#chart.png" in message
    assert "rename" in message.lower()
