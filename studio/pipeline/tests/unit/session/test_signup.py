"""`studio signup` — four steps, one command, and the order they run in.

Cognito is a fake at `adapters/auth._cognito`, as in `test_auth.py`; the API is
`tests/support/fake_api`. What is asserted is the sequence — register, confirm,
sign in, create the library — and that a failure late in it leaves the person
with a signed-in account rather than nothing.
"""

from __future__ import annotations

import base64
import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, auth


def _jwt(**claims) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{body}.signature"


class _Pool:
    """Records every call; refuses the wrong invite code and the wrong code."""

    def __init__(self):
        self.calls: list[tuple] = []

    def user(self, username=None):
        pool = self

        class _User:
            id_token = _jwt(email=username, sub="s-new", token_use="id",
                            iss="https://x/us-east-1_fake")
            refresh_token = "r-1"

            def set_base_attributes(self, **attributes):
                pool.calls.append(("attributes", attributes))

            def register(self, u, password, attr_map=None, client_metadata=None):  # noqa: ARG002
                pool.calls.append(("register", u, client_metadata))
                if client_metadata.get("invite_code") != "open-sesame":
                    raise type("UserLambdaValidationException", (Exception,), {})(
                        "PreSignUp failed with error Studio is invite-only."
                    )
                return {"CodeDeliveryDetails": {"Destination": "n***@s***"}}

            def confirm_sign_up(self, code, username=None):  # noqa: ARG002
                pool.calls.append(("confirm", code))
                if code != "424242":
                    raise type("CodeMismatchException", (Exception,), {})("no")

            def resend_confirmation_code(self, u):
                pool.calls.append(("resend", u))

            def authenticate(self, password):
                pool.calls.append(("authenticate", password))

        return _User()


@pytest.fixture
def pool(monkeypatch):
    fake = _Pool()
    monkeypatch.setattr(auth, "_cognito", fake.user)
    return fake


def _run(argv, input_text, env=None):
    return CliRunner().invoke(cli.main, ["signup", *argv], input=input_text, env=env or {})


def test_the_happy_path_registers_confirms_signs_in_and_makes_a_library(fake_api, pool):
    result = _run(
        ["--email", "new@studio.test", "--library", "Mine"],
        # password, password again, invite code, confirmation code
        "Correct-horse-1\nCorrect-horse-1\nopen-sesame\n424242\n",
    )

    assert result.exit_code == 0, result.output
    assert [call[0] for call in pool.calls] == [
        "attributes", "register", "confirm", "authenticate",
    ]
    assert pool.calls[1][2] == {"invite_code": "open-sesame"}
    assert "sent to n***@s***" in result.output
    assert "Signed in as new@studio.test" in result.output
    assert "library  Mine  (lib-created, owner)" in result.output
    # Nothing secret is echoed.
    assert "Correct-horse-1" not in result.output
    assert "open-sesame" not in result.output


def test_a_wrong_invite_code_stops_before_anything_is_made(fake_api, pool):
    result = _run(
        ["--email", "new@studio.test", "--library", "Mine"],
        "Correct-horse-1\nCorrect-horse-1\nwrong\n",
    )

    assert result.exit_code == 1
    assert "invite-only" in result.output
    assert [call[0] for call in pool.calls] == ["attributes", "register"]


def test_the_password_and_invite_code_come_from_the_environment(fake_api, pool):
    """Non-interactive provisioning: neither is prompted for when exported."""
    result = _run(
        ["--email", "new@studio.test", "--library", "Mine"],
        "424242\n",
        env={"STUDIO_PASSWORD": "Correct-horse-1", "STUDIO_INVITE_CODE": "open-sesame"},
    )

    assert result.exit_code == 0, result.output
    assert ("authenticate", "Correct-horse-1") in pool.calls


def test_resume_skips_registration_and_resends_the_code(fake_api, pool):
    result = _run(
        ["--email", "new@studio.test", "--library", "Mine", "--resume"],
        "424242\n",
        env={"STUDIO_PASSWORD": "Correct-horse-1"},
    )

    assert result.exit_code == 0, result.output
    assert [call[0] for call in pool.calls] == ["resend", "confirm", "authenticate"]


def test_the_library_name_defaults_to_the_address(fake_api, pool):
    result = _run(
        ["--email", "ada@studio.test"],
        # accept the default at the library prompt
        "424242\n\n",
        env={"STUDIO_PASSWORD": "Correct-horse-1", "STUDIO_INVITE_CODE": "open-sesame"},
    )

    assert result.exit_code == 0, result.output
    assert "library  ada's library" in result.output


def test_a_library_failure_leaves_a_signed_in_account(fake_api, pool, monkeypatch):
    """The library is last so that this is the worst case: signed in, empty."""

    def refuse(name):  # noqa: ARG001
        raise api.ApiError("catalog is down", 502)

    monkeypatch.setattr(api, "create_library", refuse)

    result = _run(
        ["--email", "new@studio.test", "--library", "Mine"],
        "424242\n",
        env={"STUDIO_PASSWORD": "Correct-horse-1", "STUDIO_INVITE_CODE": "open-sesame"},
    )

    assert result.exit_code == 1
    assert "Signed in, but could not create the library" in result.output
    assert ("authenticate", "Correct-horse-1") in pool.calls
    assert auth.whoami()["email"] == "new@studio.test"
