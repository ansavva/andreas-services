"""One file in and out of an empty dev stack, over HTTP (#289).

**This is what replaced the last bullet of #289.** That one asserted a seeded
tree against `manifest.json`, and the seed does not exist: `dev-seed publish`
landed in #284 and has never been run, so the fixture it would promote is a
session somebody has to sit through first. The assertion was therefore blocked
on a person, and paying for one to unblock a test is the wrong way round. So the
suite creates what it needs instead — a library, a folder, a file, and the bytes
behind it — and removes all of it afterwards. It passes against a stack that has
had nothing done to it beyond `dev-aws-setup.sh` and `dev-user.sh`.

**Every assertion here goes through the Flask app**, which is what makes it a
smoke test rather than a second copy of `test_storage_live.py`. That file settles
module-level claims against real AWS — a signature S3 will honour, a
`CancellationReasons` shape, a bucket unchanged across a move. This one settles
that the routes over them are wired together: the ordering of the four upload
calls, the status codes, the header the browser needs, and that a size written by
`confirm-upload` is the size a listing reports.

## WHAT THIS CANNOT CATCH, AND IT IS MORE THAN IT LOOKS

**The dev stack has no compute.** `infra/envs/dev` wires `auth` and `storage` and
stops — there is no `modules/compute`, so no Lambda, no API Gateway and **no API
role**. `dev-up.sh` runs Flask on `localhost:8000` under the *developer's own*
AWS credentials, and so does this suite. Every call below is authorized as a
human with broad access.

So:

* **The IAM bug that took prod down would pass this suite.** #438 was a missing
  `dynamodb:BatchGetItem` on the API role; every folder listing failed in
  production and nothing local could see it, because nothing local uses that
  role. `GET /api/tree` below makes exactly the call that failed, gets exactly
  the same 200 it got locally then, and proves nothing about the grant.
  `tests/test_iam_agreement.py` is what covers that, by reading the Terraform —
  and it is a static check, so it cannot see a policy that was never applied.
* **Nothing between the browser and Flask is exercised.** No API Gateway, so no
  CORS preflight — the one failure in this service that carries no message at
  all — and no authorizer. No Mangum and no `WsgiToAsgi`, so
  `BodyLengthMiddleware` is a no-op here: Flask's test client always sets
  `Content-Length`, which is precisely why the suite was green while prod could
  not read a JSON body. No CloudFront, and no 6 MB Lambda payload limit.
* **Nothing about the deployed configuration.** The env vars the Lambda actually
  runs with are set by `update-lambda` in the deploy workflow, not by Terraform
  and not by anything here.
* **Nothing about production data.** This library is minutes old. Prod holds keys
  written years before the catalog existed, and the legacy shapes those produce
  are not reachable from an empty stack.

What it does catch is a break in the round trip itself, which is the thing a
person would otherwise find by opening the site.
"""

import time
import urllib.request

import pytest

from studio_core import app_factory
from studio_core.clients.aws import s3
from studio_core.errors import NotFoundError
from studio_core.services import catalog, identity

# The file this test puts through the round trip. Small on purpose — the claim is
# about the four calls agreeing, and a big body would only make a slow test that
# still says nothing about multipart, for which there is no grant.
BODY = b"smoke-test bytes, written by tests/integration/test_smoke_round_trip.py\n"
CONTENT_TYPE = "text/plain"
FILENAME = "note.txt"

# How long a write may take to show up in a listing. See `_eventually`.
CONSISTENCY_SECONDS = 15.0


class Api:
    """The app, signed in, scoped to one library.

    **The library header is not optional here, and that is a property of the
    fixture rather than of the API.** `_resolve_library` falls back to a sole
    membership, and this account has one only until a previous crashed run leaves
    a `lib-it-…` row behind — at which point every request would 400 asking to be
    told which library, and the failure would read as a bug in the route. Naming
    it on every call makes the suite indifferent to debris it did not make.
    """

    def __init__(self, token: str, lib: str):
        self.client = app_factory.create_app().test_client()
        self.headers = {"Authorization": f"Bearer {token}", "X-Studio-Library": lib}

    def get(self, path: str):
        return self.client.get(path, headers=self.headers)

    def post(self, path: str, body: dict | None = None):
        return self.client.post(path, headers=self.headers, json=body or {})

    def delete(self, path: str):
        return self.client.delete(path, headers=self.headers)


@pytest.fixture
def api(library, id_token) -> Api:
    """The app, once the fixture's own rows are visible to it.

    **The wait is the price of a fixture written directly to DynamoDB.**
    `conftest.library` puts three items in with `PutItem` and hands back
    immediately; `before_request` then resolves the caller with
    `catalog.libraries_for`, an eventually consistent Query, and every route
    reads the root with an eventually consistent `GetItem`. Racing that produces
    a 403 saying the caller is a member of nothing, or a 404 on the library root
    — two failures that look like authorisation bugs and are neither.

    So all three rows are waited for once, here, rather than each test learning
    to distrust its first request.
    """

    def _visible() -> str:
        libs = [row["lib"] for row in catalog.libraries_for(library["sub"])]
        if library["lib"] not in libs:
            return "membership row"
        try:
            catalog.library(library["lib"])
        except NotFoundError:
            return "library row"
        try:
            catalog.node(library["root"])
        except NotFoundError:
            return "root node"
        return ""

    _eventually(
        _visible,
        lambda missing: missing == "",
        what="the fixture's own rows never became readable",
    )
    return Api(id_token, library["lib"])


@pytest.fixture
def debris(library):
    """Records what a test made, and removes it however the test ends.

    **Its own fixture rather than `library`'s `created` list**, because that list
    is cleaned with `catalog.delete_node`, which removes rows and returns the
    blob keys for its caller to deal with. The harness has no bucket to hand and
    deliberately does not raise, so an uploaded object would survive it. Here the
    keys are collected and deleted, which is the same two steps
    `DELETE /api/nodes/<id>` takes and in the same order.

    Teardown runs on a passing test, a failing one and an error in another
    fixture, which is the point — a suite that leaves `smoke-*` folders behind in
    a stack somebody also uses by hand is a suite that gets run once. It does not
    survive the process being killed outright; what that leaves is one
    `lib-it-<uuid>` library, visible in `studio dev-seed tree`.

    Deepest first, so a folder is not deleted out from under a child that is
    about to be looked up. Every step is best effort: a teardown that raised
    would replace the assertion that failed with a `NotFoundError` about tidying
    up, and the failure is the thing worth reading.
    """
    made: list[str] = []
    yield made

    for node_id in reversed(made):
        try:
            result = catalog.delete_node(node_id)
        except Exception:  # noqa: BLE001 - already gone is the common case
            continue
        try:
            if result["blob_keys"]:
                s3.delete(result["blob_keys"])
        except Exception:  # noqa: BLE001, S110 - an orphan blob is collectable
            pass


def _eventually(read, matches, *, what: str):
    """Poll a listing until it agrees, or fail saying what it last said.

    **Not flake-proofing — the read is genuinely eventually consistent.**
    `catalog.children` is an unconditional `Query` on the base table, so
    DynamoDB may serve it from a replica that has not caught up with the write
    the line above just made. That is a deliberate choice in the service (a
    consistent read costs double and a folder listing does not need one), so a
    test that asserted it once would be asserting something the code never
    promised.

    Bounded, and it fails with the last value it saw rather than with a timeout,
    because "the folder never appeared" and "the folder appeared with the wrong
    size" are different bugs and a bare timeout tells them apart for nobody.
    """
    deadline = time.monotonic() + CONSISTENCY_SECONDS
    seen = None
    while True:
        seen = read()
        if matches(seen):
            return seen
        if time.monotonic() > deadline:
            pytest.fail(f"{what} — after {CONSISTENCY_SECONDS:g}s the last read was {seen!r}")
        time.sleep(0.25)


def _fetch(url: str) -> tuple[bytes, dict]:
    """Follow a presigned URL as something outside this process, and report both.

    moto signs URLs; it does not serve them. The signature, the expiry, the
    region and `response-content-disposition` are only exercised the moment a
    real HTTP client follows one, which is the whole reason this suite exists.
    """
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        return response.read(), dict(response.headers)


def _put(grant: dict, body: bytes) -> None:
    """PUT the bytes to the signed URL, with exactly the headers it signed.

    **Both headers are signed, so neither is advisory.** A different length or a
    different type fails signature validation at S3 and writes nothing — that is
    what bounds `presign_put` to one object of one size, and sending the grant's
    own values back is the only way to prove the grant is usable rather than
    merely well-formed.

    `Content-Length` is set explicitly and urllib then leaves it alone, which is
    not what the browser does: `setRequestHeader` for it is a silent no-op and
    Chrome computes the value from the body instead. The two agree because the
    number is `file.size` either way — see `frontend/src/apis/upload.ts`.
    """
    request = urllib.request.Request(grant["url"], data=body, method="PUT")  # noqa: S310
    for header, value in grant["headers"].items():
        request.add_header(header, value)
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        assert response.status in (200, 204), response.status


def test_a_real_dev_pool_token_reaches_the_library_root(api, id_token, library):
    """The 401 seam and the 500 seam, in one request.

    Two things have to be true before anything else in this file can be, and
    `before_request` does both on every call: `identity.caller_sub` verifies an
    RS256 signature against the pool's live JWKS, and `catalog.libraries_for`
    reads the membership row out of real DynamoDB. The unit suite stubs the pair
    outright, so this is the only place they run.

    **`GET /api/tree` on the root is the call that broke in production.** It came
    back "Could not read the catalog" for every folder in #438. The negative
    cases for the token — expired, wrong pool, access token, malformed — are in
    `test_identity_live.py`; what is asserted here is that the good one arrives.
    """
    assert identity.caller_sub(f"Bearer {id_token}") == library["sub"]

    response = api.get("/api/tree")

    assert response.status_code == 200
    body = response.get_json()
    assert body["breadcrumbs"][0]["id"] == library["root"]
    # A stack with nothing in it. Asserted rather than assumed: a root that
    # already held a `smoke-…` folder would mean a previous run did not clean up,
    # and the round trip below would then be testing something else.
    assert body["counts"] == {"folders": 0, "files": 0, "media": 0}


def test_a_file_makes_the_whole_round_trip(api, library, debris, bucket):
    """Folder, upload, listing, fetch, delete — the four calls and what they leave.

    One test rather than five because every step is the previous step's output.
    Split up they would each need the ones before it as a fixture, which is the
    same sequence with the failure reported one layer further from where it
    happened.
    """
    client, bucket_name = bucket

    # ── the folder ──────────────────────────────────────────────────────────
    created = api.post(
        "/api/nodes", {"parent": library["root"], "name": "smoke", "kind": "folder"}
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    folder_id = created.get_json()["id"]
    debris.append(folder_id)

    listing = _eventually(
        lambda: api.get("/api/tree").get_json(),
        lambda body: [entry["name"] for entry in body["folders"]] == ["smoke"],
        what="the new folder never appeared in the library root",
    )
    # The listing addresses it by name path as well as by id, which is what every
    # share link ever handed out is made of.
    assert listing["folders"][0]["prefix"] == "smoke/"

    # ── the upload, in the four calls `apis/upload.ts` makes ────────────────
    #
    # 1. a placeholder, which is what mints the key. `on_conflict: "number"` is
    #    what the uploader sends: a file keeps the name it arrived with and the
    #    catalog decides what to do when that name is taken.
    node = api.post(
        "/api/nodes",
        {"parent": folder_id, "name": FILENAME, "kind": "file", "on_conflict": "number"},
    )
    assert node.status_code == 201, node.get_data(as_text=True)
    node_id = node.get_json()["id"]
    assert node.get_json()["name"] == FILENAME
    # Recorded before the bytes exist. Every failure from here leaves a row
    # naming a key with nothing behind it, and nothing in the service collects
    # one — `studio catalog gc` deletes blobs no row names, the other direction.
    debris.append(node_id)

    # 2. a signature for exactly that key, that length and that type.
    grant = api.post(
        f"/api/nodes/{node_id}/upload-url",
        {"size": len(BODY), "content_type": CONTENT_TYPE},
    )
    assert grant.status_code == 200, grant.get_data(as_text=True)
    grant = grant.get_json()
    assert grant["headers"] == {
        "Content-Length": str(len(BODY)),
        "Content-Type": CONTENT_TYPE,
    }

    # 3. the bytes, straight to S3 and never through the API.
    _put(grant, BODY)

    # 4. the size the bucket reports, written onto the row. The client already
    #    declared one in step 2; this checks it rather than trusting it twice.
    confirmed = api.post(f"/api/nodes/{node_id}/confirm-upload")
    assert confirmed.status_code == 200, confirmed.get_data(as_text=True)
    assert confirmed.get_json()["size"] == len(BODY)

    # ── the listing, with its size ──────────────────────────────────────────
    folder = _eventually(
        lambda: api.get(f"/api/tree?node={folder_id}").get_json(),
        lambda body: len(body["files"]) == 1,
        what="the uploaded file never appeared in its folder",
    )
    entry = folder["files"][0]
    assert entry["id"] == node_id
    assert entry["name"] == FILENAME
    # The number the grid draws, off the row `confirm-upload` wrote, having come
    # from `HeadObject` rather than from anything the client said.
    assert entry["size"] == len(BODY)
    assert entry["kind"] == "text"

    # ── the bytes back, through a URL S3 actually honours ───────────────────
    #
    # The listing's own URL, not one signed here: this is the exact string the
    # browser is handed, and a URL that only this process can build would settle
    # nothing about the tile.
    fetched, _ = _fetch(entry["url"])
    assert fetched == BODY

    # `disposition=attachment` is signed into the URL because the URL is
    # cross-origin to the app and a cross-origin `<a download>` is ignored. Only
    # S3 can say whether the header comes back.
    download = api.get(f"/api/nodes/{node_id}/download-url?disposition=attachment")
    assert download.status_code == 200, download.get_data(as_text=True)
    _, headers = _fetch(download.get_json()["url"])
    assert headers["Content-Disposition"] == f'attachment; filename="{FILENAME}"'

    # ── gone, rows and bytes both ───────────────────────────────────────────
    blob_key = catalog.blob_key_for(node_id)
    # Proved present first, or the assertion after the delete is a tautology
    # about a key that was never written.
    assert client.head_object(Bucket=bucket_name, Key=blob_key)["ContentLength"] == len(BODY)

    # **The delete walks `by-path`, and that is a GSI.** `test_transfer.py`
    # sidesteps the index for exactly this reason; here it cannot be sidestepped,
    # because `catalog.delete_node` is what the route calls. Racing it makes the
    # delete report one node and leave the file's bytes in the bucket — a failure
    # that would land two assertions later, on `s3.head`, saying nothing about
    # the cause. `child_path` is the folder's own children's `path` prefix, which
    # is the string the index is queried on.
    folder_record = catalog.node(folder_id)
    _eventually(
        lambda: [
            entry["node_id"]
            for entry in catalog.subtree(folder_record["lib"], catalog.child_path(folder_record))
        ],
        lambda ids: node_id in ids,
        what="the by-path index never listed the uploaded file",
    )

    deleted = api.delete(f"/api/nodes/{folder_id}")
    assert deleted.status_code == 200, deleted.get_data(as_text=True)
    # The folder and the file under it: a delete takes the whole subtree.
    assert deleted.get_json()["deleted"] == 2

    _eventually(
        lambda: api.get("/api/tree").get_json(),
        lambda body: body["folders"] == [],
        what="the deleted folder is still in the library root",
    )
    # Rows first and then blobs, so the bytes going too is the second half of the
    # promise and the half that is not visible from the API.
    with pytest.raises(NotFoundError):
        s3.head(blob_key)
    # The node id is unreachable as well as unlisted — a 404 rather than a row
    # that only the listing has stopped showing.
    _eventually(
        lambda: api.get(f"/api/nodes/{node_id}").status_code,
        lambda status: status == 404,
        what="the deleted node is still readable by id",
    )


def test_a_duplicate_name_in_one_folder_is_a_409(api, library, debris):
    """The status the UI keeps its rename field open on, from real DynamoDB.

    **The cheapest way to provoke a `TransactWriteItems` condition failure**, and
    the only one that costs nothing to set up. DynamoDB reports a failed
    condition inside `CancellationReasons` rather than as a top-level error, and
    that shape is exactly what a fake gets close enough to pass and wrong enough
    to matter — `catalog._write` reads it to decide which of two errors to raise.

    Through the route rather than through `services.catalog`, which is where
    `test_storage_live.py` asserts the same collision: what is added here is that
    `ConflictError` reaches the client as **409** and not as the 500 an unmapped
    exception would be.
    """
    first = api.post(
        "/api/nodes", {"parent": library["root"], "name": "smoke-dup", "kind": "folder"}
    )
    assert first.status_code == 201, first.get_data(as_text=True)
    debris.append(first.get_json()["id"])

    again = api.post(
        "/api/nodes", {"parent": library["root"], "name": "smoke-dup", "kind": "folder"}
    )

    assert again.status_code == 409, again.get_data(as_text=True)
    assert "already exists" in again.get_json()["error"]
