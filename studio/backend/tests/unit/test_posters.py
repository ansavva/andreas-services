"""A clip's poster: a still the worker takes off its first frame, stored
beside it, hidden from every listing, and reported wherever the clip is.

Why a poster at all is `media/faststart.py`'s measurement: a tile that draws
its own poster off the clip's metadata costs the whole clip in Chrome, and a
wall of forty costs a quarter of a gigabyte. The still is kilobytes.
"""
import pytest

from studio_core.services import catalog, layout, render

from tests.unit.test_render import _clip, _project
from tests.unit.test_render import queue as _queue

# The moto queue `test_render` owns, re-exported under its own name so the
# tests below can ask for it without ruff reading each use as a redefinition.
queue = _queue


@pytest.fixture
def grabber(monkeypatch):
    """ffmpeg, stood in for: a JPEG of known bytes and a duration of 5.0."""
    from studio_core.media import ffmpeg

    def fake_poster(_src, dest, width=640):
        with open(dest, "wb") as handle:
            handle.write(b"\xff\xd8\xff" + b"P" * 64)
        return dest

    monkeypatch.setattr(ffmpeg, "poster", fake_poster)
    monkeypatch.setattr(ffmpeg, "duration", lambda _p: 5.0)


def _poster(api, clip):
    job = api.post("/api/renders", json={"kind": "poster", "params": {
        "node": clip["node_id"]}}).get_json()
    return render.run(job["id"])["result"]


def test_the_still_lands_beside_the_clip_linked_both_ways(empty_api, queue, grabber):
    project = _project(empty_api)
    clip = _clip(empty_api, project)

    result = _poster(empty_api, clip)

    still = catalog.node(result["poster"]["node"])
    assert still["parent_id"] == clip["parent_id"]
    assert still["name"] == "shot-01.poster.jpg"
    assert still["poster_of"] == clip["node_id"]
    linked = catalog.node(clip["node_id"])
    assert linked["poster"] == still["node_id"]
    assert linked["duration"] == 5.0
    assert result["duration"] == 5.0


def test_a_second_pass_costs_no_render(empty_api, queue, grabber, monkeypatch):
    """The backfill runs over whole projects; a clip already covered is a read."""
    project = _project(empty_api)
    clip = _clip(empty_api, project)
    first = _poster(empty_api, clip)

    from studio_core.clients.aws import s3
    monkeypatch.setattr(s3, "download", lambda *_a, **_k: pytest.fail("pulled the clip"))
    again = _poster(empty_api, clip)

    assert again["existing"] is True
    assert again["poster"]["node"] == first["poster"]["node"]


def test_the_still_is_hidden_from_listings_and_reported_on_the_clip(empty_api, queue, grabber):
    project = _project(empty_api)
    clip = _clip(empty_api, project)
    still = _poster(empty_api, clip)["poster"]

    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    listing = empty_api.get(f"/api/nodes?under={pool['node_id']}").get_json()
    names = [entry["name"] for entry in listing["entries"]]
    assert "shot-01.mp4" in names
    assert "shot-01.poster.jpg" not in names
    entry = next(e for e in listing["entries"] if e["name"] == "shot-01.mp4")
    assert entry["poster"]["node"] == still["node"]
    assert entry["poster"]["url"]
    assert entry["duration"] == 5.0

    # Media view — the flat, recursive one the wall used to be — hides it too.
    flat = empty_api.get(
        f"/api/nodes?under={project['root']}&depth=all&kind=image,video").get_json()
    assert [e["name"] for e in flat["entries"]] == ["shot-01.mp4"]


def test_a_run_output_carries_its_poster(empty_api, queue, grabber):
    """The feed row and the run record expand the same pointer."""
    from studio_core.routes import support

    project = _project(empty_api)
    clip = _clip(empty_api, project)
    still = _poster(empty_api, clip)["poster"]

    pointer = support.assets([clip["node_id"]])[0]
    assert pointer["poster"]["node"] == still["node"]
    assert pointer["duration"] == 5.0
    # A still has neither.
    assert "poster" not in support.assets([still["node"]])[0]


def test_deleting_the_clip_takes_the_still_with_it(empty_api, queue, grabber):
    """Nothing can select a hidden row, so the clip's delete is the only way
    the still ever goes."""
    project = _project(empty_api)
    clip = _clip(empty_api, project)
    still = _poster(empty_api, clip)["poster"]

    resp = empty_api.delete("/api/nodes", json={"ids": [clip["node_id"]]})
    assert resp.status_code == 200, resp.get_json()
    with pytest.raises(Exception):
        catalog.node(still["node"])


def test_a_video_run_landing_queues_a_poster_per_clip(empty_api, queue, monkeypatch):
    """And an image run queues nothing; a still is its own poster."""
    from studio_core.services import generate

    project = _project(empty_api)
    draft = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": "seedance",
        "model": "bytedance/seedance-2.0",
        "plan": {"version": 1, "origin": "authored", "prompt": "waves", "params": {}},
        "input": {"prompt": "waves"},
    }).get_json()
    empty_api.post(f"/api/runs/{draft['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, draft["id"])

    queued = []
    monkeypatch.setattr(render, "enqueue",
                        lambda lib, kind, params: queued.append((kind, params)))
    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.mp4", "https://fake.invalid/x/1.mp4"]})

    assert closed["status"] == "succeeded"
    assert queued == [("poster", {"node": node}) for node in closed["outputs"]]


def test_a_missing_queue_never_fails_the_close(empty_api, monkeypatch):
    from studio_core.services import generate

    project = _project(empty_api)
    draft = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": "seedance",
        "model": "bytedance/seedance-2.0",
        "plan": {"version": 1, "origin": "authored", "prompt": "waves", "params": {}},
        "input": {"prompt": "waves"},
    }).get_json()
    empty_api.post(f"/api/runs/{draft['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, draft["id"])
    monkeypatch.delenv("STUDIO_RENDER_QUEUE_URL", raising=False)

    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.mp4"]})
    assert closed["status"] == "succeeded"
