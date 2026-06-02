"""Unit tests for the headless-render fetch backend (renderer_client.py)."""

import io
import json
import os
import unittest
from unittest import mock

from scout_core.adapters import renderer_client


def _payload(obj):
    """Build a fake boto3 Lambda invoke response wrapping `obj` as the payload."""
    return {"Payload": io.BytesIO(json.dumps(obj).encode())}


class TestRendererClient(unittest.TestCase):
    def setUp(self):
        renderer_client._lambda = None
        os.environ["SCOUT_RENDERER_FN"] = "scout-source-renderer-test"

    def tearDown(self):
        os.environ.pop("SCOUT_RENDERER_FN", None)

    def test_success_returns_status_and_html(self):
        fake = mock.Mock()
        fake.invoke.return_value = _payload(
            {"status": 200, "html": "<html>hi</html>", "final_url": "https://x"})
        with mock.patch.object(renderer_client, "_client", return_value=fake):
            status, html = renderer_client.fetch_rendered("https://x", timeout=5)
        self.assertEqual(status, 200)
        self.assertEqual(html, "<html>hi</html>")
        # url + timeout (ms) are forwarded to the renderer.
        sent = json.loads(fake.invoke.call_args.kwargs["Payload"])
        self.assertEqual(sent, {"url": "https://x", "timeout_ms": 5000})

    def test_error_payload_raises(self):
        fake = mock.Mock()
        fake.invoke.return_value = _payload({"status": 0, "error": "boom"})
        with mock.patch.object(renderer_client, "_client", return_value=fake):
            with self.assertRaises(RuntimeError):
                renderer_client.fetch_rendered("https://x")

    def test_function_error_raises(self):
        fake = mock.Mock()
        resp = _payload({"errorMessage": "unhandled"})
        resp["FunctionError"] = "Unhandled"
        fake.invoke.return_value = resp
        with mock.patch.object(renderer_client, "_client", return_value=fake):
            with self.assertRaises(RuntimeError):
                renderer_client.fetch_rendered("https://x")

    def test_unconfigured_renderer_raises(self):
        os.environ.pop("SCOUT_RENDERER_FN", None)
        with self.assertRaises(RuntimeError):
            renderer_client.fetch_rendered("https://x")


if __name__ == "__main__":
    unittest.main()
