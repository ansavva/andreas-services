"""A media file's poster: a small still the worker makes — off a clip's first
frame, or a still scaled down — stored beside it, hidden from every listing,
and reported wherever the file is.

Why a poster at all is two measurements. For a clip, `media/faststart.py`'s: a
tile that draws its own poster off the clip's metadata costs the whole clip
in Chrome, and a wall of forty costs a quarter of a gigabyte. For a still,
`media/imaging.poster`'s: a tile drew the original — a 0.4 MB JPEG per output,
and the phone photos and multi-megabyte PNGs a run was sent — and a feed of
twenty runs was a hundred megabytes of thumbnails. The poster is kilobytes.
"""
import io

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


def _png(width, height, *, mode="RGB", orientation=None) -> bytes:
    """A real, decodable picture of a known size — the worker resizes it."""
    from PIL import Image

    im = Image.new(mode, (width, height), (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30))
    buf = io.BytesIO()
    if orientation:
        exif = Image.Exif()
        exif[0x0112] = orientation
        im.save(buf, "JPEG", exif=exif.tobytes())
    else:
        im.save(buf, "PNG")
    return buf.getvalue()


def _still(api, project, name="frame-01.png", body=None):
    """A file node with real image bytes behind it, in the project's input pool."""
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    node = catalog.create_node(pool["node_id"], name, catalog.KIND_FILE)
    from studio_core.clients.aws import s3

    body = body if body is not None else _png(1600, 900)
    content_type = "image/jpeg" if name.endswith(".jpg") else "image/png"
    s3.put_text(node["blob_key"], body, content_type)
    catalog.set_blob(node["node_id"], node["blob_key"], size=len(body),
                     content_type=content_type)
    return node


def _poster(api, clip):
    job = api.post("/api/renders", json={"kind": "poster", "params": {
        "node": clip["node_id"]}}).get_json()
    return render.run(job["id"])["result"]


def _size_of(node_id) -> tuple[int, int]:
    from PIL import Image

    from studio_core.clients.aws import s3

    record = catalog.node(node_id)
    body = s3.client().get_object(Bucket=s3.config.media_bucket(),
                                  Key=record["blob_key"])["Body"].read()
    with Image.open(io.BytesIO(body)) as im:
        return im.size, im.format


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


# ─────────────────────────────── stills ───────────────────────────────


def test_a_still_gets_a_smaller_still_beside_it(empty_api, queue):
    """The one that carries the weight: 1600 across becomes 640, linked both
    ways, hidden from the listing, and reported on the original's pointer."""
    from studio_core.routes import support

    project = _project(empty_api)
    still = _still(empty_api, project)

    result = _poster(empty_api, still)

    poster = catalog.node(result["poster"]["node"])
    assert poster["name"] == "frame-01.poster.jpg"
    assert poster["parent_id"] == still["parent_id"]
    assert poster["poster_of"] == still["node_id"]
    assert catalog.node(still["node_id"])["poster"] == poster["node_id"]
    assert "duration" not in result
    assert "duration" not in catalog.node(still["node_id"])
    (width, height), fmt = _size_of(poster["node_id"])
    assert (width, height) == (640, 360)
    assert fmt == "JPEG"
    assert poster["size"] < catalog.node(still["node_id"])["size"]

    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    listing = empty_api.get(f"/api/nodes?under={pool['node_id']}").get_json()
    names = [entry["name"] for entry in listing["entries"]]
    assert names == ["frame-01.png"]
    assert listing["entries"][0]["poster"]["node"] == poster["node_id"]

    pointer = support.assets([still["node_id"]])[0]
    assert pointer["poster"]["node"] == poster["node_id"]
    assert pointer["poster"]["url"]
    assert "duration" not in pointer


def test_a_small_still_is_never_upscaled(empty_api, queue):
    project = _project(empty_api)
    still = _still(empty_api, project, "tiny.png", _png(320, 200))
    result = _poster(empty_api, still)
    (size, _fmt) = _size_of(result["poster"]["node"])
    assert size == (320, 200)


def test_a_still_with_alpha_keeps_it_as_webp(empty_api, queue):
    """A cut-out drawn over a checkerboard would otherwise get a black hole."""
    from PIL import Image

    from studio_core.clients.aws import s3

    project = _project(empty_api)
    still = _still(empty_api, project, "cutout.png", _png(1000, 1000, mode="RGBA"))
    result = _poster(empty_api, still)
    poster = catalog.node(result["poster"]["node"])
    assert poster["name"] == "cutout.poster.webp"
    assert poster["content_type"] == "image/webp"
    body = s3.client().get_object(Bucket=s3.config.media_bucket(),
                                  Key=poster["blob_key"])["Body"].read()
    with Image.open(io.BytesIO(body)) as im:
        assert im.format == "WEBP"
        assert im.size == (640, 640)
        assert im.mode == "RGBA"


def test_a_phone_photo_stands_the_way_it_displays(empty_api, queue):
    """EXIF orientation 6 is a 90° turn the browser applies and a resize
    would drop; the poster is transposed first, so a 1200×800 JPEG tagged
    sideways is an 800×1200 portrait, and scales to 640×960."""
    project = _project(empty_api)
    still = _still(empty_api, project, "phone.jpg", _png(1200, 800, orientation=6))
    result = _poster(empty_api, still)
    (size, _fmt) = _size_of(result["poster"]["node"])
    assert size == (640, 960)


def test_a_poster_never_gets_a_poster(empty_api, queue):
    project = _project(empty_api)
    still = _still(empty_api, project)
    poster = _poster(empty_api, still)["poster"]

    assert render.wants_poster(catalog.node(poster["node"])) is False
    job = empty_api.post("/api/renders", json={"kind": "poster", "params": {
        "node": poster["node"]}}).get_json()
    assert render.run(job["id"])["status"] == "failed"


def test_a_file_that_is_not_a_picture_fails_for_good(empty_api, queue, monkeypatch):
    """Bytes Pillow cannot read are a permanent failure, not a redrive."""
    project = _project(empty_api)
    still = _still(empty_api, project, "broken.png", b"not a png at all")
    job = empty_api.post("/api/renders", json={"kind": "poster", "params": {
        "node": still["node_id"]}}).get_json()
    done = render.run(job["id"])
    assert done["status"] == "failed"
    assert "Pillow" in done["error"]


def test_confirming_an_upload_queues_a_poster(empty_api, queue, monkeypatch):
    """Uploads are where the heavy files come from."""
    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    created = empty_api.post("/api/nodes", json={
        "parent": pool["node_id"], "name": "photo.jpg", "kind": "file"}).get_json()
    empty_api.post(f"/api/nodes/{created['id']}/upload-url",
                   json={"size": 4, "content_type": "image/jpeg"})
    from studio_core.clients.aws import s3
    s3.put_text(catalog.node(created["id"])["blob_key"], b"four", "image/jpeg")

    queued = []
    monkeypatch.setattr(render, "enqueue",
                        lambda lib, kind, params: queued.append((kind, params)))
    resp = empty_api.post(f"/api/nodes/{created['id']}/confirm-upload", json={})
    assert resp.status_code == 200
    assert queued == [("poster", {"node": created["id"]})]


def test_confirming_a_document_queues_nothing(empty_api, queue, monkeypatch):
    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    created = empty_api.post("/api/nodes", json={
        "parent": pool["node_id"], "name": "notes.txt", "kind": "file"}).get_json()
    from studio_core.clients.aws import s3
    s3.put_text(catalog.node(created["id"])["blob_key"], b"four", "text/plain")
    monkeypatch.setattr(render, "enqueue",
                        lambda *_a: pytest.fail("queued a poster for a text file"))
    assert empty_api.post(f"/api/nodes/{created['id']}/confirm-upload",
                          json={}).status_code == 200


def test_the_sweep_queues_what_lacks_one_and_skips_the_rest(empty_api, queue, grabber):
    project = _project(empty_api)
    covered = _clip(empty_api, project, "covered.mp4")
    _poster(empty_api, covered)
    bare_clip = _clip(empty_api, project, "bare.mp4")
    bare_still = _still(empty_api, project, "bare.png")
    # A folder and a document sit in the tree too and are never media.
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    catalog.create_node(pool["node_id"], "notes", catalog.KIND_FOLDER)

    resp = empty_api.post("/api/posters")
    assert resp.status_code == 202, resp.get_json()
    report = resp.get_json()
    assert sorted(report["queued"]) == sorted([bare_clip["node_id"], bare_still["node_id"]])
    assert report["truncated"] is False
    # The covered clip and its poster were walked and passed over.
    assert report["skipped"] == 2

    # Idempotent by construction: run again before the worker has moved and
    # the same two are queued; run after and none are.
    for render_id in _queued_ids(queue):
        render.run(render_id)
    again = empty_api.post("/api/posters").get_json()
    assert again["queued"] == []


def _queued_ids(queue):
    import json

    client, url = queue
    ids = []
    while True:
        got = client.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", [])
        if not got:
            return ids
        for message in got:
            ids.append(json.loads(message["Body"])["render"])
            client.delete_message(QueueUrl=url, ReceiptHandle=message["ReceiptHandle"])


def test_the_sweep_refuses_without_a_queue(empty_api, monkeypatch):
    monkeypatch.delenv("STUDIO_RENDER_QUEUE_URL", raising=False)
    resp = empty_api.post("/api/posters")
    assert resp.status_code >= 500
    assert "STUDIO_RENDER_QUEUE_URL" in resp.get_data(as_text=True)


def test_a_hero_and_a_listing_thumb_carry_the_poster(empty_api, queue):
    """Every pointer that signs a picture for a tile signs its poster too —
    a character's card, a project's card, a run listing's thumb."""
    project = _project(empty_api)
    still = _still(empty_api, project)
    poster = _poster(empty_api, still)["poster"]

    empty_api.patch(f"/api/projects/{project['id']}",
                    json={"rev": 1, "hero": still["node_id"]})
    cards = empty_api.get("/api/projects").get_json()
    card = next(c for c in cards if c["id"] == project["id"])
    assert card["hero"]["node"] == still["node_id"]
    assert card["hero"]["poster"]["node"] == poster["node"]

    inputs = empty_api.get(f"/api/projects/{project['id']}/inputs").get_json()["inputs"]
    assert [i["name"] for i in inputs] == ["frame-01.png"]
    assert inputs[0]["poster"]["node"] == poster["node"]


def test_a_characters_file_count_excludes_posters(empty_api, queue):
    character = empty_api.post("/api/characters", json={"name": "subject-a"}).get_json()
    pool = catalog.node(character["root"])
    node = catalog.create_node(pool["node_id"], "face.png", catalog.KIND_FILE)
    from studio_core.clients.aws import s3
    body = _png(900, 900)
    s3.put_text(node["blob_key"], body, "image/png")
    catalog.set_blob(node["node_id"], node["blob_key"], size=len(body), content_type="image/png")
    _poster(empty_api, node)

    cards = empty_api.get("/api/characters").get_json()
    assert cards[0]["counts"]["files"] == 1


def test_a_run_landing_queues_a_poster_per_output_still_or_clip(empty_api, queue, monkeypatch):
    """A still is no longer its own poster: the feed drew every output whole."""
    from studio_core.services import generate

    project = _project(empty_api)
    draft = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "image", "engine": "gpt-image-2",
        "model": "openai/gpt-image-2",
        "plan": {"version": 1, "origin": "authored", "prompt": "a frame", "params": {}},
        "input": {"prompt": "a frame"},
    }).get_json()
    empty_api.post(f"/api/runs/{draft['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, draft["id"])

    queued = []
    monkeypatch.setattr(render, "enqueue",
                        lambda lib, kind, params: queued.append((kind, params)))
    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.png", "https://fake.invalid/x/1.png"]})

    assert closed["status"] == "succeeded"
    assert queued == [("poster", {"node": node}) for node in closed["outputs"]]


def test_a_video_run_landing_queues_a_poster_per_clip(empty_api, queue, monkeypatch):
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
