"""Projects as rows: the claim, the involvement links, the counts, the inputs.

A project used to be a folder name, which made it **impossible to rename** — the
slug was the primary key, so a rename was a tree rewrite and every run that had
recorded a path was stranded by it. These tests pin the four things that changed:

* a rename is one conditional write and touches no object,
* characters involved are rows, so the reverse question is answerable,
* `counts` is maintained inside the transaction that moves it rather than
  scanned,
* `input/` is resolved **by name at write time and created if absent**, which is
  what makes the folder layout a convention rather than a schema.

Raw items are read through the `catalog_table` client so a test cannot pass
because the reader and the writer share a mistake.
"""

from studio_core import config
from studio_core.services import catalog, layout
from tests.conftest import CATALOG_LIBRARY, CATALOG_ROOT


def _item(client, pk, sk):
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _project(api, slug="rooftop-teaser", **body):
    resp = api.post("/api/projects", json={"slug": slug, **body})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _character(api, slug="subject-a"):
    return api.post(
        "/api/characters", json={"slug": slug, "fictional": True}
    ).get_json()


def _run(api, project, slug="rooftop-portrait"):
    resp = api.post(
        "/api/runs",
        json={
            "project": project["id"],
            "slug": slug,
            "kind": "image",
            "model": "google/nano-banana-pro",
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _child(parent_id, name):
    return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])


# ──────────────────────── create, as one transaction ────────────────────────


def test_creating_a_project_writes_the_record_claim_root_and_subfolders(empty_api, catalog_table):
    """Record, claim, root and the five `PROJECT_LAYOUT` folders, or none of them."""
    project = _project(empty_api)

    record = _item(catalog_table, f"PROJ#{project['id']}", "META")
    assert record["slug"]["S"] == "rooftop-teaser"
    assert int(record["rev"]["N"]) == 1
    assert record["counts"]["M"]["runs"]["N"] == "0"

    claim = _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", "PROJSLUG#rooftop-teaser")
    assert claim["entity"]["S"] == project["id"]

    root = _item(catalog_table, f"NODE#{project['root']}", "META")
    assert root["entity"]["S"] == project["id"]

    assert sorted(entry["name"] for entry in catalog.children(project["root"])) == sorted(
        layout.PROJECT_LAYOUT
    )


def test_involvement_is_rows_and_not_a_list_on_the_record(empty_api, catalog_table):
    """**A list would answer forwards and nothing at all backwards.**

    `PROJ#<id>` / `CHAR#<id>` is "who is in this project" read forwards and
    "which projects involve this character" read backwards on `by-sk` — and a
    character delete needs the second to find what points at it.
    """
    character = _character(empty_api)
    project = _project(empty_api, characters=[character["id"]])

    link = _item(catalog_table, f"PROJ#{project['id']}", f"CHAR#{character['id']}")
    assert link["lib"]["S"] == CATALOG_LIBRARY
    assert "characters" not in _item(catalog_table, f"PROJ#{project['id']}", "META")

    fetched = empty_api.get(f"/api/projects/{project['id']}").get_json()
    assert [entry["slug"] for entry in fetched["characters"]] == ["subject-a"]


def test_a_taken_project_slug_is_409(empty_api):
    _project(empty_api)

    resp = empty_api.post("/api/projects", json={"slug": "rooftop-teaser"})

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "conflict"


def test_creating_with_a_character_that_does_not_exist_is_404(empty_api):
    """A link to a missing character would answer the reverse query forever."""
    assert empty_api.post(
        "/api/projects", json={"slug": "rooftop-teaser", "characters": ["char-nobody"]}
    ).status_code == 404


# ──────────────────────────── rename ────────────────────────────


def test_renaming_a_project_was_impossible_and_is_now_one_write(empty_api, catalog_table):
    """The slug was the primary key, so this could not be done at all.

    Zero objects copied, every node id kept, and the run recorded inside it still
    reachable — because a run record names its own folder node id rather than a
    path.
    """
    project = _project(empty_api)
    run = _run(empty_api, project)
    before = {
        node["node_id"]: node.get("blob_key")
        for node in catalog.branch(CATALOG_LIBRARY, "/", 100)[0]
    }

    resp = empty_api.patch(
        f"/api/projects/{project['id']}", json={"slug": "launch-teaser", "rev": 1}
    )

    assert resp.status_code == 200
    after = {
        node["node_id"]: node.get("blob_key")
        for node in catalog.branch(CATALOG_LIBRARY, "/", 100)[0]
    }
    assert after == before
    assert catalog.node(project["root"])["name"] == "launch-teaser"
    assert _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", "PROJSLUG#rooftop-teaser") is None
    assert empty_api.get(f"/api/runs/{run['id']}").status_code == 200


def test_a_stale_project_rev_is_409(empty_api):
    project = _project(empty_api)
    empty_api.patch(f"/api/projects/{project['id']}", json={"title": "First", "rev": 1})

    resp = empty_api.patch(
        f"/api/projects/{project['id']}", json={"title": "Second", "rev": 1}
    )

    assert resp.status_code == 409


# ──────────────────────── the involvement set ────────────────────────


def test_replacing_the_character_set_adds_and_removes(empty_api, catalog_table):
    """A replace rather than an add, because the SPA edits a set.

    An add-only endpoint would need a remove beside it, and a client that got the
    difference wrong would accumulate links nothing removes.
    """
    first = _character(empty_api, "subject-a")
    second = _character(empty_api, "subject-b")
    project = _project(empty_api, characters=[first["id"]])

    resp = empty_api.patch(
        f"/api/projects/{project['id']}/characters", json={"characters": [second["id"]]}
    )

    assert resp.status_code == 200
    assert _item(catalog_table, f"PROJ#{project['id']}", f"CHAR#{first['id']}") is None
    assert _item(catalog_table, f"PROJ#{project['id']}", f"CHAR#{second['id']}") is not None
    assert empty_api.get(f"/api/characters/{first['id']}/projects").get_json() == []


# ──────────────────────────── the input pool ────────────────────────────


def test_inputs_are_numbered_from_one_in_name_order(empty_api):
    """**Position in this list is what `--input N` means.**

    Numbered in the response rather than left to the caller, because the position
    *is* the address: two clients sorting a listing differently would disagree
    about what `--input 3` means, and the disagreement would only ever be visible
    in the output of a generation.
    """
    project = _project(empty_api)
    pool = _child(project["root"], layout.INPUT_FOLDER)["node_id"]
    for name in ("street-plate.png", "rooftop-plate.png"):
        empty_api.post("/api/nodes", json={"parent": pool, "name": name, "kind": "file"})

    body = empty_api.get(f"/api/projects/{project['id']}/inputs").get_json()

    assert [(entry["position"], entry["name"]) for entry in body["inputs"]] == [
        (1, "rooftop-plate.png"),
        (2, "street-plate.png"),
    ]


def test_a_deleted_input_folder_is_made_again_rather_than_404ing(empty_api):
    """**The layout is convention, and this is the self-healing half of it.**

    A person can rename `input/`, move it or delete it — those are ordinary file
    operations and they must stay ordinary. A route that cannot find its
    conventional folder makes one; it never fails, and it never guesses.
    """
    project = _project(empty_api)
    pool = _child(project["root"], layout.INPUT_FOLDER)
    assert empty_api.delete(f"/api/nodes/{pool['node_id']}").status_code == 200

    body = empty_api.get(f"/api/projects/{project['id']}/inputs").get_json()

    assert body["inputs"] == []
    assert body["folder"] != pool["node_id"]
    assert catalog.node(body["folder"])["name"] == layout.INPUT_FOLDER


# ──────────────────────────── counts ────────────────────────────


def test_counts_move_with_the_transaction_that_creates_and_deletes(empty_api):
    """**Maintained, never scanned.**

    A project card shows runs, scenes and movies, and a screen that had to count
    them would page every listing row to draw a tile. Maintaining it inside the
    same transaction is what stops it drifting by one.
    """
    project = _project(empty_api)
    assert empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"] == {
        "runs": 0,
        "scenes": 0,
        "movies": 0,
    }

    run = _run(empty_api, project)
    empty_api.post(
        "/api/scenes", json={"project": project["id"], "slug": "stadium", "title": "S"}
    )

    counts = empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]
    assert (counts["runs"], counts["scenes"], counts["movies"]) == (1, 1, 0)

    empty_api.delete(f"/api/runs/{run['id']}")

    assert empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]["runs"] == 0


# ──────────────────────────── delete ────────────────────────────


def test_deleting_a_project_refuses_while_it_holds_runs(empty_api):
    """A run's envelope names its project, so deleting it strands every one.

    `?force=1` says to do it anyway, which is a reasonable thing to want for a
    project of failed experiments.
    """
    project = _project(empty_api)
    _run(empty_api, project)

    resp = empty_api.delete(f"/api/projects/{project['id']}")

    assert resp.status_code == 409
    assert resp.get_json()["counts"]["runs"] == 1
    assert empty_api.delete(f"/api/projects/{project['id']}?force=1").status_code == 200


def test_deleting_an_empty_project_keeps_its_files_by_default(empty_api, catalog_table):
    project = _project(empty_api)

    assert empty_api.delete(f"/api/projects/{project['id']}").status_code == 200

    assert _item(catalog_table, f"PROJ#{project['id']}", "META") is None
    assert "entity" not in catalog.node(project["root"])
    assert [entry["name"] for entry in catalog.children(CATALOG_ROOT)] == ["rooftop-teaser"]
