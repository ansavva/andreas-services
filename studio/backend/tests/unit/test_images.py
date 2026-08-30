"""`convert` and `crop`: the two operations that are **not** on the render queue.

The issue that moved ffmpeg into the service asked the question directly — *do
`convert` and `crop` belong on the queue at all?* — and the answer these routes
are is no. Both are sub-second on one image, so an enqueue plus two polls costs
more wall clock than the work, and Pillow is ~3 MB where `imageio-ffmpeg` is ~80.
So the API image carries Pillow and the render image carries both.

What is under test here is the addressing, the cap and the destination.
`media/imaging.py` is the arithmetic and is covered in `test_media.py`.
"""

import io

from PIL import Image

from studio_core.services import catalog, layout


def _project(api, slug="rooftop-teaser"):
    return api.post("/api/projects", json={"slug": slug}).get_json()


def _image(api, project, name="wide.png", width=400, height=600, mode="RGB"):
    from studio_core.clients.aws import s3

    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    node = catalog.create_node(pool["node_id"], name, catalog.KIND_FILE)
    buffer = io.BytesIO()
    Image.new(mode, (width, height), (10, 120, 200)).save(
        buffer, "PNG" if name.endswith(".png") else "WEBP")
    s3.put_text(node["blob_key"], buffer.getvalue(), "image/png")
    catalog.set_blob(node["node_id"], node["blob_key"],
                     size=len(buffer.getvalue()), content_type="image/png")
    return node


def _bytes(node_id):
    from studio_core.clients.aws import s3

    return s3.get_body(catalog.node(node_id)["blob_key"], 10_000_000)


# ──────────────────────────── convert ────────────────────────────


def test_converting_writes_a_new_node_and_leaves_the_source_alone(empty_api):
    """A run's output is append-only history, so it is copied, never re-encoded
    in place."""
    project = _project(empty_api)
    source = _image(empty_api, project)
    before = _bytes(source["node_id"])

    resp = empty_api.post("/api/images/convert", json={
        "node": source["node_id"], "to": "jpg"})

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["image"]["node"] != source["node_id"]
    assert body["image"]["name"] == "wide.jpg"
    assert _bytes(source["node_id"]) == before
    assert Image.open(io.BytesIO(_bytes(body["image"]["node"]))).format == "JPEG"


def test_a_conversion_lands_beside_its_source_unless_a_destination_is_named(empty_api):
    """Converting a frame in place beside itself is the common case and needs no
    folder to be named."""
    project = _project(empty_api)
    source = _image(empty_api, project)

    body = empty_api.post("/api/images/convert", json={
        "node": source["node_id"], "to": "jpg"}).get_json()

    assert catalog.node(body["image"]["node"])["parent_id"] == source["parent_id"]


def test_a_second_conversion_lands_beside_the_first_rather_than_409ing(empty_api):
    """**`create_numbered`, and it is a retry property rather than a nicety.**

    A clash would be a `ConflictError`, so a caller repeating a conversion — which
    `--for` documents as safe — would get a 409 for a file it does not care about.
    Nothing is silently destroyed either, which an overwrite would be.
    """
    project = _project(empty_api)
    source = _image(empty_api, project)

    names = [empty_api.post("/api/images/convert", json={
        "node": source["node_id"], "to": "jpg"}).get_json()["image"]["name"]
        for _ in range(2)]

    assert names == ["wide.jpg", "wide (2).jpg"]


def test_an_explicit_destination_is_used_and_checked(empty_api):
    project = _project(empty_api)
    source = _image(empty_api, project)
    scenes = layout.folder_under(project["root"], layout.SCENE_PARENT)

    body = empty_api.post("/api/images/convert", json={
        "node": source["node_id"], "to": "png", "dest": scenes["node_id"],
        "name": "start.png"}).get_json()

    assert catalog.node(body["image"]["node"])["parent_id"] == scenes["node_id"]
    assert catalog.node(body["image"]["node"])["name"] == "start.png"


def test_a_destination_that_is_a_file_is_refused(empty_api):
    project = _project(empty_api)
    source = _image(empty_api, project)

    resp = empty_api.post("/api/images/convert", json={
        "node": source["node_id"], "to": "png", "dest": source["node_id"]})

    assert resp.status_code == 400
    assert "not a folder" in resp.get_json()["error"]


def test_a_source_that_is_not_a_file_is_refused(empty_api):
    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)

    resp = empty_api.post("/api/images/convert", json={
        "node": pool["node_id"], "to": "png"})

    assert resp.status_code == 400
    assert "not a file" in resp.get_json()["error"]


def test_a_source_larger_than_the_cap_costs_one_catalog_read_and_no_download(
        empty_api, monkeypatch):
    """**The cap is about memory, not policy.** This route runs in the API image
    at 512 MB and Pillow decodes to raw pixels; anything larger belongs on the
    render queue, where there is a real disk."""
    monkeypatch.setenv("STUDIO_MAX_IMAGE_BYTES", "10")
    project = _project(empty_api)
    source = _image(empty_api, project)

    resp = empty_api.post("/api/images/convert", json={
        "node": source["node_id"], "to": "jpg"})

    assert resp.status_code == 400
    assert "render queue" in resp.get_json()["error"]


def test_a_format_nothing_can_write_is_refused_by_name(empty_api):
    project = _project(empty_api)
    source = _image(empty_api, project)

    resp = empty_api.post("/api/images/convert", json={
        "node": source["node_id"], "to": "tiff"})

    assert resp.status_code == 400
    assert "tiff" in resp.get_json()["error"]


def test_a_source_pillow_cannot_read_is_a_400_and_not_a_500(empty_api):
    """`crop --run` against a run whose only output is a video is the way here."""
    from studio_core.clients.aws import s3

    project = _project(empty_api)
    pool = layout.folder_under(project["root"], layout.INPUT_FOLDER)
    node = catalog.create_node(pool["node_id"], "clip.mp4", catalog.KIND_FILE)
    s3.put_text(node["blob_key"], b"\x00\x00\x00\x18ftypmp42", "video/mp4")
    catalog.set_blob(node["node_id"], node["blob_key"], size=8,
                     content_type="video/mp4")

    resp = empty_api.post("/api/images/convert", json={
        "node": node["node_id"], "to": "png"})

    assert resp.status_code == 400
    assert "not an image" in resp.get_json()["error"]


# ──────────────────────────── crop ────────────────────────────


def test_cropping_reports_the_box_it_cut_and_the_size_it_produced(empty_api):
    project = _project(empty_api)
    source = _image(empty_api, project)

    body = empty_api.post("/api/images/crop", json={
        "node": source["node_id"], "box": "100,50,300,550"}).get_json()

    assert body["box"] == [100, 50, 300, 550]
    assert body["clamped"] is False
    assert (body["width"], body["height"]) == (200, 500)
    assert Image.open(io.BytesIO(_bytes(body["image"]["node"]))).size == (200, 500)


def test_a_clamped_box_says_so_and_says_what_was_asked_for(empty_api):
    """**A silent clamp is a box that is not the box anybody stated**, and the
    route is the only side that has read the image's dimensions."""
    project = _project(empty_api)
    source = _image(empty_api, project)

    body = empty_api.post("/api/images/crop", json={
        "node": source["node_id"], "box": "-10,0,4000,600"}).get_json()

    assert body["clamped"] is True
    assert body["requested"] == [-10, 0, 4000, 600]
    assert body["box"] == [0, 0, 400, 600]


def test_a_box_that_misses_the_image_is_refused(empty_api):
    project = _project(empty_api)
    source = _image(empty_api, project)

    resp = empty_api.post("/api/images/crop", json={
        "node": source["node_id"], "box": "900,900,1000,1000"})

    assert resp.status_code == 400
    assert "entirely outside" in resp.get_json()["error"]


def test_a_box_given_as_a_list_is_accepted_too(empty_api):
    """The CLI sends a string because that is what a person types; the SPA has
    four numbers. Both spellings, one route."""
    project = _project(empty_api)
    source = _image(empty_api, project)

    body = empty_api.post("/api/images/crop", json={
        "node": source["node_id"], "box": [0, 0, 100, 100]}).get_json()

    assert body["box"] == [0, 0, 100, 100]


def test_the_crop_keeps_the_source_format_unless_told_otherwise(empty_api):
    project = _project(empty_api)
    source = _image(empty_api, project)

    body = empty_api.post("/api/images/crop", json={
        "node": source["node_id"], "box": "0,0,100,100"}).get_json()

    # `wide (2).png`, not `wide.png`: the crop lands beside its source, which
    # is already called `wide.png`, and `create_numbered` never overwrites. The
    # extension is what this test is about.
    assert body["image"]["name"] == "wide (2).png"
    assert Image.open(io.BytesIO(_bytes(body["image"]["node"]))).format == "PNG"
