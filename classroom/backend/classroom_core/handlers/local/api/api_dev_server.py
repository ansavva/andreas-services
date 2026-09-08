"""Local dev server: Flask on :8001, standing in for API Gateway and the CDN.

Two deployed things are missing on a laptop, and this supplies both:

* **The gateway's ROUTING.** `/api/public/*` is anonymous and GET-only,
  `/api/pages*` is authenticated, and nothing else is routed at all. That split
  is classroom's security model, so a local server that answered
  `POST /api/public/pages` would let through a change production refuses.

* **The lesson CDN.** `/lesson/<id>/…` is served straight out of S3, with the
  directory-index rewrite that is a CloudFront function in production.

**What it deliberately does NOT do any more is fake an identity.** It used to
verify the token here and inject the claims where the gateway would have put
them. That made local development pass while production 401'd every request,
because the claims never actually reach Flask through Mangum — see
`classroom_core/auth.py`. The app validates the token itself now, identically on
a laptop and in Lambda, so this file has no opinion about who the caller is.
"""

import json
import os

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

from classroom_core.app_factory import create_app  # noqa: E402

_PUBLIC_PREFIX = "/api/public/"
_PAGES_PREFIX = "/api/pages"
_LESSON_PREFIX = "/lesson/"


def _deny(start_response, status: str, message: str):
    """The gateway's own wording, so a local failure reads like a deployed one."""
    body = json.dumps({"message": message}).encode()
    start_response(
        status,
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
            # The SPA is a cross-origin caller at :5174, so without this the
            # browser reports a CORS error and hides the 401 underneath it.
            ("Access-Control-Allow-Origin", "*"),
        ],
    )
    return [body]


class ApiGatewayStandIn:
    """Route like the deployed REST API, and nothing more."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "GET")

        # Lesson files, standing in for the student-facing CloudFront.
        # Anonymous by design: a student has no account and never will.
        if path.startswith(_LESSON_PREFIX):
            if method not in ("GET", "HEAD"):
                return _deny(start_response, "403 Forbidden", "Missing Authentication Token")
            return _serve_lesson(path, start_response)

        if path.startswith(_PUBLIC_PREFIX):
            if method not in ("GET", "HEAD"):
                # The gateway declares GET and nothing else on this resource, so
                # a write here is unrouted rather than forbidden by the app.
                return _deny(start_response, "403 Forbidden", "Missing Authentication Token")
            return self.app(environ, start_response)

        if path.startswith(_PAGES_PREFIX):
            # Straight through. The gateway would check a token here; the app
            # does it itself, so there is nothing left to imitate — and imitating
            # it is what hid a production outage last time.
            return self.app(environ, start_response)

        return _deny(start_response, "403 Forbidden", "Missing Authentication Token")


def _serve_lesson(path: str, start_response):
    """Stream one uploaded lesson file straight out of S3.

    **This stands in for CloudFront, not for the API.** In production nothing of
    ours sits between a student and a lesson: the files are served from a
    separate host by CloudFront, byte for byte, with their scripts intact. This
    reproduces that locally so a developer exercises the real shape — including
    the directory index, which is a CloudFront function in production.

    It is deliberately dumb. No sanitizing, no rewriting, no templating: what she
    uploaded is what comes back.
    """
    from classroom_core.repositories import lessons

    key = path.lstrip("/")
    if key.endswith("/"):
        key += lessons.INDEX_FILE
    elif "." not in key.rsplit("/", 1)[-1]:
        key += f"/{lessons.INDEX_FILE}"

    try:
        obj = lessons.client().get_object(Bucket=lessons.bucket(), Key=key)
    except Exception:  # noqa: BLE001 - NoSuchKey, AccessDenied and friends
        return _deny(start_response, "404 Not Found", "Not found")

    payload = obj["Body"].read()
    start_response(
        "200 OK",
        [
            ("Content-Type", obj.get("ContentType", "application/octet-stream")),
            ("Content-Length", str(len(payload))),
            # The headers CloudFront's response policy sets in production. No
            # CSP: lessons are interactive and their scripts must run — the
            # protection is the separate origin, not a header.
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Frame-Options", "DENY"),
        ],
    )
    return [payload]


app = create_app()
app.wsgi_app = ApiGatewayStandIn(app.wsgi_app)


if __name__ == "__main__":
    # 8001, matching `frontend/.env.local.example`. Not 8000: studio's API is
    # there, and both are routinely up at once on one machine.
    app.run(debug=True, host="127.0.0.1", port=int(os.getenv("PORT", "8001")))
