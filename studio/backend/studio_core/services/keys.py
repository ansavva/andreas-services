"""Validation and normalisation for every S3 key and prefix the API accepts.

This is the one module standing between a query string and `GetObject`, so it is
deliberately strict and deliberately boring. Everything the caller supplies must
end up inside `config.media_root_prefix()`; anything that does not is a
`ValidationError`, never a clamped-and-carried-on.
"""

import posixpath

from studio_core import config
from studio_core.errors import ValidationError

# Extensions we are willing to render. Compared case-insensitively because the
# bucket really does contain both `.jpg` and `.JPG` (mr-p/originals).
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov", ".m4v"})
TEXT_EXTENSIONS = frozenset({".json", ".md", ".txt", ".yaml", ".yml", ".csv", ".log"})

# What the read-only viewer labels a text file as, for syntax highlighting.
TEXT_LANGUAGES = {
    ".json": "json",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".csv": "csv",
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

    An empty or missing prefix means the root itself. The return value always
    ends in a slash so it can be handed straight to `ListObjectsV2`.
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
    """Highlighting hint for the read-only text viewer."""
    return TEXT_LANGUAGES.get(extension(key), "text")


def is_folder_marker(key: str, size: int) -> bool:
    """True for the zero-byte objects the console creates to fake a folder.

    The bucket has several (`media/`, `media/fred/originals/`). They are not
    files and must never appear in a listing.
    """
    return size == 0 and key.endswith("/")


def basename(key: str) -> str:
    return posixpath.basename(key.rstrip("/"))


def breadcrumbs(prefix: str) -> list[dict]:
    """Ancestor trail for a prefix, root first, each entry navigable."""
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
