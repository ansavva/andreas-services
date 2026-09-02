"""The deployed prod API, exercised end to end by a real signed-in caller.

**What this catches that nothing else can: the Lambda's own execution role.**
The unit suite runs against moto, which does not enforce IAM at all — the whole
backend suite passes against a policy that grants nothing. The integration suite
runs real AWS, but it runs Flask in-process under a *developer's* credentials,
which are far wider than the function's. So the one thing neither can settle is
whether the role the deployed function actually assumes may make the calls the
code actually makes. That gap shipped: `dynamodb:BatchGetItem` was missing from
the API role, sign-in kept working because membership resolves with a `Query`,
and every folder listing returned "Could not read the catalog" — behind a fully green suite. It was found by a person opening the site.

**Which is why the listing here is done twice.** An empty folder short-circuits
`catalog.records([])` and issues no `BatchGetItem` at all, so a smoke test that
listed an empty root would have gone green through exactly that outage. Every
listing this file asserts on has a child in it.

**This is a detector, not a gate.** Studio has no staging: `studio-prod.yaml`
deploys straight to production, and this runs *after* the new image is already
serving traffic. Nothing here prevents a bad deploy. It fails the workflow
because red is the signal — the point is that the failure arrives in minutes
with a named cause rather than weeks later from whoever opened the site.

**Everything it does happens inside one library**, the smoke account's own. See
`conftest.py` for how that is enforced and why `test_the_smoke_account_reaches_
exactly_one_library` below is the assertion the rest of the suite rests on.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

# Small on purpose. This proves the four-call shape and the round trip through
# S3, not throughput; a large body would spend deploy minutes to assert the same
# thing.
BODY = b"studio prod smoke: bytes that went to S3 and came back\n"
CONTENT_TYPE = "text/plain"


def test_the_smoke_account_reaches_exactly_one_library(api, fixture):
    """The assertion this whole exercise exists to make.

    The repo owner's library is private and the smoke account is not in it. That
    is enforced structurally — one membership row, and the API resolves a
    request's library from the caller's memberships — and enforcement without a
    check is a promise. This is the check.

    Asserted here as well as in the `only_library` fixture that everything else
    depends on, deliberately: the fixture is what stops a violating token from
    reaching a `POST`, and this is what makes the violation a **named failing
    test** rather than a collection error nobody reads.
    """
    reachable = api.get("/api/libraries")

    assert [entry["id"] for entry in reachable] == [fixture["library"]["id"]], (
        "The smoke account must be a member of exactly one library and of nothing "
        f"else. It reported {len(reachable)}. Membership is the whole of "
        "authorisation in this service: an extra one is an extra library this suite "
        "can create in, upload to and DELETE from."
    )
    assert reachable[0]["name"] == fixture["library"]["name"]
    assert reachable[0]["role"] == fixture["user"]["role"]


def test_the_lambda_can_read_the_provider_token(api):
    """**The `ssm:GetParameter` + `kms:Decrypt` grant, and nothing else can prove it.**

    Generation moved into the API, so the deployed function now holds a provider
    credential — a SecureString it reads at call time under its own role. That is
    a new IAM grant, and this suite exists because a new IAM grant is exactly
    what the other two suites cannot check: moto does not enforce IAM, and the
    integration suite runs under a developer's own key. `dynamodb:BatchGetItem`
    shipped missing behind a fully green suite for precisely this reason.

    **It is a READ route, deliberately, and it bills nothing.**
    `GET /api/models/<name>/schema` makes the API fetch the token, decrypt it and
    call Replicate — every step of the credential path — without creating a
    prediction. Exercising the grant through `POST /api/runs/<id>/submit` would
    have meant a real generation on every deploy, which is a bill and, under hard
    rule #2, a payload nobody approved.

    **Two grants, and only one of them fails visibly on its own.** Granting
    `ssm:GetParameter` without `kms:Decrypt` fails at runtime with an
    `AccessDeniedException` naming *KMS*, which sends a reader to the wrong
    policy — so the assertion is on the schema coming back, which requires both.
    """
    schema = api.get("/api/models/google/nano-banana-pro/schema")

    assert schema["model"] == "google/nano-banana-pro"
    assert schema["props"], (
        "The live schema came back empty. `services/schema.fetch` swallows a "
        "provider failure and reports a skipped validation, so this is what a "
        "missing ssm:GetParameter, a missing kms:Decrypt, an unset "
        "STUDIO_REPLICATE_TOKEN_PARAMETER or a placeholder token all look like "
        "from outside. Check the Lambda's log group for which."
    )
    assert "prompt" in schema["props"]


def test_the_root_folder_lists(api, root_node, scratch):
    """`GET /api/nodes` on the library's own root, with something in it.

    `scratch` is requested so the root is not empty — see this module's header:
    an empty listing takes the one code path that would have survived the outage
    this file exists to detect.
    """
    listing = api.get("/api/nodes", under=root_node)

    assert listing["counts"].get("folder", 0) >= 1
    assert scratch in {entry["id"] for entry in listing["entries"]}
    assert listing["breadcrumbs"], "a listing always names where it is"


def test_a_new_folder_appears_in_its_parents_listing(api, scratch):
    """Create, then list — one round trip each, and the listing is the point.

    The `POST` is a `TransactWriteItems` over the record and its by-parent item;
    the listing that follows is a `Query` plus the `BatchGetItem` that fetches
    the full records. Three distinct DynamoDB grants, none of which the unit
    suite can prove the deployed role holds.
    """
    created = api.post(
        "/api/nodes", {"parent": scratch, "name": "listing", "kind": "folder"}, expect=201
    )

    listing = api.get("/api/nodes", under=scratch)

    assert created["id"] in {entry["id"] for entry in listing["entries"]}
    # A count, not an exact one: what this test needs is a listing with a child
    # in it, and pinning the number would make it fail for a later test's
    # leftovers rather than for anything it is about.
    assert listing["counts"].get("folder", 0) >= 1


def test_a_file_uploads_in_four_calls_and_the_bytes_come_back(api, scratch):
    """The upload the SPA performs, and the download a tile performs.

    Four calls, because the bytes never transit the Lambda — a 6 MB request
    limit against a video is not a limit you tune around. `POST /api/nodes`
    mints the placeholder that names the key, `upload-url` signs a PUT for
    exactly that key, length and type, the bytes go straight to S3, and
    `confirm-upload` writes back the size **S3 reports** rather than the one the
    client claimed.

    Then the round trip that no mock can settle: a presigned URL fetched by
    something outside this process. moto signs URLs; it does not serve them, so
    the signature, the expiry and the region are only ever exercised here and in
    the integration suite — and only here against the *deployed* function's
    credentials, which are what sign it in production.
    """
    node = api.post(
        "/api/nodes", {"parent": scratch, "name": "upload.txt", "kind": "file"}, expect=201
    )
    assert node.get("size") is None, "a placeholder has no size until it is confirmed"

    grant = api.post(
        f"/api/nodes/{node['id']}/upload-url",
        {"size": len(BODY), "content_type": CONTENT_TYPE},
    )
    # Echoed by the API because they are not advisory: the PUT must carry
    # exactly these two or the signature fails.
    assert grant["headers"]["Content-Length"] == str(len(BODY))

    put = urllib.request.Request(grant["url"], data=BODY, method="PUT")
    for header, value in grant["headers"].items():
        put.add_header(header, value)
    with urllib.request.urlopen(put, timeout=60) as response:  # noqa: S310
        assert response.status == 200

    confirmed = api.post(f"/api/nodes/{node['id']}/confirm-upload")
    assert confirmed["size"] == len(BODY), "confirm-upload records what S3 stored"
    assert confirmed["content_type"] == CONTENT_TYPE

    download = api.get(f"/api/nodes/{node['id']}/download-url")
    with urllib.request.urlopen(download["url"], timeout=60) as response:  # noqa: S310
        assert response.read() == BODY

    listing = api.get("/api/nodes", under=scratch)
    uploaded = next(entry for entry in listing["entries"] if entry["id"] == node["id"])
    assert uploaded["size"] == len(BODY)
    # A listing presigns every file it returns, and that URL is signed by the
    # Lambda's credentials on a code path `download-url` does not share.
    with urllib.request.urlopen(uploaded["url"], timeout=60) as response:  # noqa: S310
        assert response.read() == BODY


def test_deleting_takes_the_rows_and_then_the_bytes(api, scratch):
    """Rows first, then blobs — and afterwards neither answers.

    The delete is the one operation here that can leave production worse than it
    found it, so it is asserted rather than assumed: the node is a 404, it is
    gone from its parent's listing, and the presigned URL taken *before* the
    delete no longer serves the object. That last one is what proves the blobs
    went too — an orphaned blob is invisible to every reader in this API, so
    nothing in a listing could tell you it was still there.

    **The file is deleted on its own, and the folder after it, rather than the
    folder taking the subtree with it.** A subtree delete is bounded by
    `catalog.subtree`, which is a query on the eventually-consistent `by-path`
    index — asking it moments after the writes is a flake waiting for a busy
    afternoon, and the flake would leave orphan rows in a production table
    rather than just failing. What the subtree bound does is covered by
    `tests/test_catalog.py` against a fake that answers an index read the moment
    it is written. Here, one node at a time is the claim worth making.
    """
    folder = api.post(
        "/api/nodes", {"parent": scratch, "name": "doomed", "kind": "folder"}, expect=201
    )
    node = api.post(
        "/api/nodes", {"parent": folder["id"], "name": "doomed.txt", "kind": "file"}, expect=201
    )
    grant = api.post(
        f"/api/nodes/{node['id']}/upload-url",
        {"size": len(BODY), "content_type": CONTENT_TYPE},
    )
    put = urllib.request.Request(grant["url"], data=BODY, method="PUT")
    for header, value in grant["headers"].items():
        put.add_header(header, value)
    with urllib.request.urlopen(put, timeout=60) as response:  # noqa: S310
        assert response.status == 200
    api.post(f"/api/nodes/{node['id']}/confirm-upload")
    blob_url = api.get(f"/api/nodes/{node['id']}/download-url")["url"]

    assert api.delete(f"/api/nodes/{node['id']}")["deleted"] == 1

    api.request("GET", f"/api/nodes/{node['id']}", expect=404)
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(blob_url, timeout=60)  # noqa: S310
    # 404 for a key that is gone; S3 answers 403 instead when the caller may not
    # list the bucket, and either proves the object no longer serves.
    assert refused.value.code in (403, 404)

    api.delete(f"/api/nodes/{folder['id']}")
    listing = api.get("/api/nodes", under=scratch)
    assert folder["id"] not in {entry["id"] for entry in listing["entries"]}
