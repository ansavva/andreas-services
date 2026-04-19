"""
Unit tests for the events-api Lambda function.

Uses moto to mock DynamoDB — no AWS credentials or network access required.
"""

import importlib
import json
import os
import sys
import unittest
from datetime import date, timedelta

import boto3
import pytest
from moto import mock_dynamodb

TABLE_NAME = "test-scout-events"


def _seed_table(table, events):
    """Write a list of event dicts directly into the mock DynamoDB table."""
    with table.batch_writer() as batch:
        for item in events:
            batch.put_item(Item=item)


def _make_event(event_id, name, event_date="", email_id="email-1"):
    return {
        "event_id": event_id,
        "email_id": email_id,
        "event_name": name,
        "date": event_date,
        "time": "7:00 PM",
        "venue": "Central Park",
        "price": "Free",
        "description": "A test event",
        "links": [],
        "email_subject": "Test Subject",
        "email_sender": "test@example.com",
        "created_at": "2026-04-16T00:00:00+00:00",
        "source_email_date": "Wed, 16 Apr 2026 00:00:00 +0000",
    }


@mock_dynamodb
class TestEventsApi(unittest.TestCase):

    def setUp(self):
        # Spin up a fresh mock DynamoDB table for every test.
        self.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        self.table = self.dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Point the module at our test table and reload so the module-level
        # `table` variable picks up the mock resource.
        os.environ["DYNAMODB_TABLE_NAME"] = TABLE_NAME
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

        # Remove cached module so the reload picks up the patched env var.
        sys.modules.pop("lambda_function", None)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import lambda_function as lf
        importlib.reload(lf)
        self.lf = lf

    # ------------------------------------------------------------------
    # Helper: call the Lambda handler with a synthetic API GW event
    # ------------------------------------------------------------------

    def _call(self, method="GET", path="/api/events", query=None):
        return self.lf.lambda_handler(
            {
                "httpMethod": method,
                "path": path,
                "queryStringParameters": query or {},
            },
            {},
        )

    # ------------------------------------------------------------------
    # sort_events
    # ------------------------------------------------------------------

    def test_sort_events_dated_before_undated(self):
        events = [
            {"event_id": "a", "event_name": "No Date"},
            {"event_id": "b", "event_name": "Future", "date": "2099-01-01"},
            {"event_id": "c", "event_name": "Past", "date": "2000-01-01"},
        ]
        result = self.lf.sort_events(events)
        assert result[0]["date"] == "2000-01-01"
        assert result[1]["date"] == "2099-01-01"
        assert result[2].get("date", "") == ""

    def test_sort_events_all_dated(self):
        events = [
            {"event_id": "a", "date": "2026-06-01"},
            {"event_id": "b", "date": "2026-03-01"},
            {"event_id": "c", "date": "2026-05-01"},
        ]
        result = self.lf.sort_events(events)
        assert [e["date"] for e in result] == ["2026-03-01", "2026-05-01", "2026-06-01"]

    def test_sort_events_empty(self):
        assert self.lf.sort_events([]) == []

    # ------------------------------------------------------------------
    # GET /api/events — list all
    # ------------------------------------------------------------------

    def test_get_events_empty_table(self):
        resp = self._call()
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["events"] == []
        assert body["count"] == 0

    def test_get_events_returns_all(self):
        _seed_table(
            self.table,
            [
                _make_event("1", "Concert", "2026-05-01"),
                _make_event("2", "Festival"),
            ],
        )
        resp = self._call()
        body = json.loads(resp["body"])
        assert body["count"] == 2

    def test_get_events_sorted(self):
        _seed_table(
            self.table,
            [
                _make_event("1", "Late Event", "2026-12-01"),
                _make_event("2", "Early Event", "2026-01-01"),
                _make_event("3", "No Date Event"),
            ],
        )
        resp = self._call()
        body = json.loads(resp["body"])
        names = [e["event_name"] for e in body["events"]]
        assert names.index("Early Event") < names.index("Late Event")
        assert names[-1] == "No Date Event"

    # ------------------------------------------------------------------
    # GET /api/events?upcoming=true
    # ------------------------------------------------------------------

    def test_get_events_upcoming_only(self):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        _seed_table(
            self.table,
            [
                _make_event("1", "Past Event", yesterday),
                _make_event("2", "Future Event", tomorrow),
                _make_event("3", "No Date Event"),
            ],
        )
        resp = self._call(query={"upcoming": "true"})
        body = json.loads(resp["body"])
        names = [e["event_name"] for e in body["events"]]
        assert "Future Event" in names
        assert "Past Event" not in names
        assert "No Date Event" not in names

    def test_get_events_upcoming_false_returns_all(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _seed_table(self.table, [_make_event("1", "Past", yesterday)])
        resp = self._call(query={"upcoming": "false"})
        body = json.loads(resp["body"])
        assert body["count"] == 1

    # ------------------------------------------------------------------
    # GET /api/events/{id}
    # ------------------------------------------------------------------

    def test_get_event_by_id_found(self):
        _seed_table(self.table, [_make_event("abc-123", "My Event", "2026-06-15")])
        resp = self._call(path="/api/events/abc-123")
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["event_id"] == "abc-123"
        assert body["event_name"] == "My Event"

    def test_get_event_by_id_not_found(self):
        resp = self._call(path="/api/events/nonexistent")
        assert resp["statusCode"] == 404

    def test_get_event_by_id_missing_id(self):
        resp = self._call(path="/api/events/")
        assert resp["statusCode"] in (400, 404)

    # ------------------------------------------------------------------
    # CORS preflight
    # ------------------------------------------------------------------

    def test_options_returns_200(self):
        resp = self._call(method="OPTIONS", path="/api/events")
        assert resp["statusCode"] == 200
        assert "Access-Control-Allow-Origin" in resp["headers"]

    # ------------------------------------------------------------------
    # Unknown endpoints
    # ------------------------------------------------------------------

    def test_unknown_path_returns_404(self):
        resp = self._call(path="/unknown")
        assert resp["statusCode"] == 404

    def test_post_returns_404(self):
        resp = self._call(method="POST", path="/api/events")
        assert resp["statusCode"] == 404

    # ------------------------------------------------------------------
    # CORS headers always present
    # ------------------------------------------------------------------

    def test_cors_headers_on_success(self):
        resp = self._call()
        assert resp["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_cors_headers_on_not_found(self):
        resp = self._call(path="/api/events/missing")
        assert "Access-Control-Allow-Origin" in resp["headers"]
