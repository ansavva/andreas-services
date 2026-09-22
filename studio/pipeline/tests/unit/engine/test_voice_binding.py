"""A voice binds like a LoRA, with one difference that changes the plumbing.

A clip and a LoRA each have a field of their own, so the field a node was bound
to says what it is for and `sends_for` reads the role off the registry. A voice
does not: it lands on the SAME field as the pictures, because the id the
provider reads sits inside the element object beside that subject's images —
which is what makes the voice the character's rather than the run's.

So `gather` takes an out-parameter for the roles a field name cannot carry, and
these tests are mostly about that seam holding: the voice reaches the send row
as a voice, the pictures are still references, and the ordering that would
silently drop one is the right way round.
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


def test_a_voice_binds_beside_the_pictures_on_the_same_field(named):
    """**Beside, not instead.** The element carries both, so the field holds
    both — and the voice goes on LAST, after the reference list is assigned,
    or it would be overwritten by the pictures without a word."""
    bound = SUB.gather(ELEMENTS, args(key=("node-face",), voice_key=("node-voice",)))
    assert bound == {"elements": ["node-face", "node-voice"]}


def test_the_send_says_which_of_them_is_the_voice(named):
    """The whole reason `gather` has an out-parameter: the field cannot say."""
    roles = {}
    bound = SUB.gather(ELEMENTS, args(key=("node-face",), voice_key=("node-voice",)),
                       roles)
    sends = SUB.sends_for(ELEMENTS, bound, roles)
    assert [(send["node"], send["role"]) for send in sends] == [
        ("node-face", "reference"), ("node-voice", "voice")]


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


def test_several_voices_bind_at_once(named):
    """Two people in a scene is two elements, each with its own voice. The API
    groups them by which character each file sits under."""
    roles = {}
    bound = SUB.gather(ELEMENTS,
                       args(key=("node-face", "node-side"),
                            voice_key=("node-voice", "node-voice")), roles)
    assert bound["elements"][:2] == ["node-face", "node-side"]
    assert roles["node-voice"] == "voice"


def test_the_reference_cap_counts_subjects_rather_than_pictures(named, monkeypatch):
    """`max_refs` is 4 ELEMENTS on this model. Read as four images it would
    refuse two characters with three views each — inside what Kling takes —
    with a message about a limit that is not the one being hit."""
    monkeypatch.setattr(SUB, "describe",
                        lambda ref: {"name": "ref.png", "size": 1})
    bound = SUB.gather(ELEMENTS, args(key=tuple(f"node-{n}" for n in range(8))))
    assert len(bound["elements"]) == 8


def test_the_byte_warning_ignores_the_voice(named, monkeypatch):
    """The warning is a measurement of how much IMAGE data has ever worked. A
    sample is not an image and must not push an ordinary payload over it."""
    seen = {}
    monkeypatch.setattr(SUB, "_warn_total_bytes",
                        lambda entry, bindings: seen.update(bindings))
    SUB.gather(ELEMENTS, args(key=("node-face",), voice_key=("node-voice",)))
    assert seen == {"elements": ["node-face"]}
