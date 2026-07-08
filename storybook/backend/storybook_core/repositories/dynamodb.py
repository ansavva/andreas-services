"""Standard DynamoDB access helpers for Storybook."""

import os

import boto3
from botocore.exceptions import ClientError

from storybook_core.config import AppConfig

_dynamodb = None

_LOCAL_TABLES = {
    "STORYBOOK_USER_PROFILES_TABLE": {"hash": ("user_id", "S")},
    "STORYBOOK_CHILD_PROFILES_TABLE": {
        "hash": ("profile_id", "S"),
        "gsis": [("project_id-index", ("project_id", "S"), None)],
    },
    "STORYBOOK_STORY_PROJECTS_TABLE": {
        "hash": ("project_id", "S"),
        "gsis": [("user_id-created_at-index", ("user_id", "S"), ("created_at", "S"))],
    },
    "STORYBOOK_STORY_PAGES_TABLE": {
        "hash": ("page_id", "S"),
        "gsis": [("project_id-page_number-index", ("project_id", "S"), ("page_number", "N"))],
    },
    "STORYBOOK_CHAT_MESSAGES_TABLE": {
        "hash": ("message_id", "S"),
        "gsis": [("project_id-sequence-index", ("project_id", "S"), ("sequence", "S"))],
    },
    "STORYBOOK_CHARACTER_ASSETS_TABLE": {
        "hash": ("asset_id", "S"),
        "gsis": [("project_id-created_at-index", ("project_id", "S"), ("created_at", "S"))],
    },
    "STORYBOOK_STORY_STATES_TABLE": {
        "hash": ("state_id", "S"),
        "gsis": [("project_id-version-index", ("project_id", "S"), ("version", "N"))],
    },
    "STORYBOOK_IMAGES_TABLE": {
        "hash": ("image_id", "S"),
        "gsis": [("project_id-created_at-index", ("project_id", "S"), ("created_at", "S"))],
    },
    "STORYBOOK_MODEL_PROJECTS_TABLE": {
        "hash": ("project_id", "S"),
        "gsis": [("user_id-created_at-index", ("user_id", "S"), ("created_at", "S"))],
    },
    "STORYBOOK_GENERATION_HISTORY_TABLE": {
        "hash": ("generation_id", "S"),
        "gsis": [("project_id-created_at-index", ("project_id", "S"), ("created_at", "S"))],
    },
    "STORYBOOK_TRAINING_RUNS_TABLE": {
        "hash": ("training_run_id", "S"),
        "gsis": [("project_id-created_at-index", ("project_id", "S"), ("created_at", "S"))],
    },
}


def resource():
    global _dynamodb
    if _dynamodb is None:
        kwargs = {"region_name": AppConfig.AWS_REGION}
        if AppConfig.DYNAMODB_ENDPOINT_URL:
            kwargs["endpoint_url"] = AppConfig.DYNAMODB_ENDPOINT_URL
        _dynamodb = boto3.resource("dynamodb", **kwargs)
    return _dynamodb


def table(env_var: str):
    return resource().Table(os.environ[env_var])


def init_db(app):
    app.extensions["dynamodb"] = resource()


def get_db():
    return resource()


def ensure_local_tables_exist():
    for env_var, spec in _LOCAL_TABLES.items():
        _ensure_table(env_var, spec)


def _ensure_table(env_var, spec):
    table_name = os.environ[env_var]
    existing = resource().Table(table_name)
    try:
        existing.load()
        return
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
            raise

    hash_name, hash_type = spec["hash"]
    attr_types = {hash_name: hash_type}
    gsis = []
    for index_name, gsi_hash, gsi_range in spec.get("gsis", []):
        gsi_hash_name, gsi_hash_type = gsi_hash
        attr_types[gsi_hash_name] = gsi_hash_type
        key_schema = [{"AttributeName": gsi_hash_name, "KeyType": "HASH"}]
        if gsi_range:
            gsi_range_name, gsi_range_type = gsi_range
            attr_types[gsi_range_name] = gsi_range_type
            key_schema.append({"AttributeName": gsi_range_name, "KeyType": "RANGE"})
        gsis.append({"IndexName": index_name, "KeySchema": key_schema, "Projection": {"ProjectionType": "ALL"}})

    kwargs = {
        "TableName": table_name,
        "KeySchema": [{"AttributeName": hash_name, "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": name, "AttributeType": attr_type}
            for name, attr_type in attr_types.items()
        ],
        "BillingMode": "PAY_PER_REQUEST",
    }
    if gsis:
        kwargs["GlobalSecondaryIndexes"] = gsis
    created = resource().create_table(**kwargs)
    created.wait_until_exists()
