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
        ("characters/fred", "characters/fred/"),
        ("projects/mr-p/runs/2026-08-15_01-00-30_pullup-originals", "projects/mr-p/runs/2026-08-15_01-00-30_pullup-originals/"),
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
        "projects/fred/../../../other-bucket-prefix",
        "/characters/fred",
        "characters\\fred",
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
    assert keys.clean_prefix("characters/fred") == "characters/fred/"


def test_clean_key_accepts():
    assert keys.clean_key("characters/fred/seed/fred_1.webp") == "characters/fred/seed/fred_1.webp"


@pytest.mark.parametrize(
    "raw",
    [None, "", "characters/fred/", "../etc/passwd", "characters/../etc/passwd", "/characters/x.png"],
)
def test_clean_key_rejects(raw):
    with pytest.raises(ValidationError):
        keys.clean_key(raw)


def test_clean_key_confines_to_a_configured_root(confined_root):
    with pytest.raises(ValidationError):
        keys.clean_key("projects/fred/runs/x/output/a.jpeg")


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
    assert keys.is_folder_marker("characters/fred/seed/", 0)
    assert not keys.is_folder_marker("characters/fred/seed/a.webp", 0)
    assert not keys.is_folder_marker("characters/fred/seed/", 12)


def test_breadcrumbs():
    trail = keys.breadcrumbs("projects/mr-p/runs/")
    assert [entry["name"] for entry in trail] == ["/", "projects", "mr-p", "runs"]
    assert [entry["prefix"] for entry in trail] == [
        "",
        "projects/",
        "projects/mr-p/",
        "projects/mr-p/runs/",
    ]


def test_breadcrumbs_at_root():
    assert keys.breadcrumbs("") == [{"name": "/", "prefix": ""}]


def test_breadcrumbs_under_a_configured_root(confined_root):
    """The root crumb takes the root prefix's own name when there is one."""
    trail = keys.breadcrumbs("characters/fred/")
    assert [entry["name"] for entry in trail] == ["characters", "fred"]
    assert [entry["prefix"] for entry in trail] == ["characters/", "characters/fred/"]


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
    assert keys.parent_prefix("characters/fred/a.jpg") == "characters/fred/"
    assert keys.parent_prefix("projects/fred/runs/") == "projects/fred/"
    # One segment up from the top level is the bucket root, which is the empty
    # string rather than a slash.
    assert keys.parent_prefix("characters/") == ""


def test_with_name_and_renamed_prefix():
    assert keys.with_name("characters/fred/a.jpg", "b.jpg") == "characters/fred/b.jpg"
    assert keys.renamed_prefix("projects/fred/runs/", "walks") == "projects/fred/walks/"


def test_assert_inside_root_refuses_the_root_itself():
    """The destructive paths' last line of defence, and now the only one.

    With the browsable root empty, every prefix is "inside" it — so what this
    still has to catch is an operation aimed at the root, which would be a
    rename or a delete of the entire library.
    """
    keys.assert_inside_root("characters/fred/")
    keys.assert_inside_root("projects/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("")


def test_assert_inside_root_confines_to_a_configured_root(confined_root):
    keys.assert_inside_root("characters/fred/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("characters/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("elsewhere/")
