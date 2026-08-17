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
"""

import posixpath

from studio_core import config
from studio_core.errors import ValidationError

# Extensions we are willing to render. Compared case-insensitively because the
# bucket really does contain both `.jpg` and `.JPG` (characters/mr-p/corpus).
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


def is_within(prefix: str, candidate: str) -> bool:
    """Whether `candidate` sits at or beneath `prefix`.

    Both are slash-terminated prefixes, which is what makes the plain
    `startswith` safe: without the trailing slash `projects/fred-2/` would read
    as living inside `projects/fred/`.
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


def is_folder_marker(key: str, size: int) -> bool:
    """True for the zero-byte objects the console creates to fake a folder.

    The bucket has none today — the pipeline writes real keys — but anyone who
    opens the console and makes a folder creates one, and it is not a file and
    must never appear in a listing.
    """
    return size == 0 and key.endswith("/")


def basename(key: str) -> str:
    return posixpath.basename(key.rstrip("/"))


def breadcrumbs(prefix: str) -> list[dict]:
    """Ancestor trail for a prefix, root first, each entry navigable.

    The root crumb is named after the root prefix, so it reads as `/` when the
    browsable root is the whole bucket and as the prefix's own name otherwise.
    """
    root = config.media_root_prefix()
    trail = [{"name": root.rstrip("/") or "/", "prefix": root}]

    remainder = prefix[len(root):].strip("/") if prefix.startswith(root) else ""
    if not remainder:
        return trail

    walked = root
    for segment in remainder.split("/"):
        walked = f"{walked}{segment}/"
        trail.append({"name": segment, "prefix": walked})
    return trail
