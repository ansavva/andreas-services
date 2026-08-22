"""The scene store, once a scene can exist before it is cut.

A scene used to be created only at the moment it was assembled, so "a scene"
and "a finished video" were the same thing and no code had to tell them apart.
Now a scene is planned first and cut later, which makes three things newly
breakable — and all three break quietly:

  * **`latest`.** It was `ids[-1]`, correct only while every id began with a
    timestamp. Slug-keyed ids sort after timestamped ones, so the old rule would
    have kept working and silently meant "alphabetically last".
  * **The scenes already in the bucket.** They are keyed `<timestamp>_<slug>`
    and have no plan behind them. They must keep resolving, and `movies` must
    keep cutting them, or a real finished piece becomes unreachable.
  * **A planned scene reaching `movies`.** `movies.create` reads each scene's
    output key off its manifest and a plan has none. It collects every scene
    missing one before it fails, so the message names all of them and the fix —
    a movie is cut from several scenes and they are planned together.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters.s3 import BUCKET
from studio_pipeline.domain import movies as MOV
from studio_pipeline.domain import scenes as SC
from studio_pipeline.domain import storyboard as SB

LEGACY = "2026-08-16_07-40-22_old-cut"
PLANNED = "board-test"


def run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def write_plan(tmp_path, **over):
    plan = {
        "defaults": {"model": "kling", "panel_model": "nano-banana-pro", "duration": 5},
        "shots": [
            {"id": "opening", "beat": "it opens",
             "panels": [{"prompt": "the opening frame"}],
             "motion": {"prompt": "it moves"}},
        ],
    }
    plan.update(over)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    return str(path)


# --- addressing ------------------------------------------------------------

def test_a_slug_keyed_scene_resolves(media_bucket):
    assert SC.resolve_scene(f"subject-a/{PLANNED}") == ("subject-a", PLANNED)


def test_a_timestamped_scene_from_before_plans_still_resolves(media_bucket):
    """Not deprecation scaffolding — to this resolver both are directory names,
    and the scenes carrying the old shape are finished cuts worth keeping."""
    assert SC.resolve_scene(f"subject-a/{LEGACY}") == ("subject-a", LEGACY)


def test_a_unique_fragment_still_resolves(media_bucket):
    assert SC.resolve_scene("subject-a/old-cut") == ("subject-a", LEGACY)


def test_latest_reads_the_manifests_rather_than_sorting_the_ids(media_bucket):
    """The fixture is built so the two rules disagree.

    `board-test` sorts last lexically but was created in January; the legacy
    scene sorts first but was created in December. `ids[-1]` would answer
    `board-test`, which is wrong — and would have been wrong silently, including
    for `studio movies new --scene <p>/latest`.
    """
    ids = SC.list_scenes("subject-a")
    assert ids[-1] == PLANNED, "the fixture only means something if this holds"
    assert SC.resolve_scene("subject-a/latest") == ("subject-a", LEGACY)


def test_an_unreadable_manifest_does_not_break_latest(media_bucket):
    """`latest` is a convenience; it must not be what stops you reaching the
    scene you actually named."""
    media_bucket.put_object(Bucket=BUCKET,
                            Key="projects/subject-a/scenes/broken/scene.json",
                            Body=b"{not json")
    assert SC.resolve_scene("subject-a/latest") == ("subject-a", LEGACY)


def test_a_scene_folder_with_no_manifest_does_not_break_latest(media_bucket):
    media_bucket.put_object(Bucket=BUCKET,
                            Key="projects/subject-a/scenes/empty/shots/shot-01.mp4",
                            Body=b"mp4-bytes")
    assert SC.resolve_scene("subject-a/latest") == ("subject-a", LEGACY)


# --- the manifest ----------------------------------------------------------

def test_read_manifest_returns_none_for_a_scene_that_is_not_there(media_bucket):
    assert SC.read_manifest("subject-a", "nope") is None


def test_a_planned_scene_is_not_assembled(media_bucket):
    m = SC.read_manifest("subject-a", PLANNED)
    assert m["output"] is None
    assert SC.is_assembled(m) is False
    assert SC.scene_output_key(m) is None


def test_a_legacy_scene_is_assembled(media_bucket):
    m = SC.read_manifest("subject-a", LEGACY)
    assert SC.is_assembled(m) is True
    assert SC.scene_output_key(m).endswith("output/old-cut.mp4")


def test_writing_a_manifest_refreshes_the_derived_status(media_bucket):
    m = SC.read_manifest("subject-a", PLANNED)
    m["shots"][1]["run"] = "subject-a/2026-08-18_10-00-00_shot-02"
    SC.write_manifest(m)

    back = SC.read_manifest("subject-a", PLANNED)
    assert back["shots"][1]["status"] == "rendered"
    assert back["status"] == "shooting"
    assert back["updated"] != "2026-01-01T00:00:00+00:00"


def test_a_manifest_is_written_back_where_it_came_from(media_bucket):
    """A legacy scene's directory is `<timestamp>_<slug>` while its `slug` field
    is the bare slug. Keying the write off `slug` would file it somewhere that
    does not exist and leave the original untouched."""
    m = SC.read_manifest("subject-a", LEGACY)
    SC.write_manifest(m)

    assert SC.read_manifest("subject-a", LEGACY) is not None
    assert SC.read_manifest("subject-a", "old-cut") is None


# --- the contract movies depends on ----------------------------------------

def test_movies_reports_every_unassembled_scene_at_once(media_bucket, capsys):
    """One round trip per missing scene is the thing worth avoiding — a movie is
    cut from several scenes and they are typically planned together."""
    media_bucket.put_object(
        Bucket=BUCKET, Key="projects/subject-a/scenes/second-plan/scene.json",
        Body=json.dumps({"scene": "subject-a/second-plan", "project": "subject-a",
                         "slug": "second-plan", "shots": [], "output": None}).encode())

    with pytest.raises(SystemExit):
        MOV.create("subject-a", "whole-thing",
                   [f"subject-a/{PLANNED}", "subject-a/second-plan"])

    err = capsys.readouterr().err
    assert "2 scene(s) are planned but not assembled" in err
    assert PLANNED in err and "second-plan" in err
    assert "studio scenes assemble" in err


# --- the plan, read back off the record ------------------------------------

def test_the_stored_plan_survives_a_round_trip_through_the_rules(media_bucket):
    """The fixture is hand-written JSON standing in for a real `scene.json`; if
    the plan module cannot read it, every assertion built on it is hollow."""
    m = SC.read_manifest("subject-a", PLANNED)
    SB.validate(m)

    assert SB.shot_status(m["shots"][0]) == "boarded"
    assert SB.shot_status(m["shots"][1]) == "planned"
    assert SB.scene_status(m) == "boarding"
    assert SB.sheet_captions(m) == [
        ("projects/subject-a/scenes/board-test/storyboard/shot-01-p1.png",
         "shot-01 p1 [start]"),
    ]


# --- starting and revising a scene -----------------------------------------

def test_new_writes_a_scene_keyed_by_slug_with_no_timestamp(media_bucket, tmp_path):
    r = run("scenes", "new", "subject-a", "--slug", "fresh",
            "--from-json", write_plan(tmp_path))
    assert r.exit_code == 0, r.output

    keys = [o["Key"] for o in media_bucket.list_objects_v2(
        Bucket=BUCKET, Prefix="projects/subject-a/scenes/fresh/")["Contents"]]
    assert keys == ["projects/subject-a/scenes/fresh/scene.json"]

    m = SC.read_manifest("subject-a", "fresh")
    assert m["scene"] == "subject-a/fresh"
    assert m["status"] == "planned" and m["output"] is None
    assert m["shots"][0]["id"] == "opening"


def test_new_refuses_a_slug_shaped_like_a_run_id(media_bucket, tmp_path):
    r = run("scenes", "new", "subject-a", "--slug", "2026-08-16_07-40-22_x",
            "--from-json", write_plan(tmp_path))
    assert r.exit_code == 1
    assert "run id" in r.output


def test_new_refuses_to_overwrite_a_scene_and_says_how_to_revise_it(media_bucket, tmp_path):
    r = run("scenes", "new", "subject-a", "--slug", PLANNED,
            "--from-json", write_plan(tmp_path))
    assert r.exit_code == 1
    assert "--force" in r.output


def test_revising_carries_recorded_work_across(media_bucket, tmp_path):
    """The whole reason `--force` merges instead of replacing: a clip already
    paid for must not disappear because its beat was reworded."""
    m = SC.read_manifest("subject-a", PLANNED)
    m["shots"][0]["run"] = "subject-a/2026-08-04_21-30-54_wave-porch"
    SC.write_manifest(m)

    plan = {"defaults": m["defaults"],
            "shots": [{"id": "shot-01", "beat": "reworded",
                       "panels": [{"prompt": "the opening frame"}],
                       "motion": {"prompt": "the opening motion"}}]}
    path = tmp_path / "revised.json"
    path.write_text(json.dumps(plan))

    r = run("scenes", "new", "subject-a", "--slug", PLANNED,
            "--from-json", str(path), "--force")
    assert r.exit_code == 0, r.output

    back = SC.read_manifest("subject-a", PLANNED)
    assert back["shots"][0]["beat"] == "reworded"
    assert back["shots"][0]["run"] == "subject-a/2026-08-04_21-30-54_wave-porch"
    assert back["shots"][0]["panels"][0]["key"].endswith("shot-01-p1.png")


def test_new_redirects_the_old_assembling_spelling(media_bucket):
    """`--shot` used to cut a scene here. A silent 'no such option' on a command
    that still exists reads as a broken install, so it answers with the move."""
    r = run("scenes", "new", "subject-a", "--slug", "fresh",
            "--shot", "subject-a/wave-porch")
    assert r.exit_code == 1
    assert "scenes assemble subject-a/fresh --shot subject-a/wave-porch" in r.output


# --- assembling ------------------------------------------------------------

def test_assemble_refuses_a_scene_that_is_not_there(media_bucket):
    r = run("scenes", "assemble", "subject-a/board-test", "--project", "subject-a")
    assert r.exit_code != 0


def test_assemble_names_the_shots_that_have_not_been_rendered(media_bucket):
    r = run("scenes", "assemble", f"subject-a/{PLANNED}")
    assert r.exit_code == 1
    assert "shot-01, shot-02" in r.output
    assert "studio scenes render" in r.output


def test_assemble_refuses_a_scene_with_nothing_in_it(media_bucket, tmp_path):
    run("scenes", "new", "subject-a", "--slug", "empty-scene")
    r = run("scenes", "assemble", "subject-a/empty-scene")
    assert r.exit_code == 1
    assert "no shots" in r.output


# --- reading the board -----------------------------------------------------

def test_plan_marks_which_panels_exist(media_bucket):
    r = run("scenes", "plan", f"subject-a/{PLANNED}")
    assert r.exit_code == 0, r.output
    assert "*p1[start]" in r.output, "a landed panel"
    assert "-p1[start]" in r.output, "one that has not been rendered"
    assert "[boarding]" in r.output


def test_sheet_refuses_a_board_with_no_panels(media_bucket, tmp_path):
    run("scenes", "new", "subject-a", "--slug", "unboarded",
        "--from-json", write_plan(tmp_path))
    r = run("scenes", "sheet", "subject-a/unboarded")
    assert r.exit_code != 0
    assert "studio scenes board" in r.output


def test_sheet_builds_a_captioned_grid_of_the_panels(media_bucket, tmp_path):
    out = tmp_path / "board"
    r = run("scenes", "sheet", f"subject-a/{PLANNED}", "--out", str(out))
    assert r.exit_code == 0, r.output
    assert (out / "board-test-board.png").is_file()


def test_the_second_shot_expects_a_handoff_and_does_not_have_one_yet(media_bucket):
    """It still renders — from its own panel — but the render says so, because
    that is exactly the cut that turns out to jump."""
    m = SC.read_manifest("subject-a", PLANNED)
    r = SB.resolve_roles(m["shots"][1])
    assert m["shots"][1]["continues"] is True
    assert r["handoff"] is None
    assert r["start_panel"] == 0, "with no handoff recorded, the panel still holds the slot"
    assert r["end_panel"] == 1


# --- carrying a shot forward -----------------------------------------------

def test_handoff_reports_when_there_is_no_video_to_take_a_frame_from(media_bucket):
    m = SC.read_manifest("subject-a", PLANNED)
    m["shots"][0]["run"] = "subject-a/2026-08-04_21-30-54_wave-porch"
    m["shots"][0]["runref"] = "subject-a/2026-08-04_21-30-54_wave-porch#1"
    SC.write_manifest(m)

    # The fixture run's only output is a .jpeg, so there is no video to grab a
    # frame from — which is exactly what should be reported.
    r = run("scenes", "handoff", f"subject-a/{PLANNED}", "--shot", "2")
    assert r.exit_code != 0
    assert "no video output" in r.output


def test_handoff_refuses_the_first_shot(media_bucket):
    r = run("scenes", "handoff", f"subject-a/{PLANNED}", "--shot", "1")
    assert r.exit_code != 0
    assert "first shot" in r.output


def test_handoff_says_to_render_the_shot_before_it_first(media_bucket):
    r = run("scenes", "handoff", f"subject-a/{PLANNED}", "--shot", "2")
    assert r.exit_code != 0
    assert "studio scenes render" in r.output


def test_handoff_refuses_a_shot_that_is_not_in_the_scene(media_bucket):
    r = run("scenes", "handoff", f"subject-a/{PLANNED}", "--shot", "9")
    assert r.exit_code != 0
    assert "no shot 9" in r.output


def test_a_chain_slug_accepts_both_spellings(media_bucket):
    from studio_pipeline.domain import frames as FRAMES
    assert FRAMES.chain_slug("subject-a/loose-sequence") == "loose-sequence"
    assert FRAMES.chain_slug("loose-sequence") == "loose-sequence"
    assert FRAMES.chain_key("subject-a", "subject-a/loose-sequence") == \
        FRAMES.chain_key("subject-a", "loose-sequence")


def test_frames_last_no_longer_invents_a_second_chain(media_bucket):
    """The qualified form now lands in the same document as the bare one.

    Chains survive only for sequences with no scene behind them — which is the
    only thing they were ever actually used for. A planned scene derives its own
    frames from `scene.json`.
    """
    from studio_pipeline.domain import frames as FRAMES
    doc = FRAMES.chain_add("subject-a", "subject-a/loose-sequence",
                           "projects/subject-a/input/subject-a_3.png", None)
    assert doc["chain"] == "subject-a/loose-sequence"
    keys = [o["Key"] for o in media_bucket.list_objects_v2(
        Bucket=BUCKET, Prefix="projects/subject-a/chains/")["Contents"]]
    assert keys == ["projects/subject-a/chains/loose-sequence.json"]


def test_a_handoff_writes_no_second_record(media_bucket):
    """The point of collapsing chains into the scene: there is now exactly one
    place the sequence lives, so it cannot drift from the scene it describes."""
    m = SC.read_manifest("subject-a", PLANNED)
    m["shots"][0]["run"] = "subject-a/2026-08-04_21-30-54_wave-porch"
    SC.write_manifest(m)

    before = media_bucket.list_objects_v2(
        Bucket=BUCKET, Prefix="projects/subject-a/chains/").get("Contents", [])
    run("scenes", "handoff", f"subject-a/{PLANNED}", "--shot", "2")
    after = media_bucket.list_objects_v2(
        Bucket=BUCKET, Prefix="projects/subject-a/chains/").get("Contents", [])
    assert [o["Key"] for o in before] == [o["Key"] for o in after]


# ══════════════════════════════════════════════════════════════════════════
# Folders, since the tree became rows (#305)
#
# S3 made `scenes/<slug>/` out of the slashes in a key, so nothing ever asked
# for a folder. The catalog needs the node before a file can hang off it, and
# the moto shim answers `store.folder` without writing anything — which is
# honest for S3 and means these are the only tests that can see the calls.
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def folders(media_bucket, monkeypatch):
    """Every path `store.folder` was asked to ensure, in order."""
    from studio_pipeline.adapters import store

    seen = []
    original = store.folder
    monkeypatch.setattr(store, "folder", lambda path: seen.append(path) or original(path))
    return seen


def test_starting_a_scene_creates_its_folder(folders, tmp_path):
    """**The failure this migration would otherwise have shipped.**

    `new_scene` writes a `scene.json` for a scene that has never existed. Under
    S3 the folder came free with the key; here the write resolves a parent, and
    without this it is a parent nobody made.
    """
    plan = write_plan(tmp_path)

    result = run("scenes", "new", "subject-a", "--slug", "brand-new", "--from-json", str(plan))

    assert result.exit_code == 0, result.output
    assert "projects/subject-a/scenes/brand-new" in folders


def test_assembling_creates_the_shots_and_output_folders(folders, monkeypatch):
    """Both are written into, and neither exists until the first cut.

    ffmpeg is stubbed rather than run: the fixture's `.mp4` objects are the
    string `mp4-bytes`, so a real stitch has nothing to probe. What is under
    test is the ordering around it — the folder has to exist before the shot
    copy and the cut land in it.
    """
    m = SC.read_manifest("subject-a", LEGACY)
    # The fixture records `shot_key` but not `key`, so `shot_video_key` would go
    # back to the run — which holds a still, not a video.
    m["shots"][0]["key"] = f"projects/subject-a/scenes/{LEGACY}/shots/shot-01.mp4"
    SC.write_manifest(m)
    def _stitch(sources, out, **_):
        pathlib.Path(out).write_bytes(b"cut-bytes")   # the joiner's only side effect
        return {"probes": [{"duration": 5.0} for _ in sources]}

    monkeypatch.setattr(SC, "stitch", _stitch)
    monkeypatch.setattr(SC, "probe", lambda *a, **k: {"duration": 5.0})
    folders.clear()

    SC.assemble("subject-a", LEGACY)

    assert f"projects/subject-a/scenes/{LEGACY}/shots" in folders
    assert f"projects/subject-a/scenes/{LEGACY}/output" in folders


def test_recording_a_chain_frame_creates_the_chains_folder(folders):
    """A project's first chain has nowhere to go until something asks."""
    from studio_pipeline.domain import frames as FRAMES

    folders.clear()
    FRAMES.chain_add("subject-a", "a-new-chain",
                     "projects/subject-a/input/subject-a_3.png", None)

    assert "projects/subject-a/chains" in folders


def test_a_refusal_does_not_read_as_an_empty_chain(monkeypatch):
    """**This used to be a bare `except`.**

    An absent chain reads as an empty one, and an empty chain is what
    `chain_add` appends to — so a 403 would have started a second chain beside
    the real one instead of saying no.
    """
    from studio_pipeline.adapters import api, store
    from studio_pipeline.domain import frames as FRAMES

    def _read(_path):
        raise api.Forbidden("not your library", 403)

    monkeypatch.setattr(store, "read", _read)

    with pytest.raises(api.Forbidden):
        FRAMES.load_chain("subject-a", "loose-sequence")


# ──────────────────────────── presigning ────────────────────────────


def test_scenes_outputs_can_presign(media_bucket):
    """The `--presign` flag shadows any same-named function in its own scope."""
    result = run("scenes", "outputs", f"subject-a/{LEGACY}", "--presign")

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "https://" in result.output


def test_scenes_outputs_says_expires_is_ignored(media_bucket):
    result = run("scenes", "outputs", f"subject-a/{LEGACY}", "--presign", "--expires", "60")

    assert result.exit_code == 0, result.output
    assert "--expires 60 is ignored" in result.output


def test_movies_outputs_can_presign(media_bucket, monkeypatch, tmp_path):
    """The movie tier has the same flag and the same shadowing trap."""
    def _stitch(sources, out, **_):
        pathlib.Path(out).write_bytes(b"cut-bytes")
        return {"probes": [{"duration": 5.0} for _ in sources]}

    monkeypatch.setattr(MOV, "stitch", _stitch)
    monkeypatch.setattr(MOV, "probe", lambda *a, **k: {"duration": 5.0})
    movie = MOV.create("subject-a", "whole-thing", [f"subject-a/{LEGACY}"])

    result = run("movies", "outputs", movie["movie"], "--presign", "--expires", "60")

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "https://" in result.output
    assert "--expires 60 is ignored" in result.output


def test_cutting_a_movie_creates_its_scenes_and_output_folders(folders, monkeypatch):
    """Neither exists until the first cut, same as a scene's."""
    def _stitch(sources, out, **_):
        pathlib.Path(out).write_bytes(b"cut-bytes")
        return {"probes": [{"duration": 5.0} for _ in sources]}

    monkeypatch.setattr(MOV, "stitch", _stitch)
    monkeypatch.setattr(MOV, "probe", lambda *a, **k: {"duration": 5.0})
    folders.clear()

    movie = MOV.create("subject-a", "whole-thing", [f"subject-a/{LEGACY}"])

    _project, _, movie_id = movie["movie"].partition("/")
    assert f"projects/subject-a/movies/{movie_id}/scenes" in folders
    assert f"projects/subject-a/movies/{movie_id}/output" in folders
