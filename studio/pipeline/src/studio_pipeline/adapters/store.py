"""The media store, addressed by path and reached through the API (#302).

**This is the seam that ends direct AWS access from the pipeline.** Call sites
say "the object at `characters/<name>/reference/face_01.png`"; this resolves that
name path to a node through `GET /api/resolve` and moves bytes through presigned
URLs the API hands out. No boto3, no bucket name, no credentials.

## Why a path-addressed facade rather than rewriting every call site to use ids

Twenty-five modules and seventy-one boto3 calls address the tree by key today,
and every `SKILL.md` describes the CLI in those terms. Rewriting all of them to
carry node ids in one change would be a refactor nobody could review. This keeps
the vocabulary the pipeline already has — a path — and changes only what is
underneath it. Call sites migrate one area at a time.

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

## Two ways in, because two kinds of thing live in the bucket

Most of the tree is **owned** — a character, a project, everything under them —
and is addressed by name path through the catalog. A little of it is **shared**:
`phrasebook/wording.yaml` and the `config/pose/` plates, which belong to no
character and no project, which `catalog_seed.py` deliberately does not record,
and which `dev-setup.sh` syncs straight into the bucket. Those have no node, so
`resolve` 404s on them.

`shared_read` and `shared_presign` reach them through the API's key-addressed
route (`GET /api/asset`) instead. Still the API, still no credentials here — a
different route to the same authority, not an exception to it. Keeping the two
names apart is the point: a call site reaching for `shared_*` is saying "this
is owned by nobody", which is exactly the fact that makes it correct.

## What is deliberately not here

No `copy`, no `delete`, no `move`. Those are catalog operations now — a move
rewrites rows and touches no object — and they belong on the API's node routes,
which the migrating call sites will call directly. A byte mover that also
pretended to move things would invite exactly the key-shuffling this replaces.
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
    always was; `adapters/s3.py` re-exports this so its callers do not churn.
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


def exists(path: str) -> bool:
    """Whether a node is there. Cheaper than fetching it, and never raises."""
    try:
        resolve(path)
    except api.NotFound:
        return False
    return True


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


def shared_presign(key: str, *, disposition: str = "inline") -> str:
    """A short-lived URL for shared material, addressed by key.

    For the phrasebook and the pose plates only. Anything a character or a
    project owns has a node, and reaching it this way would bypass the
    permission check that node carries.
    """
    signed = api.get("/api/asset", key=key.strip("/"), disposition=disposition)
    return signed["url"]


def shared_read(key: str) -> bytes:
    """The bytes of one shared file. See `shared_presign`."""
    return _fetch(shared_presign(key))


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
