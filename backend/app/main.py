"""Gmail → OpenAI → DynamoDB ingestion workflow.

This module is designed to run inside a container that is scheduled by
EventBridge on ECS/EKS as well as locally via ``python -m app.main``.

The handler keeps compatibility with the earlier Lambda implementation but the
``run`` function is the canonical entrypoint for container executions.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
import requests
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from dateutil import parser as date_parser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field, ValidationError, root_validator, validator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
MAX_OPENAI_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
MAX_GMAIL_RETRIES = int(os.getenv("GMAIL_MAX_RETRIES", "3"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT_URL")
SECRETSMANAGER_ENDPOINT = os.getenv("SECRETSMANAGER_ENDPOINT_URL")


def _create_boto_client(service: str):
    kwargs: Dict[str, Any] = {"region_name": AWS_REGION}
    if service == "dynamodb":
        if DYNAMODB_ENDPOINT:
            kwargs["endpoint_url"] = DYNAMODB_ENDPOINT
        return boto3.resource(service, **kwargs)
    if service == "secretsmanager":
        if SECRETSMANAGER_ENDPOINT:
            kwargs["endpoint_url"] = SECRETSMANAGER_ENDPOINT
    return boto3.client(service, **kwargs)


DYNAMODB = _create_boto_client("dynamodb")
SECRETS_CLIENT = _create_boto_client("secretsmanager")


class EventModel(BaseModel):
    title: Optional[str]
    description: Optional[str]
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    location: Optional[str]
    category: Optional[str]
    source_name: Optional[str]
    source_email: Optional[str]
    source_domain: Optional[str]
    organizer_name: Optional[str]
    organizer_url: Optional[str]
    source_url: Optional[str]
    email_id: str = Field(..., description="Unique Gmail message id")
    created_at: Optional[datetime]
    tags: Optional[List[str]]
    normalized_location: Optional[str]

    @validator("tags", pre=True)
    def _ensure_tags_list(cls, value: Any) -> Optional[List[str]]:  # noqa: D417
        if value is None:
            return None
        if isinstance(value, list):
            return [str(v) for v in value]
        raise ValueError("tags must be an array of strings or null")

    @validator("start_time", "end_time", "created_at", pre=True)
    def _parse_datetime(cls, value: Any) -> Optional[datetime]:  # noqa: D417
        if value in (None, "", "null"):
            return None
        if isinstance(value, datetime):
            return value
        try:
            parsed = date_parser.isoparse(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid datetime value: {value}") from exc

    @root_validator
    def _strip_empty_strings(cls, values: Dict[str, Any]) -> Dict[str, Any]:  # noqa: D417
        for key, val in list(values.items()):
            if isinstance(val, str) and not val.strip():
                values[key] = None
        return values

    class Config:
        extra = "forbid"

secrets_cache: Dict[str, Dict[str, Any]] = {}


def get_secret(secret_arn: str) -> Dict[str, Any]:
    if secret_arn in secrets_cache:
        return secrets_cache[secret_arn]
    try:
        response = SECRETS_CLIENT.get_secret_value(SecretId=secret_arn)
    except ClientError as error:  # pragma: no cover - passthrough for observability
        logger.error("Failed to retrieve secret %s: %s", secret_arn, error)
        raise
    secret_string = response.get("SecretString")
    if not secret_string:
        raise ValueError(f"Secret {secret_arn} does not contain a SecretString")
    secret_value = json.loads(secret_string)
    secrets_cache[secret_arn] = secret_value
    return secret_value


def load_openai_api_key() -> str:
    secret_arn = os.getenv("OPENAI_SECRET_ARN")
    if secret_arn:
        secret_value = get_secret(secret_arn)
        api_key = secret_value.get("apiKey") or secret_value.get("api_key")
        if api_key:
            return api_key
        raise ValueError(
            "OpenAI secret must contain `apiKey` or `api_key`."
        )
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    raise ValueError(
        "OpenAI credentials missing. Set OPENAI_SECRET_ARN (production) or OPENAI_API_KEY (local)."
    )


def _load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_gmail_credentials() -> Dict[str, Any]:
    secret_arn = os.getenv("GMAIL_SECRET_ARN")
    if secret_arn:
        return get_secret(secret_arn)
    inline_json = os.getenv("GMAIL_CREDENTIALS_JSON")
    if inline_json:
        return json.loads(inline_json)
    credentials_path = os.getenv("GMAIL_CREDENTIALS_FILE")
    if credentials_path:
        return _load_json_file(credentials_path)
    raise ValueError(
        "Gmail credentials missing. Set GMAIL_SECRET_ARN (production) or provide "
        "GMAIL_CREDENTIALS_JSON / GMAIL_CREDENTIALS_FILE for local runs."
    )


def build_gmail_service(credentials_payload: Dict[str, Any]):
    creds = Credentials(
        token=credentials_payload.get("token"),
        refresh_token=credentials_payload.get("refresh_token"),
        token_uri=credentials_payload.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=credentials_payload.get("client_id"),
        client_secret=credentials_payload.get("client_secret"),
        scopes=credentials_payload.get(
            "scopes",
            [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.modify",
            ],
        ),
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_gmail_messages(service, query: str) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    request = service.users().messages().list(userId="me", q=query)
    while request is not None:
        for attempt in range(1, MAX_GMAIL_RETRIES + 1):
            try:
                response = request.execute()
                break
            except HttpError as error:
                logger.warning("Gmail API error on list attempt %s: %s", attempt, error)
                if attempt == MAX_GMAIL_RETRIES:
                    raise
                time.sleep(2 ** attempt)
        else:  # pragma: no cover - loop control safeguard
            raise RuntimeError("Exceeded Gmail retries for listing messages")
        messages.extend(response.get("messages", []))
        request = service.users().messages().list_next(
            previous_request=request, previous_response=response
        )
    return messages


def fetch_message_body(service, message_id: str) -> str:
    for attempt in range(1, MAX_GMAIL_RETRIES + 1):
        try:
            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            break
        except HttpError as error:
            logger.warning(
                "Failed to fetch Gmail message %s on attempt %s: %s",
                message_id,
                attempt,
                error,
            )
            if attempt == MAX_GMAIL_RETRIES:
                raise
            time.sleep(2 ** attempt)
    else:  # pragma: no cover - defensive guard
        raise RuntimeError("Exceeded Gmail retries for fetching message")

    payload = message.get("payload", {})
    parts = payload.get("parts")
    if parts:
        texts = [extract_part(part) for part in parts]
        body = "\n".join(filter(None, texts))
    else:
        body = extract_part(payload)
    if not body:
        body = message.get("snippet", "")
    return body


def extract_part(part: Dict[str, Any]) -> str:
    mime_type = part.get("mimeType", "")
    body = part.get("body", {})
    data = body.get("data")
    if not data and part.get("parts"):
        return "\n".join(
            filter(None, (extract_part(child) for child in part.get("parts", [])))
        )
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    decoded_bytes = base64.urlsafe_b64decode(data + padding)
    text = decoded_bytes.decode("utf-8", errors="ignore")
    if mime_type == "text/html":
        text = strip_html(text)
    return text


def strip_html(content: str) -> str:
    clean = re.sub(r"<script.*?>.*?</script>", " ", content, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<style.*?>.*?</style>", " ", clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def call_openai(api_key: str, email_text: str, email_id: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "start_time": {"type": ["string", "null"], "description": "ISO 8601 UTC"},
            "end_time": {"type": ["string", "null"], "description": "ISO 8601 UTC"},
            "location": {"type": ["string", "null"]},
            "category": {"type": ["string", "null"]},
            "source_name": {"type": ["string", "null"]},
            "source_email": {"type": ["string", "null"]},
            "source_domain": {"type": ["string", "null"]},
            "organizer_name": {"type": ["string", "null"]},
            "organizer_url": {"type": ["string", "null"]},
            "source_url": {"type": ["string", "null"]},
            "email_id": {"type": "string"},
            "created_at": {"type": ["string", "null"]},
            "tags": {"type": ["array", "null"], "items": {"type": "string"}},
            "normalized_location": {"type": ["string", "null"]},
        },
        "required": ["email_id"],
        "additionalProperties": False,
    }

    system_prompt = (
        "You are a data extraction assistant. Extract structured event information "
        "from the provided email text. Always produce valid JSON matching the provided schema. "
        "Use null when data is unavailable. Dates must be ISO 8601 in UTC."
    )
    schema_json = json.dumps(schema)
    user_prompt = (
        "Return ONLY valid JSON. Do not include explanations or code fences. "
        "Ensure email_id is set to the provided identifier.\n\n"
        f"EMAIL_ID: {email_id}\n"
        f"EMAIL TIMEZONE: {TIMEZONE}\n"
        f"EMAIL BODY:\n{email_text}\n"
        f"SCHEMA:\n{schema_json}"
    )

    payload = {
        "model": OPENAI_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    for attempt in range(1, MAX_OPENAI_RETRIES + 1):
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=HTTP_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"].get("content")
            if not content:
                function_call = data["choices"][0]["message"].get("function_call", {})
                if function_call.get("arguments"):
                    content = function_call["arguments"]
            if not content:
                raise ValueError("OpenAI response did not include content")
            return json.loads(content)
        except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError, ValueError) as error:
            logger.warning("OpenAI request failed on attempt %s: %s", attempt, error)
            if attempt == MAX_OPENAI_RETRIES:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Exceeded OpenAI retries")


def serialize_event(event: EventModel) -> Dict[str, Any]:
    data = event.dict()
    now = datetime.now(timezone.utc)
    if data.get("created_at") is None:
        data["created_at"] = now
    for key in ("start_time", "end_time", "created_at"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.astimezone(timezone.utc).isoformat()
    data["updated_at"] = now.isoformat()
    if data.get("tags") is None:
        data["tags"] = []
    return data


def find_existing_item(table, email_id: str, source_name: Optional[str], start_time: Optional[str]) -> Optional[Dict[str, Any]]:
    if start_time:
        query_kwargs = {
            "IndexName": "start_time-index",
            "KeyConditionExpression": Key("start_time").eq(start_time),
        }
        response = table.query(**query_kwargs)
        for item in response.get("Items", []):
            if item.get("email_id") == email_id and item.get("source_name") == source_name:
                return item
    scan_kwargs = {"FilterExpression": Attr("email_id").eq(email_id)}
    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get("Items", []):
            if item.get("source_name") == source_name:
                return item
        if "LastEvaluatedKey" not in response:
            items = response.get("Items", [])
            if items:
                return items[0]
            break
        scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return None


def put_event(table, item: Dict[str, Any]) -> None:
    table.put_item(Item=item)


def process_messages(table_name: str, query: str = "label:Events") -> Dict[str, int]:
    table = DYNAMODB.Table(table_name)
    openai_api_key = load_openai_api_key()
    gmail_credentials = load_gmail_credentials()
    gmail_service = build_gmail_service(gmail_credentials)

    try:
        messages = list_gmail_messages(gmail_service, query)
    except Exception as error:  # pragma: no cover - surfaced via logs
        logger.exception("Failed to list Gmail messages: %s", error)
        raise

    processed = created = updated = failed = deduplicated = 0

    for message_meta in messages:
        message_id = message_meta.get("id")
        if not message_id:
            continue
        processed += 1
        try:
            email_text = fetch_message_body(gmail_service, message_id)
            if not email_text:
                logger.info("Skipping message %s due to empty body", message_id)
                continue
            openai_payload = call_openai(openai_api_key, email_text, message_id)
            try:
                event_model = EventModel(**openai_payload)
            except ValidationError as validation_error:
                failed += 1
                logger.warning(
                    "Skipping message %s due to validation error: %s",
                    message_id,
                    validation_error,
                )
                continue
            event_data = serialize_event(event_model)
            start_time = event_data.get("start_time")
            source_name = event_data.get("source_name")
            existing = find_existing_item(
                table, event_data["email_id"], source_name, start_time
            )
            if existing:
                event_data["id"] = existing["id"]
                put_event(table, event_data)
                updated += 1
                deduplicated += 1
            else:
                event_data["id"] = str(uuid.uuid4())
                put_event(table, event_data)
                created += 1
        except Exception as error:  # pylint: disable=broad-except
            failed += 1
            logger.exception("Processing failed for message %s: %s", message_id, error)
            continue

    summary = {
        "processed": processed,
        "created": created,
        "updated": updated,
        "deduplicated": deduplicated,
        "failed": failed,
    }
    logger.info("Processing summary: %s", summary)
    return summary


def run() -> Dict[str, int]:
    table_name = os.environ["TABLE_NAME"]
    query = os.getenv("GMAIL_QUERY", "label:Events")
    return process_messages(table_name=table_name, query=query)


def handler(event, context):  # pragma: no cover - retained for compatibility
    return run()


if __name__ == "__main__":
    run()
