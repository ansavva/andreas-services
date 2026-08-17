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
    resp = _client().get("/prod/api/tree?prefix=characters/")
    assert resp.status_code == 200


def test_tree_with_no_prefix_opens_on_the_bucket_root(media_bucket):
    """What the app requests first, and what broke when `media/` went away."""
    resp = _client().get("/api/tree")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["prefix"] == ""
    # Newest-first is the default sort, and folders have no date to sort by, so
    # the order here is the name descending.
    assert [f["name"] for f in body["folders"]] == ["projects", "phrasebook", "characters"]


def test_tree(media_bucket):
    resp = _client().get("/api/tree?prefix=characters/fred/seed/")
    assert resp.status_code == 200
    assert len(resp.get_json()["files"]) == 2


def test_tree_rejects_escape(media_bucket):
    resp = _client().get("/api/tree?prefix=../elsewhere")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_reel(media_bucket):
    resp = _client().get("/api/reel?prefix=characters/fred/")
    assert resp.status_code == 200
    assert all(item["kind"] in ("image", "video") for item in resp.get_json()["items"])


def test_asset_missing_key_is_404(media_bucket):
    resp = _client().get("/api/asset?key=characters/fred/seed/nope.webp")
    assert resp.status_code == 404


def test_asset_rejects_bad_disposition(media_bucket):
    resp = _client().get("/api/asset?key=characters/fred/profile.yaml&disposition=evil")
    assert resp.status_code == 400


def test_text_rejects_binary(media_bucket):
    resp = _client().get("/api/text?key=characters/fred/seed/fred_1.webp")
    assert resp.status_code == 400


def test_unknown_route_is_404():
    resp = _client().get("/api/nope")
    assert resp.status_code == 404


def test_tree_accepts_a_sort(media_bucket):
    resp = _client().get("/api/tree?prefix=characters/fred/seed/&sort=name_desc")
    assert resp.status_code == 200
    assert [f["name"] for f in resp.get_json()["files"]] == ["fred_2.webp", "fred_1.webp"]


def test_tree_rejects_an_unknown_sort(media_bucket):
    assert _client().get("/api/tree?sort=sideways").status_code == 400


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

RUN = "projects/fred/runs/2026-08-04_21-30-54_wave-porch-1x1/"


def test_create_folder(media_bucket):
    resp = _client().post("/api/folder", json={"prefix": "characters/fred/", "name": "keepers"})
    assert resp.status_code == 201
    assert resp.get_json()["prefix"] == "characters/fred/keepers/"


def test_create_folder_conflict_is_409(media_bucket):
    resp = _client().post("/api/folder", json={"prefix": "characters/fred/", "name": "seed"})
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_rename_object(media_bucket):
    resp = _client().patch(
        "/api/object",
        json={"key": f"{RUN}output/wave-porch.jpeg", "name": "keeper.jpeg"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["key"] == f"{RUN}output/keeper.jpeg"


def test_rename_object_rejects_a_slash(media_bucket):
    resp = _client().patch(
        "/api/object", json={"key": f"{RUN}output/wave-porch.jpeg", "name": "a/b.jpeg"}
    )
    assert resp.status_code == 400


def test_rename_folder(media_bucket):
    resp = _client().patch("/api/folder", json={"prefix": RUN, "name": "wave-porch-final"})
    assert resp.status_code == 200
    assert resp.get_json()["objects"] == 3


def test_delete_objects_takes_a_body(media_bucket):
    resp = _client().delete(
        "/api/objects", json={"keys": [f"{RUN}output/wave-porch.jpeg"]}
    )
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 1


def test_delete_objects_without_a_body_is_400(media_bucket):
    assert _client().delete("/api/objects").status_code == 400


def test_delete_folder(media_bucket):
    resp = _client().delete("/api/folder", json={"prefix": RUN})
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 3


def test_delete_folder_refuses_the_root(media_bucket):
    assert _client().delete("/api/folder", json={"prefix": ""}).status_code == 400
    # And with no prefix at all, which normalises *to* the root.
    assert _client().delete("/api/folder", json={}).status_code == 400


def test_preflight_advertises_the_write_verbs():
    """Covers local dev only — in prod API Gateway's MOCK answers the OPTIONS.

    flask-cors only writes `Access-Control-Allow-Methods` when the request looks
    like a real preflight, which means the `Access-Control-Request-Method` header
    a browser always sends and a bare `client.options()` never does.
    """
    resp = _client().options(
        "/api/objects",
        headers={
            "Origin": "https://studio.andreas.services",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert resp.status_code == 204
    allowed = resp.headers.get("Access-Control-Allow-Methods", "")
    assert {"PATCH", "DELETE", "POST"} <= {m.strip() for m in allowed.split(",")}
