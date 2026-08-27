"""A model that takes no prompt, and one that takes no reference list.

Every model in the registry until now was a generator: it took a prompt, and
most took an array of reference images. An upscaler takes neither — one image
and some settings — and both assumptions were load-bearing in a way that made
such a model **unrunnable**, not merely awkward:

* `run` demanded a prompt before it knew whether the model had one, so the only
  payload it would build was the one the model's schema rejected. There was no
  flag, no file and no ordering of options that got past it.
* binding an image with `--key` wrote it under the reference field, which is
  `null` here — producing a dict with a `None` key that surfaced two calls later
  as `TypeError: '<' not supported between instances of 'NoneType' and 'str'`,
  inside the error path whose job is to explain the fault.

Both are asserted here against the registry's own shape rather than against a
model name, so the next promptless or single-image model inherits the fix.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from studio_pipeline.engine import add_model as AM
from studio_pipeline.engine import runner as RUN
from studio_pipeline.engine import submit as SUB


PROMPTLESS = {
    "key": "an-upscaler",
    "model": "vendor/an-upscaler",
    "kind": "image",
    "images": {"refs": None, "max_refs": None, "start": "image", "end": None,
               "start_excludes_refs": False, "accepts_ext": [".jpg", ".png"]},
    "prompt": None,
}
PROMPTED = {**PROMPTLESS, "key": "a-generator",
            "images": {**PROMPTLESS["images"], "refs": "image_input", "start": None},
            "prompt": {"max_chars": None}}


def args(**over):
    base = dict(input_file=None, prompt=None, prompt_file=None, extra=None,
                aspect_ratio=None, key=(), character=(), ref_run=(), slots=None,
                pick=None, pick_tag=None, image_run=None, input_=None,
                start_run=None, start_key=None, end_run=None, end_key=None,
                project={"id": "proj-1", "slug": "p"})
    return SimpleNamespace(**{**base, **over})


# ── the prompt is required only where there is one ──────────────────────────

def test_a_promptless_model_builds_a_payload_with_no_prompt():
    payload = RUN.build_payload(PROMPTLESS, args(extra='{"upscale_factor":"2x"}'))
    assert payload == {"upscale_factor": "2x"}
    assert "prompt" not in payload


def test_a_prompt_passed_to_a_promptless_model_is_refused_by_name(capsys):
    """Refused, not dropped. A silently ignored option is how you spend money
    believing you steered something you did not."""
    with pytest.raises(SystemExit):
        RUN.build_payload(PROMPTLESS, args(prompt="make it sharper"))
    message = capsys.readouterr().err
    assert "takes no prompt" in message
    assert "an-upscaler" in message


def test_a_prompted_model_still_demands_one(capsys):
    with pytest.raises(SystemExit):
        RUN.build_payload(PROMPTED, args())
    assert "a prompt is required" in capsys.readouterr().err


# ── a model with no reference list says so ──────────────────────────────────

def test_binding_a_reference_list_to_a_single_image_model_names_the_right_flag():
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(PROMPTLESS, args(key=("node-abc",)))
    message = str(caught.value)
    assert "takes no reference list" in message
    assert "--start-key" in message      # the flag that does work
    assert "image" in message            # the field it binds to


def test_the_same_model_binds_a_start_key_happily(monkeypatch):
    """The positive half. `_ext` and the byte warning both read a node's name
    off the API, which is not what this is asserting — the binding is."""
    monkeypatch.setattr(SUB, "_ext", lambda node: ".jpg")
    monkeypatch.setattr(SUB, "_warn_total_bytes", lambda entry, bindings: None)
    assert SUB.gather(PROMPTLESS, args(start_key="node-abc")) == {"image": "node-abc"}


# ── the registry records the difference, so add-model does too ──────────────

def test_add_model_writes_a_null_prompt_when_the_schema_has_none():
    entry, notes = AM.infer("vendor/an-upscaler",
                            {"image": {"type": "string"},
                             "upscale_factor": {"type": "string"}},
                            {}, "an upscaler")
    assert entry["prompt"] is None
    assert any("prompt=null" in n for n in notes)


def test_add_model_still_writes_a_prompt_block_when_the_schema_has_one():
    entry, _ = AM.infer("vendor/a-generator",
                        {"prompt": {"type": "string",
                                    "description": "Max 5000 characters."}},
                        {}, "a generator")
    assert entry["prompt"] == {"max_chars": 5000}
