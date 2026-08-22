"""Validation and normalisation for every S3 key and prefix the API accepts.

This is the one module standing between a query string and `GetObject`, so it is
deliberately strict and deliberately boring. Everything the caller supplies must
end up inside `config.media_root_prefix()`; anything that does not is a
`ValidationError`, never a clamped-and-carried-on.

In prod that root is empty — the whole bucket — so the prefix check passes
everything and the traversal rules are what is left doing the work. They still
matter: `..`, a leading `/` and a backslash are rejected before normalisation,
so no input can walk out of the bucket or smuggle a key past the checks below.
Point the root at a real prefix and the confinement comes back with it, which is
why the check stays.

## What #312 can take now, and the one thing it still cannot

#312 shrinks this module to classification and naming, on the premise that the
API has nothing left to guard. **#316–#319 finished making that true for the
writes.** `services.manage` addresses the catalog: it resolves a slash-joined
name path one exact `NAME#` lookup per segment, starting at the library's own
root node, so there is no prefix to normalise and nothing to confine — a name
path cannot name a node outside the library, and `..` is a name nothing is
called rather than traversal to reject.

**Seven functions have no caller left**, and #312 owns removing them and their
tests. They are still here, and still exercised by `tests/test_keys.py`, because
deleting behaviour and deleting its tests in different changes is how a rule
gets lost:

* `clean_prefix`, `assert_inside_root`, `is_within`, `parent_prefix`,
  `with_name`, `renamed_prefix`, `moved_prefix`.

Three of those describe operations that no longer exist as string edits at all:
`with_name` was a rename, `moved_prefix` was a move, and `renamed_prefix` was a
folder rename. They are `catalog.rename_node` and `catalog.move_node` now, and
the separation they held is held by the argument each one takes.

**`clean_key` is the exception and it is load-bearing.** `browse.asset_url` and
`browse.text_object` still take a raw S3 key from a query string and still do a
`GetObject` at it — they were expected to retire with the key-addressed writes
and did not — so this is still the only line between that query string and the
bucket, and `_reject_traversal`, `_normalise` and `basename` stay alive
underneath it. #312 has to move those two routes onto node ids before it can take
any of the four.

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

# What can be favourited. The same two kinds the reel shows, and for the same
# reason: a favourites folder is a shelf of picked output, not a second copy of
# the run metadata that happened to sit beside it.

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


def clean_prefix(raw: str | None) -> str:
    """Normalise a folder prefix and confine it to the media root.

    An empty or missing prefix means the root itself — which, when the root is
    the bucket, is the empty string. Every other return value ends in a slash so
    it can be handed straight to `ListObjectsV2`.
    """
    root = config.media_root_prefix()
    if raw is None or raw.strip() in ("", "/"):
        return root

    normalised = _normalise(raw.strip(), "prefix")
    if not normalised:
        return root

    prefix = normalised if normalised.endswith("/") else normalised + "/"
    if prefix != root and not prefix.startswith(root):
        raise ValidationError(f"prefix must sit inside '{root}'")
    return prefix


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


def parent_prefix(key: str) -> str:
    """The folder one key or prefix sits in, always ending in a slash."""
    trimmed = key.rstrip("/")
    head = posixpath.dirname(trimmed)
    return f"{head}/" if head else ""


def with_name(key: str, name: str) -> str:
    """The same key with its last segment replaced — a rename in place."""
    return f"{parent_prefix(key)}{name}"


def renamed_prefix(prefix: str, name: str) -> str:
    """The same folder prefix with its last segment replaced."""
    return f"{parent_prefix(prefix)}{name}/"


def moved_prefix(prefix: str, destination: str) -> str:
    """The same folder, carried under a different parent — a move.

    The counterpart of `renamed_prefix`: that one keeps the parent and changes
    the name, this one keeps the name and changes the parent. Between them they
    are the only two ways a prefix is allowed to change, which is what keeps
    "rename" and "move" separate operations rather than one string edit.
    """
    return f"{destination}{basename(prefix)}/"


def numbered_name(name: str, index: int) -> str:
    """`shot-01.mp4` at 2 → `shot-01 (2).mp4`.

    The convention the bucket already holds, from folders filled by hand out of a
    Finder window — there is a ` (3).mp4` and a ` copy.mp4` in there. Worth
    matching rather than inventing a third form. Reached whenever a copy's name
    is already taken at its destination, which is ordinary rather than rare:
    `shot-01.mp4` is what *every* scene calls its first shot.
    """
    stem, ext = posixpath.splitext(name)
    return f"{stem} ({index}){ext}"


def is_within(prefix: str, candidate: str) -> bool:
    """Whether `candidate` sits at or beneath `prefix`.

    Both are slash-terminated prefixes, which is what makes the plain
    `startswith` safe: without the trailing slash `projects/<name>-2/` would read
    as living inside `projects/<name>/`.
    """
    return candidate == prefix or candidate.startswith(prefix)


def assert_inside_root(prefix: str) -> None:
    """Refuse an operation aimed at the media root itself.

    `clean_prefix('')` returns the root, so every "which folder" argument has a
    valid value even when the caller sent nothing. That is right for browsing
    and catastrophic for deleting, which is why the destructive paths ask this
    question separately instead of trusting the normaliser.
    """
    root = config.media_root_prefix()
    if prefix == root:
        raise ValidationError(f"'{root}' is the library root and cannot be changed")
    if not prefix.startswith(root):
        raise ValidationError(f"prefix must sit inside '{root}'")


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
