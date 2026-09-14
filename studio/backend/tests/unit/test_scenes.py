"""Scenes: a named, ordered series of runs.

**A scene used to be a data model of its own** — a plan of `SHOT#` rows with
panels, prompts and the run each one rendered into — and 700 lines of storyboard
service over it. Every one of those things was already a run. So a scene is now
two facts and a name, and this file tests exactly those:

| Fact | Where | Edge beside it |
|---|---|---|
| a run belongs to a scene | `scene` on the run | `RUN#<run>` / `SCENE#<scene>` |
| the cut, in order | `runs` on the scene | `SCENE#<scene>` / `RUN#<run>` |

The cut may name a run that has not rendered yet — the cut IS the plan — and
naming a run in it puts the run into the scene. A run belongs to at most one.

Stitching is a render job (`test_render.py`). `POST /api/scenes/<id>/output`
is still here and still tested: it signs an upload for a cut made somewhere
else, which is what a client that already holds the bytes wants.
"""

from studio_core import config
from studio_core.services import catalog, layout


def _item(client, pk, sk):
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _project(api, name="rooftop-teaser"):
    return api.post("/api/projects", json={"name": name}).get_json()


def _scene(api, project, name="stadium-encounter", **body):
    resp = api.post("/api/scenes", json={"project": project["id"], "name": name, **body})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _run(api, project, kind="video", **body):
    resp = api.post(
        "/api/runs",
        json={"project": project["id"], "kind": kind, "engine": "kling",
              "model": "kwaivgi/kling-v3-omni-video", **body},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _output(api, run, name="clip.mp4"):
    return api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": name, "size": 10, "content_type": "video/mp4"},
    ).get_json()["node"]


def _uploaded(api, parent_id, name):
    node = api.post("/api/nodes", json={"parent": parent_id, "name": name,
                                        "kind": "file"}).get_json()
    record = catalog.node(node["id"])
    return catalog.set_blob(node["id"], record["blob_key"], size=4,
                            content_type="image/png")


def _child(parent_id, name):
    return layout.folder_under(parent_id, name)


# ──────────────────────────── the record ────────────────────────────


def test_creating_a_scene_writes_the_record_listing_row_and_folder(empty_api, catalog_table):
    project = _project(empty_api)

    scene = _scene(empty_api, project)

    assert _item(catalog_table, f"SCENE#{scene['id']}", "META")["status"]["S"] == "planned"
    assert [row["id"] for row in catalog.project_entities(project["id"], "scene")] == [
        scene["id"]
    ]
    assert catalog.node(scene["folder"])["parent_id"] == _child(
        project["root"], layout.SCENE_PARENT
    )["node_id"]
    assert scene["runs"] == [] and scene["frames"] == [] and scene["movies"] == []


def test_a_scene_listing_row_carries_its_name(empty_api):
    """A row without one cannot be DRAWN, and a list of UUIDs is unreadable."""
    project = _project(empty_api)
    _scene(empty_api, project, name="Opening")

    (row,) = empty_api.get(f"/api/scenes?project={project['id']}").get_json()["scenes"]
    assert row["name"] == "Opening" and row["status"] == "planned"


def test_a_scene_holds_no_plan_rows(empty_api, catalog_table):
    """**The point of the rework.** The partition is the record and its edges;
    nothing else lives under it, because everything a shot held is a run."""
    project = _project(empty_api)
    run = _run(empty_api, project)
    scene = _scene(empty_api, project, runs=[run["id"]])

    rows = catalog_table.query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": f"SCENE#{scene['id']}"}},
    )["Items"]
    assert sorted(item["sk"]["S"] for item in rows) == ["META", f"RUN#{run['id']}"]


# ──────────────────────────── membership ────────────────────────────


def test_a_run_made_for_a_scene_names_it_and_is_listed_under_it(empty_api):
    """`scene` is a field on the run, with an edge beside it, and it is
    projected onto the listing row so `?scene=` is one range query narrowed."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    still = _run(empty_api, project, kind="image", scene=scene["id"])
    _run(empty_api, project, kind="image")

    assert still["scene"] == scene["id"]
    assert empty_api.get(f"/api/runs/{still['id']}").get_json()["scene"] == scene["id"]
    assert catalog.linked(scene["id"], catalog.ENTITY_RUN) == [still["id"]]
    listed = empty_api.get(
        f"/api/runs?project={project['id']}&scene={scene['id']}&include=drafts"
    ).get_json()["runs"]
    assert [row["id"] for row in listed] == [still["id"]]
    assert listed[0]["scene"] == scene["id"]


def test_a_feed_row_says_which_scene_a_run_is_in(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    run = _run(empty_api, project, scene=scene["id"])

    (row,) = empty_api.get(
        f"/api/runs?project={project['id']}&scene={scene['id']}&include=drafts&view=feed"
    ).get_json()["runs"]
    assert row["id"] == run["id"] and row["scene"] == scene["id"]


def test_a_run_with_no_scene_says_none_rather_than_omitting_the_field(empty_api):
    project = _project(empty_api)
    run = _run(empty_api, project)

    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["scene"] is None


def test_a_run_can_be_put_into_a_scene_later_and_taken_out_again(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    run = _run(empty_api, project)

    resp = empty_api.patch(f"/api/runs/{run['id']}", json={"scene": scene["id"]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert catalog.linked(scene["id"], catalog.ENTITY_RUN) == [run["id"]]
    (row,) = empty_api.get(f"/api/runs?project={project['id']}&include=drafts").get_json()["runs"]
    assert row["scene"] == scene["id"]

    empty_api.patch(f"/api/runs/{run['id']}", json={"scene": None})
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["scene"] is None
    assert catalog.linked(scene["id"], catalog.ENTITY_RUN) == []
    (row,) = empty_api.get(f"/api/runs?project={project['id']}&include=drafts").get_json()["runs"]
    assert "scene" not in row


def test_moving_a_run_between_scenes_moves_the_edge(empty_api):
    project = _project(empty_api)
    first = _scene(empty_api, project, name="one")
    second = _scene(empty_api, project, name="two")
    run = _run(empty_api, project, scene=first["id"])

    empty_api.patch(f"/api/runs/{run['id']}", json={"scene": second["id"]})

    assert catalog.linked(first["id"], catalog.ENTITY_RUN) == []
    assert catalog.linked(second["id"], catalog.ENTITY_RUN) == [run["id"]]


def test_a_run_cannot_name_a_scene_in_another_project(empty_api):
    """A run and its scene share a project by construction; nothing downstream
    checks it again, so the one write that could break it refuses."""
    here = _project(empty_api, name="here")
    there = _project(empty_api, name="there")
    scene = _scene(empty_api, there)

    resp = empty_api.post("/api/runs", json={
        "project": here["id"], "kind": "video", "model": "m", "scene": scene["id"]})
    assert resp.status_code == 400
    assert "not in this project" in resp.get_json()["error"]


# ──────────────────────────── the cut ────────────────────────────


def test_the_cut_is_an_ordered_list_answered_as_rows(empty_api):
    """`GET` and the write that changes the list answer in one shape, for the
    reason `test_edges` gives: a client that merged strings over rows read empty."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    first, second = _run(empty_api, project), _run(empty_api, project)
    clip = _output(empty_api, second)

    written = empty_api.patch(f"/api/scenes/{scene['id']}/runs",
                              json={"runs": [second["id"], first["id"]]}).get_json()
    read = empty_api.get(f"/api/scenes/{scene['id']}").get_json()

    assert written["runs"] == read["runs"]
    assert [row["id"] for row in read["runs"]] == [second["id"], first["id"]]
    # A rendered run draws its clip; one that has not rendered yet draws as a
    # row with nothing in it, which is what a planned cut looks like.
    assert read["runs"][0]["output"]["node"] == clip and read["runs"][0]["output"]["url"]
    assert read["runs"][1]["output"] is None
    assert read["runs"][0]["kind"] == "video" and read["runs"][0]["status"] == "draft"


def test_naming_a_run_in_the_cut_puts_it_into_the_scene(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    run = _run(empty_api, project)

    empty_api.patch(f"/api/scenes/{scene['id']}/runs", json={"runs": [run["id"]]})

    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["scene"] == scene["id"]
    assert catalog.linked(scene["id"], catalog.ENTITY_RUN) == [run["id"]]
    assert catalog.links(scene["id"], catalog.ENTITY_RUN) == [run["id"]]


def test_a_scene_can_be_created_with_its_cut(empty_api):
    project = _project(empty_api)
    run = _run(empty_api, project)

    scene = _scene(empty_api, project, runs=[run["id"]])

    assert [row["id"] for row in scene["runs"]] == [run["id"]]
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["scene"] == scene["id"]


def test_dropping_a_run_from_the_cut_keeps_it_in_the_scene(empty_api):
    """The cut is the order; membership is the run's. Reordering a cut is not
    a decision about where a run lives."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    first, second = _run(empty_api, project), _run(empty_api, project)
    empty_api.patch(f"/api/scenes/{scene['id']}/runs",
                    json={"runs": [first["id"], second["id"]]})

    empty_api.patch(f"/api/scenes/{scene['id']}/runs", json={"runs": [second["id"]]})

    assert catalog.links(scene["id"], catalog.ENTITY_RUN) == [second["id"]]
    assert empty_api.get(f"/api/runs/{first['id']}").get_json()["scene"] == scene["id"]


def test_a_reprise_is_legal_and_the_edge_rows_deduplicate(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    run = _run(empty_api, project)

    body = empty_api.patch(f"/api/scenes/{scene['id']}/runs",
                           json={"runs": [run["id"], run["id"]]}).get_json()

    assert [row["id"] for row in body["runs"]] == [run["id"], run["id"]]
    assert catalog.links(scene["id"], catalog.ENTITY_RUN) == [run["id"]]


def test_a_still_cannot_be_cut(empty_api):
    """The cut is what `assemble` walks; a still there is a stitch that fails at
    the far end of a queue rather than at the request that caused it."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    still = _run(empty_api, project, kind="image")

    resp = empty_api.patch(f"/api/scenes/{scene['id']}/runs", json={"runs": [still["id"]]})

    assert resp.status_code == 400
    assert "only a video can be cut" in resp.get_json()["error"]
    assert empty_api.get(f"/api/runs/{still['id']}").get_json()["scene"] is None


def test_a_run_in_another_scene_cannot_be_cut_here(empty_api):
    """A run belongs to at most one scene, and moving it is a decision to make
    on the run — not a side effect of ordering somebody else's cut."""
    project = _project(empty_api)
    theirs = _scene(empty_api, project, name="theirs")
    mine = _scene(empty_api, project, name="mine")
    run = _run(empty_api, project, scene=theirs["id"])

    resp = empty_api.patch(f"/api/scenes/{mine['id']}/runs", json={"runs": [run["id"]]})

    assert resp.status_code == 400
    assert theirs["id"] in resp.get_json()["error"]
    assert catalog.links(mine["id"], catalog.ENTITY_RUN) == []


def test_a_cut_cannot_name_a_run_from_another_project(empty_api):
    here = _project(empty_api, name="here")
    there = _project(empty_api, name="there")
    scene = _scene(empty_api, here)
    run = _run(empty_api, there)

    resp = empty_api.patch(f"/api/scenes/{scene['id']}/runs", json={"runs": [run["id"]]})

    assert resp.status_code == 400
    assert "not in this project" in resp.get_json()["error"]


def test_runs_must_be_a_list_of_ids(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    assert empty_api.patch(f"/api/scenes/{scene['id']}/runs",
                           json={"runs": "run-x"}).status_code == 400
    assert empty_api.patch(f"/api/scenes/{scene['id']}/runs",
                           json={"runs": [{"id": "run-x"}]}).status_code == 400


def test_the_scenes_frames_are_the_first_frame_each_cut_run_opened_on(empty_api):
    """Derived from the cut's `start` sends on read, in cut order — the seed
    shot 1 started from and every handoff since. It was a `chains/<scene>.json`
    kept in step by hand, and then a `scene_frames` over shot rows; both
    drifted from the scene they described."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    pool = _child(project["root"], layout.INPUT_FOLDER)["node_id"]
    seed = _uploaded(empty_api, pool, "seed.png")["node_id"]
    handoff = _uploaded(empty_api, pool, "handoff.png")["node_id"]
    reference = _uploaded(empty_api, pool, "ref.png")["node_id"]
    first = _run(empty_api, project, sends=[
        {"field": "start_image", "role": "start", "node": seed},
        {"field": "reference_images", "role": "reference", "node": reference}])
    second = _run(empty_api, project, sends=[
        {"field": "start_image", "role": "start", "node": handoff}])
    unstarted = _run(empty_api, project)

    empty_api.patch(f"/api/scenes/{scene['id']}/runs",
                    json={"runs": [first["id"], second["id"], unstarted["id"]]})

    frames = empty_api.get(f"/api/scenes/{scene['id']}").get_json()["frames"]
    assert [frame["node"] for frame in frames] == [seed, handoff]
    assert all(frame["url"] for frame in frames)


# ──────────────────────────── deletion ────────────────────────────


def test_deleting_a_scene_leaves_its_runs_and_clears_their_scene(empty_api, catalog_table):
    """A run is the record; the scene was a grouping of them. The attribute is
    a field on another record, which a partition delete cannot reach, so the
    route clears it — nothing may point at an id that is gone."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    run = _run(empty_api, project, scene=scene["id"])
    empty_api.patch(f"/api/scenes/{scene['id']}/runs", json={"runs": [run["id"]]})

    resp = empty_api.delete(f"/api/scenes/{scene['id']}")

    assert resp.status_code == 200
    assert _item(catalog_table, f"SCENE#{scene['id']}", "META") is None
    fetched = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert fetched["status"] == "draft" and fetched["scene"] is None
    assert catalog.links(run["id"], catalog.ENTITY_SCENE) == []
    assert catalog.linked(scene["id"], catalog.ENTITY_RUN) == []
    assert catalog.entity(catalog.ENTITY_PROJECT, project["id"])["counts"]["scenes"] == 0


def test_deleting_a_run_takes_it_out_of_the_cut(empty_api):
    """A cut naming a deleted run would draw an empty row and refuse to
    assemble for a reason nobody can act on."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    gone, kept = _run(empty_api, project), _run(empty_api, project)
    empty_api.patch(f"/api/scenes/{scene['id']}/runs",
                    json={"runs": [gone["id"], kept["id"]]})

    assert empty_api.delete(f"/api/runs/{gone['id']}").status_code == 200

    fetched = empty_api.get(f"/api/scenes/{scene['id']}").get_json()
    assert [row["id"] for row in fetched["runs"]] == [kept["id"]]
    assert catalog.links(scene["id"], catalog.ENTITY_RUN) == [kept["id"]]


def test_deleting_a_scene_drops_the_edge_the_movie_held_to_it(empty_api):
    """`delete_entity` used to clear a scene's run holders and not its movie
    holders, so a movie kept an edge to a scene that was gone."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    movie = empty_api.post("/api/movies", json={
        "project": project["id"], "name": "cut", "scenes": [scene["id"]]}).get_json()

    empty_api.delete(f"/api/scenes/{scene['id']}")

    assert catalog.links(movie["id"], catalog.ENTITY_SCENE) == []


# ──────────────────────────── the output ────────────────────────────


def test_a_scene_output_is_one_take_and_becomes_the_thumbnail(empty_api):
    """A scene *is* one take — the runs that made it hold their own outputs."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    resp = empty_api.post(
        f"/api/scenes/{scene['id']}/output",
        json={"name": "stadium.mp4", "size": 100, "content_type": "video/mp4"},
    )

    assert resp.status_code == 201
    node = resp.get_json()["node"]
    cut = empty_api.get(f"/api/scenes/{scene['id']}").get_json()["output"]
    assert cut["node"] == node
    assert cut["name"] == "stadium.mp4"
    assert cut["url"]
    assert catalog.project_entities(project["id"], "scene")[0]["thumb"] == node
    assert catalog.node(node)["blob_key"] == f"projects/{project['id']}/{node}.mp4"


def test_a_cut_is_reported_as_something_a_page_can_draw(empty_api):
    """Stored as a pointer, reported as an asset — the probe the worker records
    travels alongside and is neither read nor validated here."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    node = empty_api.post(
        f"/api/scenes/{scene['id']}/output",
        json={"name": "stadium.mp4", "size": 100, "content_type": "video/mp4"},
    ).get_json()["node"]

    empty_api.patch(
        f"/api/scenes/{scene['id']}",
        json={"output": {"node": node, "duration": 12.5, "width": 1920}},
    )

    cut = empty_api.get(f"/api/scenes/{scene['id']}").get_json()["output"]
    assert cut["node"] == node
    assert cut["name"] == "stadium.mp4"
    assert cut["url"]
    assert cut["duration"] == 12.5 and cut["width"] == 1920


def test_a_cut_written_before_it_was_a_pointer_still_reads(empty_api, catalog_table):
    """Rows written before `output` was a pointer hold a bare node id, and are
    normalised on the way out rather than migrated."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    node = empty_api.post(
        f"/api/scenes/{scene['id']}/output",
        json={"name": "stadium.mp4", "size": 100, "content_type": "video/mp4"},
    ).get_json()["node"]

    catalog_table.update_item(
        TableName=config.catalog_table(),
        Key={"pk": {"S": f"SCENE#{scene['id']}"}, "sk": {"S": "META"}},
        UpdateExpression="SET #o = :node",
        ExpressionAttributeNames={"#o": "output"},
        ExpressionAttributeValues={":node": {"S": node}},
    )

    cut = empty_api.get(f"/api/scenes/{scene['id']}").get_json()["output"]
    assert cut["node"] == node
    assert cut["url"]


def test_a_cut_recorded_by_a_client_carries_everything_it_reports(empty_api):
    """`characters`, `stitch`, `output` and `assembled` — the fields a cut made
    elsewhere sends, and which this route once dropped after the upload."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    node = empty_api.post(
        f"/api/scenes/{scene['id']}/output",
        json={"name": "stadium.mp4", "size": 100, "content_type": "video/mp4"},
    ).get_json()["node"]

    resp = empty_api.patch(
        f"/api/scenes/{scene['id']}",
        json={
            "characters": ["char-1"],
            "stitch": {"tool": "ffmpeg", "shots": 3},
            "output": {"node": node, "duration": 12.5},
            "assembled": "2026-08-25T10:00:00Z",
            "status": "assembled",
        },
    )

    assert resp.status_code == 200
    body = empty_api.get(f"/api/scenes/{scene['id']}").get_json()
    assert body["characters"] == ["char-1"]
    assert body["stitch"] == {"tool": "ffmpeg", "shots": 3}
    assert body["assembled"] == "2026-08-25T10:00:00Z"
    assert body["output"]["node"] == node
    assert body["status"] == "assembled"


def test_a_patch_that_changes_nothing_is_refused(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    resp = empty_api.patch(f"/api/scenes/{scene['id']}", json={"setting": "a room"})

    assert resp.status_code == 400


def test_re_cutting_a_scene_keeps_the_cut_it_displaced(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    # A NEW name per cut, which is what the worker sends: `create_node` dedupes
    # on name, so re-cutting to the same filename would hand back the same node
    # and there would be no displaced take to keep.
    first = empty_api.post(
        f"/api/scenes/{scene['id']}/output",
        json={"size": 10, "content_type": "video/mp4", "name": "cut.mp4"},
    ).get_json()["node"]
    empty_api.post(
        f"/api/scenes/{scene['id']}/output",
        json={"size": 10, "content_type": "video/mp4", "name": "cut-2.mp4"},
    )

    fetched = empty_api.get(f"/api/scenes/{scene['id']}").get_json()
    assert fetched["output"]["node"] != first
    assert [cut["node"] for cut in fetched["cuts"]] == [first]


def test_a_kept_cut_comes_back_drawable(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    for name in ("cut.mp4", "cut-2.mp4"):
        empty_api.post(
            f"/api/scenes/{scene['id']}/output",
            json={"size": 10, "content_type": "video/mp4", "name": name},
        )

    cut = empty_api.get(f"/api/scenes/{scene['id']}").get_json()["cuts"][0]
    assert cut["node"] and "url" in cut


def test_an_output_needs_a_size_and_a_content_type(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    assert empty_api.post(f"/api/scenes/{scene['id']}/output",
                          json={"name": "a.mp4", "content_type": "video/mp4"}).status_code == 400
    assert empty_api.post(f"/api/scenes/{scene['id']}/output",
                          json={"name": "a.mp4", "size": 1}).status_code == 400
