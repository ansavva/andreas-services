"""Unit tests for the source service layer (sources.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.domain import labels  # noqa: E402
from scout_core.domain import sources  # noqa: E402
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
class TestSources(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        _create_core(boto3.resource("dynamodb", region_name="us-east-1"))

    def test_create_email_source(self):
        src = sources.create_source(sources.EMAIL, "venue@Example.com",
                                    config={"check_frequency": "weekly"})
        self.assertEqual(src["type"], "email")
        self.assertEqual(src["identity_norm"], "venue@example.com")
        self.assertEqual(src["config"]["check_frequency"], "weekly")
        self.assertIn("next_run_at", src)  # schedulable
        self.assertEqual(src["GSI1PK"], "SRC#LISTED")

    def test_create_validates_config(self):
        with self.assertRaises(ValueError):
            sources.create_source(sources.EMAIL, "x@y.com",
                                  config={"check_frequency": "monthly"})
        with self.assertRaises(ValueError):
            sources.create_source(sources.WEBPAGE, "https://x.com",
                                  config={"mode": "bogus"})
        with self.assertRaises(ValueError):
            sources.create_source("ftp", "x")

    def test_oneoff_webpage_is_due_then_falls_off(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "one-off"})
        due = sources.due_sources()
        self.assertIn(src["source_id"], [s["source_id"] for s in due])
        # Simulate that it has run.
        store.set_attrs(store.source_pk(src["source_id"]), "META",
                        {"last_run_at": store.now_iso()})
        sources.advance_schedule(src["source_id"])
        self.assertEqual(sources.due_sources(), [])

    def test_scheduled_source_not_due_until_interval(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "scheduled", "schedule_preset": "daily"})
        # next_run_at is ~1 day out, so not due now.
        self.assertEqual(sources.due_sources(), [])
        self.assertGreater(src["next_run_at"], store.now_iso())

    def test_disable_removes_from_schedule(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "one-off"})
        sid = src["source_id"]
        self.assertTrue(sources.due_sources())
        sources.update_source(sid, {"status": "disabled"})
        self.assertEqual(sources.due_sources(), [])
        updated = store.get(store.source_pk(sid), "META")
        self.assertNotIn("GSI4PK", updated)

    def test_archive_moves_between_listings(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "scheduled"})
        sid = src["source_id"]
        self.assertEqual(len(sources.list_sources()), 1)
        self.assertEqual(sources.list_sources(archived=True), [])

        sources.set_archived(sid, True)
        self.assertEqual(sources.list_sources(), [])
        self.assertEqual(len(sources.list_sources(archived=True)), 1)
        # Archiving stops scheduled runs.
        self.assertEqual(sources.due_sources(), [])

    def test_list_filter_by_status(self):
        a = sources.create_source(sources.WEBPAGE, "https://a.com",
                                  config={"mode": "scheduled"})
        sources.create_source(sources.WEBPAGE, "https://b.com",
                              config={"mode": "scheduled"})
        sources.update_source(a["source_id"], {"status": "disabled"})
        self.assertEqual(len(sources.list_sources(status="active")), 1)
        self.assertEqual(len(sources.list_sources(status="disabled")), 1)

    def test_source_labels(self):
        src = sources.create_source(sources.EMAIL, "x@y.com")
        label = labels.create_label(store.SOURCE_LABEL, "Newsletter")
        sources.add_label(src["source_id"], label["label_id"])
        self.assertEqual(sources.label_ids(src["source_id"]), [label["label_id"]])
        sources.remove_label(src["source_id"], label["label_id"])
        self.assertEqual(sources.label_ids(src["source_id"]), [])

    def test_delete_and_restore(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "scheduled"})
        sid = src["source_id"]
        sources.delete_source(sid)
        self.assertEqual(sources.list_sources(), [])
        self.assertEqual(sources.due_sources(), [])
        self.assertEqual(len(store.query_deleted(store.SOURCE)), 1)

        sources.restore_source(sid)
        self.assertEqual(len(sources.list_sources()), 1)

    def test_follow_links_and_agent_overrides(self):
        src = sources.create_source(
            sources.WEBPAGE, "https://x.com", config={"mode": "scheduled"},
            follow_links=True, agent_model="claude-sonnet-4-6",
            agent_budget_tokens=50000,
        )
        self.assertTrue(src["follow_links"])
        self.assertEqual(src["agent_model_override"], "claude-sonnet-4-6")
        self.assertEqual(src["agent_budget_tokens_override"], 50000)

    def test_ensure_email_source_creates_active_and_due_now(self):
        src, created = sources.ensure_email_source("Eventbrite.com")
        self.assertTrue(created)
        self.assertEqual(src["type"], "email")
        self.assertEqual(src["identity"], "eventbrite.com")
        self.assertEqual(src["status"], "active")
        # Due immediately so the next scheduler tick ingests its backlog.
        self.assertLessEqual(src["next_run_at"], sources._iso(sources._now()))
        self.assertEqual([s["source_id"] for s in sources.due_sources()],
                         [src["source_id"]])

    def test_ensure_email_source_is_idempotent(self):
        first, created1 = sources.ensure_email_source("venue.org")
        second, created2 = sources.ensure_email_source("venue.org")
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(first["source_id"], second["source_id"])
        self.assertEqual(len(sources.list_sources()), 1)

    def test_ensure_email_source_leaves_archived_untouched(self):
        src, _ = sources.ensure_email_source("venue.org")
        sources.set_archived(src["source_id"], True)
        again, created = sources.ensure_email_source("venue.org")
        self.assertFalse(created)
        self.assertEqual(again["source_id"], src["source_id"])
        self.assertTrue(again["archived"])


if __name__ == "__main__":
    unittest.main()
