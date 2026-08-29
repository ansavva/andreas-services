"""The scene plan's semantics — normalising, validating, merging, deriving status.

**These tests came from `pipeline/tests/unit/domain/test_storyboard.py`**, with
the code they exercise. All of it ran on one client and the API stored whatever
it was handed: `POST /api/scenes` wrote `SHOT#` rows without asking whether the
plan was coherent, and `shot_status` / `scene_status` were derived in the CLI and
recorded, so anything else that wrote a shot left them stale and the SPA drew the
stale answer.

Three behaviours changed on the way across and each has a test here saying so:

  * `normalise` is **sparse** — it writes only what the author named. It used to
    fill every field with a default, which was harmless with a client-side merge
    running first and destructive without one, because `catalog.put_shots` merges
    on "naming a field wins".
  * `validate` refuses only what cannot be **stored** — duplicate ids, a bad
    role, two start frames. "This shot has nothing to render from" is a plan in
    progress, not corruption, and refusing it would reject a plan editor's first
    save. `unrenderable` keeps that check for the ingest path.
  * `merge_panels` is the level below `put_shots`' merge, moved here from the
    pipeline, where its own docstring explained it existed *because* the API's
    merge was one level deep — which made the CLI the only client that could
    revise a plan without orphaning a board.
"""

from __future__ import annotations

import pytest

from studio_core.services import storyboard as SB


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
    return SB.normalise(base, "my-scene")


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
    }, "my-scene")
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
    }, "my-scene")
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


def test_a_scene_with_no_shots_is_refused():
    with pytest.raises(SB.PlanError):
        SB.validate(SB.normalise({"shots": []}, "my-scene"))


def test_shot_status_is_derived_from_what_the_shot_has():
    shot = {"panels": [{"n": 1, "prompt": "a"}]}
    assert SB.shot_status(shot) == "planned"
    shot["panels"][0]["node"] = "node-panel-1"
    assert SB.shot_status(shot) == "boarded"
    shot["run"] = "p/2026-08-18_10-00-00_x"
    assert SB.shot_status(shot) == "rendered"
    shot["shot_node"] = "node-shot-copy"
    assert SB.shot_status(shot) == "cut"


def test_a_reference_only_panel_does_not_hold_a_shot_back_from_boarded():
    """Only the panels that BIND — the start and end frames — gate the status.

    A reference panel is optional steering; waiting on one would leave a shot
    perpetually unboarded for an image it can render perfectly well without.
    """
    shot = {"panels": [
        {"n": 1, "prompt": "a", "node": "node-k1"},
        {"n": 2, "prompt": "b", "role": "reference"},
        {"n": 3, "prompt": "c", "node": "node-k3"},
    ]}
    assert SB.shot_status(shot) == "boarded"


def test_scene_status_walks_from_planned_to_assembled():
    m = plan()
    assert SB.scene_status(m) == "planned"
    m["shots"][0]["panels"][0]["node"] = "node-k"
    assert SB.scene_status(m) == "boarding", "some boarded, not all"
    for p in m["shots"][1]["panels"]:
        p["node"] = "node-k"
    assert SB.scene_status(m) == "boarded"
    m["shots"][0]["run"] = "p/2026-08-18_10-00-00_x"
    assert SB.scene_status(m) == "shooting"
    m["output"] = {"node": "node-cut"}
    assert SB.scene_status(m) == "assembled"


@pytest.mark.parametrize("shot, expected", [
    ({"panels": []}, "planned"),
    ({"panels": [{"n": 1, "prompt": "a"}]}, "planned"),
    ({"panels": [{"n": 1, "prompt": "a", "node": "node-1"}]}, "boarded"),
    ({"panels": [{"n": 1, "prompt": "a", "node": "node-1"},
                 {"n": 2, "prompt": "b"}]}, "planned"),
    ({"run": "run-1", "panels": [{"n": 1, "prompt": "a"}]}, "rendered"),
    ({"shot_node": "node-cut", "run": "run-1", "panels": []}, "cut"),
])
def test_a_shots_status_is_derived_and_never_stored(shot, expected):
    """Recomputed on every write, which is the discipline the character index
    follows: a status stored and never recomputed is a claim nobody checks.

    `cut` beats `rendered` beats the panels — a shot that has been stitched does
    not stop being cut because somebody edited a prompt underneath it.
    """
    assert SB.shot_status(shot) == expected


def test_a_reference_panel_does_not_hold_a_shot_back():
    """`shot_status` counts only the panels that BIND — a reference is an input
    to the render, not a frame of it, so a shot whose binding panels are all
    boarded is boarded."""
    shot = {"panels": [{"n": 1, "prompt": "a", "node": "node-1"},
                       {"n": 2, "prompt": "b", "node": "node-2"}]}
    roles = SB.panel_roles(shot)

    assert SB.shot_status(shot) == "boarded"
    assert len(roles) == len(shot["panels"])




# ── what `validate` stopped refusing, and where it went ─────────────────────


def test_a_shot_with_nothing_to_render_from_is_STORABLE():
    """The check that moved out of `validate`, and why.

    A shot with a beat and no words anywhere is a plan in progress. Refusing it
    would reject the first save of anything authored top-down — write the beats,
    then fill them in — and `shot_status` already answers `planned`, which is
    honest. The API stores it.
    """
    doc = SB.normalise({"shots": [{"beat": "they meet"}]}, "s")
    SB.validate(doc)
    assert doc["shots"][0]["status"] == "planned"


def test_it_is_still_reported_for_a_plan_somebody_called_finished():
    """`unrenderable` keeps it as advice, for the ingest path.

    A blank shot in a file handed over as a finished plan is nearly always a
    typo, and that is the last cheap moment to say so.
    """
    doc = SB.normalise({"shots": [{"beat": "they meet"}]}, "s")
    problems = SB.unrenderable(doc)
    assert len(problems) == 1 and "nothing to render from" in problems[0]


def test_a_panel_with_neither_prompt_nor_image_is_reported_not_refused():
    doc = SB.normalise({"shots": [{"panels": [{"prompt": "a"}, {}]}]}, "s")
    SB.validate(doc)
    assert any("panel 2" in problem for problem in SB.unrenderable(doc))


# ── `normalise` is sparse, which is the change that could destroy work ──────


def test_normalise_writes_only_what_the_author_named():
    """**The property that stops a revision wiping rendered work.**

    `catalog.put_shots` merges with `entry.get(field, previous.get(field))`, so
    naming a field wins. This used to fill every field with a default — `run:
    None`, `panels: []` — which was harmless in the pipeline because a
    client-side merge folded the existing shot in first, and destructive without
    one: a revision that renamed a beat arrived carrying `run: None` and unlinked
    the render underneath it.
    """
    shot = SB.normalise({"shots": [{"beat": "one"}]}, "s")["shots"][0]
    for absent in ("panels", "motion", "run", "node", "opens_on", "prompt"):
        assert absent not in shot, f"{absent} was named and the author did not name it"
    # Derived, so always present.
    assert shot["id"] == "shot-01" and shot["status"] == "planned"
    assert shot["continues"] is False


def test_a_named_field_is_still_normalised():
    shot = SB.normalise(
        {"defaults": {"panel_model": "nano-banana-pro"},
         "shots": [{"panels": [{"prompt": "a"}]}]}, "s")["shots"][0]
    assert shot["panels"][0]["model"] == "nano-banana-pro"


# ── the panel merge, which is the level below `put_shots`' ──────────────────


def test_merge_panels_carries_the_image_under_a_reworded_panel():
    """Rewriting a prompt must not orphan the board it already has."""
    previous = {"panels": [{"n": 1, "prompt": "a", "node": "node-1", "boarded": True}]}
    merged = SB.merge_panels(previous, {"panels": [{"n": 1, "prompt": "a wider shot"}]})
    assert merged[0]["node"] == "node-1"
    assert merged[0]["boarded"] is True


def test_a_reworded_panel_is_marked_stale():
    """The picture in the library no longer illustrates the words beside it.

    A warning rather than a block: the point of a board this cheap is that
    living with an out-of-date panel can be the right call.
    """
    previous = {"panels": [{"n": 1, "prompt": "a", "node": "node-1"}]}
    merged = SB.merge_panels(previous, {"panels": [{"n": 1, "prompt": "b"}]})
    assert merged[0]["stale"] is True


def test_whitespace_alone_is_not_a_rewording():
    previous = {"panels": [{"n": 1, "prompt": "a  wave", "node": "node-1"}]}
    merged = SB.merge_panels(previous, {"panels": [{"n": 1, "prompt": "a wave\n"}]})
    assert merged[0]["stale"] is False


def test_staleness_survives_a_revision_that_did_not_touch_the_words():
    previous = {"panels": [{"n": 1, "prompt": "a", "node": "node-1", "stale": True}]}
    merged = SB.merge_panels(previous, {"panels": [{"n": 1, "prompt": "a"}]})
    assert merged[0]["stale"] is True


def test_an_explicit_stale_wins_over_the_derivation():
    """`scenes board --redo` marks a panel stale to force a re-render.

    A merge that recomputed unconditionally answered `False` — the previous panel
    was not stale and the prompt had not changed — and dropped the flag on the
    write that was supposed to set it.
    """
    previous = {"panels": [{"n": 1, "prompt": "a", "node": "node-1"}]}
    merged = SB.merge_panels(previous, {"panels": [{"n": 1, "prompt": "a", "stale": True}]})
    assert merged[0]["stale"] is True


def test_a_supplied_panel_is_never_stale():
    """It has no prompt to have drifted from."""
    previous = {"panels": [{"n": 1, "node": "node-1", "stale": True}]}
    merged = SB.merge_panels(previous, {"panels": [{"n": 1, "node": "node-1"}]})
    assert merged[0]["stale"] is False


def test_a_revision_that_does_not_name_panels_leaves_them_alone():
    """`None` rather than `[]` — the caller must be able to say nothing."""
    assert SB.merge_panels({"panels": [{"n": 1}]}, {"beat": "reworded"}) is None
