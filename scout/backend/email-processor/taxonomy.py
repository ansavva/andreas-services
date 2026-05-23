"""
Pure helpers for sender normalization and slugging, shared by the
email-processor's region/category logic.

Kept dependency-free so it is trivial to unit test and so the events-api
package (a separate Lambda image) can carry an identical copy.
"""

import re

_ADDR_RE = re.compile(r"<([^>]+)>")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_sender(from_header):
    """
    Derive a stable (sender_key, display) pair from a raw "From" header.

    sender_key is the lowercased email address (the part inside <> when
    present), used as the partition key in scout-senders and as the
    re-tag join key on events. display is the original header text.
    """
    raw = (from_header or "").strip()
    match = _ADDR_RE.search(raw)
    addr = match.group(1) if match else raw
    sender_key = addr.strip().lower()
    return sender_key, (raw or addr)


def slugify(name):
    """Lowercase, hyphenate, and strip a human name into a URL-safe slug."""
    slug = _SLUG_RE.sub("-", (name or "").strip().lower())
    return slug.strip("-")
