"""Scenes and movies: the two tiers above a run, and the plan that is rows.

A scene is shots stitched into one continuous take; a movie is scenes cut into
one piece. Both are the same envelope-plus-blob split a run is, with one addition
that is the whole reason a scene is not just a folder of runs: **the plan**.
`SCENE#<id>` / `SHOT#<shot_id>` is one row per planned shot, carrying `order`,
`prompt`, and the `run` and `panel` that rendered it.

**The one non-obvious rule in the module is that a plan revision merges onto
rendered work rather than replacing it.** Rewriting prompts is what a person does
to a plan; `run` and `panel` are what a render put there, and a plain replace
would silently discard them — which would read as "the render vanished" long
after the request that caused it.

**Stitching stays in the CLI.** `ffmpeg` ships in the pipeline wheel and the
Lambda has none, so `assemble` downloads, stitches locally, uploads through
`POST /api/scenes/<id>/output` and patches the record. The API owns the record,
not the encode — which is why there is an upload route here and no encode.
"""

from studio_core import config
from studio_core.services import catalog, layout


def _item(client, pk, sk):
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _project(api, slug="rooftop-teaser"):
    return api.post("/api/projects", json={"slug": slug}).get_json()


def _scene(api, project, slug="stadium-encounter", shots=None):
    resp = api.post(
        "/api/scenes",
        json={"project": project["id"], "slug": slug, "title": "Stadium", "shots": shots or []},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _movie(api, project, slug="launch-cut", **body):
    resp = api.post("/api/movies", json={"project": project["id"], "slug": slug, **body})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _child(parent_id, name):
    return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])


# ──────────────────────────── scenes ────────────────────────────


def test_creating_a_scene_writes_the_record_listing_row_folder_and_shots(empty_api, catalog_table):
    """The envelope and the plan, and the plan is rows rather than a document.

    `scene.json` was a document nobody could parse, so a scene could be shown as
    a folder and nothing else.
    """
    project = _project(empty_api)

    scene = _scene(empty_api, project, shots=[{"prompt": "wide"}, {"prompt": "close"}])

    assert _item(catalog_table, f"SCENE#{scene['id']}", "META")["status"]["S"] == "planned"
    assert [row["id"] for row in catalog.project_entities(project["id"], "scene")] == [
        scene["id"]
    ]
    assert catalog.node(scene["folder"])["parent_id"] == _child(
        project["root"], layout.SCENE_PARENT
    )["node_id"]
    assert [shot["prompt"] for shot in scene["shots"]] == ["wide", "close"]


def test_shots_come_back_in_order(empty_api):
    """`order` is gapped by ten so a plan can be reordered without renumbering it."""
    project = _project(empty_api)
    scene = _scene(empty_api, project, shots=[{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}])

    fetched = empty_api.get(f"/api/scenes/{scene['id']}").get_json()

    assert [shot["prompt"] for shot in fetched["shots"]] == ["a", "b", "c"]
    assert [shot["order"] for shot in fetched["shots"]] == [10, 20, 30]


def test_a_plan_revision_keeps_the_work_already_rendered(empty_api):
    """**The rule this module exists to hold.**

    A shot matched by id keeps its `run` and `panel` unless the request names
    them, so rewriting a prompt does not throw away the render that answered the
    old one. A plain replace would, and would do it silently — the plan would look
    right and the scene would have lost its footage.
    """
    project = _project(empty_api)
    scene = _scene(empty_api, project, shots=[{"prompt": "wide"}])
    shot_id = scene["shots"][0]["id"]
    empty_api.patch(
        f"/api/scenes/{scene['id']}/shots/{shot_id}",
        json={"run": "run-abc", "panel": 2},
    )

    resp = empty_api.patch(
        f"/api/scenes/{scene['id']}/shots",
        json={"shots": [{"id": shot_id, "prompt": "wider"}]},
    )

    assert resp.status_code == 200
    shot = resp.get_json()["shots"][0]
    assert shot["prompt"] == "wider"
    assert (shot["run"], shot["panel"]) == ("run-abc", 2)


def test_a_plan_revision_drops_shots_it_omits_and_appends_new_ones(empty_api):
    """A revision is the whole plan, so a shot left out of it is a shot removed.

    That is the half a merge could get wrong in the other direction: keeping
    everything would make a plan impossible to shorten.
    """
    project = _project(empty_api)
    scene = _scene(empty_api, project, shots=[{"prompt": "a"}, {"prompt": "b"}])
    keep = scene["shots"][0]["id"]

    body = empty_api.patch(
        f"/api/scenes/{scene['id']}/shots",
        json={"shots": [{"id": keep, "prompt": "a"}, {"prompt": "c"}]},
    ).get_json()

    assert [shot["prompt"] for shot in body["shots"]] == ["a", "c"]
    assert len(catalog.shots(scene["id"])) == 2


def test_one_shot_can_be_patched_on_its_own(empty_api):
    """What a render reports when it finishes: which run produced which shot."""
    project = _project(empty_api)
    scene = _scene(empty_api, project, shots=[{"prompt": "wide"}])

    resp = empty_api.patch(
        f"/api/scenes/{scene['id']}/shots/{scene['shots'][0]['id']}",
        json={"run": "run-xyz", "panel": 1},
    )

    assert resp.status_code == 200
    assert catalog.shots(scene["id"])[0]["run"] == "run-xyz"


def test_a_scene_output_is_one_take_and_becomes_the_thumbnail(empty_api):
    """A scene *is* one take — the shots that made it are rows naming their runs.

    So there is one `output`, not a list, and each shot's own outputs live on the
    run that rendered it.
    """
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
    """The cut is stored as a pointer and reported as an asset.

    It used to be reported as the pointer, and both readers broke on it
    differently: the SPA drew a `<video>` with no `src`, and the CLI's
    `scene_output_node` did `(output or {}).get("node")` against a bare string.

    The probe `assemble` records travels alongside and is neither read nor
    validated here — `ffmpeg` ships in the CLI's wheel and the Lambda has none.
    """
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
    """Every row written up to this change holds a bare node id.

    Normalised on the way out rather than migrated: there was one writer of the
    old shape and it now writes the new one.
    """
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


def test_assembling_a_scene_records_everything_it_reports(empty_api):
    """`assemble` sends four fields this route used to drop.

    It allowlisted `title`, `status` and `error`, so a PATCH carrying only
    `characters`, `stitch`, `output` and `assembled` matched nothing, fell
    through to `nothing to change` and 400ed — *after* the take had been encoded
    locally and uploaded. The cut sat in the bucket and the scene never learned
    it had one.
    """
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
        },
    )

    assert resp.status_code == 200
    body = empty_api.get(f"/api/scenes/{scene['id']}").get_json()
    assert body["characters"] == ["char-1"]
    assert body["stitch"] == {"tool": "ffmpeg", "shots": 3}
    assert body["assembled"] == "2026-08-25T10:00:00Z"
    assert body["output"]["node"] == node


def test_deleting_a_scene_removes_its_shots(empty_api, catalog_table):
    """A `SHOT#` row outliving its scene is a row nothing can reach."""
    project = _project(empty_api)
    scene = _scene(empty_api, project, shots=[{"prompt": "a"}])
    shot_id = scene["shots"][0]["id"]

    assert empty_api.delete(f"/api/scenes/{scene['id']}").status_code == 200

    assert _item(catalog_table, f"SCENE#{scene['id']}", f"SHOT#{shot_id}") is None
    assert catalog.project_entities(project["id"], "scene") == []


# ──────────────────────────── movies ────────────────────────────


def test_creating_a_movie_records_the_cut(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    movie = _movie(empty_api, project, scenes=[scene["id"]], title="Launch")

    assert movie["scenes"] == [scene["id"]]
    assert [row["id"] for row in catalog.project_entities(project["id"], "movie")] == [
        movie["id"]
    ]


def test_a_movie_resolves_the_scenes_it_names(empty_api):
    """The list is ids; the read is what a person can act on."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    movie = _movie(empty_api, project, scenes=[scene["id"]])

    body = empty_api.get(f"/api/movies/{movie['id']}").get_json()

    assert body["scenes"] == [
        {
            "id": scene["id"],
            "slug": "stadium-encounter",
            "title": "Stadium",
            "status": "planned",
            "output": None,
            "thumb": None,
        }
    ]


def test_a_movies_scene_rows_carry_what_it_takes_to_draw_one(empty_api):
    """A row was `{id, slug, status, output}`, and the SPA draws `title` and `thumb`.

    So the cut list showed every scene by its slug behind an empty square. A
    scene's thumbnail is its own cut, which is why it is derived from `output`
    rather than read off a listing row — the listing row belongs to the project,
    and this query goes to the scene records.
    """
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    node = empty_api.post(
        f"/api/scenes/{scene['id']}/output",
        json={"name": "stadium.mp4", "size": 100, "content_type": "video/mp4"},
    ).get_json()["node"]
    movie = _movie(empty_api, project, scenes=[scene["id"]])

    row = empty_api.get(f"/api/movies/{movie['id']}").get_json()["scenes"][0]

    assert row["title"] == "Stadium"
    assert row["thumb"]["node"] == node
    assert row["thumb"]["url"]


def test_replacing_a_movies_scenes_takes_an_ordered_list(empty_api):
    """A replace rather than an append, for the involvement set's reason.

    An add-only endpoint would need a remove beside it *and* an ordering verb,
    and a client that got any of the three wrong would produce a cut nobody asked
    for.
    """
    project = _project(empty_api)
    first = _scene(empty_api, project, "first-scene")
    second = _scene(empty_api, project, "second-scene")
    movie = _movie(empty_api, project, scenes=[first["id"], second["id"]])

    resp = empty_api.patch(
        f"/api/movies/{movie['id']}/scenes", json={"scenes": [second["id"], first["id"]]}
    )

    assert resp.status_code == 200
    assert empty_api.get(f"/api/movies/{movie['id']}").get_json()["scenes"][0]["id"] == (
        second["id"]
    )


def test_a_movie_cannot_name_a_scene_that_does_not_exist(empty_api):
    """The list is what `assemble` walks.

    A missing id there is a stitch that fails half way through an upload rather
    than at the request that caused it.
    """
    project = _project(empty_api)
    movie = _movie(empty_api, project)

    assert empty_api.patch(
        f"/api/movies/{movie['id']}/scenes", json={"scenes": ["scene-nobody"]}
    ).status_code == 404


def test_a_movie_output_is_the_finished_cut(empty_api):
    project = _project(empty_api)
    movie = _movie(empty_api, project)

    resp = empty_api.post(
        f"/api/movies/{movie['id']}/output",
        json={"name": "launch.mp4", "size": 100, "content_type": "video/mp4"},
    )

    assert resp.status_code == 201
    cut = empty_api.get(f"/api/movies/{movie['id']}").get_json()["output"]
    assert cut["node"] == resp.get_json()["node"]
    assert cut["name"] == "launch.mp4"
    assert cut["url"]


def test_assembling_a_movie_records_the_report_as_well_as_the_cut(empty_api):
    """`output` was accepted here and `characters`, `stitch` and `assembled` were not.

    So a movie recorded its cut while silently losing the report of how it was
    made — the same drop as the scene route, minus the 400 that would have said
    so.
    """
    project = _project(empty_api)
    movie = _movie(empty_api, project)
    node = empty_api.post(
        f"/api/movies/{movie['id']}/output",
        json={"name": "launch.mp4", "size": 100, "content_type": "video/mp4"},
    ).get_json()["node"]

    resp = empty_api.patch(
        f"/api/movies/{movie['id']}",
        json={
            "characters": ["char-1"],
            "stitch": {"tool": "ffmpeg", "scenes": 2},
            "status": "assembled",
            "output": {"node": node, "duration": 90.0},
            "assembled": "2026-08-25T10:00:00Z",
        },
    )

    assert resp.status_code == 200
    body = empty_api.get(f"/api/movies/{movie['id']}").get_json()
    assert body["characters"] == ["char-1"]
    assert body["stitch"] == {"tool": "ffmpeg", "scenes": 2}
    assert body["assembled"] == "2026-08-25T10:00:00Z"
    assert body["output"]["node"] == node


def test_deleting_a_movie_leaves_its_scenes_alone(empty_api):
    """A movie is a cut of scenes, not an owner of them.

    Deleting the cut must not take the takes with it — they are the expensive
    half, and each one is its own entity with its own folder.
    """
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    movie = _movie(empty_api, project, scenes=[scene["id"]])

    assert empty_api.delete(f"/api/movies/{movie['id']}").status_code == 200

    assert empty_api.get(f"/api/scenes/{scene['id']}").status_code == 200
