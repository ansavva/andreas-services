"""S3 and DynamoDB behaviours moto does not reproduce (#289).

Three things the unit suite asserts against a fake and therefore cannot settle:
a presigned URL that a real HTTP client can actually fetch, a
`TransactWriteItems` condition failure with real cancellation semantics, and the
claim that moving a node touches no object at all.
"""

import urllib.request

import pytest

from studio_core.clients.aws import s3
from studio_core.errors import ConflictError
from studio_core.services import catalog


def test_a_presigned_url_fetches_real_bytes(bucket, library):
    """moto signs URLs; it does not serve them. Only S3 can answer this.

    The signature, the expiry and the region are all only exercised the moment
    something outside this process follows the URL.
    """
    client, name = bucket
    key = f"blobs/it-{library['root']}-presign"
    body = b"integration-bytes"
    client.put_object(Bucket=name, Key=key, Body=body, ContentType="text/plain")
    try:
        with urllib.request.urlopen(s3.presign(key), timeout=30) as response:  # noqa: S310
            assert response.read() == body
    finally:
        client.delete_object(Bucket=name, Key=key)


def test_an_attachment_url_sets_the_download_header(bucket, library):
    """Signed into the URL, because a cross-origin `<a download>` is ignored."""
    client, name = bucket
    key = f"blobs/it-{library['root']}-attach"
    client.put_object(Bucket=name, Key=key, Body=b"x")
    try:
        url = s3.presign(key, disposition="attachment", filename="my file.txt")
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            assert "attachment" in response.headers.get("Content-Disposition", "")
    finally:
        client.delete_object(Bucket=name, Key=key)


def test_a_name_collision_is_a_conflict_under_real_dynamodb(library):
    """The 409 the UI depends on, from a real cancellation reason.

    `TransactWriteItems` reports a failed condition in `CancellationReasons`
    rather than as a top-level error, and the shape of that response is exactly
    the kind of thing a fake gets close enough to pass and wrong enough to
    matter.
    """
    first = catalog.create_node(library["root"], "characters", catalog.KIND_FOLDER)
    library["created"].append(first["node_id"])

    with pytest.raises(ConflictError):
        catalog.create_node(library["root"], "characters", catalog.KIND_FOLDER)


def test_moving_a_node_writes_no_s3_objects(bucket, library):
    """Asserted against a real bucket listing before and after, not a call log.

    A move rewrites one `parent_id`, one by-parent item and every descendant's
    `path`. Zero objects move — that is the entire point of the catalog, and a
    mock's "no calls were made" is a weaker claim than the bucket being
    byte-identical.
    """
    client, name = bucket
    source = catalog.create_node(library["root"], "characters", catalog.KIND_FOLDER)
    destination = catalog.create_node(library["root"], "archive", catalog.KIND_FOLDER)
    library["created"].extend([source["node_id"], destination["node_id"]])

    def listing() -> set:
        paginator = client.get_paginator("list_objects_v2")
        return {
            item["Key"]
            for page in paginator.paginate(Bucket=name)
            for item in page.get("Contents", [])
        }

    before = listing()
    catalog.move_node(source["node_id"], destination["node_id"])
    assert listing() == before


def test_a_rename_leaves_descendant_paths_untouched(library):
    """`path` names ancestors by id, so a rename changes none of them."""
    folder = catalog.create_node(library["root"], "characters", catalog.KIND_FOLDER)
    child = catalog.create_node(folder["node_id"], "seed", catalog.KIND_FOLDER)
    library["created"].append(folder["node_id"])

    before = catalog.node(child["node_id"])["path"]
    catalog.rename_node(folder["node_id"], "subjects")

    assert catalog.node(child["node_id"])["path"] == before
