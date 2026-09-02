"""`routes/movies.py` — scenes cut into one piece.

**These lived in `test_scenes.py`**, which covered two route modules and left
`routes/movies.py` at 77% with eight of its twenty-six tests. A movie is the
tier above a scene and has its own file now, for the same reason
`domain/movies.py` does.

**Stitching stays in the CLI.** `ffmpeg` ships in the pipeline wheel and the
Lambda has none, so `movies new` downloads each scene, stitches locally, uploads
through `POST /api/movies/<id>/output` and patches the record. The API owns the
record, not the encode — which is why there is an upload route here and no
encode.
"""

from studio_core import config
from studio_core.services import catalog


def _item(client, pk, sk):
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _project(api, name="rooftop-teaser"):
    return api.post("/api/projects", json={"name": name}).get_json()


def _scene(api, project, name="stadium-encounter", shots=None):
    resp = api.post(
        "/api/scenes",
        json={"project": project["id"], "name": "Stadium",
              "shots": shots or []},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _movie(api, project, name="launch-cut", **body):
    resp = api.post("/api/movies", json={"project": project["id"], "name": name, **body})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _child(parent_id, name):
    return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])


def test_a_movie_resolves_the_scenes_it_names(empty_api):
    """The list is ids; the read is what a person can act on."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    movie = _movie(empty_api, project, scenes=[scene["id"]])

    body = empty_api.get(f"/api/movies/{movie['id']}").get_json()

    assert body["scenes"] == [
        {
            "id": scene["id"],
            "name": "Stadium",
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

    assert row["name"] == "Stadium"
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

# ── the gaps coverage found ─────────────────────────────────────────────────


def test_listing_without_a_project_walks_every_project_newest_first(empty_api):
    """`GET /api/movies` with no `?project=` is a library-wide listing.

    It was the uncovered half of the route: with a project it is one query, and
    without one it walks every project in the library and sorts the union. A
    caller with two projects would have seen whichever order the walk happened
    to produce.
    """
    first = _project(empty_api, "first-project")
    second = _project(empty_api, "second-project")
    _movie(empty_api, first, "early-cut")
    _movie(empty_api, second, "later-cut")

    body = empty_api.get("/api/movies").get_json()

    slugs = [row["name"] for row in body["movies"]]
    assert slugs == ["later-cut", "early-cut"]
    assert body["cursor"] is None


def test_listing_by_project_returns_only_that_projects_movies(empty_api):
    first = _project(empty_api, "first-project")
    second = _project(empty_api, "second-project")
    _movie(empty_api, first, "early-cut")
    _movie(empty_api, second, "later-cut")

    body = empty_api.get(f"/api/movies?project={first['id']}").get_json()

    assert [row["name"] for row in body["movies"]] == ["early-cut"]


def test_scenes_must_be_a_list_rather_than_whatever_was_sent(empty_api):
    """A string is the plausible mistake — `scenes: "scene-1"` iterates into
    characters and creates a movie naming twelve scenes that do not exist."""
    project = _project(empty_api)
    resp = empty_api.post("/api/movies",
                          json={"project": project["id"], "name": "bad-cut",
                                "scenes": "scene-1"})
    assert resp.status_code == 400
    assert "must be a list" in resp.get_data(as_text=True)


def test_a_movie_with_no_scenes_is_a_real_state(empty_api):
    """`movies new` creates the record BEFORE any bytes move, so a movie with an
    empty cut list is what a half-finished assemble leaves behind — visible and
    re-runnable rather than absent."""
    project = _project(empty_api)
    movie = _movie(empty_api, project, "empty-cut")

    body = empty_api.get(f"/api/movies/{movie['id']}").get_json()
    assert body["scenes"] == []
    assert body["status"] != "assembled"
