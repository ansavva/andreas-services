"""
Pure helpers for sender normalization and slugging.

This is an intentional copy of the email-processor's taxonomy module — the two
Lambdas ship as independent images and do not share a package.
"""

import re

_ADDR_RE = re.compile(r"<([^>]+)>")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_sender(from_header):
    """Derive a stable (sender_key, display) pair from a raw "From" header."""
    raw = (from_header or "").strip()
    match = _ADDR_RE.search(raw)
    addr = match.group(1) if match else raw
    sender_key = addr.strip().lower()
    return sender_key, (raw or addr)


def slugify(name):
    """Lowercase, hyphenate, and strip a human name into a URL-safe slug."""
    slug = _SLUG_RE.sub("-", (name or "").strip().lower())
    return slug.strip("-")
