"""
Unit tests for the email-processor Lambda function.

Tests cover the pure-Python logic (content extraction, event storage, dedup)
using moto for DynamoDB. Gmail and OpenAI calls are mocked with unittest.mock
so no network access or real credentials are required.
"""

import base64
import importlib
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_dynamodb

TABLE_NAME = "test-scout-events"


def _b64(text: str) -> str:
    """URL-safe base64-encode a string (as Gmail API returns body data)."""
    return base64.urlsafe_b64encode(text.encode()).decode()


def _make_message(subject="Test Subject", sender="test@example.com", body_html=None, body_plain=None, msg_id="email-001"):
    """Build a minimal Gmail message dict with the given fields."""
    body_html = body_html or "<p>Join us for an amazing concert!</p>"
    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": sender},
        {"name": "Date", "value": "Wed, 16 Apr 2026 10:00:00 +0000"},
    ]
    parts = [
        {
            "mimeType": "text/html",
            "body": {"data": _b64(body_html)},
        }
    ]
    if body_plain:
        parts.append(
            {
                "mimeType": "text/plain",
                "body": {"data": _b64(body_plain)},
            }
        )
    return {
        "id": msg_id,
        "payload": {
            "headers": headers,
            "parts": parts,
        },
    }


@mock_dynamodb
class TestEmailProcessor(unittest.TestCase):

    def setUp(self):
        # Mock DynamoDB table
        self.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        self.table = self.dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        os.environ["DYNAMODB_TABLE_NAME"] = TABLE_NAME
        os.environ["OPENAI_API_KEY"] = "test-key"
        os.environ["GMAIL_CLIENT_ID"] = "test-client-id"
        os.environ["GMAIL_CLIENT_SECRET"] = "test-secret"
        os.environ["GMAIL_ACCESS_TOKEN"] = "test-access-token"
        os.environ["GMAIL_REFRESH_TOKEN"] = "test-refresh-token"
        os.environ["MAX_EMAILS_PER_RUN"] = "5"
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

        sys.modules.pop("lambda_function", None)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import lambda_function as lf
        importlib.reload(lf)
        self.lf = lf

    # ------------------------------------------------------------------
    # MAX_EMAILS_PER_RUN env var
    # ------------------------------------------------------------------

    def test_max_emails_per_run_reads_env(self):
        assert self.lf.MAX_EMAILS_PER_RUN == 5

    # ------------------------------------------------------------------
    # extract_email_content
    # ------------------------------------------------------------------

    def test_extract_email_content_html(self):
        msg = _make_message(body_html="<h1>Concert Tonight</h1><p>Doors open at 7pm</p>")
        subject, sender, date_str, content = self.lf.extract_email_content(msg)
        assert subject == "Test Subject"
        assert "Concert Tonight" in content
        assert "7pm" in content

    def test_extract_email_content_plain_fallback(self):
        msg = _make_message(body_html=None, body_plain="Just plain text content")
        # Overwrite the html part so it has no data
        msg["payload"]["parts"][0]["body"]["data"] = ""
        subject, sender, date_str, content = self.lf.extract_email_content(msg)
        assert "Just plain text content" in content

    def test_extract_email_content_single_part(self):
        """Single-part messages (no 'parts' key in payload)."""
        msg = {
            "id": "single-001",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Single Part"},
                    {"name": "From", "value": "a@b.com"},
                    {"name": "Date", "value": "Wed, 16 Apr 2026 10:00:00 +0000"},
                ],
                "mimeType": "text/plain",
                "body": {"data": _b64("Hello from a single-part email.")},
            },
        }
        subject, sender, date_str, content = self.lf.extract_email_content(msg)
        assert subject == "Single Part"
        assert "Hello from a single-part email." in content

    def test_extract_email_content_caps_at_6000(self):
        long_body = "x" * 10000
        msg = _make_message(body_plain=long_body, body_html=None)
        msg["payload"]["parts"][0]["body"]["data"] = ""
        _, _, _, content = self.lf.extract_email_content(msg)
        assert len(content) <= 6000

    # ------------------------------------------------------------------
    # store_events
    # ------------------------------------------------------------------

    def test_store_events_writes_to_dynamodb(self):
        events = [
            {
                "event_name": "Jazz Night",
                "date": "2026-05-10",
                "time": "8:00 PM",
                "venue": "Blue Note",
                "price": "$25",
                "description": "Live jazz",
                "links": ["https://example.com"],
            }
        ]
        count = self.lf.store_events(events, "email-001", "Jazz Subject", "venue@example.com", "Thu, 10 Apr 2026")
        assert count == 1

        result = self.table.scan()
        assert len(result["Items"]) == 1
        item = result["Items"][0]
        assert item["event_name"] == "Jazz Night"
        assert item["email_id"] == "email-001"
        assert item["venue"] == "Blue Note"

    def test_store_events_multiple(self):
        events = [
            {"event_name": "Event A", "date": "2026-06-01", "time": "", "venue": "", "price": "", "description": "", "links": []},
            {"event_name": "Event B", "date": "2026-06-02", "time": "", "venue": "", "price": "", "description": "", "links": []},
        ]
        count = self.lf.store_events(events, "email-002", "Multi Event Email", "a@b.com", "")
        assert count == 2
        result = self.table.scan()
        assert len(result["Items"]) == 2

    def test_store_events_handles_missing_optional_fields(self):
        events = [{"event_name": "Minimal Event"}]
        count = self.lf.store_events(events, "email-003", "Subject", "sender@x.com", "")
        assert count == 1
        item = self.table.scan()["Items"][0]
        assert item["date"] == ""
        assert item["venue"] == ""
        assert item["links"] == []

    # ------------------------------------------------------------------
    # email_already_processed
    # ------------------------------------------------------------------

    def test_email_already_processed_false_when_absent(self):
        assert self.lf.email_already_processed("not-in-db") is False

    def test_email_already_processed_true_after_storing(self):
        events = [
            {"event_name": "Stored Event", "date": "", "time": "", "venue": "", "price": "", "description": "", "links": []}
        ]
        self.lf.store_events(events, "email-dup", "Subj", "s@s.com", "")
        assert self.lf.email_already_processed("email-dup") is True

    # ------------------------------------------------------------------
    # lambda_handler — integration with mocked Gmail + OpenAI
    # ------------------------------------------------------------------

    def _make_gmail_service(self, messages, label_id="LABEL_1"):
        """Return a mock Gmail service that yields the given message stubs."""
        service = MagicMock()
        # labels().list()
        service.users().labels().list().execute.return_value = {
            "labels": [{"id": label_id, "name": "Events"}]
        }
        # messages().list()
        service.users().messages().list().execute.return_value = {
            "messages": [{"id": m["id"]} for m in messages]
        }
        # messages().get() — return the full message dict for each id
        msg_map = {m["id"]: m for m in messages}
        service.users().messages().get().execute.side_effect = lambda: None

        def _get_execute(msg_id):
            return msg_map[msg_id]

        # Wire up the call chain: .get(userId=…, id=msg_id, …).execute()
        def _get_side_effect(**kwargs):
            mock_get = MagicMock()
            mock_get.execute.return_value = msg_map[kwargs["id"]]
            return mock_get

        service.users().messages().get.side_effect = _get_side_effect
        return service

    @patch("lambda_function.get_gmail_service")
    @patch("lambda_function.openai.ChatCompletion.create")
    def test_lambda_handler_processes_emails(self, mock_openai, mock_gmail):
        messages = [_make_message(msg_id="msg-001")]
        mock_gmail.return_value = self._make_gmail_service(messages)
        mock_openai.return_value = MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content=json.dumps([
                            {"event_name": "Test Gig", "date": "2026-05-01", "time": "9 PM",
                             "venue": "CBGB", "price": "$10", "description": "Rock show", "links": []}
                        ])
                    )
                )
            ]
        )

        resp = self.lf.lambda_handler({}, {})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["emails_processed"] == 1
        assert body["events_stored"] == 1
        assert body["errors"] == []

    @patch("lambda_function.get_gmail_service")
    @patch("lambda_function.openai.ChatCompletion.create")
    def test_lambda_handler_skips_already_processed(self, mock_openai, mock_gmail):
        # Pre-seed the table so email-exists looks up the email as processed.
        events = [{"event_name": "Pre-existing", "date": "", "time": "", "venue": "", "price": "", "description": "", "links": []}]
        self.lf.store_events(events, "msg-dup", "Subj", "a@a.com", "")

        messages = [_make_message(msg_id="msg-dup")]
        mock_gmail.return_value = self._make_gmail_service(messages)

        resp = self.lf.lambda_handler({}, {})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["emails_processed"] == 0
        mock_openai.assert_not_called()

    @patch("lambda_function.get_gmail_service")
    @patch("lambda_function.openai.ChatCompletion.create")
    def test_lambda_handler_handles_no_events_from_openai(self, mock_openai, mock_gmail):
        messages = [_make_message(msg_id="msg-empty")]
        mock_gmail.return_value = self._make_gmail_service(messages)
        mock_openai.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="[]"))]
        )

        resp = self.lf.lambda_handler({}, {})
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["emails_processed"] == 1
        assert body["events_stored"] == 0

    @patch("lambda_function.get_gmail_service")
    def test_lambda_handler_fatal_error_returns_500(self, mock_gmail):
        mock_gmail.side_effect = RuntimeError("Gmail blew up")
        resp = self.lf.lambda_handler({}, {})
        assert resp["statusCode"] == 500
