import os

import boto3
import pytest

# Credentials/region must exist before boto3/moto import time.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("WEBSITE_TABLE_SUFFIX", "")

from moto import mock_dynamodb  # noqa: E402

from website_core.repositories import dynamodb  # noqa: E402
from website_core import config  # noqa: E402


@pytest.fixture
def intake_table():
    """A live (moto-backed) website-intake table, isolated per test."""
    with mock_dynamodb():
        dynamodb._dynamodb = None  # drop any cached resource from a prior test
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=config.intake_table(),
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield
        dynamodb._dynamodb = None
