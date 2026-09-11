"""`env_value` precedence: the environment, then `dev.env`.

`studio/.env` used to be a third source, read last; it is not read at all now.
The environment still wins so one invocation can override a file without
editing it.
"""

import studio_pipeline
from studio_pipeline import env_value

NAME = "STUDIO_TEST_ONLY_VALUE"


def _file(tmp_path, monkeypatch, *, config: str | None):
    """Point the env file at tmp_path, writing it only when asked."""
    config_file = tmp_path / "dev.env"
    if config is not None:
        config_file.write_text(f"{NAME}={config}\n")
    monkeypatch.setattr(studio_pipeline, "DEV_ENV_FILE", config_file)
    monkeypatch.delenv(NAME, raising=False)


def test_environment_beats_the_file(tmp_path, monkeypatch):
    _file(tmp_path, monkeypatch, config="from-config")
    monkeypatch.setenv(NAME, "from-environment")
    assert env_value(NAME) == "from-environment"


def test_file_read_when_the_environment_has_nothing(tmp_path, monkeypatch):
    _file(tmp_path, monkeypatch, config="from-config")
    assert env_value(NAME) == "from-config"


def test_missing_everywhere_is_none(tmp_path, monkeypatch):
    _file(tmp_path, monkeypatch, config=None)
    assert env_value(NAME) is None
