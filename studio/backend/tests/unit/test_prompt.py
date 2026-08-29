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


def test_the_scan_matches_whole_words_only_and_so_misses_plurals():
    """**A known gap, pinned rather than fixed.** `\bzoom\b` does not match
    "zooms", and "the camera pans across the bay" is a very ordinary thing to
    write in an action line.

    Left alone on this pass because the move was meant to relocate the rules, not
    change what they decide — a behaviour change smuggled into a port is the kind
    nobody reviews. Widening to `zooms?|zooming` would also start catching
    "tracks" and "pans" in their innocent senses, and this is a warning, so a
    false positive is cheap but not free. Worth doing deliberately, with the
    plural forms chosen one at a time.
    """
    assert not any("camera-move words" in w
                   for w in warnings_for(base(action="she zooms toward the water")))


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
