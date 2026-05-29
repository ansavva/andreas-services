"""Unit tests for the event/sub-event service layer (events.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.domain import events  # noqa: E402
from scout_core.domain import images  # noqa: E402
from scout_core.domain import labels  # noqa: E402
from scout_core.domain import locations  # noqa: E402
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


def _pubvis_ids():
    return {i.get("event_id") or i.get("subevent_id")
            for i in store.query_index_all("GSI1", "PUBVIS", live_only=True)}


@mock_dynamodb
class TestEvents(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        store.reset_settings_cache()
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)

    # --- creation & review queue ----------------------------------------
    def test_create_event_pending_unpublished(self):
        ev = events.create_event("src1", title="Show", start_date="2099-01-01")
        self.assertEqual(ev["review_status"], "pending")
        self.assertEqual(ev["publish_status"], "unpublished")
        self.assertFalse(ev["past"])
        # In the pending review queue, not in public visibility.
        pending = events.list_by_review("pending")
        self.assertEqual([e["event_id"] for e in pending], [ev["event_id"]])
        self.assertNotIn(ev["event_id"], _pubvis_ids())

    def test_review_transition_moves_queue(self):
        ev = events.create_event("src1", title="Show", start_date="2099-01-01")
        events.set_review(ev["event_id"], events.REVIEW_APPROVED)
        self.assertEqual(events.list_by_review("pending"), [])
        self.assertEqual(len(events.list_by_review("approved")), 1)

    def test_bulk_review(self):
        ids = [events.create_event("s", title=f"E{i}", start_date="2099-01-01")["event_id"]
               for i in range(3)]
        events.bulk_review(ids, events.REVIEW_APPROVED)
        self.assertEqual(len(events.list_by_review("approved")), 3)

    def test_review_groups_nest_occurrences_under_parent(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02")

        groups, _ = events.list_review_groups("pending")
        self.assertEqual(len(groups), 1)  # one parent, no standalone occurrence row
        self.assertEqual(groups[0]["event"]["event_id"], ev["event_id"])
        self.assertTrue(groups[0]["parent_matches"])
        self.assertEqual([s["subevent_id"] for s in groups[0]["subevents"]],
                         [sub["subevent_id"]])

    def test_review_groups_show_divergent_parent_as_context(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        events.create_subevent(ev["event_id"], start_date="2099-01-02")
        # Approve the parent; its occurrence stays pending.
        events.set_review(ev["event_id"], events.REVIEW_APPROVED)

        # Pending tab still surfaces the parent (for context) with its occurrence,
        # but flagged not-matching so the UI renders it muted / non-actionable.
        pending, _ = events.list_review_groups("pending")
        self.assertEqual([g["event"]["event_id"] for g in pending], [ev["event_id"]])
        self.assertFalse(pending[0]["parent_matches"])
        self.assertEqual(len(pending[0]["subevents"]), 1)

        # Approved tab shows the same parent, now actionable, with all occurrences.
        approved, _ = events.list_review_groups("approved")
        self.assertEqual([g["event"]["event_id"] for g in approved], [ev["event_id"]])
        self.assertTrue(approved[0]["parent_matches"])
        self.assertEqual(len(approved[0]["subevents"]), 1)

    # --- swipe decision (review + publish in one) -----------------------
    def test_approve_decision_publishes_event_and_all_occurrences(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02")

        result = events.review_with_feedback(ev["event_id"], events.REVIEW_APPROVED)
        self.assertEqual(result["event"]["review_status"], "approved")
        self.assertEqual(result["event"]["publish_status"], "published")
        self.assertEqual(result["subevents"][0]["review_status"], "approved")
        self.assertEqual(result["subevents"][0]["publish_status"], "published")
        # Both parent and occurrence are now publicly visible.
        self.assertEqual(_pubvis_ids(), {ev["event_id"], sub["subevent_id"]})

    def test_reject_decision_unpublishes_event_and_all_occurrences(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02")
        events.review_with_feedback(ev["event_id"], events.REVIEW_APPROVED)
        self.assertEqual(_pubvis_ids(), {ev["event_id"], sub["subevent_id"]})

        # Changing the mind: reject flips status and pulls everything offline.
        result = events.review_with_feedback(ev["event_id"], events.REVIEW_REJECTED)
        self.assertEqual(result["event"]["review_status"], "rejected")
        self.assertEqual(result["event"]["publish_status"], "unpublished")
        self.assertEqual(result["subevents"][0]["review_status"], "rejected")
        self.assertEqual(_pubvis_ids(), set())

    def test_decision_rejects_invalid_value_and_missing_event(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        with self.assertRaises(ValueError):
            events.review_with_feedback(ev["event_id"], "pending")
        self.assertIsNone(events.review_with_feedback("nope", events.REVIEW_APPROVED))

    def test_feedback_history_appends_in_order(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        events.review_with_feedback(ev["event_id"], events.REVIEW_REJECTED,
                                    feedback="too vague", author="a@b.com")
        events.review_with_feedback(ev["event_id"], events.REVIEW_APPROVED,
                                    feedback="fixed up")
        notes = events.get_event(ev["event_id"])["review_feedback"]
        self.assertEqual([n["text"] for n in notes], ["too vague", "fixed up"])
        self.assertEqual([n["decision"] for n in notes], ["rejected", "approved"])
        self.assertEqual(notes[0]["author"], "a@b.com")
        self.assertNotIn("author", notes[1])

    # --- publish / visibility -------------------------------------------
    def test_publish_adds_to_pubvis_unpublish_removes(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        events.set_publish(ev["event_id"], True)
        self.assertIn(ev["event_id"], _pubvis_ids())
        events.set_publish(ev["event_id"], False)
        self.assertNotIn(ev["event_id"], _pubvis_ids())

    def test_cancel_clears_visibility_and_cascades_to_subs(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        events.set_publish(ev["event_id"], True)
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02",
                                     publish_status=events.PUBLISHED)
        # Parent published -> sub can be visible.
        self.assertIn(sub["subevent_id"], _pubvis_ids())

        events.cancel_event(ev["event_id"])
        self.assertNotIn(ev["event_id"], _pubvis_ids())
        self.assertNotIn(sub["subevent_id"], _pubvis_ids())
        refreshed_sub = events._get_sub(ev["event_id"], sub["subevent_id"])
        self.assertTrue(refreshed_sub["lifecycle_cancelled"])

    # --- sub-events: publishing dependency ------------------------------
    def test_sub_cannot_publish_while_parent_unpublished(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02")
        with self.assertRaises(ValueError):
            events.set_subevent_publish(ev["event_id"], sub["subevent_id"], True)

    def test_unpublishing_parent_hides_subs(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        events.set_publish(ev["event_id"], True)
        sub = events.create_subevent(ev["event_id"], start_date="2099-01-02",
                                     publish_status=events.PUBLISHED)
        self.assertIn(sub["subevent_id"], _pubvis_ids())
        events.set_publish(ev["event_id"], False)
        self.assertNotIn(sub["subevent_id"], _pubvis_ids())

    # --- inheritance & overrides ----------------------------------------
    def test_inheritance_and_overrides(self):
        loc = locations.create_location("Parent Venue", timezone="UTC")
        loc2 = locations.create_location("Override Venue", timezone="UTC")
        plabel = labels.create_label(store.EVENT_LABEL, "music")
        loclabel = labels.create_label(store.LOCATION_LABEL, "outdoor")
        labels.attach_label(store.LOCATION_LABEL, loclabel["label_id"],
                            store.LOCATION, loc["location_id"])

        ev = events.create_event("s", title="Show", start_date="2099-01-01",
                                 location_id=loc["location_id"],
                                 event_label_ids=[plabel["label_id"]])
        inheriting = events.create_subevent(ev["event_id"], start_date="2099-01-02")
        overriding = events.create_subevent(
            ev["event_id"], start_date="2099-01-03",
            location_id_override=loc2["location_id"], event_label_ids=[])

        # Inheriting sub picks up the parent's location, event-labels and the
        # location's labels.
        self.assertEqual(events.effective_location_id(ev, inheriting), loc["location_id"])
        self.assertEqual(events.effective_event_label_ids(ev, inheriting),
                         [plabel["label_id"]])
        self.assertEqual(events.effective_location_label_ids(ev, inheriting),
                         [loclabel["label_id"]])
        # Overriding sub replaces location (new location has no labels) and
        # short-circuits event-label inheritance (explicit empty override).
        self.assertEqual(events.effective_location_id(ev, overriding), loc2["location_id"])
        self.assertEqual(events.effective_event_label_ids(ev, overriding), [])
        self.assertEqual(events.effective_location_label_ids(ev, overriding), [])

    # --- dedup / re-extraction ------------------------------------------
    def test_convert_extraction_dedupes_repeat_runs(self):
        from unittest.mock import patch  # noqa: PLC0415
        from scout_core.adapters import image_store as _image_store  # noqa: PLC0415

        extracted = [{
            "title": "Jazz Night", "start_date": "2099-05-01",
            "description": "x", "event_labels": ["jazz"],
            "location": {"name": "Blue Note", "timezone": "UTC"},
            "images": ["https://x/a.jpg"], "sub_events": [],
        }]
        # Stub the image download so the agent image gets stored with an s3_ref.
        with patch.object(_image_store, "download",
                          return_value=(b"\x89PNG", "image/png")), \
                patch.object(_image_store, "put_bytes",
                             return_value="s3://b/images/x"):
            first = events.convert_extraction("s", extracted)
        self.assertEqual(first["created"], 1)
        # Agent image attached pending approval.
        imgs = images.list_images(store.EVENT, first["event_ids"][0])
        self.assertEqual(len(imgs), 1)
        self.assertFalse(imgs[0]["approved"])

        # Re-running the same extraction creates nothing (duplicate).
        second = events.convert_extraction("s", extracted)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skipped"], 1)

    def test_rejected_duplicate_is_not_recreated(self):
        extracted = [{"title": "Gig", "start_date": "2099-05-01",
                      "location": None, "event_labels": [], "sub_events": []}]
        result = events.convert_extraction("s", extracted)
        events.set_review(result["event_ids"][0], events.REVIEW_REJECTED)
        again = events.convert_extraction("s", extracted)
        self.assertEqual(again["created"], 0)
        # The rejected event was not resurrected.
        self.assertEqual(len(events.list_by_review("rejected")), 1)
        self.assertEqual(events.list_by_review("pending"), [])

    def test_convert_creates_subevents(self):
        extracted = [{
            "title": "Tour", "start_date": "2099-05-01", "location": None,
            "event_labels": [], "images": [],
            "sub_events": [
                {"start_date": "2099-05-01"},
                {"start_date": "2099-05-02"},
            ],
        }]
        result = events.convert_extraction("s", extracted)
        subs = events.list_subevents(result["event_ids"][0])
        self.assertEqual(len(subs), 2)

    def test_convert_extraction_downloads_agent_image_bytes(self):
        from unittest.mock import patch  # noqa: PLC0415
        from scout_core.adapters import image_store  # noqa: PLC0415
        from scout_core.domain import images  # noqa: PLC0415

        extracted = [{
            "title": "With Image", "start_date": "2099-07-01", "location": None,
            "event_labels": [], "images": ["https://example.com/p.png"],
            "sub_events": [],
        }]
        # Stub the downloader; assert the image record picks up the s3_ref.
        with patch.object(image_store, "download",
                          return_value=(b"\x89PNG\r\n", "image/png")), \
                patch.object(image_store, "put_bytes",
                             return_value="s3://b/images/abc") as put_mock:
            result = events.convert_extraction("s", extracted)
        event_id = result["event_ids"][0]
        stored = images.list_images(store.EVENT, event_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["s3_ref"], "s3://b/images/abc")
        # The image_id passed to put_bytes is what the public route uses.
        put_mock.assert_called_once_with(stored[0]["image_id"],
                                         b"\x89PNG\r\n", "image/png")

    def test_convert_extraction_drops_image_when_download_fails(self):
        from unittest.mock import patch  # noqa: PLC0415
        from scout_core.adapters import image_store  # noqa: PLC0415
        from scout_core.domain import images  # noqa: PLC0415

        extracted = [{
            "title": "Skipped Image", "start_date": "2099-07-02", "location": None,
            "event_labels": [], "images": ["https://example.com/q.png"],
            "sub_events": [],
        }]
        with patch.object(image_store, "download",
                          side_effect=image_store.DownloadError("blocked")):
            result = events.convert_extraction("s", extracted)
        # Strict policy: failed download → no image record. There is no
        # external-url fallback.
        stored = images.list_images(store.EVENT, result["event_ids"][0])
        self.assertEqual(stored, [])

    # --- update ----------------------------------------------------------
    def test_update_marks_edited_and_recomputes_dup_key(self):
        ev = events.create_event("s", title="Old Title", start_date="2099-01-01")
        before = ev["dup_key"]
        updated = events.update_event(ev["event_id"], {"title": "New Title"})
        self.assertTrue(updated["edited"])
        self.assertNotEqual(updated["dup_key"], before)
        self.assertEqual(updated["title_norm"], "new title")

    def test_update_event_syncs_event_labels(self):
        ev = events.create_event("s", title="Show", start_date="2099-01-01")
        a = labels.create_label(store.EVENT_LABEL, "Music")
        b = labels.create_label(store.EVENT_LABEL, "Art")
        events.update_event(ev["event_id"], {"event_label_ids": [a["label_id"]]})
        self.assertEqual(
            labels.label_ids_of(store.EVENT, ev["event_id"], store.EVENT_LABEL),
            [a["label_id"]])
        # Swap labels: old detached, new attached.
        events.update_event(ev["event_id"], {"event_label_ids": [b["label_id"]]})
        self.assertEqual(
            labels.label_ids_of(store.EVENT, ev["event_id"], store.EVENT_LABEL),
            [b["label_id"]])

    def test_admin_detail_includes_label_ids(self):
        lbl = labels.create_label(store.EVENT_LABEL, "Music")
        ev = events.create_event("s", title="Show", start_date="2099-01-01",
                                 event_label_ids=[lbl["label_id"]])
        sub = events.create_subevent(ev["event_id"], start_date="2099-02-01",
                                     event_label_ids=[lbl["label_id"]])
        detail = events.admin_detail(ev["event_id"])
        self.assertEqual(detail["event"]["event_label_ids"], [lbl["label_id"]])
        self.assertEqual(detail["subevents"][0]["subevent_id"], sub["subevent_id"])
        self.assertEqual(detail["subevents"][0]["event_label_ids"], [lbl["label_id"]])
        self.assertIsNone(events.admin_detail("nope"))

    def test_update_subevent_in_place_when_date_unchanged(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-02-01")
        before_sk = sub["SK"]
        updated = events.update_subevent(
            ev["event_id"], sub["subevent_id"],
            {"start_time": "19:00", "end_time": "21:00"})
        self.assertEqual(updated["SK"], before_sk)  # same row
        self.assertEqual(updated["start_time"], "19:00")
        self.assertEqual(updated["end_time"], "21:00")

    def test_update_subevent_date_change_moves_row(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-02-01")
        old_sk = sub["SK"]
        updated = events.update_subevent(
            ev["event_id"], sub["subevent_id"], {"start_date": "2099-03-15"})
        self.assertNotEqual(updated["SK"], old_sk)
        self.assertEqual(updated["start_date"], "2099-03-15")
        self.assertEqual(updated["subevent_id"], sub["subevent_id"])  # identity kept
        self.assertEqual(updated["created_at"], sub["created_at"])
        # Old row is gone; exactly one occurrence remains.
        self.assertIsNone(store.get(store.event_pk(ev["event_id"]), old_sk))
        self.assertEqual(len(events.list_subevents(ev["event_id"])), 1)

    def test_update_subevent_reindexes_pubvis_on_move(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        events.set_publish(ev["event_id"], True)
        sub = events.create_subevent(ev["event_id"], start_date="2099-02-01")
        events.set_subevent_publish(ev["event_id"], sub["subevent_id"], True)
        self.assertIn(sub["subevent_id"], _pubvis_ids())
        # Moving the date keeps it publicly visible under the new key.
        events.update_subevent(ev["event_id"], sub["subevent_id"],
                               {"start_date": "2099-04-01"})
        self.assertIn(sub["subevent_id"], _pubvis_ids())

    def test_update_subevent_sets_location_and_label_overrides(self):
        loc = locations.create_location("Hall", address="1 St", timezone="UTC")
        lbl = labels.create_label(store.EVENT_LABEL, "Jazz")
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        sub = events.create_subevent(ev["event_id"], start_date="2099-02-01")
        self.assertFalse(sub.get("event_labels_overridden"))
        updated = events.update_subevent(
            ev["event_id"], sub["subevent_id"],
            {"location_id_override": loc["location_id"],
             "event_label_ids": [lbl["label_id"]]})
        self.assertEqual(updated["location_id_override"], loc["location_id"])
        self.assertTrue(updated["event_labels_overridden"])
        self.assertEqual(
            labels.label_ids_of(store.SUBEVENT, sub["subevent_id"], store.EVENT_LABEL),
            [lbl["label_id"]])

    def test_update_subevent_missing_returns_none(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01")
        self.assertIsNone(events.update_subevent(ev["event_id"], "nope", {}))
        self.assertIsNone(events.update_subevent("nope", "nope", {}))

    # --- sweep -----------------------------------------------------------
    def test_sweep_keeps_past_flag_correct(self):
        past = events.create_event("s", title="Old", start_date="2000-01-01")
        future = events.create_event("s", title="New", start_date="2099-01-01")
        events.sweep()
        self.assertTrue(events.get_event(past["event_id"])["past"])
        self.assertFalse(events.get_event(future["event_id"])["past"])

    def test_sweep_auto_past_parent_when_all_subs_past(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01",
                                 auto_past_parent=True)
        events.create_subevent(ev["event_id"], start_date="2000-01-01")
        events.create_subevent(ev["event_id"], start_date="2000-02-01")
        events.sweep()
        # Parent's own date is in the future, but all sub-events are past.
        self.assertTrue(events.get_event(ev["event_id"])["past"])

    def test_auto_cancel_parent_when_all_subs_cancelled(self):
        ev = events.create_event("s", title="Series", start_date="2099-01-01",
                                 auto_cancel_parent=True)
        s1 = events.create_subevent(ev["event_id"], start_date="2099-01-02")
        s2 = events.create_subevent(ev["event_id"], start_date="2099-01-03")
        events.cancel_subevent(ev["event_id"], s1["subevent_id"])
        self.assertFalse(events.get_event(ev["event_id"])["lifecycle_cancelled"])
        events.cancel_subevent(ev["event_id"], s2["subevent_id"])
        self.assertTrue(events.get_event(ev["event_id"])["lifecycle_cancelled"])


if __name__ == "__main__":
    unittest.main()
