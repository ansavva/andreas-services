"""The validation layer is the API's only real attack surface — test it directly."""

import pytest

from studio_core.errors import ValidationError
from studio_core.services import keys


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "media/"),
        ("", "media/"),
        ("/", "media/"),
        ("media/", "media/"),
        ("media/fred", "media/fred/"),
        ("media/fred/", "media/fred/"),
        ("media/mr-p/runs/2026-08-15_01-00-30_pullup-originals", "media/mr-p/runs/2026-08-15_01-00-30_pullup-originals/"),
    ],
)
def test_clean_prefix_accepts(raw, expected):
    assert keys.clean_prefix(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "../secrets",
        "media/../../etc",
        "media/fred/../../../other-bucket-prefix",
        "/media/fred",
        "media\\fred",
        "other/",
        "medialike/",
    ],
)
def test_clean_prefix_rejects(raw):
    with pytest.raises(ValidationError):
        keys.clean_prefix(raw)


def test_clean_key_accepts():
    assert keys.clean_key("media/fred/originals/fred_1.webp") == "media/fred/originals/fred_1.webp"


@pytest.mark.parametrize(
    "raw",
    [None, "", "media/fred/", "../etc/passwd", "media/../etc/passwd", "/media/x.png", "elsewhere/x.png"],
)
def test_clean_key_rejects(raw):
    with pytest.raises(ValidationError):
        keys.clean_key(raw)


@pytest.mark.parametrize(
    "key,expected",
    [
        ("a/b.webp", "image"),
        ("a/b.JPG", "image"),  # the bucket has uppercase extensions
        ("a/b.jpeg", "image"),
        ("a/b.png", "image"),
        ("a/b.mp4", "video"),
        ("a/b.json", "text"),
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
    assert keys.language("a/profile.md") == "markdown"
    assert keys.language("a/caption.txt") == "text"


def test_folder_marker_detection():
    assert keys.is_folder_marker("media/fred/originals/", 0)
    assert not keys.is_folder_marker("media/fred/originals/a.webp", 0)
    assert not keys.is_folder_marker("media/fred/originals/", 12)


def test_breadcrumbs():
    trail = keys.breadcrumbs("media/mr-p/runs/")
    assert [entry["name"] for entry in trail] == ["media", "mr-p", "runs"]
    assert [entry["prefix"] for entry in trail] == ["media/", "media/mr-p/", "media/mr-p/runs/"]


def test_breadcrumbs_at_root():
    assert keys.breadcrumbs("media/") == [{"name": "media", "prefix": "media/"}]


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
    assert keys.parent_prefix("media/fred/a.jpg") == "media/fred/"
    assert keys.parent_prefix("media/fred/runs/") == "media/fred/"
    assert keys.parent_prefix("media/") == ""


def test_with_name_and_renamed_prefix():
    assert keys.with_name("media/fred/a.jpg", "b.jpg") == "media/fred/b.jpg"
    assert keys.renamed_prefix("media/fred/runs/", "walks") == "media/fred/walks/"


def test_assert_inside_root():
    keys.assert_inside_root("media/fred/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("media/")
    with pytest.raises(ValidationError):
        keys.assert_inside_root("elsewhere/")
