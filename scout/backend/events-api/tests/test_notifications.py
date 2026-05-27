"""Unit tests for in-app notifications (notifications.py)."""

import os
import unittest

import boto3
from moto import mock_dynamodb

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.domain import notifications  # noqa: E402
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


@mock_dynamodb
class TestNotifications(unittest.TestCase):
    def setUp(self):
        store._dynamodb = None
        _create_core(boto3.resource("dynamodb", region_name="us-east-1"))

    def test_run_failure_and_budget_are_distinct(self):
        notifications.notify_run_failure("s1", "r1", "boom")
        notifications.notify_budget_exceeded("s2", "r2")
        items = notifications.list_notifications()
        types = sorted(i["type"] for i in items)
        self.assertEqual(types, ["budget_exceeded", "run_failure"])

    def test_unread_filter_and_mark_read(self):
        a = notifications.notify_run_failure("s1", "r1", "boom")
        notifications.notify_budget_exceeded("s2", "r2")
        self.assertEqual(len(notifications.list_notifications(unread_only=True)), 2)

        notifications.mark_read(a["notification_id"])
        unread = notifications.list_notifications(unread_only=True)
        self.assertEqual(len(unread), 1)
        self.assertEqual(unread[0]["type"], "budget_exceeded")


if __name__ == "__main__":
    unittest.main()
