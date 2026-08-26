"""`studio scenes` and `studio movies` — envelopes, `SHOT#` rows, and a local cut.

**`scene.json` is gone, and most of this file used to be about it.** A scene was
a document in the bucket: `read_manifest` / `write_manifest`, a manifest that
could be missing or unreadable, an id that was a folder name, and a `latest` that
had to open every manifest in the project because a lexical sort over folder
names put every slug after every timestamp. All of that was the document being
the record.

A scene is a row. `latest` is `created` on it, `status` is recomputed and
`PATCH`ed, and the shots are their own rows that `PUT /api/scenes/<id>/shots`
merges by id. So the tests that guarded the document are gone and what replaced
them asserts the row.

**One thing deliberately did not move: the encode.** ffmpeg ships in this wheel
and the Lambda has none, so `assemble` still downloads every rendered shot,
stitches locally, uploads through a signed URL and only then `PATCH`es the
record. `test_the_cut_is_made_locally_and_only_the_record_goes_to_the_api` is the
test that says so.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E, store
from studio_pipeline.domain import projects as PROJECTS
from studio_pipeline.domain import scenes as SC


def _run(*args):
    return CliRunner().invoke(cli.main, ["scenes", *args])


def _plan(tmp_path, **over):
    """A two-shot plan on disk, as `scenes new --from-json` takes it."""
    doc = {
        "defaults": {"model": "kling", "panel_model": "nano-banana-pro", "duration": 5},
        "shots": [
            {"beat": "one", "panels": [{"prompt": "a"}], "motion": {"prompt": "m1"}},
            {"beat": "two", "panels": [{"prompt": "b"}], "motion": {"prompt": "m2"}},
        ],
    }
    doc.update(over)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(doc))
    return str(path)


@pytest.fixture
def scene(library, tmp_path):
    """One planned scene in the fixture project."""
    project = PROJECTS.resolve("porch-teaser")
    return SC.new_scene(project, "the-encounter", _plan(tmp_path))


# ── resolving ───────────────────────────────────────────────────────────────

def test_a_scene_resolves_by_slug(library, scene):
    assert SC.resolve_scene("porch-teaser/the-encounter")["id"] == scene["id"]


def test_a_scene_resolves_by_id_with_no_project_at_all(library, scene):
    """The property a record storing a scene id depends on.

    A movie names its scenes by id, so nothing has to remember which project
    they were in and a project rename strands none of them.
    """
    assert SC.resolve_scene(scene["id"])["id"] == scene["id"]


def test_a_unique_fragment_still_resolves(library, scene):
    assert SC.resolve_scene("porch-teaser/encounter")["id"] == scene["id"]


def test_latest_reads_created_off_the_row(library, scene, tmp_path):
    """**Not a lexical sort over folder names, and not a walk of the manifests.**

    `latest` meant `ids[-1]` while every id began with a timestamp, which made
    the lexical sort accidentally chronological. Slug-keyed scenes sort after
    every timestamped one, so it came to mean "alphabetically last" — and
    `movies new --scene <project>/latest` was exactly the caller that would have
    got it wrong. The fix was to open every manifest; the row carries the
    timestamp, so there is nothing left to re-derive.
    """
    project = PROJECTS.resolve("porch-teaser")
    newer = SC.new_scene(project, "aaa-later", _plan(tmp_path))
    assert SC.resolve_scene("porch-teaser/latest")["id"] == newer["id"]
    assert newer["slug"] < scene["slug"], "and it sorts FIRST alphabetically"


def test_a_scene_that_is_not_there_is_a_clean_refusal(library):
    result = _run("show", "porch-teaser/nothing")
    assert result.exit_code == 1
    assert "no scene" in result.output


def test_a_project_with_no_scenes_says_so(library):
    result = _run("list", "porch-teaser")
    assert result.exit_code == 0, result.output
    assert "no scenes" in result.output


# ── planning ────────────────────────────────────────────────────────────────

def test_new_creates_the_record_and_its_shot_rows(library, tmp_path):
    project = PROJECTS.resolve("porch-teaser")
    record = SC.new_scene(project, "the-encounter", _plan(tmp_path))

    assert record["id"].startswith("scene-")
    assert record["project"] == library.project
    assert [s["id"] for s in SC.scene_shots(record)] == ["shot-01", "shot-02"]
    assert record["status"] == "planned"
    # Its folder is a child of the project's `scenes/`, and the record names it.
    assert record["folder"].startswith("node-")


def test_a_shot_read_back_carries_its_position(library, tmp_path):
    """**`n` is derived on read, never stored.**

    It is the shot's 1-based position, which `order` already decides — storing it
    would be a second answer to one question and would go stale the first time a
    plan was reordered. `storyboard.normalise` sets it while building a plan from
    JSON, so a freshly ingested scene had it and a scene *read back from the API*
    did not: the rows come off `SHOT#` and had never been through `normalise`.
    Everything downstream reads it — `--shot 3`, the handoff hint, panel slugs —
    so `scenes check` on a stored plan died with `KeyError: 'n'`.
    """
    project = PROJECTS.resolve("porch-teaser")
    created = SC.new_scene(project, "the-encounter", _plan(tmp_path))

    reread = SC.scene_shots(SC.resolve_scene(created["id"]))

    assert [s["n"] for s in reread] == [1, 2]
    assert [s["n"] for s in SC.scene_shots(created)] == [1, 2]


def test_a_slug_shaped_like_a_run_id_is_accepted_now(library, tmp_path):
    """**This was refused, and the reason expired.**

    A scene folder was once `<timestamp>_<slug>`, so such a slug was
    indistinguishable from a legacy scene and the resolver would have gone to
    the wrong directory. A scene is a row with a UUID; there is nothing left to
    collide with.
    """
    project = PROJECTS.resolve("porch-teaser")
    record = SC.new_scene(project, "2026-08-16_07-40-22_the-encounter",
                          _plan(tmp_path))
    assert SC.resolve_scene(record["id"])["slug"] == \
        "2026-08-16_07-40-22_the-encounter"


def test_new_refuses_to_overwrite_and_says_how_to_revise(library, scene, tmp_path):
    result = _run("new", "porch-teaser", "--slug", "the-encounter",
                  "--from-json", _plan(tmp_path))
    assert result.exit_code == 1
    assert "--force" in result.output


def test_revising_carries_recorded_work_across(library, scene, tmp_path):
    """**Editing prose must not orphan a clip somebody paid for.**

    Two merges, and both are needed. `PUT /api/scenes/<id>/shots` merges by shot
    id server-side, which protects the shot; a revised shot's `panels` list
    replaces the stored one wholesale, so `storyboard.merge` runs first to carry
    the recorded panel images across. The API's merge protects the shot, this
    one protects what is inside it, and they are not the same write.
    """
    shots = SC.scene_shots(scene)
    shots[0].update(run="run-earlier", node="node-clip", duration=5.04)
    shots[0]["panels"][0]["node"] = "node-panel-1"
    SC.save_shots(scene, shots)

    revised = _plan(tmp_path, shots=[
        {"id": "shot-01", "beat": "one, but reworded",
         "panels": [{"prompt": "a"}], "motion": {"prompt": "m1"}},
        {"id": "shot-02", "beat": "two", "panels": [{"prompt": "b"}],
         "motion": {"prompt": "m2"}},
    ])
    result = _run("new", "porch-teaser", "--slug", "the-encounter",
                  "--from-json", revised, "--force")
    assert result.exit_code == 0, result.output

    after = SC.scene_shots(SC.resolve_scene(scene["id"]))
    assert after[0]["run"] == "run-earlier"
    assert after[0]["duration"] == 5.04
    assert after[0]["panels"][0]["node"] == "node-panel-1"
    assert after[0]["beat"] == "one, but reworded"


def test_new_redirects_the_old_assembling_spelling(library):
    """`--shot` used to assemble here. A silent "unknown option" on a command
    that still exists reads as a broken install, so it is answered."""
    result = _run("new", "porch-teaser", "--slug", "x", "--shot", "some/run")
    assert result.exit_code == 1
    assert "scenes assemble" in result.output


def test_plan_marks_which_panels_exist(library, scene):
    shots = SC.scene_shots(scene)
    shots[0]["panels"][0]["node"] = "node-panel-1"
    SC.save_shots(scene, shots)

    result = _run("plan", "porch-teaser/the-encounter")
    assert result.exit_code == 0, result.output
    assert "*p1" in result.output           # boarded
    assert "-p1" in result.output           # not boarded


def test_the_status_is_recomputed_and_never_read_back_as_authority(library, scene):
    """Derived on every write, so a person can see where a scene is without
    replaying the rules — and so a hand-edited status cannot lie."""
    assert SC.resolve_scene(scene["id"])["status"] == "planned"
    shots = SC.scene_shots(scene)
    for shot in shots:
        shot["panels"][0]["node"] = "node-panel"
    after = SC.save_shots(scene, shots)
    assert after["status"] == "boarded"


# ── assembling ──────────────────────────────────────────────────────────────

def test_assemble_refuses_a_scene_that_is_not_there(library):
    result = _run("assemble", "porch-teaser/nothing")
    assert result.exit_code == 1


def test_assemble_names_every_shot_that_has_not_been_rendered(library, scene):
    """All of them at once — being told one per attempt is one round trip each."""
    result = _run("assemble", "porch-teaser/the-encounter")
    assert result.exit_code == 1
    assert "shot-01" in result.output and "shot-02" in result.output


def test_assemble_refuses_a_scene_with_nothing_in_it(library):
    project = PROJECTS.resolve("porch-teaser")
    SC.new_scene(project, "empty", None)
    result = _run("assemble", "porch-teaser/empty")
    assert result.exit_code == 1
    assert "no shots" in result.output


def test_the_cut_is_made_locally_and_only_the_record_goes_to_the_api(
        library, scene, monkeypatch, tmp_path):
    """**Stitching stays in the CLI, and this is the test that says so.**

    ffmpeg ships in this wheel and the Lambda has none. So the shots come DOWN,
    `adapters/ffmpeg` joins them here, the result goes UP through the URL
    `POST /api/scenes/<id>/output` signs, and the API owns the record and
    nothing about how the file was made.
    """
    joined = []

    def fake_stitch(paths, out, label=""):
        joined.extend(paths)
        with open(out, "wb") as fh:
            fh.write(b"mp4-bytes")
        return {"method": "concat demuxer, stream copy (no re-encode)",
                "probes": [{"duration": 5.0} for _ in paths]}

    monkeypatch.setattr(SC, "stitch", fake_stitch)
    monkeypatch.setattr(SC, "probe", lambda path: {"duration": 10.0})

    # Two rendered shots: a run each, with a video output.
    clips = []
    for n in (1, 2):
        run = E.create_run(project=library.project, kind="video", engine="kling",
                           model="kwaivgi/kling", input={},
                           bindings={})
        signed = E.add_run_output(run["id"], f"shot-{n}.mp4", 9, "video/mp4")
        library.fake.s3.put_object(
            Bucket="studio-prod-media-us-east-1",
            Key=signed["url"].removeprefix("memory://"), Body=b"mp4-bytes")
        node = library.fake.nodes[signed["node"]]
        node.update(size=9, content_type="video/mp4")
        node.pop("pending", None)
        clips.append((run["id"], signed["node"]))

    shots = SC.scene_shots(scene)
    for shot, (run_id, node) in zip(shots, clips):
        shot.update(run=run_id, node=node)
    SC.save_shots(scene, shots)

    result = _run("assemble", "porch-teaser/the-encounter")
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert len(joined) == 2, "both shots were joined on this machine"

    after = SC.resolve_scene(scene["id"])
    assert after["output"]["node"].startswith("node-")
    assert after["status"] == "assembled"
    assert SC.is_assembled(after) is True
    # Each shot was copied into the scene, so it stays playable as its runs
    # accumulate around it, and the copy is a real one — two blobs.
    for shot in SC.scene_shots(after):
        assert shot["shot_node"].startswith("node-")
        assert shot["shot_node"] != shot["node"]


# ── handoff ─────────────────────────────────────────────────────────────────

def test_handoff_refuses_the_first_shot(library, scene):
    result = _run("handoff", "porch-teaser/the-encounter", "--shot", "1")
    assert result.exit_code == 1
    assert "nothing before it" in result.output


def test_handoff_refuses_a_shot_that_is_not_in_the_scene(library, scene):
    result = _run("handoff", "porch-teaser/the-encounter", "--shot", "9")
    assert result.exit_code == 1
    assert "has no shot 9" in result.output


def test_handoff_says_to_render_the_shot_before_it_first(library, scene):
    result = _run("handoff", "porch-teaser/the-encounter", "--shot", "2")
    assert result.exit_code == 1
    assert "has not been rendered" in result.output


# ── outputs ─────────────────────────────────────────────────────────────────

def test_scenes_outputs_lists_nothing_before_a_cut(library, scene):
    result = _run("outputs", "porch-teaser/the-encounter")
    assert result.exit_code == 0, result.output


# ── movies ──────────────────────────────────────────────────────────────────

def test_movies_reports_every_unassembled_scene_at_once(library, scene, tmp_path):
    """A scene can exist as a plan, so "not assembled" is an ordinary state.

    Being told one per attempt would be one round trip per missing scene.
    """
    project = PROJECTS.resolve("porch-teaser")
    SC.new_scene(project, "second", _plan(tmp_path))

    result = CliRunner().invoke(cli.main, [
        "movies", "new", "porch-teaser", "--slug", "the-cut",
        "--scene", "porch-teaser/the-encounter", "--scene", "porch-teaser/second"])

    assert result.exit_code == 1
    assert "the-encounter" in result.output and "second" in result.output


def test_a_movie_lists_nothing_in_an_empty_project(library):
    result = CliRunner().invoke(cli.main, ["movies", "list", "porch-teaser"])
    assert result.exit_code == 0, result.output
    assert "no movies" in result.output


def test_a_movie_resolves_by_id_and_by_slug(library):
    from studio_pipeline.domain import movies as MV

    record = E.create_movie(project=library.project, slug="the-cut")
    assert MV.resolve_movie(record["id"])["id"] == record["id"]
    assert MV.resolve_movie("porch-teaser/the-cut")["id"] == record["id"]


def test_store_reads_a_scene_output_by_node(library, scene):
    """The scene's folder is a node the record names, not a path anyone builds."""
    assert store.node(scene["folder"])["name"] == "the-encounter"
