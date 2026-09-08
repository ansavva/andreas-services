"""Test fixtures: a moto-backed DynamoDB table and a Flask test client.

``CLASSROOM_PAGES_TABLE`` is set before importing anything from
``classroom_core`` because ``repositories.store`` resolves it at import time and
raises when it is absent — which is the behaviour we want in production.
"""

import os

import boto3
import pytest
from moto import mock_dynamodb, mock_s3

TABLE_NAME = "classroom-test-pages"
LESSONS_BUCKET = "classroom-test-lessons"

os.environ.setdefault("CLASSROOM_PAGES_TABLE", TABLE_NAME)
os.environ.setdefault("CLASSROOM_LESSONS_BUCKET", LESSONS_BUCKET)
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
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Reset the memoised boto3 resource so it binds to the mocked backend.
        from classroom_core.repositories import dynamodb as dynamodb_module

        dynamodb_module._dynamodb = None
        yield


@pytest.fixture
def lessons_bucket():
    """A mocked lesson bucket, so publish/withdraw move real objects."""
    with mock_s3():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=LESSONS_BUCKET)
        from classroom_core.repositories import lessons as lessons_module

        lessons_module._client = None
        yield boto3.client("s3", region_name="us-east-1")


def upload(s3, page_id, path, body=b"<h1>hi</h1>"):
    """Put a file where a presigned browser upload would have put it."""
    s3.put_object(Bucket=LESSONS_BUCKET, Key=f"draft/{page_id}/{path}", Body=body)


def live_keys(s3, page_id):
    listing = s3.list_objects_v2(Bucket=LESSONS_BUCKET, Prefix=f"lesson/{page_id}/")
    prefix = f"lesson/{page_id}/"
    return sorted(o["Key"][len(prefix):] for o in listing.get("Contents", []))


@pytest.fixture
def client(dynamodb_table, lessons_bucket):
    from classroom_core.app_factory import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def as_teacher(claims):
    """Environ overrides that mimic the API Gateway JWT authorizer."""
    return {"aws.event": {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}}
