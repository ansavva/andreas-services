"""The three catalog read routes, over the moto-backed catalog table.

Every test drives a real request through `create_app()`, because half of what is
under test is the response itself: which fields arrive, and which status a node
in someone else's library comes back with. Neither is a property of a function
called inside the route.

**The arrangement here uses `services.catalog` and the fixtures do not**, and the
two are deliberate opposites. `tests/conftest.py` and `test_libraries.py` spell
their items out literally so the schema is asserted from outside the module that
implements it; that job is done, by `test_catalog.py`. What is under test here is
a route, so the tree it reads is built with the same writer the API uses — a
three-deep tree written by hand would be a dozen items of noise pinning nothing
these tests are about. The one exception is the second library below, which is
literal because it has to exist without the caller ever being able to write to
it.

`identity.caller_sub` is stubbed, since verifying a real RS256 signature needs a
live Cognito pool and `test_identity.py` already covers the four checks token by
token. It is `before_request` that calls it now rather than the routes — see the
`signed_in` fixture below for why this module overrides `conftest`'s. The 401
test hands the header back to the real parsing.
"""

import pytest

from studio_core import config
from studio_core.app_factory import create_app
from studio_core.errors import NotFoundError
from studio_core.services import catalog, identity
from tests.conftest import CATALOG_LIBRARY, CATALOG_OWNER, CATALOG_ROOT

OTHER_LIBRARY = "lib-0002"
OTHER_ROOT = "node-root-0002"
OTHER_NODE = "node-elsewhere"

_SEED_TIME = "2026-08-19T12:00:00.000000+00:00"

BLOB_KEY = "projects/<project>/runs/2026-08-04_21-30-54_<slug>/output/<slug>.jpeg"


@pytest.fixture(autouse=True)
def signed_in(monkeypatch):
    """Whoever the next request is from. Defaults to the seeded library's owner.

    **Overrides `conftest`'s fixture of the same name**, and the difference is
    the membership read. `conftest.SignedIn` stands in for `identity` *and*
    `catalog` on `app_factory`, which is right for a suite whose tests are not
    about who is in what — they are about listings and moves, and a static
    membership keeps them saying so. Every test in this module is about exactly
    that question: it writes rows and asserts what the hook and the route make of
    them. So only the token half is stubbed here, and `before_request` reads its
    memberships from the moto-backed table like the route does.

    `authenticated = False` hands the header back to the real `caller_sub`
    rather than raising a canned `AuthError`, so the 401 tests still exercise the
    parsing that refuses a missing or bearerless header before a key is fetched.
    """
    real_caller_sub = identity.caller_sub

    class Caller:
        sub = CATALOG_OWNER
        authenticated = True

    caller = Caller()
    monkeypatch.setattr(
        identity,
        "caller_sub",
        lambda header: caller.sub if caller.authenticated else real_caller_sub(header),
    )
    return caller


def _client():
    return create_app().test_client()


def _get(path, **headers):
    """The route, with a header that the stub ignores and the real code needs."""
    return _client().get(path, headers={"Authorization": "Bearer t", **headers})


def _post(path, body, **headers):
    return _client().post(path, json=body, headers={"Authorization": "Bearer t", **headers})


def _patch(path, body, **headers):
    return _client().patch(path, json=body, headers={"Authorization": "Bearer t", **headers})


def _delete(path, **headers):
    return _client().delete(path, headers={"Authorization": "Bearer t", **headers})


def _folder(name, parent=CATALOG_ROOT):
    return catalog.create_node(parent, name, catalog.KIND_FOLDER)


def _file(name, parent=CATALOG_ROOT, **kwargs):
    return catalog.create_node(parent, name, catalog.KIND_FILE, blob_key=BLOB_KEY, **kwargs)


def _second_library(client):
    """A library the caller is not in, holding a root and one node.

    Written literally, and it has to be: the point of it is a node the caller
    could never have created, so building it through `catalog` as the signed-in
    caller would arrange the wrong thing.
    """
    items = [
        {
            "pk": {"S": f"LIB#{OTHER_LIBRARY}"},
            "sk": {"S": "META"},
            "name": {"S": "Archive"},
            "root_node": {"S": OTHER_ROOT},
            "created_at": {"S": _SEED_TIME},
        },
        {
            "pk": {"S": f"NODE#{OTHER_ROOT}"},
            "sk": {"S": "META"},
            "node_id": {"S": OTHER_ROOT},
            "lib": {"S": OTHER_LIBRARY},
            "name": {"S": "Archive"},
            "kind": {"S": "folder"},
            "path": {"S": "/"},
            "created_at": {"S": _SEED_TIME},
            "updated_at": {"S": _SEED_TIME},
        },
        {
            "pk": {"S": f"NODE#{OTHER_NODE}"},
            "sk": {"S": "META"},
            "node_id": {"S": OTHER_NODE},
            "parent_id": {"S": OTHER_ROOT},
            "lib": {"S": OTHER_LIBRARY},
            "name": {"S": "secret.jpeg"},
            "kind": {"S": "file"},
            "blob_key": {"S": BLOB_KEY},
            "path": {"S": f"/{OTHER_ROOT}/"},
            "created_at": {"S": _SEED_TIME},
            "updated_at": {"S": _SEED_TIME},
        },
        {
            "pk": {"S": f"NODE#{OTHER_ROOT}"},
            "sk": {"S": "NAME#secret.jpeg"},
            "node_id": {"S": OTHER_NODE},
            "lib": {"S": OTHER_LIBRARY},
            "kind": {"S": "file"},
            "path": {"S": f"/{OTHER_ROOT}/"},
            "created_at": {"S": _SEED_TIME},
        },
    ]
    for item in items:
        client.put_item(TableName=config.catalog_table(), Item=item)


# ──────────────────────────── GET /api/nodes ────────────────────────────


def test_listing_a_folder_returns_its_children(catalog_table, signed_in):
    """Folders and files in one array, name-ascending, `kind` telling them apart."""
    _folder("characters")
    _file("notes.txt")
    _folder("projects")

    resp = _get(f"/api/nodes?parent={CATALOG_ROOT}")

    assert resp.status_code == 200
    assert [(entry["name"], entry["kind"]) for entry in resp.get_json()] == [
        ("characters", "folder"),
        ("notes.txt", "file"),
        ("projects", "folder"),
    ]


def test_listing_carries_size_and_content_type(catalog_table, signed_in):
    """The two attributes the by-parent projection does not hold.

    This is the assertion the `BatchGetItem` in `list_nodes` exists for: both
    live on the record half only, so a listing built from `catalog.children`
    alone would return every file without a size and nothing would say so.
    """
    _file("clip.mp4", size=4096, content_type="video/mp4")

    entry = _get(f"/api/nodes?parent={CATALOG_ROOT}").get_json()[0]

    assert entry["size"] == 4096
    assert entry["content_type"] == "video/mp4"


def test_a_folder_carries_no_size(catalog_table, signed_in):
    """Absent rather than null — a folder has no bytes, not zero bytes."""
    _folder("characters")

    entry = _get(f"/api/nodes?parent={CATALOG_ROOT}").get_json()[0]

    assert "size" not in entry
    assert "content_type" not in entry


def test_listing_never_returns_blob_key(catalog_table, signed_in):
    """The one field that must not leave, checked on the route that lists many."""
    _file("clip.mp4")

    entry = _get(f"/api/nodes?parent={CATALOG_ROOT}").get_json()[0]

    assert "blob_key" not in entry
    assert BLOB_KEY not in _get(f"/api/nodes?parent={CATALOG_ROOT}").get_data(as_text=True)


def test_listing_never_returns_path(catalog_table, signed_in):
    """`path` is a rebuildable index; `parent_id` is the answer a client gets."""
    _folder("characters")

    entry = _get(f"/api/nodes?parent={CATALOG_ROOT}").get_json()[0]

    assert "path" not in entry
    assert entry["parent_id"] == CATALOG_ROOT


def test_listing_an_empty_folder_is_an_empty_list(catalog_table, signed_in):
    empty = _folder("characters")

    resp = _get(f"/api/nodes?parent={empty['node_id']}")

    assert resp.status_code == 200
    assert resp.get_json() == []


def test_listing_more_children_than_one_batch(catalog_table, signed_in):
    """Past `BATCH_GET_KEYS`, so the chunking in `catalog.records` is exercised.

    A folder of 101 files needs two `BatchGetItem` calls, and a `records` that
    forgot to chunk would either be rejected by DynamoDB or quietly return the
    first hundred. Both failures look like a short listing, which is why the
    count is asserted and not just the shape.
    """
    folder = _folder("corpus")
    for index in range(101):
        _file(f"frame_{index:03d}.webp", parent=folder["node_id"], size=index)

    entries = _get(f"/api/nodes?parent={folder['node_id']}").get_json()

    assert len(entries) == 101
    assert all("size" in entry for entry in entries)


def test_listing_a_missing_parent_is_404(catalog_table, signed_in):
    resp = _get("/api/nodes?parent=node-nope")

    assert resp.status_code == 404


def test_listing_without_a_parent_is_400(catalog_table, signed_in):
    resp = _get("/api/nodes")

    assert resp.status_code == 400


def test_listing_another_callers_library_is_403(catalog_table, signed_in):
    """The parent is read for its `lib`, and the `lib` is what is checked."""
    _second_library(catalog_table)

    resp = _get(f"/api/nodes?parent={OTHER_ROOT}")

    assert resp.status_code == 403


# ──────────────────────── GET /api/nodes/<id> ────────────────────────


def test_fetching_one_node(catalog_table, signed_in):
    created = _file("clip.mp4", size=17, content_type="video/mp4")

    resp = _get(f"/api/nodes/{created['node_id']}")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "id": created["node_id"],
        "lib": CATALOG_LIBRARY,
        "parent_id": CATALOG_ROOT,
        "name": "clip.mp4",
        "kind": "file",
        "size": 17,
        "content_type": "video/mp4",
        "created_at": created["created_at"],
        "updated_at": created["updated_at"],
    }


def test_fetching_a_node_never_returns_blob_key(catalog_table, signed_in):
    """Asserted separately from the shape above so it fails on its own terms.

    The equality test would catch this too, and would report it as "the response
    changed". This one reports it as what it is.
    """
    created = _file("clip.mp4")

    body = _get(f"/api/nodes/{created['node_id']}").get_data(as_text=True)

    assert "blob_key" not in body
    assert BLOB_KEY not in body


def test_fetching_a_missing_node_is_404(catalog_table, signed_in):
    resp = _get("/api/nodes/node-nope")

    assert resp.status_code == 404


def test_fetching_a_node_in_another_library_is_403(catalog_table, signed_in):
    """The whole point of the check: a real id, a real node, and not the caller's.

    403 and not 404, because the caller is known and signing in again will not
    help — see `errors.ForbiddenError`.
    """
    _second_library(catalog_table)

    resp = _get(f"/api/nodes/{OTHER_NODE}")

    assert resp.status_code == 403
    assert BLOB_KEY not in resp.get_data(as_text=True)


def test_no_authorization_header_is_401(catalog_table, signed_in):
    """Unstubbed, and refused before a key is ever fetched."""
    signed_in.authenticated = False

    resp = _client().get(f"/api/nodes/{CATALOG_ROOT}")

    assert resp.status_code == 401


# ───────────────────────── GET /api/resolve ─────────────────────────


def test_resolving_a_deep_path(catalog_table, signed_in):
    """Four segments, walked one `GetItem` at a time from the library root."""
    projects = _folder("projects")
    project = _folder("<project>", parent=projects["node_id"])
    runs = _folder("runs", parent=project["node_id"])
    clip = _file("clip.mp4", parent=runs["node_id"], size=99)

    resp = _get("/api/resolve?path=projects/<project>/runs/clip.mp4")

    assert resp.status_code == 200
    assert resp.get_json()["id"] == clip["node_id"]
    # The full record, not just the id: `size` is on the META row the walk ends
    # at, and a resolve that returned the by-parent projection would not have it.
    assert resp.get_json()["size"] == 99


def test_resolving_an_empty_path_is_the_library_root(catalog_table, signed_in):
    """The one node no other route hands out, and where a client starts."""
    resp = _get("/api/resolve?path=")

    assert resp.status_code == 200
    assert resp.get_json()["id"] == CATALOG_ROOT


def test_resolving_ignores_empty_segments(catalog_table, signed_in):
    """A leading or doubled slash is a typo, not a different path."""
    folder = _folder("characters")

    resp = _get("/api/resolve?path=/characters//")

    assert resp.get_json()["id"] == folder["node_id"]


def test_resolving_a_missing_path_is_404(catalog_table, signed_in):
    """And the message names the walk up to the segment that failed."""
    projects = _folder("projects")
    _folder("<project>", parent=projects["node_id"])

    resp = _get("/api/resolve?path=projects/<project>/nope/clip.mp4")

    assert resp.status_code == 404
    assert "projects/<project>/nope" in resp.get_json()["error"]


def test_resolving_a_missing_first_segment_is_404(catalog_table, signed_in):
    resp = _get("/api/resolve?path=nope")

    assert resp.status_code == 404


def test_resolving_never_returns_blob_key(catalog_table, signed_in):
    _file("clip.mp4")

    body = _get("/api/resolve?path=clip.mp4").get_data(as_text=True)

    assert "blob_key" not in body
    assert BLOB_KEY not in body


def test_resolving_starts_from_the_named_library(catalog_table, signed_in, monkeypatch):
    """A caller in two libraries names one, and the walk starts at *its* root.

    Names collide across libraries — that is the point of a library — so a
    resolve that ignored the header would return whichever tree it happened to
    start in.
    """
    _second_library(catalog_table)
    catalog_table.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": f"USER#{CATALOG_OWNER}"},
            "sk": {"S": f"LIB#{OTHER_LIBRARY}"},
            "role": {"S": "member"},
            "created_at": {"S": _SEED_TIME},
        },
    )

    resp = _get("/api/resolve?path=secret.jpeg", **{"X-Studio-Library": OTHER_LIBRARY})

    assert resp.status_code == 200
    assert resp.get_json()["id"] == OTHER_NODE


def test_resolving_in_a_library_the_caller_is_not_in_is_403(catalog_table, signed_in):
    _second_library(catalog_table)

    resp = _get("/api/resolve?path=secret.jpeg", **{"X-Studio-Library": OTHER_LIBRARY})

    assert resp.status_code == 403


def test_resolving_without_naming_one_of_several_libraries_is_400(catalog_table, signed_in):
    """`before_request`'s refusal, reached through this route.

    Asserted here and not only in `test_before_request.py` because `/api/resolve`
    is the route that would be tempted to guess — it is handed a path and no
    node, so a library it invented would be indistinguishable from a correct
    answer until two libraries held the same name. The caller's own library ids
    are listed in the message, so the retry is one round trip.
    """
    _second_library(catalog_table)
    catalog_table.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": f"USER#{CATALOG_OWNER}"},
            "sk": {"S": f"LIB#{OTHER_LIBRARY}"},
            "role": {"S": "member"},
            "created_at": {"S": _SEED_TIME},
        },
    )

    resp = _get("/api/resolve?path=clip.mp4")

    assert resp.status_code == 400
    assert OTHER_LIBRARY in resp.get_json()["error"]


def test_resolving_as_a_member_of_no_library_is_403(catalog_table, signed_in):
    """403 and not 400: there is no header this caller could send that works."""
    signed_in.sub = "sub-stranger"

    resp = _get("/api/resolve?path=clip.mp4")

    assert resp.status_code == 403


# ──────────────────────── POST /api/nodes ────────────────────────


def test_creating_a_folder(catalog_table, signed_in):
    resp = _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "characters", "kind": "folder"})

    assert resp.status_code == 201
    body = resp.get_json()
    assert (body["name"], body["kind"], body["parent_id"]) == ("characters", "folder", CATALOG_ROOT)
    assert "blob_key" not in body


def test_creating_a_file_needs_a_blob_key(catalog_table, signed_in):
    """The whole definition of a folder is a node with no blob (#280)."""
    resp = _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file"})

    assert resp.status_code == 400


def test_creating_a_file(catalog_table, signed_in):
    resp = _post(
        "/api/nodes",
        {
            "parent": CATALOG_ROOT,
            "name": "clip.mp4",
            "kind": "file",
            "blob_key": BLOB_KEY,
            "size": 17,
            "content_type": "video/mp4",
        },
    )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["size"] == 17
    # The one field that must not leave, asserted on the route that accepts it.
    assert "blob_key" not in body
    assert BLOB_KEY not in resp.get_data(as_text=True)


def test_creating_without_a_parent_is_400(catalog_table, signed_in):
    resp = _post("/api/nodes", {"name": "characters", "kind": "folder"})

    assert resp.status_code == 400


def test_creating_a_duplicate_name_is_409(catalog_table, signed_in):
    """409 and not 400: it tells the UI to keep the name field open."""
    _folder("characters")

    resp = _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "characters", "kind": "folder"})

    assert resp.status_code == 409


def test_creating_in_another_callers_library_is_403(catalog_table, signed_in):
    """The parent authorises the create — the new node has no `lib` of its own yet."""
    _second_library(catalog_table)

    resp = _post("/api/nodes", {"parent": OTHER_ROOT, "name": "characters", "kind": "folder"})

    assert resp.status_code == 403


# ──────────────────── PATCH /api/nodes/<id> ────────────────────


def test_renaming_a_node(catalog_table, signed_in):
    created = _folder("characters")

    resp = _patch(f"/api/nodes/{created['node_id']}", {"name": "subjects"})

    assert resp.status_code == 200
    assert resp.get_json()["name"] == "subjects"
    assert catalog.node(created["node_id"])["name"] == "subjects"


def test_renaming_a_folder_leaves_every_descendant_untouched(catalog_table, signed_in):
    """`path` names ancestors by id, and a rename changes none of them.

    The assertion the ticket asks for, and the reason rename and move are
    separate fields: a rename that rewrote descendants would be doing a move's
    work for none of a move's reasons.
    """
    folder = _folder("characters")
    child = _folder("<name>", parent=folder["node_id"])
    grandchild = _file("profile.yaml", parent=child["node_id"])
    before = {node["node_id"]: node["path"] for node in (child, grandchild)}

    assert _patch(f"/api/nodes/{folder['node_id']}", {"name": "subjects"}).status_code == 200

    for node_id, path in before.items():
        assert catalog.node(node_id)["path"] == path


def test_renaming_onto_an_existing_name_is_409(catalog_table, signed_in):
    _folder("characters")
    other = _folder("projects")

    resp = _patch(f"/api/nodes/{other['node_id']}", {"name": "characters"})

    assert resp.status_code == 409


def test_moving_a_node(catalog_table, signed_in):
    source = _folder("characters")
    destination = _folder("archive")

    resp = _patch(f"/api/nodes/{source['node_id']}", {"parent": destination["node_id"]})

    assert resp.status_code == 200
    assert resp.get_json()["parent_id"] == destination["node_id"]


def test_sending_both_name_and_parent_is_400(catalog_table, signed_in):
    """A refusal rather than a guess — the two orderings differ on a collision."""
    source = _folder("characters")
    destination = _folder("archive")

    resp = _patch(
        f"/api/nodes/{source['node_id']}",
        {"name": "subjects", "parent": destination["node_id"]},
    )

    assert resp.status_code == 400
    assert catalog.node(source["node_id"])["name"] == "characters"


def test_sending_neither_name_nor_parent_is_400(catalog_table, signed_in):
    created = _folder("characters")

    assert _patch(f"/api/nodes/{created['node_id']}", {}).status_code == 400


def test_moving_into_another_library_is_400(catalog_table, signed_in):
    """`catalog.move_node` owns this rule; the route does not restate it."""
    _second_library(catalog_table)
    catalog_table.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": f"USER#{CATALOG_OWNER}"},
            "sk": {"S": f"LIB#{OTHER_LIBRARY}"},
            "role": {"S": "member"},
            "created_at": {"S": _SEED_TIME},
        },
    )
    source = _folder("characters")

    resp = _patch(f"/api/nodes/{source['node_id']}", {"parent": OTHER_ROOT})

    assert resp.status_code == 400


def test_patching_a_node_in_another_library_is_403(catalog_table, signed_in):
    _second_library(catalog_table)

    resp = _patch(f"/api/nodes/{OTHER_NODE}", {"name": "mine.jpeg"})

    assert resp.status_code == 403


# ──────────────────── DELETE /api/nodes/<id> ────────────────────


def test_deleting_a_node(catalog_table, media_bucket, signed_in):
    created = _folder("characters")

    resp = _delete(f"/api/nodes/{created['node_id']}")

    assert resp.status_code == 200
    assert resp.get_json() == {"id": created["node_id"], "deleted": 1}
    with pytest.raises(NotFoundError):
        catalog.node(created["node_id"])


def test_deleting_a_folder_takes_its_subtree(catalog_table, media_bucket, signed_in):
    folder = _folder("characters")
    child = _folder("<name>", parent=folder["node_id"])
    grandchild = _folder("seed", parent=child["node_id"])

    resp = _delete(f"/api/nodes/{folder['node_id']}")

    assert resp.get_json()["deleted"] == 3
    for gone in (folder, child, grandchild):
        with pytest.raises(NotFoundError):
            catalog.node(gone["node_id"])


def test_deleting_a_file_removes_its_blob(catalog_table, media_bucket, signed_in):
    """Rows first, then blobs. Asserted against the bucket, not a call log."""
    key = "characters/subject-a/seed/subject-a_1.webp"
    created = catalog.create_node(CATALOG_ROOT, "seed.webp", catalog.KIND_FILE, blob_key=key)

    assert _delete(f"/api/nodes/{created['node_id']}").status_code == 200

    listed = media_bucket.list_objects_v2(Bucket=config.media_bucket(), Prefix=key)
    assert listed.get("KeyCount") == 0


def test_deleting_never_returns_blob_keys(catalog_table, media_bucket, signed_in):
    """The internal half of a record does not leave, on the verb that knows them all."""
    created = catalog.create_node(
        CATALOG_ROOT, "seed.webp", catalog.KIND_FILE, blob_key=BLOB_KEY
    )

    body = _delete(f"/api/nodes/{created['node_id']}").get_data(as_text=True)

    assert "blob_key" not in body
    assert BLOB_KEY not in body


def test_deleting_the_library_root_is_400(catalog_table, media_bucket, signed_in):
    assert _delete(f"/api/nodes/{CATALOG_ROOT}").status_code == 400


def test_deleting_in_another_library_is_403(catalog_table, media_bucket, signed_in):
    _second_library(catalog_table)

    resp = _delete(f"/api/nodes/{OTHER_NODE}")

    assert resp.status_code == 403
    assert catalog.node(OTHER_NODE)["node_id"] == OTHER_NODE
