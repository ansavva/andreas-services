"""Unit tests for the source-run lifecycle (runs.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.services import runs  # noqa: E402
from scout_core.services import sources  # noqa: E402
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
class TestRuns(unittest.TestCase):
    def setUp(self):
        dynamodb_adapter._dynamodb = None
        _create_core(boto3.resource("dynamodb", region_name="us-east-1"))
        self.src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                         config={"mode": "scheduled"})
        self.sid = self.src["source_id"]

    def test_start_and_finish_success(self):
        run = runs.start_run(self.sid, runs.TRIGGER_MANUAL)
        self.assertEqual(run["status"], "in_progress")
        self.assertEqual(run["GSI1PK"], "RUN#INPROGRESS")

        runs.finish_run(self.sid, run["run_id"], status=runs.SUCCESS, events_count=3)
        done = runs.get_run(self.sid, run["run_id"])
        self.assertEqual(done["status"], "success")
        self.assertIn("finished_at", done)
        self.assertNotIn("GSI1PK", done)  # in-progress marker cleared

        src = store.get(store.source_pk(self.sid), "META")
        self.assertEqual(src["last_run_status"], "success")
        self.assertEqual(int(src["consecutive_zero_event_runs"]), 0)

    def test_zero_event_counter_increments(self):
        for _ in range(2):
            run = runs.start_run(self.sid, runs.TRIGGER_SCHEDULED)
            runs.finish_run(self.sid, run["run_id"], status=runs.SUCCESS, events_count=0)
        src = store.get(store.source_pk(self.sid), "META")
        self.assertEqual(int(src["consecutive_zero_event_runs"]), 2)
        # A productive run resets it.
        run = runs.start_run(self.sid, runs.TRIGGER_SCHEDULED)
        runs.finish_run(self.sid, run["run_id"], status=runs.SUCCESS, events_count=1)
        src = store.get(store.source_pk(self.sid), "META")
        self.assertEqual(int(src["consecutive_zero_event_runs"]), 0)

    def test_artifacts_links_and_tools(self):
        run = runs.start_run(self.sid, runs.TRIGGER_MANUAL)
        rid = run["run_id"]
        runs.set_artifacts(self.sid, rid, root_html="s3://b/root.html",
                           transcript="s3://b/t.json")
        runs.add_link_outcome(self.sid, rid, {"url": "https://x.com/1", "ok": True})
        runs.add_link_outcome(self.sid, rid, {"url": "https://x.com/2", "ok": False,
                                              "reason": "http 404"})

        got = runs.get_run(self.sid, rid)
        self.assertNotIn("s3_root_body_ref", got)
        self.assertEqual(got["s3_root_html_ref"], "s3://b/root.html")
        self.assertEqual(got["agent_transcript_ref"], "s3://b/t.json")
        self.assertEqual(len(got["link_outcomes"]), 2)
        self.assertFalse(got["link_outcomes"][1]["ok"])

    def test_list_runs_newest_first(self):
        ids = []
        for _ in range(3):
            ids.append(runs.start_run(self.sid, runs.TRIGGER_MANUAL)["run_id"])
        listed = [r["run_id"] for r in runs.list_runs(self.sid)]
        self.assertEqual(listed, list(reversed(ids)))

    def test_reconcile_orphaned_runs(self):
        runs.start_run(self.sid, runs.TRIGGER_MANUAL)
        runs.start_run(self.sid, runs.TRIGGER_SCHEDULED)
        count = runs.reconcile_orphaned_runs()
        self.assertEqual(count, 2)
        for run in runs.list_runs(self.sid):
            self.assertEqual(run["status"], "error")
            self.assertEqual(run["error_reason"], runs.REASON_ORPHANED)
        self.assertEqual(runs.reconcile_orphaned_runs(), 0)


if __name__ == "__main__":
    unittest.main()
