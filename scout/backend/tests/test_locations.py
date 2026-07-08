"""Unit tests for the location service layer (locations.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.services import labels  # noqa: E402
from scout_core.services import locations  # noqa: E402
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
class TestLocations(unittest.TestCase):
    def setUp(self):
        dynamodb_adapter._dynamodb = None
        _create_core(boto3.resource("dynamodb", region_name="us-east-1"))

    def test_create_get_and_defaults(self):
        loc = locations.create_location("The Fillmore", address="1805 Geary Blvd")
        self.assertEqual(loc["name_norm"], "the fillmore")
        self.assertEqual(loc["timezone"], "UTC")
        self.assertEqual(locations.get_location(loc["location_id"])["address"],
                         "1805 Geary Blvd")

    def test_create_requires_name(self):
        with self.assertRaises(ValueError):
            locations.create_location("  ")

    def test_list_sorted_and_update_reorders(self):
        a = locations.create_location("Apollo")
        locations.create_location("Beacon")
        self.assertEqual([x["name"] for x in locations.list_locations()],
                         ["Apollo", "Beacon"])
        locations.update_location(a["location_id"], {"name": "Zenith"})
        self.assertEqual([x["name"] for x in locations.list_locations()],
                         ["Beacon", "Zenith"])

    def test_update_timezone(self):
        loc = locations.create_location("Hall")
        locations.update_location(loc["location_id"], {"timezone": "America/New_York"})
        self.assertEqual(locations.get_location(loc["location_id"])["timezone"],
                         "America/New_York")

    def test_fuzzy_match(self):
        locations.create_location("Madison Square Garden")
        locations.create_location("Radio City Music Hall")
        matches = locations.fuzzy_match("madison square gardens")
        self.assertTrue(matches)
        self.assertEqual(matches[0]["name"], "Madison Square Garden")
        self.assertEqual(locations.fuzzy_match("Totally Different Venue"), [])

    def test_delete_and_restore(self):
        loc = locations.create_location("Temporary")
        locations.delete_location(loc["location_id"])
        self.assertEqual(locations.list_locations(), [])
        locations.restore_location(loc["location_id"])
        self.assertEqual([x["name"] for x in locations.list_locations()],
                         ["Temporary"])

    def test_event_pointers(self):
        loc = locations.create_location("Venue")
        locations.link_event_to_location(loc["location_id"], store.EVENT, "e1")
        locations.link_event_to_location(loc["location_id"], store.EVENT, "e2")
        refs = locations.events_at_location(loc["location_id"])
        self.assertEqual(sorted(p["target_id"] for p in refs), ["e1", "e2"])

    def test_merge_reassigns_references_and_soft_deletes_sources(self):
        target = locations.create_location("Canonical Venue")
        source = locations.create_location("Dup Venue")
        # An event lives at the source location.
        store.put(store.base_item(store.event_pk("e1"), "META", store.EVENT,
                                  location_id=source["location_id"]))
        locations.link_event_to_location(source["location_id"], store.EVENT, "e1")

        result = locations.merge_locations(target["location_id"], [source["location_id"]])

        self.assertEqual(result["references_moved"], 1)
        # Event now points at the target.
        event = store.get(store.event_pk("e1"), "META")
        self.assertEqual(event["location_id"], target["location_id"])
        # Pointer moved under the target.
        self.assertEqual(
            [p["target_id"] for p in locations.events_at_location(target["location_id"])],
            ["e1"],
        )
        # Only the target remains listed.
        remaining = locations.list_locations()
        self.assertEqual([x["location_id"] for x in remaining],
                         [target["location_id"]])
        deleted_source = store.get(store.location_pk(source["location_id"]), "META")
        self.assertIn("deleted_at", deleted_source)
        self.assertEqual(deleted_source["merged_into"], target["location_id"])

    def test_merge_requires_existing_target(self):
        with self.assertRaises(ValueError):
            locations.merge_locations("nope", ["also-nope"])

    def test_location_label_inheritance_helper(self):
        loc = locations.create_location("Park")
        outdoor = labels.create_label(store.LOCATION_LABEL, "Outdoor")
        labels.attach_label(store.LOCATION_LABEL, outdoor["label_id"],
                            store.LOCATION, loc["location_id"])
        self.assertEqual(locations.location_label_ids(loc["location_id"]),
                         [outdoor["label_id"]])


if __name__ == "__main__":
    unittest.main()
