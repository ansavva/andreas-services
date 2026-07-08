from decimal import Decimal

from website_core.clients.external import kit
from website_core.app_factory import create_app
from website_core.services import intake


def _client():
    return create_app().test_client()


def test_options_preflight():
    resp = _client().options("/api/intake")
    assert resp.status_code == 204
    assert "Access-Control-Allow-Origin" in resp.headers


def test_intake_created(intake_table):
    resp = _client().post("/api/intake", json={"email": "sam@acme.com", "message": "help"})
    assert resp.status_code == 201
    assert resp.get_json()["email"] == "sam@acme.com"


def test_intake_validation_400(intake_table):
    resp = _client().post("/api/intake", json={"email": "x", "message": "y"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_admin_submissions(intake_table):
    intake.create_submission({"email": "sam@acme.com", "message": "help"})
    resp = _client().get("/api/admin/submissions")
    assert resp.status_code == 200
    assert len(resp.get_json()["submissions"]) == 1


def test_admin_submissions_serializes_decimals(monkeypatch):
    monkeypatch.setattr(
        intake,
        "list_submissions",
        lambda limit=50, cursor=None: {
            "submissions": [{"score": Decimal("2"), "ratio": Decimal("1.5")}]
        },
    )
    resp = _client().get("/api/admin/submissions")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["submissions"][0]["score"] == 2
    assert body["submissions"][0]["ratio"] == 1.5


def test_store_uses_local_dynamodb_endpoint(monkeypatch):
    from website_core.repositories import dynamodb

    monkeypatch.setenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8001")
    dynamodb._dynamodb = None
    try:
        assert dynamodb.resource().meta.client.meta.endpoint_url == "http://localhost:8001"
    finally:
        dynamodb._dynamodb = None


def test_subscribe_route(monkeypatch):
    monkeypatch.setattr(kit, "subscribe", lambda email, first_name=None: {"ok": True})
    resp = _client().post("/api/subscribe", json={"email": "sam@acme.com"})
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "subscribed"


def test_unknown_route_404(intake_table):
    resp = _client().get("/api/nope")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Not found"}


def test_route_handles_custom_domain_base_path(intake_table):
    resp = _client().post(
        "/prod/api/intake",
        json={"email": "sam@acme.com", "message": "help"},
    )
    assert resp.status_code == 201
