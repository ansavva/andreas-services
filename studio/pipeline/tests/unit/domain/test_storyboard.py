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


def _shot(n, panels, **over):
    """One shot in the shape the API stores, built here rather than normalised.

    `SB.normalise` is the backend's now, so this file cannot call it — and
    should not want to. What these tests exercise is what the CLI still reads
    off a scene the API already normalised, so building that shape directly is
    both the honest fixture and the one that fails loudly if the shape moves.
    """
    return {
        "n": n, "id": f"shot-{n:02d}", "status": "planned",
        "beat": ["", "one", "two"][n] if n < 3 else "",
        "panels": [{"n": j, "role": None, "prompt": text, "node": None,
                    "run": None, "source_node": None, "boarded": None, "stale": None,
                    "model": "nano-banana-pro", "extra": {}, "aspect_ratio": None,
                    "references": {}}
                   for j, text in enumerate(panels, 1)],
        "motion": {"prompt": f"m{n}", "references": {"max_scene_frames": None,
                                                     "characters": [], "keys": []}},
        "continues": n > 1,
        "opens_on": {"node": None, "from_run": None},
        **over,
    }


def plan(**over):
    """A two-shot scene record: one panel on the first shot, three on the second."""
    base = {
        "name": "my-scene", "version": SB.VERSION, "status": "planned",
        "setting": "", "logline": "", "title": "", "characters": [],
        "defaults": {"model": "kling", "panel_model": "nano-banana-pro", "duration": 5},
        "shots": [_shot(1, ["a"]), _shot(2, ["b", "c", "d"])],
    }
    base.update(over)
    return base


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


def test_a_sample_binds_to_nothing():
    """A sample is a picture of the shot for a person, not a frame for the model.

    It is what makes a fifteen-second render judgeable before it is bought, so
    it must appear on the board and in no binding list.
    """
    shot = {"panels": [{"n": 1}, {"n": 2, "role": "sample"}]}

    r = SB.resolve_roles(shot)
    assert r["sample_panels"] == [1]
    assert r["start_panel"] == 0
    assert r["end_panel"] is None, "a sample is not the shot's last frame"
    assert r["reference_panels"] == [], "and it is not a reference either"


def test_a_sample_does_not_consume_a_positional_slot():
    """Counting positions over every panel would make the sample the end frame
    and demote the panel beside it — and an end frame on Kling silently drops
    every reference sent with it, so the mistake costs a whole render.
    """
    shot = {"panels": [{"n": 1, "role": "sample"}, {"n": 2}, {"n": 3}]}

    assert SB.panel_roles(shot) == ["sample", "start", "end"]


def test_a_shot_of_nothing_but_samples_has_no_frames():
    shot = {"panels": [{"n": 1, "role": "sample"}, {"n": 2, "role": "sample"}]}

    r = SB.resolve_roles(shot)
    assert r["sample_panels"] == [0, 1]
    assert (r["start_panel"], r["end_panel"], r["reference_panels"]) == (None, None, [])


def test_a_handoff_takes_the_start_slot_and_demotes_the_panel():
    """A cut is only seamless from the literal last frame of the shot before it.

    The displaced panel is not discarded — it rides along as a reference, still
    steering where the shot goes.
    """
    m = plan()
    shot = m["shots"][1]
    shot["opens_on"]["node"] = "node-handoff"

    r = SB.resolve_roles(shot)
    assert r["handoff"] == "node-handoff"
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
    shot["opens_on"]["node"] = "node-handoff"
    shot["continues"] = False

    r = SB.resolve_roles(shot)
    assert r["handoff"] is None
    assert r["start_panel"] == 0 and r["demoted"] is False


# --- defaults --------------------------------------------------------------

def test_a_name_shaped_like_a_run_id_is_allowed():
    """**This asserted the opposite, and the reason it did has expired.**

    A scene folder was once `<timestamp>_<slug>`, so a scene NAMED that way
    would have been indistinguishable from one of them and the resolver would
    have gone to the wrong directory. A scene is a row with a UUID now and its
    folder is named by that id; there is nothing left for a timestamp-shaped
    name to collide with.
    """
    assert SB.check_scene_name("2026-08-16_07-40-22_the-encounter") == \
        "2026-08-16_07-40-22_the-encounter"
    assert SB.check_scene_name("the-encounter") == "the-encounter"


def test_a_name_with_spaces_and_capitals_is_accepted_and_folded():
    """**The slug character class went with slugs.**

    `Not A Slug` was refused, because the name became a path segment and was
    claimed. A scene's folder is named by its id and its name is a label, so the
    only thing left worth refusing is an empty one.
    """
    assert SB.check_scene_name("  Not   A Slug ") == "Not A Slug"


def test_a_scene_still_needs_some_name():
    with pytest.raises(SB.PlanError):
        SB.check_scene_name("   ")


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

def test_is_assembled_is_the_planned_versus_cut_discriminator():
    m = plan()
    assert SB.is_assembled(m) is False
    m["output"] = {"node": "node-cut"}
    assert SB.is_assembled(m) is True


# --- revising --------------------------------------------------------------

def test_sheet_captions_name_the_role_because_position_does_not():
    m = plan()
    m["shots"][0]["panels"][0]["node"] = "node-k1"
    m["shots"][1]["panels"][0]["node"] = "node-k2"
    m["shots"][1]["panels"][2]["node"] = "node-k4"
    m["shots"][1]["panels"][2]["stale"] = True

    assert SB.sheet_captions(m) == [
        ("node-k1", "shot-01 p1 [start]"),
        ("node-k2", "shot-02 p1 [start]"),
        ("node-k4", "shot-02 p3 [end] STALE"),
    ]


def test_sheet_captions_skip_panels_that_do_not_exist_yet():
    assert SB.sheet_captions(plan()) == []


# --- the scene's own frames ------------------------------------------------

def test_scene_frames_are_derived_from_the_plan():
    """They used to live in a `chains/<slug>.json` written beside the scene and
    kept in sync by hand. Everything the list needs is already in the plan: shot
    1's opening panel is the seed, and every later shot's `opens_on.node` is the
    handoff the shot before it produced. Both halves are NODE IDS, so a frame
    renamed or moved is still the frame the scene opens on."""
    m = plan()
    assert SB.scene_frames(m) == [], "nothing rendered yet"

    m["shots"][0]["panels"][0]["node"] = "node-seed"
    assert SB.scene_frames(m) == ["node-seed"]

    m["shots"][1]["opens_on"]["node"] = "node-h1"
    assert SB.scene_frames(m) == ["node-seed", "node-h1"]


def test_scene_frames_keep_both_ends_when_a_cap_forces_a_choice():
    """The seed anchors the look the whole scene inherits; the newest frames
    carry the current state. The middle is what gives way."""
    m = plan()
    m["shots"][0]["panels"][0]["node"] = "node-seed"
    m["shots"][1]["opens_on"]["node"] = "node-h1"
    # Stand in for a longer scene by appending shots that already have handoffs.
    for i in range(2, 6):
        m["shots"].append({"n": i + 1, "id": f"shot-{i:02d}", "panels": [],
                           "opens_on": {"node": f"node-h{i}"}, "continues": True})

    assert SB.scene_frames(m) == ["node-seed", "node-h1", "node-h2", "node-h3",
                                  "node-h4", "node-h5"]
    assert SB.scene_frames(m, 3) == ["node-seed", "node-h4", "node-h5"]
    assert SB.scene_frames(m, 2) == ["node-seed", "node-h5"]
    # A cap of one is the seed alone. Written as one slice this returns the
    # WHOLE list, because `nodes[-0:]` is `nodes[0:]` — the cap silently does
    # nothing and every handoff frame is billed into the payload.
    assert SB.scene_frames(m, 1) == ["node-seed"]


def test_scene_frames_never_repeat_a_key():
    m = plan()
    m["shots"][0]["panels"][0]["node"] = "node-seed"
    m["shots"][1]["opens_on"]["node"] = "node-seed"
    assert SB.scene_frames(m) == ["node-seed"]


# --- a supplied panel ------------------------------------------------------

def test_a_panel_given_as_an_image_is_supplied_not_rendered():
    """A plan can pin an image that already exists — the frame a scene opens on,
    or a pose pulled out of an earlier clip that is exactly right and would only
    be degraded by asking a model to reproduce it."""
    assert SB.is_supplied({"node": "node-supplied"}) is True
    assert SB.is_supplied({"node": "node-supplied", "prompt": "   "}) is True, \
        "whitespace is not a prompt"
    assert SB.is_supplied({"node": "node-supplied", "prompt": "render this"}) is False
    assert SB.is_supplied({"prompt": "render this"}) is False


