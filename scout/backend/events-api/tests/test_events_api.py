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
from moto import mock_dynamodb

EVENTS_TABLE_NAME = "scout-events"
EMAILS_TABLE_NAME = "scout-emails"
SENDERS_TABLE_NAME = "scout-senders"
REGIONS_TABLE_NAME = "scout-regions"
CATEGORIES_TABLE_NAME = "scout-categories"


def _seed(table, items):
    """Write a list of item dicts directly into a mock table."""
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)


# Backwards-compatible aliases used throughout the suite.
_seed_events = _seed
_seed_emails = _seed


def _make_event(event_id, name, event_date="", email_id="email-1", status="published",
                regions=None, categories=None, sender_key="news@example.com"):
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
        "status": status,
        "regions": regions if regions is not None else ["nyc"],
        "categories": categories if categories is not None else [],
        "sender_key": sender_key,
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

        self.senders_table = self.dynamodb.create_table(
            TableName=SENDERS_TABLE_NAME,
            KeySchema=[{"AttributeName": "sender_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "sender_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        self.regions_table = self.dynamodb.create_table(
            TableName=REGIONS_TABLE_NAME,
            KeySchema=[{"AttributeName": "slug", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "slug", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        self.categories_table = self.dynamodb.create_table(
            TableName=CATEGORIES_TABLE_NAME,
            KeySchema=[{"AttributeName": "slug", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "slug", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        os.environ.pop("SCOUT_TABLE_SUFFIX", None)
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

        sys.modules.pop("lambda_function", None)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import lambda_function as lf
        importlib.reload(lf)
        self.lf = lf

    # ------------------------------------------------------------------
    # Helper: call the Lambda handler with a synthetic API GW event
    # ------------------------------------------------------------------

    def _call(self, method="GET", path="/api/events", query=None, body=None):
        # Simulate an API Gateway proxy event. Routing anchors on the "/api/"
        # segment of `path`, so we don't need to model resource templates.
        return self.lf.lambda_handler(
            {
                "httpMethod": method,
                "resource": path,
                "path": path,
                "pathParameters": {},
                "queryStringParameters": query or {},
                "body": json.dumps(body) if body is not None else None,
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
    # status / region / category filtering (public)
    # ------------------------------------------------------------------

    def test_public_events_only_published(self):
        _seed_events(self.table, [
            _make_event("1", "Live", "2026-05-01", status="published"),
            _make_event("2", "Pending", "2026-05-02", status="pending"),
            _make_event("3", "Rejected", "2026-05-03", status="rejected"),
        ])
        body = json.loads(self._call()["body"])
        names = [e["event_name"] for e in body["events"]]
        assert names == ["Live"]

    def test_public_events_filter_by_region(self):
        _seed_events(self.table, [
            _make_event("1", "NYC Show", "2026-05-01", regions=["nyc"]),
            _make_event("2", "SF Show", "2026-05-02", regions=["sf"]),
        ])
        body = json.loads(self._call(query={"region": "sf"})["body"])
        names = [e["event_name"] for e in body["events"]]
        assert names == ["SF Show"]

    def test_public_events_filter_by_category(self):
        _seed_events(self.table, [
            _make_event("1", "Gallery", "2026-05-01", categories=["art"]),
            _make_event("2", "Dinner", "2026-05-02", categories=["food"]),
        ])
        body = json.loads(self._call(query={"category": "food"})["body"])
        names = [e["event_name"] for e in body["events"]]
        assert names == ["Dinner"]

    def test_regionless_event_hidden_under_region_filter(self):
        _seed_events(self.table, [_make_event("1", "Unclassified", "2026-05-01", regions=[])])
        body = json.loads(self._call(query={"region": "nyc"})["body"])
        assert body["count"] == 0

    # ------------------------------------------------------------------
    # GET /api/regions and /api/categories
    # ------------------------------------------------------------------

    def test_get_regions_only_with_events(self):
        _seed(self.regions_table, [
            {"slug": "nyc", "name": "New York City"},
            {"slug": "sf", "name": "San Francisco"},
        ])
        _seed_events(self.table, [_make_event("1", "NYC", "2026-05-01", regions=["nyc"])])
        body = json.loads(self._call(path="/api/regions")["body"])
        slugs = [r["slug"] for r in body["regions"]]
        assert slugs == ["nyc"]  # sf has no events
        assert body["regions"][0]["count"] == 1

    def test_get_categories_only_active(self):
        _seed(self.categories_table, [
            {"slug": "food", "name": "Food", "status": "active"},
            {"slug": "fashion", "name": "Fashion", "status": "suggested"},
        ])
        _seed_events(self.table, [_make_event("1", "Dinner", "2026-05-01", categories=["food"])])
        body = json.loads(self._call(path="/api/categories")["body"])
        slugs = [c["slug"] for c in body["categories"]]
        assert slugs == ["food"]
        assert body["categories"][0]["count"] == 1

    # ------------------------------------------------------------------
    # Admin: event approval lifecycle
    # ------------------------------------------------------------------

    def test_admin_events_lists_all_statuses(self):
        _seed_events(self.table, [
            _make_event("1", "Live", status="published"),
            _make_event("2", "Pending", status="pending"),
        ])
        body = json.loads(self._call(path="/api/admin/events", query={"status": "pending"})["body"])
        assert [e["event_name"] for e in body["events"]] == ["Pending"]

    def test_admin_approve_publishes_event(self):
        _seed_events(self.table, [_make_event("e1", "Pending", "2026-05-01", status="pending")])
        resp = self._call(method="POST", path="/api/admin/events/e1/approve")
        assert resp["statusCode"] == 200
        # Now visible publicly
        body = json.loads(self._call()["body"])
        assert [e["event_name"] for e in body["events"]] == ["Pending"]

    def test_admin_reject_hides_event(self):
        _seed_events(self.table, [_make_event("e1", "Bad", "2026-05-01", status="pending")])
        self._call(method="POST", path="/api/admin/events/e1/reject")
        item = self.table.get_item(Key={"event_id": "e1"})["Item"]
        assert item["status"] == "rejected"

    def test_admin_unpublish_returns_to_pending(self):
        _seed_events(self.table, [_make_event("e1", "Live", "2026-05-01", status="published")])
        self._call(method="POST", path="/api/admin/events/e1/unpublish")
        item = self.table.get_item(Key={"event_id": "e1"})["Item"]
        assert item["status"] == "pending"
        assert json.loads(self._call()["body"])["count"] == 0

    def test_admin_edit_event_fields(self):
        _seed_events(self.table, [_make_event("e1", "Typo", "2026-05-01")])
        resp = self._call(method="PUT", path="/api/admin/events/e1",
                          body={"event_name": "Fixed", "categories": ["music"]})
        assert resp["statusCode"] == 200
        item = self.table.get_item(Key={"event_id": "e1"})["Item"]
        assert item["event_name"] == "Fixed"
        assert item["categories"] == ["music"]

    # ------------------------------------------------------------------
    # Admin: sender classification re-tags events
    # ------------------------------------------------------------------

    def test_admin_classify_sender_retags_and_reveals(self):
        _seed(self.senders_table, [{
            "sender_key": "promo@venue.com", "display_sender": "Promo",
            "regions": [], "status": "pending", "first_seen": "2026-01-01T00:00:00+00:00",
        }])
        _seed_events(self.table, [
            _make_event("e1", "Hidden", "2026-05-01", status="published",
                        regions=[], sender_key="promo@venue.com"),
        ])
        # Initially hidden under any region
        assert json.loads(self._call(query={"region": "nyc"})["body"])["count"] == 0

        resp = self._call(method="PUT", path="/api/admin/senders/promo@venue.com",
                          body={"regions": ["nyc"]})
        assert resp["statusCode"] == 200

        sender = self.senders_table.get_item(Key={"sender_key": "promo@venue.com"})["Item"]
        assert sender["status"] == "classified"
        assert sender["regions"] == ["nyc"]
        # Region registry auto-created, and the event now shows under nyc
        assert self.regions_table.get_item(Key={"slug": "nyc"}).get("Item") is not None
        assert json.loads(self._call(query={"region": "nyc"})["body"])["count"] == 1

    # ------------------------------------------------------------------
    # Admin: category review queue
    # ------------------------------------------------------------------

    def test_admin_approve_category_makes_it_active(self):
        _seed(self.categories_table, [
            {"slug": "fashion", "name": "Fashion", "status": "suggested", "suggested_count": 3},
        ])
        resp = self._call(method="POST", path="/api/admin/categories", body={"slug": "fashion"})
        assert resp["statusCode"] == 200
        item = self.categories_table.get_item(Key={"slug": "fashion"})["Item"]
        assert item["status"] == "active"

    def test_admin_reject_category_deletes_it(self):
        _seed(self.categories_table, [{"slug": "junk", "name": "Junk", "status": "suggested"}])
        self._call(method="DELETE", path="/api/admin/categories/junk")
        assert self.categories_table.get_item(Key={"slug": "junk"}).get("Item") is None

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
