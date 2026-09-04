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

import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from studio_core import config
from studio_core.clients.aws import s3
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


def _api_key(record):
    """The key `create_node` stamps for this node, recomputed from the outside.

    Spelled out rather than read back off the record, because a test that
    asserted `record["blob_key"] == record["blob_key"]` would pass against any
    key at all. Everything these tests create sits directly under the library
    root, which is owned by no entity — so the owner is the library and the
    prefix is `libraries/`.
    """
    return catalog.blob_key_for(record["node_id"], record["name"], None, CATALOG_LIBRARY)


def _folder(name, parent=CATALOG_ROOT):
    return catalog.create_node(parent, name, catalog.KIND_FOLDER)


def _file(name, parent=CATALOG_ROOT, **kwargs):
    """A file with bytes behind it.

    **`size` is defaulted, and it has to be.** A row carrying a `blob_key` and no
    `size` is a placeholder an upload never confirmed, and the one listing this
    API has hides those rather than drawing a tile it cannot load — so a fixture
    that omitted it would be testing the listing's ability to hide things.
    Anything that wants a placeholder builds one explicitly; `test_browse` does.
    """
    kwargs.setdefault("size", 1024)
    return catalog.create_node(parent, name, catalog.KIND_FILE, blob_key=BLOB_KEY, **kwargs)


def _minted(name, parent=CATALOG_ROOT):
    """A file whose key the catalog stamps, rather than one handed a literal.

    `_file` above passes an explicit `blob_key` because most of this module is
    about routes rather than about keys, and a literal keeps those assertions
    readable. Anything testing the *stamp* has to let `create_node` derive it
    from the owner the parent resolves to, which is what this is for.
    """
    return catalog.create_node(parent, name, catalog.KIND_FILE)


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

    resp = _get(f"/api/nodes?under={CATALOG_ROOT}&sort=name")

    assert resp.status_code == 200
    # `kind` is what the file HOLDS, not the storage vocabulary — `image`,
    # `video`, `text`, `other`, or `folder`. A client deciding whether to draw a
    # thumbnail cannot do anything with "file".
    assert [(entry["name"], entry["kind"]) for entry in resp.get_json()["entries"]] == [
        ("characters", "folder"),
        ("notes.txt", "text"),
        ("projects", "folder"),
    ]


def test_listing_carries_size_and_content_type(catalog_table, signed_in):
    """The two attributes the by-parent projection does not hold.

    This is the assertion the `BatchGetItem` in `list_nodes` exists for: both
    live on the record half only, so a listing built from `catalog.children`
    alone would return every file without a size and nothing would say so.
    """
    _file("clip.mp4", size=4096, content_type="video/mp4")

    entry = _get(f"/api/nodes?under={CATALOG_ROOT}").get_json()["entries"][0]

    assert entry["size"] == 4096
    assert entry["content_type"] == "video/mp4"


def test_a_folder_carries_no_size(catalog_table, signed_in):
    """Absent rather than null — a folder has no bytes, not zero bytes."""
    _folder("characters")

    entry = _get(f"/api/nodes?under={CATALOG_ROOT}").get_json()["entries"][0]

    assert "size" not in entry
    assert "content_type" not in entry


def test_listing_never_returns_blob_key(catalog_table, signed_in):
    """The one field that must not leave, checked on the route that lists many."""
    _file("clip.mp4")

    entry = _get(f"/api/nodes?under={CATALOG_ROOT}").get_json()["entries"][0]

    assert "blob_key" not in entry
    assert BLOB_KEY not in _get(f"/api/nodes?under={CATALOG_ROOT}").get_data(as_text=True)


def test_listing_never_returns_path(catalog_table, signed_in):
    """`path` is a rebuildable index; `parent_id` is the answer a client gets."""
    _folder("characters")

    entry = _get(f"/api/nodes?under={CATALOG_ROOT}").get_json()["entries"][0]

    assert "path" not in entry
    assert entry["parent_id"] == CATALOG_ROOT


def test_listing_an_empty_folder_is_an_empty_list(catalog_table, signed_in):
    empty = _folder("characters")

    resp = _get(f"/api/nodes?under={empty['node_id']}")

    assert resp.status_code == 200
    assert resp.get_json()["entries"] == []


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

    entries = _get(f"/api/nodes?under={folder['node_id']}").get_json()["entries"]

    assert len(entries) == 101
    assert all("size" in entry for entry in entries)


def test_listing_a_missing_parent_is_404(catalog_table, signed_in):
    resp = _get("/api/nodes?under=node-nope")

    assert resp.status_code == 404


def test_listing_without_an_under_opens_on_the_library_root(catalog_table, signed_in):
    """It was a 400, and the root was the one address it could not express.

    `?parent=` was required, so "open the library" needed a different route —
    which is one of the reasons there were three listing endpoints. The root is
    the default now, and `/api/libraries` still deliberately does not report a
    root node id, so this is the request a client makes first.
    """
    _folder("characters")

    resp = _get("/api/nodes")

    assert resp.status_code == 200
    assert [entry["name"] for entry in resp.get_json()["entries"]] == ["characters"]


def test_listing_another_callers_library_is_403(catalog_table, signed_in):
    """The parent is read for its `lib`, and the `lib` is what is checked."""
    _second_library(catalog_table)

    resp = _get(f"/api/nodes?under={OTHER_ROOT}")

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

    A client cannot name the key at create time because it does not know the node
    id yet, so the only way to have an id-derived key is for `create_node` to
    mint both together. The node is a placeholder until the bytes land: a key
    with no object behind it, and no size.

    The entity model changed the *shape* — `blobs/<node_id>` became
    `<owner_kind>/<owner_id>/<node_id>.<ext>` — without changing that rule.
    """
    resp = _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file"})

    assert resp.status_code == 201
    created = catalog.node(resp.get_json()["id"])
    assert created["blob_key"] == _api_key(created)
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


def test_a_numbering_create_takes_the_next_free_name(catalog_table, signed_in):
    """`clip.mp4` beside a `clip.mp4` is `clip (2).mp4`, exactly as a copy is.

    The uploader's case (#294). It is asserted on the *form* of the name rather
    than on "it did not 409", because the form is the thing that has to agree
    with `manage.copy_objects` — a folder that has been through both must not
    hold two spellings of the same idea.
    """
    _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file"})

    resp = _post(
        "/api/nodes",
        {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file", "on_conflict": "number"},
    )

    assert resp.status_code == 201
    assert resp.get_json()["name"] == "clip (2).mp4"


def test_numbering_keeps_counting_past_the_second(catalog_table, signed_in):
    """Three of one name, and the third is `(3)` — the loop advances, not retries."""
    for _ in range(3):
        _post(
            "/api/nodes",
            {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file", "on_conflict": "number"},
        )

    assert sorted(entry["name"] for entry in catalog.children(CATALOG_ROOT)) == [
        "clip (2).mp4",
        "clip (3).mp4",
        "clip.mp4",
    ]


def test_numbering_is_opt_in(catalog_table, signed_in):
    """The default is still the 409, and every existing caller sends no field.

    `record_run` and the CLI both create through this route; a route that quietly
    started numbering would turn a run recorded twice into two run folders that
    look like one.
    """
    _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file"})

    resp = _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file"})

    assert resp.status_code == 409


def test_an_unknown_conflict_policy_is_400(catalog_table, signed_in):
    """Refused rather than read as `fail`: "overwrite" must not silently not."""
    resp = _post(
        "/api/nodes",
        {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file", "on_conflict": "overwrite"},
    )

    assert resp.status_code == 400


def test_a_numbered_placeholder_still_gets_the_api_key(catalog_table, signed_in):
    """The numbered row is uploadable — `upload-url` refuses any other key."""
    _post("/api/nodes", {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file"})

    body = _post(
        "/api/nodes",
        {"parent": CATALOG_ROOT, "name": "clip.mp4", "kind": "file", "on_conflict": "number"},
    ).get_json()

    created = catalog.node(body["id"])
    assert created["blob_key"] == _api_key(created)


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
    assert _api_key(created) in body["url"]
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
    assert _api_key(created) in body["url"]


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
        Key=_api_key(created),
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
        Key=_api_key(created),
        Body=b"four",
    )

    body = _post(f"/api/nodes/{created['node_id']}/confirm-upload", {}).get_data(as_text=True)

    assert "blob_key" not in body
    assert created["blob_key"] not in body


def test_confirming_in_another_library_is_403(catalog_table, media_bucket, signed_in):
    _second_library(catalog_table)

    resp = _post(f"/api/nodes/{OTHER_NODE}/confirm-upload", {})

    assert resp.status_code == 403


# ─────────────────────── owner derivation ───────────────────────
#
# `owner` is **derived, never stored on the node**, which is what makes it
# correct the instant a file moves rather than after a rewrite of anything. The
# node's `path` is already the materialised list of ancestor ids and an entity's
# root folder carries `entity`, so the answer is the deepest ancestor holding
# that attribute — one `BatchGetItem` over a list the table already keeps.
#
# The entities here are created through their real routes rather than written by
# hand. A hand-written `entity` attribute would test the walk and not the thing
# that puts the attribute there, and those are the two halves that have to agree.


def _character(name="subject-a"):
    body = _post("/api/characters", {"name": name})
    assert body.status_code == 201, body.get_data(as_text=True)
    return body.get_json()


def _project(name="rooftop-teaser"):
    body = _post("/api/projects", {"name": name})
    assert body.status_code == 201, body.get_data(as_text=True)
    return body.get_json()


def _child(parent_id, name):
    """One named child of a folder, as a full record."""
    return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])


def test_a_node_view_carries_the_entity_it_belongs_to(catalog_table, signed_in):
    """What the SPA draws as "in <name>", and what stamps the blob prefix.

    On the listing rather than only on the single-node read, because the listing
    is where it would be tempting to leave it out: resolving it per row would be
    a batched read per thumbnail. It is resolved once from the parent instead,
    which is only correct because every child of one folder is in the same entity
    as the folder — the exception being a child that is an entity root itself,
    which carries `entity` and answers for itself.
    """
    character = _character()

    listing = _get(f"/api/nodes?under={character['root']}&sort=name").get_json()["entries"]

    assert [entry["name"] for entry in listing] == ["archive", "corpus", "reference", "seed"]
    for entry in listing:
        assert entry["owner"] == {
            "kind": "character",
            "id": character["id"],
            "name": "subject-a",
        }


def test_a_node_under_the_library_root_is_owned_by_nobody(catalog_table, signed_in):
    """**A real answer, not a missing one.**

    Folders a person makes by hand are meant to be reachable without becoming
    somebody's, and the bucket has a third prefix — `libraries/` — precisely so
    that material owned by neither a character nor a project still lands
    somewhere one prefix can scope.
    """
    loose = _folder("scratch")

    assert _get(f"/api/nodes/{loose['node_id']}/owner").get_json() == {
        "id": loose["node_id"],
        "owner": None,
    }


def test_an_entity_root_reports_itself_rather_than_its_parent(catalog_table, signed_in):
    """The one child of a folder whose owner is not the folder's.

    A character's root sits under the library root, which is owned by nobody, so
    a listing that handed every child the parent's answer would report `null` for
    the very row that carries the reverse pointer — and the home screen would
    draw a folder icon where a character card belongs.
    """
    character = _character()

    listing = _get(f"/api/nodes?under={CATALOG_ROOT}").get_json()["entries"]
    root = next(entry for entry in listing if entry["id"] == character["root"])

    assert root["entity"] == character["id"]
    assert root["owner"]["id"] == character["id"]


def test_the_deepest_entity_wins(catalog_table, signed_in):
    """A run's output reports the run, not the project it sits inside.

    That is the answer a person wants from a file, and the project is one hop up
    the same `path` for anyone who wants it instead. Worth pinning because the
    walk is deepest-first and reversing it would be invisible until somebody
    looked at a run.
    """
    project = _project()
    run = _post(
        "/api/runs",
        {
            "project": project["id"],
            "kind": "image",
            "model": "google/nano-banana-pro",
        },
    ).get_json()
    output_folder = _child(run["folder"], "output")

    assert _get(f"/api/nodes/{output_folder['node_id']}/owner").get_json()["owner"] == {
        "kind": "run",
        "id": run["id"],
        "name": None,
    }


def test_resolve_reports_the_owner_too(catalog_table, signed_in):
    """A name path turns into an id *and* the entity holding it in one call.

    The answer has to say which character the path resolved inside, or a caller
    needs a second round trip to find out what it just addressed. The first
    segment is the entity's ROOT FOLDER, which is named by the entity id — the
    slug it used to take could not survive two characters sharing a name.
    """
    character = _character()

    resolved = _get(f"/api/resolve?path={character['id']}/reference").get_json()

    assert resolved["owner"]["id"] == character["id"]


# ───────────────────── the blob key an owner stamps ─────────────────────


def test_a_file_takes_the_prefix_of_the_entity_that_holds_it(catalog_table, signed_in):
    """Three prefixes in the bucket, and a listing of it leaks no name.

    The old layout wrote the slug into every key, which made a listing of the
    media bucket a list of character names — hard rule #1 broken in the one place
    nobody was reading, and broken for PRODUCTION characters, which the rule
    still covers absolutely. Each of the three is asserted here rather than only the
    character's, because the fallback to `libraries/` is the one a reader would
    assume is unreachable.
    """
    character = _character()
    project = _project()
    reference = _child(character["root"], "reference")
    inputs = _child(project["root"], "input")

    in_character = _minted("front.png", reference["node_id"])
    in_project = _minted("plate.png", inputs["node_id"])
    in_library = _minted("loose.png")

    assert in_character["blob_key"] == (
        f"characters/{character['id']}/{in_character['node_id']}.png"
    )
    assert in_project["blob_key"] == f"projects/{project['id']}/{in_project['node_id']}.png"
    assert in_library["blob_key"] == f"libraries/{CATALOG_LIBRARY}/{in_library['node_id']}.png"


def test_moving_a_file_between_owners_does_not_rewrite_its_key(catalog_table, signed_in):
    """**Stamped once, never re-derived, and this is the honest cost of that.**

    The key keeps the prefix of the owner the node had when it was created. It is
    still correct — it is a pointer — but it now *looks* like it means something
    it does not, which is exactly the trap the old slug-in-the-key layout set.
    `studio catalog reseat` rewrites drifted keys out of band; nothing here may
    do it automatically, because a presigned URL, a copy and a delete all name
    the recorded string and a second opinion about it is a lost object.
    """
    character = _character()
    project = _project()
    reference = _child(character["root"], "reference")
    inputs = _child(project["root"], "input")

    moved = _minted("front.png", reference["node_id"])
    stamped = moved["blob_key"]

    assert _patch(f"/api/nodes/{moved['node_id']}", {"parent": inputs["node_id"]}).status_code == 200

    assert catalog.node(moved["node_id"])["blob_key"] == stamped
    assert catalog.node(moved["node_id"])["blob_key"].startswith("characters/")


def test_a_drifted_key_is_still_uploadable(catalog_table, signed_in):
    """The reason `is_api_blob` reads the tail and never the prefix.

    Checked against the prefix instead, a file dragged from a character into a
    project would stop being uploadable — its key still says `characters/` — and
    the refusal would read "this node's blob was not written through the API",
    which is false and unactionable.
    """
    character = _character()
    project = _project()
    reference = _child(character["root"], "reference")
    inputs = _child(project["root"], "input")

    moved = _minted("front.png", reference["node_id"])
    _patch(f"/api/nodes/{moved['node_id']}", {"parent": inputs["node_id"]})

    resp = _post(
        f"/api/nodes/{moved['node_id']}/upload-url",
        {"size": 4, "content_type": "image/png"},
    )

    assert resp.status_code == 200
    assert moved["blob_key"] in resp.get_json()["url"]


# ───────────────── POST /api/nodes/move and /copy ─────────────────
#
# **One route for files and folders, where there used to be two of each.** The
# split was an artefact of S3: moving a prefix meant a `CopyObject` per key
# underneath it and moving an object meant one. Neither copies anything now, so
# the only thing the two verbs still differed in was the shape of their request.


def test_moving_a_mixed_selection_in_one_request(catalog_table, signed_in):
    """A grid selection is files and folders together, and always was.

    `/api/objects/move` took files and `/api/folder/move` took exactly one
    folder, so selecting both meant two requests with no way to report a partial
    outcome across them.
    """
    destination = _folder("archive")
    branch = _folder("run-01")
    _file("shot.mp4", parent=branch["node_id"])
    loose = _file("plate.png")

    resp = _post(
        "/api/nodes/move",
        {"ids": [branch["node_id"], loose["node_id"]], "destination": destination["node_id"]},
    )

    assert resp.status_code == 200
    assert resp.get_json()["moved"] == 2
    assert resp.get_json()["descendants"] == 1
    assert sorted(entry["name"] for entry in catalog.children(destination["node_id"])) == [
        "plate.png",
        "run-01",
    ]


def test_a_move_refuses_before_it_has_applied_any_of_itself(catalog_table, signed_in):
    """**Every destination is checked before any node moves.**

    Each `move_node` is its own transaction, so a conflict found on the second
    entry would leave the first already moved — a selection split across two
    folders with nothing to say where the boundary fell. The check is a read and
    a read is beatable, but that is the rare case it exists to make rare.
    """
    destination = _folder("archive")
    _file("plate.png", parent=destination["node_id"])
    first = _file("keeper.png")
    second = _file("plate.png", parent=_folder("staging")["node_id"])

    resp = _post(
        "/api/nodes/move",
        {"ids": [first["node_id"], second["node_id"]], "destination": destination["node_id"]},
    )

    assert resp.status_code == 409
    # The first entry is still where it was: nothing was applied.
    assert catalog.node(first["node_id"])["parent_id"] == CATALOG_ROOT


def test_a_move_skips_what_is_already_there(catalog_table, signed_in):
    """"Move these forty there" is reasonable when three of them are there already."""
    destination = _folder("archive")
    settled = _file("plate.png", parent=destination["node_id"])
    moving = _file("keeper.png")

    body = _post(
        "/api/nodes/move",
        {"ids": [settled["node_id"], moving["node_id"]], "destination": destination["node_id"]},
    ).get_json()

    assert (body["moved"], body["skipped"]) == (1, 1)


def test_two_sources_of_one_name_refuse_each_other(catalog_table, signed_in):
    """Otherwise the second is a conflict against the first, found half-way.

    A grid selection lives in one folder so its names are already unique, but the
    endpoint does not require that and must not depend on it.
    """
    destination = _folder("archive")
    first = _file("plate.png", parent=_folder("a")["node_id"])
    second = _file("plate.png", parent=_folder("b")["node_id"])

    resp = _post(
        "/api/nodes/move",
        {"ids": [first["node_id"], second["node_id"]], "destination": destination["node_id"]},
    )

    assert resp.status_code == 409


def test_a_copy_is_stamped_with_the_destinations_owner(catalog_table, media_bucket, signed_in):
    """The one place a blob key is chosen rather than inherited.

    Copying a run output into a character's reference pool files the *new* bytes
    under the character, because the new node is the character's — while the
    source object keeps its own key untouched, because it is still the run's.
    Getting this backwards would file every reference a person ever curated under
    whichever project it happened to come from.
    """
    character = _character()
    project = _project()
    reference = _child(character["root"], "reference")
    inputs = _child(project["root"], "input")

    source = _minted("plate.png", inputs["node_id"])
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=source["blob_key"], Body=b"png-bytes"
    )

    resp = _post(
        "/api/nodes/copy",
        {"ids": [source["node_id"]], "destination": reference["node_id"]},
    )

    assert resp.status_code == 201
    copied = catalog.node(resp.get_json()["nodes"][0]["id"])
    assert copied["blob_key"].startswith(f"characters/{character['id']}/")
    assert catalog.node(source["node_id"])["blob_key"] == source["blob_key"]


def test_a_copy_gets_its_own_blob(catalog_table, media_bucket, signed_in):
    """**Load-bearing rather than incidental.**

    A second row on one `blob_key` would be cheaper, and `catalog.delete_node`
    reports the keys it removed rows for without asking whether anything else
    still points at them — there is no index on `blob_key` — so a delete would
    destroy the surviving copy's bytes. Copy-on-write is #334 and has to revisit
    that; until it does, "no two rows share a key" is held by the `CopyObject`.
    """
    destination = _folder("archive")
    source = _minted("plate.png")
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=source["blob_key"], Body=b"png-bytes"
    )

    body = _post(
        "/api/nodes/copy",
        {"ids": [source["node_id"]], "destination": destination["node_id"]},
    ).get_json()

    copied = catalog.node(body["nodes"][0]["id"])
    assert copied["blob_key"] != source["blob_key"]
    assert media_bucket.get_object(
        Bucket=config.media_bucket(), Key=copied["blob_key"]
    )["Body"].read() == b"png-bytes"


def test_a_copy_carries_the_description_and_the_tags(catalog_table, media_bucket, signed_in):
    """A copy is a second print of the same picture.

    So the caption is true of both. A blank copy sitting beside a described
    original is drift nobody would go looking for — the name is the only thing
    that may differ, and only because the destination might already hold it.
    """
    destination = _folder("archive")
    source = _minted("plate.png")
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=source["blob_key"], Body=b"png-bytes"
    )
    _patch(
        f"/api/nodes/{source['node_id']}",
        {"description": "the pool at dusk", "tags": ["poolside"]},
    )

    body = _post(
        "/api/nodes/copy",
        {"ids": [source["node_id"]], "destination": destination["node_id"]},
    ).get_json()

    copied = catalog.node(body["nodes"][0]["id"])
    assert copied["description"] == "the pool at dusk"
    assert copied["tags"] == ["poolside"]


def test_a_copy_numbers_a_name_the_destination_already_holds(
    catalog_table, media_bucket, signed_in
):
    """A copy has no split to leave behind, so it numbers where a move refuses.

    Copying a file into a folder that already holds the name is the ordinary case
    rather than the edge, and nothing is overwritten in any branch.
    """
    destination = _folder("archive")
    _file("plate.png", parent=destination["node_id"])
    source = _minted("plate.png")
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=source["blob_key"], Body=b"png-bytes"
    )

    body = _post(
        "/api/nodes/copy",
        {"ids": [source["node_id"]], "destination": destination["node_id"]},
    ).get_json()

    assert body["nodes"][0]["name"] == "plate (2).png"


def test_a_copy_refuses_a_folder_source(catalog_table, media_bucket, signed_in):
    """A recursive copy is a different operation with a different cost.

    Every descendant's bytes rather than one selection's — and refusing it is the
    same refusal `/api/objects/copy` always made, said out loud now that one
    route takes both kinds.
    """
    destination = _folder("archive")
    branch = _folder("run-01")

    resp = _post(
        "/api/nodes/copy",
        {"ids": [branch["node_id"]], "destination": destination["node_id"]},
    )

    assert resp.status_code == 400


def test_a_copy_never_returns_blob_key(catalog_table, media_bucket, signed_in):
    """The one response that has a freshly minted key for every entry.

    `manage.copy_nodes` hands back full records because it is the thing that
    wrote them; the allowlist is applied at the route, once. A `pop` there would
    leak the next internal attribute anybody adds.
    """
    destination = _folder("archive")
    source = _minted("plate.png")
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=source["blob_key"], Body=b"png-bytes"
    )

    body = _post(
        "/api/nodes/copy",
        {"ids": [source["node_id"]], "destination": destination["node_id"]},
    ).get_data(as_text=True)

    assert "blob_key" not in body
    assert "libraries/" not in body


# ─────────────────────── DELETE /api/nodes (bulk) ───────────────────────


def test_deleting_many_nodes_in_one_request(catalog_table, media_bucket, signed_in):
    """The grid's selection is the reason delete exists at all.

    A viewer that could only remove one file at a time would not be worth the
    write permission this endpoint needs.
    """
    branch = _folder("run-01")
    _file("shot.mp4", parent=branch["node_id"])
    loose = _file("plate.png")

    resp = _client().delete(
        "/api/nodes", json={"ids": [branch["node_id"], loose["node_id"]]}
    )

    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 2
    assert catalog.children(CATALOG_ROOT) == []


def test_a_bulk_delete_resolves_one_id_named_twice_once(catalog_table, media_bucket, signed_in):
    """Two spellings of one file used to be two idempotent `DeleteObject`s.

    A row deleted twice is a 404 raised *after* the first half of the request has
    already applied, so the deduplication is what keeps "resolve everything, then
    delete" true for a selection that names something twice.
    """
    loose = _file("plate.png")

    body = _client().delete(
        "/api/nodes", json={"ids": [loose["node_id"], loose["node_id"]]}
    ).get_json()

    assert body["deleted"] == 1


def test_a_bulk_delete_of_an_empty_list_is_400(catalog_table, media_bucket, signed_in):
    assert _client().delete("/api/nodes", json={"ids": []}).status_code == 400


def test_a_bulk_delete_past_the_cap_is_refused(catalog_table, media_bucket, signed_in, monkeypatch):
    """Refused rather than silently split.

    A partially applied bulk delete is the worst possible outcome to report back
    to a UI, and the cap now bounds a per-node cost rather than the single
    `DeleteObjects` call it was chosen for.
    """
    monkeypatch.setenv("STUDIO_MAX_BULK_KEYS", "2")

    resp = _client().delete("/api/nodes", json={"ids": ["a", "b", "c"]})

    assert resp.status_code == 400


# ──────────────── the entity-root delete refusal ────────────────
#
# **The one structural rule the layout leaves.** Every other folder in a
# character or a project may be renamed, moved or deleted freely, because
# reference-ness and run-ness are row attributes rather than locations. The root
# is different only because a record names it, and a record naming a node that is
# gone is the one broken state the tree cannot repair from.


def test_deleting_an_entitys_root_folder_is_refused(catalog_table, media_bucket, signed_in):
    """And the refusal says which entity to delete instead.

    A message reading "cannot delete" and nothing else would leave a person
    clicking the same button; the entity id is the thing they need, and it is on
    the row already.
    """
    character = _character()

    resp = _delete(f"/api/nodes/{character['root']}")

    assert resp.status_code == 400
    assert character["id"] in resp.get_json()["error"]
    assert catalog.node(character["root"])


def test_deleting_a_folder_holding_an_entity_root_is_refused(catalog_table, media_bucket, signed_in):
    """The nested case, which the named record alone would not catch.

    Deleting the library's `characters/` folder would take every character's root
    with it and leave every `CHAR#` record naming nothing. The check runs over the
    subtree the delete is about to remove — the same query the delete makes
    anyway, so it costs nothing.
    """
    character = _character()
    shelf = _folder("shelf")
    _patch(f"/api/nodes/{character['root']}", {"parent": shelf["node_id"]})

    resp = _delete(f"/api/nodes/{shelf['node_id']}")

    assert resp.status_code == 400
    assert character["id"] in resp.get_json()["error"]


def test_a_bulk_delete_refuses_every_entity_root_before_deleting_any(
    catalog_table, media_bucket, signed_in
):
    """**The pre-pass, and the reason it exists.**

    The refusal inside `delete_node` comes too late for a selection: the second
    entry refusing would leave the first already gone. `manage.delete_nodes` asks
    `catalog.assert_deletable` for every record first, and only then deletes any
    of them.
    """
    loose = _file("plate.png")
    character = _character()

    resp = _client().delete(
        "/api/nodes", json={"ids": [loose["node_id"], character["root"]]}
    )

    assert resp.status_code == 400
    # The file named first is untouched, which is what the pre-pass buys.
    assert catalog.node(loose["node_id"])


# ──────────────── GET/PATCH /api/nodes/<id>/text ────────────────
#
# One address for both directions, which is the whole of what this replaces:
# `GET /api/text?key=` read an S3 key and `PATCH /api/text?key=` walked a name
# path, so the pair agreed only for material written before the catalog — a file
# the editor could save was a file the editor could not re-open (#432).


def _text_node(media_bucket, name="notes.md", body=b"# heading\n"):
    """A text file that has actually been uploaded — bytes *and* a confirmed row.

    Both halves, because a row carrying a `blob_key` and no `size` is a
    *placeholder* and every read and write here refuses one. Putting the object
    without stamping the row would make this fixture an abandoned upload, which
    is a different test's subject and would fail these for the wrong reason.
    """
    created = catalog.create_node(CATALOG_ROOT, name, catalog.KIND_FILE)
    media_bucket.put_object(Bucket=config.media_bucket(), Key=created["blob_key"], Body=body)
    return catalog.set_blob(
        created["node_id"], created["blob_key"], size=len(body), content_type="text/markdown"
    ), body


def test_reading_and_writing_a_text_node_round_trips(catalog_table, media_bucket, signed_in):
    created, _body = _text_node(media_bucket)

    read = _get(f"/api/nodes/{created['node_id']}/text").get_json()
    assert read["content"] == "# heading\n"
    assert read["language"] == "markdown"

    saved = _patch(f"/api/nodes/{created['node_id']}/text", {"content": "# rewritten\n"})
    assert saved.status_code == 200

    assert _get(f"/api/nodes/{created['node_id']}/text").get_json()["content"] == (
        "# rewritten\n"
    )


def test_saving_restamps_the_row_from_the_bytes_it_wrote(catalog_table, media_bucket, signed_in):
    """Bytes first, then the row — the reverse of a delete, for the same reason.

    `size` on the row is a claim about an object; writing it before the object
    exists would be a claim about bytes that were never stored, and a listing
    reports that number without re-reading S3.
    """
    created, _body = _text_node(media_bucket)

    _patch(f"/api/nodes/{created['node_id']}/text", {"content": "é" * 3})

    # Bytes, not characters: three two-byte code points.
    assert catalog.node(created["node_id"])["size"] == 6


def test_editing_cannot_become_uploading(catalog_table, media_bucket, signed_in):
    """A placeholder whose bytes never landed is refused rather than created into.

    It used to be `s3.exists` on the key; it is now a row that must be a file and
    must carry a blob. Studio's only upload is the presigned PUT, and this route
    must not become a second one.
    """
    created = catalog.create_node(CATALOG_ROOT, "notes.md", catalog.KIND_FILE)

    assert _patch(f"/api/nodes/{created['node_id']}/text", {"content": "x"}).status_code == 404


def test_a_binary_node_is_not_editable_text(catalog_table, media_bucket, signed_in):
    created = catalog.create_node(CATALOG_ROOT, "clip.mp4", catalog.KIND_FILE)
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=created["blob_key"], Body=b"mp4-bytes"
    )

    assert _get(f"/api/nodes/{created['node_id']}/text").status_code == 400
    assert _patch(f"/api/nodes/{created['node_id']}/text", {"content": "x"}).status_code == 400


def test_a_folder_has_no_text(catalog_table, media_bucket, signed_in):
    folder = _folder("archive")

    assert _get(f"/api/nodes/{folder['node_id']}/text").status_code == 400


def test_text_over_the_cap_is_truncated_on_read_and_refused_on_save(
    catalog_table, media_bucket, signed_in, monkeypatch
):
    """**Not a formality.** The reader truncates, so the writer has to refuse.

    A client that opened a truncated copy and saved it back would delete the
    tail. The frontend refuses to open an editor on a truncated file; the cap
    here means a file that somehow grew past it in between cannot be silently
    beheaded either.
    """
    monkeypatch.setenv("STUDIO_MAX_TEXT_BYTES", "8")
    created, _body = _text_node(media_bucket, body=b"x" * 32)

    read = _get(f"/api/nodes/{created['node_id']}/text").get_json()
    assert read["truncated"] is True
    assert len(read["content"]) == 8

    assert _patch(
        f"/api/nodes/{created['node_id']}/text", {"content": "y" * 32}
    ).status_code == 400


def test_reading_text_in_another_library_is_403(catalog_table, media_bucket, signed_in):
    _second_library(catalog_table)

    assert _get(f"/api/nodes/{OTHER_NODE}/text").status_code == 403


# ──────────────────────────── describing a file ────────────────────────────
#
# What a file SHOWS lives on the file. It used to live on the `REF#` row that
# made one a character's reference, which meant the same picture had a caption
# inside a reference set and none anywhere else — and twelve files in this
# library's `reference/` folders had no row, so no caption at all.


def test_a_file_takes_a_description_and_tags(catalog_table, media_bucket, signed_in):
    created = _file("plate.webp")

    resp = _patch(
        f"/api/nodes/{created['node_id']}",
        {"description": "Head and shoulders, front on.", "tags": ["face", "neutral"]},
    )

    assert resp.status_code == 200
    assert resp.get_json()["description"] == "Head and shoulders, front on."
    assert resp.get_json()["tags"] == ["face", "neutral"]


def test_tags_are_folded_so_a_selector_matches_what_somebody_typed(
    catalog_table, media_bucket, signed_in
):
    """`Poolside` and `poolside ` filtering as two things is a bug you cannot see.

    They render identically in a chip, so the only symptom is a `--pick-tag` that
    quietly returns half the set.
    """
    created = _file("plate.webp")

    resp = _patch(
        f"/api/nodes/{created['node_id']}",
        {"tags": ["  Poolside ", "poolside", "SHIRTLESS", ""]},
    )

    assert resp.get_json()["tags"] == ["poolside", "shirtless"]


def test_describing_is_not_renaming_and_the_two_cannot_be_sent_together(
    catalog_table, media_bucket, signed_in
):
    """Three operations on one address, exactly one per request.

    The same refusal `name` and `parent` already make, extended rather than
    reasoned about again: a request asking for two has orderings with different
    outcomes, and picking one silently is the failure.
    """
    created = _file("plate.webp")

    assert _patch(
        f"/api/nodes/{created['node_id']}", {"name": "other.webp", "description": "x"}
    ).status_code == 400
    assert _patch(f"/api/nodes/{created['node_id']}", {}).status_code == 400


def test_clearing_a_description_removes_it_rather_than_writing_an_empty_one(
    catalog_table, media_bucket, signed_in
):
    """`None` is a REMOVE here, the same rule the sparse `reel` key relies on."""
    created = _file("plate.webp")
    _patch(f"/api/nodes/{created['node_id']}", {"description": "something"})

    resp = _patch(f"/api/nodes/{created['node_id']}", {"description": ""})

    assert "description" not in resp.get_json()
    assert catalog.node(created["node_id"]).get("description") is None


def test_a_description_survives_a_rename_and_a_move(catalog_table, media_bucket, signed_in):
    """It describes the picture, not the filename and not the folder."""
    folder = _folder("elsewhere")
    created = _file("plate.webp")
    _patch(f"/api/nodes/{created['node_id']}", {"description": "the pool at dusk"})

    _patch(f"/api/nodes/{created['node_id']}", {"name": "renamed.webp"})
    _patch(f"/api/nodes/{created['node_id']}", {"parent": folder["node_id"]})

    assert catalog.node(created["node_id"])["description"] == "the pool at dusk"


# ── the content hash ────────────────────────────────────────────────────────


def test_confirming_an_upload_records_the_content_hash(catalog_table, media_bucket, signed_in):
    """**The MD5, taken off the ETag S3 already returns.**

    Every upload this API signs is a single PUT — `max_upload_bytes` is S3's own
    ceiling and there is no multipart grant — so the ETag *is* the content hash
    rather than the hash-of-hashes a multipart upload produces.

    Recorded because `studio curate dedupe` was downloading every same-size
    candidate to compute exactly this, over HTTPS, out of the bucket: hashing a
    forty-image pool to find no duplicates was forty downloads.
    """
    created = _placeholder()
    _post(f"/api/nodes/{created['node_id']}/upload-url",
          {"size": 4, "content_type": "video/mp4"})
    media_bucket.put_object(Bucket=config.media_bucket(), Key=_api_key(created),
                            Body=b"four", ContentType="video/mp4")

    body = _post(f"/api/nodes/{created['node_id']}/confirm-upload", {}).get_json()

    assert body["checksum"] == hashlib.md5(b"four").hexdigest()
    assert catalog.node(created["node_id"])["checksum"] == body["checksum"]


def test_two_identical_uploads_share_a_hash(catalog_table, media_bucket, signed_in):
    """Which is the whole point: equality of the served value means equal bytes."""
    hashes = []
    for name in ("one.mp4", "two.mp4"):
        created = _placeholder(name=name)
        _post(f"/api/nodes/{created['node_id']}/upload-url",
              {"size": 4, "content_type": "video/mp4"})
        media_bucket.put_object(Bucket=config.media_bucket(), Key=_api_key(created),
                                Body=b"same", ContentType="video/mp4")
        hashes.append(
            _post(f"/api/nodes/{created['node_id']}/confirm-upload", {}).get_json()["checksum"]
        )
    assert hashes[0] == hashes[1]


def test_a_copy_carries_the_sources_hash(catalog_table, media_bucket, signed_in):
    """A copy IS byte-identical, and a server-side `CopyObject` keeps the ETag."""
    source = _placeholder(name="original.mp4")
    _post(f"/api/nodes/{source['node_id']}/upload-url",
          {"size": 4, "content_type": "video/mp4"})
    media_bucket.put_object(Bucket=config.media_bucket(), Key=_api_key(source),
                            Body=b"same", ContentType="video/mp4")
    confirmed = _post(f"/api/nodes/{source['node_id']}/confirm-upload", {}).get_json()

    folder = catalog.create_node(CATALOG_ROOT, "copies", catalog.KIND_FOLDER)
    copied = _post("/api/nodes/copy", {"ids": [source["node_id"]],
                                       "destination": folder["node_id"]}).get_json()
    assert copied["nodes"][0]["checksum"] == confirmed["checksum"]


def test_a_multipart_etag_is_not_recorded_as_a_hash():
    """`-N` means a hash of part hashes, which differs by part size for one file.

    Storing it would be storing a value that compares unequal for two identical
    uploads — worse than storing nothing, because nothing falls back to reading
    the bytes and a wrong hash silently reports "not duplicates".
    """
    assert s3.content_hash({"ETag": '"d41d8cd98f00b204e9800998ecf8427e-3"'}) is None
    assert s3.content_hash({"ETag": '"d41d8cd98f00b204e9800998ecf8427e"'}) == \
        "d41d8cd98f00b204e9800998ecf8427e"
    assert s3.content_hash({}) is None
