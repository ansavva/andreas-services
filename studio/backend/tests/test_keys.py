"""Classification, naming, and the one raw key left — tested directly.

**Most of this file went with #312**, and what it covered is worth knowing was
deleted rather than forgotten. `clean_prefix`, `assert_inside_root`, `is_within`,
`parent_prefix`, `with_name`, `renamed_prefix` and `moved_prefix` had no caller
left once the writes moved onto the catalog: a name path is walked one exact
`NAME#` lookup per segment from the library root, so there is no string to
confine and the operations three of them described are transactions now. Their
tests are gone with them, in the same change, because a test asserting behaviour
nothing calls is how a deleted rule looks like a live one.

`clean_key` and the traversal rules under it are still here, still tested, and
still reachable — `GET /api/asset?key=` is a raw S3 key, because that is how the
pipeline reads shared material that deliberately has no node.
"""

import pytest

from studio_core.errors import ValidationError
from studio_core.services import keys


@pytest.fixture
def confined_root(monkeypatch):
    """Run a test against a non-empty browsable root.

    Prod browses the whole bucket, so the confinement passes everything there and
    would go untested. The knob is still real — point it at a prefix and the API
    narrows to it — so the test that covers it sets one.
    """
    monkeypatch.setattr(keys.config, "media_root_prefix", lambda: "characters/")


def test_clean_key_accepts():
    assert keys.clean_key("characters/subject-a/seed/subject-a_1.webp") == "characters/subject-a/seed/subject-a_1.webp"


@pytest.mark.parametrize(
    "raw",
    [None, "", "characters/subject-a/", "../etc/passwd", "characters/../etc/passwd", "/characters/x.png"],
)
def test_clean_key_rejects(raw):
    with pytest.raises(ValidationError):
        keys.clean_key(raw)


def test_clean_key_confines_to_a_configured_root(confined_root):
    with pytest.raises(ValidationError):
        keys.clean_key("projects/subject-a/runs/x/output/a.jpeg")


@pytest.mark.parametrize(
    "key,expected",
    [
        ("a/b.webp", "image"),
        ("a/b.JPG", "image"),  # the bucket has uppercase extensions
        ("a/b.jpeg", "image"),
        ("a/b.png", "image"),
        ("a/b.mp4", "video"),
        ("a/b.json", "text"),
        ("a/b.yaml", "text"),  # profile.yaml, phrasebook/wording.yaml
        ("a/b.md", "text"),
        ("a/b.txt", "text"),
        ("a/b.bin", "other"),
        ("a/b", "other"),
    ],
)
def test_kind(key, expected):
    assert keys.kind(key) == expected


def test_language():
    assert keys.language("a/request.json") == "json"
    assert keys.language("a/profile.yaml") == "yaml"
    assert keys.language("a/notes.md") == "markdown"
    assert keys.language("a/caption.txt") == "text"


# `is_folder_marker` and `breadcrumbs` were tested here until #309. Both described
# S3 listings: a marker cannot exist where a folder is a row, and a breadcrumb
# trail is a walk up `parent_id` rather than a string split. Their tests went
# with them — `tests/test_browse.py` covers the trail now.


# ---------------------------------------------------------------------------
# Names — one path segment, supplied by a user, on its way to a write.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["a/b", "a\\b", "..", ".", "", "   ", "with\nnewline", "with\x00nul", "x" * 256],
)
def test_clean_name_rejects(name):
    with pytest.raises(ValidationError):
        keys.clean_name(name)


@pytest.mark.parametrize(
    "name", ["keeper.jpeg", "wave porch 1x1", "IMG_1966_Original.JPG", "café.webp", "a.b.c"]
)
def test_clean_name_accepts(name):
    assert keys.clean_name(name) == name


def test_clean_name_trims_but_does_not_otherwise_alter():
    assert keys.clean_name("  keeper.jpeg  ") == "keeper.jpeg"


def test_content_type_covers_every_text_extension():
    """A text file studio will save must have something to save it as.

    `TEXT_EXTENSIONS` is what the editor is allowed to open, so an extension in
    it with no content type would be written as `text/plain` — harmless, but
    worth knowing about deliberately rather than discovering in the bucket.
    """
    assert keys.content_type("characters/subject-a/profile.yaml") == "application/yaml"
    assert keys.content_type(f"{'a'}.json") == "application/json"
    assert keys.content_type("notes.md") == "text/markdown"
    # The two that fall through to the default on purpose.
    assert keys.content_type("run.log") == "text/plain"
    assert keys.content_type("caption.txt") == "text/plain"


# ---------------------------------------------------------------------------
# Numbering a name that is taken
#
# What `manage.copy_objects` reaches for when a copy's basename already exists
# at its destination. The bucket already holds hand-made ` (3).mp4` names, so
# this matches that rather than inventing a third form.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,index,expected",
    [
        ("shot-01.mp4", 2, "shot-01 (2).mp4"),
        ("wave-porch.jpeg", 3, "wave-porch (3).jpeg"),
        # Dots in the stem are not extensions. Only the last one is.
        ("v6.white.bg.jpeg", 2, "v6.white.bg (2).jpeg"),
        ("README", 2, "README (2)"),
    ],
)
def test_numbered_name(name, index, expected):
    assert keys.numbered_name(name, index) == expected
