from studio_core.app_factory import create_app


def _client():
    return create_app().test_client()


def test_health():
    resp = _client().get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_options_preflight():
    resp = _client().options("/api/tree")
    assert resp.status_code == 204
    assert "Access-Control-Allow-Origin" in resp.headers


def test_stage_prefixed_path_still_routes(media_bucket):
    """A direct stage invoke arrives as /prod/api/... — the middleware strips it."""
    resp = _client().get("/prod/api/tree?prefix=media/")
    assert resp.status_code == 200


def test_tree(media_bucket):
    resp = _client().get("/api/tree?prefix=media/fred/originals/")
    assert resp.status_code == 200
    assert len(resp.get_json()["files"]) == 2


def test_tree_rejects_escape(media_bucket):
    resp = _client().get("/api/tree?prefix=../elsewhere")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_reel(media_bucket):
    resp = _client().get("/api/reel?prefix=media/fred/")
    assert resp.status_code == 200
    assert all(item["kind"] in ("image", "video") for item in resp.get_json()["items"])


def test_asset_missing_key_is_404(media_bucket):
    resp = _client().get("/api/asset?key=media/fred/originals/nope.webp")
    assert resp.status_code == 404


def test_asset_rejects_bad_disposition(media_bucket):
    resp = _client().get("/api/asset?key=media/fred/profile.md&disposition=evil")
    assert resp.status_code == 400


def test_text_rejects_binary(media_bucket):
    resp = _client().get("/api/text?key=media/fred/originals/fred_1.webp")
    assert resp.status_code == 400


def test_unknown_route_is_404():
    resp = _client().get("/api/nope")
    assert resp.status_code == 404
