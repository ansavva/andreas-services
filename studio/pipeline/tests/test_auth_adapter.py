"""`adapters/auth` — the CLI's session, holding no AWS credentials (#300)."""

from __future__ import annotations

import base64
import json
import stat

import pytest

from studio_pipeline.adapters import auth


def _jwt(**claims) -> str:
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{body}.signature"


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_DIR", tmp_path / "studio")
    monkeypatch.setattr(auth, "CREDENTIALS_FILE", tmp_path / "studio" / "credentials")
    monkeypatch.setenv("STUDIO_COGNITO_USER_POOL_ID", "us-east-1_fake")
    monkeypatch.setenv("STUDIO_COGNITO_CLIENT_ID", "client-1")


def test_claims_decodes_a_padless_payload():
    """A JWT payload is base64url with the padding stripped; forgetting that raises."""
    token = _jwt(email="dev@studio.test", sub="s-1", token_use="id")

    assert auth.claims(token)["email"] == "dev@studio.test"


def test_credentials_are_written_600(monkeypatch):
    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser())

    auth.login("dev@studio.test", "hunter2")

    mode = auth.CREDENTIALS_FILE.stat().st_mode
    assert stat.S_IMODE(mode) == 0o600
    assert not mode & (stat.S_IRGRP | stat.S_IROTH)


def test_the_password_is_not_stored(monkeypatch):
    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser())

    auth.login("dev@studio.test", "hunter2")

    assert "hunter2" not in auth.CREDENTIALS_FILE.read_text()


def test_whoami_reads_the_stored_token(monkeypatch):
    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser())
    auth.login("dev@studio.test", "hunter2")

    who = auth.whoami()

    assert who["email"] == "dev@studio.test"
    assert who["pool"] == "us-east-1_fake"


def test_whoami_without_a_session_says_what_to_run():
    with pytest.raises(auth.AuthError) as caught:
        auth.whoami()

    assert "studio login" in str(caught.value)


def test_logout_reports_whether_there_was_a_session(monkeypatch):
    assert auth.logout() is False

    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser())
    auth.login("dev@studio.test", "hunter2")

    assert auth.logout() is True
    assert not auth.CREDENTIALS_FILE.exists()


def test_a_failed_sign_in_never_quotes_the_error(monkeypatch):
    """botocore puts the username in some messages, and this runs in pasteable terminals."""

    class _Boom:
        def authenticate(self, password):  # noqa: ARG002
            raise RuntimeError("NotAuthorizedException: dev@studio.test is wrong")

    monkeypatch.setattr(auth, "_cognito", lambda username=None: _Boom())

    with pytest.raises(auth.AuthError) as caught:
        auth.login("dev@studio.test", "hunter2")

    assert "dev@studio.test" not in str(caught.value)
    assert "RuntimeError" in str(caught.value)


def test_a_missing_pool_names_the_variables(monkeypatch):
    monkeypatch.delenv("STUDIO_COGNITO_USER_POOL_ID", raising=False)

    with pytest.raises(auth.AuthError) as caught:
        auth.login("dev@studio.test", "hunter2")

    assert "STUDIO_COGNITO_USER_POOL_ID" in str(caught.value)


def test_the_api_url_defaults_to_prod_and_is_overridable(monkeypatch):
    monkeypatch.delenv("STUDIO_API_URL", raising=False)
    assert auth.api_url() == "https://studio-api.andreas.services"

    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:8000/")
    assert auth.api_url() == "http://localhost:8000"


def test_refresh_replaces_the_stored_id_token(monkeypatch):
    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser())
    auth.login("dev@studio.test", "hunter2")
    assert auth.id_token() == _FakeUser.ID_TOKEN

    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser(refreshed=True))
    refreshed = auth.id_token(refresh=True)

    assert refreshed == _FakeUser.REFRESHED_TOKEN
    assert json.loads(auth.CREDENTIALS_FILE.read_text())["id_token"] == refreshed


class _FakeUser:
    """Stands in for `pycognito.Cognito`. Never reaches the network."""

    ID_TOKEN = _jwt(email="dev@studio.test", sub="s-1", token_use="id", iss="https://x/us-east-1_fake")
    REFRESHED_TOKEN = _jwt(email="dev@studio.test", sub="s-1", token_use="id", iss="https://x/us-east-1_fake", exp=2)

    def __init__(self, refreshed: bool = False) -> None:
        self.id_token = self.REFRESHED_TOKEN if refreshed else self.ID_TOKEN
        self.refresh_token = "refresh-1"

    def authenticate(self, password):  # noqa: ARG002
        return None

    def renew_access_token(self):
        return None
