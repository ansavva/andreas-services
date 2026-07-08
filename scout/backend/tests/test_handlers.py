"""Tests for the processor / scheduler / sweep Lambda entrypoints."""

import json
import os
import unittest
from unittest import mock

import boto3
from moto import mock_dynamodb, mock_s3

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")
os.environ["SCOUT_ARTIFACTS_BUCKET"] = "scout-artifacts-test"

from scout_core.repositories import artifacts  # noqa: E402
from scout_core.services import events  # noqa: E402
from scout_core.clients.external import extractor  # noqa: E402
from scout_core.services import pipeline  # noqa: E402
from scout_core.services import runs  # noqa: E402
from scout_core.services import sources  # noqa: E402
from scout_core.repositories import store  # noqa: E402
from scout_core.repositories import dynamodb as dynamodb_adapter  # noqa: E402
from scout_core.handlers.aws.jobs import processor_handler  # noqa: E402
from scout_core.handlers.aws.jobs import scheduler_handler  # noqa: E402
from scout_core.handlers.aws.jobs import sweep_handler  # noqa: E402

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


def _stub_triage(_pages):
    return extractor.TriageResult(
        extractor.STATUS_COMPLETED,
        candidates=[{"title": "From Agent", "detail_url": None,
                     "fallback_event": {"title": "From Agent",
                                        "start_date": "2099-07-01"}}])


def _stub_enrich(_candidate, _page_text, **_kwargs):  # pragma: no cover
    raise AssertionError("enrich should not run for a linkless candidate")


def _stub_passes(*_args, **_kwargs):
    return _stub_triage, _stub_enrich


@mock_dynamodb
@mock_s3
class TestHandlers(unittest.TestCase):
    def setUp(self):
        dynamodb_adapter._dynamodb = None
        store.reset_settings_cache()
        artifacts._s3 = None
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket="scout-artifacts-test")

    def test_processor_runs_email_source_and_persists_events(self):
        src = sources.create_source(sources.EMAIL, "venue@example.com")
        with mock.patch.object(pipeline, "make_passes", side_effect=_stub_passes):
            result = processor_handler.lambda_handler(
                {"source_id": src["source_id"], "trigger": "manual",
                 "email_body": "<p>show</p>"}, None)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["events_count"], 1)
        # The extracted event is persisted as pending.
        self.assertEqual(len(events.list_by_review("pending")), 1)

    def test_processor_preview_persists_nothing(self):
        src = sources.create_source(sources.EMAIL, "venue@example.com")
        with mock.patch.object(pipeline, "make_passes", side_effect=_stub_passes):
            result = processor_handler.lambda_handler(
                {"source_id": src["source_id"], "mode": "preview",
                 "email_body": "<p>show</p>"}, None)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(events.list_by_review("pending"), [])
        self.assertEqual(runs.list_runs(src["source_id"]), [])

    def test_processor_unknown_source(self):
        self.assertEqual(processor_handler.lambda_handler({"source_id": "nope"}, None),
                         {"error": "source not found"})

    def test_processor_renders_webpage_fetches(self):
        src = sources.create_source(sources.WEBPAGE, "https://x.com",
                                    config={"mode": "one-off"})
        with mock.patch.object(pipeline, "make_passes", side_effect=_stub_passes), \
                mock.patch.object(pipeline, "execute_run") as run:
            run.return_value = {"run_id": "r", "status": "success", "events_count": 0}
            processor_handler.lambda_handler(
                {"source_id": src["source_id"], "trigger": "manual"}, None)
        self.assertIs(run.call_args.kwargs["fetch_fn"],
                      processor_handler.renderer_client.fetch_rendered)

    def test_processor_runs_ical_source_and_persists_events(self):
        src = sources.create_source(sources.ICAL, "https://feed.test/cal.ics",
                                    config={"mode": "one-off"})
        ics = ("BEGIN:VCALENDAR\r\nX-WR-TIMEZONE:UTC\r\nBEGIN:VEVENT\r\n"
               "SUMMARY:Gallery Opening\r\nDTSTART:20990701T180000Z\r\n"
               "LOCATION:Main St Gallery\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        with mock.patch.object(pipeline.fetcher, "fetch_url",
                               return_value=(200, ics)):
            result = processor_handler.lambda_handler(
                {"source_id": src["source_id"], "trigger": "manual"}, None)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["events_count"], 1)
        pending = events.list_by_review("pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["title"], "Gallery Opening")

    def test_processor_renders_email_followed_links(self):
        # Email bodies come from Gmail, but the links followed out of them are
        # page fetches and must render too.
        src = sources.create_source(sources.EMAIL, "venue@example.com")
        with mock.patch.object(pipeline, "make_passes", side_effect=_stub_passes), \
                mock.patch.object(pipeline, "execute_run") as run:
            run.return_value = {"run_id": "r", "status": "success", "events_count": 0}
            processor_handler.lambda_handler(
                {"source_id": src["source_id"], "trigger": "manual",
                 "email_body": "<p>x</p>"}, None)
        self.assertIs(run.call_args.kwargs["fetch_fn"],
                      processor_handler.renderer_client.fetch_rendered)

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
