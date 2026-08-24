"""`adapters/auth` — the CLI's session, holding no AWS credentials (#300)."""

from __future__ import annotations

import base64
import json
import stat

import pytest

from studio_pipeline import profiles
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
    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:8000")


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

    assert "studio --profile dev login" in str(caught.value)


def test_an_unreadable_stored_token_does_not_break_logout(monkeypatch):
    """**`logout` is the command for getting rid of a bad session.**

    So it must survive one. Filing a pre-profile file by its issuer means
    decoding the token, and `claims` splits on "." and indexes [1] — a truncated
    or hand-edited file raises `IndexError`, which turned `studio logout` into a
    traceback and left the bad file exactly where it was.
    """
    auth.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    auth.CREDENTIALS_FILE.write_text(json.dumps({"id_token": "not-a-jwt",
                                                 "refresh_token": "r"}))

    assert auth.sessions() == {"dev"}
    assert auth.logout() is True
    assert not auth.CREDENTIALS_FILE.exists()


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


def test_the_api_url_has_no_default_at_all(monkeypatch):
    """**It used to default to `https://studio-api.andreas.services`.**

    Which meant a shell with nothing set — no `dev-up.sh`, no profile — pointed
    the CLI at PRODUCTION, the exact opposite of what `studio/CLAUDE.md` says
    the CLI does. Unset is a refusal now, the same shape #434 gave the bucket
    and the catalog table.
    """
    monkeypatch.delenv("STUDIO_API_URL", raising=False)

    with pytest.raises(auth.AuthError) as caught:
        auth.api_url()
    assert "studio-api.andreas.services" not in str(caught.value)

    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:8000/")
    assert auth.api_url() == "http://localhost:8000"


def test_a_session_is_stored_per_profile(monkeypatch):
    """Signing in to one profile must not sign you out of another.

    One credentials file per machine and one flat session in it meant a prod
    login silently replaced the dev one for every shell, indefinitely — the
    target outliving the shell that chose it, which is the whole thing a
    profile exists to prevent.
    """
    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser())
    auth.login("dev@studio.test", "hunter2")

    profiles.select("prod")
    with pytest.raises(auth.AuthError):
        auth.whoami()
    auth.login("prod@studio.test", "hunter2")
    assert auth.sessions() == {"dev", "prod"}

    assert auth.logout() is True
    assert auth.sessions() == {"dev"}

    profiles.select(None)
    assert auth.whoami()["profile"] == "dev"


def test_a_pre_profile_credentials_file_is_filed_by_its_issuer(monkeypatch, tmp_path):
    """The flat shape still on every machine today, moved by the token's `iss`.

    Filed by the pool that minted it rather than by whichever profile happens
    to be current — otherwise a first-ever `--profile prod` invocation inherits
    the dev session and reports itself signed in to production.
    """
    profiles.save("dev", {"cognito_user_pool_id": "us-east-1_fake",
                          "api_url": "http://localhost:8000"})
    profiles.save("prod", {"cognito_user_pool_id": "us-east-1_real",
                           "api_url": "https://studio-api.andreas.services"})
    auth.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    auth.CREDENTIALS_FILE.write_text(json.dumps(
        {"id_token": _FakeUser.ID_TOKEN, "refresh_token": "r", "username": "dev@studio.test"}))

    profiles.select("prod")
    assert auth.sessions() == {"dev"}
    with pytest.raises(auth.AuthError):
        auth.whoami()

    profiles.select("dev")
    assert auth.whoami()["email"] == "dev@studio.test"


def test_refresh_replaces_the_stored_id_token(monkeypatch):
    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser())
    auth.login("dev@studio.test", "hunter2")
    assert auth.id_token() == _FakeUser.ID_TOKEN

    monkeypatch.setattr(auth, "_cognito", lambda username=None: _FakeUser(refreshed=True))
    refreshed = auth.id_token(refresh=True)

    assert refreshed == _FakeUser.REFRESHED_TOKEN
    stored = json.loads(auth.CREDENTIALS_FILE.read_text())["profiles"]["dev"]
    assert stored["id_token"] == refreshed


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
