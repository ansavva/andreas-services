import pytest

from website_core.adapters import kit
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
