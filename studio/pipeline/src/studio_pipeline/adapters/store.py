"""The media store, addressed by path and reached through the API (#302).

**This is the seam that ends direct AWS access from the pipeline.** Call sites
say "the object at `characters/<name>/reference/face_01.png`"; this resolves that
name path to a node through `GET /api/resolve` and moves bytes through presigned
URLs the API hands out. No boto3, no bucket name, no credentials.

## Why a path-addressed facade rather than rewriting every call site to use ids

Twenty-five modules and seventy-one boto3 calls addressed the tree by key when
this was written, and every `SKILL.md` described the CLI in those terms.
Rewriting all of them to carry node ids in one change would have been a refactor
nobody could review, so this kept the vocabulary the pipeline already had — a
path — and changed only what sits underneath it, and the call sites migrated one
area at a time.

**They have.** What still opens an S3 client is `adapters/s3.py`, `adapters/ddb`
borrowing its session, and the four `maintenance/` commands, which reconcile the
bucket against the table and so have to see both. Everything else is here. The
census above is the history of why this module exists, not a count of what is
left to do.

**The path is not a key.** It is the name path the API resolves: the same string
a person types and the same one `paths.py` builds. That it currently equals the
S3 key is a coincidence of how the tree was laid out, and one that ends the first
time a node is renamed without its blob moving.

## Bytes do not go through the API

`GET /api/nodes/<id>/download-url` and `POST /api/nodes/<id>/upload-url` return
presigned URLs, and the bytes travel directly to S3. That is what keeps a video
out of the Lambda's 6 MB request limit, and it is also **hard rule #3 intact**:
anything handed to a model is an S3 object reached by a short-lived presigned
URL, never an upload from disk.

## One way in, and there used to be two

Everything in the bucket is now addressed the same way: a node id, or a name
path the API resolves to one. There is no second scheme and no exception.

**There was, and it is worth knowing what closed it.** `phrasebook/wording.yaml`
and the `config/pose/` plates belonged to no character and no project, had no
catalog node, and were reached by raw key through `GET /api/asset?key=` by a
pair of `shared_*` functions here. That parameter was the last raw S3 key in the
service and the sole reason `keys.clean_key` survived on the API side.

Both halves went with the entity model rather than one of them: the phrasebook
is `TERM#` rows, so there is no document to address, and the plates are ordinary
nodes in a `config/` folder the library is created with. So `shared_read`,
`shared_presign` and the `shared:<key>` marker `submit` carried them under are
all deleted, and a plate is now *recorded* in a run's bindings like every other
image — which the marker could not do, and said so.

## What is deliberately not here

No `delete`, no `move`, no `rename`. Those are catalog operations now — a move
rewrites rows and touches no object — and they belong on the API's node routes,
which the migrating call sites call directly. A byte mover that also pretended
to move things would invite exactly the key-shuffling this replaces.

`copy` is here and is the exception that proves it: it moves bytes, twice, and
says so. See its docstring for why it is not the cheap catalog operation it
looks like.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path

from studio_pipeline.adapters import api

TIMEOUT_SECONDS = 300


class StoreError(RuntimeError):
    """The store could not be read or written."""


_NUM_RE = re.compile(r"(\d+)")


def natural_key(name: str):
    """Sort key so `<name>_2` precedes `<name>_10`, which lexical sort flips.

    **Load-bearing, not cosmetic.** `studio presign --folder <name>/reference`
    feeds images to a model as `[Image1]..[ImageN]` and the mapping is
    positional — a folder that sorted `_10` before `_2` would hand the model its
    references in the wrong order, and the prompt would name the wrong one.

    It lives here because the API returns children *name-ascending*, which is
    DynamoDB's lexical sort-key order. The natural ordering is the CLI's, and
    always was. `adapters/s3.py` re-exports it — but not, as this used to say,
    to spare its callers a churn: that module counted them and there are none.
    The re-export is kept for its own `_list`, on the weaker ground it states.
    """
    return [int(part) if part.isdigit() else part.lower() for part in _NUM_RE.split(name)]


def resolve(path: str) -> dict:
    """The node at a name path, or `api.NotFound`.

    An empty path is the library root — the one node no listing hands out, and
    where a client starts.
    """
    return api.get("/api/resolve", path=path.strip("/"))


def children(path: str) -> list:
    """The direct children of a folder, name-ascending.

    Not recursive, deliberately. Every caller that wanted a recursive listing
    wanted it to build a key prefix, and that is the habit this module exists to
    end — walk with `resolve` on the path you actually mean.
    """
    node = resolve(path)
    listed = api.get("/api/nodes", parent=node["id"])
    return listed if isinstance(listed, list) else []


def children_or_empty(path: str) -> list:
    """`children`, with a missing folder reported as empty rather than raising.

    The forgiving read `files` already makes, exposed on its own for the one
    caller that needs folders as well — `characters.refs.ref_files` walks the
    group subfolders, because the reference index keys entries on
    `face/<name>_1.png` and a listing one level deep would find no images at all.
    """
    try:
        return children(path)
    except api.NotFound:
        return []


def walk_files(path: str) -> list[str]:
    """Every file path beneath a folder, depth first, natural order per level.

    **The catalog has no prefix scan.** `list_objects_v2` took a prefix and
    returned the whole subtree in pages; a listing here is per folder, because
    that is the unit a node's library membership authorises. So the descent is
    explicit and costs one request per folder rather than one per thousand
    objects — worse for a wide shallow tree, and the price of the listing being
    checked rather than assumed.

    Only two callers want a subtree at all (`rewrite` and a character rename),
    and both are maintenance-shaped. Anything reading one folder should use
    `files`.
    """
    found: list[str] = []
    for entry in children_or_empty(path):
        child = f"{path.rstrip('/')}/{entry['name']}"
        if entry.get("kind") == "folder":
            found += walk_files(child)
        else:
            found.append(child)
    return found


def files(path: str) -> list[dict]:
    """The file children of a folder, natural-sorted by name. Missing folder -> [].

    Three decisions, made once. Each has already been a bug or a near one:

    - **The kind filter is now explicit where it used to be structural.**
      `list_objects_v2` with a delimiter put folders in `CommonPrefixes`, a
      separate field, so a caller got files whether it filtered or not. The
      catalog returns both in one list keyed by `kind`, and dropping the filter
      lists a subfolder as if it were an object.
    - **The natural sort is load-bearing.** `children` is name-ascending, which
      is DynamoDB's lexical order: `_10` before `_2`. These names become
      `[Image1]..[ImageN]` positionally, so lexical order hands a model the
      wrong image under the right name.
    - **A folder that is not there is empty, not an error.** Every caller asks
      "what is in here" and none distinguishes absent from empty; `resolve`
      404s on a project with no `input/` yet, and the paginator this replaces
      answered with zero keys.

    Entries, not names, because a caller usually wants `size` or `id` too.
    `paths._folder_names` is the folder-shaped twin and keeps a plain sort — its
    ids are timestamps, where a numeric-run sort asks a different question.
    """
    entries = children_or_empty(path)
    return sorted(
        (entry for entry in entries if entry.get("kind") == "file" and entry.get("name")),
        key=lambda entry: natural_key(entry["name"]),
    )


def exists(path: str) -> bool:
    """Whether a node is there. Cheaper than fetching it, and never raises."""
    try:
        resolve(path)
    except api.NotFound:
        return False
    return True


def folder(path: str) -> dict:
    """Ensure a folder exists at a name path and return its node.

    **Folders were free in S3 and are rows now**, and that is the whole reason
    this exists. `characters/<name>/reference/face/` needed no creating — a key
    with slashes in it produced the appearance of one — so nothing in the
    pipeline ever asked for a folder, and `store.write` resolves the parent it
    is given rather than inventing it. Under the catalog a run has to be told to
    exist before a document can be written inside it.

    Missing ancestors are created too, deepest last, so a caller that knows the
    path it wants does not have to walk it. Idempotent by construction: a
    `Conflict` means something else created it between the resolve and the
    create, and the node it made is the right answer.

    Refuses to hand back a file. A caller asking for a folder is about to write
    children into it, and `catalog.create_node` would refuse them one at a time
    with the parent's id rather than the path that was actually wrong.
    """
    clean = path.strip("/")
    try:
        node = resolve(clean)
    except api.NotFound:
        node = None
    if node is not None:
        if node.get("kind") != "folder":
            raise StoreError(f"{clean!r} is a file, not a folder.")
        return node
    if not clean:
        # The library root is created with the library, so its absence is not
        # something a client can fix by creating one.
        raise StoreError("The library root does not exist.")

    parent_path, _, name = clean.rpartition("/")
    parent = folder(parent_path)
    try:
        return api.post(
            "/api/nodes", {"parent": parent["id"], "name": name, "kind": "folder"}
        )
    except api.Conflict:
        return resolve(clean)


def size(path: str) -> int:
    """The recorded byte size of a file, or 0 if it has none yet.

    Off the node record rather than a HEAD against the object: the catalog knows
    this, and a placeholder that has not been confirmed genuinely has no size —
    reporting 0 is the honest answer, not a failure.
    """
    return int(resolve(path).get("size") or 0)


def copy(source: str, destination: str, *, content_type: str) -> dict:
    """Copy one file's bytes to another path.

    **The bytes travel through this process**, which a server-side
    `CopyObject` did not. That is the cost, and it is accepted here rather than
    hidden: the alternative is a second node pointing at one blob, which is
    copy-on-write (#334, deferred) and carries a hazard already written into the
    API's delete route — the day two rows share a key, deleting one destroys the
    other's bytes.

    So this is a real copy: two blobs, two independent lifetimes. Fine for the
    images it is used for; reconsider before pointing it at video.
    """
    return write(destination, read(source), content_type=content_type)


def read(path: str) -> bytes:
    """The bytes of one file."""
    signed = api.get(f"/api/nodes/{resolve(path)['id']}/download-url")
    return _fetch(signed["url"])


def download(path: str, destination: Path) -> Path:
    """Write one file to disk, creating parents."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(read(path))
    return destination


def presign(path: str, *, disposition: str = "inline") -> str:
    """A short-lived HTTPS URL for one file.

    **This is how anything reaches Replicate.** The URL is signed by the API
    against its own credentials, so the CLI hands out access it does not itself
    hold — which is the whole arrangement hard rule #3 describes.
    """
    signed = api.get(
        f"/api/nodes/{resolve(path)['id']}/download-url", disposition=disposition
    )
    return signed["url"]


def write(path: str, body: bytes, *, content_type: str) -> dict:
    """Create or replace a file at a name path, and return its node.

    Three calls, and the order is the recoverable one: create the placeholder,
    PUT the bytes at the signed URL, then confirm — which is when the row learns
    its size. A failure before the confirm leaves a placeholder, which the app
    skips and which is a row nobody sees; a failure after it would leave a row
    promising bytes that are not there.
    """
    parent_path, _, name = path.strip("/").rpartition("/")
    parent = resolve(parent_path)

    try:
        node = api.post(
            "/api/nodes", {"parent": parent["id"], "name": name, "kind": "file"}
        )
    except api.Conflict:
        # Already there: this is a replace, and the node keeps its identity so
        # every record naming it stays true.
        node = resolve(path)

    signed = api.post(
        f"/api/nodes/{node['id']}/upload-url",
        {"size": len(body), "content_type": content_type},
    )
    _put(signed["url"], body, signed["headers"])
    return api.post(f"/api/nodes/{node['id']}/confirm-upload")


def upload(path: str, source: Path, *, content_type: str) -> dict:
    """Write a local file into the store."""
    return write(path, source.read_bytes(), content_type=content_type)


def _fetch(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return response.read()
    except urllib.error.URLError as error:
        # The URL is presigned and short-lived, so the useful failure is almost
        # always expiry — say that rather than echoing a signed URL into a
        # terminal, which would put a working credential in the scrollback.
        raise StoreError(f"Could not fetch the object ({error.reason}).") from error


def _put(url: str, body: bytes, headers: dict) -> None:
    request = urllib.request.Request(url, data=body, method="PUT")  # noqa: S310
    # Exactly the headers the API signed. `content-length` and `content-type`
    # are in `X-Amz-SignedHeaders`, so anything else here fails the signature and
    # writes nothing — which is the bound, not a formality.
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):  # noqa: S310
            return
    except urllib.error.URLError as error:
        raise StoreError(f"Could not upload the object ({error.reason}).") from error


# ── the tree, addressed by node id ──────────────────────────────────────────
#
# **The half of this module that survives the entity model.** Everything above
# takes a name path, which is what a person types and what `GET /api/resolve`
# turns into a node. Everything below takes a node id, which is what a *record*
# holds — a run names its folder, a reference names its image, a character names
# its root — and a record that named a path would be stranded by the first
# rename, which is the whole disease `docs/ENTITY_MODEL.md` sets out to cure.
#
# So the two halves are not duplicates and neither is scaffolding. A path is an
# address a human uses once; an id is an identity a row keeps forever.


def node(node_id: str) -> dict:
    """One node's record by id. Raises `api.NotFound` if it is gone."""
    return api.get(f"/api/nodes/{node_id}")


def children_of(node_id: str) -> list[dict]:
    """The direct children of a folder node, name-ascending as DynamoDB sorts.

    Not natural order. `files_of` imposes that, for the reason `files` gives —
    positional `[Image1]..[ImageN]` mapping — and a caller wanting folders
    usually wants them alphabetically.
    """
    listed = api.get("/api/nodes", parent=node_id)
    return listed if isinstance(listed, list) else []


def files_of(node_id: str) -> list[dict]:
    """The file children of a folder node, natural-sorted by name.

    The id-addressed twin of `files`, and the sort is load-bearing for the same
    reason: these become `[Image1]..[ImageN]` positionally, and a lexical sort
    puts `_10` before `_2` and hands a model the wrong image under the right
    name.
    """
    return sorted(
        (entry for entry in children_of(node_id)
         if entry.get("kind") == "file" and entry.get("name")),
        key=lambda entry: natural_key(entry["name"]),
    )


def child(parent_id: str, name: str) -> dict | None:
    """The child of a folder with this name, or None.

    One listing rather than a resolve, because the caller almost always wants
    several children of the same parent — a character's four pools, a run's
    `output/` — and a listing is one request where four resolves are four.

    **A missing folder is None, not an error**, and that is the self-healing
    property the layout section of the spec describes: the conventional folders
    are convention, so anything that cannot find one is entitled to make one
    (`ensure_child_folder`) rather than to fail.
    """
    for entry in children_of(parent_id):
        if entry.get("name") == name:
            return entry
    return None


def ensure_child_folder(parent_id: str, name: str) -> dict:
    """The named child folder, created if it is absent.

    Idempotent by construction: a `Conflict` means something else created it
    between the listing and the create, and the node it made is the right
    answer. Refuses to hand back a file, because a caller asking for a folder is
    about to write children into it.
    """
    found = child(parent_id, name)
    if found is not None:
        if found.get("kind") != "folder":
            raise StoreError(f"{name!r} is a file, not a folder.")
        return found
    try:
        return api.post("/api/nodes", {"parent": parent_id, "name": name,
                                       "kind": "folder"})
    except api.Conflict:
        return child(parent_id, name) or {}


def folder_path(root_id: str, *names: str) -> dict:
    """Walk (and create) a chain of folders below a node. Returns the last one."""
    current = {"id": root_id}
    for name in names:
        current = ensure_child_folder(current["id"], name)
    return current


def read_node(node_id: str) -> bytes:
    """The bytes of one file, by id."""
    return _fetch(api.get(f"/api/nodes/{node_id}/download-url")["url"])


def presign_node(node_id: str, *, disposition: str = "inline") -> str:
    """A short-lived HTTPS URL for one file, by id. **How anything reaches Replicate.**"""
    return api.get(f"/api/nodes/{node_id}/download-url", disposition=disposition)["url"]


def download_node(node_id: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(read_node(node_id))
    return destination


def write_into(parent_id: str, name: str, body: bytes, *, content_type: str) -> dict:
    """Create or replace a file inside a folder node, and return its node.

    Three calls in the recoverable order, exactly as `write`: placeholder, PUT,
    confirm. A failure before the confirm leaves a row nobody sees; a failure
    after it would leave a row promising bytes that are not there.

    A `Conflict` is a replace, and the node **keeps its identity** — which is
    the property every record naming it depends on.
    """
    try:
        node_record = api.post("/api/nodes", {"parent": parent_id, "name": name,
                                              "kind": "file"})
    except api.Conflict:
        node_record = child(parent_id, name)
        if node_record is None:
            raise
    signed = api.post(f"/api/nodes/{node_record['id']}/upload-url",
                      {"size": len(body), "content_type": content_type})
    _put(signed["url"], body, signed["headers"])
    return api.post(f"/api/nodes/{node_record['id']}/confirm-upload")


def upload_into(parent_id: str, name: str, source: Path, *, content_type: str) -> dict:
    return write_into(parent_id, name, Path(source).read_bytes(), content_type=content_type)


def upload_to_url(signed: dict, source: Path) -> None:
    """PUT a local file at a URL some entity route already signed.

    `POST /api/runs/<id>/outputs` and `POST /api/scenes/<id>/output` mint the
    node and the URL together, so the placeholder dance `write_into` performs
    has already happened server-side and repeating it would make a second node.
    """
    _put(signed["url"], Path(source).read_bytes(), signed.get("headers") or {})


def rename_node(node_id: str, name: str) -> dict:
    """Rename in place. **No object is written** — a name is a column."""
    return api.patch(f"/api/nodes/{node_id}", {"name": name})


def reparent_node(node_id: str, parent_id: str) -> dict:
    """Reparent in place. **No object is written**, and the id survives."""
    return api.patch(f"/api/nodes/{node_id}", {"parent": parent_id})


def move_nodes(ids: list[str], destination: str) -> dict:
    """Move many nodes into a folder. Rows only; the blobs never budge."""
    return api.post("/api/nodes/move", {"ids": list(ids), "destination": destination})


def copy_nodes(ids: list[str], destination: str) -> dict:
    """Copy many nodes into a folder.

    A real copy — two blobs, two independent lifetimes — for the reason `copy`
    gives: a second row pointing at one blob is copy-on-write (#334), and the
    delete route destroys the shared bytes when either row goes.
    """
    return api.post("/api/nodes/copy", {"ids": list(ids), "destination": destination})


def delete_nodes(ids: list[str]) -> dict:
    """Delete nodes and their blobs. The one operation here that destroys bytes."""
    return api.request("DELETE", "/api/nodes", {"ids": list(ids)})


def node_owner(node_id: str) -> dict | None:
    """Which entity a node belongs to, derived from its ancestry.

    `{kind, id, slug}` or None. Derived rather than stored, so a move that
    changes the owner is visible immediately even though the blob key it was
    stamped with is not rewritten — see the spec's note on key drift and
    `catalog reseat`.
    """
    found = api.get(f"/api/nodes/{node_id}/owner")
    return found or None


def node_text(node_id: str) -> str:
    """A text node's content. Used for run payload documents, which are NEVER parsed."""
    return api.get(f"/api/nodes/{node_id}/text").get("content", "")


def set_node_text(node_id: str, content: str) -> dict:
    return api.patch(f"/api/nodes/{node_id}/text", {"content": content})
