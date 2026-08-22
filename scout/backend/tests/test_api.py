"""Routing tests for the events-api Flask app."""

import json
import os
import unittest
import base64

import boto3
from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum
from moto import mock_dynamodb, mock_s3

os.environ.setdefault("SCOUT_ARTIFACTS_BUCKET", "scout-artifacts-test")

from scout_core.services import events  # noqa: E402
from scout_core.services import runs  # noqa: E402
from scout_core.app_factory import create_app  # noqa: E402
from scout_core.repositories import artifacts  # noqa: E402
from scout_core.repositories import image_store  # noqa: E402
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


def _create_settings(dynamodb):
    dynamodb.create_table(
        TableName="scout-settings",
        KeySchema=[{"AttributeName": "setting_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "setting_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _request(method, path, *, body=None, query=None):
    resp = create_app().test_client().open(
        f"/api{path}",
        method=method,
        json=body if body is not None else None,
        query_string=query,
    )
    data = resp.get_data()
    is_binary = resp.headers.get("Content-Type", "").startswith("image/")
    return {
        "statusCode": resp.status_code,
        "headers": dict(resp.headers),
        "body": base64.b64encode(data).decode() if is_binary else data.decode(),
        "isBase64Encoded": is_binary,
    }


def _lambda_request(method, path, *, body=None, with_content_length=True):
    """Drive the app the way prod does: through Mangum, off an API Gateway event.

    REST API's proxy event does not reliably carry ``Content-Length`` in
    ``headers``, and nothing downstream of it synthesises the length — which is
    what ``BodyLengthMiddleware`` exists to survive.
    """
    payload = json.dumps(body) if body is not None else ""
    headers = {"Content-Type": "application/json"}
    if with_content_length:
        headers["Content-Length"] = str(len(payload.encode()))
    event = {
        "resource": "/{proxy+}",
        "path": f"/api{path}",
        "httpMethod": method,
        "headers": headers,
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "pathParameters": {"proxy": f"api{path}"},
        "requestContext": {
            "resourcePath": "/{proxy+}",
            "httpMethod": method,
            "path": f"/prod/api{path}",
            "stage": "prod",
            "requestId": "test",
            "identity": {"sourceIp": "127.0.0.1"},
            "domainName": "events.andreas.services",
            "apiId": "test",
            "protocol": "HTTP/1.1",
        },
        "body": payload,
        "isBase64Encoded": False,
    }
    return Mangum(WsgiToAsgi(create_app()), lifespan="off")(event, None)


def _json(response):
    return json.loads(response["body"])


@mock_dynamodb
class TestApi(unittest.TestCase):
    def setUp(self):
        dynamodb_adapter._dynamodb = None
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

    def test_delete_subevent_via_api(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02")

        resp = _request("DELETE",
                        f"/admin/events/{ev['event_id']}/subevents/{sub['subevent_id']}")
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(events.list_subevents(ev["event_id"]), [])
        self.assertNotIn("deleted_at", events.get_event(ev["event_id"]))

        deleted = _json(_request("GET", "/admin/deleted/subevent"))["items"]
        self.assertEqual(len(deleted), 1)

    def test_delete_missing_subevent_is_404(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        resp = _request("DELETE", f"/admin/events/{ev['event_id']}/subevents/nope")
        self.assertEqual(resp["statusCode"], 404)

    def test_update_subevent_via_api(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02")
        resp = _request("PUT",
                        f"/admin/events/{ev['event_id']}/subevents/{sub['subevent_id']}",
                        body={"start_date": "2099-05-05", "start_time": "20:00"})
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(_json(resp)["start_date"], "2099-05-05")
        subs = events.list_subevents(ev["event_id"])
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["start_time"], "20:00")

    def test_update_missing_subevent_is_404(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        resp = _request("PUT", f"/admin/events/{ev['event_id']}/subevents/nope",
                        body={"start_time": "20:00"})
        self.assertEqual(resp["statusCode"], 404)

    # --- events review/publish + public feed ----------------------------
    def test_event_review_publish_and_public_feed(self):
        source_id = _json(_request("POST", "/admin/sources", body={
            "type": "email", "identity": "x@y.com"}))["source_id"]
        ev = events.create_event(source_id, title="Concert", start_date="2099-06-01")
        event_id = ev["event_id"]

        # Shows up in the admin pending queue (parent-centric groups).
        pending = _json(_request("GET", "/admin/events", query={"review": "pending"}))
        self.assertEqual([g["event"]["event_id"] for g in pending["groups"]], [event_id])
        self.assertTrue(pending["groups"][0]["parent_matches"])
        self.assertEqual(pending["groups"][0]["subevents"], [])

        # Not yet public.
        self.assertEqual(_json(_request("GET", "/public/events"))["events"], [])

        _request("POST", f"/admin/events/{event_id}/review", body={"status": "approved"})
        _request("POST", f"/admin/events/{event_id}/publish", body={"published": True})

        feed = _json(_request("GET", "/public/events"))["events"]
        self.assertEqual([e["event_id"] for e in feed], [event_id])
        self.assertNotIn("source_id", feed[0])  # attribution stripped

        detail = _json(_request("GET", f"/public/events/{event_id}"))
        self.assertEqual(detail["title"], "Concert")

    def test_decide_endpoint_approves_publishes_and_records_feedback(self):
        ev = events.create_event("s", title="Concert", start_date="2099-06-01")
        events.create_subevent(ev["event_id"], start_date="2099-06-02")

        result = _json(_request(
            "POST", f"/admin/events/{ev['event_id']}/decide",
            body={"decision": "approved", "feedback": "looks great"}))
        self.assertEqual(result["event"]["review_status"], "approved")
        self.assertEqual(result["event"]["publish_status"], "published")
        self.assertEqual(result["subevents"][0]["publish_status"], "published")
        self.assertEqual(result["event"]["review_feedback"][0]["text"], "looks great")

        # Now publicly visible end-to-end.
        feed = _json(_request("GET", "/public/events"))["events"]
        self.assertEqual([e["event_id"] for e in feed], [ev["event_id"]])

    def test_decide_endpoint_404_for_missing_event(self):
        resp = _request("POST", "/admin/events/nope/decide",
                        body={"decision": "approved"})
        self.assertEqual(resp["statusCode"], 404)

    def test_decide_endpoint_rejects_invalid_decision(self):
        ev = events.create_event("s", title="X", start_date="2099-06-01")
        resp = _request("POST", f"/admin/events/{ev['event_id']}/decide",
                        body={"decision": "maybe"})
        self.assertEqual(resp["statusCode"], 400)

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
        self.assertEqual(len(first["groups"]), 2)
        self.assertIsNotNone(first["next_cursor"])

        second = _json(_request("GET", "/admin/events", query={
            "review": "pending", "page_size": "2",
            "cursor": first["next_cursor"]}))
        third = _json(_request("GET", "/admin/events", query={
            "review": "pending", "page_size": "2",
            "cursor": second["next_cursor"]}))

        ids = {g["event"]["event_id"] for page in (first, second, third)
               for g in page["groups"]}
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

    def test_admin_event_images_list_approve_reject_delete(self):
        from scout_core.services import images

        ev = events.create_event("s", title="Has images", start_date="2099-01-01")
        eid = ev["event_id"]
        img = images.add_image(store.EVENT, eid, s3_ref="s3://b/p.jpg",
                               url="https://x/p.jpg", source=images.AGENT)
        iid = img["image_id"]

        # Listed for the admin with its (unapproved) state and a streamable url.
        listed = _json(_request("GET", f"/admin/events/{eid}/images"))["images"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["image_id"], iid)
        self.assertFalse(listed[0]["approved"])
        self.assertEqual(listed[0]["url"], f"/public/images/{iid}")

        # Approve → visible to the public serializer; reject → hidden again.
        approved = _json(_request("POST", f"/admin/events/{eid}/images/{iid}/approve"))
        self.assertTrue(approved["approved"])
        rejected = _json(_request("POST", f"/admin/events/{eid}/images/{iid}/reject"))
        self.assertFalse(rejected["approved"])

        # Delete drops the record entirely.
        self.assertEqual(
            _request("DELETE", f"/admin/events/{eid}/images/{iid}")["statusCode"], 200)
        self.assertEqual(_json(_request("GET", f"/admin/events/{eid}/images"))["images"], [])

    def test_admin_event_images_404_when_event_missing(self):
        self.assertEqual(
            _request("GET", "/admin/events/nope/images")["statusCode"], 404)

    def test_settings_get_and_update(self):
        defaults = _json(_request("GET", "/admin/settings"))
        self.assertEqual(defaults["link_follow_cap"], 10)
        updated = _json(_request("PUT", "/admin/settings", body={"link_follow_cap": 20}))
        self.assertEqual(updated["link_follow_cap"], 20)

    # --- the Lambda path -------------------------------------------------
    def test_write_survives_an_event_without_content_length(self):
        # The header is what asgiref turns into CONTENT_LENGTH; without it
        # Werkzeug reads a zero-byte body and the route 400s on its own field.
        created = _lambda_request(
            "POST", "/admin/labels/event",
            body={"name": "Music"}, with_content_length=False)
        self.assertEqual(created["statusCode"], 201)
        self.assertEqual(json.loads(created["body"])["name"], "Music")

    def test_write_still_works_when_content_length_is_present(self):
        created = _lambda_request(
            "POST", "/admin/labels/event", body={"name": "Theatre"})
        self.assertEqual(created["statusCode"], 201)
        self.assertEqual(json.loads(created["body"])["name"], "Theatre")


if __name__ == "__main__":
    unittest.main()
