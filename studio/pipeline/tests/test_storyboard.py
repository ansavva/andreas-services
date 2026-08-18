"""The scene plan: roles, status, and what survives a revision.

Pure functions over a document — no S3, no models, no Click — so everything here
is the logic that decides what a shot *sends*, isolated from the machinery that
sends it.

Three things would fail silently rather than loudly, and they are what this file
is mostly about:

  * **Which panel is the start frame.** Get it wrong and the render still
    succeeds; it just cuts badly, or animates from the wrong composition. The
    handoff outranking a panel is the subtle half — a shot that continues a
    movement must open on the literal last frame of the shot before it, not on a
    panel that merely resembles it.
  * **A re-ingest orphaning paid work.** Revising a scene means re-ingesting the
    whole plan. If the merge drops a recorded run, the clip is still in S3 and
    the scene no longer knows about it, so it silently vanishes from the cut.
  * **A scene slug shaped like a run id.** Scene folders used to be
    `<timestamp>_<slug>` and those still exist, so such a slug would collide with
    a real one — and the failure would surface as a scene resolving to the wrong
    directory.
"""

from __future__ import annotations

import json

import pytest

from studio_pipeline.domain import storyboard as SB


def plan(**over):
    """A two-shot plan: one panel on the first shot, three on the second."""
    base = {
        "defaults": {"model": "kling", "panel_model": "nano-banana-pro", "duration": 5},
        "shots": [
            {"beat": "one", "panels": [{"prompt": "a"}], "motion": {"prompt": "m1"}},
            {"beat": "two",
             "panels": [{"prompt": "b"}, {"prompt": "c"}, {"prompt": "d"}],
             "motion": {"prompt": "m2"}},
        ],
    }
    base.update(over)
    return SB.normalise(base, "proj", "my-scene")


# --- roles -----------------------------------------------------------------

@pytest.mark.parametrize("count, expected", [
    (1, ["start"]),
    (2, ["start", "end"]),
    (3, ["start", "reference", "end"]),
    (5, ["start", "reference", "reference", "reference", "end"]),
])
def test_panel_roles_default_by_position(count, expected):
    """One panel is a start frame; two bracket the shot; extras pin the middle."""
    shot = {"panels": [{"n": i, "prompt": "x"} for i in range(1, count + 1)]}
    assert SB.panel_roles(shot) == expected


def test_an_explicit_role_beats_the_positional_default():
    shot = {"panels": [{"n": 1, "role": "reference"}, {"n": 2}, {"n": 3}]}
    assert SB.panel_roles(shot) == ["reference", "reference", "end"]


def test_a_handoff_takes_the_start_slot_and_demotes_the_panel():
    """A cut is only seamless from the literal last frame of the shot before it.

    The displaced panel is not discarded — it rides along as a reference, still
    steering where the shot goes.
    """
    m = plan()
    shot = m["shots"][1]
    shot["opens_on"]["key"] = "projects/proj/input/proj_in_9.png"

    r = SB.resolve_roles(shot)
    assert r["handoff"] == "projects/proj/input/proj_in_9.png"
    assert r["start_panel"] is None, "the handoff owns the start slot"
    assert r["demoted"] is True
    assert r["reference_panels"] == [0, 1], "the demoted start comes first, in panel order"
    assert r["end_panel"] == 2, "the end frame is unaffected"


def test_shot_one_has_no_handoff_so_its_first_panel_really_is_the_start():
    m = plan()
    shot = m["shots"][0]
    assert shot["continues"] is False, "nothing precedes shot 1"
    r = SB.resolve_roles(shot)
    assert r["start_panel"] == 0 and r["demoted"] is False


def test_continues_false_forces_the_panel_back():
    """The right answer when a shot deliberately opens on a new composition."""
    m = plan()
    shot = m["shots"][1]
    shot["opens_on"]["key"] = "projects/proj/input/proj_in_9.png"
    shot["continues"] = False

    r = SB.resolve_roles(shot)
    assert r["handoff"] is None
    assert r["start_panel"] == 0 and r["demoted"] is False


# --- defaults --------------------------------------------------------------

def test_shots_inherit_the_scene_defaults():
    m = plan()
    assert m["shots"][0]["motion"]["model"] == "kling"
    assert m["shots"][0]["motion"]["duration"] == 5
    assert m["shots"][0]["panels"][0]["model"] == "nano-banana-pro"


def test_a_shot_overrides_one_default_without_restating_the_rest():
    m = SB.normalise({
        "defaults": {"model": "kling", "duration": 5, "extra": {"mode": "standard"}},
        "shots": [{"panels": [{"prompt": "a"}],
                   "motion": {"prompt": "m", "duration": 12,
                              "extra": {"generate_audio": True}}}],
    }, "proj", "my-scene")
    motion = m["shots"][0]["motion"]
    assert motion["duration"] == 12, "the override wins"
    assert motion["model"] == "kling", "everything else still inherits"
    assert motion["extra"] == {"mode": "standard", "generate_audio": True}, \
        "extra merges rather than replacing, so one knob can move alone"


def test_a_panel_never_inherits_the_video_models_settings():
    """`model` and `extra` at scene level belong to the VIDEO engine.

    A panel inheriting them would ask an image model for `mode: standard` and
    `generate_audio`, which it has never heard of — caught at preflight, but only
    after a plan that reads fine has been written and reviewed.
    """
    m = SB.normalise({
        "defaults": {"model": "kling", "extra": {"mode": "standard", "generate_audio": False},
                     "panel_model": "nano-banana-pro", "panel_extra": {"output_format": "png"}},
        "shots": [{"panels": [{"prompt": "a"}], "motion": {"prompt": "m"}}],
    }, "proj", "my-scene")
    panel = m["shots"][0]["panels"][0]
    assert panel["model"] == "nano-banana-pro"
    assert panel["extra"] == {"output_format": "png"}
    assert "generate_audio" not in panel["extra"] and "mode" not in panel["extra"]
    assert m["shots"][0]["motion"]["extra"] == {"mode": "standard", "generate_audio": False}


def test_only_the_first_shot_opens_on_its_own_panel_by_default():
    """Building a scene as a sequence is the point; every later shot continues."""
    m = plan()
    assert m["shots"][0]["continues"] is False
    assert m["shots"][1]["continues"] is True


def test_motion_references_default_to_the_scenes_own_frames_not_the_character():
    """Sending a character's curated set mid-scene fights the continuity a scene
    exists to hold, so it stays empty unless the plan asks."""
    m = plan()
    refs = m["shots"][1]["motion"]["references"]
    assert refs["characters"] == []
    assert refs["max_scene_frames"] is None, "all of them, unless a cap is asked for"


# --- validation ------------------------------------------------------------

def test_duplicate_shot_ids_are_refused_because_they_are_the_merge_key():
    m = plan()
    m["shots"][1]["id"] = m["shots"][0]["id"]
    with pytest.raises(SB.PlanError) as exc:
        SB.validate(m)
    assert "duplicate shot id" in str(exc.value)


def test_two_panels_cannot_both_be_the_start_frame():
    m = plan()
    m["shots"][1]["panels"][1]["role"] = "start"
    with pytest.raises(SB.PlanError) as exc:
        SB.validate(m)
    assert "start frame" in str(exc.value)


def test_an_unknown_role_is_refused_naming_the_real_ones():
    m = plan()
    m["shots"][0]["panels"][0]["role"] = "middle"
    with pytest.raises(SB.PlanError) as exc:
        SB.validate(m)
    assert "'middle'" in str(exc.value) and "reference" in str(exc.value)


def test_a_shot_with_no_panel_and_no_motion_is_refused():
    m = SB.normalise({"shots": [{"beat": "nothing"}]}, "proj", "my-scene")
    with pytest.raises(SB.PlanError):
        SB.validate(m)


def test_a_scene_with_no_shots_is_refused():
    with pytest.raises(SB.PlanError):
        SB.validate(SB.normalise({"shots": []}, "proj", "my-scene"))


def test_a_slug_shaped_like_a_run_id_is_refused():
    """Scene folders used to be `<timestamp>_<slug>` and those still resolve, so
    such a slug would be indistinguishable from a legacy scene."""
    with pytest.raises(SB.PlanError) as exc:
        SB.check_scene_slug("2026-08-16_07-40-22_stadium-encounter")
    assert "run id" in str(exc.value)
    assert SB.check_scene_slug("stadium-encounter") == "stadium-encounter"


def test_an_ordinary_bad_slug_is_still_refused():
    with pytest.raises(SB.PlanError):
        SB.check_scene_slug("Not A Slug")


def test_load_plan_names_the_file_that_is_wrong(tmp_path):
    bad = tmp_path / "plan.json"
    bad.write_text("{not json")
    with pytest.raises(SB.PlanError) as exc:
        SB.load_plan(str(bad))
    assert str(bad) in str(exc.value)

    with pytest.raises(SB.PlanError) as exc:
        SB.load_plan(str(tmp_path / "absent.json"))
    assert "no such plan file" in str(exc.value)

    listy = tmp_path / "listy.json"
    listy.write_text(json.dumps([1, 2]))
    with pytest.raises(SB.PlanError) as exc:
        SB.load_plan(str(listy))
    assert "must be a JSON object" in str(exc.value)


# --- status ----------------------------------------------------------------

def test_shot_status_is_derived_from_what_the_shot_has():
    shot = {"panels": [{"n": 1, "prompt": "a"}]}
    assert SB.shot_status(shot) == "planned"
    shot["panels"][0]["key"] = "projects/p/scenes/s/storyboard/shot-01-p1.png"
    assert SB.shot_status(shot) == "boarded"
    shot["run"] = "p/2026-08-18_10-00-00_x"
    assert SB.shot_status(shot) == "rendered"
    shot["shot_key"] = "projects/p/scenes/s/shots/shot-01.mp4"
    assert SB.shot_status(shot) == "cut"


def test_a_reference_only_panel_does_not_hold_a_shot_back_from_boarded():
    """Only the panels that BIND — the start and end frames — gate the status.

    A reference panel is optional steering; waiting on one would leave a shot
    perpetually unboarded for an image it can render perfectly well without.
    """
    shot = {"panels": [
        {"n": 1, "prompt": "a", "key": "k1"},
        {"n": 2, "prompt": "b", "role": "reference"},
        {"n": 3, "prompt": "c", "key": "k3"},
    ]}
    assert SB.shot_status(shot) == "boarded"


def test_scene_status_walks_from_planned_to_assembled():
    m = plan()
    assert SB.scene_status(m) == "planned"
    m["shots"][0]["panels"][0]["key"] = "k"
    assert SB.scene_status(m) == "boarding", "some boarded, not all"
    for p in m["shots"][1]["panels"]:
        p["key"] = "k"
    assert SB.scene_status(m) == "boarded"
    m["shots"][0]["run"] = "p/2026-08-18_10-00-00_x"
    assert SB.scene_status(m) == "shooting"
    m["output"] = {"key": "projects/proj/scenes/my-scene/output/my-scene.mp4"}
    assert SB.scene_status(m) == "assembled"


def test_is_assembled_is_the_planned_versus_cut_discriminator():
    m = plan()
    assert SB.is_assembled(m) is False
    m["output"] = {"key": "projects/proj/scenes/my-scene/output/my-scene.mp4"}
    assert SB.is_assembled(m) is True


# --- revising --------------------------------------------------------------

def test_a_re_ingest_carries_recorded_work_forward():
    """Editing prose must not throw away clips that have already been paid for."""
    old = plan()
    old["shots"][0]["run"] = "proj/2026-08-18_10-00-00_shot-01"
    old["shots"][0]["key"] = "projects/proj/runs/2026-08-18_10-00-00_shot-01/output/x.mp4"
    old["shots"][0]["shot_key"] = "projects/proj/scenes/my-scene/shots/shot-01.mp4"
    old["shots"][0]["duration"] = 5.04
    old["shots"][0]["panels"][0]["key"] = "projects/proj/scenes/my-scene/storyboard/shot-01-p1.png"
    old["shots"][1]["opens_on"]["key"] = "projects/proj/input/proj_in_9.png"

    revised = plan()
    revised["shots"][0]["beat"] = "one, but reworded"
    merged = SB.merge(old, revised)

    assert merged["shots"][0]["run"] == "proj/2026-08-18_10-00-00_shot-01"
    assert merged["shots"][0]["duration"] == 5.04
    assert merged["shots"][0]["panels"][0]["key"].endswith("shot-01-p1.png")
    assert merged["shots"][1]["opens_on"]["key"].endswith("proj_in_9.png")
    assert merged["shots"][0]["status"] == "cut"


def test_a_changed_panel_prompt_keeps_its_image_and_marks_it_stale():
    """The picture on disk no longer illustrates the words beside it. That is a
    warning, not a block — living with an out-of-date panel can be the right
    call, and the point of a board this cheap is that the choice is yours."""
    old = plan()
    old["shots"][0]["panels"][0]["key"] = "projects/proj/scenes/my-scene/storyboard/shot-01-p1.png"

    revised = plan()
    revised["shots"][0]["panels"][0]["prompt"] = "a, but different"
    merged = SB.merge(old, revised)

    panel = merged["shots"][0]["panels"][0]
    assert panel["key"].endswith("shot-01-p1.png"), "the image is kept"
    assert panel["stale"] is True


def test_whitespace_alone_does_not_make_a_panel_stale():
    old = plan()
    old["shots"][0]["panels"][0]["prompt"] = "a  wrapped\n  prompt"
    old["shots"][0]["panels"][0]["key"] = "k"
    revised = plan()
    revised["shots"][0]["panels"][0]["prompt"] = "a wrapped prompt"
    assert SB.merge(old, revised)["shots"][0]["panels"][0]["stale"] is False


def test_staleness_survives_a_further_revision():
    """Once stale, a panel stays stale until it is re-rendered — a second edit
    that happens to restore the original wording must not clear the flag."""
    old = plan()
    old["shots"][0]["panels"][0]["key"] = "k"
    old["shots"][0]["panels"][0]["stale"] = True
    assert SB.merge(old, plan())["shots"][0]["panels"][0]["stale"] is True


def test_a_shot_renamed_between_revisions_starts_clean():
    """Ids are the merge key; a new id is a new shot, by definition."""
    old = plan()
    old["shots"][0]["run"] = "proj/2026-08-18_10-00-00_shot-01"
    revised = plan()
    revised["shots"][0]["id"] = "opening"
    assert SB.merge(old, revised)["shots"][0]["run"] is None


def test_a_merge_preserves_the_original_creation_time():
    old = plan()
    old["created"] = "2026-01-01T00:00:00+00:00"
    revised = plan()
    revised["created"] = None
    assert SB.merge(old, revised)["created"] == "2026-01-01T00:00:00+00:00"


# --- reading the board -----------------------------------------------------

def test_sheet_captions_name_the_role_because_position_does_not():
    m = plan()
    m["shots"][0]["panels"][0]["key"] = "k1"
    m["shots"][1]["panels"][0]["key"] = "k2"
    m["shots"][1]["panels"][2]["key"] = "k4"
    m["shots"][1]["panels"][2]["stale"] = True

    assert SB.sheet_captions(m) == [
        ("k1", "shot-01 p1 [start]"),
        ("k2", "shot-02 p1 [start]"),
        ("k4", "shot-02 p3 [end] STALE"),
    ]


def test_sheet_captions_skip_panels_that_do_not_exist_yet():
    assert SB.sheet_captions(plan()) == []


# --- the scene's own frames ------------------------------------------------

def test_scene_frames_are_derived_from_the_plan():
    """They used to live in a `chains/<slug>.json` written beside the scene and
    kept in sync by hand. Everything the list needs is already in the plan: shot
    1's opening panel is the seed, and every later shot's `opens_on.key` is the
    handoff the shot before it produced."""
    m = plan()
    assert SB.scene_frames(m) == [], "nothing rendered yet"

    m["shots"][0]["panels"][0]["key"] = "seed.png"
    assert SB.scene_frames(m) == ["seed.png"]

    m["shots"][1]["opens_on"]["key"] = "handoff-1.png"
    assert SB.scene_frames(m) == ["seed.png", "handoff-1.png"]


def test_scene_frames_keep_both_ends_when_a_cap_forces_a_choice():
    """The seed anchors the look the whole scene inherits; the newest frames
    carry the current state. The middle is what gives way."""
    m = plan()
    m["shots"][0]["panels"][0]["key"] = "seed.png"
    m["shots"][1]["opens_on"]["key"] = "h1.png"
    # Stand in for a longer scene by appending shots that already have handoffs.
    for i in range(2, 6):
        m["shots"].append({"n": i + 1, "id": f"shot-{i:02d}", "panels": [],
                           "opens_on": {"key": f"h{i}.png"}, "continues": True})

    assert SB.scene_frames(m) == ["seed.png", "h1.png", "h2.png", "h3.png",
                                  "h4.png", "h5.png"]
    assert SB.scene_frames(m, 3) == ["seed.png", "h4.png", "h5.png"]
    assert SB.scene_frames(m, 2) == ["seed.png", "h5.png"]
    # A cap of one is the seed alone. Written as one slice this returns the
    # WHOLE list, because `keys[-0:]` is `keys[0:]` — the cap silently does
    # nothing and every handoff frame is billed into the payload.
    assert SB.scene_frames(m, 1) == ["seed.png"]


def test_scene_frames_never_repeat_a_key():
    m = plan()
    m["shots"][0]["panels"][0]["key"] = "seed.png"
    m["shots"][1]["opens_on"]["key"] = "seed.png"
    assert SB.scene_frames(m) == ["seed.png"]


# --- a supplied panel ------------------------------------------------------

def test_a_panel_given_as_an_image_is_supplied_not_rendered():
    """A plan can pin an image that already exists — the frame a scene opens on,
    or a pose pulled out of an earlier clip that is exactly right and would only
    be degraded by asking a model to reproduce it."""
    assert SB.is_supplied({"key": "projects/p/input/p_in_9.jpg"}) is True
    assert SB.is_supplied({"key": "k", "prompt": "   "}) is True, "whitespace is not a prompt"
    assert SB.is_supplied({"key": "k", "prompt": "render this"}) is False
    assert SB.is_supplied({"prompt": "render this"}) is False


def test_a_supplied_panel_never_goes_stale():
    """It has no prompt to have drifted from, so marking it stale would be a
    permanent warning about nothing."""
    old = plan()
    old["shots"][0]["panels"][0].update(key="projects/p/input/p_in_9.jpg", prompt="")
    revised = plan()
    revised["shots"][0]["panels"][0].update(key="projects/p/input/p_in_9.jpg", prompt="")
    revised["shots"][0]["beat"] = "reworded around it"

    panel = SB.merge(old, revised)["shots"][0]["panels"][0]
    assert panel["stale"] is False
    assert panel["key"].endswith("p_in_9.jpg")


def test_a_supplied_panel_still_counts_as_boarded():
    shot = {"panels": [{"n": 1, "key": "projects/p/input/p_in_9.jpg", "prompt": ""}]}
    assert SB.shot_status(shot) == "boarded"
