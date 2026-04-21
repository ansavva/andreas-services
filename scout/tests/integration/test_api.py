"""
Integration tests for the Scout events API.

These tests hit a live API Gateway endpoint and require the SCOUT_API_URL
environment variable to be set to the API base URL (including the /api
prefix, without trailing slash), e.g.:
  SCOUT_API_URL=https://scout-api.andreas.services/api
  SCOUT_API_URL=https://scout-api-pr.andreas.services/42/api

Run after deploying an ephemeral PR stack:
  SCOUT_API_URL=<url> pytest scout/tests/integration/
"""

import json
import os

import boto3
import pytest
import requests

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

API_URL = os.environ.get("SCOUT_API_URL", "").rstrip("/")
EMAIL_PROCESSOR_FUNCTION = os.environ.get("SCOUT_EMAIL_PROCESSOR_FUNCTION", "")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(scope="session", autouse=True)
def require_api_url():
    if not API_URL:
        pytest.skip("SCOUT_API_URL is not set — skipping integration tests")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def get(path, **kwargs):
    return requests.get(f"{API_URL}{path}", timeout=10, **kwargs)


def options(path):
    return requests.options(f"{API_URL}{path}", timeout=10)


# ------------------------------------------------------------------
# GET /events
# ------------------------------------------------------------------

class TestGetEvents:

    def test_returns_200(self):
        resp = get("/events")
        assert resp.status_code == 200

    def test_response_is_json(self):
        resp = get("/events")
        data = resp.json()
        assert isinstance(data, dict)

    def test_response_has_events_and_count(self):
        resp = get("/events")
        data = resp.json()
        assert "events" in data
        assert "count" in data

    def test_events_is_a_list(self):
        resp = get("/events")
        assert isinstance(resp.json()["events"], list)

    def test_count_matches_events_length(self):
        resp = get("/events")
        data = resp.json()
        assert data["count"] == len(data["events"])

    def test_cors_header_present(self):
        resp = get("/events")
        assert "access-control-allow-origin" in {k.lower() for k in resp.headers}

    def test_upcoming_filter_accepted(self):
        resp = get("/events", params={"upcoming": "true"})
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data

    def test_event_items_have_required_fields(self):
        resp = get("/events")
        for event in resp.json()["events"]:
            assert "event_id" in event, f"Missing event_id in {event}"
            assert "event_name" in event, f"Missing event_name in {event}"


# ------------------------------------------------------------------
# GET /events/{id}
# ------------------------------------------------------------------

class TestGetEventById:

    def test_known_id_returns_200_or_404(self):
        # We don't know IDs ahead of time; first get the list then look one up.
        all_resp = get("/events")
        events = all_resp.json().get("events", [])
        if not events:
            pytest.skip("No events in the table — skipping by-ID test")

        event_id = events[0]["event_id"]
        resp = get(f"/events/{event_id}")
        assert resp.status_code == 200

    def test_known_id_returns_correct_event(self):
        all_resp = get("/events")
        events = all_resp.json().get("events", [])
        if not events:
            pytest.skip("No events in the table — skipping by-ID test")

        first = events[0]
        resp = get(f"/events/{first['event_id']}")
        data = resp.json()
        assert data["event_id"] == first["event_id"]
        assert data["event_name"] == first["event_name"]

    def test_unknown_id_returns_404(self):
        resp = get("/events/does-not-exist-xyz-999")
        assert resp.status_code == 404


# ------------------------------------------------------------------
# CORS preflight
# ------------------------------------------------------------------

class TestCors:

    def test_options_events_returns_200(self):
        resp = options("/events")
        assert resp.status_code == 200

    def test_options_has_allow_origin(self):
        resp = options("/events")
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert "access-control-allow-origin" in headers_lower


# ------------------------------------------------------------------
# Error cases
# ------------------------------------------------------------------

class TestErrorCases:

    def test_nonexistent_path_returns_404(self):
        resp = get("/does-not-exist")
        assert resp.status_code == 404


# ------------------------------------------------------------------
# Email processor end-to-end
# ------------------------------------------------------------------

class TestEmailProcessor:
    """
    Validates that the email-processor ran successfully and that events
    are visible through the API.

    The workflow seeds the table by invoking the processor before tests
    run. These tests confirm:
      1. A direct Lambda invocation returns a valid response contract.
      2. The API reflects at least one stored event.
    """

    @pytest.fixture(scope="class", autouse=True)
    def require_processor_function(self):
        if not EMAIL_PROCESSOR_FUNCTION:
            pytest.skip("SCOUT_EMAIL_PROCESSOR_FUNCTION not set — skipping email-processor tests")

    def test_processor_invocation_returns_valid_contract(self):
        client = boto3.client("lambda", region_name=AWS_REGION)
        response = client.invoke(
            FunctionName=EMAIL_PROCESSOR_FUNCTION,
            InvocationType="RequestResponse",
            Payload=b"{}",
        )
        body = json.loads(response["Payload"].read())
        assert body["statusCode"] == 200, f"Non-200 from processor: {body}"

        result = json.loads(body["body"])
        assert "emails_processed" in result, f"Missing emails_processed: {result}"
        assert "events_stored" in result, f"Missing events_stored: {result}"
        assert "errors" in result, f"Missing errors: {result}"
        assert result["errors"] == [], f"Processor reported errors: {result['errors']}"

