"""On fal, a multi-shot timeline REPLACES the prompt — the two never go out together.

fal's OpenAPI says it on the `prompt` field of both Kling entries:

    "Text prompt for video generation. Either prompt or multi_prompt must be
     provided, but not both."

and the input schema's `required` array is `["start_image_url"]` alone, so a
payload with no prompt at all is a complete one there. studio sent both: a
prompt carrying the globals — who is in the shot, the room, the grade, the
sound, the closing `Avoid …` — and `multi_prompt` carrying the beats. That is
an invalid payload on fal, and the CLI made it the only one it would build,
because it refused to build any payload without a prompt.

So on an entry the registry marks `video.shots_replace_prompt`, the globals are
folded into the FIRST beat and `prompt` comes off the payload, before the render
a person reads under hard rule #2.

**Replicate is the other half of every test here.** Its proxy for the same model
family REQUIRES `prompt`, so `replicate-kling` keeps sending both and nothing
about it changes. The flag is registry data rather than a rule about Kling
precisely so the two providers can differ, and each assertion about fal has a
Replicate twin so they cannot drift silently.

The entries are read off the real registry rather than written out as literals:
a flag that stopped being set would otherwise leave both halves passing.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import runner as RUN
from studio_pipeline.engine import submit as SUB

#: What the prompt used to carry, and what has to survive the move.
GLOBALS = ("Two figures on a wet platform at night. Sodium light, hard shadows. "
           "Handheld documentary grade. Distant announcements. Avoid extra fingers.")
BEATS = [{"prompt": "Wide shot, static. The train pulls away.", "duration": "5"},
         {"prompt": "Close on the departure board.", "duration": "5"}]


@pytest.fixture
def fal():
    return REG.get("fal-kling-v3-i2v")


@pytest.fixture
def replicate():
    return REG.get("replicate-kling")


def args(**over):
    base = dict(input_file=None, prompt=None, prompt_file=None, extra=None,
                aspect_ratio=None, project={"id": "proj-1", "name": "p"})
    return SimpleNamespace(**{**base, **over})


def timeline(beats=None, duration="10", as_json_string=False):
    """`--extra`, the way a multi-shot run actually arrives at the CLI."""
    beats = json.loads(json.dumps(beats or BEATS))
    return json.dumps({"duration": duration,
                       "multi_prompt": json.dumps(beats) if as_json_string else beats})


# ── the flag, which every rule below hangs off ──────────────────────────────

def test_the_registry_says_which_entries_replace_the_prompt(fal, replicate):
    assert REG.field(fal, "video.shots_replace_prompt") is True
    assert REG.field(REG.get("fal-kling-o3-r2v"),
                     "video.shots_replace_prompt") is True
    assert REG.field(replicate, "video.shots_replace_prompt") is None


# ── fal: the timeline is the only text field ────────────────────────────────

def test_a_timeline_takes_the_prompt_off_the_payload(fal):
    payload = RUN.build_payload(fal, args(prompt=GLOBALS, extra=timeline()))
    assert "prompt" not in payload
    assert len(payload["multi_prompt"]) == 2


def test_the_globals_survive_in_the_first_beat(fal):
    payload = RUN.build_payload(fal, args(prompt=GLOBALS, extra=timeline()))
    first, second = payload["multi_prompt"]
    assert first["prompt"] == f"{GLOBALS}\n\n{BEATS[0]['prompt']}"
    assert first["duration"] == "5"
    # Every other beat is untouched: the globals are a preamble, not a refrain.
    assert second == BEATS[1]


def test_the_folded_payload_is_one_the_preflight_accepts(fal):
    """End to end: build it, then run the rules that guard a submit over it."""
    payload = RUN.build_payload(fal, args(prompt=GLOBALS, extra=timeline()))
    SUB.check_payload_rules(fal, payload)


def test_a_timeline_only_run_is_no_longer_refused(fal):
    """The CLI's `a prompt is required` used to block this, with a sentence
    naming three flags none of which would have produced a valid payload."""
    payload = RUN.build_payload(fal, args(extra=timeline()))
    assert "prompt" not in payload
    assert payload["multi_prompt"][0]["prompt"] == BEATS[0]["prompt"]


def test_a_json_string_timeline_folds_and_keeps_its_spelling(fal):
    """A beat list written Replicate's way is folded, not re-spelled — what the
    author wrote is what the render shows."""
    payload = RUN.build_payload(
        fal, args(prompt=GLOBALS, extra=timeline(as_json_string=True)))
    assert "prompt" not in payload
    assert isinstance(payload["multi_prompt"], str)
    assert json.loads(payload["multi_prompt"])[0]["prompt"].startswith(GLOBALS)


def test_an_empty_prompt_beside_a_timeline_is_dropped_too(fal):
    """Two text fields to a provider that documents one, even when one is blank."""
    payload = RUN.build_payload(fal, args(prompt="   ", extra=timeline()))
    assert "prompt" not in payload


def test_without_a_timeline_fal_is_unchanged(fal):
    payload = RUN.build_payload(fal, args(prompt=GLOBALS))
    assert payload["prompt"] == GLOBALS
    assert "multi_prompt" not in payload


def test_a_prompt_is_still_required_when_there_is_no_timeline(fal, capsys):
    with pytest.raises(SystemExit):
        RUN.build_payload(fal, args())
    assert "a prompt is required" in capsys.readouterr().err


def test_both_fields_together_are_refused_with_the_schema_s_own_words(fal):
    """The backstop for a payload this CLI did not build — the app's, or a
    draft written before the fold existed."""
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(fal, {"duration": "10", "prompt": GLOBALS,
                                      "multi_prompt": BEATS})
    said = str(refusal.value)
    assert "Either prompt or multi_prompt must be provided, but not both" in said
    assert "fal-kling-v3-i2v" in said


# ── the ceiling follows the text: 512 a beat on fal ──────────────────────────
#
# fal's server caps every `multi_prompt[].prompt` at 512 characters and its
# OpenAPI document does not say so; a live submit on 2026-09-23 came back 422,
# "Prompt must not exceed 512 characters." The 2500 is the single `prompt`
# field's alone. `video.shot_max_chars` carries the 512 — measured on v3,
# assumed on O3 — and Replicate declares none.

@pytest.mark.parametrize("key", ["fal-kling-v3-i2v", "fal-kling-o3-r2v"])
def test_the_registry_caps_each_beat_at_512_on_fal(key):
    assert REG.field(REG.get(key), "video.shot_max_chars") == 512
    assert SUB.shot_cap(REG.get(key)) == 512


def test_replicate_has_no_per_beat_cap(replicate):
    assert REG.field(replicate, "video.shot_max_chars") is None
    assert SUB.shot_cap(replicate) is None


def test_folding_over_the_cap_is_refused_before_a_draft_and_says_why(fal, capsys):
    """Beat one is capped like every beat, and it is where the globals land,
    so that is the beat a fold can blow. Refused while the payload is built —
    before the render, before a draft is written."""
    with pytest.raises(SystemExit):
        RUN.build_payload(
            fal, args(prompt="g" * 400,
                      extra=timeline([{"prompt": "b" * 200, "duration": "5"},
                                      {"prompt": "second", "duration": "5"}])))
    said = capsys.readouterr().err
    assert "caps each beat at 512 characters" in said
    assert "shot 1" in said and "602" in said
    assert "400 of --prompt + 200 of the beat" in said
    assert "one identity sentence" in said


def test_a_fold_that_fits_is_left_alone(fal):
    payload = RUN.build_payload(
        fal, args(prompt="g" * 300,
                  extra=timeline([{"prompt": "b" * 210, "duration": "5"},
                                  {"prompt": "second", "duration": "5"}])))
    assert len(payload["multi_prompt"][0]["prompt"]) == 512
    SUB.check_payload_rules(fal, payload)


def test_the_fold_refuses_without_touching_the_payload(fal):
    payload = {"prompt": "g" * 600, "multi_prompt": [{"prompt": "b", "duration": "5"}]}
    with pytest.raises(SUB.SubmitError):
        SUB.fold_timeline_globals(fal, payload)
    assert payload["multi_prompt"][0]["prompt"] == "b"


@pytest.mark.parametrize("key", ["fal-kling-v3-i2v", "fal-kling-o3-r2v"])
def test_a_513_character_beat_is_refused_on_fal(key):
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(
            REG.get(key), {"duration": "10",
                           "multi_prompt": [{"prompt": "a" * 513, "duration": "5"},
                                            {"prompt": "second", "duration": "5"}]})
    said = str(refusal.value)
    assert f"{key} caps each beat at 512 characters and shot 1 carries 513" in said


def test_a_513_character_beat_passes_on_replicate(replicate):
    SUB.check_payload_rules(
        replicate, {"duration": 10, "prompt": GLOBALS,
                    "multi_prompt": json.dumps([{"prompt": "a" * 513, "duration": 5},
                                                {"prompt": "second", "duration": 5}])})


def test_a_later_beat_over_the_cap_does_not_blame_the_fold(fal):
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(
            fal, {"duration": "10",
                  "multi_prompt": [{"prompt": "first", "duration": "5"},
                                   {"prompt": "b" * 2600, "duration": "5"}]})
    said = str(refusal.value)
    assert "shot 2" in said and "folded" not in said


# ── an @Element tag costs more than its nine characters ─────────────────────
#
# Kling, behind fal, refused three beats fal had accepted — "multiPrompt[0].
# prompt: size must be between 0 and 512" on 492 characters with five tags —
# and rendered 464 with four (2026-09-23). Inferred ~+6 a tag; budgeted at 8
# (`video.shot_tag_chars`), so a beat counts `len + 8 × tags` against the 512.

def tagged(length, tags):
    """A beat of exactly `length` characters carrying `tags` @Element tags."""
    text = "".join(f"@Element{n % 4 + 1} " for n in range(tags))
    return text + "x" * (length - len(text))


@pytest.mark.parametrize("key", ["fal-kling-v3-i2v", "fal-kling-o3-r2v"])
def test_the_registry_weights_a_tag_at_8_on_fal(key):
    assert REG.field(REG.get(key), "video.shot_tag_chars") == 8


def test_the_tags_are_counted_as_kling_counts_them(fal, replicate):
    beat = tagged(480, 5)
    assert SUB.beat_length(fal, beat) == (520, 5)
    assert SUB.beat_length(replicate, beat) == (480, 5)


@pytest.mark.parametrize("key", ["fal-kling-v3-i2v", "fal-kling-o3-r2v"])
def test_480_characters_with_five_tags_is_refused_with_the_arithmetic(key):
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(
            REG.get(key), {"duration": "10",
                           "multi_prompt": [{"prompt": "first", "duration": "5"},
                                            {"prompt": tagged(480, 5), "duration": "5"}]})
    said = str(refusal.value)
    assert ("shot 2 is 480 characters and carries 5 @Element tags, which "
            "Kling counts as about 520 of its 512 (480 + 5 × 8)") in said
    assert "Measured 2026-09-23" in said
    assert "Cut words or tags" in said and "the seated man" in said
    assert "globals" not in said


def test_the_same_beat_with_one_tag_passes(fal):
    SUB.check_payload_rules(
        fal, {"duration": "10",
              "multi_prompt": [{"prompt": "first", "duration": "5"},
                               {"prompt": tagged(480, 1), "duration": "5"}]})


def test_the_measured_render_passes_and_the_measured_refusal_does_not(fal):
    """The four live data points, as lengths and tag counts."""
    rendered = [tagged(359, 4), tagged(464, 4), tagged(462, 4)]
    SUB.check_payload_rules(
        fal, {"duration": "15", "multi_prompt": [
            {"prompt": b, "duration": "5"} for b in rendered]})
    refused = [tagged(492, 5), tagged(484, 6), tagged(496, 5)]
    for index, beat in enumerate(refused, start=1):
        payload = {"duration": "15", "multi_prompt": [
            {"prompt": "short", "duration": "5"} for _ in range(3)]}
        payload["multi_prompt"][index - 1]["prompt"] = beat
        with pytest.raises(SUB.SubmitError):
            SUB.check_payload_rules(fal, payload)


def test_a_fold_the_tags_push_over_is_refused_with_the_arithmetic(fal, capsys):
    with pytest.raises(SystemExit):
        RUN.build_payload(
            fal, args(prompt="g" * 200,
                      extra=timeline([{"prompt": tagged(290, 5), "duration": "5"},
                                      {"prompt": "second", "duration": "5"}])))
    said = capsys.readouterr().err
    assert "makes it 492 (200 of --prompt + 290 of the beat)" in said
    assert "5 @Element tags make Kling count it as about 532 (492 + 5 × 8" in said
    assert "the seated man" in said


def test_a_tag_is_not_weighted_on_replicate(replicate):
    SUB.check_payload_rules(
        replicate, {"duration": 10, "prompt": GLOBALS,
                    "multi_prompt": json.dumps([{"prompt": tagged(510, 5), "duration": 5},
                                                {"prompt": "second", "duration": 5}])})


# ── Replicate, pinned exactly as it is ──────────────────────────────────────

def test_replicate_keeps_its_prompt_beside_the_timeline(replicate):
    payload = RUN.build_payload(
        replicate, args(prompt=GLOBALS,
                        extra=json.dumps({"duration": 10,
                                          "multi_prompt": json.dumps(BEATS)})))
    assert payload["prompt"] == GLOBALS
    assert json.loads(payload["multi_prompt"]) == BEATS


def test_replicate_still_demands_a_prompt_even_with_a_timeline(replicate, capsys):
    """`prompt` is required by its live schema, so a timeline does not excuse
    one — and this refusal is what says so before the provider does."""
    with pytest.raises(SystemExit):
        RUN.build_payload(replicate,
                          args(extra=json.dumps({"duration": 10,
                                                 "multi_prompt": json.dumps(BEATS)})))
    assert "a prompt is required" in capsys.readouterr().err


def test_both_fields_together_are_fine_on_replicate(replicate):
    SUB.check_payload_rules(replicate, {"duration": 10, "prompt": GLOBALS,
                                        "multi_prompt": json.dumps(BEATS)})


def test_a_long_beat_on_replicate_is_not_measured_against_the_prompt_cap(replicate):
    """There the beats go out BESIDE a prompt that has its own 2500."""
    SUB.check_payload_rules(
        replicate, {"duration": 10, "prompt": GLOBALS,
                    "multi_prompt": json.dumps([{"prompt": "b" * 2600, "duration": 5},
                                                {"prompt": "second", "duration": 5}])})


def test_a_timeline_that_is_not_a_list_of_beats_is_refused(fal):
    """Checked before the globals are taken off the payload, so a malformed
    timeline costs a refusal and never a quietly dropped prompt."""
    payload = {"prompt": GLOBALS, "multi_prompt": {"prompt": "not a list"}}
    with pytest.raises(SUB.SubmitError):
        SUB.fold_timeline_globals(fal, payload)
    assert payload["prompt"] == GLOBALS
