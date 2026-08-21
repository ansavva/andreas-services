import json

from studio_core.app_factory import create_app
from studio_core.handlers.aws.api.api_handler import handler


def _client():
    return create_app().test_client()


def _unsigned(value):
    """A response with its presigned URLs dropped — two calls sign two URLs."""
    if isinstance(value, dict):
        return {key: _unsigned(item) for key, item in value.items() if key != "url"}
    if isinstance(value, list):
        return [_unsigned(item) for item in value]
    return value


def test_health():
    resp = _client().get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_options_preflight():
    resp = _client().options("/api/tree")
    assert resp.status_code == 204
    assert "Access-Control-Allow-Origin" in resp.headers


def test_stage_prefixed_path_still_routes(catalog_tree):
    """A direct stage invoke arrives as /prod/api/... — the middleware strips it."""
    resp = _client().get("/prod/api/tree?prefix=characters/")
    assert resp.status_code == 200


def test_tree_with_no_prefix_opens_on_the_library_root(catalog_tree):
    """What the app requests first, and what broke when `media/` went away.

    The empty prefix used to mean the bucket root and now means the library's
    root node. Both answer to the same request, which is why the SPA needed no
    change for #309.
    """
    resp = _client().get("/api/tree")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["prefix"] == ""
    # Newest-first, on the folders' own `created_at` — a folder is a row now and
    # is stamped like anything else.
    assert [f["name"] for f in body["folders"]] == ["projects", "phrasebook", "characters"]


def test_tree(catalog_tree):
    resp = _client().get("/api/tree?prefix=characters/subject-a/seed/")
    assert resp.status_code == 200
    assert len(resp.get_json()["files"]) == 2


def test_tree_takes_a_node_id_instead_of_a_prefix(catalog_tree):
    """The cold-load address: a share link carries an id and no path (#313).

    Same folder, same body — including `prefix`, which is read back off the
    breadcrumb walk rather than echoed from the request.
    """
    by_prefix = _client().get("/api/tree?prefix=characters/subject-a/seed/").get_json()
    node_id = next(
        crumb["id"] for crumb in by_prefix["breadcrumbs"] if crumb["name"] == "seed"
    )

    by_node = _client().get(f"/api/tree?node={node_id}").get_json()

    assert _unsigned(by_node) == _unsigned(by_prefix)
    assert by_node["prefix"] == "characters/subject-a/seed/"


def test_tree_refuses_a_prefix_and_a_node_together(catalog_tree):
    """Two addresses that can disagree. Refused rather than resolved by rule."""
    node_id = _client().get("/api/tree").get_json()["folders"][0]["id"]
    resp = _client().get(f"/api/tree?prefix=characters/&node={node_id}")

    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_reel_takes_a_node_id_too(catalog_tree):
    by_prefix = _client().get("/api/reel?prefix=characters/subject-a/").get_json()
    node_id = next(
        crumb["id"] for crumb in _client()
        .get("/api/tree?prefix=characters/subject-a/")
        .get_json()["breadcrumbs"]
        if crumb["name"] == "subject-a"
    )

    assert _unsigned(_client().get(f"/api/reel?node={node_id}").get_json()) == _unsigned(by_prefix)


def test_tree_on_a_path_that_names_nothing_is_404(catalog_tree):
    """`..` used to be refused as a string before it could be looked up.

    `keys.clean_prefix` rejected it, and did so as a 400. It is now looked up
    like any other name and found to be nothing — which it always was, since
    `keys.clean_name` refuses a `..` on the way in.
    """
    resp = _client().get("/api/tree?prefix=../elsewhere")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_reel(catalog_tree):
    resp = _client().get("/api/reel?prefix=characters/subject-a/")
    assert resp.status_code == 200
    assert all(item["kind"] in ("image", "video") for item in resp.get_json()["items"])


def test_asset_missing_key_is_404(media_bucket):
    resp = _client().get("/api/asset?key=characters/subject-a/seed/nope.webp")
    assert resp.status_code == 404


def test_asset_rejects_bad_disposition(media_bucket):
    resp = _client().get("/api/asset?key=characters/subject-a/profile.yaml&disposition=evil")
    assert resp.status_code == 400


def test_text_rejects_binary(media_bucket):
    resp = _client().get("/api/text?key=characters/subject-a/seed/subject-a_1.webp")
    assert resp.status_code == 400


def test_unknown_route_is_404():
    resp = _client().get("/api/nope")
    assert resp.status_code == 404


def test_tree_accepts_a_sort(catalog_tree):
    resp = _client().get("/api/tree?prefix=characters/subject-a/seed/&sort=name_desc")
    assert resp.status_code == 200
    assert [f["name"] for f in resp.get_json()["files"]] == ["subject-a_2.webp", "subject-a_1.webp"]


def test_tree_rejects_an_unknown_sort(catalog_tree):
    assert _client().get("/api/tree?sort=sideways").status_code == 400


# ---------------------------------------------------------------------------
# Writes
#
# **On `catalog_tree` rather than `media_bucket` since #316.** These routes write
# rows now, so the fixture has to hold the rows; the bucket is still there
# because a copy and a text save move real bytes.
#
# What they send is unchanged. `prefix`, `key` and `destination` were always the
# slash-joined name path a listing hands back — for material written before the
# catalog it happened to equal the S3 key, and these requests are the proof that
# the SPA needed no change.
# ---------------------------------------------------------------------------

RUN = "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1/"


def test_create_folder(catalog_tree):
    resp = _client().post("/api/folder", json={"prefix": "characters/subject-a/", "name": "keepers"})
    assert resp.status_code == 201
    assert resp.get_json()["prefix"] == "characters/subject-a/keepers/"


def test_create_folder_conflict_is_409(catalog_tree):
    """A transaction condition failure, not a listing this route did first."""
    resp = _client().post("/api/folder", json={"prefix": "characters/subject-a/", "name": "seed"})
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_rename_object(catalog_tree):
    resp = _client().patch(
        "/api/object",
        json={"key": f"{RUN}output/wave-porch.jpeg", "name": "keeper.jpeg"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["key"] == f"{RUN}output/keeper.jpeg"


def test_rename_object_rejects_a_slash(catalog_tree):
    resp = _client().patch(
        "/api/object", json={"key": f"{RUN}output/wave-porch.jpeg", "name": "a/b.jpeg"}
    )
    assert resp.status_code == 400


def test_rename_folder(catalog_tree):
    resp = _client().patch("/api/folder", json={"prefix": RUN, "name": "wave-porch-final"})
    assert resp.status_code == 200
    # No `objects` count: a rename changes one name and moves nothing beneath it.
    assert resp.get_json() == {
        "prefix": "projects/subject-a/runs/wave-porch-final/",
        "name": "wave-porch-final",
        "renamed": True,
    }


def test_move_objects(catalog_tree):
    resp = _client().post(
        "/api/objects/move",
        json={"keys": [f"{RUN}output/wave-porch.jpeg"], "destination": "characters/subject-a/"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["keys"] == ["characters/subject-a/wave-porch.jpeg"]


def test_move_objects_conflict_is_409(catalog_tree):
    resp = _client().post(
        "/api/objects/move",
        json={
            "keys": ["characters/subject-a/reference/subject-a_1.webp"],
            "destination": "characters/subject-a/seed/",
        },
    )
    assert resp.status_code == 409


def test_move_folder(catalog_tree):
    resp = _client().post(
        "/api/folder/move", json={"prefix": RUN, "destination": "projects/misc/runs/"}
    )
    assert resp.status_code == 200
    # `descendants` replaces `objects`, and counts a different thing: no object
    # moved, and what the move touched is the `path` on every row beneath it.
    assert resp.get_json()["descendants"] == 4


def test_move_folder_into_itself_is_400(catalog_tree):
    resp = _client().post("/api/folder/move", json={"prefix": RUN, "destination": RUN})
    assert resp.status_code == 400


def test_update_text(catalog_tree):
    resp = _client().patch(
        "/api/text",
        json={"key": "characters/subject-a/profile.yaml", "content": "name: Subject Alt\n"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["bytes"] == len(b"name: Subject Alt\n")

    reread = _client().get("/api/text?key=characters/subject-a/profile.yaml")
    assert reread.get_json()["content"] == "name: Subject Alt\n"


def test_update_text_on_a_binary_key_is_400(catalog_tree):
    resp = _client().patch(
        "/api/text", json={"key": f"{RUN}output/wave-porch.jpeg", "content": "nope"}
    )
    assert resp.status_code == 400


def test_update_text_on_a_missing_key_is_404(catalog_tree):
    resp = _client().patch(
        "/api/text", json={"key": "characters/subject-a/nowhere.md", "content": "# new"}
    )
    assert resp.status_code == 404


def test_delete_objects_takes_a_body(catalog_tree):
    resp = _client().delete(
        "/api/objects", json={"keys": [f"{RUN}output/wave-porch.jpeg"]}
    )
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 1


def test_delete_objects_without_a_body_is_400(catalog_tree):
    assert _client().delete("/api/objects").status_code == 400


def test_delete_folder(catalog_tree):
    resp = _client().delete("/api/folder", json={"prefix": RUN})
    assert resp.status_code == 200
    # Rows, not objects: the run folder, its `output` folder and its three files.
    assert resp.get_json()["deleted"] == 5


def test_delete_folder_refuses_the_root(catalog_tree):
    assert _client().delete("/api/folder", json={"prefix": ""}).status_code == 400
    # And with no prefix at all, which resolves *to* the root.
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


def test_copy_objects(catalog_tree):
    _client().post("/api/folder", json={"prefix": "projects/subject-a/", "name": "input"})
    resp = _client().post(
        "/api/objects/copy",
        json={"keys": [f"{RUN}output/wave-porch.jpeg"], "destination": "projects/subject-a/input/"},
    )

    assert resp.status_code == 201
    assert resp.get_json()["keys"] == ["projects/subject-a/input/wave-porch.jpeg"]


def test_copy_objects_takes_anything_in_the_library(catalog_tree):
    """Unlike favouriting, which was images and video inside a project only."""
    _client().post("/api/folder", json={"prefix": "projects/subject-a/", "name": "input"})
    resp = _client().post(
        "/api/objects/copy",
        json={
            "keys": ["characters/subject-a/seed/subject-a_1.webp"],
            "destination": "projects/subject-a/input/",
        },
    )
    assert resp.status_code == 201


def test_copy_objects_without_a_body_is_400(catalog_tree):
    assert _client().post("/api/objects/copy").status_code == 400


# ---------------------------------------------------------------------------
# The Lambda path, which the test client above cannot stand in for.
#
# Every test in this file so far drives `create_app().test_client()`, and Werkzeug
# always sets `Content-Length` on a request it builds. Production does not: API
# Gateway's proxy event omits the header, Mangum forwards the headers verbatim,
# and `asgiref` sets `CONTENT_LENGTH` only from a header — so the body arrived
# intact and Flask was told to read none of it. Every write answered 400 naming
# its own field as missing while all 200-odd tests passed.
#
# These go through the real `Mangum(WsgiToAsgi(app))` handler with the header
# absent, because that is the only shape that reproduces it.
# ---------------------------------------------------------------------------


def _proxy_event(method: str, path: str, body: dict | None = None) -> dict:
    """An API Gateway REST proxy event, shaped like the deployed API's.

    Deliberately no `Content-Length` in `headers` — that omission is the whole
    point, and it is copied from the integration request of the live API.
    """
    return {
        "resource": "/api/{proxy+}",
        "path": path,
        "httpMethod": method,
        "headers": {"Content-Type": "application/json"},
        "multiValueHeaders": {"Content-Type": ["application/json"]},
        "queryStringParameters": None,
        "multiValueQueryStringParameters": None,
        "pathParameters": {"proxy": path.removeprefix("/api/")},
        "stageVariables": None,
        "requestContext": {
            "resourcePath": "/api/{proxy+}",
            "httpMethod": method,
            "path": path,
            "stage": "prod",
            "protocol": "HTTP/1.1",
            "requestId": "test",
            "apiId": "test",
            "identity": {"sourceIp": "127.0.0.1"},
        },
        "body": None if body is None else json.dumps(body),
        "isBase64Encoded": False,
    }


def _invoke(method: str, path: str, body: dict | None = None):
    response = handler(_proxy_event(method, path, body), None)
    return response["statusCode"], json.loads(response["body"])


def test_lambda_reads_a_json_body_without_a_content_length_header(catalog_tree):
    """The move from the bug report: a good body must not read as a missing one."""
    status, body = _invoke(
        "POST",
        "/api/objects/move",
        {
            "keys": ["characters/subject-a/seed/subject-a_1.webp"],
            "destination": "characters/subject-b/corpus/",
        },
    )

    assert status == 200, body
    assert body["moved"] == 1
    assert body["keys"] == ["characters/subject-b/corpus/subject-a_1.webp"]


def test_lambda_body_reaches_every_write_verb(catalog_tree):
    """POST, PATCH and DELETE all carry bodies, and all three were broken."""
    assert _invoke("POST", "/api/folder", {"prefix": "projects/", "name": "fresh"})[0] == 201
    assert _invoke(
        "POST",
        "/api/objects/copy",
        {
            "keys": ["characters/subject-a/seed/subject-a_1.webp"],
            "destination": "characters/subject-a/reference/",
        },
    )[0] == 201
    assert _invoke(
        "PATCH",
        "/api/object",
        {"key": "characters/subject-a/profile.yaml", "name": "bible.yaml"},
    )[0] == 200
    assert _invoke(
        "PATCH",
        "/api/text",
        {"key": "phrasebook/wording.yaml", "content": "greeting: hi\n"},
    )[0] == 200
    assert _invoke(
        "DELETE",
        "/api/objects",
        {"keys": ["characters/subject-a/seed/subject-a_2.webp"]},
    )[0] == 200


def test_lambda_still_reports_a_genuinely_empty_body(catalog_tree):
    """The validation the bug was impersonating must survive the fix."""
    status, body = _invoke("POST", "/api/objects/move", {"keys": [], "destination": "projects/"})
    assert status == 400
    assert body["error"] == "keys must be a non-empty list"


def test_lambda_get_needs_no_body(catalog_tree):
    """A bodyless request must not acquire a phantom length."""
    status, body = _invoke("GET", "/api/tree")
    assert status == 200
    assert body["prefix"] == ""
