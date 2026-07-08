"""Unit tests for the Gmail ingestion layer (gmail.py) with a stub service.

No live Gmail access: a FakeService mimics the slice of the API the module uses
(labels.list, messages.list, messages.get), so discovery, per-domain fetching,
and MIME/markdown extraction can be exercised in isolation.
"""

import base64
import os
import unittest

os.environ.setdefault("SCOUT_TABLE_SUFFIX", "")

from scout_core.clients.external import gmail  # noqa: E402
from scout_core.utils import taxonomy  # noqa: E402


def _b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _message(msg_id, sender, *, subject="Subj", html=None, plain=None):
    parts = []
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(plain)}})
    return {
        "id": msg_id,
        "payload": {
            "headers": [{"name": "Subject", "value": subject},
                        {"name": "From", "value": sender}],
            "parts": parts,
        },
    }


class FakeService:
    """Minimal stand-in for the Gmail API client. labels()/messages() set the
    mode so the shared list()/execute() chain resolves to the right resource."""

    def __init__(self, messages, *, label_name="Events"):
        self._messages = {m["id"]: m for m in messages}
        self._label_name = label_name
        self._mode = None
        self._pending = None

    def users(self):
        return self

    def labels(self):
        self._mode = "labels"
        return self

    def messages(self):
        self._mode = "messages"
        return self

    def list(self, *, userId, labelIds=None, q=None, maxResults=None):
        self._pending = ("list", q)
        return self

    def get(self, *, userId, id, format=None):
        self._pending = ("get", id)
        return self

    def execute(self):
        if self._mode == "labels":
            return {"labels": [{"id": "L1", "name": self._label_name}]}
        kind, arg = self._pending
        if kind == "get":
            return self._messages[arg]
        ids = list(self._messages)
        if arg and "from:" in arg:
            domain = arg.split("from:", 1)[1].split()[0]
            ids = [mid for mid, m in self._messages.items()
                   if taxonomy.sender_domain(_from(m)) == domain]
        return {"messages": [{"id": mid} for mid in ids]}


def _from(message):
    for h in message["payload"]["headers"]:
        if h["name"] == "From":
            return h["value"]
    return ""


class TestSenderDomain(unittest.TestCase):
    def test_parses_domain_from_angle_address(self):
        self.assertEqual(taxonomy.sender_domain("Venue <hi@Example.com>"), "example.com")

    def test_strips_www(self):
        self.assertEqual(taxonomy.sender_domain("a@www.foo.org"), "foo.org")

    def test_empty_without_at(self):
        self.assertEqual(taxonomy.sender_domain("not-an-email"), "")


class TestExtractContent(unittest.TestCase):
    def test_html_converted_to_markdown_and_image_picked(self):
        html = ('<html><body><img src="https://cdn.example.com/poster.jpg">'
                '<h1>Jazz Night</h1><p>Doors 8pm</p></body></html>')
        content = gmail.extract_content(_message("m1", "x@example.com", html=html))
        self.assertIn("Jazz Night", content["body_markdown"])
        self.assertEqual(content["image_url"], "https://cdn.example.com/poster.jpg")
        self.assertEqual(content["sender"], "x@example.com")

    def test_tracking_pixel_skipped(self):
        html = '<img src="https://t.co/tracking.gif"><p>hi</p>'
        content = gmail.extract_content(_message("m1", "x@example.com", html=html))
        self.assertEqual(content["image_url"], "")

    def test_plain_text_fallback(self):
        content = gmail.extract_content(_message("m1", "x@example.com", plain="just text"))
        self.assertEqual(content["body_markdown"].strip(), "just text")

    def test_links_extracted_and_junk_dropped(self):
        html = ('<p><a href="https://offsite.com/jazz">Tickets</a></p>'
                '<p><a href="https://mailchi.mp/x/unsubscribe">Unsubscribe</a></p>'
                '<p><a href="https://instagram.com/venue">IG</a></p>')
        content = gmail.extract_content(_message("m1", "x@example.com", html=html))
        self.assertEqual(content["links"], ["https://offsite.com/jazz"])

    def test_body_cap_is_generous(self):
        big = "<p>" + ("event " * 5000) + "</p>"
        content = gmail.extract_content(_message("m1", "x@example.com", html=big))
        # Old cap was 6000 chars; the body should now exceed it.
        self.assertGreater(len(content["body_markdown"]), 6000)


class TestDiscoverAndFetch(unittest.TestCase):
    def setUp(self):
        self.service = FakeService([
            _message("a", "Eventbrite <no-reply@eventbrite.com>", html="<p>A</p>"),
            _message("b", "hi@eventbrite.com", html="<p>B</p>"),
            _message("c", "shows@venue.org", html="<p>C</p>"),
        ])

    def test_discover_domains_dedups_by_domain(self):
        domains = gmail.discover_domains(service=self.service, since_epoch=0)
        self.assertEqual(domains, ["eventbrite.com", "venue.org"])

    def test_fetch_for_domain_filters_to_that_domain(self):
        msgs = gmail.fetch_for_domain("eventbrite.com", service=self.service, since_epoch=0)
        self.assertEqual({m["message_id"] for m in msgs}, {"a", "b"})
        self.assertTrue(all("body_markdown" in m for m in msgs))


if __name__ == "__main__":
    unittest.main()
