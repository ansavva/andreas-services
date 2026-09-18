"""`media/faststart.py`: `moov` in front of `mdat`, with the chunk offsets moved.

The MP4s here are built by hand — an `ftyp`, an `mdat` of known bytes, and a
`moov` holding one `stco` (and, in one case, a `co64`) whose entries point
into the `mdat`. That is the whole of what the operation reads and writes,
and building it in fifty bytes is what lets the assertion be exact: every
offset is the old offset plus the size of `moov`, and nothing else moved.
Checked against a real provider clip by hand (ffprobe reports `ftyp moov
mdat`, and the decoded frames hash identically) — that clip is 6 MB and is
not a fixture.
"""
import struct

import pytest

from studio_core.media import faststart
from studio_core.services import catalog, layout
from tests.unit.test_render import queue as _queue

# The moto queue `test_render` owns, re-exported so the worker tests below
# can ask for it without ruff reading each use as a redefinition.
queue = _queue


def atom(kind: bytes, body: bytes, large: bool = False) -> bytes:
    if large:
        return struct.pack(">I4sQ", 1, kind, 16 + len(body)) + body
    return struct.pack(">I4s", 8 + len(body), kind) + body


def stco(offsets: list[int]) -> bytes:
    return atom(b"stco", struct.pack(">II", 0, len(offsets)) + b"".join(
        struct.pack(">I", each) for each in offsets))


def co64(offsets: list[int]) -> bytes:
    return atom(b"co64", struct.pack(">II", 0, len(offsets)) + b"".join(
        struct.pack(">Q", each) for each in offsets))


def moov_around(table: bytes) -> bytes:
    # The nesting `_shift_offsets` walks: moov / trak / mdia / minf / stbl / stco.
    stbl = atom(b"stbl", table)
    return atom(b"moov", atom(b"mvhd", b"\0" * 8) + atom(
        b"trak", atom(b"mdia", atom(b"minf", stbl))))


FTYP = atom(b"ftyp", b"isom\0\0\0\1isom")
MDAT = atom(b"mdat", bytes(range(64)))


def write(path, *parts: bytes) -> str:
    path.write_bytes(b"".join(parts))
    return str(path)


def top_level(path: str) -> list[bytes]:
    return [a.kind for a in faststart._top_level(path)]


def offsets(path: str, kind: bytes) -> list[int]:
    data = open(path, "rb").read()
    at = data.index(kind)
    count = struct.unpack_from(">I", data, at + 8)[0]
    width, fmt = (4, ">I") if kind == b"stco" else (8, ">Q")
    return [struct.unpack_from(fmt, data, at + 12 + i * width)[0] for i in range(count)]


def test_a_provider_shaped_file_is_reordered_and_its_offsets_shifted(tmp_path):
    """`ftyp mdat moov` becomes `ftyp moov mdat`; every chunk offset grows by
    exactly `moov`'s size, because `mdat` moved forward by exactly that."""
    mdat_body_at = len(FTYP) + 8
    moov = moov_around(stco([mdat_body_at, mdat_body_at + 16, mdat_body_at + 40]))
    path = write(tmp_path / "clip.mp4", FTYP, MDAT, moov)
    before = open(path, "rb").read()

    assert faststart.needs_faststart(path)
    assert faststart.faststart(path) is True

    assert top_level(path) == [b"ftyp", b"moov", b"mdat"]
    assert offsets(path, b"stco") == [
        mdat_body_at + len(moov), mdat_body_at + 16 + len(moov), mdat_body_at + 40 + len(moov)]
    after = open(path, "rb").read()
    assert len(after) == len(before)
    # The frames are untouched: the `mdat` bytes are where the new offsets say.
    assert after[after.index(b"mdat") + 4:][:64] == bytes(range(64))
    assert not faststart.needs_faststart(path)


def test_an_already_indexed_file_is_left_alone(tmp_path):
    moov = moov_around(stco([100]))
    path = write(tmp_path / "clip.mp4", FTYP, moov, MDAT)
    before = open(path, "rb").read()
    assert not faststart.needs_faststart(path)
    assert faststart.faststart(path) is False
    assert open(path, "rb").read() == before


def test_a_64bit_table_and_a_large_atom_header_shift_too(tmp_path):
    moov = moov_around(co64([50, 60]))
    path = write(tmp_path / "clip.mp4", FTYP, atom(b"mdat", bytes(64), large=True), moov)
    assert faststart.faststart(path) is True
    assert top_level(path) == [b"ftyp", b"moov", b"mdat"]
    assert offsets(path, b"co64") == [50 + len(moov), 60 + len(moov)]


def test_what_it_refuses_is_left_byte_for_byte(tmp_path):
    """Not an MP4, a compressed `moov`, a 32-bit offset that would overflow:
    each is `False` and the file as it came. A refusal here runs inside a
    callback that has just paid for the clip, so it must never raise."""
    cases = {
        "not-mp4.mp4": b"RIFF....WEBPVP8 " + bytes(40),
        "cmov.mp4": FTYP + MDAT + atom(b"moov", atom(b"cmov", bytes(8))),
        "overflow.mp4": FTYP + MDAT + moov_around(stco([0xFFFFFFF0])),
        "no-moov.mp4": FTYP + MDAT,
        "truncated.mp4": FTYP + struct.pack(">I4s", 400, b"mdat") + bytes(10),
    }
    for name, data in cases.items():
        path = tmp_path / name
        path.write_bytes(data)
        assert faststart.faststart(str(path)) is False, name
        assert path.read_bytes() == data, name


def test_is_mp4_name():
    assert faststart.is_mp4_name("video.mp4")
    assert faststart.is_mp4_name("Clip.MOV")
    assert not faststart.is_mp4_name("frame.png")
    assert not faststart.is_mp4_name("clip.webm")


# ──────────────────────────── the route ────────────────────────────


def _clip_node(api, name="video.mp4"):
    from studio_core.clients.aws import s3
    project = api.post("/api/projects", json={"name": "wall"}).get_json()
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    node = catalog.create_node(pool["node_id"], name, catalog.KIND_FILE)
    moov = moov_around(stco([len(FTYP) + 8]))
    data = FTYP + MDAT + moov
    s3.put_text(node["blob_key"], data, "video/mp4")
    catalog.set_blob(node["node_id"], node["blob_key"], size=len(data), content_type="video/mp4")
    return node, data


def test_the_route_rewrites_in_place_and_is_idempotent(empty_api):
    from studio_core.clients.aws import s3
    node, before = _clip_node(empty_api)

    resp = empty_api.post(f"/api/nodes/{node['node_id']}/faststart")
    assert resp.status_code == 200
    assert resp.get_json()["rewritten"] is True
    after = s3.get_body(node["blob_key"], 10_000)
    assert after != before
    assert len(after) == len(before)
    assert after.index(b"moov") < after.index(b"mdat")
    # Same node, same key; the row re-read off the object.
    assert catalog.node(node["node_id"])["blob_key"] == node["blob_key"]
    assert catalog.node(node["node_id"])["size"] == len(before)

    again = empty_api.post(f"/api/nodes/{node['node_id']}/faststart")
    assert again.get_json()["rewritten"] is False
    assert s3.get_body(node["blob_key"], 10_000) == after


def test_the_route_skips_a_still_without_reading_it(empty_api):
    node, _ = _clip_node(empty_api, name="frame.png")
    resp = empty_api.post(f"/api/nodes/{node['node_id']}/faststart")
    assert resp.status_code == 200
    assert resp.get_json() == {"id": node["node_id"], "rewritten": False}


# ──────────────────────────── at ingest ────────────────────────────


def test_a_clip_is_indexed_before_it_is_stored(empty_api, media_bucket, monkeypatch):
    """The provider's file arrives `mdat` first; the bucket gets `moov` first.
    Same bytes otherwise — the checksum recorded is of what was stored."""
    from studio_core.clients.aws import s3
    from studio_core.services import generate

    project = empty_api.post("/api/projects", json={"name": "wall"}).get_json()
    draft = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": "seedance",
        "model": "bytedance/seedance-2.0",
        "plan": {"version": 1, "origin": "authored", "prompt": "waves", "params": {}},
        "input": {"prompt": "waves"},
    }).get_json()
    empty_api.post(f"/api/runs/{draft['id']}/submit")
    record = catalog.entity(catalog.ENTITY_RUN, draft["id"])

    provider_file = FTYP + MDAT + moov_around(stco([len(FTYP) + 8]))

    def hands_back_the_clip(url, path, *, max_bytes):
        with open(path, "wb") as handle:
            handle.write(provider_file)
        return len(provider_file)

    monkeypatch.setattr(generate.replicate, "download", hands_back_the_clip)
    closed = generate.close_from_prediction(record, {
        "id": record["prediction_id"], "status": "succeeded",
        "output": ["https://fake.invalid/x/0.mp4"]})

    assert closed["status"] == "succeeded"
    stored = s3.get_body(catalog.node(closed["outputs"][0])["blob_key"], 10_000)
    assert stored != provider_file
    assert len(stored) == len(provider_file)
    assert stored.index(b"moov") < stored.index(b"mdat")
    assert catalog.node(closed["outputs"][0])["faststart"] is True


# ──────────────────────────── on the worker ────────────────────────────


def test_the_remote_probe_reads_headers_not_the_clip():
    """`needs_faststart_at` stops at the first of `moov`/`mdat`, a few bytes in."""
    ordered = FTYP + moov_around(stco([len(FTYP) + 8])) + MDAT
    provider = FTYP + atom(b"free", b"\0" * 4) + MDAT + moov_around(stco([len(FTYP) + 8]))
    for data, expected, budget in ((ordered, False, 2), (provider, True, 3)):
        reads = []

        def read(offset, length, data=data):
            reads.append((offset, length))
            return data[offset:offset + length]

        assert faststart.needs_faststart_at(read, len(data)) is expected
        assert len(reads) <= budget
        assert all(length <= 16 for _, length in reads)
    # Not an MP4 at all: no, and nothing blew up.
    assert faststart.needs_faststart_at(lambda o, n: b"PNG\r\n\x1a\n"[o:o + n], 8) is False


def _job(api, node_id):
    from studio_core.services import render
    job = api.post("/api/renders", json={"kind": "faststart", "params": {
        "node": node_id}}).get_json()
    return render.run(job["id"])


def test_the_job_rewrites_a_provider_clip_and_marks_it(empty_api, queue):
    from studio_core.clients.aws import s3
    node, before = _clip_node(empty_api)

    done = _job(empty_api, node["node_id"])
    assert done["status"] == "succeeded", done
    assert done["result"] == {"rewritten": True}
    after = s3.get_body(node["blob_key"], 10_000)
    assert after.index(b"moov") < after.index(b"mdat")
    assert len(after) == len(before)
    row = catalog.node(node["node_id"])
    assert row["faststart"] is True
    assert row["blob_key"] == node["blob_key"]


def test_the_job_marks_an_ordered_clip_without_pulling_it(empty_api, queue, monkeypatch):
    from studio_core.clients.aws import s3
    node, _ = _clip_node(empty_api)
    _job(empty_api, node["node_id"])
    catalog.set_blob(node["node_id"], node["blob_key"], faststart=None)

    monkeypatch.setattr(s3, "download", lambda *_a, **_k: pytest.fail("pulled the clip"))
    done = _job(empty_api, node["node_id"])
    assert done["result"] == {"rewritten": False}
    assert catalog.node(node["node_id"])["faststart"] is True


def test_the_sweep_queues_unmarked_clips_only(empty_api, queue, monkeypatch):
    from studio_core.services import render
    node, _ = _clip_node(empty_api)
    still, _ = _clip_node(empty_api, name="frame.png")
    marked, _ = _clip_node(empty_api, name="done.mp4")
    catalog.set_blob(marked["node_id"], marked["blob_key"], faststart=True)

    resp = empty_api.post("/api/faststarts")
    assert resp.status_code == 202, resp.get_json()
    report = resp.get_json()
    assert report["queued"] == [node["node_id"]]
    assert report["truncated"] is False

    for render_id in _queued(queue):
        render.run(render_id)
    assert empty_api.post("/api/faststarts").get_json()["queued"] == []


def _queued(queue):
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


def test_confirming_an_mp4_upload_queues_a_faststart(empty_api, queue, monkeypatch):
    from studio_core.clients.aws import s3
    from studio_core.services import render
    project = empty_api.post("/api/projects", json={"name": "wall"}).get_json()
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    created = empty_api.post("/api/nodes", json={
        "parent": pool["node_id"], "name": "phone.mp4", "kind": "file"}).get_json()
    s3.put_text(catalog.node(created["id"])["blob_key"], FTYP + MDAT, "video/mp4")

    queued = []
    monkeypatch.setattr(render, "enqueue",
                        lambda lib, kind, params: queued.append((kind, params)))
    assert empty_api.post(f"/api/nodes/{created['id']}/confirm-upload",
                          json={}).status_code == 200
    assert queued == [("poster", {"node": created["id"]}),
                      ("faststart", {"node": created["id"]})]
