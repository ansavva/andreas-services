"""Classification and naming: what a file is, and what it may be called.

**No raw S3 key reaches this module any more.** Every address the API takes is a
node id; `clean_key`, `_normalise` and `_reject_traversal` went with the two
routes that needed them — `GET /api/asset?key=` and `PATCH /api/text?key=`. The
last thing holding them up was *shared* material: `phrasebook/wording.yaml` and
the `config/angle/` angle images belonged to no character and no project, had no node,
and so had no id to be addressed by. The entity model closed that — the
phrasebook is `TERM#` rows and the angle images are nodes in a `config/` folder — so
the exception it justified closed with it. One addressing scheme, no
exceptions.

What that deletion cost, stated so nobody restores it by accident: nothing. The
browsable root is the whole bucket — there is no root prefix knob any more — so
the root check passed everything, and the traversal rules were guarding a string
that is no longer built from user input anywhere in this service.

**`clean_name` keeps every refusal it has.** None of them was ever about S3: a
slash is refused so a rename cannot become a move by punctuation, `.` and `..`
because they name nothing, control characters because a name holding a newline
can be written and then never referenced from a URL again, and 255 UTF-8 bytes
because a name is one segment. It refuses rather than strips — a silently
altered name is a rename nobody asked for.

**`clean_label` replaced `clean_slug`, and is far weaker on purpose.** A slug was
lowercase, digits, `-` and `_`, refused rather than repaired, because it was
library-unique: it was claimed by a conditional write, so silently lowercasing
`Subject-A` would let two people believe they held two different names for one
claim. None of that survives. An entity's `name` is a free-text label, nothing is
unique, and nothing resolves an entity by it — so the only things worth refusing
are the two that would break something downstream: an empty name, and `#`, which
separates every segment of a key in the catalog table.

Whitespace is folded rather than refused, which is the one repair here and is
safe for the same reason: `Anna  Smith` and `Anna Smith` are not two claims on
one name any more, they are two ways of typing a label, and collapsing them
means what a person sees is what is stored.
"""

import posixpath

from studio_core.errors import ValidationError

# Extensions we are willing to render. Compared case-insensitively because the
# bucket really does contain both `.jpg` and `.JPG` (characters/<name>/corpus).
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".m4v"})
TEXT_EXTENSIONS = frozenset({".json", ".md", ".txt", ".yaml", ".yml", ".csv", ".log"})

# What the text viewer labels a text file as, for syntax highlighting.
TEXT_LANGUAGES = {
    ".json": "json",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".csv": "csv",
}

# What a saved text file is written back with. Only consulted for extensions in
# `TEXT_EXTENSIONS`, since those are the only ones the editor will save — an
# extension missing from this map keeps `text/plain`, which is what S3 would have
# guessed anyway and is never wrong enough to matter for a file this small.
TEXT_CONTENT_TYPES = {
    ".json": "application/json",
    ".md": "text/markdown",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".csv": "text/csv",
}


def clean_name(raw: str | None) -> str:
    """Validate one path segment supplied as a new name.

    A name is not a key: it is exactly one segment, so a slash in it is not a
    traversal to normalise away but a different request entirely — "rename" is
    not "move", and letting one become the other by punctuation is how a rename
    ends up writing outside the folder the caller was looking at. Everything
    suspect is refused rather than stripped, because a silently altered name is
    a rename the user did not ask for.
    """
    if raw is None or not raw.strip():
        raise ValidationError("name is required")

    name = raw.strip()
    if "/" in name or "\\" in name:
        raise ValidationError("name may not contain slashes")
    if name in (".", ".."):
        raise ValidationError("name may not be '.' or '..'")
    # S3 keys are UTF-8 byte strings and will happily hold a newline or a NUL.
    # Such a key can be written and then never referenced from a URL again.
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in name):
        raise ValidationError("name may not contain control characters")
    if len(name.encode("utf-8")) > 255:
        raise ValidationError("name is too long")
    return name


# A slug: lowercase letters, digits, `-` and `_`. Anchored, so the whole string
# has to match rather than some part of it.
# Long enough for a descriptive label, short enough that it stays a label —
# a listing draws these in a card, and nothing can draw 255 bytes of them.
MAX_LABEL_LENGTH = 120


def clean_label(raw: str | None, label: str = "name") -> str:
    """Fold and check the free-text name of an entity.

    Two refusals, and they are the only two that break something: an empty name,
    and `#`, which separates the segments of every key in the catalog table.
    Everything else is allowed, so a character may be called `Anna Smith` and a
    project `Winter '26 — reshoots`.

    **Not unique, and nothing checks.** This replaced `clean_slug`, whose whole
    severity came from being a claim: it refused rather than repaired because
    silently lowercasing a slug would let two people believe they held two names
    for one claim. There is no claim, so there is nothing to protect.
    """
    name = " ".join((raw or "").split())
    if not name:
        raise ValidationError(f"{label} is required")
    if "#" in name:
        raise ValidationError(f"{label} may not contain '#'")
    if len(name) > MAX_LABEL_LENGTH:
        raise ValidationError(f"{label} may be at most {MAX_LABEL_LENGTH} characters")
    return name


# How many `name (n).ext` variants one name may spawn in one folder before the
# request is refused. Generous — copying the same clip into one folder twice is
# ordinary, and so is uploading the same phone photo twice — but finite, so a
# script cannot fill a folder with numbered variants.
#
# It lives here rather than beside either caller because there are now two of
# them: `manage.copy_objects` and `catalog.create_numbered`. Two constants of the
# same value would let `clip (100).mp4` be legal from one entry point and refused
# from the other, which is a difference nobody would ever go looking for.
MAX_NAME_VARIANTS = 100


def numbered_name(name: str, index: int) -> str:
    """`shot-01.mp4` at 2 → `shot-01 (2).mp4`.

    The convention the bucket already holds, from folders filled by hand out of a
    Finder window — there is a ` (3).mp4` and a ` copy.mp4` in there. Worth
    matching rather than inventing a third form. Reached whenever a name is
    already taken where it is landing, which is ordinary rather than rare:
    `shot-01.mp4` is what *every* scene calls its first shot, and a phone hands
    out `IMG_0001.HEIC` more than once in a lifetime.

    **The one place this form is decided.** An uploader that produced its own
    numbering client-side would be a second implementation of a convention that
    has to agree with copy's, and the disagreement would only ever be seen in a
    folder that had been through both.
    """
    stem, ext = posixpath.splitext(name)
    return f"{stem} ({index}){ext}"


def extension(key: str) -> str:
    return posixpath.splitext(key)[1].lower()


def kind(key: str) -> str:
    """Classify a key for the UI: image, video, text or other."""
    ext = extension(key)
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "other"


def language(key: str) -> str:
    """Highlighting hint for the text viewer."""
    return TEXT_LANGUAGES.get(extension(key), "text")


def content_type(key: str) -> str:
    """What a text file is written back to S3 as."""
    return TEXT_CONTENT_TYPES.get(extension(key), "text/plain")


def basename(key: str) -> str:
    return posixpath.basename(key.rstrip("/"))
