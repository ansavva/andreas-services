"""`profiles` — which stack an invocation is talking to.

The resolution order is the subject. Everything else in this module is a
consequence of it, and it is the part that is dangerous to get wrong: the two
directions differ, deliberately, and each direction has a way of being silently
wrong that these tests exist to catch.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from studio_pipeline import cli, profiles


@pytest.fixture
def two_profiles():
    """A dev and a prod profile, as `studio profile sync` would have written them."""
    profiles.save("dev", {
        "api_url": "http://localhost:8000",
        "cognito_user_pool_id": "us-east-1_dev",
        "cognito_client_id": "client-dev",
        "s3_bucket": "studio-dev-abc123456789-media-us-east-1",
        "catalog_table": "studio-dev-abc123456789-catalog",
        "source": "terraform:studio/dev/…",
    })
    profiles.save("prod", {
        "api_url": "https://studio-api.andreas.services",
        "cognito_user_pool_id": "us-east-1_prod",
        "cognito_client_id": "client-prod",
        "s3_bucket": "studio-prod-media-us-east-1",
        "catalog_table": "studio-prod-catalog",
        "source": "ssm:/studio/prod",
    })


# ── the resolution order ────────────────────────────────────────────────────


def test_an_explicit_profile_beats_an_exported_variable(two_profiles, monkeypatch):
    """**The direction that matters, and the one that is unlike the AWS CLI.**

    `dev-up.sh` exports STUDIO_API_URL and both Cognito ids into the shell it
    runs in. If an exported variable beat an explicit `--profile prod`, typing
    that in such a shell would keep talking to dev — you would believe you were
    looking at production and you would not be.
    """
    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:8000")
    monkeypatch.setenv("STUDIO_S3_BUCKET", "studio-dev-abc123456789-media-us-east-1")

    profiles.select("prod")

    assert profiles.value("api_url") == "https://studio-api.andreas.services"
    assert profiles.value("s3_bucket") == "studio-prod-media-us-east-1"
    assert profiles.value("catalog_table") == "studio-prod-catalog"


def test_an_override_is_announced_on_stderr(two_profiles, monkeypatch, capsys):
    """Silence is what would make the override rule dangerous rather than safe."""
    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:8000")
    profiles.select("prod")

    profiles.value("api_url")
    first = capsys.readouterr().err
    assert "--profile prod overrides $STUDIO_API_URL" in first
    assert "http://localhost:8000" in first

    # Once per process, not once per call: a command making forty API calls
    # must not print the same notice forty times.
    profiles.value("api_url")
    assert capsys.readouterr().err == ""


def test_agreement_is_not_announced(two_profiles, monkeypatch, capsys):
    monkeypatch.setenv("STUDIO_API_URL", "https://studio-api.andreas.services/")
    profiles.select("prod")

    profiles.value("api_url")

    assert capsys.readouterr().err == ""


def test_without_a_selection_the_environment_wins(two_profiles, monkeypatch):
    """The path every existing caller is on, and it must not change.

    `dev-up.sh`, `backend/tests/integration/conftest.py` and this suite's own
    conftest all set the variables directly and none of them passes a profile.
    """
    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:9999")
    profiles.set_current("prod")

    assert profiles.resolve("api_url") == ("http://localhost:9999", "$STUDIO_API_URL")


def test_without_a_selection_the_current_profile_answers(two_profiles, monkeypatch):
    monkeypatch.delenv("STUDIO_API_URL", raising=False)
    profiles.set_current("prod")

    assert profiles.resolve("api_url") == (
        "https://studio-api.andreas.services", "profile prod")


def test_the_default_profile_is_dev(two_profiles, monkeypatch):
    """Not prod, and never prod. `auth.DEFAULT_API_URL` used to make it prod."""
    monkeypatch.delenv("STUDIO_API_URL", raising=False)

    assert profiles.current() == "dev"
    assert profiles.resolve("api_url") == ("http://localhost:8000", "profile dev")


def test_nothing_anywhere_is_a_refusal_that_names_both_commands(monkeypatch):
    for field in profiles.FIELDS:
        monkeypatch.delenv(profiles.ENV_VAR[field], raising=False)

    assert profiles.resolve("s3_bucket") == ("", "unset")

    with pytest.raises(SystemExit):
        profiles.value("s3_bucket")
    message = profiles.missing("s3_bucket")
    assert "--profile dev" in message and "--profile prod" in message


def test_a_selected_profile_that_defines_nothing_says_how_to_fill_it(monkeypatch):
    monkeypatch.setenv("STUDIO_S3_BUCKET", "studio-dev-abc123456789-media-us-east-1")
    profiles.select("staging")

    assert profiles.resolve("s3_bucket") == ("", "profile staging")
    assert "studio profile sync staging" in profiles.missing("s3_bucket")


# ── the file ────────────────────────────────────────────────────────────────


def test_the_meta_section_is_not_a_profile(two_profiles):
    """`current` is stored in `[studio]`, which must never list as an environment.

    A real `[DEFAULT]` would be wrong for the same reason: configparser copies
    its keys into every other section, so `current = prod` would show up as a
    field of every profile.
    """
    profiles.set_current("prod")

    assert profiles.names() == ["dev", "prod"]
    with pytest.raises(profiles.ProfileError):
        profiles.save(profiles.META_SECTION, {"api_url": "http://x"})


def test_saving_one_profile_leaves_the_other_alone(two_profiles):
    profiles.save("dev", {"api_url": "http://localhost:5000"})

    assert profiles.fields("dev")["api_url"] == "http://localhost:5000"
    assert profiles.fields("dev")["s3_bucket"] == "studio-dev-abc123456789-media-us-east-1"
    assert profiles.fields("prod")["api_url"] == "https://studio-api.andreas.services"


def test_using_a_profile_that_does_not_exist_is_refused(two_profiles):
    with pytest.raises(profiles.ProfileError):
        profiles.set_current("staging")


def test_a_half_made_profile_is_never_written():
    """A sync that could not read every field must write nothing.

    Four correct values and one missing is the shape that produces a command
    talking to two stacks at once, which is the failure the whole module exists
    to remove.
    """
    with pytest.raises(profiles.ProfileError) as caught:
        profiles._require_complete("prod", {"api_url": "https://x", "s3_bucket": "b"})

    assert "cognito_user_pool_id" in str(caught.value)


def test_sync_prod_reads_the_deploy_workflows_ssm_parameters(monkeypatch):
    """SSM, not Terraform state — these are what the *deploy* wrote.

    So they cannot drift from what is actually serving, which is the mirror of
    the argument for reading dev's values from Terraform: nothing deploys a dev
    stack, and nothing but the deploy writes these.
    """
    page = {"Parameters": [
        {"Name": "/studio/prod/api-domain", "Value": "https://studio-api.andreas.services"},
        {"Name": "/studio/prod/cognito-user-pool-id", "Value": "us-east-1_prod"},
        {"Name": "/studio/prod/cognito-client-id", "Value": "client-prod"},
        {"Name": "/studio/prod/media-bucket", "Value": "studio-prod-media-us-east-1"},
        {"Name": "/studio/prod/catalog-table", "Value": "studio-prod-catalog"},
        {"Name": "/studio/prod/cf-dist-id", "Value": "EXAMPLE"},
    ]}

    class _Session:
        def client(self, name):  # noqa: ARG002
            return _Ssm()

    class _Ssm:
        def get_parameters_by_path(self, **kwargs):  # noqa: ARG002
            return page

    monkeypatch.setattr(profiles, "aws_session", _Session)

    values = profiles.sync_prod()

    assert values["api_url"] == "https://studio-api.andreas.services"
    assert values["catalog_table"] == "studio-prod-catalog"
    assert values["source"] == "ssm:/studio/prod"
    # `cf-dist-id` and `app-bucket` are in that path and are not profile fields.
    assert set(values) == set(profiles.FIELDS) | {"source"}


# ── through the CLI ─────────────────────────────────────────────────────────


def test_the_root_option_selects_before_any_subcommand_runs(two_profiles):
    """The reason `s3.BUCKET` and `ddb.TABLE` had to stop being module constants.

    A constant is bound at import, which is before Click has parsed a single
    argument, so it could never reflect `--profile`.
    """
    seen = {}

    @cli.main.command("probe-target", hidden=True)
    def _probe():
        seen["bucket"] = profiles.value("s3_bucket")

    try:
        result = CliRunner().invoke(cli.main, ["--profile", "prod", "probe-target"])
        assert result.exit_code == 0, result.output
        assert seen["bucket"] == "studio-prod-media-us-east-1"
    finally:
        cli.main.commands.pop("probe-target")


def test_studio_profile_reads_as_an_environment_selection(two_profiles, monkeypatch):
    """`STUDIO_PROFILE=prod studio …` and `studio --profile prod …` are one path.

    Click puts group options before the subcommand, so the variable is the only
    way to write it the other way round.
    """
    monkeypatch.setenv("STUDIO_PROFILE", "prod")
    seen = {}

    @cli.main.command("probe-env", hidden=True)
    def _probe():
        seen["table"] = profiles.value("catalog_table")

    try:
        result = CliRunner().invoke(cli.main, ["probe-env"])
        assert result.exit_code == 0, result.output
        assert seen["table"] == "studio-prod-catalog"
    finally:
        cli.main.commands.pop("probe-env")


def test_profile_list_marks_the_one_in_force(two_profiles):
    result = CliRunner().invoke(cli.main, ["--profile", "prod", "profile", "list"])

    assert result.exit_code == 0, result.output
    assert "* prod" in result.output
    assert "  dev" in result.output


def test_profile_show_says_where_each_value_came_from(two_profiles, monkeypatch):
    monkeypatch.setenv("STUDIO_S3_BUCKET", "something-a-shell-exported")

    result = CliRunner().invoke(cli.main, ["profile", "show"])

    assert result.exit_code == 0, result.output
    assert "$STUDIO_S3_BUCKET" in result.output
    assert "profile dev" in result.output


def test_profile_show_refuses_a_name_that_does_not_exist(two_profiles):
    result = CliRunner().invoke(cli.main, ["profile", "show", "staging"])

    assert result.exit_code != 0
    assert "studio profile sync staging" in result.output


def test_profile_sync_refuses_a_name_with_no_known_source(two_profiles):
    result = CliRunner().invoke(cli.main, ["profile", "sync", "staging"])

    assert result.exit_code != 0
    assert "dev, prod" in result.output
