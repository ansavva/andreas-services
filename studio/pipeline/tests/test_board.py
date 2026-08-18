"""Rendering a board and rendering a shot: the gates, and the engine guards.

Two classes of thing are pinned here.

**The gates.** These are the two commands in a scene's life that spend money.
`--dry-run` must render every payload and create no prediction; the confirm must
be the only way through; and no `--yes` flag may exist on either — an approval
flag is the door an agent walks through while believing some earlier exchange
counted as consent. The dry-run assertion in particular exists because that
exact gate was once broken by a `json` vs `json_` attribute and `--help` still
passed.

**That the model rules were not reimplemented.** `submit.gather` and
`submit.preflight` already know every cap, exclusion and format rule, with error
messages that name the fix. This module is supposed to decide role and order and
hand the result over, so the tests assert that a violation comes back in
`submit`'s own words. A copy of a cap here would pass a test written against the
copy and drift from the original.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters.s3 import BUCKET
from studio_pipeline.domain import scenes as SC
from studio_pipeline.engine import board as BOARD
from studio_pipeline.engine import registry as REG

PLANNED = "board-test"
SCENE = f"subject-a/{PLANNED}"


@pytest.fixture
def no_network(monkeypatch):
    """A permissive live schema, and a prediction call that refuses to be made."""
    def props(*_a, **_k):
        fields = {"prompt", "aspect_ratio", "output_format", "quality", "moderation",
                  "mode", "duration", "generate_audio", "image_input", "input_images",
                  "reference_images", "start_image", "end_image", "image",
                  "last_frame_image"}
        return {f: {} for f in fields}, {}

    monkeypatch.setattr("studio_pipeline.engine.schema.fetch", props)

    def refuse(*_a, **_k):
        raise AssertionError("nothing may create a prediction in this suite")

    monkeypatch.setattr("studio_pipeline.adapters.replicate.create_prediction", refuse)


def run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def board_ready(s3):
    """The fixture scene, with every panel landed so a shot can be rendered."""
    m = SC.read_manifest(s3, "subject-a", PLANNED)
    for shot in m["shots"]:
        for panel in shot["panels"]:
            key = f"projects/subject-a/scenes/{PLANNED}/storyboard/{shot['id']}-p{panel['n']}.png"
            s3.put_object(Bucket=BUCKET, Key=key, Body=b"png-bytes")
            panel["key"] = key
    return SC.write_manifest(s3, m)


# --- the gates -------------------------------------------------------------

def test_board_dry_run_shows_every_payload_and_submits_nothing(media_bucket, no_network):
    r = run("scenes", "board", SCENE, "--dry-run")
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    assert "1/2  PROMPT" in r.output and "2/2  INPUT" in r.output
    assert "shot-02 panel 1" in r.output
    assert "nothing billed" in r.output


def test_board_skips_a_panel_that_already_exists(media_bucket, no_network):
    """Shot 1's panel is already on the board in the fixture."""
    r = run("scenes", "board", SCENE, "--dry-run")
    assert "shot-01 panel 1" not in r.output
    r = run("scenes", "board", SCENE, "--dry-run", "--redo")
    assert "shot-01 panel 1" in r.output


def test_render_dry_run_shows_the_payload_and_submits_nothing(media_bucket, no_network):
    board_ready(media_bucket)
    r = run("scenes", "render", SCENE, "--shot", "1", "--dry-run")
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    assert "1/2  PROMPT" in r.output and "2/2  INPUT" in r.output
    assert "nothing billed" in r.output


def test_declining_the_confirm_submits_nothing(media_bucket, no_network, monkeypatch):
    monkeypatch.setattr("click.confirm", lambda *a, **k: False)
    r = run("scenes", "board", SCENE)
    assert r.exit_code == 1
    assert "nothing submitted" in r.output


@pytest.mark.parametrize("command", ["board", "render"])
def test_no_approval_flag_exists(command):
    """There is no way to answer the gate from a command line, by design."""
    help_text = run("scenes", command, "--help").output
    assert "--yes" not in help_text
    assert "--dry-run" in help_text


def test_render_requires_a_shot(media_bucket, no_network):
    """No whole-scene default: a four-shot scene with audio is real money, and
    a later shot's start frame does not exist until the one before it is cut."""
    r = run("scenes", "render", SCENE, "--dry-run")
    assert r.exit_code != 0
    assert "--shot" in r.output


# --- roles, turned into bindings -------------------------------------------

def test_the_first_shot_starts_from_its_own_panel(media_bucket, no_network):
    m = board_ready(media_bucket)
    entry = REG.get("kling")
    start, end, refs, _notes = BOARD.shot_bindings(
        media_bucket, m, m["shots"][0], entry)
    assert start.endswith("shot-01-p1.png")
    assert end is None, "one panel is a start frame, not a pair"
    # The chain's seed rides along: it is the look the whole scene inherits.
    assert refs == ["projects/subject-a/input/subject-a_3.png"]


def test_a_handoff_takes_the_start_slot_and_the_panel_becomes_a_reference(
        media_bucket, no_network):
    m = board_ready(media_bucket)
    shot = m["shots"][1]
    shot["chain"]["start_key"] = "projects/subject-a/input/subject-a_1.webp"

    start, end, refs, notes = BOARD.shot_bindings(media_bucket, m, shot, REG.get("kling"))
    assert start == "projects/subject-a/input/subject-a_1.webp"
    assert refs[0].endswith("shot-02-p1.png"), "the demoted panel leads the references"
    assert end.endswith("shot-02-p2.png")
    assert any("seamless" in n for n in notes), "the demotion is reported, not silent"


def test_a_shot_that_expects_a_handoff_and_has_none_says_so(media_bucket, no_network):
    m = board_ready(media_bucket)
    _s, _e, _r, notes = BOARD.shot_bindings(media_bucket, m, m["shots"][1], REG.get("kling"))
    assert any("scenes handoff" in n for n in notes)


def test_an_unrendered_panel_blocks_its_shot_and_names_the_fix(media_bucket, no_network):
    r = run("scenes", "render", SCENE, "--shot", "2", "--dry-run")
    assert r.exit_code != 0
    assert "has not been rendered yet" in r.output
    assert "studio scenes board" in r.output


def test_the_chains_frames_ride_along_behind_the_panels(media_bucket, no_network):
    """Panels are the instruction for THIS shot; the chain is context, and
    context goes last."""
    m = board_ready(media_bucket)
    media_bucket.put_object(
        Bucket=BUCKET, Key=f"projects/subject-a/chains/{PLANNED}.json",
        Body=json.dumps({
            "chain": f"subject-a/{PLANNED}", "project": "subject-a", "slug": PLANNED,
            "seed": "projects/subject-a/input/subject-a_1.webp",
            "frames": [{"n": 1, "key": "projects/subject-a/input/subject-a_2.webp"}],
        }).encode())
    shot = m["shots"][1]
    shot["chain"]["start_key"] = "projects/subject-a/scenes/board-test/shots/shot-01.mp4"

    _s, _e, refs, _n = BOARD.shot_bindings(media_bucket, m, shot, REG.get("kling"))
    assert refs[0].endswith("shot-02-p1.png"), "a panel first"
    assert refs[-1].endswith("subject-a_2.webp"), "the chain last"


# --- the model rules stay in submit ----------------------------------------

def test_a_start_frame_on_seedance_is_refused_in_submits_own_words(media_bucket, no_network):
    """Seedance sets `start_excludes_refs`: a start frame kills the reference
    list. The refusal must come from `gather`, not from a copy of the rule."""
    m = board_ready(media_bucket)
    m["shots"][1]["motion"]["model"] = "seedance"
    m["shots"][1]["chain"]["start_key"] = "projects/subject-a/input/subject-a_1.webp"
    SC.write_manifest(media_bucket, m)

    r = run("scenes", "render", SCENE, "--shot", "2", "--dry-run")
    assert r.exit_code != 0
    assert "mutually exclusive" in r.output


def test_a_webp_panel_bound_into_kling_is_refused_naming_convert(media_bucket, no_network):
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    key = f"projects/subject-a/scenes/{PLANNED}/storyboard/shot-01-p1.webp"
    media_bucket.put_object(Bucket=BUCKET, Key=key, Body=b"webp-bytes")
    m["shots"][0]["panels"][0]["key"] = key
    SC.write_manifest(media_bucket, m)

    r = run("scenes", "render", SCENE, "--shot", "1", "--dry-run")
    assert r.exit_code != 0
    assert "studio convert" in r.output


def test_a_panel_is_rendered_in_a_format_its_video_model_accepts(media_bucket, no_network):
    """Kling rejects `.webp` and GPT Image writes it by default, so a whole
    board can be rendered into a format the shot it exists for cannot read."""
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    shot, panel = m["shots"][1], m["shots"][1]["panels"][0]
    panel["model"] = "gpt-image-2"
    panel["extra"] = {}
    args = BOARD.panel_args(m, shot, panel, REG.get("gpt-image-2"),
                            _opts(dry_run=True))
    assert json.loads(args.extra)["output_format"] == "png"


def test_an_explicit_format_in_the_plan_is_left_alone(media_bucket, no_network):
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    shot, panel = m["shots"][1], m["shots"][1]["panels"][0]
    panel["model"] = "gpt-image-2"
    panel["extra"] = {"output_format": "jpg"}
    args = BOARD.panel_args(m, shot, panel, REG.get("gpt-image-2"), _opts(dry_run=True))
    assert json.loads(args.extra)["output_format"] == "jpg"


def test_a_shot_render_never_drags_in_the_characters_curated_set(media_bucket, no_network):
    """Sending a character's reference library mid-scene pulls the render toward
    the context those images were shot in and fights the continuity the chain
    exists to hold."""
    m = board_ready(media_bucket)
    args = BOARD.shot_args(m, m["shots"][0], REG.get("kling"), _opts(dry_run=True))
    assert args.character == ()
    assert args.record_characters == ("subject-a",)


def test_a_run_records_which_scene_and_shot_it_came_from(media_bucket, no_network):
    m = board_ready(media_bucket)
    shot_args = BOARD.shot_args(m, m["shots"][0], REG.get("kling"), _opts(dry_run=True))
    assert shot_args.record_extra == {"scene": SCENE, "scene_shot": "shot-01"}

    panel_args = BOARD.panel_args(m, m["shots"][0], m["shots"][0]["panels"][0],
                                  REG.get("nano-banana-pro"), _opts(dry_run=True))
    assert panel_args.record_extra == {"scene": SCENE, "scene_shot": "shot-01",
                                       "scene_panel": 1}


# --- chaining the panels ---------------------------------------------------

def test_a_panel_sees_the_panels_before_it(media_bucket, no_network):
    m = board_ready(media_bucket)
    shot = m["shots"][1]
    earlier = BOARD.earlier_panel_keys(m, shot, shot["panels"][1])
    assert [k.rsplit("/", 1)[-1] for k in earlier] == [
        "shot-01-p1.png", "shot-02-p1.png"]


def test_the_first_panel_on_the_board_sees_nothing(media_bucket, no_network):
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    m["shots"][0]["panels"][0]["key"] = None
    shot = m["shots"][0]
    assert BOARD.earlier_panel_keys(m, shot, shot["panels"][0]) == []


def test_a_long_board_keeps_the_newest_panels_rather_than_refusing(media_bucket):
    """`gather` would refuse rather than truncate, which is right — but a board
    should not need hand-pruning to keep rendering."""
    keys = [f"panel-{i}" for i in range(20)]
    assert BOARD._trim(keys, 5) == keys[-5:]
    assert BOARD._trim(keys, None) == keys


# --- check -----------------------------------------------------------------

def test_check_reports_every_problem_at_once(media_bucket, no_network):
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    m["shots"][0]["motion"]["model"] = "not-a-model"
    m["shots"][1]["panels"][0]["prompt"] = ""
    SC.write_manifest(media_bucket, m)

    r = run("scenes", "check", SCENE)
    assert r.exit_code == 1
    assert "not-a-model" in r.output
    assert "no prompt" in r.output
    assert "problem(s)" in r.output


def test_check_passes_a_plan_that_would_fly(media_bucket, no_network):
    board_ready(media_bucket)
    r = run("scenes", "check", SCENE)
    assert r.exit_code == 0, r.output
    assert "would be accepted" in r.output


def _opts(**kw):
    from types import SimpleNamespace
    base = dict(dry_run=False, dest=None, expires=3600, project=None,
                review_sheet=None, shot=(), panel=(), redo=False)
    base.update(kw)
    return SimpleNamespace(**base)
