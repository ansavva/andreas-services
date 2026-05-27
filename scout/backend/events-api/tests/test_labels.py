"""Unit tests for the label taxonomy service layer (labels.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.domain import labels  # noqa: E402
from scout_core.adapters import store  # noqa: E402

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
class TestLabels(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        _create_core(boto3.resource("dynamodb", region_name="us-east-1"))

    def test_create_and_get(self):
        label = labels.create_label(store.EVENT_LABEL, "Live Music")
        self.assertEqual(label["name"], "Live Music")
        self.assertEqual(label["name_norm"], "live music")
        fetched = labels.get_label(store.EVENT_LABEL, label["label_id"])
        self.assertEqual(fetched["name"], "Live Music")

    def test_create_rejects_blank_and_unknown_taxonomy(self):
        with self.assertRaises(ValueError):
            labels.create_label(store.EVENT_LABEL, "   ")
        with self.assertRaises(ValueError):
            labels.create_label("bogus", "X")

    def test_list_is_sorted_and_taxonomies_isolated(self):
        labels.create_label(store.EVENT_LABEL, "Zebra")
        labels.create_label(store.EVENT_LABEL, "Apple")
        labels.create_label(store.SOURCE_LABEL, "Newsletter")

        event_labels = labels.list_labels(store.EVENT_LABEL)
        self.assertEqual([x["name"] for x in event_labels], ["Apple", "Zebra"])
        # Separate namespace — source labels don't leak into the event list.
        self.assertEqual(len(labels.list_labels(store.SOURCE_LABEL)), 1)

    def test_rename_updates_listing_order(self):
        a = labels.create_label(store.EVENT_LABEL, "Apple")
        labels.create_label(store.EVENT_LABEL, "Mango")
        labels.rename_label(store.EVENT_LABEL, a["label_id"], "Zucchini")
        names = [x["name"] for x in labels.list_labels(store.EVENT_LABEL)]
        self.assertEqual(names, ["Mango", "Zucchini"])

    def test_attach_detach_and_bidirectional_lookup(self):
        label = labels.create_label(store.EVENT_LABEL, "Jazz")
        lid = label["label_id"]
        labels.attach_label(store.EVENT_LABEL, lid, store.EVENT, "e1")
        labels.attach_label(store.EVENT_LABEL, lid, store.EVENT, "e2")

        self.assertEqual(sorted(labels.label_ids_of(store.EVENT, "e1")), [lid])
        tagged = labels.entities_with_label(store.EVENT_LABEL, lid)
        self.assertEqual(sorted(t[1] for t in tagged), ["e1", "e2"])

        labels.detach_label(store.EVENT_LABEL, lid, store.EVENT, "e1")
        self.assertEqual(labels.label_ids_of(store.EVENT, "e1"), [])

    def test_attach_rejects_wrong_target_type(self):
        label = labels.create_label(store.SOURCE_LABEL, "Promo")
        with self.assertRaises(ValueError):
            labels.attach_label(store.SOURCE_LABEL, label["label_id"], store.EVENT, "e1")

    def test_label_ids_of_filters_by_taxonomy(self):
        evt = labels.create_label(store.EVENT_LABEL, "Music")
        loc = labels.create_label(store.LOCATION_LABEL, "Outdoor")
        labels.attach_label(store.EVENT_LABEL, evt["label_id"], store.EVENT, "e1")
        # Location label attached to a location, not the event.
        labels.attach_label(store.LOCATION_LABEL, loc["label_id"], store.LOCATION, "l1")

        self.assertEqual(
            labels.label_ids_of(store.EVENT, "e1", taxonomy=store.EVENT_LABEL),
            [evt["label_id"]],
        )

    def test_delete_label_removes_references_and_hides_from_listing(self):
        label = labels.create_label(store.EVENT_LABEL, "Temp")
        lid = label["label_id"]
        labels.attach_label(store.EVENT_LABEL, lid, store.EVENT, "e1")

        labels.delete_label(store.EVENT_LABEL, lid)

        self.assertEqual(labels.list_labels(store.EVENT_LABEL), [])
        # Reference removed from the entity's live label view.
        self.assertEqual(labels.label_ids_of(store.EVENT, "e1"), [])
        # Visible in the deleted view.
        self.assertEqual(len(store.query_deleted(store.EVENT_LABEL)), 1)

    def test_restore_label_returns_to_listing(self):
        label = labels.create_label(store.EVENT_LABEL, "Comeback")
        lid = label["label_id"]
        labels.delete_label(store.EVENT_LABEL, lid)
        labels.restore_label(store.EVENT_LABEL, lid)
        names = [x["name"] for x in labels.list_labels(store.EVENT_LABEL)]
        self.assertEqual(names, ["Comeback"])

    def test_resolve_labels_skips_deleted(self):
        a = labels.create_label(store.EVENT_LABEL, "Keep")
        b = labels.create_label(store.EVENT_LABEL, "Drop")
        labels.delete_label(store.EVENT_LABEL, b["label_id"])
        resolved = labels.resolve_labels(
            store.EVENT_LABEL, [a["label_id"], b["label_id"]]
        )
        self.assertEqual([x["name"] for x in resolved], ["Keep"])


if __name__ == "__main__":
    unittest.main()
