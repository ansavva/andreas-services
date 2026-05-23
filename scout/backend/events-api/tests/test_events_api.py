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

EVENTS_TABLE_NAME = "test-scout-events"
EMAILS_TABLE_NAME = "test-scout-emails"


def _seed_events(table, events):
    """Write a list of event dicts directly into the mock events table."""
    with table.batch_writer() as batch:
        for item in events:
            batch.put_item(Item=item)


def _seed_emails(table, emails):
    """Write a list of email dicts directly into the mock emails table."""
    with table.batch_writer() as batch:
        for item in emails:
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
    }


def _make_email(email_id="email-1", subject="Test Subject", sender="test@example.com",
                processed_at="2026-04-16T00:00:00+00:00", event_count=1):
    return {
        "email_id": email_id,
        "email_subject": subject,
        "email_sender": sender,
        "source_email_date": "Wed, 16 Apr 2026 00:00:00 +0000",
        "image_url": "",
        "processed_at": processed_at,
        "event_count": event_count,
    }


@mock_dynamodb
class TestEventsApi(unittest.TestCase):

    def setUp(self):
        self.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        self.table = self.dynamodb.create_table(
            TableName=EVENTS_TABLE_NAME,
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        self.emails_table = self.dynamodb.create_table(
            TableName=EMAILS_TABLE_NAME,
            KeySchema=[{"AttributeName": "email_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "email_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        os.environ["DYNAMODB_TABLE_NAME"] = EVENTS_TABLE_NAME
        os.environ["DYNAMODB_EMAILS_TABLE_NAME"] = EMAILS_TABLE_NAME
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

        sys.modules.pop("lambda_function", None)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import lambda_function as lf
        importlib.reload(lf)
        self.lf = lf

    # ------------------------------------------------------------------
    # Helper: call the Lambda handler with a synthetic API GW event
    # ------------------------------------------------------------------

    def _call(self, method="GET", path="/api/events", query=None):
        # Simulate the API Gateway event shape: resource holds the route template
        # (e.g. "/api/events/{id}") and pathParameters holds the extracted values.
        if path.startswith("/api/events/"):
            suffix = path[len("/api/events/"):]
            resource = "/api/events/{id}"
            path_params = {"id": suffix}
        else:
            resource = path
            path_params = {}

        return self.lf.lambda_handler(
            {
                "httpMethod": method,
                "resource": resource,
                "path": path,
                "pathParameters": path_params,
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
        _seed_events(
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
        _seed_events(
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

    def test_get_events_joins_email_metadata(self):
        _seed_events(self.table, [_make_event("1", "Concert", "2026-05-01", email_id="email-1")])
        _seed_emails(self.emails_table, [_make_email(
            email_id="email-1",
            subject="Concert Newsletter",
            sender="venue@example.com",
        )])
        resp = self._call()
        body = json.loads(resp["body"])
        assert body["count"] == 1
        event = body["events"][0]
        assert event["email_subject"] == "Concert Newsletter"
        assert event["email_sender"] == "venue@example.com"

    # ------------------------------------------------------------------
    # GET /api/events?upcoming=true
    # ------------------------------------------------------------------

    def test_get_events_upcoming_only(self):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        _seed_events(
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
        _seed_events(self.table, [_make_event("1", "Past", yesterday)])
        resp = self._call(query={"upcoming": "false"})
        body = json.loads(resp["body"])
        assert body["count"] == 1

    # ------------------------------------------------------------------
    # GET /api/events/{id}
    # ------------------------------------------------------------------

    def test_get_event_by_id_found(self):
        _seed_events(self.table, [_make_event("abc-123", "My Event", "2026-06-15")])
        resp = self._call(path="/api/events/abc-123")
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["event_id"] == "abc-123"
        assert body["event_name"] == "My Event"

    def test_get_event_by_id_joins_email_metadata(self):
        _seed_events(self.table, [_make_event("abc-123", "My Event", email_id="email-1")])
        _seed_emails(self.emails_table, [_make_email(email_id="email-1", subject="The Newsletter")])
        resp = self._call(path="/api/events/abc-123")
        body = json.loads(resp["body"])
        assert body["email_subject"] == "The Newsletter"

    def test_get_event_by_id_not_found(self):
        resp = self._call(path="/api/events/nonexistent")
        assert resp["statusCode"] == 404

    def test_get_event_by_id_missing_id(self):
        resp = self._call(path="/api/events/")
        assert resp["statusCode"] in (400, 404)

    # ------------------------------------------------------------------
    # GET /api/admin/emails
    # ------------------------------------------------------------------

    def test_get_admin_emails_empty(self):
        resp = self._call(path="/api/admin/emails")
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["emails"] == []
        assert body["count"] == 0

    def test_get_admin_emails_returns_emails(self):
        _seed_emails(self.emails_table, [
            _make_email("email-1", subject="Newsletter A", processed_at="2026-05-01T10:00:00+00:00", event_count=3),
            _make_email("email-2", subject="Newsletter B", processed_at="2026-04-01T10:00:00+00:00", event_count=1),
        ])
        resp = self._call(path="/api/admin/emails")
        body = json.loads(resp["body"])
        assert body["count"] == 2

    def test_get_admin_emails_sorted_newest_first(self):
        _seed_emails(self.emails_table, [
            _make_email("email-1", processed_at="2026-03-01T10:00:00+00:00"),
            _make_email("email-2", processed_at="2026-05-01T10:00:00+00:00"),
        ])
        resp = self._call(path="/api/admin/emails")
        body = json.loads(resp["body"])
        dates = [e["processed_at"] for e in body["emails"]]
        assert dates == sorted(dates, reverse=True)

    def test_get_admin_emails_has_required_fields(self):
        _seed_emails(self.emails_table, [_make_email(
            email_id="email-1",
            subject="Test Subject",
            sender="test@example.com",
            processed_at="2026-05-01T10:00:00+00:00",
            event_count=2,
        )])
        resp = self._call(path="/api/admin/emails")
        body = json.loads(resp["body"])
        email = body["emails"][0]
        assert email["email_id"] == "email-1"
        assert email["email_subject"] == "Test Subject"
        assert email["email_sender"] == "test@example.com"
        assert email["processed_at"] == "2026-05-01T10:00:00+00:00"
        assert email["event_count"] == 2

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
