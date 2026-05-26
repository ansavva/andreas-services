"""Routing tests for the events-api Lambda handler (lambda_function.py)."""

import json
import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.domain import events  # noqa: E402
from scout_core.handlers import api  # noqa: E402
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


def _create_settings(dynamodb):
    dynamodb.create_table(
        TableName="scout-settings",
        KeySchema=[{"AttributeName": "setting_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "setting_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _request(method, path, *, body=None, query=None):
    return api.route_request({
        "httpMethod": method,
        "path": f"/api{path}",
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
    })


def _json(response):
    return json.loads(response["body"])


@mock_dynamodb
class TestApi(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        store.reset_settings_cache()
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)

    # --- plumbing --------------------------------------------------------
    def test_cors_preflight(self):
        resp = _request("OPTIONS", "/public/events")
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(resp["headers"]["Access-Control-Allow-Origin"], "*")

    def test_unknown_endpoint_404(self):
        self.assertEqual(_request("GET", "/nope")["statusCode"], 404)

    # --- labels ----------------------------------------------------------
    def test_label_crud_via_api(self):
        created = _request("POST", "/admin/labels/event", body={"name": "Music"})
        self.assertEqual(created["statusCode"], 201)
        label_id = _json(created)["label_id"]

        listed = _json(_request("GET", "/admin/labels/event"))["labels"]
        self.assertEqual([x["name"] for x in listed], ["Music"])

        _request("DELETE", f"/admin/labels/event/{label_id}")
        self.assertEqual(_json(_request("GET", "/admin/labels/event"))["labels"], [])

    def test_unknown_taxonomy_is_400(self):
        self.assertEqual(_request("GET", "/admin/labels/bogus")["statusCode"], 400)

    # --- sources ---------------------------------------------------------
    def test_source_lifecycle_via_api(self):
        created = _request("POST", "/admin/sources", body={
            "type": "webpage", "identity": "https://x.com",
            "config": {"mode": "scheduled"}})
        self.assertEqual(created["statusCode"], 201)
        source_id = _json(created)["source_id"]

        self.assertEqual(len(_json(_request("GET", "/admin/sources"))["sources"]), 1)
        _request("POST", f"/admin/sources/{source_id}/archive", body={"archived": True})
        self.assertEqual(_json(_request("GET", "/admin/sources"))["sources"], [])
        self.assertEqual(
            len(_json(_request("GET", "/admin/sources", query={"archived": "true"}))["sources"]),
            1)

    def test_create_source_validation_error_is_400(self):
        resp = _request("POST", "/admin/sources",
                        body={"type": "webpage", "identity": "https://x.com",
                              "config": {"mode": "bogus"}})
        self.assertEqual(resp["statusCode"], 400)

    def test_delete_source_and_restore_via_api(self):
        source_id = _json(_request("POST", "/admin/sources", body={
            "type": "email", "identity": "x@y.com"}))["source_id"]
        ev = events.create_event(source_id, title="Show", start_date="2099-01-01")

        result = _json(_request("DELETE", f"/admin/sources/{source_id}"))
        self.assertEqual(result["events"], 1)
        self.assertEqual(_json(_request("GET", "/admin/sources"))["sources"], [])

        deleted = _json(_request("GET", "/admin/deleted/source"))["items"]
        self.assertEqual(len(deleted), 1)
        _request("POST", "/admin/restore",
                 body={"pk": store.source_pk(source_id), "sk": "META"})
        self.assertEqual(len(_json(_request("GET", "/admin/sources"))["sources"]), 1)
        self.assertNotIn("deleted_at", events.get_event(ev["event_id"]))

    # --- events review/publish + public feed ----------------------------
    def test_event_review_publish_and_public_feed(self):
        source_id = _json(_request("POST", "/admin/sources", body={
            "type": "email", "identity": "x@y.com"}))["source_id"]
        ev = events.create_event(source_id, title="Concert", start_date="2099-06-01")
        event_id = ev["event_id"]

        # Shows up in the admin pending queue.
        pending = _json(_request("GET", "/admin/events", query={"review": "pending"}))
        self.assertEqual([e["event_id"] for e in pending["events"]], [event_id])

        # Not yet public.
        self.assertEqual(_json(_request("GET", "/public/events"))["events"], [])

        _request("POST", f"/admin/events/{event_id}/review", body={"status": "approved"})
        _request("POST", f"/admin/events/{event_id}/publish", body={"published": True})

        feed = _json(_request("GET", "/public/events"))["events"]
        self.assertEqual([e["event_id"] for e in feed], [event_id])
        self.assertNotIn("source_id", feed[0])  # attribution stripped

        detail = _json(_request("GET", f"/public/events/{event_id}"))
        self.assertEqual(detail["title"], "Concert")

    def test_public_detail_404_when_unpublished(self):
        ev = events.create_event("s", title="Hidden", start_date="2099-01-01")
        self.assertEqual(
            _request("GET", f"/public/events/{ev['event_id']}")["statusCode"], 404)

    # --- settings --------------------------------------------------------
    def test_settings_get_and_update(self):
        defaults = _json(_request("GET", "/admin/settings"))
        self.assertEqual(defaults["link_follow_cap"], 10)
        updated = _json(_request("PUT", "/admin/settings", body={"link_follow_cap": 20}))
        self.assertEqual(updated["link_follow_cap"], 20)


if __name__ == "__main__":
    unittest.main()
