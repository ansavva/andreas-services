"""A LoRA binds like a clip: its own flags, its own extensions, its own role.

The model that loads weights beside its own (`loras` in the registry) takes a
`.safetensors` node per denoising stage; nothing about it is an image, so it
is kept out of the image list, the budget and the byte warning.
"""

from types import SimpleNamespace

import pytest

from studio_pipeline.engine import submit as SUB

LORA = {
    "key": "a-lora-model", "model": "runpod/x", "kind": "video", "skill": "s",
    "images": {"refs": None, "max_refs": None, "start": "image", "end": None,
               "start_excludes_refs": False, "accepts_ext": [".jpg", ".png"]},
    "loras": {"high": "high_noise_loras", "low": "low_noise_loras",
              "accepts_ext": [".safetensors"], "scale_param": "lora_scale"},
    "prompt": {"max_chars": None},
}
PLAIN = {**LORA, "key": "a-plain-model", "loras": None}
# A one-stage model: one list, bound with --lora-key.
SINGLE = {**LORA, "key": "a-single-lora-model", "model": "fal/x",
          "images": {**LORA["images"], "start": "image_url"},
          "loras": {"lora": "loras", "accepts_ext": [".safetensors"], "scale_param": "lora_scale"}}


def args(**over):
    base = dict(input_file=None, prompt=None, prompt_file=None, extra=None,
                aspect_ratio=None, key=(), character=(), ref_run=(), slots=None,
                pick=None, pick_tag=None, image_run=None, input_=None,
                start_run=None, start_key=None, end_run=None, end_key=None,
                clip_run=None, clip_key=None, lora_key=(), lora_high_key=(), lora_low_key=(),
                project={"id": "proj-1", "name": "p"})
    return SimpleNamespace(**{**base, **over})


@pytest.fixture
def named(monkeypatch):
    names = {"node-still": "frame.png", "node-high": "orbit_high.safetensors",
             "node-low": "orbit_low.safetensors", "node-bad": "orbit.ckpt"}
    monkeypatch.setattr(SUB, "describe",
                        lambda ref: {"name": names.get(ref, "x.bin"), "size": 1})
    return names


def test_a_lora_binds_per_stage_beside_the_frame(named):
    bound = SUB.gather(LORA, args(start_key="node-still", lora_high_key=("node-high",),
                                  lora_low_key=("node-low",)))
    assert bound == {"image": "node-still", "high_noise_loras": ["node-high"],
                     "low_noise_loras": ["node-low"]}


def test_the_sends_carry_the_lora_role(named):
    bound = SUB.gather(LORA, args(start_key="node-still", lora_high_key=("node-high",)))
    roles = {send["field"]: send["role"] for send in SUB.sends_for(LORA, bound)}
    assert roles == {"image": "start", "high_noise_loras": "lora"}


def test_weights_in_a_format_the_model_refuses_are_refused_here(named):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(LORA, args(start_key="node-still", lora_low_key=("node-bad",)))
    assert ".safetensors" in str(caught.value) and "orbit.ckpt" in str(caught.value)


def test_a_model_with_no_lora_input_says_so(named):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(PLAIN, args(start_key="node-still", lora_high_key=("node-high",)))
    assert "takes no LoRA" in str(caught.value)


def test_a_one_stage_model_binds_one_list_with_lora_key(named):
    bound = SUB.gather(SINGLE, args(start_key="node-still", lora_key=("node-high",)))
    assert bound == {"image_url": "node-still", "loras": ["node-high"]}
    roles = {send["field"]: send["role"] for send in SUB.sends_for(SINGLE, bound)}
    assert roles == {"image_url": "start", "loras": "lora"}


def test_the_wrong_slots_flag_names_the_right_one(named):
    """`--lora-high-key` on a one-stage model, or `--lora-key` on Wan 2.2: the
    refusal says which flag the model does take."""
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(SINGLE, args(start_key="node-still", lora_high_key=("node-high",)))
    assert "--lora-high-key" in str(caught.value) and "it takes --lora-key" in str(caught.value)
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(LORA, args(start_key="node-still", lora_key=("node-high",)))
    assert "it takes --lora-high-key, --lora-low-key" in str(caught.value)
