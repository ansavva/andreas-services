"""The clip: the one VIDEO a model works from, bound like a frame.

A motion-control model copies the movement of a reference clip; an editing
model changes a clip it is given. Both take that clip in a scalar `format: uri`
field the registry names under `clips.source`, and until this seam existed the
only way in was a presigned URL pasted into `--extra` — which recorded an
expiring URL where a node id belongs, and left the run unable to say which clip
it worked from. `--clip-run` / `--clip-key` bind a node, the send carries the
role `clip`, and dispatch presigns it with everything else.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from studio_pipeline.engine import add_model as AM
from studio_pipeline.engine import runner as RUN
from studio_pipeline.engine import schema as MS
from studio_pipeline.engine import submit as SUB


MOTION = {
    "key": "a-motion-model",
    "model": "vendor/a-motion-model",
    "kind": "video",
    "images": {"refs": None, "max_refs": 0, "start": "image", "end": None,
               "start_excludes_refs": False, "accepts_ext": [".jpg", ".png"]},
    "clips": {"source": "video", "accepts_ext": [".mp4", ".mov"]},
    "prompt": {"max_chars": None},
}
STILL_ONLY = {**MOTION, "key": "a-still-only-model", "clips": None}


def args(**over):
    base = dict(input_file=None, prompt=None, prompt_file=None, extra=None,
                aspect_ratio=None, key=(), character=(), ref_run=(), slots=None,
                pick=None, pick_tag=None, image_run=None, input_=None,
                start_run=None, start_key=None, end_run=None, end_key=None,
                clip_run=None, clip_key=None,
                project={"id": "proj-1", "name": "p"})
    return SimpleNamespace(**{**base, **over})


@pytest.fixture
def named(monkeypatch):
    """Node names, as the API would answer them, without an API."""
    names = {"node-still": "frame.png", "node-clip": "dance.mp4",
             "node-webm": "dance.webm"}
    monkeypatch.setattr(SUB, "describe",
                        lambda ref: {"name": names.get(ref, "x.bin"), "size": 1})
    return names


def test_a_clip_binds_beside_the_frame(named):
    bound = SUB.gather(MOTION, args(start_key="node-still", clip_key="node-clip"))
    assert bound == {"image": "node-still", "video": "node-clip"}


def test_the_send_carries_the_clip_role(named):
    bound = SUB.gather(MOTION, args(start_key="node-still", clip_key="node-clip"))
    roles = {send["field"]: send["role"] for send in SUB.sends_for(MOTION, bound)}
    assert roles == {"image": "start", "video": "clip"}


def test_a_clip_in_a_format_the_model_refuses_is_refused_here(named):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(MOTION, args(start_key="node-still", clip_key="node-webm"))
    assert ".mp4" in str(caught.value) and "dance.webm" in str(caught.value)


def test_a_model_with_no_clip_input_says_so(named):
    with pytest.raises(SUB.SubmitError) as caught:
        SUB.gather(STILL_ONLY, args(start_key="node-still", clip_key="node-clip"))
    assert "takes no clip" in str(caught.value)


def test_the_clip_is_not_counted_in_the_image_byte_warning(named, monkeypatch, capsys):
    """The 6.4 MiB ceiling was measured on stills; a 60 MB clip is normal."""
    monkeypatch.setattr(SUB, "describe",
                        lambda ref: {"name": named.get(ref, "x.bin"),
                                     "size": 60 * 1024 * 1024 if ref == "node-clip" else 1})
    SUB.gather(MOTION, args(start_key="node-still", clip_key="node-clip"))
    assert "warning" not in capsys.readouterr().err


def test_the_clip_field_may_not_be_smuggled_through_the_payload(capsys):
    with pytest.raises(SystemExit):
        RUN.build_payload(MOTION, SimpleNamespace(
            input_file=None, prompt="x", prompt_file=None, aspect_ratio=None,
            extra='{"video": "https://example.invalid/a.mp4"}'))
    assert "--clip-run" in capsys.readouterr().err


# ── the schema's own `required` list is checked before a draft is written ───

PROPS = {"prompt": {"type": "string"}, "image": {"type": "string"},
         "video": {"type": "string"}}
SCHEMAS = {"Input": {"required": ["image", "video"]}}


def test_a_missing_required_input_is_a_refusal_not_a_draft():
    with pytest.raises(MS.SchemaError) as caught:
        MS.check({"prompt": "x"}, {"image": "node-still"},
                 "vendor/a-motion-model", PROPS, SCHEMAS)
    assert "requires ['video']" in str(caught.value)


def test_a_required_input_is_met_by_a_binding_or_a_value():
    MS.check({"prompt": "x"}, {"image": "node-still", "video": "node-clip"},
             "vendor/a-motion-model", PROPS, SCHEMAS)
    MS.check({"prompt": "x", "video": "https://signed"}, {"image": "node-still"},
             "vendor/a-motion-model", PROPS, SCHEMAS)


# ── add-model reads the clip off the schema ─────────────────────────────────

def test_add_model_infers_the_clip_block():
    entry, notes = AM.infer(
        "vendor/a-motion-model",
        {"prompt": {"type": "string"}, "image": {"type": "string"},
         "video": {"type": "string", "description": "Reference video. Supports .mp4/.mov, max 100MB."},
         "mode": {"type": "string"}},
        {}, "")
    assert entry["clips"] == {"source": "video", "accepts_ext": [".mov", ".mp4"]}
    assert any("clips.source=video" in n for n in notes)


def test_add_model_writes_no_clip_block_where_there_is_no_clip():
    entry, _ = AM.infer("vendor/a-generator",
                        {"prompt": {"type": "string"}, "image_input": {"type": "array"}},
                        {}, "")
    assert "clips" not in entry
