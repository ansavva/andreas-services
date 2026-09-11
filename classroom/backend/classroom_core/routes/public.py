"""The one unauthenticated route left: a health check.

**The student reader used to live here** — `GET /api/public/pages/<slug>`
returned a page's sanitized HTML as JSON and the SPA rendered it. That is gone,
along with the sanitizer it depended on.

Students now open a lesson's files directly from a separate host
(`classroom.andreas.services`), served out of S3 by CloudFront exactly as the
teacher uploaded them. The reasoning is in `infra/modules/lesson_hosting`: her
lessons are interactive, so their scripts must run, and once scripts run the
only thing that can keep her session safe is that the lesson is on a different
ORIGIN to the app she signs in to. No amount of sanitizing substitutes for that,
and any amount of sanitizing would have destroyed her formatting.

So there is no application code between a student and a lesson any more, which
is also why this file no longer sets a Content-Security-Policy: the headers are
CloudFront's now.
"""

from flask import Blueprint

from classroom_core.routes._shared import ok

bp = Blueprint("public", __name__, url_prefix="/api/public")


@bp.get("/health")
def health():
    return ok({"status": "ok"})
