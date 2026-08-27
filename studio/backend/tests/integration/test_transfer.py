"""A transfer against real AWS, where a `CopyObject` would actually show up (#324).

**The claim is about bytes, so the bucket has to be the one asserted on.** The
unit half of this lives in `tests/test_manage.py` and runs against moto, which
would report a copy faithfully enough — but moto is also the thing that would
have to be wrong for the unit test to be lying, and a claim this programme rests
on is worth settling once against S3 itself. A mock's call log settles nothing in
either place: it passes for code that copies through a different client, and it
passes for a copy-then-delete that puts every byte back where it started.

The listing carries each object's ETag, size and last-modified stamp rather than
just its key, so a copy *onto a key's own name* — which leaves the key set
identical — fails this too.

**Two libraries, and the second is built here.** `conftest.library` makes one and
a transfer needs somewhere to go. Both are written literally, for the reason that
fixture gives: `services.catalog` is the only module allowed to know these
shapes, and this is the suite that would catch a shape DynamoDB accepts and moto
does not.
"""

import uuid

import boto3
import pytest

from studio_core.services import catalog


@pytest.fixture
def destination_library(dev_stack, library):
    """A second library for the same caller, removed afterwards.

    Takes `library` so the two exist together and tear down in the right order:
    this one goes first, and the nodes that were transferred into it are removed
    by `library`'s own teardown, which reads them by id rather than through the
    library row.
    """
    table = dev_stack["catalog_table_name"]
    client = boto3.client("dynamodb")

    lib = f"lib-it-{uuid.uuid4()}"
    root = f"node-it-{uuid.uuid4()}"
    now = "2026-08-20T00:00:00.000000+00:00"
    items = [
        {"pk": {"S": f"LIB#{lib}"}, "sk": {"S": "META"}, "name": {"S": "Integration destination"},
         "root_node": {"S": root}, "created_at": {"S": now}},
        {"pk": {"S": f"USER#{library['sub']}"}, "sk": {"S": f"LIB#{lib}"},
         "role": {"S": "owner"}, "created_at": {"S": now}},
        {"pk": {"S": f"NODE#{root}"}, "sk": {"S": "META"}, "node_id": {"S": root},
         "lib": {"S": lib}, "name": {"S": "Integration destination"},
         "kind": {"S": "folder"}, "path": {"S": "/"},
         "created_at": {"S": now}, "updated_at": {"S": now}},
    ]
    for item in items:
        client.put_item(TableName=table, Item=item)

    yield {"lib": lib, "root": root}

    # Best effort, like `library`'s: a leaked row in a dev table is noise, and a
    # teardown that raises would mask the assertion that failed.
    for item in items:
        try:
            client.delete_item(TableName=table, Key={"pk": item["pk"], "sk": item["sk"]})
        except Exception:  # noqa: BLE001, S110
            pass


def _bucket_state(client, name) -> dict:
    """Every object in the bucket, with enough of each to notice a rewrite."""
    paginator = client.get_paginator("list_objects_v2")
    return {
        item["Key"]: (item["ETag"], item["Size"], item["LastModified"])
        for page in paginator.paginate(Bucket=name)
        for item in page.get("Contents", [])
    }


def test_a_transfer_writes_no_s3_objects(bucket, library, destination_library):
    """A real bucket, byte-identical either side of a subtree changing hands."""
    client, name = bucket

    # A subtree with bytes actually behind it. A transfer over rows pointing at
    # nothing would prove nothing about objects.
    folder = catalog.create_node(library["root"], "projects", catalog.KIND_FOLDER)
    library["created"].append(folder["node_id"])
    child = catalog.create_node(folder["node_id"], "output", catalog.KIND_FOLDER)
    clip = catalog.create_node(child["node_id"], "clip.mp4", catalog.KIND_FILE)
    # Off the row rather than re-derived — see `test_smoke_round_trip.py` on
    # why this was a TypeError nobody had seen.
    key = clip["blob_key"]
    client.put_object(Bucket=name, Key=key, Body=b"integration-bytes")

    try:
        before = _bucket_state(client, name)
        result = catalog.transfer_node(folder["node_id"], destination_library["lib"])

        # The transfer has to have happened, or the assertion below is a
        # tautology about a bucket nothing touched.
        assert result["transferred"] is True
        assert result["descendants"] == 2

        assert _bucket_state(client, name) == before
    finally:
        client.delete_object(Bucket=name, Key=key)


def test_a_transfer_rewrites_the_library_on_every_node(library, destination_library):
    """The rows, from real DynamoDB — one transaction for the node, batches below it.

    **Asserted on records rather than on a `subtree` query**, deliberately. A
    subtree read is a GSI query and every global secondary index is eventually
    consistent, so asking `by-path` immediately after the write is a flake
    waiting for a busy afternoon. `catalog.node` is a `GetItem` on the base
    table. What the GSI rewrite is *for* is covered in `test_catalog.py`, where
    moto answers an index read the moment it is written.
    """
    folder = catalog.create_node(library["root"], "characters", catalog.KIND_FOLDER)
    library["created"].append(folder["node_id"])
    child = catalog.create_node(folder["node_id"], "reference", catalog.KIND_FOLDER)

    catalog.transfer_node(folder["node_id"], destination_library["lib"])

    assert catalog.node(folder["node_id"])["lib"] == destination_library["lib"]
    assert catalog.node(folder["node_id"])["parent_id"] == destination_library["root"]
    assert catalog.node(child["node_id"])["lib"] == destination_library["lib"]
