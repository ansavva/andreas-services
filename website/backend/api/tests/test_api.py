import json

from website_core.adapters import kit
from website_core.domain import intake
from website_core.handlers import api


def _event(method, path, body=None, query=None):
    return {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    }


def test_options_preflight():
    resp = api.lambda_handler(_event("OPTIONS", "/api/intake"), None)
    assert resp["statusCode"] == 204
    assert "Access-Control-Allow-Origin" in resp["headers"]


def test_intake_created(intake_table):
    resp = api.lambda_handler(
        _event("POST", "/api/intake", {"email": "sam@acme.com", "message": "help"}), None
    )
    assert resp["statusCode"] == 201
    assert json.loads(resp["body"])["email"] == "sam@acme.com"


def test_intake_validation_400(intake_table):
    resp = api.lambda_handler(_event("POST", "/api/intake", {"email": "x", "message": "y"}), None)
    assert resp["statusCode"] == 400
    assert "error" in json.loads(resp["body"])


def test_admin_submissions(intake_table):
    intake.create_submission({"email": "sam@acme.com", "message": "help"})
    resp = api.lambda_handler(_event("GET", "/api/admin/submissions"), None)
    assert resp["statusCode"] == 200
    assert len(json.loads(resp["body"])["submissions"]) == 1


def test_subscribe_route(monkeypatch):
    monkeypatch.setattr(kit, "subscribe", lambda email, first_name=None: {"ok": True})
    resp = api.lambda_handler(_event("POST", "/api/subscribe", {"email": "sam@acme.com"}), None)
    assert resp["statusCode"] == 201
    assert json.loads(resp["body"])["status"] == "subscribed"


def test_unknown_route_404(intake_table):
    resp = api.lambda_handler(_event("GET", "/api/nope"), None)
    assert resp["statusCode"] == 404


def test_route_handles_custom_domain_base_path(intake_table):
    # API Gateway custom-domain base-path mapping can prefix the path; the
    # router anchors on "/api/" so it still resolves.
    resp = api.lambda_handler(
        _event("POST", "/prod/api/intake", {"email": "sam@acme.com", "message": "help"}), None
    )
    assert resp["statusCode"] == 201
