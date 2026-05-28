"""Runtime configuration helpers.

Tiny accessors for env-driven values used across serialization and handlers.
Kept here (pure, no AWS) so it can be imported anywhere without coupling.
"""

import os


def public_api_base():
    """Absolute public base URL of this Lambda's API (no trailing slash).

    Set by `SCOUT_PUBLIC_API_URL` per env (matches the frontend's `VITE_API_URL`,
    e.g. `https://scout-api.andreas.services/api`). Returns "" when unconfigured
    (unit tests) so serialization falls back to relative paths.
    """
    return os.environ.get("SCOUT_PUBLIC_API_URL", "").rstrip("/")
