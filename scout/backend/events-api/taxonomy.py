"""
Pure helpers for sender normalization and slugging.

This is an intentional copy of the email-processor's taxonomy module — the two
Lambdas ship as independent images and do not share a package.
"""

import re
import unicodedata

_ADDR_RE = re.compile(r"<([^>]+)>")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+")


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


def normalize_title(title):
    """Normalize an event title for duplicate detection: NFKC fold, lowercase,
    strip punctuation, drop a single leading article, collapse whitespace."""
    text = unicodedata.normalize("NFKC", title or "").lower().strip()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return _LEADING_ARTICLE_RE.sub("", text)


def normalize_name(name):
    """Normalize a location/label name for fuzzy matching and search keys."""
    text = unicodedata.normalize("NFKC", name or "").lower().strip()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def dup_key(title, event_date, location_id=None):
    """Deterministic duplicate-detection key: normalized title | date | location.

    Computed per occurrence — a sub-event uses its own date, a single-date event
    its start date. Matched against live events via the dedup GSI.
    """
    return f"{normalize_title(title)}|{(event_date or '').strip()}|{location_id or 'none'}"
