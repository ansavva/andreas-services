"""The pre-sign-up trigger — the one gate between "anyone" and "an account".

Driven as Cognito drives it: an event dict in, the same dict back to allow, an
exception to refuse. No AWS is involved, which is the point of the file.
"""

import pytest

from studio_core.handlers.aws.signup import presignup_handler


def _event(code=None):
    metadata = {} if code is None else {presignup_handler.INVITE_KEY: code}
    return {
        "triggerSource": "PreSignUp_SignUp",
        "request": {"userAttributes": {"email": "x@example.com"}, "clientMetadata": metadata},
        "response": {"autoConfirmUser": False, "autoVerifyEmail": False},
    }


def test_the_right_code_lets_the_sign_up_through(monkeypatch):
    monkeypatch.setenv("STUDIO_INVITE_CODE", "open-sesame")

    event = _event("open-sesame")
    assert presignup_handler.handler(event, None) is event
    # Verification is still Cognito's: nothing here confirms the account.
    assert event["response"] == {"autoConfirmUser": False, "autoVerifyEmail": False}


@pytest.mark.parametrize("supplied", ["wrong", "", None])
def test_anything_but_the_code_is_refused(monkeypatch, supplied):
    monkeypatch.setenv("STUDIO_INVITE_CODE", "open-sesame")

    with pytest.raises(Exception, match="invite-only"):
        presignup_handler.handler(_event(supplied), None)


def test_no_configured_code_refuses_everyone(monkeypatch):
    """Closed by default: a missing secret is a pool nobody can join."""
    monkeypatch.delenv("STUDIO_INVITE_CODE", raising=False)

    with pytest.raises(Exception, match="invite-only"):
        presignup_handler.handler(_event(""), None)


def test_a_hosted_page_sign_up_carries_no_metadata_and_is_refused(monkeypatch):
    """Managed Login sends no `clientMetadata` key at all — not an empty one."""
    monkeypatch.setenv("STUDIO_INVITE_CODE", "open-sesame")
    event = _event()
    del event["request"]["clientMetadata"]

    with pytest.raises(Exception, match="invite-only"):
        presignup_handler.handler(event, None)
