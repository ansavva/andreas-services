"""The validation layer is the API's only real attack surface — test it directly."""

import pytest

from studio_core.errors import ValidationError
from studio_core.services import keys


@pytest.fixture
def confined_root(monkeypatch):
    """Run a test against a non-empty browsable root.

    Prod browses the whole bucket, so the prefix confinement passes everything
    there and would go untested. The knob is still real — point it at a prefix
    and the API narrows to it — so the tests that cover it set one.
    """
    monkeypatch.setattr(keys.config, "media_root_prefix", lambda: "characters/")


@pytest.mark.parametrize(
    "raw,expected",
    [
        # The root is the bucket, so "no prefix" is the empty string.
        (None, ""),
        ("", ""),
        ("/", ""),
        ("characters/", "characters/"),
        ("characters/subject-a", "characters/subject-a/"),
        ("projects/subject-b/runs/2026-08-15_01-00-30_pullup-originals", "projects/subject-b/runs/2026-08-15_01-00-30_pullup-originals/"),
        ("phrasebook/", "phrasebook/"),
    ],
)
def test_clean_prefix_accepts(raw, expected):
    assert keys.clean_prefix(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "../secrets",
        "characters/../../etc",
        "projects/subject-a/../../../other-bucket-prefix",
        "/characters/subject-a",
        "characters\\subject-a",
    ],
)
def test_clean_prefix_rejects(raw):
    with pytest.raises(ValidationError):
        keys.clean_prefix(raw)


@pytest.mark.parametrize("raw", ["projects/", "characterslike/", "other/"])
def test_clean_prefix_confines_to_a_configured_root(confined_root, raw):
    with pytest.raises(ValidationError):
        keys.clean_prefix(raw)


def test_clean_prefix_root_itself_under_a_configured_root(confined_root):
    assert keys.clean_prefix(None) == "characters/"
    assert keys.clean_prefix("characters/subject-a") == "characters/subject-a/"


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


def test_folder_marker_detection():
    assert keys.is_folder_marker("characters/subject-a/seed/", 0)
    assert not keys.is_folder_marker("characters/subject-a/seed/a.webp", 0)
    assert not keys.is_folder_marker("characters/subject-a/seed/", 12)


def test_breadcrumbs():
    trail = keys.breadcrumbs("projects/subject-b/runs/")
    assert [entry["name"] for entry in trail] == ["/", "projects", "subject-b", "runs"]
    assert [entry["prefix"] for entry in trail] == [
        "",
        "projects/",
        "projects/subject-b/",
        "projects/subject-b/runs/",
    ]


def test_breadcrumbs_at_root():
    assert keys.breadcrumbs("") == [{"name": "/", "prefix": ""}]


def test_breadcrumbs_under_a_configured_root(confined_root):
    """The root crumb takes the root prefix's own name when there is one."""
    trail = keys.breadcrumbs("characters/subject-a/")
    assert [entry["name"] for entry in trail] == ["characters", "subject-a"]
    assert [entry["prefix"] for entry in trail] == ["characters/", "characters/subject-a/"]


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


def test_parent_prefix():
    assert keys.parent_prefix("characters/subject-a/a.jpg") == "characters/subject-a/"
    assert keys.parent_prefix("projects/subject-a/runs/") == "projects/subject-a/"
    # One segment up from the top level is the bucket root, which is the empty
    # string rather than a slash.
    assert keys.parent_prefix("characters/") == ""


def test_with_name_and_renamed_prefix():
    assert keys.with_name("characters/subject-a/a.jpg", "b.jpg") == "characters/subject-a/b.jpg"
    assert keys.renamed_prefix("projects/subject-a/runs/", "walks") == "projects/subject-a/walks/"


def test_moved_prefix_keeps_the_name_and_changes_the_parent():
    """The mirror image of `renamed_prefix`, which does exactly the opposite."""
    assert keys.moved_prefix("projects/subject-a/runs/", "characters/") == "characters/runs/"
    # To the library root, which is the empty string.
    assert keys.moved_prefix("projects/subject-a/runs/", "") == "runs/"


def test_is_within_needs_the_trailing_slash_to_be_right():
    assert keys.is_within("characters/subject-a/", "characters/subject-a/seed/")
    assert keys.is_within("characters/subject-a/", "characters/subject-a/")
    # The case the slash exists for: a sibling whose name merely starts the same
    # way is not inside, and reading it as inside would refuse a legal move.
    assert not keys.is_within("characters/subject-a/", "characters/subject-a-2/")
    assert not keys.is_within("characters/subject-a/", "characters/")
    # Everything is within the library root.
    assert keys.is_within("", "characters/subject-a/")


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


def test_assert_inside_root_refuses_the_root_itself():
    """The destructive paths' last line of defence, and now the only one.

    With the browsable root empty, every prefix is "inside" it — so what this
    still has to catch is an operation aimed at the root, which would be a
    rename or a delete of the entire library.
    """
    keys.assert_inside_root("characters/subject-a/")
    keys.assert_inside_root("projects/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("")


def test_assert_inside_root_confines_to_a_configured_root(confined_root):
    keys.assert_inside_root("characters/subject-a/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("characters/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("elsewhere/")


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
