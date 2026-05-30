"""
Unit tests for the scout-core data-access layer (store.py) and the taxonomy
normalization helpers.

Uses moto to mock DynamoDB — no AWS credentials or network access required.
"""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.adapters import store  # noqa: E402  (import after env is set)
from scout_core.common import taxonomy  # noqa: E402

CORE_TABLE = "scout-core"
SETTINGS_TABLE = "scout-settings"

_GSI_ATTRS = [
    "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "GSI3PK", "GSI3SK",
    "GSI4PK", "GSI4SK", "GSI5PK", "GSI5SK",
]


def _create_core(dynamodb):
    attribute_definitions = [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
    ] + [{"AttributeName": n, "AttributeType": "S"} for n in _GSI_ATTRS]

    gsis = []
    for i in range(1, 6):
        gsis.append({
            "IndexName": f"GSI{i}",
            "KeySchema": [
                {"AttributeName": f"GSI{i}PK", "KeyType": "HASH"},
                {"AttributeName": f"GSI{i}SK", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        })

    dynamodb.create_table(
        TableName=CORE_TABLE,
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
        TableName=SETTINGS_TABLE,
        KeySchema=[{"AttributeName": "setting_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "setting_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


@mock_dynamodb
class TestStore(unittest.TestCase):
    def setUp(self):
        # Rebind the (lazily cached) boto3 resource to this method's mock and
        # drop the settings cache so tests are independent.
        store._dynamodb = None
        store.reset_settings_cache()
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        _create_core(dynamodb)
        _create_settings(dynamodb)

    # --- ids -------------------------------------------------------------
    def test_new_id_format_and_uniqueness(self):
        ids = {store.new_id() for _ in range(200)}
        self.assertEqual(len(ids), 200)
        for value in ids:
            self.assertEqual(len(value), 26)
            self.assertTrue(all(c in store._CROCKFORD for c in value))

    # --- key builders ----------------------------------------------------
    def test_key_builders(self):
        self.assertEqual(store.source_pk("abc"), "SRC#abc")
        self.assertEqual(store.event_pk("e1"), "EVT#e1")
        self.assertEqual(store.location_pk("l1"), "LOC#l1")
        self.assertEqual(store.label_pk(store.EVENT_LABEL, "music"), "ELBL#music")
        self.assertEqual(store.sub_sk("2026-05-01", "s1"), "SUB#2026-05-01#s1")
        self.assertEqual(store.link_sk(store.EVENT, "e1"), "LINK#EVT#e1")

    # --- reads / writes --------------------------------------------------
    def test_put_and_get(self):
        item = store.base_item(store.event_pk("e1"), "META", store.EVENT, title="Hi")
        store.put(item)
        fetched = store.get(store.event_pk("e1"), "META")
        self.assertEqual(fetched["title"], "Hi")
        self.assertEqual(fetched["entity_type"], store.EVENT)
        self.assertIn("created_at", fetched)

    def test_base_item_drops_none_values(self):
        item = store.base_item(store.event_pk("e1"), "META", store.EVENT,
                               title="Hi", location_id=None)
        self.assertNotIn("location_id", item)

    def test_query_all_begins_with_and_live_only(self):
        pk = store.event_pk("e1")
        store.put(store.base_item(pk, "META", store.EVENT, title="Parent"))
        store.put(store.base_item(pk, store.sub_sk("2026-05-01", "s1"), store.SUBEVENT))
        store.put(store.base_item(pk, store.sub_sk("2026-05-02", "s2"), store.SUBEVENT))

        subs = store.query_all(pk, sk_begins_with="SUB#")
        self.assertEqual(len(subs), 2)
        # SK embeds the date, so ascending order is chronological.
        self.assertEqual(subs[0]["SK"], store.sub_sk("2026-05-01", "s1"))

    # --- soft delete / restore ------------------------------------------
    def test_soft_delete_removes_hot_index_and_excludes_from_live(self):
        pk = store.event_pk("e1")
        item = store.base_item(
            pk, "META", store.EVENT,
            GSI1PK="PUBVIS", GSI1SK="2026-05-01#e1",
            GSI3PK="DUP#k", GSI3SK="EVT#e1",
        )
        store.put(item)

        store.soft_delete(pk, "META", store.EVENT)

        deleted = store.get(pk, "META")
        self.assertIn("deleted_at", deleted)
        self.assertEqual(deleted["GSI5PK"], "DELETED#event")
        # Hot-path index keys are stripped so the row leaves public/dedup paths.
        for attr in store.HOT_INDEX_ATTRS:
            self.assertNotIn(attr, deleted)

        # A live-only query no longer surfaces it; the deleted view does.
        self.assertEqual(store.query_all(pk, sk_begins_with="META"), [])
        deleted_view = store.query_deleted(store.EVENT)
        self.assertEqual(len(deleted_view), 1)
        self.assertEqual(deleted_view[0]["PK"], pk)

    def test_soft_delete_records_cascade_metadata(self):
        pk = store.event_pk("e1")
        store.put(store.base_item(pk, "META", store.EVENT))
        store.soft_delete(pk, "META", store.EVENT, cascade_id="c-123",
                          via_cascade=True, parent_ref="SRC#s1")
        deleted = store.get(pk, "META")
        self.assertEqual(deleted["cascade_id"], "c-123")
        self.assertTrue(deleted["deleted_via_cascade"])
        self.assertEqual(deleted["deleted_parent_ref"], "SRC#s1")

    def test_restore_clears_markers(self):
        pk = store.event_pk("e1")
        store.put(store.base_item(pk, "META", store.EVENT))
        store.soft_delete(pk, "META", store.EVENT, cascade_id="c-1", via_cascade=True)
        store.restore(pk, "META")

        restored = store.get(pk, "META")
        for attr in ("deleted_at", "cascade_id", "deleted_via_cascade",
                     "deleted_parent_ref", "GSI5PK", "GSI5SK"):
            self.assertNotIn(attr, restored)
        self.assertEqual(len(store.query_all(pk, sk_begins_with="META")), 1)
        self.assertEqual(store.query_deleted(store.EVENT), [])

    # --- GSI queries -----------------------------------------------------
    def test_query_index_reverse_labels(self):
        label = store.label_pk(store.EVENT_LABEL, "music")
        ref = store.entity_ref(store.EVENT, "e1")
        store.put(store.base_item(
            label, store.link_sk(store.EVENT, "e1"), store.EVENT_LABEL_LINK,
            GSI2PK=ref, GSI2SK="LINK#ELBL#music",
        ))
        # Reverse direction: "labels of event e1".
        labels = store.query_index_all("GSI2", ref)
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["PK"], label)

    # --- settings --------------------------------------------------------
    def test_settings_defaults(self):
        settings = store.get_settings()
        self.assertEqual(settings["system_timezone"], "UTC")
        self.assertEqual(settings["link_follow_cap"], 10)
        self.assertEqual(settings["default_agent_model"], "claude-sonnet-4-6")
        self.assertEqual(settings["default_triage_model"], "claude-haiku-4-5")

    def test_settings_override_and_cache_invalidation(self):
        store.put_settings({"link_follow_cap": 25, "system_timezone": "America/New_York"})
        settings = store.get_settings()
        self.assertEqual(settings["link_follow_cap"], 25)
        self.assertEqual(settings["system_timezone"], "America/New_York")
        # Untouched keys fall back to defaults.
        self.assertEqual(settings["fallback_timezone"], "UTC")


class TestTaxonomyNormalization(unittest.TestCase):
    def test_normalize_title_strips_punct_article_and_case(self):
        self.assertEqual(taxonomy.normalize_title("The  Big!! Show"), "big show")
        self.assertEqual(taxonomy.normalize_title("A Night Out"), "night out")
        self.assertEqual(taxonomy.normalize_title("Café Night"), "café night")

    def test_normalize_title_handles_empty(self):
        self.assertEqual(taxonomy.normalize_title(None), "")
        self.assertEqual(taxonomy.normalize_title("   "), "")

    def test_normalize_name(self):
        self.assertEqual(taxonomy.normalize_name("The O2 Arena!"), "the o2 arena")

    def test_dup_key_is_deterministic_and_normalized(self):
        a = taxonomy.dup_key("The Big Show", "2026-05-01", "loc-1")
        b = taxonomy.dup_key("big   show", "2026-05-01", "loc-1")
        self.assertEqual(a, b)
        self.assertEqual(a, "big show|2026-05-01|loc-1")

    def test_dup_key_without_location(self):
        self.assertEqual(taxonomy.dup_key("Show", "2026-05-01"), "show|2026-05-01|none")


if __name__ == "__main__":
    unittest.main()
