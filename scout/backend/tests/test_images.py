"""Unit tests for event/sub-event image management (images.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.services import images  # noqa: E402
from scout_core.repositories import store  # noqa: E402
from scout_core.repositories import dynamodb as dynamodb_adapter  # noqa: E402

_GSI_ATTRS = [
    "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "GSI3PK", "GSI3SK",
    "GSI4PK", "GSI4SK", "GSI5PK", "GSI5SK",
]


def _create_core(dynamodb):
    attribute_definitions = [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
    ] + [{"AttributeName": n, "AttributeType": "S"} for n in _GSI_ATTRS]
    gsis = [{
        "IndexName": f"GSI{i}",
        "KeySchema": [
            {"AttributeName": f"GSI{i}PK", "KeyType": "HASH"},
            {"AttributeName": f"GSI{i}SK", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    } for i in range(1, 6)]
    dynamodb.create_table(
        TableName="scout-core",
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=attribute_definitions,
        GlobalSecondaryIndexes=gsis,
        BillingMode="PAY_PER_REQUEST",
    )


@mock_dynamodb
class TestImages(unittest.TestCase):
    def setUp(self):
        dynamodb_adapter._dynamodb = None
        _create_core(boto3.resource("dynamodb", region_name="us-east-1"))

    def test_admin_image_is_approved_agent_image_is_not(self):
        admin = images.add_image(store.EVENT, "e1", s3_ref="s3://b/a.jpg",
                                 source=images.ADMIN)
        agent = images.add_image(store.EVENT, "e1", s3_ref="s3://b/p.jpg",
                                 url="https://x/p.jpg", source=images.AGENT)
        self.assertTrue(admin["approved"])
        self.assertFalse(agent["approved"])

    def test_requires_s3_ref(self):
        # Missing entirely (signature-level) and falsy (validation-level)
        # both fail — we only serve images we own.
        with self.assertRaises(TypeError):
            images.add_image(store.EVENT, "e1")  # type: ignore[call-arg]
        with self.assertRaises(ValueError):
            images.add_image(store.EVENT, "e1", s3_ref="",
                             url="https://x/p.jpg")

    def test_list_and_approved_filter(self):
        images.add_image(store.EVENT, "e1", s3_ref="s3://b/a.jpg", source=images.ADMIN)
        agent = images.add_image(store.EVENT, "e1", s3_ref="s3://b/p.jpg",
                                 url="https://x/p.jpg", source=images.AGENT)
        self.assertEqual(len(images.list_images(store.EVENT, "e1")), 2)
        self.assertEqual(len(images.list_images(store.EVENT, "e1", approved_only=True)), 1)

        images.approve_image(store.EVENT, "e1", agent["image_id"])
        self.assertEqual(len(images.list_images(store.EVENT, "e1", approved_only=True)), 2)

    def test_subevent_images_scoped_to_parent(self):
        images.add_image(store.SUBEVENT, "s1", s3_ref="s3://b/1.jpg",
                         source=images.AGENT, parent_event_id="e1")
        subimgs = images.list_images(store.SUBEVENT, "s1", parent_event_id="e1")
        self.assertEqual(len(subimgs), 1)
        # Event-level listing does not pick up the sub-event image.
        self.assertEqual(images.list_images(store.EVENT, "e1"), [])
        with self.assertRaises(ValueError):
            images.add_image(store.SUBEVENT, "s1", s3_ref="s3://b/1.jpg")

    def test_set_image_approved_toggles_visibility(self):
        agent = images.add_image(store.EVENT, "e1", s3_ref="s3://b/p.jpg",
                                 url="https://x/p.jpg", source=images.AGENT)
        approved = images.set_image_approved(store.EVENT, "e1",
                                             agent["image_id"], True)
        self.assertTrue(approved["approved"])
        self.assertEqual(len(images.list_images(store.EVENT, "e1", approved_only=True)), 1)
        # Rejecting hides it again without deleting the record.
        rejected = images.set_image_approved(store.EVENT, "e1",
                                             agent["image_id"], False)
        self.assertFalse(rejected["approved"])
        self.assertEqual(images.list_images(store.EVENT, "e1", approved_only=True), [])
        self.assertEqual(len(images.list_images(store.EVENT, "e1")), 1)

    def test_delete_image(self):
        img = images.add_image(store.EVENT, "e1", s3_ref="s3://b/a.jpg")
        images.delete_image(store.EVENT, "e1", img["image_id"])
        self.assertEqual(images.list_images(store.EVENT, "e1"), [])


if __name__ == "__main__":
    unittest.main()
