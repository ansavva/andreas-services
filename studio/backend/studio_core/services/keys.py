"""Classification, naming, and the one raw S3 key the API still accepts.

**This module used to be the line between a query string and `GetObject`**, and
after #312 it is that for exactly one parameter. Everything else the API takes is
a node id or a slash-joined name path, resolved against the catalog one exact
`NAME#` lookup per segment from the library's own root — a walk that cannot leave
the library it starts in, so there is no prefix to normalise and `..` is a name
nothing is called rather than traversal to reject.

## What #312 took, and the one thing it could not

Seven functions went with their callers: `clean_prefix`, `assert_inside_root`,
`is_within`, `parent_prefix`, `with_name`, `renamed_prefix` and `moved_prefix`.
Three of them described operations that no longer exist as string edits at all —
`with_name` was a rename, `renamed_prefix` a folder rename, `moved_prefix` a
move — and they are `catalog.rename_node` and `catalog.move_node` now, with the
separation they held now held by the argument each one takes.

**`clean_key` stayed, and #312 expected to take it.** #432 moved
`browse.text_object` onto the catalog and `browse.asset_url` half way: that route
also serves the pipeline's *shared* material — `phrasebook/wording.yaml` and the
`config/pose/` plates — which belongs to no character and no project, which
`catalog_seed` deliberately records no node for, and which therefore has neither
an id nor a name path to be addressed by. `GET /api/asset?key=` is a raw S3 key
for that reason alone, and `_reject_traversal`, `_normalise` and `basename` stay
alive underneath it.

So the confinement below still runs, on one parameter, and it is worth knowing
what it is actually doing. In prod `config.media_root_prefix()` is empty — the
whole bucket — so the root check passes everything and the traversal rules are
the whole of it: `..`, a leading `/` and a backslash are rejected *before*
normalisation, because `posixpath.normpath` collapses `a/../b` silently and a
guess is worse than a refusal. Point the root at a real prefix and the
confinement comes back with it, which is why the check stays.

**`clean_name` keeps every refusal it has.** None of them was ever about S3: a
slash is refused so a rename cannot become a move by punctuation, `.` and `..`
because they name nothing, control characters because a name holding a newline
can be written and then never referenced from a URL again, and 255 UTF-8 bytes
because a name is one segment. It refuses rather than strips — a silently altered
name is a rename nobody asked for.
"""

import posixpath

from studio_core import config
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


def _reject_traversal(value: str, label: str) -> None:
    if "\\" in value:
        raise ValidationError(f"{label} may not contain backslashes")
    if value.startswith("/"):
        raise ValidationError(f"{label} may not be absolute")
    # Checked on the raw value as well as after normalisation: `posixpath.normpath`
    # collapses `a/../b` silently, and we would rather say no than guess.
    if any(segment == ".." for segment in value.split("/")):
        raise ValidationError(f"{label} may not contain '..'")


def _normalise(value: str, label: str) -> str:
    _reject_traversal(value, label)
    normalised = posixpath.normpath(value)
    if normalised in (".", "/"):
        return ""
    if normalised.startswith("../") or normalised == "..":
        raise ValidationError(f"{label} escapes the media root")
    return normalised


def clean_key(raw: str | None) -> str:
    """Normalise an object key and confine it to the media root."""
    if raw is None or not raw.strip():
        raise ValidationError("key is required")

    stripped = raw.strip()
    # Checked before normalising: `posixpath.normpath` drops a trailing slash, so
    # after it a folder is indistinguishable from an object.
    if stripped.endswith("/"):
        raise ValidationError("key must name an object, not a folder")

    key = _normalise(stripped, "key")
    if not key:
        raise ValidationError("key must name an object, not a folder")
    if not key.startswith(config.media_root_prefix()):
        raise ValidationError(f"key must sit inside '{config.media_root_prefix()}'")
    return key


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
