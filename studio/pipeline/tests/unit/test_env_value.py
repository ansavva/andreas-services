"""`env_value` precedence: environment, then the config dir, then `studio/.env`.

The order is the whole point of the config-dir file, so it is worth a test
rather than a docstring. A credential moved to
`~/.config/andreas-services/studio/dev.env` has to WIN over a copy left behind
in `studio/.env` — if the repo file shadowed it, moving the token would look
like it worked while every call still carried the stale one.
"""

import studio_pipeline
from studio_pipeline import env_value

NAME = "STUDIO_TEST_ONLY_VALUE"


def _files(tmp_path, monkeypatch, *, config: str | None, repo: str | None):
    """Point both env files at tmp_path, writing only the ones asked for."""
    config_file = tmp_path / "dev.env"
    repo_file = tmp_path / ".env"
    if config is not None:
        config_file.write_text(f"{NAME}={config}\n")
    if repo is not None:
        repo_file.write_text(f"{NAME}={repo}\n")
    monkeypatch.setattr(studio_pipeline, "DEV_ENV_FILE", config_file)
    monkeypatch.setattr(studio_pipeline, "ENV_FILE", repo_file)
    monkeypatch.delenv(NAME, raising=False)


def test_environment_beats_both_files(tmp_path, monkeypatch):
    _files(tmp_path, monkeypatch, config="from-config", repo="from-repo")
    monkeypatch.setenv(NAME, "from-environment")
    assert env_value(NAME) == "from-environment"


def test_config_dir_beats_the_repo_file(tmp_path, monkeypatch):
    _files(tmp_path, monkeypatch, config="from-config", repo="from-repo")
    assert env_value(NAME) == "from-config"


def test_repo_file_still_read_when_the_config_dir_has_nothing(tmp_path, monkeypatch):
    _files(tmp_path, monkeypatch, config=None, repo="from-repo")
    assert env_value(NAME) == "from-repo"


def test_repo_file_still_read_for_a_key_the_config_dir_omits(tmp_path, monkeypatch):
    """The two files are merged per key, not chosen between.

    `dev-setup.sh` pins STUDIO_S3_BUCKET and STUDIO_CATALOG_TABLE in
    `studio/.env`; moving only the token to the config dir must not orphan them.
    """
    _files(tmp_path, monkeypatch, config="unused", repo="from-repo")
    (tmp_path / "dev.env").write_text("STUDIO_SOMETHING_ELSE=x\n")
    assert env_value(NAME) == "from-repo"


def test_missing_everywhere_is_none(tmp_path, monkeypatch):
    _files(tmp_path, monkeypatch, config=None, repo=None)
    assert env_value(NAME) is None
