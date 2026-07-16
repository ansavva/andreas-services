import json

import pytest


@pytest.fixture(autouse=True)
def local_registry(monkeypatch):
    monkeypatch.setenv(
        "MAILER_DEVELOPMENT_SERVICES_JSON",
        json.dumps(
            {
                "humbugg": {
                    "sender_name": "Humbugg",
                    "sender_address": "no-reply@humbugg.com",
                    "allowed_categories": ["invitation", "reminder"],
                    "allowed_message_classes": ["exchange"],
                }
            }
        ),
    )
