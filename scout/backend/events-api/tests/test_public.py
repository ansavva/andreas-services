"""Unit tests for the public read/query layer (public.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.domain import events  # noqa: E402
from scout_core.domain import labels  # noqa: E402
from scout_core.domain import locations  # noqa: E402
from scout_core.domain import public  # noqa: E402
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


def _publish(event_id):
    events.set_review(event_id, events.REVIEW_APPROVED)
    events.set_publish(event_id, True)


@mock_dynamodb
class TestPublic(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        store.reset_settings_cache()
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)

    def _feed_ids(self, **kwargs):
        return [e["event_id"] for e in public.feed(**kwargs)["events"]]

    def test_only_published_future_events_are_visible(self):
        published = events.create_event("s", title="Live", start_date="2099-01-01")
        _publish(published["event_id"])
        events.create_event("s", title="Pending", start_date="2099-01-01")
        past = events.create_event("s", title="Past", start_date="2000-01-01")
        _publish(past["event_id"])

        ids = self._feed_ids()
        self.assertEqual(ids, [published["event_id"]])  # not pending, not past

    def test_serialization_strips_source_attribution(self):
        ev = events.create_event("secret-source", title="Show",
                                 start_date="2099-01-01", description="desc")
        _publish(ev["event_id"])
        serialized = public.feed()["events"][0]
        self.assertNotIn("source_id", serialized)
        self.assertEqual(serialized["title"], "Show")
        self.assertEqual(serialized["description"], "desc")

    def test_and_only_label_filtering(self):
        music = labels.create_label(store.EVENT_LABEL, "music")
        free = labels.create_label(store.EVENT_LABEL, "free")
        both = events.create_event("s", title="Both", start_date="2099-01-01",
                                   event_label_ids=[music["label_id"], free["label_id"]])
        only_music = events.create_event("s", title="Music", start_date="2099-01-01",
                                         event_label_ids=[music["label_id"]])
        _publish(both["event_id"])
        _publish(only_music["event_id"])

        # Requiring both labels (AND) yields only the event that has both.
        ids = self._feed_ids(event_label_ids=[music["label_id"], free["label_id"]])
        self.assertEqual(ids, [both["event_id"]])

    def test_inherited_location_label_filtering(self):
        loc = locations.create_location("Park")
        outdoor = labels.create_label(store.LOCATION_LABEL, "outdoor")
        labels.attach_label(store.LOCATION_LABEL, outdoor["label_id"],
                            store.LOCATION, loc["location_id"])
        ev = events.create_event("s", title="Picnic", start_date="2099-01-01",
                                 location_id=loc["location_id"])
        _publish(ev["event_id"])
        other = events.create_event("s", title="Indoor", start_date="2099-01-01")
        _publish(other["event_id"])

        ids = self._feed_ids(location_label_ids=[outdoor["label_id"]])
        self.assertEqual(ids, [ev["event_id"]])

    def test_search_matches_title_and_location_name(self):
        loc = locations.create_location("Blue Note")
        a = events.create_event("s", title="Jazz Evening", start_date="2099-01-01",
                                location_id=loc["location_id"])
        b = events.create_event("s", title="Rock Show", start_date="2099-01-01")
        _publish(a["event_id"])
        _publish(b["event_id"])

        self.assertEqual(self._feed_ids(search="jazz"), [a["event_id"]])
        self.assertEqual(self._feed_ids(search="blue note"), [a["event_id"]])

    def test_pagination(self):
        for i in range(3):
            ev = events.create_event("s", title=f"E{i}", start_date=f"2099-01-0{i + 1}")
            _publish(ev["event_id"])
        first = public.feed(page_size=2)
        self.assertEqual(len(first["events"]), 2)
        self.assertIsNotNone(first["next_cursor"])
        second = public.feed(page_size=2, cursor=first["next_cursor"])
        self.assertEqual(len(second["events"]), 1)
        self.assertIsNone(second["next_cursor"])

    def test_event_detail_nests_visible_subs(self):
        ev = events.create_event("s", title="Tour", start_date="2099-01-01")
        _publish(ev["event_id"])
        sub = events.create_subevent(ev["event_id"], start_date="2099-02-01",
                                     publish_status=events.PUBLISHED)
        # Past + cancelled subs are excluded.
        events.create_subevent(ev["event_id"], start_date="2000-01-01",
                               publish_status=events.PUBLISHED)

        detail = public.event_detail(ev["event_id"])
        self.assertEqual([s["subevent_id"] for s in detail["sub_events"]],
                         [sub["subevent_id"]])
        self.assertFalse(detail["no_upcoming_dates"])

    def test_parent_with_no_visible_subs_shows_no_upcoming_dates(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        _publish(ev["event_id"])
        # Only a past sub-event exists.
        events.create_subevent(ev["event_id"], start_date="2000-01-01",
                               publish_status=events.PUBLISHED)
        detail = public.event_detail(ev["event_id"])
        self.assertTrue(detail["no_upcoming_dates"])
        self.assertEqual(detail["sub_events"], [])

    def test_event_detail_includes_event_url(self):
        ev = events.create_event("s", title="Linked", start_date="2099-01-01",
                                 event_url="https://venue.test/gig")
        _publish(ev["event_id"])
        detail = public.event_detail(ev["event_id"])
        self.assertEqual(detail["event_url"], "https://venue.test/gig")

    def test_event_detail_event_url_none_when_absent(self):
        ev = events.create_event("s", title="No Link", start_date="2099-01-01")
        _publish(ev["event_id"])
        detail = public.event_detail(ev["event_id"])
        self.assertIsNone(detail["event_url"])

    def test_unpublished_event_detail_is_none(self):
        ev = events.create_event("s", title="Hidden", start_date="2099-01-01")
        self.assertIsNone(public.event_detail(ev["event_id"]))

    def test_preview_renders_unpublished_event_with_all_subs(self):
        ev = events.create_event("s", title="Draft", start_date="2099-01-01",
                                 description="A pending event")
        # Unpublished + past sub-events that the public detail would hide.
        future = events.create_subevent(ev["event_id"], start_date="2099-02-01")
        past = events.create_subevent(ev["event_id"], start_date="2000-01-01")

        detail = public.preview_detail(ev["event_id"])
        self.assertEqual(detail["title"], "Draft")
        self.assertEqual(detail["description"], "A pending event")
        self.assertFalse(detail["no_upcoming_dates"])
        self.assertEqual([s["subevent_id"] for s in detail["sub_events"]],
                         [past["subevent_id"], future["subevent_id"]])

    def test_preview_of_missing_event_is_none(self):
        self.assertIsNone(public.preview_detail("does-not-exist"))

    def test_preview_includes_unapproved_images(self):
        from scout_core.domain import images  # noqa: PLC0415

        ev = events.create_event("s", title="Draft", start_date="2099-01-01")
        # Agent images land unapproved with the bytes already stored under
        # their image_id; they should still appear in preview so admins see
        # what the page will look like before approval.
        image = images.add_image(
            store.EVENT, ev["event_id"],
            url="https://example.com/a.png", s3_ref="s3://b/images/x",
            source=images.AGENT)

        public_detail = public.event_detail(ev["event_id"])  # not yet published
        self.assertIsNone(public_detail)

        # After publishing, the public detail still hides unapproved images.
        _publish(ev["event_id"])
        published = public.event_detail(ev["event_id"])
        self.assertEqual(published["images"], [])

        # Preview surfaces them regardless of approval, via the our-domain URL.
        preview = public.preview_detail(ev["event_id"])
        self.assertEqual(len(preview["images"]), 1)
        self.assertEqual(
            preview["images"][0]["url"],
            f"/public/images/{image['image_id']}",
        )

    def test_facets_only_reflect_visible_events(self):
        loc = locations.create_location("Venue")
        music = labels.create_label(store.EVENT_LABEL, "music")
        ev = events.create_event("s", title="Show", start_date="2099-01-01",
                                 location_id=loc["location_id"],
                                 event_label_ids=[music["label_id"]])
        _publish(ev["event_id"])
        # An unpublished event whose label should NOT appear in facets.
        hidden_label = labels.create_label(store.EVENT_LABEL, "hidden")
        events.create_event("s", title="Hidden", start_date="2099-01-01",
                            event_label_ids=[hidden_label["label_id"]])

        result = public.facets()
        self.assertEqual([loc_["id"] for loc_ in result["locations"]],
                         [loc["location_id"]])
        self.assertEqual([x["name"] for x in result["event_labels"]], ["music"])


if __name__ == "__main__":
    unittest.main()
