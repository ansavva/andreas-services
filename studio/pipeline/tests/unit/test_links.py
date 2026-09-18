"""`links` — the CLI says where to LOOK at a run or a scene, not only its id.

Two shapes of profile are the subject: a deployed one, whose web app is derived
from the API's host, and a local one, whose web app is the Vite port. Every
command that prints a run or scene id prints the link beside it, and a JSON
document carries it as `ui` rather than as a line.

The suite's default environment sets no API URL, so the ordinary tests print no
link at all — a missing link is an empty string, never a wrong one. These set
one on purpose.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli, links, profiles
from studio_pipeline.adapters import entities as E
from studio_pipeline.domain import runs as R
from studio_pipeline.domain import scenes as SC
from studio_pipeline.domain import projects as PROJECTS
from tests.support.fake_api import BUCKET, add_run_output

PROD_WEB = "https://studio.andreas.services"
DEV_WEB = "http://localhost:5173"


@pytest.fixture
def prod_shaped(monkeypatch):
    """A prod profile as `studio profile sync prod` writes it, in force.

    Through `STUDIO_PROFILE` rather than `profiles.select`: the root group
    selects on every invocation, so a selection made before it is overwritten.
    """
    profiles.save("prod", {
        "api_url": "https://studio-api.andreas.services",
        "web_url": PROD_WEB,
        "cognito_user_pool_id": "us-east-1_prod",
        "cognito_client_id": "client-prod",
        "s3_bucket": "studio-prod-media-us-east-1",
        "catalog_table": "studio-prod-catalog",
    })
    monkeypatch.setenv("STUDIO_PROFILE", "prod")


@pytest.fixture
def dev_shaped(monkeypatch):
    """A `dev-up.sh` shell: the API URL exported, nothing said about the app."""
    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:8000")


def _draft(library, **extra) -> dict:
    return R.record_request(library.project, kind="image", engine="e",
                            model="google/nano-banana-pro",
                            input={"prompt": "a porch"}, bindings={}, **extra)


# ── deriving the web app from the API ───────────────────────────────────────


@pytest.mark.parametrize("api_url, expected", [
    ("https://studio-api.andreas.services", PROD_WEB),
    ("https://studio-api.andreas.services/", PROD_WEB),
    ("http://localhost:8000", DEV_WEB),
    ("http://localhost:8010", DEV_WEB),
    ("http://127.0.0.1:8000", DEV_WEB),
    ("https://api.example.com", ""),
    ("", ""),
])
def test_the_web_app_is_derived_from_the_api_host(api_url, expected):
    """`studio-api.<host>` → `studio.<host>`; loopback → the Vite port; else nothing.

    The app's domain is a local in `infra/envs/prod/main.tf` — not an output,
    not an SSM parameter — so a sync cannot read it and derives it instead.
    """
    assert profiles.derive_web_url(api_url) == expected


def test_a_profile_synced_before_the_field_existed_still_resolves_it():
    """Read-time derivation, and `profile show` says that is what happened."""
    profiles.save("prod", {
        "api_url": "https://studio-api.andreas.services",
        "cognito_user_pool_id": "p", "cognito_client_id": "c",
        "s3_bucket": "b", "catalog_table": "t",
    })
    profiles.select("prod")
    try:
        assert profiles.resolve("web_url") == (PROD_WEB, "derived from api_url")
    finally:
        profiles.select(None)


def test_an_exported_web_url_wins_when_no_profile_is_selected(dev_shaped, monkeypatch):
    monkeypatch.setenv("STUDIO_WEB_URL", "http://localhost:5178/")
    assert links.web_url() == "http://localhost:5178"


def test_profile_show_prints_the_web_url(prod_shaped):
    result = CliRunner().invoke(cli.main, ["profile", "show"])
    assert result.exit_code == 0, result.output
    assert "web_url" in result.output and PROD_WEB in result.output


def test_sync_prod_writes_the_derived_web_url(monkeypatch):
    page = {"Parameters": [
        {"Name": "/studio/prod/api-domain", "Value": "https://studio-api.andreas.services"},
        {"Name": "/studio/prod/cognito-user-pool-id", "Value": "us-east-1_prod"},
        {"Name": "/studio/prod/cognito-client-id", "Value": "client-prod"},
        {"Name": "/studio/prod/media-bucket", "Value": "studio-prod-media-us-east-1"},
        {"Name": "/studio/prod/catalog-table", "Value": "studio-prod-catalog"},
    ]}

    class _Session:
        def client(self, name):  # noqa: ARG002
            return _Ssm()

    class _Ssm:
        def get_parameters_by_path(self, **kwargs):  # noqa: ARG002
            return page

    monkeypatch.setattr(profiles, "aws_session", _Session)

    assert profiles.sync_prod()["web_url"] == PROD_WEB


def test_no_web_url_means_no_link_and_no_ui_field(library):
    """The suite's own environment: an unset field is silence, not a bad URL."""
    record = _draft(library)
    assert links.run(record) == ""
    assert "ui" not in links.with_ui({"id": record["id"]}, links.run(record))
    result = CliRunner().invoke(cli.main, ["runs", "show", record["id"]])
    assert result.exit_code == 0, result.output
    assert "ui" not in json.loads(result.output)


# ── the run commands ────────────────────────────────────────────────────────


def test_a_dry_run_prints_the_drafts_link_beside_submit_and_discard(library, prod_shaped,
                                                                    monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")
    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "a porch at dawn", "--key", library.face_1, "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    draft = E.query_runs(project=library.project, status="draft")["runs"][0]
    assert f"ui:          {PROD_WEB}/p/{library.project}/r/{draft['id']}" in result.output
    assert "submit it:" in result.output


def test_a_dry_run_json_carries_ui(library, dev_shaped, monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")
    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "a porch at dawn", "--key", library.face_1, "--dry-run", "--json",
    ])
    assert result.exit_code == 0, result.output
    # stdout is the JSON document; the trailer goes to stderr, which CliRunner
    # mixes in — so parse up to the closing brace.
    document = json.loads(result.output[: result.output.rindex("}") + 1])
    draft = E.query_runs(project=library.project, status="draft")["runs"][0]
    assert document["ui"] == f"{DEV_WEB}/p/{library.project}/r/{draft['id']}"


def test_a_real_run_prints_the_link_on_completion(library, prod_shaped, monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")
    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "a porch at dawn", "--key", library.face_1,
    ])
    assert result.exit_code == 0, result.output
    run_id = E.query_runs(project=library.project, status="succeeded")["runs"][0]["id"]
    link = f"{PROD_WEB}/p/{library.project}/r/{run_id}"
    assert f'"ui": "{link}"' in result.output
    assert f"ui:  {link}" in result.output


def test_runs_submit_reports_the_link(library, dev_shaped):
    draft = _draft(library)
    result = CliRunner().invoke(cli.main, ["runs", "submit", draft["id"]])
    assert result.exit_code == 0, result.output
    link = f"{DEV_WEB}/p/{library.project}/r/{draft['id']}"
    assert f"ui:  {link}" in result.output
    assert f'"ui": "{link}"' in result.output


def test_runs_show_carries_ui_for_both_shapes(library, monkeypatch):
    draft = _draft(library)
    path = f"/p/{library.project}/r/{draft['id']}"

    monkeypatch.setenv("STUDIO_API_URL", "http://localhost:8000")
    result = CliRunner().invoke(cli.main, ["runs", "show", draft["id"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ui"] == DEV_WEB + path

    profiles.save("prod", {
        "api_url": "https://studio-api.andreas.services", "web_url": PROD_WEB,
        "cognito_user_pool_id": "p", "cognito_client_id": "c",
        "s3_bucket": "b", "catalog_table": "t",
    })
    result = CliRunner().invoke(cli.main, ["--profile", "prod", "runs", "show", draft["id"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ui"] == PROD_WEB + path


def test_runs_list_links_the_project_once_and_each_json_row(library, prod_shaped):
    """One link for the listing — forty URLs would bury forty rows."""
    first, second = _draft(library), _draft(library)
    for record in (first, second):
        E.submit_run(record["id"])

    human = CliRunner().invoke(cli.main, ["runs", "list", "porch-teaser"])
    assert human.exit_code == 0, human.output
    assert human.output.count("ui:  ") == 1
    assert f"ui:  {PROD_WEB}/p/{library.project}" in human.output
    assert f"/r/{first['id']}" not in human.output

    machine = CliRunner().invoke(cli.main, ["runs", "list", "porch-teaser", "--json"])
    assert machine.exit_code == 0, machine.output
    rows = json.loads(machine.output)
    assert {row["ui"] for row in rows} >= {
        f"{PROD_WEB}/p/{library.project}/r/{first['id']}",
        f"{PROD_WEB}/p/{library.project}/r/{second['id']}",
    }


def test_runs_reconcile_and_adopt_carry_ui(library, dev_shaped):
    record = _draft(library)
    E.submit_run(record["id"])
    result = CliRunner().invoke(cli.main, ["runs", "reconcile", record["id"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ui"].endswith(f"/r/{record['id']}")

    result = CliRunner().invoke(cli.main, ["runs", "adopt", "porch-teaser",
                                           "--key", library.face_1])
    assert result.exit_code == 0, result.output
    adopted = json.loads(result.output)
    assert adopted["ui"] == f"{DEV_WEB}/p/{library.project}/r/{adopted['id']}"


# ── scenes ──────────────────────────────────────────────────────────────────


def _video(library, name="clip.mp4"):
    run = E.create_run(project=library.project, kind="video", engine="kling",
                       model="kwaivgi/kling", input={}, bindings={})
    signed = add_run_output(run["id"], name, 9, "video/mp4")
    library.fake.s3.put_object(
        Bucket=BUCKET, Key=signed["url"].removeprefix("memory://"), Body=b"mp4-bytes")
    node = library.fake.nodes[signed["node"]]
    node.update(size=9, content_type="video/mp4")
    node.pop("pending", None)
    E.patch_run(run["id"], status="succeeded")
    return run["id"]


def test_scenes_show_and_the_cut_rows_link_the_scene(library, prod_shaped):
    """A scene's page is `/s/<id>` — the SPA's own shape, not nested in the project."""
    scene = SC.new_scene(PROJECTS.resolve("porch-teaser"), "the-encounter")
    link = f"{PROD_WEB}/s/{scene['id']}"

    shown = CliRunner().invoke(cli.main, ["scenes", "show", "porch-teaser/the-encounter"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["ui"] == link

    made = CliRunner().invoke(cli.main, ["scenes", "new", "porch-teaser", "--name", "two"])
    assert made.exit_code == 0, made.output
    assert "ui:  " + PROD_WEB + "/s/" in made.output


def test_scenes_assemble_links_the_scene_the_cut_lives_on(library, dev_shaped):
    scene = SC.new_scene(PROJECTS.resolve("porch-teaser"), "the-encounter")
    SC.order_runs(scene, [_video(library, "a.mp4"), _video(library, "b.mp4")])

    result = CliRunner().invoke(cli.main, ["scenes", "assemble", "porch-teaser/the-encounter"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    link = f"{DEV_WEB}/s/{scene['id']}"
    assert f"ui:  {link}" in result.output
    document, _ = json.JSONDecoder().raw_decode(result.output[result.output.index("{"):])
    assert document["ui"] == link


# ── frames ──────────────────────────────────────────────────────────────────


def test_frames_last_names_the_run_the_frame_came_from(library, prod_shaped):
    """On stderr: stdout stays the node id, so `$(studio frames last …)` still is one."""
    run_id = _video(library)
    result = CliRunner().invoke(cli.main, ["frames", "last", run_id, "--add-input"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert result.stdout.strip().startswith("node-")
    assert "ui:" not in result.stdout
    assert f"from {run_id}  ui:  {PROD_WEB}/p/{library.project}/r/{run_id}" in result.stderr
