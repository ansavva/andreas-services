"""Newsletter capture — the owned-audience asset (Phase 2).

Thin validation over the Kit adapter; the site posts every signup here.
"""

import re

from website_core.clients.external import kit
from website_core.errors import ValidationError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def subscribe(payload):
    """Validate and forward a newsletter signup to Kit. Returns {status}."""
    email = str(payload.get("email") or "").strip()
    first_name = str(payload.get("first_name") or "").strip()[:200] or None

    if not _EMAIL_RE.match(email):
        raise ValidationError("A valid email is required.")

    kit.subscribe(email, first_name=first_name)
    return {"status": "subscribed", "email": email}
