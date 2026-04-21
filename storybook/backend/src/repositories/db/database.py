"""
DynamoDB resource module for Storybook.
Provides a lazy boto3 DynamoDB resource and a helper to get a Table by env var name.
"""
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr  # noqa: F401 — re-exported for convenience

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')


def _table(env_var: str):
    """Return a DynamoDB Table object whose name is stored in *env_var*."""
    return dynamodb.Table(os.environ[env_var])
