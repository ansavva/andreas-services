"""DynamoDB access and local table bootstrap for the website API."""

import os

import boto3
from botocore.exceptions import ClientError

from website_core import config

_dynamodb = None


def _region():
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


def ensure_local_tables_exist():
    intake_table = table(config.intake_table())
    try:
        intake_table.load()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        intake_table = resource().create_table(
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
        intake_table.wait_until_exists()
    return intake_table
