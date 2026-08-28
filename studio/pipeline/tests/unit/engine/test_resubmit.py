"""Rebuilding a draft's provider input from its own record (`engine/resubmit`).

`studio run` gathers bindings from arguments; `studio runs submit` rebuilds them
from the send rows a draft already carries. The two paths have to agree about
SHAPE as well as content, and that is the whole subject here — a difference
between them is invisible until a real provider rejects the payload, and by then
the run has been patched to `pending` and cannot be resubmitted.
"""
from __future__ import annotations

from studio_pipeline.engine import resubmit


KLING = {
    "key": "kling",
    "model": "kwaivgi/kling-v3-omni-video",
    "images": {"refs": "reference_images", "start": "start_image",
               "end": "end_image", "max_refs": 7},
}


def _record(sends: list[tuple[str, str]]) -> dict:
    return {"id": "run-1", "model": KLING["model"],
            "sends": [{"field": f, "node": n, "role": "x"} for f, n in sends]}


def test_a_start_frame_rebuilds_as_a_scalar_not_a_list():
    """The 422 this exists to prevent.

    `reference_images` is an array and `start_image` is a string, and `submit`
    presigns whatever shape it is handed — so rebuilding every field as a list
    sent `{"start_image": ["https://…"]}`. Replicate answered
    `422 Invalid type. Expected: string, given: array`, and because the run is
    patched to `pending` before the request goes out, the draft was left wedged
    rather than merely refused.
    """
    bindings = resubmit.bindings_of(
        _record([("start_image", "node-start"),
                 ("reference_images", "node-a"),
                 ("reference_images", "node-b")]),
        KLING)

    assert bindings["start_image"] == "node-start"
    assert bindings["reference_images"] == ["node-a", "node-b"]


def test_an_end_frame_is_a_scalar_too():
    """`images.end` is read from the registry beside `images.start`, not guessed."""
    bindings = resubmit.bindings_of(
        _record([("start_image", "node-s"), ("end_image", "node-e")]), KLING)

    assert bindings["start_image"] == "node-s"
    assert bindings["end_image"] == "node-e"


def test_reference_order_is_the_send_order():
    """A prompt citing "the first image" depends on this, so it is pinned."""
    bindings = resubmit.bindings_of(
        _record([("reference_images", f"node-{i}") for i in range(5)]), KLING)

    assert bindings["reference_images"] == [f"node-{i}" for i in range(5)]


def test_an_image_model_has_no_frame_fields_and_keeps_its_list():
    """`images.start` is null for every image engine, so nothing is unwrapped.

    A one-item list must stay a list there: `input_images` takes an array even
    when only one image is bound, and unwrapping on count rather than on registry
    data would have broken a single-reference image run.
    """
    entry = {"key": "gpt-image-2", "model": "openai/gpt-image-2",
             "images": {"refs": "input_images", "start": None, "end": None}}
    record = {"id": "run-2", "model": entry["model"],
              "sends": [{"field": "input_images", "node": "node-only", "role": "reference"}]}

    assert resubmit.bindings_of(record, entry) == {"input_images": ["node-only"]}


def test_the_payload_carries_no_image_fields():
    """Images are sends, presigned in at the last moment — never part of `plan`."""
    record = {"id": "run-3", "model": KLING["model"],
              "plan": {"prompt": "a shot", "params": {"duration": 12, "mode": "standard"}},
              "sends": [{"field": "start_image", "node": "node-s", "role": "start"}]}

    payload = resubmit.payload_of(record)

    assert payload == {"duration": 12, "mode": "standard", "prompt": "a shot"}
    assert "start_image" not in payload
