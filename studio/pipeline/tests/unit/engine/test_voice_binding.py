"""A voice binds like a LoRA, with one difference that changes the plumbing —
and, on fal, only beside a video.

A clip and a LoRA each have a field of their own, so the field a node was bound
to says what it is for and `sends_for` reads the role off the registry. A voice
does not: it lands on the SAME field as the pictures, because the id the
provider reads sits inside the element object. So `gather` takes an
out-parameter for the roles a field name cannot carry.

**fal binds a voice only to an element carrying a `video_url`.** Its page for
Kling 3.0 says "Voice binding is only supported for video elements, not image
elements", and "a request can only have one element with a video" — so one
voice at most. This command binds only images into an element, so every
`--voice-key` is refused at gather today, before a draft is written that the
API's preflight would refuse at submit. Kling invents the voice instead when
`generate_audio` is on.
"""

from types import SimpleNamespace

import pytest

from studio_pipeline.engine import submit as SUB

#: Kling on fal, in miniature: elements are the reference field, and a voice
#: binds to the same one.
ELEMENTS = {
    "key": "an-element-model", "model": "fal/x", "kind": "video", "skill": "s",
    "images": {"refs": "elements", "max_refs": 4, "start": "start_image_url",
               "end": "end_image_url", "start_excludes_refs": False,
               "accepts_ext": [".jpg", ".png"]},
    "elements": {"field": "elements", "frontal": "frontal_image_url",
                 "refs": "reference_image_urls", "clip": "video_url",
                 "voice": "voice_id", "max": 4, "max_images_each": 4},
    "audio": {"voice": "elements", "create": "fal/x/create-voice",
              "accepts_ext": [".mp3", ".wav"], "min_seconds": 5, "max_seconds": 30},
    "prompt": {"max_chars": 2500},
}
#: Kling on Replicate: same model family, no elements and no voice input.
FLAT = {**ELEMENTS, "key": "a-flat-model", "model": "vendor/y",
        "images": {**ELEMENTS["images"], "refs": "reference_images"},
        "elements": None, "audio": None}


def args(**over):
    base = dict(input_file=None, prompt=None, prompt_file=None, extra=None,
                aspect_ratio=None, key=(), character=(), ref_run=(), slots=None,
                pick=None, pick_tag=None, image_run=None, input_=None,
                start_run=None, start_key=None, end_run=None, end_key=None,
                clip_run=None, clip_key=None, lora_key=(), lora_high_key=(),
                lora_low_key=(), voice_key=(),
                project={"id": "proj-1", "name": "p"})
    return SimpleNamespace(**{**base, **over})


@pytest.fixture
def named(monkeypatch):
    names = {"node-still": "frame.png", "node-face": "face.png",
             "node-side": "side.png", "node-voice": "take.mp3",
             "node-notaudio": "take.txt"}
    monkeypatch.setattr(SUB, "describe",
                        lambda ref: {"name": names.get(ref, "x.bin"), "size": 1})
    return names


def test_a_voice_on_an_image_element_is_refused_with_fals_own_words(named):
    """**The rule fal states and nothing else enforced.** The pictures make an
    image element; a voice beside them is what fal refuses."""
    roles = {}
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(ELEMENTS, args(key=("node-face",), voice_key=("node-voice",)),
                   roles)
    message = str(caught.value)
    assert ("Voice binding is only supported for video elements, "
            "not image elements.") in message
    assert "Kling invents" in message
    assert roles == {}, "a refused voice must not reach the send rows"


def test_a_voice_alone_is_refused_too(named):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(ELEMENTS, args(voice_key=("node-voice",)))
    assert "only supported for video elements" in str(caught.value)


def test_the_send_says_which_of_them_is_the_voice():
    """The seam `gather`'s out-parameter feeds: a per-node role beats the
    field's, so a voice and a clip on the elements field are told apart from
    the pictures beside them."""
    bound = {"elements": ["node-face", "node-clip", "node-voice"]}
    sends = SUB.sends_for(ELEMENTS, bound,
                          {"node-clip": "clip", "node-voice": "voice"})
    assert [(send["node"], send["role"]) for send in sends] == [
        ("node-face", "reference"), ("node-clip", "clip"), ("node-voice", "voice")]


def test_a_model_with_no_voice_input_says_so_and_names_the_ones_that_have_it(named):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(FLAT, args(key=("node-face",), voice_key=("node-voice",)))
    assert "takes no voice" in str(caught.value)
    assert "fal-kling-v3-i2v" in str(caught.value)


def test_a_sample_in_a_format_the_model_will_not_read_is_refused_here(named):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(ELEMENTS, args(key=("node-face",), voice_key=("node-notaudio",)))
    assert "clones a voice from" in str(caught.value)
    assert "take.txt" in str(caught.value)
    # The length the model asks for, said at the moment somebody binds one.
    assert "5–30 seconds" in str(caught.value)


def test_two_voices_are_refused(named):
    """One element per request can carry a video, and only that one can carry
    a voice — so two voices is never a request fal will take."""
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(ELEMENTS, args(key=("node-face", "node-side"),
                                  voice_key=("node-voice", "node-voice")))
    assert "one voice at most" in str(caught.value)


def test_the_reference_cap_counts_subjects_rather_than_pictures(named, monkeypatch):
    """`max_refs` is 4 ELEMENTS on this model. Read as four images it would
    refuse two characters with three views each — inside what Kling takes —
    with a message about a limit that is not the one being hit."""
    monkeypatch.setattr(SUB, "describe",
                        lambda ref: {"name": "ref.png", "size": 1})
    bound = SUB.gather(ELEMENTS, args(key=tuple(f"node-{n}" for n in range(8))))
    assert len(bound["elements"]) == 8


# ── the floor: an image element is two pictures, not one ────────────────────
#
# fal's server refused a lone frontal on 2026-09-23 (a 422, no charge) with
# "Either frontal_image_url and reference_image_urls or video_url must be
# provided." Its OpenAPI document does not say so; `elements.min_images_each`
# does. This command binds only images into an element, so a `--character` or
# `--location` yielding one picture is an element fal would refuse — stopped
# here, before a draft is written. The API's `_check_elements` is the gate.

FLOORED = {**ELEMENTS, "elements": {**ELEMENTS["elements"], "min_images_each": 2}}


@pytest.fixture
def subjects(monkeypatch):
    views = {"char-a": ["node-a1", "node-a2"], "char-one": ["node-o1"],
             "loc-room": ["node-r1"], "loc-two": ["node-r1", "node-r2"]}
    monkeypatch.setattr(SUB.REFS, "character_ref_nodes",
                        lambda name, *a, **k: list(views[name]))
    monkeypatch.setattr(SUB.REFS, "location_ref_nodes",
                        lambda name, *a, **k: list(views[name]))
    monkeypatch.setattr(SUB, "describe", lambda ref: {"name": "ref.png", "size": 1})


def test_the_registry_puts_a_floor_of_two_under_both_fal_entries():
    from studio_pipeline.engine import registry as REG
    for key in ("fal-kling-v3-i2v", "fal-kling-o3-r2v"):
        assert REG.elements(REG.get(key))["min_images_each"] == 2


@pytest.mark.parametrize("flag,name", [("character", "char-one"),
                                       ("location", "loc-room")])
def test_a_subject_with_one_picture_is_refused_in_fals_own_words(subjects, flag, name):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(FLOORED, args(**{flag: (name,)}))
    message = str(caught.value)
    assert ("Either frontal_image_url and reference_image_urls or video_url "
            "must be provided.") in message
    assert f"--{flag} {name} binds 1 image(s)" in message
    assert "location's folder" in message


def test_two_pictures_of_each_subject_pass(subjects):
    bound = SUB.gather(FLOORED, args(character=("char-a",), location=("loc-two",)))
    assert bound["elements"] == ["node-a1", "node-a2", "node-r1", "node-r2"]


def test_a_model_without_a_floor_takes_one_picture(subjects):
    bound = SUB.gather(ELEMENTS, args(character=("char-one",)))
    assert bound["elements"] == ["node-o1"]
