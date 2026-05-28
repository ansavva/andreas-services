"""Routing tests for the events-api Lambda handler (lambda_function.py)."""

import json
import os
import unittest

import boto3
from moto import mock_dynamodb, mock_s3

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")
os.environ.setdefault("SCOUT_ARTIFACTS_BUCKET", "scout-artifacts-test")

from scout_core.domain import events  # noqa: E402
from scout_core.domain import runs  # noqa: E402
from scout_core.handlers import api  # noqa: E402
from scout_core.adapters import artifacts  # noqa: E402
from scout_core.adapters import image_store  # noqa: E402
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

    def test_admin_preview_renders_unpublished_event(self):
        ev = events.create_event("s", title="Draft", start_date="2099-01-01",
                                 description="Not live yet")
        # Public detail is hidden, but the admin preview returns the page shape.
        self.assertEqual(
            _request("GET", f"/public/events/{ev['event_id']}")["statusCode"], 404)
        detail = _json(_request("GET", f"/admin/events/{ev['event_id']}/preview"))
        self.assertEqual(detail["title"], "Draft")
        self.assertEqual(detail["description"], "Not live yet")

    def test_admin_preview_404_when_missing(self):
        self.assertEqual(
            _request("GET", "/admin/events/nope/preview")["statusCode"], 404)

    # --- settings --------------------------------------------------------
    def test_sources_list_flags_in_progress_runs(self):
        source_id = _json(_request("POST", "/admin/sources", body={
            "type": "email", "identity": "x@y.com"}))["source_id"]

        listed = _json(_request("GET", "/admin/sources"))["sources"]
        self.assertEqual([s["running"] for s in listed], [False])

        run = runs.start_run(source_id, runs.TRIGGER_MANUAL)
        listed = _json(_request("GET", "/admin/sources"))["sources"]
        self.assertTrue(listed[0]["running"])

        runs.finish_run(source_id, run["run_id"], status=runs.SUCCESS, events_count=2)
        listed = _json(_request("GET", "/admin/sources"))["sources"]
        self.assertFalse(listed[0]["running"])

    @mock_s3
    def test_run_artifact_streams_in_utf8_safe_chunks(self):
        artifacts._s3 = None
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket="scout-artifacts-test")
        # Mix ASCII and a 4-byte UTF-8 char (😀) so a naïve byte cut would
        # split the emoji mid-character.
        body = ("a" * 100 + "\U0001F600" + "b" * 100)
        source_id = _json(_request("POST", "/admin/sources", body={
            "type": "email", "identity": "x@y.com"}))["source_id"]
        run = runs.start_run(source_id, runs.TRIGGER_MANUAL)
        ref = artifacts.store_transcript(source_id, run["run_id"], body)
        runs.set_artifacts(source_id, run["run_id"], transcript=ref)

        path = f"/admin/sources/{source_id}/runs/{run['run_id']}/artifact"
        # Tiny chunks force multiple round-trips that straddle the emoji bytes.
        accumulated = ""
        offset = 0
        for _ in range(50):
            page = _json(_request("GET", path, query={
                "kind": "transcript", "offset": str(offset), "chunk_size": "32"}))
            accumulated += page["content"]
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        self.assertEqual(accumulated, body)

        missing = _request("GET", path, query={"kind": "root_body"})
        self.assertEqual(missing["statusCode"], 404)

    def test_sources_running_endpoint(self):
        source_id = _json(_request("POST", "/admin/sources", body={
            "type": "email", "identity": "x@y.com"}))["source_id"]
        empty = _json(_request("GET", "/admin/sources/running"))
        self.assertEqual(empty["running"], [])

        run = runs.start_run(source_id, runs.TRIGGER_MANUAL)
        listed = _json(_request("GET", "/admin/sources/running"))
        self.assertEqual(listed["running"], [source_id])

        runs.finish_run(source_id, run["run_id"], status=runs.SUCCESS)
        cleared = _json(_request("GET", "/admin/sources/running"))
        self.assertEqual(cleared["running"], [])

    def test_event_review_pagination_walks_all_rows(self):
        for i in range(5):
            events.create_event("s", title=f"E{i}", start_date="2099-01-01")

        first = _json(_request("GET", "/admin/events", query={
            "review": "pending", "page_size": "2"}))
        self.assertEqual(len(first["events"]), 2)
        self.assertIsNotNone(first["next_cursor"])

        second = _json(_request("GET", "/admin/events", query={
            "review": "pending", "page_size": "2",
            "cursor": first["next_cursor"]}))
        third = _json(_request("GET", "/admin/events", query={
            "review": "pending", "page_size": "2",
            "cursor": second["next_cursor"]}))

        ids = {e["event_id"] for page in (first, second, third)
               for e in page["events"]}
        self.assertEqual(len(ids), 5)
        self.assertIsNone(third["next_cursor"])

    def test_runs_list_includes_artifact_urls(self):
        source_id = _json(_request("POST", "/admin/sources", body={
            "type": "email", "identity": "x@y.com"}))["source_id"]
        run = runs.start_run(source_id, runs.TRIGGER_MANUAL)
        runs.set_artifacts(source_id, run["run_id"],
                           transcript="s3://b/transcript.json")
        runs.finish_run(source_id, run["run_id"], status=runs.SUCCESS)

        os.environ["SCOUT_PUBLIC_API_URL"] = "https://api.example/api"
        try:
            page = _json(_request("GET", f"/admin/sources/{source_id}/runs"))
        finally:
            del os.environ["SCOUT_PUBLIC_API_URL"]

        self.assertEqual(len(page["runs"]), 1)
        kinds = [a["kind"] for a in page["runs"][0]["artifacts"]]
        self.assertEqual(kinds, ["transcript"])
        url = page["runs"][0]["artifacts"][0]["url"]
        self.assertTrue(url.startswith("https://api.example/api/admin/sources/"))
        self.assertIn("kind=transcript", url)

    @mock_s3
    def test_public_image_streams_stored_bytes(self):
        image_store._s3 = None
        os.environ["SCOUT_IMAGES_BUCKET"] = "scout-images-test"
        boto3.client("s3", region_name="us-east-1").create_bucket(
            Bucket="scout-images-test")
        try:
            image_store.put_bytes("img-abc", b"\x89PNG\r\n", "image/png")
            resp = _request("GET", "/public/images/img-abc")
            self.assertEqual(resp["statusCode"], 200)
            self.assertEqual(resp["headers"]["Content-Type"], "image/png")
            self.assertTrue(resp["isBase64Encoded"])

            missing = _request("GET", "/public/images/nope")
            self.assertEqual(missing["statusCode"], 404)
        finally:
            del os.environ["SCOUT_IMAGES_BUCKET"]

    def test_settings_get_and_update(self):
        defaults = _json(_request("GET", "/admin/settings"))
        self.assertEqual(defaults["link_follow_cap"], 10)
        updated = _json(_request("PUT", "/admin/settings", body={"link_follow_cap": 20}))
        self.assertEqual(updated["link_follow_cap"], 20)


if __name__ == "__main__":
    unittest.main()
