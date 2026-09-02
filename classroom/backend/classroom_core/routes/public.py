"""The anonymous student-facing reader.

This is the only unauthenticated route in the service. It returns a published
page's sanitized HTML together with a restrictive Content-Security-Policy.

The CSP is the second of the two XSS layers described in ``utils.html``. The
sanitizer should already have removed anything executable; this header means
that even if something slipped past it, the browser will not run it. ``script-src
'none'`` blocks inline and remote script alike, and ``sandbox`` drops the page
into an opaque origin so it cannot reach our cookies or storage.
"""

from flask import Blueprint, jsonify

from classroom_core.routes._shared import not_found, ok
from classroom_core.services import pages

bp = Blueprint("public", __name__, url_prefix="/api/public")

_READER_CSP = (
    "default-src 'none'; "
    "img-src https: data:; "
    "style-src 'unsafe-inline'; "
    "font-src https:; "
    "script-src 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'none'; "
    "base-uri 'none'; "
    "sandbox allow-popups"
)


@bp.get("/pages/<slug>")
def read_page(slug):
    page = pages.get_published_page(slug)
    if page is None:
        # Deliberately the same answer for "never existed" and "withdrawn", so
        # the endpoint does not confirm that a slug is real to someone probing.
        return not_found("page not found")

    response = jsonify(page)
    response.headers["Content-Security-Policy"] = _READER_CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response, 200


@bp.get("/health")
def health():
    return ok({"status": "ok"})
