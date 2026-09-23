"""A multi-shot timeline adds up, whichever way its provider spells a second.

`duration` is an INTEGER on the Replicate Kling entry and a STRING enum
("3".."15") on the fal ones, which is why the two are registered separately —
the providers really do differ. The preflight that stops an E006 before it is
billed compared the sum of the shot durations against that field with `!=`, so
on a fal entry `15 != "15"` was true of a timeline that added up perfectly and
every multi-shot run was refused. Passing an int instead failed the live schema,
which demands the string: the catch-22 made multi-shot impossible there.

So these tests are about the comparison being numeric on both sides, and about
a `duration` that is no kind of number being refused with a sentence rather than
a traceback out of a preflight.
"""

import json

import pytest

from studio_pipeline.engine import submit as SUB

#: Kling on fal, in miniature: `duration` is the string the schema demands.
FAL = {"key": "fal-kling-v3-i2v", "model": "fal/kling", "kind": "video",
       "video": {"max_cuts": 6}}
#: The same family on Replicate, where the field is an int and always was.
REPLICATE = {**FAL, "key": "replicate-kling", "model": "kwaivgi/kling-v3-omni-video"}


def shots(*seconds):
    return [{"prompt": f"beat {n}", "duration": s} for n, s in enumerate(seconds, 1)]


def test_a_string_duration_matching_int_shots_passes():
    """The bug, stated the short way: this used to raise E006."""
    SUB.check_payload_rules(FAL, {"duration": "15", "multi_prompt": shots(5, 5, 5)})


def test_string_shots_against_a_string_duration_pass_too():
    """fal's own documents spell the shot durations as strings as well."""
    SUB.check_payload_rules(FAL, {"duration": "9", "multi_prompt": shots("3", "3", "3")})


def test_an_int_duration_still_passes_on_the_replicate_entry():
    SUB.check_payload_rules(REPLICATE, {"duration": 10, "multi_prompt": shots(6, 4)})


def test_a_multi_prompt_serialised_as_json_is_read_the_same_way():
    """Replicate takes `multi_prompt` as a JSON string; fal takes a real array."""
    SUB.check_payload_rules(
        REPLICATE, {"duration": 8, "multi_prompt": json.dumps(shots(4, 4))})


@pytest.mark.parametrize("duration, beats", [
    ("15", (5, 5)),          # the string case that must still refuse
    (15, (5, 5)),            # and the int one it always caught
    ("10", ("3", "3", "3")),
])
def test_a_timeline_that_does_not_add_up_is_still_refused(duration, beats):
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(FAL, {"duration": duration, "multi_prompt": shots(*beats)})
    # The marker and the shape of the sentence are referenced by the skills.
    assert "this is E006" in str(refusal.value)


@pytest.mark.parametrize("duration", ["fifteen", "", None, {"seconds": 5}])
def test_a_duration_that_is_no_number_is_refused_not_crashed(duration):
    """A bad value is a refusal with words, never a `ValueError` out of a preflight.

    `None` is the exception and deliberately so: the field being absent means
    the model does not take one, and there is then nothing to sum against.
    """
    payload = {"duration": duration, "multi_prompt": shots(5, 5, 5)}
    if duration is None:
        SUB.check_payload_rules(FAL, payload)
        return
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(FAL, payload)
    assert "number of seconds" in str(refusal.value)


def test_a_shot_duration_that_is_no_number_is_refused_too():
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(
            FAL, {"duration": "15", "multi_prompt": shots(5, "five", 5)})
    assert "number of seconds" in str(refusal.value)


def test_the_cut_cap_is_still_enforced_after_the_sum_agrees():
    with pytest.raises(SUB.SubmitError) as refusal:
        SUB.check_payload_rules(
            FAL, {"duration": "7", "multi_prompt": shots(1, 1, 1, 1, 1, 1, 1)})
    assert "at most 6 shots" in str(refusal.value)
