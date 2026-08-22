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

from urllib.parse import parse_qs, urlparse

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


def _grant(client, lib, role):
    """A membership row putting the signed-in caller in a library, with a role.

    Literal, like the library beside it, and for the same reason: nothing in
    `services.catalog` writes a membership — `scripts/add-member.sh` does, and it
    is a script rather than a route precisely so the deployed surface cannot
    grant itself access. This is the test's stand-in for running it.

    Note what a second row does to every request the test then makes: the caller
    is a member of more than one library, so `before_request` stops resolving one
    for them and starts refusing to guess. Use `_transfer` or
    `_patch_with_library`, which name one.
    """
    client.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": f"USER#{CATALOG_OWNER}"},
            "sk": {"S": f"LIB#{lib}"},
            "role": {"S": role},
            "created_at": {"S": _SEED_TIME},
        },
    )


def _with_library(library):
    """Request headers naming which library the request is about."""
    headers = {"Authorization": "Bearer t"}
    if library is not None:
        headers["X-Studio-Library"] = library
    return headers


def _patch_with_library(path, body, library=CATALOG_LIBRARY):
    return _client().patch(path, json=body, headers=_with_library(library))


def _transfer(node_id, body, library=CATALOG_LIBRARY):
    """`POST /api/nodes/<id>/transfer`, with a library header by default.

    The header authorises nothing here — the node's own `lib` and the body's are
    the two the route checks — but the hook scopes every path that is not
    `/api/libraries`, and the only caller who can transfer at all is one with
    two memberships. Passing `library=None` is how the test below asserts that.
    """
    return _client().post(
        f"/api/nodes/{node_id}/transfer", json=body, headers=_with_library(library)
    )


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


def test_creating_a_file_without_a_blob_key_makes_a_placeholder(catalog_table, signed_in):
    """**Reverses what #293 asserted here**, which was a 400, and #294 is why.

    A client cannot name `blobs/<node_id>` at create time because it does not
    know the id yet, so the only way to have an id-derived key is for
    `create_node` to mint both together. The node is a placeholder until the
    bytes land: a key with no object behind it, and no size.
    """
    resp = _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file"})

    assert resp.status_code == 201
    created = catalog.node(resp.get_json()["id"])
    assert created["blob_key"] == catalog.blob_key_for(created["node_id"])
    assert "size" not in created


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
    _grant(catalog_table, OTHER_LIBRARY, "member")
    source = _folder("characters")

    # **The header is what makes this test about the move.** Granting a second
    # membership above makes the caller one `before_request` refuses to guess
    # for, so without it the 400 is the hook's "name one" and `move_node` is
    # never reached — the same status for a different reason, which is the way a
    # test passes while the rule it names is gone.
    resp = _patch_with_library(f"/api/nodes/{source['node_id']}", {"parent": OTHER_ROOT})

    assert resp.status_code == 400
    assert "another library" in resp.get_json()["error"]


def test_patching_a_node_in_another_library_is_403(catalog_table, signed_in):
    _second_library(catalog_table)

    resp = _patch(f"/api/nodes/{OTHER_NODE}", {"name": "mine.jpeg"})

    assert resp.status_code == 403


# ─────────────── POST /api/nodes/<id>/transfer ───────────────
#
# The one route that touches two libraries. What these assert is the pair of
# checks and which library each is about — the rewriting itself is
# `test_catalog.py`'s, and the claim that no object moves is `test_manage.py`'s
# and the integration suite's.


def test_transferring_a_subtree_to_a_library_the_caller_owns(catalog_table, signed_in):
    _second_library(catalog_table)
    _grant(catalog_table, OTHER_LIBRARY, "owner")
    source = _folder("projects")
    _file("clip.mp4", parent=source["node_id"])

    resp = _transfer(source["node_id"], {"lib": OTHER_LIBRARY})

    assert resp.status_code == 200
    assert resp.get_json()["lib"] == OTHER_LIBRARY
    assert resp.get_json()["parent_id"] == OTHER_ROOT
    # The node keeps its id, which is what keeps a share link to it working.
    assert resp.get_json()["id"] == source["node_id"]


def test_a_transfer_never_returns_blob_key(catalog_table, signed_in):
    """The allowlist holds on the route that changes which library owns a key."""
    _second_library(catalog_table)
    _grant(catalog_table, OTHER_LIBRARY, "owner")
    created = _file("clip.mp4")

    resp = _transfer(created["node_id"], {"lib": OTHER_LIBRARY})

    assert "blob_key" not in resp.get_json()
    assert BLOB_KEY not in resp.get_data(as_text=True)


def test_a_transfer_out_of_a_library_the_caller_only_belongs_to_is_403(
    catalog_table, signed_in
):
    """Member of the source, owner of the destination. The source check refuses."""
    _second_library(catalog_table)
    _grant(catalog_table, OTHER_LIBRARY, "owner")
    source = _folder("projects")
    # Demote the caller in the seeded library, which they own by default.
    _grant(catalog_table, CATALOG_LIBRARY, "member")

    resp = _transfer(source["node_id"], {"lib": OTHER_LIBRARY})

    assert resp.status_code == 403
    assert CATALOG_LIBRARY in resp.get_json()["error"]


def test_a_transfer_into_a_library_the_caller_only_belongs_to_is_403(
    catalog_table, signed_in
):
    """Owner of the source, member of the destination. The destination check refuses."""
    _second_library(catalog_table)
    _grant(catalog_table, OTHER_LIBRARY, "member")
    source = _folder("projects")

    resp = _transfer(source["node_id"], {"lib": OTHER_LIBRARY})

    assert resp.status_code == 403
    assert OTHER_LIBRARY in resp.get_json()["error"]


def test_a_transfer_into_a_library_the_caller_is_not_in_is_403(catalog_table, signed_in):
    """No membership row at all, so the caller is not told whether it exists."""
    _second_library(catalog_table)
    source = _folder("projects")

    resp = _transfer(source["node_id"], {"lib": OTHER_LIBRARY}, library=None)

    assert resp.status_code == 403
    assert "not a member" in resp.get_json()["error"]


def test_a_transfer_of_a_node_in_another_library_is_403(catalog_table, signed_in):
    """Checked against the node's own `lib`, as everywhere else in this file.

    The destination here is a library the caller genuinely owns, so nothing but
    the source check can refuse it — which is the point: owning where a subtree
    is going is not permission to take it from where it is.
    """
    _second_library(catalog_table)

    resp = _transfer(OTHER_NODE, {"lib": CATALOG_LIBRARY}, library=None)

    assert resp.status_code == 403
    assert OTHER_LIBRARY in resp.get_json()["error"]


def test_a_transfer_without_a_lib_is_400(catalog_table, signed_in):
    _second_library(catalog_table)
    _grant(catalog_table, OTHER_LIBRARY, "owner")
    source = _folder("projects")

    assert _transfer(source["node_id"], {}).status_code == 400


def test_a_transfer_to_a_library_that_does_not_exist_is_404(catalog_table, signed_in):
    """A membership pointing at no library record — the dangling row #291 reports.

    Reached only because the caller "owns" it: the checks pass on the membership
    and the read fails on the library. That order is why a stranger cannot use
    this route to find out which library ids exist.
    """
    _grant(catalog_table, "lib-gone", "owner")
    source = _folder("projects")

    resp = _transfer(source["node_id"], {"lib": "lib-gone"})

    assert resp.status_code == 404


def test_a_transfer_with_no_library_header_is_400(catalog_table, signed_in):
    """The hook still scopes this route, and a two-library caller must name one.

    Documented in the route rather than worked around: every caller who can
    transfer is a member of two libraries, which is exactly the caller
    `_resolve_library` refuses to guess for. The switcher in the SPA is what
    sends it.
    """
    _second_library(catalog_table)
    _grant(catalog_table, OTHER_LIBRARY, "owner")
    source = _folder("projects")

    resp = _transfer(source["node_id"], {"lib": OTHER_LIBRARY}, library=None)

    assert resp.status_code == 400
    assert "more than one library" in resp.get_json()["error"]


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


# ─────────────── GET /api/nodes/<id>/download-url ───────────────

# These need the bucket as well as the table: the route heads the object before
# signing, so a node whose blob is absent is a 404 and not a URL.
REAL_KEY = "characters/subject-a/seed/subject-a_1.webp"


def _file_on_disk(name="seed.webp", key=REAL_KEY):
    return catalog.create_node(CATALOG_ROOT, name, catalog.KIND_FILE, blob_key=key)


def test_a_download_url_is_signed_for_the_nodes_blob(catalog_table, media_bucket, signed_in):
    created = _file_on_disk()

    resp = _get(f"/api/nodes/{created['node_id']}/download-url")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == created["node_id"]
    assert body["expires_in"] == config.presign_ttl_seconds()
    # The signature covers the key, so the key is necessarily in the URL. That is
    # not the leak `_view` guards against — the URL *is* the grant, and it is
    # useless for any other object.
    assert "X-Amz-Signature" in body["url"]
    assert REAL_KEY in body["url"]


def test_a_download_url_reports_the_objects_size_not_the_rows(
    catalog_table, media_bucket, signed_in
):
    """S3 is asked, because the bytes are what is being fetched.

    The row here claims a size that is deliberately wrong. A response that
    repeated it would hand the client a number the download then contradicts.
    """
    created = catalog.create_node(
        CATALOG_ROOT, "seed.webp", catalog.KIND_FILE, blob_key=REAL_KEY, size=999_999
    )

    body = _get(f"/api/nodes/{created['node_id']}/download-url").get_json()

    real = media_bucket.head_object(Bucket=config.media_bucket(), Key=REAL_KEY)
    assert body["size"] == real["ContentLength"] != 999_999


def test_a_download_url_can_ask_for_attachment(catalog_table, media_bucket, signed_in):
    """The node's name, not the blob key — the key is meaningless to a person."""
    created = _file_on_disk(name="my portrait.webp")

    body = _get(
        f"/api/nodes/{created['node_id']}/download-url?disposition=attachment"
    ).get_json()

    assert "response-content-disposition" in body["url"].lower()
    assert "my%20portrait.webp" in body["url"] or "my+portrait.webp" in body["url"]


def test_a_bad_disposition_is_400(catalog_table, media_bucket, signed_in):
    created = _file_on_disk()

    resp = _get(f"/api/nodes/{created['node_id']}/download-url?disposition=nope")

    assert resp.status_code == 400


def test_a_folder_has_nothing_to_download(catalog_table, media_bucket, signed_in):
    """400, not 404 — the node is there, the request does not apply to it."""
    folder = _folder("characters")

    resp = _get(f"/api/nodes/{folder['node_id']}/download-url")

    assert resp.status_code == 400


def test_a_row_pointing_at_a_missing_blob_is_404(catalog_table, media_bucket, signed_in):
    """Head before sign, so this fails here rather than in the browser."""
    created = catalog.create_node(
        CATALOG_ROOT, "gone.webp", catalog.KIND_FILE, blob_key="characters/gone.webp"
    )

    resp = _get(f"/api/nodes/{created['node_id']}/download-url")

    assert resp.status_code == 404


def test_a_download_url_in_another_library_is_403(catalog_table, media_bucket, signed_in):
    _second_library(catalog_table)

    resp = _get(f"/api/nodes/{OTHER_NODE}/download-url")

    assert resp.status_code == 403


# ──────────── POST /api/nodes/<id>/upload-url + confirm ────────────


def _placeholder(name="clip.mp4"):
    """A file node whose key is the API's own — what an upload targets."""
    return catalog.create_node(CATALOG_ROOT, name, catalog.KIND_FILE)


def test_an_upload_url_is_signed_for_the_nodes_own_key(catalog_table, signed_in):
    created = _placeholder()

    resp = _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": 17, "content_type": "video/mp4"},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert catalog.blob_key_for(created["node_id"]) in body["url"]
    assert body["expires_in"] == config.upload_ttl_seconds()


def test_an_upload_url_signs_the_length_and_type(catalog_table, signed_in):
    """The constraint #294 asks for: an oversized body is refused by S3, not found later.

    `content-length` and `content-type` in `X-Amz-SignedHeaders` is what makes
    that true — a client sending different values fails signature validation and
    writes nothing. Asserted against the URL rather than trusted, because the
    whole bound rests on it.
    """
    created = _placeholder()

    body = _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": 17, "content_type": "video/mp4"},
    ).get_json()

    signed = parse_qs(urlparse(body["url"]).query)["X-Amz-SignedHeaders"][0]
    assert "content-length" in signed
    assert "content-type" in signed
    assert body["headers"] == {"Content-Length": "17", "Content-Type": "video/mp4"}


def test_an_upload_url_cannot_be_redirected_to_another_key(catalog_table, signed_in):
    """The key is the node's own, never one the caller named.

    The `blob_key` in the body is ignored — a caller-supplied key would make this
    a signature for an arbitrary object in the bucket.
    """
    created = _placeholder()

    body = _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": 17, "content_type": "video/mp4", "blob_key": "characters/someone-elses.webp"},
    ).get_json()

    assert "someone-elses" not in body["url"]
    assert catalog.blob_key_for(created["node_id"]) in body["url"]


def test_an_oversized_upload_is_refused_at_signing(catalog_table, signed_in):
    created = _placeholder()

    resp = _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": config.max_upload_bytes() + 1, "content_type": "video/mp4"},
    )

    assert resp.status_code == 400
    assert "multipart" in resp.get_json()["error"]


def test_a_boolean_size_is_not_an_integer(catalog_table, signed_in):
    """`True` is an `int` in Python, and would otherwise sign a one-byte upload."""
    created = _placeholder()

    resp = _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": True, "content_type": "video/mp4"},
    )

    assert resp.status_code == 400


def test_an_upload_url_needs_a_content_type(catalog_table, signed_in):
    created = _placeholder()

    resp = _post(f"/api/nodes/{created['node_id']}/upload-url", {"size": 17})

    assert resp.status_code == 400


def test_a_legacy_key_cannot_be_overwritten_through_a_signature(catalog_table, signed_in):
    """A node whose bytes predate the catalog is not what these routes are for."""
    created = catalog.create_node(
        CATALOG_ROOT, "old.webp", catalog.KIND_FILE, blob_key=REAL_KEY
    )

    resp = _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": 17, "content_type": "image/webp"},
    )

    assert resp.status_code == 400


def test_a_folder_cannot_be_uploaded_to(catalog_table, signed_in):
    folder = _folder("characters")

    resp = _post(
        f"/api/nodes/{folder['node_id']}/upload-url",
        {"size": 17, "content_type": "video/mp4"},
    )

    assert resp.status_code == 400


def test_an_upload_url_in_another_library_is_403(catalog_table, signed_in):
    _second_library(catalog_table)

    resp = _post(
        f"/api/nodes/{OTHER_NODE}/upload-url", {"size": 17, "content_type": "video/mp4"}
    )

    assert resp.status_code == 403


def test_a_node_stays_a_placeholder_until_confirmed(catalog_table, media_bucket, signed_in):
    """Signing changes no row, and confirming before the bytes land is a 404."""
    created = _placeholder()

    _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": 17, "content_type": "video/mp4"},
    )
    assert "size" not in catalog.node(created["node_id"])

    assert _post(f"/api/nodes/{created['node_id']}/confirm-upload", {}).status_code == 404


def test_confirming_writes_what_s3_stored_not_what_the_client_claimed(
    catalog_table, media_bucket, signed_in
):
    """The declared size is checked once, not trusted twice.

    The upload is signed for 17 bytes and the object put here is a different
    length — moto does not enforce the signature, which is what lets the test
    ask the question at all: does the row come from S3 or from the request?
    """
    created = _placeholder()
    _post(
        f"/api/nodes/{created['node_id']}/upload-url",
        {"size": 17, "content_type": "video/mp4"},
    )
    media_bucket.put_object(
        Bucket=config.media_bucket(),
        Key=catalog.blob_key_for(created["node_id"]),
        Body=b"four",
        ContentType="video/mp4",
    )

    body = _post(f"/api/nodes/{created['node_id']}/confirm-upload", {}).get_json()

    assert body["size"] == 4
    assert body["content_type"] == "video/mp4"
    assert catalog.node(created["node_id"])["size"] == 4


def test_confirming_never_returns_blob_key(catalog_table, media_bucket, signed_in):
    created = _placeholder()
    media_bucket.put_object(
        Bucket=config.media_bucket(),
        Key=catalog.blob_key_for(created["node_id"]),
        Body=b"four",
    )

    body = _post(f"/api/nodes/{created['node_id']}/confirm-upload", {}).get_data(as_text=True)

    assert "blob_key" not in body
    assert "blobs/" not in body


def test_confirming_in_another_library_is_403(catalog_table, media_bucket, signed_in):
    _second_library(catalog_table)

    resp = _post(f"/api/nodes/{OTHER_NODE}/confirm-upload", {})

    assert resp.status_code == 403


# ──────────────────────────── POST /api/runs ────────────────────────────

RUN_NAME = "2026-08-04_21-30-54_wave-porch-1x1"
REQUEST_JSON = '{"model": "x", "prompt": "a porch"}'


def _record_run(**overrides):
    payload = {
        "parent": CATALOG_ROOT,
        "name": RUN_NAME,
        "documents": {"request.json": REQUEST_JSON},
        "outputs": [{"name": "wave-porch.jpeg", "size": 4, "content_type": "image/jpeg"}],
    }
    payload.update(overrides)
    return _post("/api/runs", payload)


def test_recording_a_run_creates_the_folder_documents_and_outputs(
    catalog_table, media_bucket, signed_in
):
    resp = _record_run()

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["run"]["name"] == RUN_NAME
    assert body["run"]["kind"] == "folder"
    assert [doc["name"] for doc in body["documents"]] == ["request.json"]
    assert [out["name"] for out in body["outputs"]] == ["wave-porch.jpeg"]

    children = catalog.children(body["run"]["id"])
    assert sorted(entry["name"] for entry in children) == ["request.json", "wave-porch.jpeg"]


def test_a_recorded_document_round_trips_byte_identical(catalog_table, media_bucket, signed_in):
    """The assertion #296 asks for by name, through the route that serves text."""
    body = _record_run().get_json()
    key = catalog.blob_key_for(body["documents"][0]["id"])

    stored = media_bucket.get_object(Bucket=config.media_bucket(), Key=key)["Body"].read()

    assert stored.decode() == REQUEST_JSON


def test_a_document_is_stored_as_text_and_never_decoded(catalog_table, media_bucket, signed_in):
    """`text/plain`, not `application/json` — nothing should be tempted to parse it."""
    body = _record_run().get_json()

    assert body["documents"][0]["content_type"].startswith("text/plain")


def test_a_documents_size_counts_bytes_not_characters(catalog_table, media_bucket, signed_in):
    """`len(text)` would be wrong for anything non-ASCII."""
    text = '{"prompt": "café"}'
    body = _record_run(documents={"request.json": text}).get_json()

    assert body["documents"][0]["size"] == len(text.encode()) != len(text)


def test_an_output_comes_back_with_an_upload_url_for_its_own_key(
    catalog_table, media_bucket, signed_in
):
    """One round trip: the placeholder and the URL its bytes go to, together."""
    body = _record_run().get_json()
    output = body["outputs"][0]

    assert catalog.blob_key_for(output["id"]) in output["upload_url"]
    assert output["headers"] == {"Content-Length": "4", "Content-Type": "image/jpeg"}
    assert "blob_key" not in output


def test_recording_a_run_needs_a_parent(catalog_table, media_bucket, signed_in):
    assert _post("/api/runs", {"name": RUN_NAME}).status_code == 400


def test_an_oversized_document_is_refused(catalog_table, media_bucket, signed_in):
    resp = _record_run(documents={"request.json": "x" * (config.max_text_bytes() + 1)})

    assert resp.status_code == 400
    assert "output" in resp.get_json()["error"]


def test_an_output_without_a_size_is_refused(catalog_table, media_bucket, signed_in):
    resp = _record_run(outputs=[{"name": "clip.mp4", "content_type": "video/mp4"}])

    assert resp.status_code == 400


def test_a_duplicate_run_name_is_409(catalog_table, media_bucket, signed_in):
    """Run folders are `<ts>_<slug>`, so a collision means the CLI re-sent one."""
    _record_run()

    assert _record_run().status_code == 409


def test_recording_a_run_in_another_library_is_403(catalog_table, media_bucket, signed_in):
    _second_library(catalog_table)

    resp = _record_run(parent=OTHER_ROOT)

    assert resp.status_code == 403
