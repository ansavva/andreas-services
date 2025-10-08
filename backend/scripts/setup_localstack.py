"""Utilities for bootstrapping LocalStack resources required by the Gmail ingestion Lambda.

This script creates the DynamoDB table (with GSIs) and the Secrets Manager
secrets expected by the Lambda when running against a LocalStack instance.

Example usage:

    python3 backend/scripts/setup_localstack.py \
        --endpoint-url http://localhost:4566 \
        --openai-api-key sk-test \
        --gmail-secret-file gmail-credentials.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

TABLE_GSIS = [
    {
        "IndexName": "category-index",
        "KeySchema": [{"AttributeName": "category", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"},
    },
    {
        "IndexName": "source_name-index",
        "KeySchema": [{"AttributeName": "source_name", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"},
    },
    {
        "IndexName": "start_time-index",
        "KeySchema": [{"AttributeName": "start_time", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"},
    },
]


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed LocalStack with DynamoDB and Secrets Manager resources "
        "required by the Gmail ingestion Lambda."
    )
    parser.add_argument(
        "--endpoint-url",
        default="http://localhost:4566",
        help="LocalStack edge endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region to use when connecting to LocalStack (default: %(default)s)",
    )
    parser.add_argument(
        "--table-name",
        default="Events",
        help="Name of the DynamoDB table to create or ensure exists (default: %(default)s)",
    )
    parser.add_argument(
        "--openai-secret-name",
        default="local/openai",
        help="Name of the Secrets Manager secret that stores the OpenAI key (default: %(default)s)",
    )
    parser.add_argument(
        "--openai-api-key",
        help="Literal OpenAI API key value to embed in the secret JSON. Mutually exclusive with --openai-secret-file.",
    )
    parser.add_argument(
        "--openai-secret-file",
        type=Path,
        help="Path to a JSON file to use verbatim for the OpenAI secret.",
    )
    parser.add_argument(
        "--gmail-secret-name",
        default="local/gmail",
        help="Name of the Secrets Manager secret that stores Gmail OAuth credentials (default: %(default)s)",
    )
    parser.add_argument(
        "--gmail-secret-file",
        type=Path,
        required=True,
        help="Path to a JSON file containing Gmail OAuth credentials (merged client + tokens).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite secrets if they already exist instead of skipping them.",
    )
    return parser.parse_args(argv)


def load_openai_secret(args: argparse.Namespace) -> str:
    if args.openai_secret_file and args.openai_api_key:
        raise ValueError("Specify either --openai-api-key or --openai-secret-file, not both.")

    if args.openai_secret_file:
        return Path(args.openai_secret_file).read_text(encoding="utf-8")

    if args.openai_api_key:
        payload = {"apiKey": args.openai_api_key}
        return json.dumps(payload)

    raise ValueError(
        "An OpenAI credential is required. Provide --openai-api-key or --openai-secret-file."
    )


def load_gmail_secret(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    # Validate JSON early so we can emit actionable errors before hitting AWS.
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Invalid JSON in Gmail credentials file: {path}") from exc
    return content


def ensure_table(dynamodb_client: Any, table_name: str) -> Dict[str, Any]:
    try:
        response = dynamodb_client.describe_table(TableName=table_name)
        print(f"DynamoDB table '{table_name}' already exists. Skipping creation.")
        return response["Table"]
    except ClientError as exc:
        error_code = exc.response["Error"].get("Code")
        if error_code != "ResourceNotFoundException":
            raise

    attribute_definitions = [
        {"AttributeName": "id", "AttributeType": "S"},
        {"AttributeName": "category", "AttributeType": "S"},
        {"AttributeName": "source_name", "AttributeType": "S"},
        {"AttributeName": "start_time", "AttributeType": "S"},
    ]

    print(f"Creating DynamoDB table '{table_name}' with global secondary indexes...")
    response = dynamodb_client.create_table(
        TableName=table_name,
        AttributeDefinitions=attribute_definitions,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        GlobalSecondaryIndexes=TABLE_GSIS,
        BillingMode="PAY_PER_REQUEST",
        StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
    )
    waiter = dynamodb_client.get_waiter("table_exists")
    waiter.wait(TableName=table_name)
    return response["Table"]


def ensure_secret(
    secrets_client: Any,
    name: str,
    secret_string: str,
    *,
    force: bool,
) -> Dict[str, Any]:
    try:
        metadata = secrets_client.describe_secret(SecretId=name)
        if not force:
            print(f"Secret '{name}' already exists. Skipping update (use --force to overwrite).")
            return metadata

        print(f"Updating existing secret '{name}'...")
        secrets_client.put_secret_value(SecretId=name, SecretString=secret_string)
        metadata = secrets_client.describe_secret(SecretId=name)
        return metadata
    except ClientError as exc:
        error_code = exc.response["Error"].get("Code")
        if error_code != "ResourceNotFoundException":
            raise

    print(f"Creating secret '{name}'...")
    response = secrets_client.create_secret(Name=name, SecretString=secret_string)
    return response


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    try:
        openai_secret = load_openai_secret(args)
        gmail_secret = load_gmail_secret(args.gmail_secret_file)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    session = boto3.session.Session(region_name=args.region)
    dynamodb = session.client("dynamodb", endpoint_url=args.endpoint_url)
    secrets = session.client("secretsmanager", endpoint_url=args.endpoint_url)

    try:
        table = ensure_table(dynamodb, args.table_name)
        openai_meta = ensure_secret(
            secrets,
            args.openai_secret_name,
            openai_secret,
            force=args.force,
        )
        gmail_meta = ensure_secret(
            secrets,
            args.gmail_secret_name,
            gmail_secret,
            force=args.force,
        )
    except ClientError as exc:  # pragma: no cover - surfaced to caller
        error = exc.response["Error"].get("Message", str(exc))
        print(f"AWS error: {error}", file=sys.stderr)
        return 2

    print("\nBootstrap complete. Useful identifiers:")
    table_arn = table.get("TableArn") if isinstance(table, dict) else None
    if not table_arn:
        table_description = dynamodb.describe_table(TableName=args.table_name)
        table_arn = table_description["Table"]["TableArn"]
    print(f"  DynamoDB Table ARN: {table_arn}")

    openai_arn = openai_meta.get("ARN") or secrets.describe_secret(SecretId=args.openai_secret_name)["ARN"]
    gmail_arn = gmail_meta.get("ARN") or secrets.describe_secret(SecretId=args.gmail_secret_name)["ARN"]
    print(f"  OpenAI Secret ARN: {openai_arn}")
    print(f"  Gmail Secret ARN: {gmail_arn}")

    print("\nSuggested environment variables (copy into .env):")
    print(f"OPENAI_SECRET_ARN={openai_arn}")
    print(f"GMAIL_SECRET_ARN={gmail_arn}")
    print(f"TABLE_NAME={args.table_name}")
    print("TIMEZONE=America/New_York")
    print(f"SECRETSMANAGER_ENDPOINT_URL={args.endpoint_url}")
    print(f"DYNAMODB_ENDPOINT_URL={args.endpoint_url}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
