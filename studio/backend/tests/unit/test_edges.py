"""Every relationship, read backwards — and answered in the shape it is read in.

**One rule, stated once and tested here.** An edge is a row whose sort key is
the *target's* id, `pk = <A>#<a_id>` / `sk = <B>#<b_id>`, because `by-sk` makes
that hash key an exact-match lookup and nothing else in the table can be
inverted. Four relationships followed it; two did not, and both of those had a
reverse question with no answer at any price:

| Was | Why it could not be read backwards |
|---|---|
| a movie's scenes, a JSON list on the record | no index addresses into a list |
| a scene's run, an attribute on a `SHOT#<n>` row | `by-sk` sees sort keys, not attributes |

The second half of the file is the *shape* contract. `GET` resolved a
relationship to objects while the write that changed it answered with the bare
ids it was handed, so a client that merged the response replaced objects with
strings — the write succeeded and everything downstream read empty. That cost
three bugs on `projects`, and `movies` was one caller away from the same thing.
"""

from studio_core.services import catalog


def _project(api, slug="rooftop-teaser", **body):
    return api.post("/api/projects", json={"slug": slug, **body}).get_json()


def _character(api, slug="subject-a"):
    return api.post("/api/characters", json={"slug": slug, "fictional": True}).get_json()


def _scene(api, project, slug="stadium-encounter", shots=None):
    resp = api.post(
        "/api/scenes",
        json={"project": project["id"], "slug": slug, "title": "Stadium",
              "shots": shots or []},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _movie(api, project, slug="launch-cut", **body):
    resp = api.post("/api/movies", json={"project": project["id"], "slug": slug, **body})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _run(api, project, **body):
    resp = api.post(
        "/api/runs",
        json={"project": project["id"], "kind": "image", "engine": "nano-banana-pro",
              "model": "google/nano-banana-pro", **body},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# ── the reverse questions ───────────────────────────────────────────────────


def test_a_scene_names_the_movies_that_cut_it(empty_api):
    """`GET /scenes/<id>` answers upwards. It had nothing to answer with."""
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    movie = _movie(empty_api, project, scenes=[scene["id"]])

    body = empty_api.get(f"/api/scenes/{scene['id']}").get_json()

    assert [entry["id"] for entry in body["movies"]] == [movie["id"]]
    assert body["movies"][0]["slug"] == "launch-cut"


def test_a_scene_cut_into_nothing_says_so_rather_than_omitting_the_field(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    assert empty_api.get(f"/api/scenes/{scene['id']}").get_json()["movies"] == []


def test_dropping_a_scene_from_a_movie_drops_the_edge(empty_api):
    """A replace has to delete, or the reverse accumulates links nothing removes."""
    project = _project(empty_api)
    kept = _scene(empty_api, project, slug="kept")
    dropped = _scene(empty_api, project, slug="dropped")
    movie = _movie(empty_api, project, scenes=[kept["id"], dropped["id"]])

    empty_api.patch(f"/api/movies/{movie['id']}/scenes", json={"scenes": [kept["id"]]})

    assert empty_api.get(f"/api/scenes/{kept['id']}").get_json()["movies"] != []
    assert empty_api.get(f"/api/scenes/{dropped['id']}").get_json()["movies"] == []


def test_a_reprise_keeps_its_order_and_collapses_to_one_edge(empty_api):
    """The same scene twice is legal, and the two halves disagree on purpose.

    `movies new` resolves its refs in order with no dedupe, copies a file per
    entry and stitches positionally — so cutting one scene twice works today and
    the list is what carries that. An edge is set membership and cannot express
    it, which is exactly why the list was kept rather than replaced by rows.
    """
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    movie = _movie(empty_api, project, scenes=[scene["id"], scene["id"]])

    cut = empty_api.get(f"/api/movies/{movie['id']}").get_json()
    assert [entry["id"] for entry in cut["scenes"]] == [scene["id"], scene["id"]]

    back = empty_api.get(f"/api/scenes/{scene['id']}").get_json()["movies"]
    assert [entry["id"] for entry in back] == [movie["id"]]


def test_a_run_names_the_scenes_that_used_it(empty_api):
    """The question `runs find --character` has always had, one prefix over."""
    project = _project(empty_api)
    run = _run(empty_api, project)
    scene = _scene(empty_api, project, shots=[{"id": "shot-01", "prompt": "wide"}])

    empty_api.patch(f"/api/scenes/{scene['id']}/shots/shot-01", json={"run": run["id"]})

    body = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert [entry["id"] for entry in body["scenes"]] == [scene["id"]]


def test_rebinding_a_shot_moves_the_edge_off_the_old_run(empty_api):
    """Derived from the shots on every write, so it cannot drift from them."""
    project = _project(empty_api)
    first = _run(empty_api, project)
    second = _run(empty_api, project)
    scene = _scene(empty_api, project, shots=[{"id": "shot-01", "prompt": "wide"}])

    empty_api.patch(f"/api/scenes/{scene['id']}/shots/shot-01", json={"run": first["id"]})
    empty_api.patch(f"/api/scenes/{scene['id']}/shots/shot-01", json={"run": second["id"]})

    assert empty_api.get(f"/api/runs/{first['id']}").get_json()["scenes"] == []
    assert [entry["id"] for entry in
            empty_api.get(f"/api/runs/{second['id']}").get_json()["scenes"]] == [scene["id"]]


def test_a_plan_revision_that_drops_a_shot_drops_its_run_edge(empty_api):
    """`put_shots` deletes rows; the edges have to go with them."""
    project = _project(empty_api)
    run = _run(empty_api, project)
    scene = _scene(empty_api, project, shots=[{"id": "shot-01", "prompt": "wide"}])
    empty_api.patch(f"/api/scenes/{scene['id']}/shots/shot-01", json={"run": run["id"]})

    empty_api.patch(f"/api/scenes/{scene['id']}/shots",
                  json={"shots": [{"id": "shot-02", "prompt": "close"}]})

    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["scenes"] == []


def test_a_run_names_what_was_chained_off_it(empty_api):
    """`lineage.from_run` is a scalar pointing up. This is the way down."""
    project = _project(empty_api)
    parent = _run(empty_api, project)
    child = _run(empty_api, project,
                 lineage={"from_run": parent["id"], "from_output": None})

    body = empty_api.get(f"/api/runs/{parent['id']}").get_json()
    assert [entry["id"] for entry in body["derived"]] == [child["id"]]
    assert empty_api.get(f"/api/runs/{child['id']}").get_json()["derived"] == []


def test_a_character_still_names_its_projects(empty_api):
    """The relationship that already worked, kept honest through the refactor.

    `set_project_characters` stopped spelling its own key and became a caller of
    `set_edges`; this is the test that the key did not change underneath it.
    """
    character = _character(empty_api)
    project = _project(empty_api, characters=[character["id"]])

    assert catalog.linked(character["id"], catalog.ENTITY_PROJECT) == [project["id"]]


# ── the shape contract ──────────────────────────────────────────────────────
#
# Each of these asserts that a write answers in the shape its read uses. They
# are deliberately written as an equality against the subsequent `GET` rather
# than against a literal, because the point is not what the shape IS — it is
# that one endpoint cannot drift from the other.


def test_setting_a_projects_characters_answers_in_the_read_shape(empty_api):
    character = _character(empty_api)
    project = _project(empty_api)

    written = empty_api.patch(f"/api/projects/{project['id']}/characters",
                            json={"characters": [character["id"]]}).get_json()
    read = empty_api.get(f"/api/projects/{project['id']}").get_json()

    assert written["characters"] == read["characters"]
    # The regression in full: ids here, objects there, and a client that merged
    # the two put strings where a record holds objects.
    assert written["characters"][0]["slug"] == "subject-a"


def test_creating_a_project_answers_in_the_read_shape(empty_api):
    character = _character(empty_api)
    created = _project(empty_api, characters=[character["id"]])
    read = empty_api.get(f"/api/projects/{created['id']}").get_json()

    assert created["characters"] == read["characters"]


def test_setting_a_movies_scenes_answers_in_the_read_shape(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)
    movie = _movie(empty_api, project)

    written = empty_api.patch(f"/api/movies/{movie['id']}/scenes",
                            json={"scenes": [scene["id"]]}).get_json()
    read = empty_api.get(f"/api/movies/{movie['id']}").get_json()

    assert written["scenes"] == read["scenes"]


def test_lineage_recorded_after_the_fact_is_still_readable_downwards(empty_api):
    """`chain` writes the envelope before it knows what it continued from.

    So the parent arrives by PATCH, not at create — and that path wrote the
    scalar without the edge, which would have made the reverse correct only for
    runs that knew their parent at birth.
    """
    project = _project(empty_api)
    parent = _run(empty_api, project)
    child = _run(empty_api, project)

    empty_api.patch(f"/api/runs/{child['id']}",
                    json={"lineage": {"from_run": parent["id"], "from_output": None}})

    body = empty_api.get(f"/api/runs/{parent['id']}").get_json()
    assert [entry["id"] for entry in body["derived"]] == [child["id"]]


def test_creating_a_movie_answers_in_the_read_shape(empty_api):
    project = _project(empty_api)
    scene = _scene(empty_api, project)

    created = _movie(empty_api, project, scenes=[scene["id"]])
    read = empty_api.get(f"/api/movies/{created['id']}").get_json()

    assert created["scenes"] == read["scenes"]


# ── listing shapes ──────────────────────────────────────────────────────────
#
# One level up from a relationship: two routes that return "the same
# conceptual thing" have to return the same shape too, for exactly the same
# reason. A client draws both with one component.


def test_a_characters_projects_are_the_same_rows_the_project_list_sends(empty_api):
    """The SPA draws both with `EntityCard`, which reads `counts` and `hero`.

    This route sent `{id, slug, title}` and nothing else, so the Projects tab
    on a character threw on `project.counts.runs` and the whole tab was the
    error boundary.
    """
    character = _character(empty_api)
    _project(empty_api, characters=[character["id"]])

    listed = empty_api.get("/api/projects").get_json()
    involved = empty_api.get(f"/api/characters/{character['id']}/projects").get_json()

    assert involved == listed


def test_the_input_pool_is_an_envelope_and_says_so(empty_api):
    """Pinned because it is the one listing that is NOT a bare array.

    Both clients assumed it was: the SPA typed it as a list and called `.map`
    on an object, and the CLI put it through a normaliser that answers `[]` for
    anything that is not a list — so the pool read as empty every time, which
    looks exactly like an empty pool.
    """
    project = _project(empty_api)

    body = empty_api.get(f"/api/projects/{project['id']}/inputs").get_json()

    assert isinstance(body, dict)
    assert set(body) == {"folder", "inputs"}
    assert body["inputs"] == []
