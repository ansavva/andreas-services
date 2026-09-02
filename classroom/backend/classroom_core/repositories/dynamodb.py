"""DynamoDB resource access and local table bootstrap for classroom."""

import os

import boto3
from botocore.exceptions import ClientError

from classroom_core import config

_dynamodb = None


def _region() -> str:
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def resource():
    global _dynamodb
    if _dynamodb is None:
        kwargs = {"region_name": _region()}
        endpoint_url = config.dynamodb_endpoint_url()
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        _dynamodb = boto3.resource("dynamodb", **kwargs)
    return _dynamodb


def table(table_name: str):
    return resource().Table(table_name)


def ensure_local_table_exists(table_name: str):
    """Create the single classroom table when running against DynamoDB Local.

    GSI1 indexes a page by its public slug so an anonymous read is a single
    query rather than a scan.
    """
    handle = table(table_name)
    try:
        handle.load()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        handle = resource().create_table(
            TableName=table_name,
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
        handle.wait_until_exists()
