"""Unit tests for cascade soft-delete and recursive restore (deletion.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

import deletion  # noqa: E402
import events  # noqa: E402
import locations  # noqa: E402
import runs  # noqa: E402
import sources  # noqa: E402
import store  # noqa: E402

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


def _create_settings(dynamodb):
    dynamodb.create_table(
        TableName="scout-settings",
        KeySchema=[{"AttributeName": "setting_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "setting_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@mock_dynamodb
class TestDeletion(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        store.reset_settings_cache()
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)

    def _source_with_event(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "scheduled"})
        ev = events.create_event(src["source_id"], title="Show", start_date="2099-01-01")
        events.create_subevent(ev["event_id"], start_date="2099-01-02")
        run = runs.start_run(src["source_id"], runs.TRIGGER_MANUAL)
        runs.finish_run(src["source_id"], run["run_id"], status=runs.SUCCESS)
        return src, ev

    def test_preview_delete_source(self):
        src, _ = self._source_with_event()
        preview = deletion.preview_delete_source(src["source_id"])
        self.assertEqual(preview, {"events": 1, "subevents": 1, "runs": 1})

    def test_delete_source_cascades_and_restores(self):
        src, ev = self._source_with_event()
        result = deletion.delete_source(src["source_id"])
        self.assertEqual(result["events"], 1)
        self.assertEqual(result["subevents"], 1)

        # Everything is hidden from default views, visible in deleted views.
        self.assertEqual(sources.list_sources(), [])
        self.assertIsNotNone(store.get(store.event_pk(ev["event_id"]), "META")["deleted_at"])
        self.assertEqual(len(store.query_deleted(store.SOURCE)), 1)
        self.assertEqual(len(store.query_deleted(store.EVENT)), 1)

        # Recursive restore brings the whole chain back.
        deletion.restore_cascade(result["cascade_id"])
        self.assertEqual(len(sources.list_sources()), 1)
        self.assertNotIn("deleted_at", events.get_event(ev["event_id"]))
        self.assertEqual(len(events.list_subevents(ev["event_id"])), 1)
        self.assertEqual(store.query_deleted(store.EVENT), [])

    def test_delete_source_opt_out_leaves_events(self):
        src, ev = self._source_with_event()
        deletion.delete_source(src["source_id"], cascade_events=False)
        # Source gone, runs gone, but the event remains live (orphaned).
        self.assertEqual(sources.list_sources(), [])
        self.assertNotIn("deleted_at", events.get_event(ev["event_id"]))

    def test_delete_location_cascades_to_events(self):
        loc = locations.create_location("Venue")
        ev = events.create_event("s", title="Show", start_date="2099-01-01",
                                 location_id=loc["location_id"])
        preview = deletion.preview_delete_location(loc["location_id"])
        self.assertEqual(preview["events"], 1)

        result = deletion.delete_location(loc["location_id"])
        self.assertEqual(result["events"], 1)
        self.assertIsNotNone(events.get_event(ev["event_id"])["deleted_at"])
        deletion.restore(store.location_pk(loc["location_id"]), "META")
        self.assertNotIn("deleted_at", events.get_event(ev["event_id"]))

    def test_delete_event_cascades_subs_with_opt_out(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        events.create_subevent(ev["event_id"], start_date="2099-01-02")

        deletion.delete_event(ev["event_id"], cascade_subs=False)
        # Event soft-deleted, sub left live.
        self.assertIsNotNone(events.get_event(ev["event_id"])["deleted_at"])
        self.assertEqual(len(events.list_subevents(ev["event_id"])), 1)

    def test_restore_via_entity_key_restores_cascade(self):
        src, ev = self._source_with_event()
        deletion.delete_source(src["source_id"])
        # Restoring by the source key recursively restores its cascade.
        deletion.restore(store.source_pk(src["source_id"]), "META")
        self.assertEqual(len(sources.list_sources()), 1)
        self.assertNotIn("deleted_at", events.get_event(ev["event_id"]))


if __name__ == "__main__":
    unittest.main()
