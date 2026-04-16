"""
Gmail Email Processor Lambda Function

Fetches emails with the "Events" label from Gmail, extracts structured
event data using OpenAI GPT-3.5-turbo, and stores results in DynamoDB.

Triggered weekly via EventBridge.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
import html2text
import openai
from boto3.dynamodb.conditions import Attr
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DYNAMODB_TABLE_NAME = os.environ["DYNAMODB_TABLE_NAME"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GMAIL_CLIENT_ID = os.environ["GMAIL_CLIENT_ID"]
GMAIL_CLIENT_SECRET = os.environ["GMAIL_CLIENT_SECRET"]
GMAIL_ACCESS_TOKEN = os.environ["GMAIL_ACCESS_TOKEN"]
GMAIL_REFRESH_TOKEN = os.environ["GMAIL_REFRESH_TOKEN"]

# Constants
MAX_EMAILS_PER_RUN = int(os.environ.get("MAX_EMAILS_PER_RUN", "20"))
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
EVENTS_LABEL = "Events"

openai.api_key = OPENAI_API_KEY
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DYNAMODB_TABLE_NAME)


def get_gmail_service():
    """Build an authenticated Gmail API service client."""
    creds = Credentials(
        token=GMAIL_ACCESS_TOKEN,
        refresh_token=GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )

    if creds.expired and creds.refresh_token:
        logger.info("Refreshing expired Gmail OAuth token")
        creds.refresh(Request())

    return build("gmail", "v1", credentials=creds)


def get_events_label_id(service):
    """Retrieve the Gmail label ID for the 'Events' label."""
    result = service.users().labels().list(userId="me").execute()
    labels = result.get("labels", [])
    for label in labels:
        if label["name"].lower() == EVENTS_LABEL.lower():
            return label["id"]
    raise ValueError(f"Gmail label '{EVENTS_LABEL}' not found")


def list_recent_messages(service, label_id):
    """
    List messages from the past week tagged with the Events label.

    Returns up to MAX_EMAILS_PER_RUN message stubs.
    """
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    after_epoch = int(one_week_ago.timestamp())
    query = f"after:{after_epoch}"

    result = (
        service.users()
        .messages()
        .list(
            userId="me",
            labelIds=[label_id],
            q=query,
            maxResults=MAX_EMAILS_PER_RUN,
        )
        .execute()
    )
    return result.get("messages", [])


def get_message_detail(service, message_id):
    """Fetch full message payload for a given message ID."""
    return (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def extract_email_content(message):
    """
    Extract subject, sender, date, and body text from a Gmail message payload.

    Prefers HTML body parts and converts them to plain text; falls back to
    plain text parts.
    """
    headers = {h["name"]: h["value"] for h in message["payload"].get("headers", [])}
    subject = headers.get("Subject", "(no subject)")
    sender = headers.get("From", "unknown")
    date_str = headers.get("Date", "")

    html_body = ""
    plain_body = ""

    def walk_parts(parts):
        nonlocal html_body, plain_body
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/html" and not html_body:
                data = part.get("body", {}).get("data", "")
                if data:
                    import base64
                    html_body = base64.urlsafe_b64decode(data + "==").decode(
                        "utf-8", errors="replace"
                    )
            elif mime == "text/plain" and not plain_body:
                data = part.get("body", {}).get("data", "")
                if data:
                    import base64
                    plain_body = base64.urlsafe_b64decode(data + "==").decode(
                        "utf-8", errors="replace"
                    )
            if "parts" in part:
                walk_parts(part["parts"])

    payload = message.get("payload", {})
    if "parts" in payload:
        walk_parts(payload["parts"])
    else:
        # Single-part message
        data = payload.get("body", {}).get("data", "")
        if data:
            import base64
            raw = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            if payload.get("mimeType") == "text/html":
                html_body = raw
            else:
                plain_body = raw

    if html_body:
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        content = converter.handle(html_body)
    else:
        content = plain_body

    return subject, sender, date_str, content[:6000]  # cap to control token usage


def extract_events_with_openai(subject, sender, content):
    """
    Call OpenAI GPT-3.5-turbo to extract structured event data from email content.

    Returns a list of event dicts (an email may contain multiple events).
    """
    prompt = f"""Extract event information from this email. Return ONLY a JSON array where each element is an event object with these exact fields:
- event_name: string
- date: ISO date string (YYYY-MM-DD) or null if not found
- time: string (e.g., "7:00 PM") or null if not found
- venue: string or null if not found
- price: string or null if not found
- description: string (brief summary)
- links: array of relevant URLs found in the email

If the email contains multiple events, return one object per event.
If no events are found, return an empty array [].

Email Subject: {subject}
Email Sender: {sender}
Email Content:
{content}

Return only valid JSON array, no other text:"""

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1500,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def store_events(events, email_id, subject, sender, source_date):
    """Persist a list of extracted event dicts to DynamoDB."""
    stored = 0
    for event in events:
        event_id = str(uuid.uuid4())
        item = {
            "event_id": event_id,
            "email_id": email_id,
            "event_name": event.get("event_name", "Unknown Event"),
            "date": event.get("date") or "",
            "time": event.get("time") or "",
            "venue": event.get("venue") or "",
            "price": event.get("price") or "",
            "description": event.get("description") or "",
            "links": event.get("links") or [],
            "email_subject": subject,
            "email_sender": sender,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_email_date": source_date,
        }
        table.put_item(Item=item)
        stored += 1
        logger.info("Stored event '%s' with id %s", item["event_name"], event_id)
    return stored


def email_already_processed(email_id):
    """Check DynamoDB to see if this email has already been processed."""
    result = table.scan(
        FilterExpression=Attr("email_id").eq(email_id),
        ProjectionExpression="event_id",
        Limit=1,
    )
    return len(result.get("Items", [])) > 0


def lambda_handler(event, context):
    """Main Lambda entry point."""
    logger.info("Starting Gmail event processor")
    total_emails = 0
    total_events = 0
    errors = []

    try:
        service = get_gmail_service()
        label_id = get_events_label_id(service)
        messages = list_recent_messages(service, label_id)
        logger.info("Found %d messages to process", len(messages))

        for msg_stub in messages:
            email_id = msg_stub["id"]

            if email_already_processed(email_id):
                logger.info("Skipping already-processed email %s", email_id)
                continue

            try:
                message = get_message_detail(service, email_id)
                subject, sender, source_date, content = extract_email_content(message)
                logger.info("Processing email: %s from %s", subject, sender)

                events = extract_events_with_openai(subject, sender, content)
                if events:
                    count = store_events(events, email_id, subject, sender, source_date)
                    total_events += count
                else:
                    logger.info("No events found in email: %s", subject)

                total_emails += 1

            except json.JSONDecodeError as exc:
                logger.error("JSON parse error for email %s: %s", email_id, exc)
                errors.append({"email_id": email_id, "error": str(exc)})
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Error processing email %s: %s", email_id, exc)
                errors.append({"email_id": email_id, "error": str(exc)})

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Fatal error in lambda_handler: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }

    summary = {
        "emails_processed": total_emails,
        "events_stored": total_events,
        "errors": errors,
    }
    logger.info("Completed: %s", summary)
    return {"statusCode": 200, "body": json.dumps(summary)}
