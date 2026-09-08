"""Local dev server: Flask on :8001, standing in for API Gateway.

**In production the gateway is the authorizer.** It verifies the ID token and
attaches the claims to the Lambda event, which is why ``classroom_core.auth``
verifies no signature of its own and only refuses to *guess* an identity. Run
the Flask app directly and there is no gateway, so every ``/api/pages`` call
answers 401 and local development of the teacher's workspace is impossible.

This module is the missing half. It wraps the app in a WSGI middleware that
does what ``infra/modules/api_gateway`` does, and nothing more:

* ``/api/public/*`` — no authorizer, ``GET`` only.
* ``/api/pages*``   — a verified Cognito identity, except ``OPTIONS``, which
  the browser sends without an ``Authorization`` header.
* anything else     — 403, because the gateway routes nothing else.

Mirroring the route split matters as much as mirroring the auth. A local server
that answered ``POST /api/public/pages`` would let a change through that
production refuses, and the split *is* classroom's security model.

**Dev only.** ``handlers/aws/api/api_handler.py`` is the deployed entrypoint;
this tree is excluded from the image by ``.dockerignore`` and its PyJWT
dependency lives in the ``dev`` group, so nothing here can reach production.

Started by ``scripts/dev-up.sh``, which exports the pool from this machine's
Terraform state.
"""

import json
import os
import sys

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import jwt  # noqa: E402
from jwt import PyJWKClient  # noqa: E402

from classroom_core.app_factory import create_app  # noqa: E402

_PUBLIC_PREFIX = "/api/public/"
_PAGES_PREFIX = "/api/pages"
_LESSON_PREFIX = "/lesson/"


def _config() -> tuple[str, str, str]:
    """The pool this server verifies against, or a refusal naming the fix.

    No defaults. A pool id that is merely *wrong* rejects every caller, and one
    naming a different pool would admit that pool's teachers — so there is no
    value worth guessing.
    """
    region = os.environ.get("AWS_REGION") or os.environ["AWS_DEFAULT_REGION"]
    try:
        return os.environ["CLASSROOM_COGNITO_USER_POOL_ID"], os.environ["CLASSROOM_COGNITO_CLIENT_ID"], region
    except KeyError as missing:
        sys.exit(
            f"{missing.args[0]} is not set, so no token can be verified.\n"
            "Start this through ./classroom/scripts/dev-up.sh, which reads both "
            "from this machine's dev stack."
        )


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
    """Verify like the Cognito authorizer, route like the REST API."""

    def __init__(self, app, pool_id: str, client_id: str, region: str):
        self.app = app
        self.client_id = client_id
        self.issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
        # Lazily fetched and then cached by PyJWKClient itself; constructing it
        # makes no network call, so an offline start still reaches the public
        # reader.
        self.jwks = PyJWKClient(f"{self.issuer}/.well-known/jwks.json")

    def _claims(self, environ) -> dict | None:
        header = environ.get("HTTP_AUTHORIZATION", "")
        # The SPA sends the raw token; `Bearer <token>` is what curl users type.
        token = header[7:].strip() if header[:7].lower() == "bearer " else header.strip()
        if not token:
            return None
        try:
            claims = jwt.decode(
                token,
                self.jwks.get_signing_key_from_jwt(token).key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
            )
        except Exception:  # noqa: BLE001 - PyJWT raises a family, all meaning "no"
            return None
        # **The ID token, not the access token.** A Cognito access token is
        # signed by the same pool and passes every check above, but carries no
        # `email` and — more to the point — the deployed authorizer rejects it.
        # Accepting it here would make local development succeed where
        # production 401s.
        return claims if claims.get("token_use") == "id" else None

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
            if method == "OPTIONS":
                # Unauthenticated by design: the browser sends the preflight
                # without an Authorization header, so an authorizer here would
                # fail every cross-origin write before it was ever made.
                return self.app(environ, start_response)
            claims = self._claims(environ)
            if claims is None:
                return _deny(start_response, "401 Unauthorized", "Unauthorized")
            # Where `classroom_core.auth` looks. The v1 (REST API) shape, which
            # is the gateway classroom actually deploys.
            environ["aws.event"] = {"requestContext": {"authorizer": {"claims": claims}}}
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
app.wsgi_app = ApiGatewayStandIn(app.wsgi_app, *_config())


if __name__ == "__main__":
    # 8001, matching `frontend/.env.local.example`. Not 8000: studio's API is
    # there, and both are routinely up at once on one machine.
    app.run(debug=True, host="127.0.0.1", port=int(os.getenv("PORT", "8001")))
