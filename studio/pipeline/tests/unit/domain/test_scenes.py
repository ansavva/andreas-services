"""`studio scenes` — a named, ordered series of runs, and the cut it stitches.

**The plan is gone, and most of this file used to be about it.** A scene was a
storyboard: shot rows with panels, a plan on disk that `new --from-json`
ingested, a `board` that rendered panels, a `handoff` that carried frames
between shots. Every one of those things was a run wearing a second record.
What is tested now is the two facts a scene is — the runs in it (`--scene` on
`studio run`) and the cut (`add` / `remove` / `order`) — plus the frames the
cut implies and the render job `assemble` enqueues.

`test_the_cut_is_a_render_job_and_the_worker_writes_the_record` is what says the
encode left the CLI: one `POST /api/renders` naming node ids in cut order, and a
record read back from the service rather than asserted.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E
from studio_pipeline.domain import projects as PROJECTS
from studio_pipeline.domain import scenes as SC
from tests.support.fake_api import add_run_output

BUCKET = "studio-prod-media-us-east-1"


def _run(*args):
    return CliRunner().invoke(cli.main, ["scenes", *args])


def _video(library, name="clip.mp4", rendered=True, sends=None, scene=None):
    """A video run, with a clip on it unless told otherwise."""
    run = E.create_run(project=library.project, kind="video", engine="kling",
                       model="kwaivgi/kling", input={}, bindings={},
                       sends=sends, scene=scene)
    if rendered:
        signed = add_run_output(run["id"], name, 9, "video/mp4")
        library.fake.s3.put_object(
            Bucket=BUCKET, Key=signed["url"].removeprefix("memory://"), Body=b"mp4-bytes")
        node = library.fake.nodes[signed["node"]]
        node.update(size=9, content_type="video/mp4")
        node.pop("pending", None)
        E.patch_run(run["id"], status="succeeded")
        return run["id"], signed["node"]
    return run["id"], None


@pytest.fixture
def scene(library):
    """One empty scene in the fixture project."""
    return SC.new_scene(PROJECTS.resolve("porch-teaser"), "the-encounter")


# ── resolving ───────────────────────────────────────────────────────────────

def test_a_scene_resolves_by_name(library, scene):
    assert SC.resolve_scene("porch-teaser/the-encounter")["id"] == scene["id"]


def test_a_scene_resolves_by_id_with_no_project_at_all(library, scene):
    """A movie names its scenes by id, so nothing has to remember which project
    they were in and a project rename strands none of them."""
    assert SC.resolve_scene(scene["id"])["id"] == scene["id"]


def test_a_unique_fragment_still_resolves(library, scene):
    assert SC.resolve_scene("porch-teaser/encounter")["id"] == scene["id"]


def test_latest_reads_created_off_the_row(library, scene):
    project = PROJECTS.resolve("porch-teaser")
    newer = SC.new_scene(project, "aaa-later")
    assert SC.resolve_scene("porch-teaser/latest")["id"] == newer["id"]
    assert newer["name"] < scene["name"], "and it sorts FIRST alphabetically"


def test_a_scene_that_is_not_there_is_a_clean_refusal(library):
    result = _run("show", "porch-teaser/nothing")
    assert result.exit_code == 1
    assert "no scene" in result.output


def test_a_project_with_no_scenes_says_so(library):
    result = _run("list", "porch-teaser")
    assert result.exit_code == 0, result.output
    assert "no scenes" in result.output


# ── new ─────────────────────────────────────────────────────────────────────

def test_new_creates_the_record_with_an_empty_cut(library):
    result = _run("new", "porch-teaser", "--name", "opening")
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    record = SC.resolve_scene("porch-teaser/opening")
    assert record["runs"] == [] and record["frames"] == []
    assert "nothing in the cut yet" in result.output
    assert "--scene porch-teaser/opening" in result.output


def test_new_with_runs_names_the_cut_in_the_order_given(library):
    first, _ = _video(library, "a.mp4")
    second, _ = _video(library, "b.mp4")

    result = _run("new", "porch-teaser", "--name", "opening", "--run", second, "--run", first)

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    record = SC.resolve_scene("porch-teaser/opening")
    assert SC.cut_ids(record) == [second, first]
    # Naming a run in the cut puts it into the scene.
    assert E.get_run(first)["scene"] == record["id"]


def test_new_refuses_a_still_in_the_cut(library):
    still = E.create_run(project=library.project, kind="image", engine="nano-banana-pro",
                         model="google/nano-banana-pro", input={}, bindings={})
    result = _run("new", "porch-teaser", "--name", "opening", "--run", still["id"])
    assert result.exit_code == 1
    assert "only a video can be cut" in result.output
    assert SC.list_scenes(PROJECTS.resolve("porch-teaser")) == []


def test_new_refuses_an_output_index(library, scene):
    """The cut names runs; which clip a run contributes is decided at assemble."""
    run_id, _ = _video(library)
    result = _run("add", "porch-teaser/the-encounter", f"{run_id}#1")
    assert result.exit_code == 1
    assert "drop the #N" in result.output


# ── membership ──────────────────────────────────────────────────────────────

def test_a_run_made_with_scene_belongs_to_it(library, scene):
    """`studio run --scene` files the draft under the scene from the start."""
    run_id, _ = _video(library, scene=scene["id"])
    assert E.get_run(run_id)["scene"] == scene["id"]
    listed = E.query_runs(project=library.project, scene=scene["id"])["runs"]
    assert [r["id"] for r in listed] == [run_id]
    assert listed[0]["scene"] == scene["id"]


def test_runs_list_filters_by_scene(library, scene):
    mine, _ = _video(library, "mine.mp4", scene=scene["id"])
    _video(library, "other.mp4")

    result = CliRunner().invoke(cli.main, ["runs", "list", "porch-teaser",
                                           "--scene", "the-encounter", "--status", "succeeded"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert mine in result.output
    assert result.output.count("run-") == 1


# ── the cut ─────────────────────────────────────────────────────────────────

def test_add_appends_in_order_and_joins(library, scene):
    first, _ = _video(library, "a.mp4")
    second, _ = _video(library, "b.mp4")

    assert _run("add", "porch-teaser/the-encounter", first).exit_code == 0
    result = _run("add", "porch-teaser/the-encounter", second)

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert SC.cut_ids(SC.resolve_scene(scene["id"])) == [first, second]
    assert E.get_run(second)["scene"] == scene["id"]


def test_add_refuses_a_run_from_another_scene(library, scene):
    theirs = SC.new_scene(PROJECTS.resolve("porch-teaser"), "theirs")
    run_id, _ = _video(library, scene=theirs["id"])

    result = _run("add", "porch-teaser/the-encounter", run_id)

    assert result.exit_code == 1
    assert theirs["id"] in result.output
    assert SC.cut_ids(SC.resolve_scene(scene["id"])) == []


def test_remove_takes_every_occurrence_out_and_leaves_membership(library, scene):
    first, _ = _video(library, "a.mp4")
    second, _ = _video(library, "b.mp4")
    SC.order_runs(scene, [first, second, first])

    result = _run("remove", "porch-teaser/the-encounter", first)

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert SC.cut_ids(SC.resolve_scene(scene["id"])) == [second]
    assert E.get_run(first)["scene"] == scene["id"]


def test_remove_refuses_a_run_that_is_not_in_the_cut(library, scene):
    run_id, _ = _video(library)
    result = _run("remove", "porch-teaser/the-encounter", run_id)
    assert result.exit_code == 1
    assert "not in the cut" in result.output


def test_order_replaces_the_cut_whole(library, scene):
    first, _ = _video(library, "a.mp4")
    second, _ = _video(library, "b.mp4")
    SC.add_runs(scene, (first,))

    result = _run("order", "porch-teaser/the-encounter", second, first)

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert SC.cut_ids(SC.resolve_scene(scene["id"])) == [second, first]


def test_show_prints_the_cut_as_rows(library, scene):
    run_id, node = _video(library)
    SC.add_runs(scene, (run_id,))
    result = _run("show", "porch-teaser/the-encounter")
    assert result.exit_code == 0
    assert run_id in result.output and node in result.output


# ── frames ──────────────────────────────────────────────────────────────────

def test_frames_are_the_start_frame_of_each_cut_run_in_order(library, scene):
    """Derived from the cut, so there is no second list to drift."""
    seed = library.input_3
    first, _ = _video(library, "a.mp4", sends=[
        {"field": "start_image", "role": "start", "node": seed},
        {"field": "reference_images", "role": "reference", "node": library.face_1}])
    second, _ = _video(library, "b.mp4", sends=[
        {"field": "start_image", "role": "start", "node": library.input_2}])
    unstarted, _ = _video(library, "c.mp4")
    SC.order_runs(scene, [first, second, unstarted])

    result = _run("frames", "porch-teaser/the-encounter")

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert result.output.split() == [seed, library.input_2]


def test_frames_args_and_max_keep_the_seed_and_the_newest(library, scene):
    nodes = [library.input_3, library.input_2, library.face_1, library.face_2]
    ids = []
    for n, node in enumerate(nodes):
        run_id, _ = _video(library, f"{n}.mp4", sends=[
            {"field": "start_image", "role": "start", "node": node}])
        ids.append(run_id)
    SC.order_runs(scene, ids)

    result = _run("frames", "porch-teaser/the-encounter", "--args", "--max", "2")

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert result.output.strip() == f"--key {nodes[0]} --key {nodes[-1]}"


def test_frames_refuses_a_scene_with_none(library, scene):
    result = _run("frames", "porch-teaser/the-encounter")
    assert result.exit_code == 1
    assert "no frames yet" in result.output


# ── assembling ──────────────────────────────────────────────────────────────

def test_assemble_refuses_a_scene_that_is_not_there(library):
    result = _run("assemble", "porch-teaser/nothing")
    assert result.exit_code == 1
    assert "no scene" in result.output


def test_assemble_refuses_an_empty_cut(library, scene):
    result = _run("assemble", "porch-teaser/the-encounter")
    assert result.exit_code == 1
    assert "nothing in its cut" in result.output


def test_assemble_names_every_run_without_a_video_at_once(library, scene):
    rendered, _ = _video(library, "a.mp4")
    one, _ = _video(library, rendered=False)
    two, _ = _video(library, rendered=False)
    SC.order_runs(scene, [rendered, one, two])

    result = _run("assemble", "porch-teaser/the-encounter")

    assert result.exit_code == 1
    assert "2 run(s) in the cut have no video yet" in result.output
    assert one in result.output and two in result.output
    assert library.fake.renders == {}


def test_the_cut_is_a_render_job_and_the_worker_writes_the_record(library, scene):
    """One `POST /api/renders` of kind `assemble`, naming this scene and its
    clips as NODE IDS in cut order, and a record read back from the service."""
    clips = [_video(library, f"shot-{n}.mp4") for n in (1, 2)]
    SC.order_runs(scene, [r for r, _ in clips])

    result = _run("assemble", "porch-teaser/the-encounter")
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"

    job = list(library.fake.renders.values())[-1]
    assert job["kind"] == "assemble"
    assert job["params"]["target"] == scene["id"]
    assert [part["node"] for part in job["params"]["parts"]] == [n for _, n in clips]
    assert [part["run"] for part in job["params"]["parts"]] == [r for r, _ in clips]

    after = SC.resolve_scene(scene["id"])
    assert after["output"]["node"].startswith("node-")
    assert after["status"] == "assembled"
    assert SC.scene_output_node(after) == after["output"]["node"]


def test_assemble_with_shot_orders_first_then_cuts(library, scene):
    """The pre-plan one-liner: a fresh scene plus runrefs is "just stitch these"."""
    first, _ = _video(library, "a.mp4")
    second, _ = _video(library, "b.mp4")

    result = _run("assemble", "porch-teaser/the-encounter", "--shot", second, "--shot", first)

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert SC.cut_ids(SC.resolve_scene(scene["id"])) == [second, first]
    job = list(library.fake.renders.values())[-1]
    assert [part["run"] for part in job["params"]["parts"]] == [second, first]


# ── outputs ─────────────────────────────────────────────────────────────────

def test_scenes_outputs_lists_nothing_before_a_cut(library, scene):
    result = _run("outputs", "porch-teaser/the-encounter")
    assert result.exit_code == 0, result.output
    assert result.output.strip() == ""


def test_scenes_outputs_lists_the_cut_after_one(library, scene):
    run_id, _ = _video(library)
    SC.add_runs(scene, (run_id,))
    _run("assemble", "porch-teaser/the-encounter")

    result = _run("outputs", "porch-teaser/the-encounter")

    assert result.exit_code == 0, result.output
    assert "the-encounter.mp4" in result.output
