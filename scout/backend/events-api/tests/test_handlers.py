"""Tests for the processor / scheduler / sweep Lambda entrypoints."""

import json
import os
import unittest
from unittest import mock

import boto3
from moto import mock_dynamodb, mock_s3

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")
os.environ["SCOUT_ARTIFACTS_BUCKET"] = "scout-artifacts-test"

import artifacts  # noqa: E402
import events  # noqa: E402
import extractor  # noqa: E402
import pipeline  # noqa: E402
import processor_handler  # noqa: E402
import runs  # noqa: E402
import scheduler_handler  # noqa: E402
import sources  # noqa: E402
import store  # noqa: E402
import sweep_handler  # noqa: E402

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


def _stub_extractor(_pages):
    return extractor.ExtractionResult(
        extractor.STATUS_COMPLETED,
        events=[{"title": "From Agent", "start_date": "2099-07-01"}])


@mock_dynamodb
@mock_s3
class TestHandlers(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        store.reset_settings_cache()
        artifacts._s3 = None
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket="scout-artifacts-test")

    def test_processor_runs_email_source_and_persists_events(self):
        src = sources.create_source(sources.EMAIL, "venue@example.com")
        with mock.patch.object(pipeline, "make_extractor", return_value=_stub_extractor):
            result = processor_handler.lambda_handler(
                {"source_id": src["source_id"], "trigger": "manual",
                 "email_body": "<p>show</p>"}, None)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["events_count"], 1)
        # The extracted event is persisted as pending.
        self.assertEqual(len(events.list_by_review("pending")), 1)

    def test_processor_preview_persists_nothing(self):
        src = sources.create_source(sources.EMAIL, "venue@example.com")
        with mock.patch.object(pipeline, "make_extractor", return_value=_stub_extractor):
            result = processor_handler.lambda_handler(
                {"source_id": src["source_id"], "mode": "preview",
                 "email_body": "<p>show</p>"}, None)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(events.list_by_review("pending"), [])
        self.assertEqual(runs.list_runs(src["source_id"]), [])

    def test_processor_unknown_source(self):
        self.assertEqual(processor_handler.lambda_handler({"source_id": "nope"}, None),
                         {"error": "source not found"})

    def test_processor_discover_ensures_email_sources(self):
        with mock.patch.object(processor_handler.gmail, "discover_domains",
                               return_value=["eventbrite.com", "venue.org"]):
            result = processor_handler.lambda_handler({"mode": "discover"}, None)
        self.assertEqual(result["mode"], "discover")
        self.assertEqual(len(result["ensured"]), 2)
        self.assertTrue(all(e["created"] for e in result["ensured"]))
        created = {s["identity"] for s in sources.list_sources()}
        self.assertEqual(created, {"eventbrite.com", "venue.org"})

    def test_scheduler_discovers_then_dispatches_due(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "one-off"})
        fake_client = mock.Mock()
        scheduler_handler._lambda_client = fake_client
        result = scheduler_handler.lambda_handler({}, None)
        self.assertEqual(result["dispatched"], [src["source_id"]])
        # One discover invoke + one due-source invoke.
        self.assertEqual(fake_client.invoke.call_count, 2)
        payloads = [json.loads(c.kwargs["Payload"])
                    for c in fake_client.invoke.call_args_list]
        self.assertIn({"mode": "discover"}, payloads)
        # Schedule advanced -> one-off no longer due.
        self.assertEqual(sources.due_sources(), [])

    def test_sweep_reconciles_and_marks_past(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "scheduled"})
        runs.start_run(src["source_id"], runs.TRIGGER_MANUAL)  # left in-progress
        result = sweep_handler.lambda_handler({}, None)
        self.assertEqual(result["orphaned_runs"], 1)
        self.assertEqual(runs.list_runs(src["source_id"])[0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
