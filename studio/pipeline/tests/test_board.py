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
import pathlib
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import store
from studio_pipeline.domain import projects as PROJECTS
from studio_pipeline.domain import scenes as SC
from studio_pipeline.domain import storyboard as SB
from studio_pipeline.engine import board as BOARD
from studio_pipeline.engine import registry as REG

PLANNED = "the-encounter"
SCENE = f"porch-teaser/{PLANNED}"


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


def named(node: str) -> str:
    """The filename behind a node id.

    Every binding, panel and frame in this file is an id now, so an assertion
    that used to read `start.endswith("shot-01-p1.png")` has to go through the
    catalog. Kept as a helper rather than inlined because the ALTERNATIVE —
    asserting on ids — would pin nothing a reader can check by eye.
    """
    return store.node(node).get("name") or node


PLAN = {
    "characters": ["subject-a"],
    "defaults": {"model": "kling", "panel_model": "nano-banana-pro", "duration": 5,
                 "panel_extra": {"output_format": "png"}},
    "shots": [
        {"id": "shot-01", "beat": "opens", "continues": False,
         "panels": [{"prompt": "the opening frame",
                     "references": {"characters": ["subject-a"]}}],
         "motion": {"prompt": "the opening motion"}},
        {"id": "shot-02", "beat": "continues", "continues": True,
         "panels": [{"prompt": "he turns"}, {"prompt": "he lands"}],
         "motion": {"prompt": "the second motion"}},
    ],
}


@pytest.fixture
def scene(library, tmp_path):
    """A part-boarded scene: shot 1's panel is landed, shot 2's two are not.

    Built through `scenes new` rather than hand-written as a manifest, because
    there is no manifest to hand-write: a scene is a row and its shots are rows,
    and a fixture that poked them directly could describe a scene the API could
    not have produced.

    **Shot 1's panel is landed deliberately**, and two things depend on it.
    `board --dry-run` must SKIP it and re-render it under `--redo`, which is the
    only way to check the skip. And shot 2's panels bind the board before them —
    they name no character of their own — so with nothing landed the second
    shot's payload would bind nothing at all and the review sheet would have no
    images to lay out. That is a real refusal, not a fixture artifact, and it
    would make every test below it fail for a reason none of them is about.
    """
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(PLAN))
    record = SC.new_scene(PROJECTS.resolve("porch-teaser"), PLANNED, str(path))
    storyboard = SC.scene_folder(record, "storyboard")
    shots = SC.scene_shots(record)
    shots[0]["panels"][0]["node"] = library.fake.put_file(
        storyboard, "shot-01-p1.png", b"png-bytes")["id"]
    return SC.save_shots(record, shots)


def board_ready(library, scene):
    """The fixture scene with every panel landed, so a shot can be rendered.

    A panel's boarded image is a NODE now, so this makes real nodes in the
    scene's `storyboard/` folder rather than putting keys in a document.
    """
    storyboard = SC.scene_folder(scene, "storyboard")
    shots = SC.scene_shots(scene)
    for shot in shots:
        for panel in shot["panels"]:
            if panel.get("node"):
                continue      # the fixture already landed shot 1's
            node = library.fake.put_file(
                storyboard, f"{shot['id']}-p{panel['n']}.png", b"png-bytes")
            panel["node"] = node["id"]
    return SC.save_shots(scene, shots)


# --- the gates -------------------------------------------------------------

def test_board_dry_run_shows_every_payload_and_submits_nothing(library, scene, no_network):
    r = run("scenes", "board", SCENE, "--dry-run")
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    assert "1/2  PROMPT" in r.output and "2/2  INPUT" in r.output
    assert "shot-02 panel 1" in r.output
    assert "nothing billed" in r.output


def test_board_skips_a_panel_that_already_exists(library, scene, no_network):
    """Shot 1's panel is already on the board in the fixture."""
    r = run("scenes", "board", SCENE, "--dry-run")
    assert "shot-01 panel 1" not in r.output
    r = run("scenes", "board", SCENE, "--dry-run", "--redo")
    assert "shot-01 panel 1" in r.output


def test_render_dry_run_shows_the_payload_and_submits_nothing(library, scene, no_network):
    board_ready(library, scene)
    r = run("scenes", "render", SCENE, "--shot", "1", "--dry-run")
    assert r.exit_code == 0, f"{r.output}\n{r.exception!r}"
    assert "1/2  PROMPT" in r.output and "2/2  INPUT" in r.output
    assert "nothing billed" in r.output


def test_declining_the_confirm_submits_nothing(library, scene, no_network, monkeypatch):
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


def test_render_requires_a_shot(library, scene, no_network):
    """No whole-scene default: a four-shot scene with audio is real money, and
    a later shot's start frame does not exist until the one before it is cut."""
    r = run("scenes", "render", SCENE, "--dry-run")
    assert r.exit_code != 0
    assert "--shot" in r.output


# --- roles, turned into bindings -------------------------------------------

def test_the_first_shot_starts_from_its_own_panel(library, scene, no_network):
    m = board_ready(library, scene)
    entry = REG.get("kling")
    start, end, refs, _notes = BOARD.shot_bindings(m, m["shots"][0], entry)
    assert named(start) == "shot-01-p1.png"
    assert end is None, "one panel is a start frame, not a pair"
    assert refs == [], "shot 1 IS the seed; there is nothing earlier to send"


def test_a_handoff_takes_the_start_slot_and_the_panel_becomes_a_reference(
        library, scene, no_network):
    m = board_ready(library, scene)
    shot = m["shots"][1]
    shot["opens_on"]["node"] = library.input_3

    # The demotion itself is a plan-level fact, and it holds regardless of what
    # any one model will accept.
    roles = SB.resolve_roles(shot)
    assert roles["demoted"] is True
    assert roles["start_panel"] is None and roles["reference_panels"][0] == 0

    start, end, refs, notes = BOARD.shot_bindings(m, shot, REG.get("kling"))
    assert start == library.input_3
    assert named(end) == "shot-02-p2.png"
    assert any("seamless" in n for n in notes), "the demotion is reported, not silent"
    # …and on THIS model the end frame then clears the reference list entirely.
    assert refs == []


def test_a_shot_that_expects_a_handoff_and_has_none_says_so(library, scene, no_network):
    m = board_ready(library, scene)
    _s, _e, _r, notes = BOARD.shot_bindings(m, m["shots"][1], REG.get("kling"))
    assert any("scenes handoff" in n for n in notes)


def test_an_unrendered_panel_blocks_its_shot_and_names_the_fix(library, scene, no_network):
    r = run("scenes", "render", SCENE, "--shot", "2", "--dry-run")
    assert r.exit_code != 0
    assert "has not been rendered yet" in r.output
    assert "studio scenes board" in r.output


def test_the_scenes_own_frames_ride_along_behind_the_panels(library, scene, no_network):
    """Panels are the instruction for THIS shot; the scene's earlier frames are
    context, and context goes last.

    Shown on a shot with no END frame, because an end frame clears the reference
    list on this model — see the test below.
    """
    m = board_ready(library, scene)
    shot = m["shots"][1]
    shot["panels"] = shot["panels"][:1]          # drop the end panel
    shot["opens_on"]["node"] = library.input_3

    _s, end, refs, _n = BOARD.shot_bindings(m, shot, REG.get("kling"))
    assert end is None
    assert named(refs[0]) == "shot-02-p1.png", "a panel first"
    assert named(refs[-1]) == "shot-01-p1.png", \
        "then the scene's own frames — here, shot 1's opening panel"


def test_the_scenes_own_frames_come_from_the_plan_not_a_second_document(
        library, scene, no_network):
    """A chain document beside the scene would be a second copy of the sequence.

    It used to be one: `chains/<slug>.json` was written alongside the scene and
    kept in sync by hand. `storyboard.scene_frames` derives the list from the
    plan instead — shot 1's opening panel is the seed and every later shot's
    `opens_on.node` is the handoff before it — so a stale document has nothing
    to mislead. This plants one and shows it does not reach the payload.
    """
    chains = store.ensure_child_folder(library.project_root, "chains")
    library.fake.put_file(chains["id"], f"{PLANNED}.json", json.dumps({
        "slug": PLANNED, "seed": library.input_1, "frames": [library.input_2],
    }).encode())

    m = board_ready(library, scene)
    shot = m["shots"][1]
    shot["opens_on"]["node"] = library.input_3

    _s, _e, refs, _n = BOARD.shot_bindings(m, shot, REG.get("kling"))
    assert library.input_2 not in refs, \
        "the stale chain document must not reach the payload"


# --- the model rules stay in submit ----------------------------------------

def test_a_start_frame_on_seedance_is_refused_in_submits_own_words(library, scene, no_network):
    """Seedance sets `start_excludes_refs`: a start frame kills the reference
    list. The refusal must come from `gather`, not from a copy of the rule."""
    m = board_ready(library, scene)
    m["shots"][1]["motion"]["model"] = "seedance"
    m["shots"][1]["opens_on"]["node"] = library.input_3
    SC.save_shots(m, SC.scene_shots(m))

    r = run("scenes", "render", SCENE, "--shot", "2", "--dry-run")
    assert r.exit_code != 0
    assert "mutually exclusive" in r.output


def test_a_webp_panel_bound_into_kling_is_refused_naming_convert(library, scene, no_network):
    m = SC.resolve_scene(scene["id"])
    node = library.fake.put_file(SC.scene_folder(m, "storyboard"),
                                 "shot-01-p1.webp", b"webp-bytes")
    m["shots"][0]["panels"][0]["node"] = node["id"]
    SC.save_shots(m, SC.scene_shots(m))

    r = run("scenes", "render", SCENE, "--shot", "1", "--dry-run")
    assert r.exit_code != 0
    assert "studio convert" in r.output


def test_a_panel_is_rendered_in_a_format_its_video_model_accepts(library, scene, no_network):
    """Kling rejects `.webp` and GPT Image writes it by default, so a whole
    board can be rendered into a format the shot it exists for cannot read."""
    m = SC.resolve_scene(scene["id"])
    shot, panel = m["shots"][1], m["shots"][1]["panels"][0]
    panel["model"] = "gpt-image-2"
    panel["extra"] = {}
    args = BOARD.panel_args(m, shot, panel, REG.get("gpt-image-2"),
                            _opts(dry_run=True))
    assert json.loads(args.extra)["output_format"] == "jpeg"


def test_a_panel_takes_the_smallest_format_the_video_model_accepts():
    """Among the formats that work, the smallest wins.

    A PNG plate off these models is ~2 MiB against ~0.3 MiB for the same picture
    as JPEG, and a panel is sent to a video model many times over its life. Kling
    fails somewhere above ~6.4 MiB of images in total, and it fails as a
    two-minute silence rather than a validation error, so the way not to meet
    that is to never get near it.
    """
    # Kling takes .jpg/.jpeg/.png; these two models offer jpg and png.
    assert BOARD.panel_format(REG.get("nano-banana-pro"), "kling") == "jpg"
    # GPT Image offers png/jpeg/webp — webp is out, jpeg beats png.
    assert BOARD.panel_format(REG.get("gpt-image-2"), "kling") == "jpeg"


def test_a_panel_format_falls_back_rather_than_guessing(library, scene):
    """An unregistered video model says nothing about formats, so nothing is
    forced — the plan's own `extra` is left to decide."""
    assert BOARD.panel_format(REG.get("gpt-image-2"), "not-a-model") is None


def test_an_explicit_format_in_the_plan_is_left_alone(library, scene, no_network):
    m = SC.resolve_scene(scene["id"])
    shot, panel = m["shots"][1], m["shots"][1]["panels"][0]
    panel["model"] = "gpt-image-2"
    panel["extra"] = {"output_format": "jpg"}
    args = BOARD.panel_args(m, shot, panel, REG.get("gpt-image-2"), _opts(dry_run=True))
    assert json.loads(args.extra)["output_format"] == "jpg"


def test_a_shot_render_never_drags_in_the_characters_curated_set(library, scene, no_network):
    """Sending a character's reference library mid-scene pulls the render toward
    the context those images were shot in and fights the continuity the chain
    exists to hold."""
    m = board_ready(library, scene)
    args = BOARD.shot_args(m, m["shots"][0], REG.get("kling"), _opts(dry_run=True))
    assert args.character == ()
    assert args.record_characters == ("subject-a",)


def test_a_run_records_which_scene_and_shot_it_came_from(library, scene, no_network):
    m = board_ready(library, scene)
    shot_args = BOARD.shot_args(m, m["shots"][0], REG.get("kling"), _opts(dry_run=True))
    assert shot_args.record_extra == {"scene": SCENE, "scene_shot": "shot-01"}

    panel_args = BOARD.panel_args(m, m["shots"][0], m["shots"][0]["panels"][0],
                                  REG.get("nano-banana-pro"), _opts(dry_run=True))
    assert panel_args.record_extra == {"scene": SCENE, "scene_shot": "shot-01",
                                       "scene_panel": 1}


# --- chaining the panels ---------------------------------------------------

def test_a_panel_sees_the_panels_before_it(library, scene, no_network):
    m = board_ready(library, scene)
    shot = m["shots"][1]
    earlier = BOARD.earlier_panel_keys(m, shot, shot["panels"][1])
    assert [named(node) for node in earlier] == [
        "shot-01-p1.png", "shot-02-p1.png"]


def test_the_first_panel_on_the_board_sees_nothing(library, scene, no_network):
    m = SC.resolve_scene(scene["id"])
    m["shots"][0]["panels"][0]["node"] = None
    shot = m["shots"][0]
    assert BOARD.earlier_panel_keys(m, shot, shot["panels"][0]) == []


def test_a_long_board_keeps_the_newest_panels_rather_than_refusing(library, scene):
    """`gather` would refuse rather than truncate, which is right — but a board
    should not need hand-pruning to keep rendering."""
    keys = [f"panel-{i}" for i in range(20)]
    assert BOARD._trim(keys, 5) == keys[-5:]
    assert BOARD._trim(keys, None) == keys


# --- check -----------------------------------------------------------------

def test_check_reports_every_problem_at_once(library, scene, no_network):
    m = SC.resolve_scene(scene["id"])
    m["shots"][0]["motion"]["model"] = "not-a-model"
    m["shots"][1]["panels"][0]["prompt"] = ""
    SC.save_shots(m, SC.scene_shots(m))

    r = run("scenes", "check", SCENE)
    assert r.exit_code == 1
    assert "not-a-model" in r.output
    assert "no prompt" in r.output
    assert "problem(s)" in r.output


def test_check_passes_a_plan_that_would_fly(library, scene, no_network):
    board_ready(library, scene)
    r = run("scenes", "check", SCENE)
    assert r.exit_code == 0, r.output
    assert "would be accepted" in r.output


def _opts(**kw):
    from types import SimpleNamespace
    base = dict(dry_run=False, dest=None, expires=3600, project=None,
                review_sheet=None, shot=(), panel=(), redo=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_an_oversized_payload_warns_and_names_the_fix(library, scene, no_network, capsys):
    """The failure this warns about does not look like a failure.

    Over roughly 6.4 MiB of images the provider accepts the job, sits on it for
    two minutes, and returns `PA — Prediction interrupted; please retry` with no
    start time, no metrics and empty logs. That reads as an upstream blip, which
    is what three consecutive retries were spent on.
    """
    from types import SimpleNamespace

    from studio_pipeline.engine import submit as SUB

    big = library.fake.put_file(library.input_pool, "huge.png",
                                b"x" * (7 * 1024 * 1024))["id"]
    args = SimpleNamespace(
        start_key=big, start_run=None, end_key=None, end_run=None, image_run=None,
        character=(), ref_run=(), input_=(), input=(), key=[], pick=None,
        pick_tag=None, slots=None, project=PROJECTS.resolve("porch-teaser"), no_refs=True)

    SUB.gather(REG.get("kling"), args)
    err = capsys.readouterr().err
    assert "7.0 MiB" in err
    assert "studio convert" in err
    assert "PA" in err, "the symptom is what makes this worth saying"


def test_a_payload_within_the_measured_range_says_nothing(library, scene, no_network, capsys):
    from types import SimpleNamespace

    from studio_pipeline.engine import submit as SUB

    args = SimpleNamespace(
        start_key=library.input_3, start_run=None,
        end_key=None, end_run=None, image_run=None, character=(), ref_run=(),
        input_=(), input=(), key=[], pick=None, pick_tag=None, slots=None,
        project=PROJECTS.resolve("porch-teaser"), no_refs=True)

    SUB.gather(REG.get("kling"), args)
    assert "warning" not in capsys.readouterr().err


def test_the_byte_warning_is_video_only(library, scene, no_network, capsys):
    """The image models have taken ~12 MiB of plates repeatedly and without
    complaint, so warning about them would be a false alarm on every reference
    shoot — and a warning that cries wolf is worse than none."""
    from types import SimpleNamespace

    from studio_pipeline.engine import submit as SUB

    big = library.fake.put_file(library.input_pool, "huge.png",
                                b"x" * (12 * 1024 * 1024))["id"]
    args = SimpleNamespace(
        start_key=None, start_run=None, end_key=None, end_run=None, image_run=None,
        character=(), ref_run=(), input_=(), input=(), key=[big], pick=None,
        pick_tag=None, slots=None, project=PROJECTS.resolve("porch-teaser"), no_refs=False)

    SUB.gather(REG.get("nano-banana-pro"), args)
    assert "warning" not in capsys.readouterr().err


def test_a_supplied_panel_is_never_rendered(library, scene, no_network):
    """Not by `board`, not by `--redo`, not by `check`. There is nothing to make."""
    m = SC.resolve_scene(scene["id"])
    m["shots"][1]["panels"][0].update(
        node=library.input_3, prompt="", stale=True)
    SC.save_shots(m, SC.scene_shots(m))

    for argv in (("scenes", "board", SCENE, "--dry-run"),
                 ("scenes", "board", SCENE, "--dry-run", "--redo")):
        assert "shot-02 panel 1" not in run(*argv).output

    assert "shot-02 panel 1 has no prompt" not in run("scenes", "check", SCENE).output


def test_a_continuing_shot_with_no_panel_and_no_handoff_says_it_has_nothing(
        library, scene, no_network):
    """Different from a shot that merely lacks its handoff. With no opening panel
    either, the shot would compose itself out of references — that is not a rough
    cut, it is a different shot."""
    m = board_ready(library, scene)
    m["shots"][1]["panels"] = []
    _s, _e, _r, notes = BOARD.shot_bindings(m, m["shots"][1], REG.get("kling"))
    assert any("start from nothing" in n for n in notes)
    assert not any("open on its own panel" in n for n in notes)


def test_a_review_sheet_lands_in_the_scene_not_only_on_disk(library, scene, no_network, tmp_path):
    """A review sheet is what someone looks at to decide whether to spend money.
    A local path is no use to anyone not sitting at the machine that made it —
    which, when the pipeline is driven remotely, is nobody."""
    m = board_ready(library, scene)
    entry = REG.get("kling")
    start, end, refs, _n = BOARD.shot_bindings(m, m["shots"][0], entry)
    bindings = {"start_image": start, "reference_images": refs}

    out = BOARD.review_sheet(m, "shot-01",
                             BOARD._sheet_items(entry, bindings), None, {})
    # A NODE ID, because that is what is browsable in the app and what outlives
    # the working directory. It used to be a key nobody but the API could open.
    assert out.startswith("node-")
    assert named(out) == "shot-01.png"
    assert store.node_owner(out)["kind"] == "project"


def test_a_review_sheet_still_keeps_a_local_copy_when_asked(library, scene, no_network, tmp_path):
    m = board_ready(library, scene)
    entry = REG.get("kling")
    start, _e, refs, _n = BOARD.shot_bindings(m, m["shots"][0], entry)
    out = BOARD.review_sheet(m, "shot-01",
                             BOARD._sheet_items(entry, {"start_image": start,
                                                       "reference_images": refs}),
                             str(tmp_path), {})
    assert "local copy" in out
    assert (tmp_path / "shot-01.png").is_file()


def test_an_end_frame_drops_the_references_where_the_model_demands_it(
        library, scene, no_network):
    """Kling takes a start frame and references together happily — but the moment
    an end frame joins them the payload is capped at those two and the whole
    request is rejected. Nothing in the live schema says so; it surfaced as an
    E006 after a submit.

    A shot bracketed by two approved compositions has already said what the
    references would have said, so the references give way — and it is reported,
    because a payload that quietly loses images is not the one that was
    approved.
    """
    m = board_ready(library, scene)
    shot = m["shots"][1]
    shot["opens_on"]["node"] = library.input_3

    start, end, refs, notes = BOARD.shot_bindings(m, shot, REG.get("kling"))
    assert start and end, "this shot is bracketed"
    assert refs == []
    assert any("dropped" in n for n in notes)


def test_submit_refuses_an_end_frame_beside_references(library, scene, no_network):
    """Defence in depth: the rule lives in the registry and `gather` enforces it,
    so a caller that is not the board cannot spend money finding out."""
    from types import SimpleNamespace

    from studio_pipeline.engine import submit as SUB

    args = SimpleNamespace(
        start_key=library.input_3,
        end_key=library.input_3,
        start_run=None, end_run=None, image_run=None, character=(), ref_run=(),
        input_=(), input=(), key=[library.input_3],
        pick=None, pick_tag=None, slots=None, project=PROJECTS.resolve("porch-teaser"), no_refs=False)

    with pytest.raises(SUB.SubmitError) as exc:
        SUB.gather(REG.get("kling"), args)
    assert "must be empty" in str(exc.value)
    assert "drop the end frame" in str(exc.value).lower()


def test_a_shot_can_ask_for_the_characters_references(library, scene, no_network):
    """Off by default, because a curated set was shot in another context and
    pulls the render toward it. But a scene built only from its own frames
    inherits whatever it has drifted into, and nothing pulls it back — so the
    plan can choose identity stability instead, and that choice has to reach the
    payload rather than being accepted and ignored."""
    m = board_ready(library, scene)
    shot = m["shots"][0]
    assert BOARD.shot_args(m, shot, REG.get("kling"), _opts()).character == ()

    shot["motion"]["references"].update(characters=["subject-a"], pick_tag="face")
    args = BOARD.shot_args(m, shot, REG.get("kling"), _opts())
    assert args.character == ("subject-a",)
    assert args.pick_tag == "face"


# ── the whole board, end to end ─────────────────────────────────────────────
#
# **Every dry run in this file passes on a `scenes board` that cannot work.**
# Six bugs shipped through this suite, and each was one module handing another a
# shape it did not expect — a run record where an exit code was read, bare node
# ids where assets were, a project slug where a record was, a name already taken,
# a node already deleted. None is reachable without a submit, so none was
# reachable by a test, and every one was found by paying a model to find it.
#
# These drive the real path with the provider stubbed at its three seams:
# creating a prediction, polling it, and downloading what it made.


@pytest.fixture
def a_model_that_answers(monkeypatch, tmp_path):
    """Replicate, replaced by three functions that succeed."""
    monkeypatch.setattr(
        "studio_pipeline.adapters.replicate.create_prediction",
        lambda *_a, **_k: {"id": "pred-1", "status": "starting"},
    )
    monkeypatch.setattr(
        "studio_pipeline.adapters.replicate.poll",
        lambda *_a, **_k: {"id": "pred-1", "status": "succeeded",
                           "output": ["https://example.invalid/out.png"], "metrics": {}},
    )

    def download(_url, dest):
        pathlib.Path(dest).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        return dest

    monkeypatch.setattr("studio_pipeline.adapters.replicate.download", download)


def _board(monkeypatch, ref, **kw):
    """`scenes board` with the approval answered, which is the only thing a test
    may answer for a person — the payload it approves is the fixture's own."""
    monkeypatch.setattr("click.confirm", lambda *_a, **_k: True)
    opts = SimpleNamespace(project=None, dry_run=False, dest=None, review_sheet=None,
                           shot=(), panel=None, redo=False, **kw)
    return BOARD.run_board(ref, opts)


def test_a_boarded_panel_records_the_run_the_node_and_the_copy(
    library, scene, no_network, a_model_that_answers, monkeypatch
):
    """**The path six bugs lived on.**

    A panel that renders must come back with the run that made it, the node it
    was copied to, and the run output it came from. Every one of those is written
    after the submit, so a dry run proves none of it.
    """
    _board(monkeypatch, f"porch-teaser/{PLANNED}")

    panel = SC.scene_shots(SC.resolve_scene(f"porch-teaser/{PLANNED}"))[1]["panels"][0]
    assert panel["run"].startswith("run-")
    assert panel["node"].startswith("node-")
    assert panel["source_node"].startswith("node-")
    assert panel["boarded"]
    assert not panel["stale"]


def test_every_panel_boarded_in_one_pass_is_recorded(
    library, scene, no_network, a_model_that_answers, monkeypatch
):
    """**The second panel of a board run was written into an orphan.**

    `save_shots` merges the API's response over the record, so `manifest["shots"]`
    is a new list of new dicts after every write — while the panels the submit
    loop holds were captured before it started. Mutating one was visible to the
    first save and to nothing after it, so a board of N panels rendered N, billed
    N, printed N node ids and recorded the first.

    Asserting the first panel is what every test here already did, and it is the
    one case the bug cannot reach. This asserts them all.
    """
    _board(monkeypatch, f"porch-teaser/{PLANNED}")

    panels = SC.scene_shots(SC.resolve_scene(f"porch-teaser/{PLANNED}"))[1]["panels"]
    assert len(panels) > 1, "the fixture must board more than one panel to prove this"
    for panel in panels:
        assert panel["node"], f"panel {panel['n']} rendered and recorded nothing"
        assert panel["run"], f"panel {panel['n']} recorded no run"


def test_the_copy_is_named_for_its_shot_and_panel(
    library, scene, no_network, a_model_that_answers, monkeypatch
):
    """The board holds a copy under a predictable name, so a person reading the
    folder can tell which panel is which."""
    _board(monkeypatch, f"porch-teaser/{PLANNED}")

    record = SC.resolve_scene(f"porch-teaser/{PLANNED}")
    names = {c["name"] for c in store.children_of(SC.scene_folder(record, "storyboard"))}
    assert "shot-02-p1.png" in names


def test_a_stale_panel_re_renders_over_the_copy_it_supersedes(
    library, scene, no_network, a_model_that_answers, monkeypatch
):
    """**Revising a prompt and re-boarding that panel never worked.**

    The new copy lands under the same `<shot>-p<n>` name the old one holds, so
    the rename collided and the render was billed and then discarded. The
    superseded copy is renamed aside rather than deleted, because a panel's
    inputs include the panels before it and every binding is resolved before the
    submit loop starts — deleting one dangles a reference a later panel holds.
    """
    ref = f"porch-teaser/{PLANNED}"
    _board(monkeypatch, ref)
    record = SC.resolve_scene(ref)
    first = SC.scene_shots(record)[1]["panels"][0]["node"]

    shots = SC.scene_shots(record)
    shots[1]["panels"][0]["stale"] = True
    SC.save_shots(record, shots)
    _board(monkeypatch, ref)

    after = SC.scene_shots(SC.resolve_scene(ref))[1]["panels"][0]
    assert after["node"] != first, "the panel points at the new copy"
    names = [c["name"] for c in store.children_of(SC.scene_folder(record, "storyboard"))]
    assert "shot-02-p1.png" in names
    assert any("superseded" in n for n in names), "the old copy is kept, renamed"
    # And the node a later panel might still be holding is still resolvable.
    assert store.node(first)["id"] == first
