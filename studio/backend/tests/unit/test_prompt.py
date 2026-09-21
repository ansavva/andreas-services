"""Prompt authoring: the rules, and the one route that runs them.

**These are new, and that is the finding.** Six hundred and ninety lines of
prompting judgement lived in `pipeline/domain/prompt.py` with no test file of its
own — what coverage it had came from the CLI dispatch test invoking every leaf
command once and checking the exit code. So the rules below were, as far as the
suite was concerned, unasserted: nothing said that a stacked camera move warns,
that a duration outside the model's range is refused, or that a negative prompt
goes in the parameter rather than in the text on the engines that have one.

The split under test is errors against warnings, and it is the whole design:

  * an **error** means the payload cannot be built — an unsupported aspect
    ratio, a duration the model will not take, nothing to render at all;
  * a **warning** means it will build and probably render worse — a vague
    adjective, a camera verb in the action line, a scene described twice when a
    start frame already fixes it.

A caller decides what to do with warnings. `studio prompt --strict` exits
non-zero; an editor draws them beside the field they came from.
"""

import json

import pytest

from studio_core.services import prompt as P


def base(**over):
    obj = {"subject": "a woman in a linen dress",
           "action": "turns to face the sea",
           "technical": {"aspect_ratio": "16:9", "duration": 5}}
    obj.update(over)
    return obj


def warnings_for(obj, engine="seedance"):
    return P.validate(obj, engine)[0]


def errors_for(obj, engine="seedance"):
    return P.validate(obj, engine)[1]


# ── the engine table comes from the registry ────────────────────────────────


def test_every_video_model_in_the_registry_is_an_engine():
    """The table is built from the registry, not restated.

    Enums and ranges used to be hardcoded — a third copy of facts the schema
    already publishes, and one that could drift silently from what the model
    accepts.
    """
    from studio_core.services import registry

    for key in registry.videos():
        assert key in P.engines()


def test_an_alias_reaches_the_same_engine():
    engines = P.engines()
    assert engines["kling-replicate"]["key"] == engines["kling"]["key"]


# ── errors: the payload cannot be built ─────────────────────────────────────


def test_nothing_to_render_is_an_error():
    assert any("nothing to render" in e for e in errors_for({}))


def test_a_duration_outside_the_models_range_is_refused():
    problems = errors_for(base(technical={"duration": 999}))
    assert any("duration" in e for e in problems)


def test_an_unsupported_aspect_ratio_is_refused_naming_the_supported_ones():
    problems = errors_for(base(technical={"aspect_ratio": "3:1"}))
    assert any("aspect_ratio" in e and "16:9" in e for e in problems)


def test_a_well_formed_object_has_no_errors():
    assert errors_for(base()) == []


# ── warnings: it will build, and render worse ───────────────────────────────


def test_a_stacked_camera_move_warns():
    """One shot type and one movement. These models degrade on stacked moves."""
    found = warnings_for(base(camera={"movement": "pan and then zoom"}))
    assert any("stacks multiple moves" in w for w in found)


def test_one_camera_move_does_not():
    assert not any("stacks multiple moves" in w
                   for w in warnings_for(base(camera={"movement": "slow push-in"})))


def test_a_substring_move_is_not_counted_twice():
    """"track" inside "tracking" was two moves once, and the warning was wrong."""
    assert not any("stacks multiple moves" in w
                   for w in warnings_for(base(camera={"movement": "tracking shot"})))


def test_bare_fast_in_the_camera_block_warns():
    found = warnings_for(base(camera={"movement": "fast"}))
    assert any("bare 'fast'" in w for w in found)


def test_a_camera_verb_in_the_action_warns():
    """The action block is subject motion; camera direction belongs in `camera`."""
    found = warnings_for(base(action="a slow dolly toward the water"))
    assert any("camera-move words" in w for w in found)


def leaks(text, field="action"):
    """Did the camera-move scan fire on this line?"""
    return any("camera-move words" in w for w in warnings_for(base(**{field: text})))


# ── the verb forms, chosen one at a time ────────────────────────────────────
#
# `\bzoom\b` does not match "zooms", so the scan missed the verb form — which is
# the more natural way to write the line, making the miss the common case rather
# than the edge one. It was pinned as a known gap through the move of these rules
# out of the pipeline, on the grounds that a behaviour change smuggled into a
# port is the kind nobody reviews.
#
# Widening is not uniformly safe, so the forms are split by whether the word has
# an innocent sense in a line about a subject. Each test below says which sense
# it means to catch and which it means to leave alone.


def test_a_camera_verb_in_its_inflected_form_warns():
    """`zoom`, `dolly` and `orbit` describe a lens, not a person.

    Nobody writing about a subject means anything else by them, so the inflected
    form is a leak wherever it appears.
    """
    assert leaks("she zooms toward the water")
    assert leaks("she dollies toward the water")
    assert leaks("the pair orbits the fire")


def test_an_ambiguous_verb_alone_is_left_alone():
    """`pans` is cookware, `tracks` is a railway, `cranes` is a bird, `drones` is
    a sound, and `tilts` is a head turning — all ordinary subject prose.

    A warning is cheap but not free: one that fires on correct writing teaches
    people to stop reading warnings, and `studio prompt --strict` turns it into a
    non-zero exit.
    """
    assert not leaks("she tilts her head toward him")
    assert not leaks("he sets the pans down on the stove")
    assert not leaks("she runs along the tracks")
    assert not leaks("cranes wade in the shallows")
    assert not leaks("the machine drones in the next room")
    assert not leaks("he pulls out a letter")


def test_the_same_verb_warns_when_the_camera_is_doing_it():
    """"the camera pans across the bay" is the phrasing people actually write,
    and naming the camera removes the ambiguity entirely."""
    assert leaks("the camera pans across the bay")
    assert leaks("the camera tracks her along the pier")
    assert leaks("the camera pulls out to a wide")


def test_an_adverb_between_the_camera_and_the_verb_does_not_hide_it():
    assert leaks("the camera slowly tilts down")


def test_the_warning_quotes_the_form_as_written():
    """Not the dictionary form — the author has to find it in their own text."""
    found = warnings_for(base(action="she zooms toward the water"))
    assert any("'zooms'" in w for w in found)


def test_the_subject_block_is_scanned_too():
    assert leaks("a woman the camera pans past", field="subject")


def test_a_vague_adjective_warns():
    found = warnings_for(base(style="a beautiful cinematic mood"))
    assert any("vague adjective" in w for w in found)


def test_the_audio_and_negative_fields_are_exempt_from_the_adjective_scan():
    """A negative prompt is a list of things to avoid — vagueness is the point."""
    assert not any("vague adjective" in w
                   for w in warnings_for(base(negative="beautiful, dramatic")))


def test_describing_what_the_start_frame_already_shows_warns():
    """Describing it twice makes the model fight the image and drift."""
    found = warnings_for(base(start_image=True, scene="a rocky coastline at dusk"))
    assert any("start" in w.lower() for w in found)


# ── the phrasebook, injected rather than imported ───────────────────────────


def test_a_phrasebook_term_in_the_text_is_reported():
    found = P.validate(
        base(action="she does a backflip"), "seedance",
        lambda model: [{"avoid": "backflip", "use": "a tumbling pass"}],
    )[0]
    assert any("backflip" in w and "tumbling pass" in w for w in found)


def test_no_lookup_means_no_phrasebook_rather_than_a_failure():
    """A caller with no library in hand still gets an assembled prompt."""
    assert P.validate(base(), "seedance")[1] == []


def test_a_phrasebook_that_cannot_be_read_warns_and_does_not_block():
    """A refusal must never be reported as "no substitutions apply"."""
    def broken(_model):
        raise RuntimeError("dynamodb is having a day")

    found = P.validate(base(), "seedance", broken)[0]
    assert any("phrasebook" in w for w in found)


# ── assembly ────────────────────────────────────────────────────────────────


def test_assemble_answers_with_the_prompt_and_the_provider_input():
    answer = P.assemble(base(), "seedance")
    assert answer["errors"] == []
    assert answer["prompt"]
    assert answer["engine"] == "seedance"


def test_the_technical_block_is_routed_off_the_prompt_text():
    """`duration` is a parameter, not words. Leaving it in the text wastes tokens
    and asks the model to honour something the API already decides."""
    answer = P.assemble(base(technical={"duration": 5, "aspect_ratio": "16:9"}),
                        "seedance")
    assert "duration" not in answer["prompt"]
    assert answer["input"]["duration"] == 5


def test_emit_narrows_what_comes_back():
    assert set(P.assemble(base(), "seedance", emit="prompt")) >= {"prompt"}
    assert "input" not in P.assemble(base(), "seedance", emit="prompt")
    assert "prompt" not in P.assemble(base(), "seedance", emit="input")


def test_errors_come_back_with_no_prompt_rather_than_raising():
    """An editor asking "what is wrong so far" gets an answer it can draw."""
    answer = P.assemble({}, "seedance")
    assert answer["prompt"] is None
    assert answer["errors"]


def test_overrides_are_applied_before_validation():
    answer = P.assemble({}, "seedance", overrides={"subject": "a runner",
                                                   "action": "crosses the line"})
    assert answer["errors"] == []


# ── the route ───────────────────────────────────────────────────────────────


def test_the_route_assembles(api):
    body = api.post("/api/prompt", json={
        "object": base(), "engine": "seedance",
    }).get_json()
    assert body["prompt"] and body["errors"] == []


def test_the_route_writes_nothing(api):
    """Safe to call per keystroke, which is the point of it being reachable."""
    before = api.get("/api/runs").get_json()
    api.post("/api/prompt", json={"object": base()})
    assert api.get("/api/runs").get_json() == before


def test_an_unknown_engine_is_a_400(api):
    resp = api.post("/api/prompt", json={"object": base(), "engine": "no-such"})
    assert resp.status_code == 400


@pytest.mark.parametrize("body", [
    {"object": "not an object"},
    {"object": base(), "emit": "sideways"},
    {"object": base(), "overrides": []},
])
def test_a_body_this_cannot_read_is_a_400(api, body):
    """The one thing that IS a bad request. A half-written prompt is not."""
    assert api.post("/api/prompt", json=body).status_code == 400


def test_a_half_written_prompt_is_200_with_errors(api):
    """Not a 400: the caller wants the list, not a refusal."""
    resp = api.post("/api/prompt", json={"object": {}})
    assert resp.status_code == 200
    assert resp.get_json()["errors"]


# ── the wire text is per engine ─────────────────────────────────────────────
#
# Every engine's `prompt` is one text field. Seedance gets the object as JSON,
# which ByteDance's own guidance endorses; Kling gets Kuaishou's formula as
# prose, because nothing Kuaishou publishes mentions JSON and the braces were
# reaching a 2,500-character field as literal characters. The object stays the
# authored record either way — only `serialize` differs.


def kling_base(**over):
    return base(
        scene="rocky coastline at dusk",
        camera={"shot": "medium", "movement": "slow push-in", "lens_mm": 35},
        lighting="low golden-hour sun",
        style="cinematic film tone",
        audio="soft wind, distant gulls",
        negative="jitter, extra fingers",
        **over,
    )


def test_seedance_receives_the_object_as_json():
    prompt = P.assemble(base(), "seedance")["prompt"]
    assert json.loads(prompt)["subject"] == "a woman in a linen dress"


def test_kling_receives_the_formula_as_prose_not_json():
    """Subject + movement + scene + (camera + lighting + atmosphere), in that
    order, as sentences. No braces, no quoted key names."""
    prompt = P.assemble(kling_base(), "kling")["prompt"]
    assert "{" not in prompt and '"subject"' not in prompt
    assert prompt.startswith("A woman in a linen dress turns to face the sea. ")
    order = ["Rocky coastline", "Medium shot, slow push-in, 35mm lens",
             "Low golden-hour sun", "Cinematic film tone", "Soft wind"]
    positions = [prompt.index(s) for s in order]
    assert positions == sorted(positions)


def test_the_kling_negative_becomes_an_avoid_sentence():
    """Kling has no negative_prompt field, so the only place the negative can
    go is the end of the text — after everything it must not colour."""
    prompt = P.assemble(kling_base(), "kling")["prompt"]
    assert prompt.endswith("Avoid jitter, extra fingers.")


def test_the_kling_alias_serializes_the_same_way():
    assert (P.assemble(kling_base(), "kling-replicate")["prompt"]
            == P.assemble(kling_base(), "kling")["prompt"])


def test_a_kling_timeline_is_shot_lines_with_durations():
    """The 3.0 Omni guide writes multi-shot prompts as `Shot N (Ns): …`. The
    durations are the ones `multi_prompt` carries, from the same arithmetic."""
    obj = {
        "subject": "a detective in a long coat",
        "style": "neo-noir grade",
        "shots": [
            {"t": "0s", "shot": "wide", "camera": "static", "description": "stands in the rain"},
            {"t": "5s", "shot": "close", "camera": "hold", "description": "he exhales"},
        ],
        "technical": {"duration": 8},
    }
    answer = P.assemble(obj, "kling")
    lines = answer["prompt"].splitlines()
    assert lines[0] == "A detective in a long coat. Neo-noir grade."
    assert "Shot 1 (5s): Wide shot, static. Stands in the rain." in lines
    assert "Shot 2 (3s): Close shot, hold. He exhales." in lines
    assert [s["duration"] for s in json.loads(answer["input"]["multi_prompt"])] == [5, 3]


def test_kling_dialogue_carries_a_speaker_label_in_quotes():
    obj = base(dialogue=[{"speaker": "Guide", "line": "This way."}, "Wait."])
    prompt = P.assemble(obj, "kling")["prompt"]
    assert 'Guide: "This way."' in prompt
    assert '"Wait."' in prompt


def test_kling_delivery_sits_on_the_speaker_label():
    """Kuaishou: name, line and delivery close together."""
    obj = base(dialogue=[{"speaker": "Mom", "line": "Shoes. Now.", "delivery": "fast, urgent"}])
    assert 'Mom (fast, urgent): "Shoes. Now."' in P.assemble(obj, "kling")["prompt"]


def test_an_acronym_opening_the_action_keeps_its_case():
    prompt = P.assemble(base(action="DJs the set"), "kling")["prompt"]
    assert prompt.startswith("A woman in a linen dress DJs the set.")


def test_the_kling_prose_is_what_the_length_cap_measures():
    """The cap is a property of the wire text. Prose is shorter than the JSON
    it replaced, so a prompt that fits as prose is not refused for a JSON
    length nothing sends."""
    long = kling_base(subject="a woman in a linen dress " * 60)
    assert P.assemble(long, "kling")["errors"] == []
    assert len(P.assemble(long, "kling")["prompt"]) < 2500


def test_prompt_format_defaults_to_json_for_an_engine_that_says_nothing():
    assert P.engines()["seedance"]["prompt_format"] == "json"
    assert P.engines()["kling"]["prompt_format"] == "kling"
