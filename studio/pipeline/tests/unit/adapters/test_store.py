"""`adapters/store` — the media store reached through the API (#302, step a).

**Stubbed at `api` and at `urlopen`, not at `store`.** The two halves fail
differently and both matter: an API call that 404s is a missing node, and a
presigned URL that fails is almost always an expired signature. A test that
stubbed `store` itself would assert nothing about either.
"""

from __future__ import annotations

import io
import urllib.error

import pytest

from studio_pipeline.adapters import api, store


class _Response(io.BytesIO):
    def __init__(self, body: bytes = b"") -> None:
        super().__init__(body)
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def apis(monkeypatch):
    """Records every API call and answers from a scripted table."""
    calls = []
    table = {}

    # `_route`, not `path`: `store.resolve` calls `api.get(..., path=...)`, and a
    # stub whose first parameter is also named `path` collides with the keyword.
    def _get(_route, **params):
        calls.append(("GET", _route, params))
        return table[("GET", _route)]

    def _post(_route, payload=None, **params):
        calls.append(("POST", _route, payload))
        value = table[("POST", _route)]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(api, "get", _get)
    monkeypatch.setattr(api, "post", _post)
    return calls, table


def test_resolve_asks_the_api_for_a_name_path(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1", "name": "face_01.png"}

    assert store.resolve("/characters/<name>/reference/face_01.png")["id"] == "node-1"
    # Leading and trailing slashes are the caller's habit, not the API's problem.
    assert calls[0][2] == {"path": "characters/<name>/reference/face_01.png"}


def test_read_fetches_the_presigned_url_not_the_api(apis, monkeypatch):
    """Bytes never travel through the API — that is what keeps a video out of the Lambda."""
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed"}
    fetched = {}

    def _urlopen(url, timeout=None):  # noqa: ARG001
        fetched["url"] = url if isinstance(url, str) else url.full_url
        return _Response(b"the-bytes")

    monkeypatch.setattr(store.urllib.request, "urlopen", _urlopen)

    assert store.read("characters/<name>/reference/face_01.png") == b"the-bytes"
    assert fetched["url"] == "https://s3/signed"


def test_presign_passes_the_disposition_through(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed"}

    assert store.presign("clip.mp4", disposition="attachment") == "https://s3/signed"
    assert calls[-1][2] == {"disposition": "attachment"}


def test_write_creates_then_uploads_then_confirms(apis, monkeypatch):
    """The order is the recoverable one: a failure before confirm leaves a placeholder."""
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-parent"}
    table[("POST", "/api/nodes")] = {"id": "node-new"}
    table[("POST", "/api/nodes/node-new/upload-url")] = {
        "url": "https://s3/put",
        "headers": {"Content-Length": "9", "Content-Type": "text/plain"},
    }
    table[("POST", "/api/nodes/node-new/confirm-upload")] = {"id": "node-new", "size": 9}
    sent = {}

    def _urlopen(request, timeout=None):  # noqa: ARG001
        sent["method"] = request.method
        sent["body"] = request.data
        sent["type"] = request.get_header("Content-type")
        return _Response()

    monkeypatch.setattr(store.urllib.request, "urlopen", _urlopen)

    result = store.write("projects/<project>/notes.txt", b"the-bytes", content_type="text/plain")

    assert result["size"] == 9
    assert sent["method"] == "PUT"
    assert sent["body"] == b"the-bytes"
    # Exactly the headers the API signed — anything else fails the signature.
    assert sent["type"] == "text/plain"
    assert [c[0] + " " + c[1] for c in calls] == [
        "GET /api/resolve",
        "POST /api/nodes",
        "POST /api/nodes/node-new/upload-url",
        "POST /api/nodes/node-new/confirm-upload",
    ]


def test_writing_over_an_existing_file_keeps_its_node(apis, monkeypatch):
    """A replace must not mint a new id — every record naming it would go stale."""
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-existing"}
    table[("POST", "/api/nodes")] = api.Conflict("'notes.txt' already exists here", 409)
    table[("POST", "/api/nodes/node-existing/upload-url")] = {
        "url": "https://s3/put",
        "headers": {"Content-Length": "3", "Content-Type": "text/plain"},
    }
    table[("POST", "/api/nodes/node-existing/confirm-upload")] = {"id": "node-existing"}
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: _Response())

    assert store.write("projects/<project>/notes.txt", b"new", content_type="text/plain")["id"] == (
        "node-existing"
    )


def test_a_failed_fetch_does_not_echo_the_signed_url(apis, monkeypatch):
    """A presigned URL in a traceback is a working credential in the scrollback."""
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed?X-Amz-Signature=abc"}

    def _urlopen(url, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("Forbidden")

    monkeypatch.setattr(store.urllib.request, "urlopen", _urlopen)

    with pytest.raises(store.StoreError) as caught:
        store.read("clip.mp4")

    assert "X-Amz-Signature" not in str(caught.value)
    assert "Forbidden" in str(caught.value)


def test_children_lists_one_level(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-folder"}
    table[("GET", "/api/nodes")] = {
        "entries": [{"id": "node-a", "name": "a.png", "kind": "image"}],
        "next_cursor": None,
    }

    assert store.children("characters/<name>/reference")[0]["name"] == "a.png"
    # `under`, not `parent` — one listing route now, and it defaults to the
    # library root rather than refusing a request that names no folder.
    assert calls[-1][2] == {"sort": "name", "limit": store.PAGE,
                            "cursor": None, "under": "node-folder"}


def test_download_writes_to_disk_creating_parents(apis, monkeypatch, tmp_path):
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1"}
    table[("GET", "/api/nodes/node-1/download-url")] = {"url": "https://s3/signed"}
    monkeypatch.setattr(store.urllib.request, "urlopen", lambda *a, **k: _Response(b"xyz"))

    written = store.download("clip.mp4", tmp_path / "nested" / "clip.mp4")

    assert written.read_bytes() == b"xyz"


def test_resolve_goes_through_the_real_api_signature(monkeypatch):
    """**The regression guard for a bug the other tests here could not see.**

    Every test above stubs `api.get`, and a stub is free to name its first
    parameter anything. The real one was not: `def get(path, **params)`, while
    `store.resolve` calls `api.get("/api/resolve", path=...)`. The two collided,
    so `resolve` raised `TypeError` on every call — and the suite was green,
    because no test drove the real signature.

    This one stubs `urlopen` instead, so the signature is part of what is
    asserted.
    """
    from studio_pipeline.adapters import auth

    monkeypatch.setattr(auth, "id_token", lambda **_: "token")
    monkeypatch.setattr(auth, "api_url", lambda: "https://api.example")
    seen = {}

    def _urlopen(request, timeout=None):  # noqa: ARG001
        seen["url"] = request.full_url
        return _Response(b'{"id": "node-1"}')

    monkeypatch.setattr(api.urllib.request, "urlopen", _urlopen)

    assert store.resolve("characters/<name>/reference")["id"] == "node-1"
    assert "path=characters" in seen["url"]


# ──────────────────────────── folders (#304) ────────────────────────────
#
# Folders were free in S3 — a key with slashes in it looked like one — and are
# rows now. `store.folder` is what a caller uses to say a run exists before
# writing a document inside it.


def test_an_existing_folder_is_returned_without_creating_anything(apis):
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-runs", "kind": "folder"}

    assert store.folder("projects/<project>/runs")["id"] == "node-runs"
    assert not [call for call in calls if call[0] == "POST"]


def test_a_missing_folder_is_created_under_its_parent(apis, monkeypatch):
    calls, table = apis
    # `store.folder` resolves the folder and then its parent, and both are
    # `GET /api/resolve` — so this one answers by path rather than by route.
    def _get(_route, **params):
        calls.append(("GET", _route, params))
        if params.get("path") == "projects/<project>/runs":
            raise api.NotFound("no such node", 404)
        return {"id": "node-project", "kind": "folder"}

    monkeypatch.setattr(api, "get", _get)
    table[("POST", "/api/nodes")] = {"id": "node-runs", "kind": "folder"}

    assert store.folder("projects/<project>/runs")["id"] == "node-runs"
    assert calls[-1] == (
        "POST", "/api/nodes",
        {"parent": "node-project", "name": "runs", "kind": "folder"},
    )


def test_a_folder_that_appears_between_the_resolve_and_the_create_is_not_an_error(
    apis, monkeypatch
):
    """409 means somebody else made it, and the node they made is the answer."""
    calls, table = apis
    answers = [api.NotFound("no such node", 404), {"id": "node-parent", "kind": "folder"},
               {"id": "node-theirs", "kind": "folder"}]

    def _get(_route, **params):
        calls.append(("GET", _route, params))
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(api, "get", _get)
    table[("POST", "/api/nodes")] = api.Conflict("'runs' already exists here", 409)

    assert store.folder("projects/<project>/runs")["id"] == "node-theirs"


def test_a_file_is_not_a_folder(apis):
    """Refused here, where the path is still known.

    `catalog.create_node` would refuse the children one at a time, naming the
    parent's id — which says nothing about which path was wrong.
    """
    _, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-1", "kind": "file"}

    with pytest.raises(store.StoreError, match="is a file"):
        store.folder("projects/<project>/project.json")


def test_a_missing_chain_of_folders_is_created_deepest_last(apis, monkeypatch):
    """Ancestors too, so a caller states the path it wants rather than walking it.

    `projects/<p>/runs/<run>/output` is four levels below the root and a fresh
    project has none of them: `projects/<p>` is written by `project create` and
    the rest were free in S3. Creating only the leaf would 404 on its parent.
    """
    calls, table = apis
    present = {"projects"}

    def _get(_route, **params):
        calls.append(("GET", _route, params))
        path = params.get("path")
        if path not in present:
            raise api.NotFound(f"no such node: {path}", 404)
        return {"id": f"node:{path}", "kind": "folder"}

    def _post(_route, payload=None, **params):
        calls.append(("POST", _route, payload))
        return {"id": f"node:{payload['name']}", "kind": "folder"}

    monkeypatch.setattr(api, "get", _get)
    monkeypatch.setattr(api, "post", _post)

    store.folder("projects/<project>/runs")

    assert [payload["name"] for verb, route, payload in calls
            if verb == "POST" and route == "/api/nodes"] == ["<project>", "runs"]


# ──────────────────────────── listing files (#305) ────────────────────────────


def test_files_are_natural_sorted_and_folders_are_dropped(apis):
    """Three decisions in one place, because each has been a bug somewhere.

    The order is positional downstream (`[Image1]..[ImageN]`), and the catalog
    returns folders in the same list as files — where `list_objects_v2` put them
    in a separate field, so the filter used to be structural and is now explicit.

    **The filter is the negative now.** One listing serves the app and this
    package, and its `kind` says what a file HOLDS — `image`, `video`, `text` —
    so "is it a file" is "is it not a folder".
    """
    calls, table = apis
    table[("GET", "/api/resolve")] = {"id": "node-folder", "kind": "folder"}
    table[("GET", "/api/nodes")] = {
        "entries": [
            {"name": "shot-10.png", "kind": "image"},
            {"name": "shot-2.png", "kind": "image"},
            {"name": "shot-1.png", "kind": "image"},
            {"name": "thumbs", "kind": "folder"},
        ],
        "next_cursor": None,
    }

    assert [entry["name"] for entry in store.files("projects/<project>/input")] == [
        "shot-1.png", "shot-2.png", "shot-10.png",
    ]
    assert calls  # the listing was actually fetched, not assumed


def test_a_folder_that_is_not_there_lists_as_empty(apis, monkeypatch):
    """Callers ask "what is in here" and none tells absent from empty.

    `resolve` 404s on a project with no `input/` yet, and the paginator this
    replaces answered the same question with zero keys.
    """
    _, _ = apis

    def _get(_route, **params):
        raise api.NotFound("no such node", 404)

    monkeypatch.setattr(api, "get", _get)

    assert store.files("projects/<project>/input") == []


# ── the tree, addressed by node id ──────────────────────────────────────────
#
# The half of this module the entity model added. These go through the
# in-memory API rather than the scripted stub above, because the interesting
# question about an id-addressed operation is what the *catalog* ends up
# holding, and a stub that echoes the request cannot answer it.


def test_a_child_that_is_not_there_is_none_not_an_error(library):
    """The self-healing property the layout section describes.

    The conventional folders are convention: a route that cannot find one is
    entitled to make one rather than to fail, and `child` returning None is what
    lets `ensure_child_folder` do that without a try/except at every call site.
    """
    assert store.child(library.character_root, "reference") is not None
    assert store.child(library.character_root, "wardrobe-refs") is None


def test_ensuring_a_folder_twice_returns_the_same_node(library):
    first = store.ensure_child_folder(library.character_root, "wardrobe-refs")
    second = store.ensure_child_folder(library.character_root, "wardrobe-refs")
    assert first["id"] == second["id"]


def test_ensuring_a_folder_over_a_file_is_refused(library):
    """A caller asking for a folder is about to write children into it."""
    with pytest.raises(store.StoreError, match="not a folder"):
        store.ensure_child_folder(library.face_folder, "front-neutral.webp")


def test_folder_path_walks_and_creates_the_whole_chain(library):
    leaf = store.folder_path(library.project_root, "runs", "made-up", "output")
    assert store.node(leaf["id"])["name"] == "output"
    assert store.child(store.child(library.project_root, "runs")["id"],
                       "made-up") is not None


def test_files_of_is_natural_sorted_and_drops_folders(library):
    """`_10` before `_2` is lexical order, and these map positionally.

    The catalog returns files and folders in one list keyed by `kind`, where
    `list_objects_v2` with a delimiter put folders in a separate field — so the
    filter is explicit where it used to be structural.
    """
    reference = store.node(library.reference)
    assert store.files_of(reference["id"]) == []          # face/ and body/ are folders
    for name in ("shot_10.webp", "shot_2.webp"):
        library.fake.put_file(library.face_folder, name, b"x")
    assert [entry["name"] for entry in store.files_of(library.face_folder)] == [
        "front-neutral.webp", "shot_2.webp", "shot_10.webp", "three-quarter.webp"]


def test_writing_into_a_folder_by_id_confirms_the_size(library):
    """Placeholder, PUT, confirm — the recoverable order.

    A failure before the confirm leaves a row nobody sees; a failure after it
    would leave a row promising bytes that are not there.
    """
    node = store.write_into(library.face_folder, "made.txt", b"hello",
                            content_type="text/plain")
    assert node["size"] == 5
    assert store.read_node(node["id"]) == b"hello"


def test_rewriting_a_file_keeps_its_node_id(library):
    """**The property every record naming it depends on.**"""
    first = store.write_into(library.face_folder, "made.txt", b"one",
                             content_type="text/plain")
    second = store.write_into(library.face_folder, "made.txt", b"two",
                              content_type="text/plain")
    assert first["id"] == second["id"]
    assert store.read_node(first["id"]) == b"two"


def test_renaming_a_node_writes_no_object(library):
    """A name is a column. The blob does not know it changed.

    Under S3 this was a `CopyObject` plus a `DeleteObject`, because a key IS the
    location — which is why renumbering a reference pool destroyed and recreated
    every file in it.
    """
    before = library.fake.nodes[library.face_1]["blob_key"]
    store.rename_node(library.face_1, "renamed.webp")
    assert library.fake.nodes[library.face_1]["blob_key"] == before
    assert store.node(library.face_1)["name"] == "renamed.webp"


def test_copying_a_node_makes_a_second_blob(library):
    """A real copy — two blobs, two independent lifetimes.

    Not a second row on one blob: that is copy-on-write (#334), and the delete
    route destroys the shared bytes when either row goes.
    """
    made = store.copy_nodes([library.face_1], library.body_folder)["nodes"][0]
    assert made["id"] != library.face_1
    assert (library.fake.nodes[made["id"]]["blob_key"]
            != library.fake.nodes[library.face_1]["blob_key"])
    assert store.read_node(made["id"]) == store.read_node(library.face_1)


def test_a_nodes_owner_is_derived_from_its_ancestry(library):
    """Derived, not stored — so a move that changes the owner is visible at once.

    The blob key it was stamped with is not rewritten, which is the drift
    `catalog reseat` exists to clean up out of band.
    """
    assert store.node_owner(library.face_1) == {
        "kind": "character", "id": library.character, "slug": "subject-a"}
    assert store.node_owner(library.run_output)["kind"] == "project"


def test_a_blob_key_carries_the_owner_and_the_node_and_no_name(library):
    """**A bucket listing stops leaking hard rule #1.**

    `<owner_kind>/<owner_id>/<node_id>.<ext>`, stamped once at creation from the
    owner the parent already resolves to. Never parsed, never re-derived. The
    rule is env-scoped for the REPO; a production bucket listing is not the
    repo, and this property is what keeps it clean.
    """
    key = library.fake.nodes[library.face_1]["blob_key"]
    assert key == f"characters/{library.character}/{library.face_1}.webp"
    assert "subject-a" not in key


def test_moving_a_node_out_of_a_character_leaves_its_key_alone(library):
    """The honest cost of entity-prefixed keys, asserted rather than assumed.

    The key is still a correct pointer — it is never parsed — but it now *looks*
    like it means something it does not. `catalog verify` reports the drift and
    `catalog reseat --apply` rewrites it, out of band and never automatically.
    """
    before = library.fake.nodes[library.face_1]["blob_key"]
    store.move_nodes([library.face_1], library.input_pool)
    assert library.fake.nodes[library.face_1]["blob_key"] == before
    assert store.node_owner(library.face_1)["kind"] == "project"


def test_deleting_an_entitys_root_folder_is_refused(library):
    """The one hard rule the convention-not-schema layout leaves.

    Everything else under a character may be renamed, moved or deleted. Its root
    may not, while the character exists — the delete route says which entity to
    delete instead.
    """
    with pytest.raises(api.Conflict, match="root folder"):
        store.delete_nodes([library.character_root])


def test_node_text_reads_a_payload_document_without_decoding_it(library):
    record = api.get(f"/api/runs/{library.run}")
    assert '"prompt"' in store.node_text(record["payload"]["request"])
