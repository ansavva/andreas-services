"""Render jobs: the route that enqueues, the row that reports, the worker that cuts.

**What replaced ~1,360 lines of local media processing.** `routes/scenes.py` used
to say stitching stays in the CLI because `ffmpeg` ships in the pipeline wheel and
the Lambda has none; a second container image has it now, and this is the seam
between the request and that image.

Three things are under test here and the split matters:

* **The route refuses what it can refuse without moving bytes.** A job that fails
  validation twenty seconds later, in a worker, reaches a person as a failed row;
  the same sentence on the `POST` reaches them as a 400 they can act on.
* **The worker's record-keeping**, which is the half that is not ffmpeg — what a
  cut writes onto a scene, that a superseded cut is kept, that the shots learn
  their copies.
* **Which failures redrive and which do not**, because getting that backwards
  either fills the dead-letter queue with something nobody can act on or loses
  work that would have succeeded.

The encode itself is not exercised: `media/ffmpeg.py` shells out to a binary only
the render image carries, and installing it here would undo the split. `stitch`
is patched, and what is asserted is the report it returns reaching the record —
which is the clause most likely to be lost in a port and the one nobody could see
being lost, because the file plays either way.
"""

import json

import boto3
import pytest
from moto import mock_sqs

from studio_core.errors import ConfigError
from studio_core.services import catalog, layout, render


@pytest.fixture
def queue(monkeypatch):
    """A moto queue, and `STUDIO_RENDER_QUEUE_URL` pointing at it.

    Assigned per test rather than defaulted in `conftest.py`, because the *absent*
    case is a behaviour worth its own test: an environment with no queue refuses
    at the moment a caller asks for work, naming the variable.
    """
    with mock_sqs():
        from studio_core.clients.aws import sqs

        sqs.reset_client()
        client = boto3.client("sqs", region_name="us-east-1")
        url = client.create_queue(QueueName="studio-test-render")["QueueUrl"]
        monkeypatch.setenv("STUDIO_RENDER_QUEUE_URL", url)
        yield client, url
        sqs.reset_client()


def _project(api, name="rooftop-teaser"):
    return api.post("/api/projects", json={"name": name}).get_json()


def _scene(api, project, name="stadium-encounter", shots=None):
    return api.post("/api/scenes", json={
        "project": project["id"], "name": name, "shots": shots or []}).get_json()


def _movie(api, project, name="launch-cut"):
    return api.post("/api/movies", json={
        "project": project["id"], "name": name}).get_json()


def _clip(api, project, name="shot-01.mp4"):
    """A file node with bytes behind it, in the project's input pool."""
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    node = catalog.create_node(pool["node_id"], name, catalog.KIND_FILE)
    from studio_core.clients.aws import s3

    s3.put_text(node["blob_key"], b"\x00\x00\x00\x18ftypmp42" + b"0" * 256,
                "video/mp4")
    catalog.set_blob(node["node_id"], node["blob_key"], size=272,
                     content_type="video/mp4")
    return node


@pytest.fixture
def stitcher(monkeypatch):
    """Stand in for ffmpeg, which only the render image has.

    It writes a real file, because everything after it — `os.path.getsize`, the
    `PutObject`, the checksum — is real and would otherwise be testing nothing.
    What it returns is the shape `media/ffmpeg.stitch` returns, including the
    report the caller is required to record.
    """
    from studio_core.media import ffmpeg

    calls = []

    def fake_stitch(paths, dest, *, label="parts"):
        calls.append({"paths": list(paths), "label": label})
        with open(dest, "wb") as handle:
            handle.write(b"\x00\x00\x00\x18ftypmp42" + b"0" * 512)
        return {"method": "concat demuxer, stream copy (no re-encode)",
                f"uniform_{label}": True,
                "probes": [{"duration": 5.0} for _ in paths]}

    monkeypatch.setattr(ffmpeg, "stitch", fake_stitch)
    monkeypatch.setattr(ffmpeg, "probe", lambda _p: {"duration": 10.0, "video": {}})
    return calls


# ──────────────────────────── enqueueing ────────────────────────────


def test_an_accepted_job_is_202_with_the_row_to_poll(empty_api, queue):
    """**Not 201.** Nothing the caller asked for exists: the scene has no new cut
    and the folder has no new image. What exists is an accepted request."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)

    resp = empty_api.post("/api/renders", json={
        "kind": "assemble",
        "params": {"target": scene["id"], "parts": [{"node": clip["node_id"]}]},
    })

    assert resp.status_code == 202
    body = resp.get_json()
    assert body["id"].startswith("render-")
    assert body["status"] == "queued"
    assert resp.headers["Location"] == f"/api/renders/{body['id']}"


def test_the_message_carries_the_render_id_and_nothing_else(empty_api, queue):
    """**One copy of the job, and it is the row.** Putting the params in the
    message too would be a second copy a redrive could disagree with."""
    client, url = queue
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)

    job = empty_api.post("/api/renders", json={
        "kind": "assemble",
        "params": {"target": scene["id"], "parts": [{"node": clip["node_id"]}]},
    }).get_json()

    messages = client.receive_message(QueueUrl=url)["Messages"]
    assert json.loads(messages[0]["Body"]) == {"render": job["id"]}


def test_an_environment_with_no_queue_says_which_variable(empty_api, monkeypatch):
    """CI deliberately sets none, and the refusal has to name the reason rather
    than fail somewhere inside boto3."""
    monkeypatch.delenv("STUDIO_RENDER_QUEUE_URL", raising=False)
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    with pytest.raises(ConfigError) as refusal:
        render.enqueue(scene["lib"], "assemble",
                       {"target": scene["id"], "parts": [{"node": "node-x"}]})

    assert "STUDIO_RENDER_QUEUE_URL" in str(refusal.value)


@pytest.mark.parametrize("kind,params,expected", [
    ("nonsense", {}, "not a render kind"),
    ("assemble", {"parts": [{"node": "node-x"}]}, "target"),
    ("frame", {"node": "node-x", "dest": "node-y"}, "at"),
    ("grid", {"node": "node-x", "dest": "node-y", "count": 0}, "count"),
])
def test_a_malformed_job_is_refused_at_the_route(empty_api, queue, kind, params, expected):
    """**Everything checkable without moving bytes is checked here**, because the
    same sentence on the POST is actionable and on a row twenty seconds later is
    archaeology."""
    resp = empty_api.post("/api/renders", json={"kind": kind, "params": params})

    assert resp.status_code == 400
    assert expected in resp.get_json()["error"]


def test_a_frame_takes_at_or_from_end_and_not_both(empty_api, queue):
    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    clip = _clip(empty_api, project)

    resp = empty_api.post("/api/renders", json={"kind": "frame", "params": {
        "node": clip["node_id"], "dest": pool["node_id"], "at": 1, "from_end": 1}})

    assert resp.status_code == 400
    assert "not both" in resp.get_json()["error"]


def test_a_destination_that_is_a_file_is_refused(empty_api, queue):
    project = _project(empty_api)
    clip = _clip(empty_api, project)

    resp = empty_api.post("/api/renders", json={"kind": "frame", "params": {
        "node": clip["node_id"], "dest": clip["node_id"], "from_end": 0.2}})

    assert resp.status_code == 400
    assert "not a folder" in resp.get_json()["error"]


def test_more_inputs_than_the_cap_are_refused_before_a_single_catalog_read(
        empty_api, queue, monkeypatch):
    """The real bound is bytes — `workspace.reserve` measures those — but a
    request naming ten thousand nodes should not cost ten thousand reads first."""
    monkeypatch.setenv("STUDIO_MAX_RENDER_INPUTS", "2")
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    resp = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": f"node-{n}"} for n in range(3)]}})

    assert resp.status_code == 400
    assert "at most 2" in resp.get_json()["error"]


# ──────────────────────────── polling ────────────────────────────


def test_a_render_row_is_membership_checked_and_not_merely_unguessable(
        empty_api, queue):
    """A render id is a v4 UUID, which is a fine thing to hand out and a poor
    thing to authorise with. The row carries the library it was created in and
    the caller has to be in it."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)
    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": clip["node_id"]}]}}).get_json()

    assert empty_api.get(f"/api/renders/{job['id']}").status_code == 200

    catalog.update_render(job["id"], lib="lib-somebody-else")

    assert empty_api.get(f"/api/renders/{job['id']}").status_code == 403


def test_a_render_that_does_not_exist_is_a_404(empty_api, queue):
    assert empty_api.get("/api/renders/render-nope").status_code == 404


# ──────────────────────────── the worker ────────────────────────────


def test_a_cut_lands_on_the_scene_with_the_stitch_report(empty_api, queue, stitcher):
    """**The clause most likely to be lost in a port.**

    `stitch` normalises inputs to the first one's geometry when they disagree and
    the caller is required to record that it happened. A worker that re-encoded
    silently would be a quality regression nobody could see, because the file
    plays either way — so the report reaching the record is asserted, not the
    encode.
    """
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clips = [_clip(empty_api, project, f"shot-{n}.mp4") for n in (1, 2)]

    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"],
        "parts": [{"node": clip["node_id"]} for clip in clips],
        "characters": ["char-b", "char-a"],
    }}).get_json()
    render.run(job["id"])

    after = catalog.entity(catalog.ENTITY_SCENE, scene["id"])
    assert after["status"] == "assembled"
    assert after["output"]["node"].startswith("node-")
    assert after["stitch"]["method"] == "concat demuxer, stream copy (no re-encode)"
    assert after["stitch"]["uniform_shots"] is True
    assert [cut["n"] for cut in after["stitch"]["cuts"]] == [1, 2]
    assert after["characters"] == ["char-a", "char-b"]
    assert stitcher[0]["label"] == "shots"


def test_a_movie_is_stitched_by_the_same_rules_as_a_scene(empty_api, queue, stitcher):
    """One layer, two tiers. A movie joins scenes exactly the way a scene joins
    shots, and the label is the only thing that differs."""
    project = _project(empty_api)
    movie = _movie(empty_api, project)
    clip = _clip(empty_api, project)

    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": movie["id"], "parts": [{"node": clip["node_id"]}]}}).get_json()
    render.run(job["id"])

    after = catalog.entity(catalog.ENTITY_MOVIE, movie["id"])
    assert after["status"] == "assembled"
    assert stitcher[0]["label"] == "scenes"
    assert after["stitch"]["uniform_scenes"] is True


def test_each_part_is_copied_in_rather_than_pointed_at(empty_api, queue, stitcher):
    """A scene stays playable and re-cuttable while its runs are rebuilt around
    it. A second node on one blob is copy-on-write and the delete route destroys
    the shared bytes when either row goes, so the copy is real — two blobs."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)

    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": clip["node_id"]}]}}).get_json()
    render.run(job["id"])

    after = catalog.entity(catalog.ENTITY_SCENE, scene["id"])
    copied = after["stitch"]["cuts"][0]["node"]
    assert copied != clip["node_id"]
    assert catalog.node(copied)["blob_key"] != clip["blob_key"]
    shots_folder = catalog.child_by_name(after["folder"], "shots")
    assert catalog.node(copied)["parent_id"] == shots_folder["node_id"]


def test_re_cutting_keeps_the_cut_it_displaces(empty_api, queue, stitcher):
    """Assembling is not a one-shot act. A superseded cut used to be reachable by
    nobody, which is the thing re-cutting is for."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)

    for _ in range(2):
        job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
            "target": scene["id"], "parts": [{"node": clip["node_id"]}]}}).get_json()
        render.run(job["id"])

    after = catalog.entity(catalog.ENTITY_SCENE, scene["id"])
    assert len(after["cuts"]) == 1
    assert after["cuts"][0]["node"] != after["output"]["node"]
    assert catalog.node(after["output"]["node"])["name"] == "stadium-encounter-2.mp4"


def test_a_shot_learns_its_copy_its_position_and_its_duration(empty_api, queue, stitcher):
    """The worker writes the shot rows, because the assemble is what knows them.
    A part with no `shot` was appended with `--shot <runref>` against a scene with
    no plan; there is no row to update and nothing is invented for it."""
    project = _project(empty_api)
    scene = _scene(empty_api, project, shots=[{"prompt": "a"}, {"prompt": "b"}])
    planned = empty_api.get(f"/api/scenes/{scene['id']}").get_json()["shots"]
    clips = [_clip(empty_api, project, f"shot-{n}.mp4") for n in (1, 2)]

    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"],
        "parts": [{"node": clip["node_id"], "shot": shot["id"]}
                  for clip, shot in zip(clips, planned)],
    }}).get_json()
    render.run(job["id"])

    written = catalog.shots(scene["id"])
    # **Position is `order`, and `n` is derived from it on read.** The worker
    # deliberately writes no `n`: storing it would be a second answer to one
    # question and would go stale the first time a plan was reordered.
    # `order` is spaced (10, 20, …) so a shot can be inserted between two
    # without renumbering the plan; what matters here is that the worker did not
    # touch it.
    assert [shot["order"] for shot in written] == [10, 20]
    assert "n" not in written[0]
    assert [shot["node"] for shot in written] == [clip["node_id"] for clip in clips]
    assert all(shot["shot_node"] != shot["node"] for shot in written)
    assert all(shot["duration"] == 5.0 for shot in written)


def test_a_job_is_idempotent_because_delivery_is_at_least_once(
        empty_api, queue, stitcher):
    """Re-running an assemble would cut the scene a second time and push a
    perfectly good cut into `cuts` for no reason, so the guard is on the row
    rather than left to each job to be idempotent about."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)

    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": clip["node_id"]}]}}).get_json()
    render.run(job["id"])
    render.run(job["id"])

    assert len(stitcher) == 1
    assert catalog.entity(catalog.ENTITY_SCENE, scene["id"]).get("cuts") == []


def test_a_part_that_is_a_folder_is_a_permanent_failure(empty_api, queue):
    """**A redrive would fail identically five times and then fill the
    dead-letter queue with a message whose only remedy is a code change.**"""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)

    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": pool["node_id"]}]}}).get_json()
    settled = render.run(job["id"])

    assert settled["status"] == "failed"
    assert "is a folder, not a file" in settled["error"]


def test_a_blob_that_has_been_deleted_is_permanent_too(empty_api, queue):
    """**The one that is easy to get wrong.** A vanished object raises
    `NotFoundError`, which reads like a transient AWS failure and is not: no
    number of redrives puts a deleted file back, and the retries spend the
    dead-letter queue on something nobody can act on.
    """
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    # A file node with a `blob_key` and no object behind it: what a delete
    # racing a render leaves.
    orphan = catalog.create_node(pool["node_id"], "gone.mp4", catalog.KIND_FILE)

    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": orphan["node_id"]}]}}).get_json()
    settled = render.run(job["id"])

    assert settled["status"] == "failed"
    assert orphan["blob_key"] in settled["error"]


def test_a_transient_failure_is_left_running_so_the_queue_brings_it_back(
        empty_api, queue, monkeypatch):
    """The row stays `running`, which is what a poller should see: the work has
    not finished and has not given up."""
    from studio_core.clients.aws import s3

    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)
    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": clip["node_id"]}]}}).get_json()

    def throttled(*_a, **_k):
        raise RuntimeError("DynamoDB throttled this write")

    monkeypatch.setattr(s3, "download", throttled)

    with pytest.raises(RuntimeError):
        render.run(job["id"])
    assert catalog.render(job["id"])["status"] == "running"


def test_a_message_naming_no_render_is_dropped_rather_than_redriven(empty_api, queue):
    """A deleted library is the ordinary way to reach this, and there is nothing
    to retry toward."""
    with pytest.raises(render.RenderError):
        render.handle(json.dumps({"render": "render-gone"}))
    with pytest.raises(render.RenderError):
        render.handle("not json at all")


def test_a_render_targeting_another_library_is_refused(empty_api, queue, monkeypatch):
    """The row carries the library because the worker has no request and therefore
    no `g.library`. A job whose target moved is a refusal, not a cross-library
    write."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    clip = _clip(empty_api, project)
    job = empty_api.post("/api/renders", json={"kind": "assemble", "params": {
        "target": scene["id"], "parts": [{"node": clip["node_id"]}]}}).get_json()

    catalog.update_render(job["id"], lib="lib-somewhere-else")
    settled = render.run(job["id"])

    assert settled["status"] == "failed"
    assert "is not in lib-somewhere-else" in settled["error"]


def test_a_frame_and_a_grid_land_where_the_caller_said(empty_api, queue, monkeypatch):
    """The worker's contract for everything except an assemble: bytes in, one
    node out, in a folder the caller named. What that node then means — a chain
    entry, a shot's handoff — is the caller's."""
    from studio_core.media import ffmpeg

    def fake_grab(_src, _when, dest, from_end=None):
        with open(dest, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        return dest

    def fake_grid(_src, count, dest, width=900):
        with open(dest, "wb") as handle:
            handle.write(b"\xff\xd8\xff" + b"0" * 64)
        return [i + 0.5 for i in range(count)]

    monkeypatch.setattr(ffmpeg, "grab", fake_grab)
    monkeypatch.setattr(ffmpeg, "contact_grid", fake_grid)

    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    clip = _clip(empty_api, project)

    frame = empty_api.post("/api/renders", json={"kind": "frame", "params": {
        "node": clip["node_id"], "dest": pool["node_id"],
        "from_end": 0.2, "name": "last.png"}}).get_json()
    grid = empty_api.post("/api/renders", json={"kind": "grid", "params": {
        "node": clip["node_id"], "dest": pool["node_id"],
        "count": 3, "name": "grid.jpg"}}).get_json()

    frame_result = render.run(frame["id"])["result"]
    grid_result = render.run(grid["id"])["result"]

    assert catalog.node(frame_result["frame"]["node"])["parent_id"] == pool["node_id"]
    assert catalog.node(frame_result["frame"]["node"])["name"] == "last.png"
    assert grid_result["sampled_at"] == [0.5, 1.5, 2.5]


def test_a_sheet_keeps_the_captions_and_the_order_it_was_given(empty_api, queue):
    """Tile N is what a prompt cites as `[ImageN]`; natural-sorting the tiles
    would renumber the citations."""
    from studio_core.clients.aws import s3

    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)

    import io

    from PIL import Image

    tiles = []
    for name in ("b.png", "a.png"):
        node = catalog.create_node(pool["node_id"], name, catalog.KIND_FILE)
        buffer = io.BytesIO()
        Image.new("RGB", (20, 20), (0, 0, 0)).save(buffer, "PNG")
        s3.put_text(node["blob_key"], buffer.getvalue(), "image/png")
        catalog.set_blob(node["node_id"], node["blob_key"],
                         size=len(buffer.getvalue()), content_type="image/png")
        tiles.append(node)

    job = empty_api.post("/api/renders", json={"kind": "sheet", "params": {
        "parts": [{"node": tiles[0]["node_id"], "caption": "[Image1] b"},
                  {"node": tiles[1]["node_id"], "caption": "[Image2] a"}],
        "cols": 2, "cell": 40, "dest": pool["node_id"], "name": "sheet.png",
    }}).get_json()

    result = render.run(job["id"])["result"]

    assert result["captions"] == ["[Image1] b", "[Image2] a"]
    assert result["tiles"] == 2
    assert catalog.node(result["sheet"]["node"])["name"] == "sheet.png"


def test_a_tile_that_is_not_an_image_is_a_permanent_failure(empty_api, queue):
    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    clip = _clip(empty_api, project)

    job = empty_api.post("/api/renders", json={"kind": "sheet", "params": {
        "parts": [{"node": clip["node_id"]}], "cols": 1, "cell": 40,
        "dest": pool["node_id"], "name": "sheet.png"}}).get_json()
    settled = render.run(job["id"])

    assert settled["status"] == "failed"
    assert "is not an image" in settled["error"]


def test_a_produced_name_that_is_taken_lands_beside_it_rather_than_409ing(
        empty_api, queue, monkeypatch):
    """**A retry bug, not a nicety.** A clash in `create_node` is a
    `ConflictError`, so a job retried after storing something would fail
    identically for ever on a filename and march to the dead-letter queue."""
    from studio_core.media import ffmpeg

    monkeypatch.setattr(ffmpeg, "grab", lambda _s, _w, dest, from_end=None: (
        open(dest, "wb").write(b"\x89PNG\r\n\x1a\n") and dest) or dest)

    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    clip = _clip(empty_api, project)

    names = []
    for _ in range(2):
        job = empty_api.post("/api/renders", json={"kind": "frame", "params": {
            "node": clip["node_id"], "dest": pool["node_id"],
            "from_end": 0.2, "name": "last.png"}}).get_json()
        result = render.run(job["id"])["result"]
        names.append(catalog.node(result["frame"]["node"])["name"])

    assert names == ["last.png", "last (2).png"]


# ──────────────────────────── the Lambda entrypoint ────────────────────────────


def test_the_worker_reports_only_the_message_that_failed(monkeypatch):
    """**Partial batch response, and it matters even at a batch size of one.**

    A batch is several jobs for several callers, and letting one exception escape
    redrives all of them. The batch size is 1 today because a stitch is minutes —
    batching would serialise unrelated callers behind each other under one
    timeout — but a batch size is a tuning value somebody will raise, and losing
    correctness to it would be a change hiding inside one.
    """
    from studio_core.handlers.aws.render import render_handler

    def handle(body):
        if "boom" in body:
            raise RuntimeError("S3 refused a read")
        return {"status": "succeeded"}

    monkeypatch.setattr(render, "handle", handle)
    answer = render_handler.handler({"Records": [
        {"messageId": "a", "body": "fine"},
        {"messageId": "b", "body": "boom"},
    ]}, None)

    assert answer["batchItemFailures"] == [{"itemIdentifier": "b"}]


def test_the_worker_drops_a_message_that_will_never_succeed(monkeypatch):
    """A `RenderError` reaching the handler names no job at all — malformed, or
    about a render deleted with its library. Redriving it only fills the
    dead-letter queue with something nobody can act on.

    Note what does NOT reach here: a job that failed permanently. `render.run`
    closed that row `failed` and returned normally, so the message is deleted
    with a record of why behind it.
    """
    from studio_core.handlers.aws.render import render_handler

    def handle(_body):
        raise render.RenderError("names no render")

    monkeypatch.setattr(render, "handle", handle)
    answer = render_handler.handler(
        {"Records": [{"messageId": "a", "body": "{}"}]}, None)

    assert answer["batchItemFailures"] == []
