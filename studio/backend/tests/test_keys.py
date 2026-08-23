"""Classification, naming and slugs — tested directly.

**This file keeps shrinking, and each round of it is worth knowing was deleted
rather than forgotten.** #312 took `clean_prefix`, `assert_inside_root`,
`is_within`, `parent_prefix`, `with_name`, `renamed_prefix` and `moved_prefix`
once the writes moved onto the catalog. The entity model took the last three:
`clean_key`, `_normalise` and `_reject_traversal`.

What kept `clean_key` alive through #312 was *shared* material —
`phrasebook/wording.yaml` and the `config/pose/` plates belonged to no character
and no project, had no catalog node, and so had no id to be addressed by, which
is why `GET /api/asset?key=` took a raw S3 key. The entity model closed that: the
phrasebook is `TERM#` rows and the plates are ordinary nodes in a `config/`
folder. One addressing scheme, no exceptions, and no string in this service that
becomes an S3 key.

Its tests go with it in the same change, because a test asserting behaviour
nothing calls is how a deleted rule looks like a live one.

`clean_name` kept every refusal it has — none of them was ever about S3 — and
`clean_slug` is the same argument one level up.
"""

import pytest

from studio_core.errors import ValidationError
from studio_core.services import keys


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


# ---------------------------------------------------------------------------
# Slugs — the label a person types, claimed by a conditional write.
#
# Narrower than a name because a slug is three things at once: a segment of a
# URL, a word on a command line, and the folder name an entity's root takes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug", ["subject-a", "subject_b", "rooftop-teaser", "shot01", "a", "9-lives"]
)
def test_clean_slug_accepts(slug):
    assert keys.clean_slug(slug) == slug


@pytest.mark.parametrize(
    "slug",
    [
        None,
        "",
        "   ",
        "Subject-A",  # uppercase
        "subject a",  # space
        "subject/a",  # a slug is not a path
        "subject.a",  # a slug is not a filename
        "subject!",
        "café",
        "x" * (keys.MAX_SLUG_LENGTH + 1),
    ],
)
def test_clean_slug_rejects(slug):
    with pytest.raises(ValidationError):
        keys.clean_slug(slug)


def test_clean_slug_refuses_rather_than_repairs():
    """**It never lowercases for you, and that is the whole point.**

    A slug is claimed by a conditional put on `LIB#<lib>` / `CHARSLUG#<slug>`, so
    the string that is validated is the string that becomes half a primary key.
    Quietly folding `Subject-A` to `subject-a` would let two people believe they
    hold two different names for one claim, and the second would then find their
    character under a name they never typed.
    """
    with pytest.raises(ValidationError):
        keys.clean_slug("Subject-A")


def test_clean_slug_names_the_field_it_was_given():
    """The message has to say which field, because two of them are slugs.

    `POST /api/runs` validates a run slug and resolves a project by one in the
    same request; a refusal reading "slug may only hold..." would leave the
    caller guessing which.
    """
    with pytest.raises(ValidationError, match="title"):
        keys.clean_slug("Not A Slug", "title")
