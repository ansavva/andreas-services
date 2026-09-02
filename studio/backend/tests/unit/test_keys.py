"""Classification, naming and slugs — tested directly.

**This file keeps shrinking, and each round of it is worth knowing was deleted
rather than forgotten.** #312 took `clean_prefix`, `assert_inside_root`,
`is_within`, `parent_prefix`, `with_name`, `renamed_prefix` and `moved_prefix`
once the writes moved onto the catalog. The entity model took the last three:
`clean_key`, `_normalise` and `_reject_traversal`.

What kept `clean_key` alive through #312 was *shared* material —
`phrasebook/wording.yaml` and the `config/angle/` plates belonged to no character
and no project, had no catalog node, and so had no id to be addressed by, which
is why `GET /api/asset?key=` took a raw S3 key. The entity model closed that: the
phrasebook is `TERM#` rows and the plates are ordinary nodes in a `config/`
folder. One addressing scheme, no exceptions, and no string in this service that
becomes an S3 key.

Its tests go with it in the same change, because a test asserting behaviour
nothing calls is how a deleted rule looks like a live one.

`clean_name` kept every refusal it has — none of them was ever about S3 — and
`clean_label` replaced `clean_slug` with something far weaker, because the
severity was the claim rather than the string.
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
# clean_label — the free-text name an entity carries.
#
# It replaced `clean_slug`, which was lowercase/digits/`-`/`_`, refused rather
# than repaired, and capped at 64. All of that severity came from the slug being
# a CLAIM: the validated string became half a primary key, so folding
# `Subject-A` quietly would let two people believe they held two names for one
# claim. There is no claim, so there is nothing to protect and almost nothing
# left to refuse.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "Anna Smith",
    "subject-a",
    "Winter '26 — reshoots",
    "café",
    "9 lives",
])
def test_clean_label_accepts_what_a_person_would_type(name):
    """Case, spaces, punctuation and non-ASCII all survive. A name is a label."""
    assert keys.clean_label(name) == name


def test_clean_label_folds_whitespace_rather_than_refusing_it():
    """**The one repair, and it is safe because there is no claim.**

    `Anna  Smith` and `Anna Smith` were two attempts on one claim once, which is
    why folding was forbidden. They are two ways of typing a label now, and
    collapsing them means what a person sees is what is stored.
    """
    assert keys.clean_label("  Anna   Smith ") == "Anna Smith"


@pytest.mark.parametrize("name", ["", "   ", None, "a#b", "x" * (keys.MAX_LABEL_LENGTH + 1)])
def test_clean_label_rejects(name):
    """Empty, over-long, and `#` — which separates every key segment in the table."""
    with pytest.raises(ValidationError):
        keys.clean_label(name)


def test_clean_label_names_the_field_it_was_given():
    """The message has to say which field when a request carries more than one."""
    with pytest.raises(ValidationError, match="title"):
        keys.clean_label("", "title")
