import io
import json

import pytest

from website_core.adapters import kit
from website_core.common import config
from website_core.common.errors import ValidationError
from website_core.domain import newsletter


def test_subscribe_forwards_to_kit(monkeypatch):
    seen = {}

    def fake_subscribe(email, first_name=None):
        seen["email"] = email
        seen["first_name"] = first_name
        return {"subscription": {"id": 1}}

    monkeypatch.setattr(kit, "subscribe", fake_subscribe)

    out = newsletter.subscribe({"email": "sam@acme.com", "first_name": "Sam"})
    assert out == {"status": "subscribed", "email": "sam@acme.com"}
    assert seen == {"email": "sam@acme.com", "first_name": "Sam"}


def test_subscribe_rejects_bad_email(monkeypatch):
    monkeypatch.setattr(kit, "subscribe", lambda *a, **k: pytest.fail("should not call Kit"))
    with pytest.raises(ValidationError):
        newsletter.subscribe({"email": "nope"})


def test_kit_adapter_uses_v4_form_subscribe(monkeypatch):
    """The adapter must hit Kit v4 with header auth — a v4 key on v3 401s."""
    monkeypatch.setattr(config, "kit_api_key", lambda: "kit_test_key")
    monkeypatch.setattr(config, "kit_form_id", lambda: "9652972")

    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = request.headers
        captured["body"] = json.loads(request.data.decode())
        return io.BytesIO(b'{"subscriber": {"id": 1}}')

    monkeypatch.setattr(kit.urllib.request, "urlopen", fake_urlopen)

    kit.subscribe("sam@acme.com", first_name="Sam")

    assert captured["url"] == "https://api.kit.com/v4/forms/9652972/subscribers"
    # urllib title-cases header keys
    assert captured["headers"]["X-kit-api-key"] == "kit_test_key"
    assert captured["body"] == {"email_address": "sam@acme.com", "first_name": "Sam"}
