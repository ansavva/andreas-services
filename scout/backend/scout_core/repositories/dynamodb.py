"""DynamoDB access and local table bootstrap for Scout."""

import os

import boto3
from botocore.exceptions import ClientError

from scout_core import config

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


def ensure_local_tables_exist(core_table_name: str, settings_table_name: str):
    _ensure_core_table(core_table_name)
    _ensure_settings_table(settings_table_name)


def _ensure_core_table(table_name: str):
    core_table = table(table_name)
    try:
        core_table.load()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        gsi_attrs = [
            "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "GSI3PK", "GSI3SK",
            "GSI4PK", "GSI4SK", "GSI5PK", "GSI5SK",
        ]
        gsis = [
            {
                "IndexName": f"GSI{i}",
                "KeySchema": [
                    {"AttributeName": f"GSI{i}PK", "KeyType": "HASH"},
                    {"AttributeName": f"GSI{i}SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
            for i in range(1, 6)
        ]
        core_table = resource().create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                *[{"AttributeName": name, "AttributeType": "S"} for name in gsi_attrs],
            ],
            GlobalSecondaryIndexes=gsis,
            BillingMode="PAY_PER_REQUEST",
        )
        core_table.wait_until_exists()


def _ensure_settings_table(table_name: str):
    settings = table(table_name)
    try:
        settings.load()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise
        settings = resource().create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "setting_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "setting_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        settings.wait_until_exists()
