"""Classification and naming: what a file is, and what it may be called.

**No raw S3 key reaches this module any more.** Every address the API takes is a
node id; `clean_key`, `_normalise` and `_reject_traversal` went with the two
routes that needed them — `GET /api/asset?key=` and `PATCH /api/text?key=`. The
last thing holding them up was *shared* material: `phrasebook/wording.yaml` and
the `config/pose/` plates belonged to no character and no project, had no node,
and so had no id to be addressed by. The entity model closed that — the
phrasebook is `TERM#` rows and the plates are nodes in a `config/` folder — so
the exception it justified closed with it. One addressing scheme, no
exceptions.

What that deletion cost, stated so nobody restores it by accident: nothing. In
prod `config.media_root_prefix()` was empty, so the root check passed
everything, and the traversal rules were guarding a string that is no longer
built from user input anywhere in this service.

**`clean_name` keeps every refusal it has.** None of them was ever about S3: a
slash is refused so a rename cannot become a move by punctuation, `.` and `..`
because they name nothing, control characters because a name holding a newline
can be written and then never referenced from a URL again, and 255 UTF-8 bytes
because a name is one segment. It refuses rather than strips — a silently
altered name is a rename nobody asked for.

**`clean_slug` is the same argument one level up.** A slug is a label on an
entity rather than a segment of a path, and it is library-unique, so it is
narrower still: lowercase, digits, `-` and `_`. It is not an id and nothing is
addressed by it — `PATCH /api/characters/<id>` changes one attribute and one
folder name — but it is what a person types, so it has to be a string a person
can type twice the same way.
"""

import posixpath
import re

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
SLUG = re.compile(r"^[a-z0-9_-]+$")

# Long enough for a descriptive label, short enough that it stays a label. The
# ceiling matters because a slug is also a folder name — `clean_name`'s 255-byte
# bound would let a slug be longer than anything a listing can draw.
MAX_SLUG_LENGTH = 64


def clean_slug(raw: str | None, label: str = "slug") -> str:
    """Validate a library-unique entity label.

    **Refused, never repaired**, for `clean_name`'s reason and one more of its
    own: a slug is claimed by a conditional write on `LIB#<lib>` /
    `CHARSLUG#<slug>`, so silently lowercasing `Subject-A` would let two people
    believe they hold two different names for one claim. What comes back is
    exactly what was sent or nothing at all.

    The character class is narrower than a name's because a slug is typed on a
    command line, appears in a URL and becomes a folder name — three places
    where a space, a quote or a non-ASCII letter is a different kind of nuisance
    each time.
    """
    if raw is None or not raw.strip():
        raise ValidationError(f"{label} is required")

    slug = raw.strip()
    if not SLUG.match(slug):
        raise ValidationError(f"{label} may only hold a-z, 0-9, '-' and '_'")
    if len(slug) > MAX_SLUG_LENGTH:
        raise ValidationError(f"{label} may be at most {MAX_SLUG_LENGTH} characters")
    return slug


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
