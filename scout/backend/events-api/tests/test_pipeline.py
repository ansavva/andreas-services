"""Integration tests for the run pipeline (pipeline.py) over moto DynamoDB + S3."""

import os
import unittest

import boto3
from moto import mock_dynamodb, mock_s3

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")
os.environ["SCOUT_ARTIFACTS_BUCKET"] = "scout-artifacts-test"

import artifacts  # noqa: E402
import extractor  # noqa: E402
import pipeline  # noqa: E402
import runs  # noqa: E402
import sources  # noqa: E402
import store  # noqa: E402

_GSI_ATTRS = [
    "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "GSI3PK", "GSI3SK",
    "GSI4PK", "GSI4SK", "GSI5PK", "GSI5SK",
]

ROOT_HTML = """
  <html><body>
    <a href="https://example.com/show">show</a>
    <a href="https://offsite.com/x">offsite</a>
  </body></html>
"""


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


def _fetch_fn(url):
    if url == "https://example.com":
        return 200, ROOT_HTML
    if url == "https://example.com/show":
        return 200, "<p>Show details</p>"
    raise AssertionError(f"unexpected fetch: {url}")


def _extract_one(pages):
    return extractor.ExtractionResult(
        extractor.STATUS_COMPLETED,
        events=[{"title": "Extracted", "pages": len(pages)}],
        transcript=[{"role": "result", "text": "{\"events\": []}"}],
        tool_use_summary=[{"tool": "WebFetch", "count": 1, "args": [{"url": "x"}]}],
    )


@mock_dynamodb
@mock_s3
class TestPipeline(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        store.reset_settings_cache()
        artifacts._s3 = None
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket="scout-artifacts-test")
        self.src = sources.create_source(
            sources.WEBPAGE, "https://example.com",
            config={"mode": "scheduled"}, follow_links=True,
        )

    def test_preview_persists_nothing(self):
        result = pipeline.preview(self.src, fetch_fn=_fetch_fn, extractor=_extract_one)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["pages_fetched"], 2)  # root + 1 same-domain link
        self.assertEqual(len(result["link_outcomes"]), 1)
        # No run record created.
        self.assertEqual(runs.list_runs(self.src["source_id"]), [])

    def test_execute_run_stores_artifacts_transcript_and_finishes(self):
        run = pipeline.execute_run(self.src, runs.TRIGGER_SCHEDULED,
                                   fetch_fn=_fetch_fn, extractor=_extract_one)
        self.assertEqual(run["status"], "success")
        self.assertEqual(int(run["events_count"]), 1)
        self.assertIn("s3_root_html_ref", run)
        self.assertIn("agent_transcript_ref", run)
        self.assertEqual(run["tool_use_summary"][0]["tool"], "WebFetch")
        self.assertEqual(len(run["link_outcomes"]), 1)
        self.assertTrue(run["link_outcomes"][0]["ok"])
        self.assertIn("s3_ref", run["link_outcomes"][0])

        # Root, linked page and transcript are in S3 and readable.
        sid, rid = self.src["source_id"], run["run_id"]
        self.assertIn("Show details", artifacts.get_text(run["link_outcomes"][0]["s3_ref"]))
        self.assertIn("offsite", artifacts.get_text(artifacts.root_html_key(sid, rid)))
        self.assertIn("events", artifacts.get_text(run["agent_transcript_ref"]))

    def test_budget_exceeded_marks_error_and_discards_output(self):
        def over_budget(_pages):
            return extractor.ExtractionResult(
                extractor.STATUS_BUDGET_EXCEEDED,
                events=[{"title": "partial"}],
                transcript=[{"role": "assistant", "text": "..."}],
            )

        run = pipeline.execute_run(self.src, runs.TRIGGER_MANUAL,
                                   fetch_fn=_fetch_fn, extractor=over_budget)
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error_reason"], runs.REASON_BUDGET_EXCEEDED)
        self.assertEqual(int(run["events_count"]), 0)  # partial output discarded

    def test_execute_run_records_error_on_root_failure(self):
        def boom(_url):
            raise ConnectionError("dns fail")

        run = pipeline.execute_run(self.src, runs.TRIGGER_MANUAL,
                                   fetch_fn=boom, extractor=_extract_one)
        self.assertEqual(run["status"], "error")
        self.assertIn("dns fail", run["error_reason"])

    def test_manual_run_does_not_shift_schedule(self):
        pk = store.source_pk(self.src["source_id"])
        before = store.get(pk, "META")["next_run_at"]
        pipeline.execute_run(self.src, runs.TRIGGER_MANUAL,
                             fetch_fn=_fetch_fn, extractor=_extract_one)
        self.assertEqual(store.get(pk, "META")["next_run_at"], before)


if __name__ == "__main__":
    unittest.main()
