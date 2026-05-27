"""
Integration tests for the Scout events API.

These tests hit a live API Gateway endpoint and require the SCOUT_API_URL
environment variable to be set to the API base URL (including the /api
prefix, without trailing slash), e.g.:
  SCOUT_API_URL=https://scout-api.andreas.services/api
  SCOUT_API_URL=https://scout-api-pr.andreas.services/42/api

Run after deploying an ephemeral PR stack:
  SCOUT_API_URL=<url> pytest scout/tests/integration/

They exercise the public read surface (consumed by the UI) and confirm the
admin subtree is gated by the Cognito authorizer. A freshly deployed PR stack
has an empty scout-core table, so the feed-shape assertions are written to hold
whether or not any events are present.
"""

import os

import pytest
import requests

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

API_URL = os.environ.get("SCOUT_API_URL", "").rstrip("/")


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
# GET /public/events — the paginated public feed
# ------------------------------------------------------------------

class TestPublicEvents:

    def test_returns_200(self):
        resp = get("/public/events")
        assert resp.status_code == 200

    def test_response_is_json_object(self):
        data = get("/public/events").json()
        assert isinstance(data, dict)

    def test_has_events_total_and_cursor(self):
        data = get("/public/events").json()
        assert "events" in data
        assert "total" in data
        assert "next_cursor" in data

    def test_events_is_a_list(self):
        assert isinstance(get("/public/events").json()["events"], list)

    def test_total_is_int(self):
        assert isinstance(get("/public/events").json()["total"], int)

    def test_cors_header_present(self):
        resp = get("/public/events")
        assert "access-control-allow-origin" in {k.lower() for k in resp.headers}

    def test_filters_are_accepted(self):
        resp = get("/public/events", params={"q": "music", "sort": "date"})
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_event_items_have_required_fields(self):
        for event in get("/public/events").json()["events"]:
            assert "event_id" in event, f"Missing event_id in {event}"
            assert "title" in event, f"Missing title in {event}"
            assert "sub_events" in event, f"Missing sub_events in {event}"


# ------------------------------------------------------------------
# GET /public/events/{id}
# ------------------------------------------------------------------

class TestPublicEventById:

    def test_known_id_returns_200(self):
        events = get("/public/events").json().get("events", [])
        if not events:
            pytest.skip("No events in the table — skipping by-ID test")
        event_id = events[0]["event_id"]
        resp = get(f"/public/events/{event_id}")
        assert resp.status_code == 200
        assert resp.json()["event_id"] == event_id

    def test_unknown_id_returns_404(self):
        resp = get("/public/events/does-not-exist-xyz-999")
        assert resp.status_code == 404


# ------------------------------------------------------------------
# GET /public/facets — filter options
# ------------------------------------------------------------------

class TestPublicFacets:

    def test_returns_200(self):
        assert get("/public/facets").status_code == 200

    def test_has_facet_lists(self):
        data = get("/public/facets").json()
        assert isinstance(data.get("locations"), list)
        assert isinstance(data.get("event_labels"), list)
        assert isinstance(data.get("location_labels"), list)


# ------------------------------------------------------------------
# CORS preflight on the public surface
# ------------------------------------------------------------------

class TestCors:

    def test_options_returns_200(self):
        assert options("/public/events").status_code == 200

    def test_options_has_allow_origin(self):
        resp = options("/public/events")
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert "access-control-allow-origin" in headers_lower


# ------------------------------------------------------------------
# Admin routes are protected by the Cognito authorizer
# ------------------------------------------------------------------

class TestAdminAuth:
    """
    The /api/admin/* subtree sits behind a Cognito authorizer, so
    unauthenticated requests must be rejected. CORS preflight (OPTIONS) stays
    open so the browser can negotiate before attaching the token.
    """

    def test_admin_sources_requires_auth(self):
        assert get("/admin/sources").status_code in (401, 403)

    def test_admin_events_requires_auth(self):
        assert get("/admin/events").status_code in (401, 403)

    def test_admin_settings_requires_auth(self):
        assert get("/admin/settings").status_code in (401, 403)

    def test_admin_options_preflight_is_open(self):
        assert options("/admin/sources").status_code == 200


# ------------------------------------------------------------------
# Error cases
# ------------------------------------------------------------------

class TestErrorCases:

    def test_nonexistent_path_returns_404(self):
        assert get("/does-not-exist").status_code == 404
