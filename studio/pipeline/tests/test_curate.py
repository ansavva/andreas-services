"""`studio curate` — the claim #306 is actually about, checked against the API.

**A rename is a row update and a move is a reparent. Neither writes an object.**
That is the headline, and `conftest`'s moto shim cannot show it: that shim spells
a `PATCH` as a copy plus a delete, which is precisely the behaviour being
retired, so a test built on it would pass while asserting the opposite. The shim
says so in its own docstring and points here.

So this file stands a small catalog behind `api.get/post/patch/delete` and counts
what the commands send. Node ids are opaque (`n1`, `n2`, …) and deliberately not
paths — the shim's id-is-the-key fiction is harmless where nothing reads an id,
and here an id surviving a rename IS the assertion.

**"No object written" means no IMAGE written.** Both commands do write: the
bible, because a description has to follow its image, and any run that cited a
moved path. That is `rewrite`'s half of #306 — the half that survived, for the
reason its module docstring gives — and it is a record rather than a blob. What
must not happen is an image being re-uploaded, and that is what is asserted.
"""

import json
import re

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store
from studio_pipeline.domain import curate

NAME = "subject-a"
REF = f"characters/{NAME}/reference"
FACE = f"{REF}/face"
CITING_RUN = f"projects/{NAME}/runs/2026-08-05_09-00-00_ref-shot/request.json"

BIBLE = f"""\
schema_version: 1
name: {NAME}
display_name: Subject A
references:
- file: face/{NAME}_face_1.webp
  description: front, neutral
  tags: [face]
- file: face/{NAME}_face_3.webp
  description: three-quarter
  tags: [face]
- file: {NAME}_5.webp
  description: ungrouped, described
  tags: []
default_set:
- face/{NAME}_face_1.webp
"""

# A hole at 2, and one loose image outside every group. Byte contents differ in
# LENGTH as well as value, so `duplicate_pairs` can be given both cases.
TREE = {
    f"characters/{NAME}/profile.yaml": BIBLE.encode(),
    f"{FACE}/{NAME}_face_1.webp": b"face-one",
    f"{FACE}/{NAME}_face_3.webp": b"face-three-longer",
    f"{REF}/{NAME}_5.webp": b"loose-five",
    f"projects/{NAME}/project.json": json.dumps({"project": NAME}).encode(),
    CITING_RUN: json.dumps({
        "model": "nano-banana-pro",
        "bindings": {"image_input": [f"{REF}/{NAME}_5.webp"]},
    }).encode(),
}


class Catalog:
    """A name-tree with opaque ids, standing in for the API's node routes.

    Only the routes `store` and `curate` actually call. An unhandled route is an
    `AssertionError` rather than a default, because a command reaching a route
    this does not model is exactly the thing worth failing on.
    """

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.blobs: dict[str, bytes] = {}
        self.calls: list[tuple[str, str]] = []
        self.patched: list[tuple[str, dict]] = []
        self.uploaded: list[str] = []
        self.fetched: list[str] = []
        self._n = 0
        self.root = self._new(None, "")

    # -- the tree ---------------------------------------------------------

    def _new(self, parent, name, kind="folder") -> dict:
        self._n += 1
        node = {"id": f"n{self._n}", "name": name, "kind": kind, "parent": parent,
                "size": 0, "updated_at": "2026-08-21T00:00:00.000001+00:00"}
        self.nodes[node["id"]] = node
        return node

    def _child(self, parent_id, name):
        return next((n for n in self.nodes.values()
                     if n["parent"] == parent_id and n["name"] == name), None)

    def seed(self, path: str, body: bytes) -> dict:
        parts = path.strip("/").split("/")
        node = self.root
        for part in parts[:-1]:
            node = self._child(node["id"], part) or self._new(node["id"], part, "folder")
        leaf = self._new(node["id"], parts[-1], "file")
        self.blobs[leaf["id"]] = body
        leaf["size"] = len(body)
        return leaf

    def resolve(self, path: str) -> dict:
        node = self.root
        for part in [p for p in path.strip("/").split("/") if p]:
            node = self._child(node["id"], part)
            if node is None:
                raise api.NotFound(f"No such node: {path}", 404)
        return dict(node)

    def path_of(self, node_id: str) -> str:
        parts = []
        node = self.nodes[node_id]
        while node["parent"] is not None:
            parts.append(node["name"])
            node = self.nodes[node["parent"]]
        return "/".join(reversed(parts))

    # -- the routes -------------------------------------------------------

    def get(self, route, **params):
        self.calls.append(("GET", route))
        if route == "/api/resolve":
            return self.resolve(params["path"])
        if route == "/api/nodes":
            # Name-ascending, as the catalog's sort key returns them. `store`
            # re-sorts naturally on top; handing it sorted input here would hide
            # a caller that relies on the API's order.
            return sorted((dict(n) for n in self.nodes.values()
                           if n["parent"] == params["parent"]),
                          key=lambda n: n["name"])
        found = re.fullmatch(r"/api/nodes/(\w+)/download-url", route)
        if found:
            self.fetched.append(found.group(1))
            return {"url": f"blob:{found.group(1)}"}
        raise AssertionError(f"unhandled GET {route}")

    def post(self, route, payload=None, **params):
        self.calls.append(("POST", route))
        if route == "/api/nodes":
            if self._child(payload["parent"], payload["name"]):
                raise api.Conflict(f"{payload['name']} already exists", 409)
            return dict(self._new(payload["parent"], payload["name"], payload["kind"]))
        found = re.fullmatch(r"/api/nodes/(\w+)/upload-url", route)
        if found:
            return {"url": f"blob:{found.group(1)}", "headers": {}}
        found = re.fullmatch(r"/api/nodes/(\w+)/confirm-upload", route)
        if found:
            node = self.nodes[found.group(1)]
            node["size"] = len(self.blobs.get(node["id"], b""))
            return dict(node)
        raise AssertionError(f"unhandled POST {route}")

    def patch(self, route, payload, **params):
        self.calls.append(("PATCH", route))
        node_id = route.removeprefix("/api/nodes/")
        self.patched.append((node_id, dict(payload)))
        node = self.nodes[node_id]
        if "name" in payload:
            node["name"] = payload["name"]
        if "parent" in payload:
            node["parent"] = payload["parent"]
        return dict(node)

    def delete(self, route, **params):
        self.calls.append(("DELETE", route))
        node = self.nodes.pop(route.removeprefix("/api/nodes/"))
        self.blobs.pop(node["id"], None)
        return {"id": node["id"], "deleted": 1}

    # -- the bytes, which do not go through the API ------------------------

    def fetch(self, url):
        return self.blobs[url.removeprefix("blob:")]

    def put(self, url, body, headers):
        node_id = url.removeprefix("blob:")
        self.uploaded.append(node_id)
        self.blobs[node_id] = body

    @property
    def uploaded_paths(self) -> list[str]:
        return [self.path_of(node_id) for node_id in self.uploaded]

    @property
    def uploaded_images(self) -> list[str]:
        return [p for p in self.uploaded_paths
                if p.rsplit(".", 1)[-1].lower() in {"webp", "png", "jpg", "jpeg"}]


@pytest.fixture
def catalog(monkeypatch):
    """`adapters.api` replaced wholesale, and the byte transport with it.

    `store._fetch` / `store._put` are the presigned-URL leg, which by design is
    not an API call at all — leaving them live would reach the network, and
    stubbing them is also what makes an upload countable.
    """
    cat = Catalog()
    for path, body in TREE.items():
        cat.seed(path, body)
    for name in ("get", "post", "patch", "delete"):
        monkeypatch.setattr(api, name, getattr(cat, name))
    monkeypatch.setattr(store, "_fetch", cat.fetch)
    monkeypatch.setattr(store, "_put", cat.put)
    return cat


def run(*argv):
    return CliRunner().invoke(cli.main, ["curate", *argv])


# ── the headline: a row update, and no image written ────────────────────────

def test_renumber_renames_rows_and_writes_no_image(catalog):
    """`3 -> 2` is one `PATCH`. The blob keeps its id, its bytes and its key."""
    node_id = catalog.resolve(f"{FACE}/{NAME}_face_3.webp")["id"]
    before = catalog.blobs[node_id]

    result = run("renumber", NAME, "--group", "face", "--apply")
    assert result.exit_code == 0, result.output

    assert catalog.patched == [(node_id, {"name": f"{NAME}_face_2.webp"})]
    assert catalog.uploaded_images == []
    assert [call for call in catalog.calls if call[0] == "DELETE"] == []
    # Same node under the new name, and nothing re-uploaded into it.
    assert catalog.resolve(f"{FACE}/{NAME}_face_2.webp")["id"] == node_id
    assert catalog.blobs[node_id] == before
    assert node_id not in catalog.uploaded
    # The description followed, which is the one write this makes.
    assert catalog.uploaded_paths == [f"characters/{NAME}/profile.yaml"]
    bible = catalog.blobs[catalog.resolve(f"characters/{NAME}/profile.yaml")["id"]].decode()
    assert f"face/{NAME}_face_2.webp" in bible
    assert "three-quarter" in bible


def test_regroup_reparents_and_writes_no_image(catalog):
    """Into `face/`: one `PATCH` carrying a parent, and the basename untouched."""
    node_id = catalog.resolve(f"{REF}/{NAME}_5.webp")["id"]
    before = catalog.blobs[node_id]

    result = run("regroup", f"{NAME}_5.webp", "face", NAME, "--apply")
    assert result.exit_code == 0, result.output

    assert catalog.patched == [(node_id, {"parent": catalog.resolve(FACE)["id"]})]
    assert catalog.uploaded_images == []
    assert [call for call in catalog.calls if call[0] == "DELETE"] == []
    assert catalog.resolve(f"{FACE}/{NAME}_5.webp")["id"] == node_id
    assert catalog.blobs[node_id] == before
    assert node_id not in catalog.uploaded
    # The record that cited the old path followed — see `rewrite`'s docstring
    # for why a rename does not spare it.
    cited = json.loads(catalog.blobs[catalog.resolve(CITING_RUN)["id"]])
    assert cited["bindings"]["image_input"] == [f"{FACE}/{NAME}_5.webp"]


# ── dedupe: the cheap test first ────────────────────────────────────────────

def test_duplicate_pairs_compares_size_before_reading_bytes(catalog):
    """Different sizes cannot be identical, so nothing is downloaded at all.

    Exact rather than a heuristic, and it is the read that costs: a read is now
    an HTTPS round trip out of the bucket, where the S3 version hashed every
    object in the pool inside it.
    """
    entries = [{"path": path, "size": len(TREE[path]), "name": path.rsplit("/", 1)[-1]}
               for path in (f"{FACE}/{NAME}_face_1.webp", f"{FACE}/{NAME}_face_3.webp")]
    assert {e["size"] for e in entries} == {8, 17}

    assert curate.duplicate_pairs(entries) == []
    assert catalog.fetched == []


def test_same_size_candidates_are_still_read_and_compared(catalog):
    """Size is a filter, never the verdict — two 8-byte files may well differ."""
    catalog.seed(f"{FACE}/{NAME}_face_4.webp", b"face-one")
    catalog.seed(f"{FACE}/{NAME}_face_5.webp", b"one-face")
    entries = [
        {"path": f"{FACE}/{NAME}_face_1.webp", "size": 8, "name": f"{NAME}_face_1.webp"},
        {"path": f"{FACE}/{NAME}_face_4.webp", "size": 8, "name": f"{NAME}_face_4.webp"},
        {"path": f"{FACE}/{NAME}_face_5.webp", "size": 8, "name": f"{NAME}_face_5.webp"},
    ]
    dupes = curate.duplicate_pairs(entries)
    assert [(d["path"], k["path"]) for d, k in dupes] == [
        (f"{FACE}/{NAME}_face_4.webp", f"{FACE}/{NAME}_face_1.webp")]
    assert len(catalog.fetched) == 3


# ── the ordering that survives the migration ────────────────────────────────

def test_ordered_moves_breaks_a_swap_through_a_temporary():
    """`1 -> 2, 2 -> 1` cannot be done in place, catalog or bucket.

    A folder refuses a duplicate name where a bucket would silently overwrite
    one, so the failure mode changed and the need did not.
    """
    one, two = f"{FACE}/{NAME}_face_1.webp", f"{FACE}/{NAME}_face_2.webp"
    plan = curate.ordered_moves([(one, two), (two, one)])

    assert len(plan) == 3, plan  # the extra step IS the temporary
    assert {src for src, _ in plan} - {one, two}, "no temporary was introduced"

    occupied = {one, two}
    for src, dst in plan:
        assert dst not in occupied, f"{dst} would be clobbered by {src}"
        occupied.discard(src)
        occupied.add(dst)
    assert occupied == {one, two}
