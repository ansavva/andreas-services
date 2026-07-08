"""Intake ("scoped quote in 48 hours") submissions — the primary money path.

Validates and persists a prospect's request, and lists submissions back for the
admin console. No email is sent (submissions are reviewed in the dashboard).
"""

import re

from website_core.repositories import store
from website_core.errors import ValidationError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Free-text fields we accept, with sane caps to keep rows small and safe.
_MAX = {"name": 200, "email": 320, "company": 200, "budget": 100, "message": 5000}


def _clean(payload, key):
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()[: _MAX[key]]


def create_submission(payload, source_page=None):
    """Validate and store one submission. Returns the stored (public) item."""
    email = _clean(payload, "email")
    message = _clean(payload, "message")

    if not _EMAIL_RE.match(email):
        raise ValidationError("A valid email is required.")
    if not message:
        raise ValidationError("Tell me what you're trying to do.")

    return store.put_submission(
        {
            "name": _clean(payload, "name"),
            "email": email,
            "company": _clean(payload, "company"),
            "budget": _clean(payload, "budget"),
            "message": message,
            "source_page": (str(source_page).strip()[:200] if source_page else ""),
        }
    )


def list_submissions(limit=50, cursor=None):
    """Return {submissions, next_cursor} newest-first for the admin console."""
    limit = max(1, min(int(limit), 100))
    items, next_cursor = store.list_submissions(limit=limit, cursor=cursor)
    return {"submissions": items, "next_cursor": next_cursor}
