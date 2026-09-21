"""Locations: the second subject kind, on the same rows as a character.

A location — a room, a set, a street — is what a character is photographed
IN, and it has to hold on-model across renders the way a character does. It
is built by the same `routes/subjects.py` that builds characters, so most of
what `test_characters.py` pins holds here by construction. These tests pin
what is a location's OWN:

* **Its rows have their own prefix** — `LOC#`, `loc-`, a `locations/` blob
  key — so nothing about a location can be mistaken for a character.
* **Its bible has its own sections**, and a character's are refused on it.
* **A run and a project record where they were shot** as edges, so "every
  run in this room" is one query, and a location cannot be deleted from
  under them.
* **Its textblock hands back the sections that say what is fixed**, not the
  ones that say what to shoot it on.

Assertions about stored items go through the raw `catalog_table` client, as in
`test_characters.py`, so a test cannot pass because reader and writer share a
mistake.
"""

from studio_core import config
from studio_core.services import catalog
from studio_core.routes.locations import PROFILE_SECTIONS, clean_profile
from studio_core.routes import characters as character_routes
from tests.conftest import CATALOG_LIBRARY, CATALOG_ROOT


def _item(client, pk, sk):
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _create(api, name="dev-kitchen", **body):
    resp = api.post("/api/locations", json={"name": name, **body})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _tagged(api, location, name, tags, body=b"webp-bytes"):
    """One image under the location, carrying `tags`, with bytes behind it."""
    node = api.post(
        "/api/nodes", json={"parent": location["root"], "name": name, "kind": "file"}
    ).get_json()
    record = catalog.node(node["id"])
    catalog.set_blob(node["id"], record["blob_key"], size=len(body), content_type="image/webp")
    api.patch(f"/api/nodes/{node['id']}", json={"tags": tags})
    return catalog.node(node["id"])


# ──────────────────────────── the rows ────────────────────────────


def test_creating_a_location_writes_its_own_rows_in_one_transaction(empty_api, catalog_table):
    """`LOC#<id>` / `META`, the `LIB#` index row, and a root named by the id.

    The same four items a character gets, under a prefix of their own — so a
    library listing its characters never lists a room, and vice versa.
    """
    location = _create(empty_api)
    assert location["id"].startswith("loc-")

    record = _item(catalog_table, f"LOC#{location['id']}", "META")
    assert record["name"]["S"] == "dev-kitchen"
    assert record["lib"]["S"] == CATALOG_LIBRARY
    assert int(record["rev"]["N"]) == 1

    index = _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", f"LOC#{location['id']}")
    assert index["entity"]["S"] == location["id"]

    root = _item(catalog_table, f"NODE#{location['root']}", "META")
    assert root["entity"]["S"] == location["id"]
    assert root["parent_id"]["S"] == CATALOG_ROOT
    assert _item(catalog_table, f"NODE#{CATALOG_ROOT}", f"NAME#{location['id']}") is not None


def test_a_location_is_listed_apart_from_characters(empty_api):
    """Two listings, two kinds. A room in `/api/characters` would be a bug."""
    location = _create(empty_api)
    empty_api.post("/api/characters", json={"name": "subject-a"})

    locations = empty_api.get("/api/locations").get_json()
    characters = empty_api.get("/api/characters").get_json()

    assert [entry["id"] for entry in locations] == [location["id"]]
    assert location["id"] not in {entry["id"] for entry in characters}
    assert locations[0]["counts"] == {"files": 0, "default": 0}


def test_a_location_cannot_be_addressed_as_a_character(empty_api):
    """The kind is on the route, and an id of the other kind is a 404."""
    location = _create(empty_api)
    assert empty_api.get(f"/api/characters/{location['id']}").status_code == 404
    assert empty_api.get(f"/api/locations/{location['id']}").status_code == 200


def test_a_location_files_its_bytes_under_its_own_prefix(empty_api):
    """`locations/<id>/<node>.<ext>` — a fourth prefix in the bucket, no name in it."""
    location = _create(empty_api)
    node = _tagged(empty_api, location, "wide.webp", ["default", "wide"])
    assert node["blob_key"].startswith(f"locations/{location['id']}/")
    assert "dev-kitchen" not in node["blob_key"]


# ──────────────────────────── the bible ────────────────────────────


def test_a_location_starts_from_the_location_template(empty_api):
    """Seeded from `location_template.json`, not the character's blank bible."""
    location = _create(empty_api)
    record = empty_api.get(f"/api/locations/{location['id']}").get_json()

    assert set(record["profile"]) == set(PROFILE_SECTIONS) | {"text_identity_block"}
    assert "face" not in record["profile"]
    assert "space" in record["profile"]
    assert clean_profile(record["profile"]) == record["profile"]

    template = empty_api.get("/api/locations/profile-template").get_json()
    assert template["profile"] == record["profile"]
    assert "space.layout" in template["hints"]


def test_a_character_section_is_refused_on_a_location(empty_api):
    """`face` is not a thing a room has; `wardrobe` neither. Refused, not stored."""
    location = _create(empty_api)
    resp = empty_api.patch(
        f"/api/locations/{location['id']}/profile",
        json={"rev": 1, "patch": {"face": {"structure": "a wall"}}},
    )
    assert resp.status_code == 400
    assert "face" in resp.get_json()["error"]

    # And the other way round: a character has no `space`.
    character = empty_api.post("/api/characters", json={"name": "subject-a"}).get_json()
    resp = empty_api.patch(
        f"/api/characters/{character['id']}/profile",
        json={"rev": 1, "patch": {"space": {"layout": "square"}}},
    )
    assert resp.status_code == 400
    assert character_routes.PROFILE_SECTIONS != PROFILE_SECTIONS


def test_the_location_textblock_hands_back_what_is_fixed(empty_api):
    """Raw material is the sections that say what the place IS — not `rendering`."""
    location = _create(empty_api, profile={
        "space": {"layout": "an L, the door on the short leg"},
        "lighting": {"sources": "one window, north"},
        "rendering": {"lens": "24mm"},
    })
    body = empty_api.get(f"/api/locations/{location['id']}/textblock").get_json()
    assert body["text"] == ""
    assert set(body["raw"]) == {"space", "lighting"}


# ──────────────────────────── the selection ────────────────────────────


def test_a_vantage_is_a_tag_and_narrows_the_default_set(empty_api):
    """`?tag=default,wide` — the same rule as a character's `face`, different word."""
    location = _create(empty_api)
    wide = _tagged(empty_api, location, "wide.webp", ["default", "wide"])
    _tagged(empty_api, location, "detail.webp", ["default", "detail"])
    _tagged(empty_api, location, "scrap.webp", ["wide"])

    everything = empty_api.get(f"/api/locations/{location['id']}/selection").get_json()
    assert [e["name"] for e in everything["selection"]] == ["detail.webp", "wide.webp"]

    wides = empty_api.get(
        f"/api/locations/{location['id']}/selection?tag=default,wide").get_json()
    assert [e["node"] for e in wides["selection"]] == [wide["node_id"]]

    resp = empty_api.get(f"/api/locations/{location['id']}/selection?tag=reverse")
    assert resp.status_code == 400
    assert "studio location images" in resp.get_json()["error"]


# ──────────────────────────── runs and projects ────────────────────────────


def _run(api, project, location, name="kitchen-wide"):
    resp = api.post(
        "/api/runs",
        json={
            "project": project["id"],
            "name": name,
            "kind": "image",
            "model": "google/nano-banana-pro",
            "locations": [location["id"]],
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def test_a_run_records_where_it_was_shot_as_an_edge(empty_api, catalog_table):
    """`locations` on the envelope AND `RUN#<run>` / `LOC#<loc>` beside it.

    The edge is what makes "every run shot in this room" one `by-sk` query;
    the field is what the run reports. Written together or not at all.
    """
    location = _create(empty_api)
    project = empty_api.post("/api/projects", json={"name": "kitchen-sink"}).get_json()
    run = _run(empty_api, project, location)

    read = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert read["locations"] == [location["id"]]
    assert _item(catalog_table, f"RUN#{run['id']}", f"LOC#{location['id']}") is not None

    found = empty_api.get(f"/api/runs?location={location['id']}&include=drafts").get_json()
    assert [entry["id"] for entry in found["runs"]] == [run["id"]]
    found = empty_api.get(f"/api/locations/{location['id']}/runs").get_json()
    assert [entry["id"] for entry in found["runs"]] == [run["id"]]


def test_a_run_naming_an_unknown_location_is_refused(empty_api):
    project = empty_api.post("/api/projects", json={"name": "kitchen-sink"}).get_json()
    resp = empty_api.post(
        "/api/runs",
        json={"project": project["id"], "kind": "image",
              "model": "google/nano-banana-pro", "locations": ["loc-nope"]},
    )
    assert resp.status_code == 404


def test_a_runs_locations_can_be_set_after_creation(empty_api, catalog_table):
    """The same late-binding `characters` got: a replace, field and edges together."""
    location = _create(empty_api)
    project = empty_api.post("/api/projects", json={"name": "kitchen-sink"}).get_json()
    run = empty_api.post(
        "/api/runs",
        json={"project": project["id"], "kind": "image", "model": "google/nano-banana-pro"},
    ).get_json()
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["locations"] == []

    resp = empty_api.patch(f"/api/runs/{run['id']}", json={"locations": [location["id"]]})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["locations"] == [location["id"]]
    assert _item(catalog_table, f"RUN#{run['id']}", f"LOC#{location['id']}") is not None

    empty_api.patch(f"/api/runs/{run['id']}", json={"locations": []})
    assert _item(catalog_table, f"RUN#{run['id']}", f"LOC#{location['id']}") is None


def test_a_project_records_where_it_is_shot(empty_api, catalog_table):
    """`PROJ#<id>` / `LOC#<id>` at creation, replaceable, expanded on read."""
    location = _create(empty_api)
    project = empty_api.post(
        "/api/projects", json={"name": "kitchen-sink", "locations": [location["id"]]}
    ).get_json()

    assert project["locations"] == [{"id": location["id"], "name": "dev-kitchen"}]
    assert project["characters"] == []
    assert _item(catalog_table, f"PROJ#{project['id']}", f"LOC#{location['id']}") is not None

    body = empty_api.get(f"/api/locations/{location['id']}/projects").get_json()
    assert [entry["id"] for entry in body] == [project["id"]]

    resp = empty_api.patch(f"/api/projects/{project['id']}/locations", json={"locations": []})
    assert resp.status_code == 200
    assert resp.get_json()["locations"] == []
    assert empty_api.get(f"/api/projects/{project['id']}").get_json()["locations"] == []


def test_deleting_refuses_while_a_project_or_a_run_is_shot_there(empty_api):
    location = _create(empty_api)
    project = empty_api.post(
        "/api/projects", json={"name": "kitchen-sink", "locations": [location["id"]]}
    ).get_json()
    _run(empty_api, project, location)

    resp = empty_api.delete(f"/api/locations/{location['id']}")
    assert resp.status_code == 409
    assert "this location" in resp.get_json()["message"]
    assert len(resp.get_json()["projects"]) == 1
    assert len(resp.get_json()["runs"]) == 1

    assert empty_api.delete(f"/api/locations/{location['id']}?force=1").status_code == 200
    assert empty_api.get(f"/api/projects/{project['id']}").get_json()["locations"] == []
