"""
Gmail ingestion for email sources.

Our code (not the agent) acquires email content: it authenticates to Gmail with
an OAuth refresh token, finds messages under the "Events" label, and converts
each message body to markdown. Two entry points back the email-source model:

- discover_domains(): the distinct sender domains seen under the Events label,
  driving auto-creation of one email source per domain.
- fetch_for_domain(): the recent Events-labeled messages from one sender domain,
  returned as pages for the extraction agent.

The Gmail service is injectable (the `service` argument) so the pipeline and
tests can supply a stub; the default lazily builds a real client from the
GMAIL_* environment credentials. The google client libraries are imported lazily
inside build_service() so importing this module never requires them.
"""

import base64
import os
import re
from datetime import datetime, timedelta, timezone

from scout_core.adapters import fetcher
from scout_core.common import taxonomy

EVENTS_LABEL = "Events"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_LOOKBACK_DAYS = 7
MAX_MESSAGES = int(os.environ.get("MAX_EMAILS_PER_RUN", "20"))
MAX_BODY_CHARS = int(os.environ.get("MAX_EMAIL_BODY_CHARS", "20000"))

_TRACKING_PIXEL_SIGNALS = (
    "pixel.", "tracking.", "/open.", "/beacon", "1x1", "spacer", "blank.gif",
    "track.",
)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

_service = None


# ---------------------------------------------------------------------------
# Service (lazy; injectable for tests)
# ---------------------------------------------------------------------------

def build_service():
    """Authenticated Gmail API client from the GMAIL_* env credentials."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        scopes=GMAIL_SCOPES,
    )
    if not creds.valid:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _svc(service):
    global _service
    if service is not None:
        return service
    if _service is None:
        _service = build_service()
    return _service


# ---------------------------------------------------------------------------
# Gmail API helpers
# ---------------------------------------------------------------------------

def _label_id(service):
    result = service.users().labels().list(userId="me").execute()
    for label in result.get("labels", []):
        if label["name"].lower() == EVENTS_LABEL.lower():
            return label["id"]
    raise ValueError(f"Gmail label '{EVENTS_LABEL}' not found")


def _since_clause(since_epoch):
    if since_epoch is None:
        since_epoch = int(
            (datetime.now(timezone.utc)
             - timedelta(days=DEFAULT_LOOKBACK_DAYS)).timestamp())
    return f"after:{int(since_epoch)}"


def _list(service, label_id, *, query, max_results=MAX_MESSAGES):
    result = (
        service.users().messages()
        .list(userId="me", labelIds=[label_id], q=query, maxResults=max_results)
        .execute()
    )
    return result.get("messages", [])


def _detail(service, message_id):
    return (
        service.users().messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def _first_image_url(html):
    """First non-tracking external image URL in the HTML, or empty string."""
    for match in _IMG_SRC_RE.finditer(html or ""):
        url = match.group(1)
        if not url.startswith(("http://", "https://")):
            continue
        if any(signal in url.lower() for signal in _TRACKING_PIXEL_SIGNALS):
            continue
        return url
    return ""


def _b64(data):
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def extract_content(message):
    """Parse a Gmail message payload into a content dict: subject, sender, date,
    body_markdown (HTML preferred and converted), candidate image_url, and the
    (non-junk) links found in the body for cross-domain link-following."""
    payload = message.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
    html_body = ""
    plain_body = ""

    def walk(parts):
        nonlocal html_body, plain_body
        for part in parts:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data", "")
            if mime == "text/html" and not html_body and data:
                html_body = _b64(data)
            elif mime == "text/plain" and not plain_body and data:
                plain_body = _b64(data)
            if "parts" in part:
                walk(part["parts"])

    if "parts" in payload:
        walk(payload["parts"])
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            raw = _b64(data)
            if payload.get("mimeType") == "text/html":
                html_body = raw
            else:
                plain_body = raw

    image_url = _first_image_url(html_body) if html_body else ""
    if html_body:
        import html2text
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        body = converter.handle(html_body)
    else:
        body = plain_body

    links = [u for u in fetcher.extract_links(html_body)
             if not fetcher.is_junk_link(u)] if html_body else []

    return {
        "subject": headers.get("Subject", "(no subject)"),
        "sender": headers.get("From", ""),
        "date": headers.get("Date", ""),
        "body_markdown": body[:MAX_BODY_CHARS],
        "image_url": image_url,
        "links": links,
    }


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def discover_domains(*, service=None, since_epoch=None):
    """Distinct sender domains seen under the Events label since `since_epoch`
    (default: the last DEFAULT_LOOKBACK_DAYS days)."""
    service = _svc(service)
    label_id = _label_id(service)
    domains = set()
    for stub in _list(service, label_id, query=_since_clause(since_epoch)):
        domain = taxonomy.sender_domain(extract_content(_detail(service, stub["id"]))["sender"])
        if domain:
            domains.add(domain)
    return sorted(domains)


def fetch_for_domain(domain, *, service=None, since_epoch=None):
    """Recent Events-labeled messages from one sender domain, newest of the
    window, each as {message_id, subject, sender, date, body_markdown,
    image_url}."""
    service = _svc(service)
    label_id = _label_id(service)
    query = f"{_since_clause(since_epoch)} from:{domain}"
    messages = []
    for stub in _list(service, label_id, query=query):
        content = extract_content(_detail(service, stub["id"]))
        # Gmail's from: is fuzzy; confirm the registrable domain actually matches.
        if taxonomy.sender_domain(content["sender"]) != domain:
            continue
        messages.append({"message_id": stub["id"], **content})
    return messages
