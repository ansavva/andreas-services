"""The API as a client sees it: real requests through `create_app()`.

**Every address here is a node id.** `?prefix=`, `?key=` and the whole of the
name-path write surface (`/api/folder`, `/api/object`, `/api/objects/*`,
`PATCH /api/text?key=`) are gone with the entity model — two live addressing
schemes was one more than the service could keep honest, and the exception that
held the second one open (shared material with no catalog node) closed when the
phrasebook became rows and the angle images became nodes.

`GET /api/resolve?path=` is the one thing that still takes a slash-joined name
path, and it is the reason the CLI's spelling keeps working: it turns an
*address* into an id once, so `<slug>/reference/face/<file>` never has to be a
key anywhere.

The write tests run on `catalog_tree` because they write rows; the bucket is
still there because a copy and a text save move real bytes.
"""

import json

from studio_core.app_factory import create_app
from studio_core.handlers.aws.api.api_handler import handler
from tests.conftest import node_id_at


def _client():
    return create_app().test_client()


def _id(path):
    """The fixture node id at one name path.

    Every request below used to carry the path itself. It carries the id now, and
    the readable name lives here — which is also the honest picture of what the
    SPA does: it holds ids and renders names.
    """
    return node_id_at(path)


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
    resp = _client().get(f"/prod/api/tree?node={_id('characters')}")
    assert resp.status_code == 200


def test_tree_with_no_node_opens_on_the_library_root(catalog_tree):
    """What the app requests first, and the one node a client cannot hold first.

    `/api/libraries` deliberately reports id, name and role and **not** the root
    node, so "open the library" has to be answerable without one. That is why
    dropping `?prefix=` did not also drop "no address at all" — the empty prefix
    meant the root, and no `node` still does.
    """
    resp = _client().get("/api/tree")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["prefix"] == ""
    # Newest-first, on the folders' own `created_at` — a folder is a row now and
    # is stamped like anything else.
    assert [f["name"] for f in body["folders"]] == ["projects", "phrasebook", "characters"]


def test_tree(catalog_tree):
    resp = _client().get(f"/api/tree?node={_id('characters/subject-a/seed')}")
    assert resp.status_code == 200
    assert len(resp.get_json()["files"]) == 2


def test_tree_reports_the_prefix_it_composed_not_one_it_was_sent(catalog_tree):
    """**The `prefix` in a response is a rendering, never an echo.**

    It used to be read back off the breadcrumb walk rather than echoed so that
    two spellings of one folder could not answer with two different values.
    There is no spelling to echo any more, and the walk still has to produce the
    same string — that is what every crumb in the SPA is drawn from.
    """
    body = _client().get(f"/api/tree?node={_id('characters/subject-a/seed')}").get_json()

    assert body["prefix"] == "characters/subject-a/seed/"
    assert [crumb["name"] for crumb in body["breadcrumbs"]] == [
        "/",
        "characters",
        "subject-a",
        "seed",
    ]


def test_reel_takes_a_node_id_too(catalog_tree):
    resp = _client().get(f"/api/reel?node={_id('characters/subject-a')}")

    assert resp.status_code == 200
    assert all(item["kind"] in ("image", "video") for item in resp.get_json()["items"])


def test_tree_on_a_node_that_names_nothing_is_404(catalog_tree):
    """An id that names no row, which is the only way to miss now.

    `?prefix=../elsewhere` used to be the interesting case: `keys.clean_prefix`
    refused it as a 400, then #312 made it an ordinary lookup that found nothing.
    There is no path parameter left to traverse with — the walk survives only on
    `/api/resolve`, where `keys.clean_name` has already made `..` a name nothing
    is called.
    """
    resp = _client().get("/api/tree?node=node-nowhere")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_resolve_turns_a_name_path_into_an_id(catalog_tree):
    """The one route that still takes a path, and why it is allowed to.

    Every command the pipeline runs names a subject and a project rather than an
    id, and every `SKILL.md` is written that way. They ask here and get an id —
    an *address*, resolved once, never a key. The S3 object behind whatever comes
    back is `<owner_kind>/<owner_id>/<node_id>.<ext>`, which nothing outside
    `services.catalog` ever sees.
    """
    resp = _client().get("/api/resolve?path=characters/subject-a/seed")

    assert resp.status_code == 200
    assert resp.get_json()["id"] == _id("characters/subject-a/seed")


def test_resolve_names_the_first_segment_that_is_missing(catalog_tree):
    """"No such object: characters/subject-a/nope" beats "no such object: nope".

    The difference is between a message that points at the folder the typo is in
    and one that only repeats the typo.
    """
    resp = _client().get("/api/resolve?path=characters/subject-a/nope/deeper")

    assert resp.status_code == 404
    assert "characters/subject-a/nope" in resp.get_json()["error"]


def test_asset_takes_a_node_id(catalog_tree):
    node_id = _client().get(
        f"/api/tree?node={_id('characters/subject-a')}"
    ).get_json()["files"][0]["id"]

    body = _client().get(f"/api/asset?node={node_id}").get_json()

    assert body["key"] == "characters/subject-a/profile.yaml"
    assert "X-Amz-Signature" in body["url"]


def test_asset_without_a_node_is_400(catalog_tree):
    """**The raw S3 key is gone, and this is what says so at the route.**

    `?key=` was the last query string in the service that became an S3 key, kept
    alive by shared material with no catalog node. `tests/test_keys.py` passes
    just as happily whether or not anything still calls the deleted validator, so
    the assertion that the parameter is not accepted has to be made here.
    """
    resp = _client().get("/api/asset?key=characters/subject-a/profile.yaml")

    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_asset_rejects_bad_disposition(catalog_tree):
    node_id = _id("characters/subject-a/profile.yaml")
    resp = _client().get(f"/api/asset?node={node_id}&disposition=evil")
    assert resp.status_code == 400


def test_text_lives_on_the_node_now(catalog_tree):
    """`GET /api/text?key=` became `GET /api/nodes/<id>/text`, paired with its save.

    That pairing is the whole of #432: the read used to `GetObject` the string it
    was handed while the save walked a name path, so the two agreed only for
    material written before the catalog — a file the editor could save was a file
    the editor could not re-open.
    """
    node_id = _id("characters/subject-a/profile.yaml")

    assert _client().get("/api/text?key=characters/subject-a/profile.yaml").status_code == 404
    assert _client().get(f"/api/nodes/{node_id}/text").get_json()["content"] == (
        "name: Subject A\n"
    )


def test_unknown_route_is_404():
    resp = _client().get("/api/nope")
    assert resp.status_code == 404


def test_tree_accepts_a_sort(catalog_tree):
    resp = _client().get(f"/api/tree?node={_id('characters/subject-a/seed')}&sort=name_desc")
    assert resp.status_code == 200
    assert [f["name"] for f in resp.get_json()["files"]] == ["subject-a_2.webp", "subject-a_1.webp"]


def test_tree_rejects_an_unknown_sort(catalog_tree):
    assert _client().get("/api/tree?sort=sideways").status_code == 400


# ---------------------------------------------------------------------------
# Writes
#
# **All of them are `/api/nodes*` now.** `POST /api/nodes` replaces
# `POST /api/folder`, `PATCH /api/nodes/<id>` replaces both `PATCH /api/object`
# and `PATCH /api/folder`, `POST /api/nodes/move` replaces `/api/objects/move`
# *and* `/api/folder/move`, and `DELETE /api/nodes` replaces `/api/objects` and
# `/api/folder`.
#
# The file/folder split in those pairs was an artefact of S3: moving a prefix
# meant a `CopyObject` per key underneath it and moving an object meant one.
# Neither copies anything now, so the only difference left was the shape of the
# request — and one shape is what the SPA's grid selection actually is.
#
# `tests/test_nodes.py` covers the semantics of each. What is covered here is
# that they are reachable, that a body reaches them, and the statuses.
# ---------------------------------------------------------------------------

RUN = "projects/subject-a/runs/2026-08-04_21-30-54_wave-porch-1x1"


def test_create_folder(catalog_tree):
    resp = _client().post(
        "/api/nodes",
        json={"parent": _id("characters/subject-a"), "name": "keepers", "kind": "folder"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["name"] == "keepers"


def test_create_folder_conflict_is_409(catalog_tree):
    """A transaction condition failure, not a listing this route did first."""
    resp = _client().post(
        "/api/nodes",
        json={"parent": _id("characters/subject-a"), "name": "seed", "kind": "folder"},
    )
    assert resp.status_code == 409
    assert "error" in resp.get_json()


def test_rename_a_file(catalog_tree):
    resp = _client().patch(
        f"/api/nodes/{_id(f'{RUN}/output/wave-porch.jpeg')}", json={"name": "keeper.jpeg"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "keeper.jpeg"


def test_rename_rejects_a_slash(catalog_tree):
    """A rename must not become a move by punctuation.

    `keys.clean_name` refuses the slash rather than escaping it, which is what
    keeps "rename" and "move" two requests all the way down — the destination of
    a move is a folder id, and there is no spelling of a name that can reach one.
    """
    resp = _client().patch(
        f"/api/nodes/{_id(f'{RUN}/output/wave-porch.jpeg')}", json={"name": "a/b.jpeg"}
    )
    assert resp.status_code == 400


def test_rename_a_folder_moves_nothing_beneath_it(catalog_tree):
    """One row changes. `path` names ancestors by id, and a rename changes none.

    This used to report an `objects` count because a prefix rename was a copy and
    a delete per key. There is nothing to count.
    """
    resp = _client().patch(f"/api/nodes/{_id(RUN)}", json={"name": "wave-porch-final"})

    assert resp.status_code == 200
    assert resp.get_json()["name"] == "wave-porch-final"
    listing = _client().get(f"/api/tree?node={_id(f'{RUN}/output')}").get_json()
    assert [f["name"] for f in listing["files"]] == ["wave-porch.jpeg"]


def test_move_nodes(catalog_tree):
    resp = _client().post(
        "/api/nodes/move",
        json={
            "ids": [_id(f"{RUN}/output/wave-porch.jpeg")],
            "destination": _id("characters/subject-a"),
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["moved"] == 1


def test_move_conflict_is_409(catalog_tree):
    resp = _client().post(
        "/api/nodes/move",
        json={
            "ids": [_id("characters/subject-a/reference/subject-a_1.webp")],
            "destination": _id("characters/subject-a/seed"),
        },
    )
    assert resp.status_code == 409


def test_move_takes_a_folder_through_the_same_door(catalog_tree):
    """`/api/folder/move` and `/api/objects/move` were one operation in two routes.

    `descendants` is what the old `objects` count became, and it counts a
    different thing: no object moves, and what the operation touched is the
    `path` on every row beneath the one that did.
    """
    resp = _client().post(
        "/api/nodes/move",
        json={"ids": [_id(RUN)], "destination": _id("projects/misc/runs")},
    )
    assert resp.status_code == 200
    assert resp.get_json()["descendants"] == 4


def test_moving_a_folder_into_itself_is_400(catalog_tree):
    resp = _client().post(
        "/api/nodes/move", json={"ids": [_id(RUN)], "destination": _id(RUN)}
    )
    assert resp.status_code == 400


def test_update_text(catalog_tree):
    node_id = _id("characters/subject-a/profile.yaml")
    resp = _client().patch(
        f"/api/nodes/{node_id}/text", json={"content": "name: Subject Alt\n"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["bytes"] == len(b"name: Subject Alt\n")

    reread = _client().get(f"/api/nodes/{node_id}/text")
    assert reread.get_json()["content"] == "name: Subject Alt\n"


def test_update_text_on_a_binary_node_is_400(catalog_tree):
    resp = _client().patch(
        f"/api/nodes/{_id(f'{RUN}/output/wave-porch.jpeg')}/text", json={"content": "nope"}
    )
    assert resp.status_code == 400


def test_update_text_on_a_node_that_does_not_exist_is_404(catalog_tree):
    resp = _client().patch("/api/nodes/node-nowhere/text", json={"content": "# new"})
    assert resp.status_code == 404


def test_delete_nodes_takes_a_body(catalog_tree):
    resp = _client().delete(
        "/api/nodes", json={"ids": [_id(f"{RUN}/output/wave-porch.jpeg")]}
    )
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 1


def test_delete_nodes_without_a_body_is_400(catalog_tree):
    assert _client().delete("/api/nodes").status_code == 400


def test_delete_a_folder_counts_rows(catalog_tree):
    """Rows, not objects: the run folder, its `output` folder and its three files."""
    resp = _client().delete(f"/api/nodes/{_id(RUN)}")
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 5


def test_delete_refuses_the_library_root(catalog_tree):
    """The root has no `parent_id`, so there is no by-parent item to remove.

    That missing pointer is what makes "rename the library root", "move it" and
    "delete it" all refuse, arrived at from the data rather than from a string
    comparison against a configured prefix.
    """
    root = _client().get("/api/resolve").get_json()["id"]
    assert _client().delete(f"/api/nodes/{root}").status_code == 400


def test_preflight_advertises_the_write_verbs():
    """Covers local dev only — in prod API Gateway's MOCK answers the OPTIONS.

    flask-cors only writes `Access-Control-Allow-Methods` when the request looks
    like a real preflight, which means the `Access-Control-Request-Method` header
    a browser always sends and a bare `client.options()` never does.
    """
    resp = _client().options(
        "/api/nodes",
        headers={
            "Origin": "https://studio.andreas.services",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert resp.status_code == 204
    allowed = resp.headers.get("Access-Control-Allow-Methods", "")
    assert {"PATCH", "DELETE", "POST"} <= {m.strip() for m in allowed.split(",")}


def test_copy_nodes(catalog_tree):
    created = _client().post(
        "/api/nodes",
        json={"parent": _id("projects/subject-a"), "name": "input", "kind": "folder"},
    ).get_json()

    resp = _client().post(
        "/api/nodes/copy",
        json={"ids": [_id(f"{RUN}/output/wave-porch.jpeg")], "destination": created["id"]},
    )

    assert resp.status_code == 201
    assert [node["name"] for node in resp.get_json()["nodes"]] == ["wave-porch.jpeg"]


def test_copy_takes_anything_in_the_library(catalog_tree):
    """Unlike favouriting, which was images and video inside a project only."""
    created = _client().post(
        "/api/nodes",
        json={"parent": _id("projects/subject-a"), "name": "input", "kind": "folder"},
    ).get_json()

    resp = _client().post(
        "/api/nodes/copy",
        json={
            "ids": [_id("characters/subject-a/seed/subject-a_1.webp")],
            "destination": created["id"],
        },
    )
    assert resp.status_code == 201


def test_copy_without_a_body_is_400(catalog_tree):
    assert _client().post("/api/nodes/copy").status_code == 400


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
        "/api/nodes/move",
        {
            "ids": [_id("characters/subject-a/seed/subject-a_1.webp")],
            "destination": _id("characters/subject-b/corpus"),
        },
    )

    assert status == 200, body
    assert body["moved"] == 1


def test_lambda_body_reaches_every_write_verb(catalog_tree):
    """POST, PATCH and DELETE all carry bodies, and all three were broken."""
    assert _invoke(
        "POST", "/api/nodes", {"parent": _id("projects"), "name": "fresh", "kind": "folder"}
    )[0] == 201
    assert _invoke(
        "POST",
        "/api/nodes/copy",
        {
            "ids": [_id("characters/subject-a/seed/subject-a_1.webp")],
            "destination": _id("characters/subject-a/reference"),
        },
    )[0] == 201
    assert _invoke(
        "PATCH",
        f"/api/nodes/{_id('characters/subject-a/profile.yaml')}",
        {"name": "bible.yaml"},
    )[0] == 200
    assert _invoke(
        "PATCH",
        f"/api/nodes/{_id('phrasebook/wording.yaml')}/text",
        {"content": "greeting: hi\n"},
    )[0] == 200
    assert _invoke(
        "POST", "/api/characters", {"slug": "subject-c"}
    )[0] == 201
    assert _invoke(
        "DELETE",
        "/api/nodes",
        {"ids": [_id("characters/subject-a/seed/subject-a_2.webp")]},
    )[0] == 200


def test_the_entity_replace_routes_are_reachable_as_patch(catalog_tree):
    """**The six routes `docs/ENTITY_MODEL.md` spells as PUT, and why they are not.**

    A profile, a reference index, a default set, a project's characters, a
    scene's shots and a movie's scenes all replace a *collection*, which is what
    PUT is for. Adding the verb means changing four places at once — Flask's
    list, the MOCK integration response, and both authorizer gateway responses in
    `modules/api_gateway` — and a verb missing from any of them fails as an
    opaque CORS error with no status, which is the one failure in this service
    that carries no message at all.

    So they are PATCH, exactly as `PATCH /api/text` has been since it was written
    for the same reason. Nothing else changed: same paths, same bodies, same
    whole-collection replace. This pins that a body reaches one of them through
    the real Lambda path, which is the half that was broken before.
    """
    created = _invoke("POST", "/api/characters", {"slug": "subject-d"})[1]

    status, body = _invoke(
        "PATCH",
        f"/api/characters/{created['id']}/default-set",
        {"nodes": [], "rev": created["rev"]},
    )

    assert status == 200, body
    assert body["default_set"] == []


def test_lambda_still_reports_a_genuinely_empty_body(catalog_tree):
    """The validation the bug was impersonating must survive the fix."""
    status, body = _invoke(
        "POST", "/api/nodes/move", {"ids": [], "destination": _id("projects")}
    )
    assert status == 400
    assert body["error"] == "ids must be a non-empty list"


def test_lambda_get_needs_no_body(catalog_tree):
    """A bodyless request must not acquire a phantom length."""
    status, body = _invoke("GET", "/api/tree")
    assert status == 200
    assert body["prefix"] == ""
