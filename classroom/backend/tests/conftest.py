"""Test fixtures: a moto-backed DynamoDB table and a Flask test client.

``CLASSROOM_PAGES_TABLE`` is set before importing anything from
``classroom_core`` because ``repositories.store`` resolves it at import time and
raises when it is absent — which is the behaviour we want in production.
"""

import os

import boto3
import pytest
from moto import mock_dynamodb

TABLE_NAME = "classroom-test-pages"

os.environ.setdefault("CLASSROOM_PAGES_TABLE", TABLE_NAME)
os.environ.setdefault("CLASSROOM_PUBLIC_SITE_URL", "https://classroom.example.test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

TEACHER = {"sub": "teacher-anita", "email": "anita@example.test", "name": "Anita"}
OTHER_TEACHER = {"sub": "teacher-other", "email": "other@example.test"}


@pytest.fixture
def dynamodb_table():
    with mock_dynamodb():
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Reset the memoised boto3 resource so it binds to the mocked backend.
        from classroom_core.repositories import dynamodb as dynamodb_module

        dynamodb_module._dynamodb = None
        yield


@pytest.fixture
def client(dynamodb_table):
    from classroom_core.app_factory import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def as_teacher(claims):
    """Environ overrides that mimic the API Gateway JWT authorizer."""
    return {"aws.event": {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}}
