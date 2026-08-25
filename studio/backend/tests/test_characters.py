"""Characters as rows: the claim, the transaction, `rev`, and the reference index.

A character used to be a folder with a YAML file in it, and the four things that
cost are what these tests pin:

* **Identity was a magic string in a path**, so a rename was a tree rewrite and
  every run that had recorded a path was stranded by it.
* **Reference order was filename order**, maintained by `curate renumber`.
* **Descriptions lived in a `references:` map keyed on the basename that
  renumbering changed**, so the two went out of step.
* **Nothing could be queried**, so "which projects involve this character" had no
  answer at any price.

Every assertion about a stored item is made through the raw `catalog_table`
client rather than through `services.catalog`, so a test cannot pass because the
reader and the writer share a mistake. The routes are driven for real, because
half of what is under test is the status a stale `rev` comes back with.

`empty_api` rather than `catalog_tree`: the fixture tree is a **pre-entity**
library — folders literally named `characters/` and `projects/` with no records
behind them — so creating a character called `subject-a` in it would collide with
a folder for reasons that have nothing to do with what is being tested.
"""

import pytest

from studio_core import app_factory, config
from studio_core.services import catalog, layout
from tests.conftest import CATALOG_LIBRARY, CATALOG_ROOT


def _item(client, pk, sk):
    """One raw item, or None. The catalog's own reads are not trusted here."""
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _create(api, slug="subject-a", **body):
    resp = api.post(
        "/api/characters",
        json={"slug": slug, "display_name": "Subject", "fictional": True, **body},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _uploaded(api, parent_id, name, body=b"webp-bytes"):
    """A file that exists on both sides — a row with a size, and bytes behind it.

    Both halves, because a row carrying a `blob_key` and no `size` is a
    placeholder that every read refuses. A reference pointing at one would fail
    these tests for a reason that is somebody else's subject.
    """
    node = api.post(
        "/api/nodes", json={"parent": parent_id, "name": name, "kind": "file"}
    ).get_json()
    record = catalog.node(node["id"])
    return catalog.set_blob(
        node["id"], record["blob_key"], size=len(body), content_type="image/webp"
    )


def _child(parent_id, name):
    return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])


# ──────────────────────── create, as one transaction ────────────────────────


def test_creating_a_character_writes_every_item_in_one_transaction(empty_api, catalog_table):
    """**Twelve items, or none of them.**

    The record, the slug claim, and two each for the root and the four starting
    pools. That atomicity is what makes "create a character" something a person
    can retry after a timeout without inspecting what survived — which is the
    whole argument for one table rather than three.

    Asserted item by item against the raw client, because the shape of these rows
    is the schema and `services.catalog` is the only module allowed to know it.
    """
    character = _create(empty_api)

    record = _item(catalog_table, f"CHAR#{character['id']}", "META")
    assert record["slug"]["S"] == "subject-a"
    assert record["lib"]["S"] == CATALOG_LIBRARY
    assert int(record["rev"]["N"]) == 1
    assert record["root"]["S"] == character["root"]

    claim = _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", "CHARSLUG#subject-a")
    assert claim["entity"]["S"] == character["id"]
    # A pointer, never a projection. `display_name` here would be a mutable copy
    # on a second item that every rename has to keep in step.
    assert "display_name" not in claim

    root = _item(catalog_table, f"NODE#{character['root']}", "META")
    assert root["kind"]["S"] == "folder"
    assert root["parent_id"]["S"] == CATALOG_ROOT
    # The reverse pointer: one attribute, written once, never changed.
    assert root["entity"]["S"] == character["id"]

    assert _item(catalog_table, f"NODE#{CATALOG_ROOT}", "NAME#subject-a") is not None

    assert sorted(
        entry["name"] for entry in catalog.children(character["root"])
    ) == sorted(layout.CHARACTER_LAYOUT)


def test_the_starting_pools_are_a_layout_and_not_a_schema(empty_api):
    """**Rename `reference/`, delete `archive/`, add your own — nothing breaks.**

    They exist because an empty character is unhelpful, and nothing afterwards
    requires them: an image is a reference when a `REF#` row says so, not because
    of the folder it sits in. This is the assertion that keeps somebody from
    reintroducing a `folders` map on the record the next time a route needs to
    find `reference/`.
    """
    character = _create(empty_api)
    reference = _child(character["root"], "reference")

    assert empty_api.delete(f"/api/nodes/{_child(character['root'], 'archive')['node_id']}") \
        .status_code == 200
    assert empty_api.patch(
        f"/api/nodes/{reference['node_id']}", json={"name": "portraits"}
    ).status_code == 200

    # The record still names one node id and no folder names at all.
    fetched = empty_api.get(f"/api/characters/{character['id']}").get_json()
    assert fetched["root"] == character["root"]
    assert "folders" not in fetched


def test_a_taken_slug_is_409_and_leaves_nothing_behind(empty_api, catalog_table):
    """The claim is a conditional put, so a collision is never a read-then-write.

    The 409 carries a machine-readable code because the client has to act on it —
    offer a different slug — and matching on prose is how that stops working.

    The second half matters as much: a failed transaction must not leave a root
    folder called `subject-a` behind, or the retry would then fail on the *folder*
    name and say something else entirely.
    """
    _create(empty_api)

    resp = empty_api.post(
        "/api/characters", json={"slug": "subject-a", "fictional": True}
    )

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "conflict"
    assert "subject-a" in resp.get_json()["message"]
    assert len(catalog.children(CATALOG_ROOT)) == 1


def test_a_slug_is_refused_rather_than_repaired(empty_api):
    """It becomes half a primary key, so the string sent is the string claimed."""
    assert empty_api.post(
        "/api/characters", json={"slug": "Subject A", "fictional": True}
    ).status_code == 400


def test_the_consent_question_is_required(empty_api):
    """`fictional` has no default, and the absence of one is the point.

    Defaulting it either way would answer a consent question on somebody's behalf
    — and the safe-looking default is the one that silently marks a real person
    as invented.
    """
    assert empty_api.post("/api/characters", json={"slug": "subject-a"}).status_code == 400


# ──────────────────────────── read and address ────────────────────────────


def test_a_character_is_addressable_by_slug_for_the_cli(empty_api):
    """`slug:` exists because a person types a name, not a UUID.

    Prefixing rather than a second route keeps `<id>` one path segment, so every
    entity route reads the same and none of them has a second handler to drift.
    """
    character = _create(empty_api)

    assert empty_api.get("/api/characters/slug:subject-a").get_json()["id"] == character["id"]


def test_asking_for_a_character_by_a_project_id_is_404(empty_api):
    """The kind is passed rather than derived, so a stale link is not answered.

    Without it `GET /api/characters/<a project id>` would compose `CHAR#proj-…`,
    miss, and 404 anyway — but a route that *did* find something would be
    answering a question nobody asked.
    """
    project = empty_api.post("/api/projects", json={"slug": "rooftop-teaser"}).get_json()

    assert empty_api.get(f"/api/characters/{project['id']}").status_code == 404


def test_a_character_in_another_library_is_403(empty_api, catalog_table):
    """Membership is checked against the record's own `lib`, never the header.

    An entity id is a v4 UUID, so this is not a guard against enumeration; it is
    the guard against a *shared* id, which is the realistic case the moment a
    library has more than one member and somebody pastes a link.
    """
    catalog_table.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": "CHAR#char-elsewhere"},
            "sk": {"S": "META"},
            "id": {"S": "char-elsewhere"},
            "lib": {"S": "lib-0002"},
            "slug": {"S": "subject-b"},
            "rev": {"N": "1"},
        },
    )

    assert empty_api.get("/api/characters/char-elsewhere").status_code == 403


# ──────────────────────── rev, and what it protects ────────────────────────


def test_a_stale_rev_is_409_rather_than_a_silent_overwrite(empty_api):
    """**Compare-and-swap, where the old code was check-then-write.**

    `write_profile` used to re-read the node's `updated_at` and refuse if it had
    moved, which is a check and a write with a gap between them. A
    `ConditionExpression` has no gap. Two people editing one bible is the case
    this exists for: the second save is refused with the numbers in the message,
    and the client re-reads rather than losing the first's work.
    """
    character = _create(empty_api)
    assert empty_api.patch(
        f"/api/characters/{character['id']}", json={"display_name": "First", "rev": 1}
    ).status_code == 200

    resp = empty_api.patch(
        f"/api/characters/{character['id']}", json={"display_name": "Second", "rev": 1}
    )

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "conflict"
    assert "rev 1 → 2" in resp.get_json()["message"]
    assert empty_api.get(f"/api/characters/{character['id']}").get_json()[
        "display_name"
    ] == "First"


def test_a_missing_rev_is_400_rather_than_the_current_one(empty_api):
    """**Required, never defaulted**, and the refusal is the point.

    A client that omits it is a client that did not read before writing, and
    defaulting would turn every one of those into a silent last-writer-wins over
    somebody else's edit.
    """
    character = _create(empty_api)

    resp = empty_api.patch(
        f"/api/characters/{character['id']}", json={"display_name": "Nope"}
    )

    assert resp.status_code == 400
    assert "rev" in resp.get_json()["error"]


@pytest.mark.parametrize(
    "path,body",
    [
        ("", {"display_name": "x"}),
        ("/profile", {"profile": {}}),
        ("/profile", {"patch": {"face": {}}}),
        ("/default-set", {"nodes": []}),
    ],
)
def test_every_mutating_character_route_carries_a_rev(empty_api, path, body):
    """One rule, asserted across all four, because three of four is a hole.

    The one that would be missed is `default-set`: it reads like a small list
    rather than an edit, and it is read on every generation.
    """
    character = _create(empty_api)

    resp = empty_api.patch(f"/api/characters/{character['id']}{path}", json={**body, "rev": 99})

    assert resp.status_code == 409


# ──────────────────────────── rename ────────────────────────────


def test_a_rename_moves_no_objects_and_rewrites_no_records(empty_api, catalog_table):
    """**The single largest simplification the entity model buys.**

    Four writes in one transaction: drop the old claim, take the new one, bump
    the record, rename the root folder node. Today this was a `PATCH` per slugged
    basename across four pools plus a rewrite pass over every run document that
    had cited the old path — which is the whole reason `domain/rewrite.py`
    existed and why #420 was open.

    So the assertion is about what did *not* change: every node id, every blob
    key, and every `REF#` row.
    """
    character = _create(empty_api)
    reference = _child(character["root"], "reference")
    picture = _uploaded(empty_api, reference["node_id"], "front.webp")
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face", "description": "front"},
    )
    before = {
        node["node_id"]: node.get("blob_key")
        for node in catalog.branch(CATALOG_LIBRARY, "/", 100)[0]
    }

    resp = empty_api.patch(
        f"/api/characters/{character['id']}", json={"slug": "subject-b", "rev": 1}
    )

    assert resp.status_code == 200
    assert resp.get_json()["slug"] == "subject-b"
    after = {
        node["node_id"]: node.get("blob_key")
        for node in catalog.branch(CATALOG_LIBRARY, "/", 100)[0]
    }
    assert after == before

    entries = catalog.references(character["id"])
    assert [entry["node"] for entry in entries] == [picture["node_id"]]
    # The caption is the file's now, not the row's — a rename must not disturb
    # either, which is what this test is about.
    assert catalog.node(picture["node_id"])["description"] == "front"


def test_a_rename_swaps_the_claim_and_the_folder_name_together(empty_api, catalog_table):
    """The old claim must go, or the slug stays taken forever.

    Both halves in one transaction, so a rename that collides leaves the folder
    name alone too — the request either happened or did not.
    """
    character = _create(empty_api)

    empty_api.patch(f"/api/characters/{character['id']}", json={"slug": "subject-b", "rev": 1})

    assert _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", "CHARSLUG#subject-a") is None
    assert _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", "CHARSLUG#subject-b") is not None
    assert catalog.node(character["root"])["name"] == "subject-b"


def test_renaming_onto_a_taken_slug_is_409(empty_api):
    _create(empty_api, "subject-a")
    other = _create(empty_api, "subject-b")

    resp = empty_api.patch(
        f"/api/characters/{other['id']}", json={"slug": "subject-a", "rev": 1}
    )

    assert resp.status_code == 409
    assert empty_api.get(f"/api/characters/{other['id']}").get_json()["slug"] == "subject-b"


# ──────────────────────── the reference index ────────────────────────


def test_attaching_a_reference_writes_a_row_and_moves_no_bytes(empty_api, catalog_table):
    """**Reference-ness is a row and nothing else.**

    That is the coupling the whole entity model removes: an image is identity
    because a row says so, not because of which folder it sits in. So the file is
    not copied, not moved, and not required to live in `reference/` at all.
    """
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "corpus")["node_id"], "front.webp")

    resp = empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face", "tags": ["face", "daylight"]},
    )

    assert resp.status_code == 201
    row = _item(catalog_table, f"CHAR#{character['id']}", f"REF#{picture['node_id']}")
    assert row["group"]["S"] == "face"
    assert int(row["order"]["N"]) == 1000
    # Still in `corpus/`, still one node, still one blob.
    assert catalog.node(picture["node_id"])["parent_id"] == \
        _child(character["root"], "corpus")["node_id"]


def test_order_is_gapped_so_an_insert_touches_no_neighbour(empty_api):
    """**This is what kills filename magic.**

    Order was the trailing number in `<slug>_<group>_<n>.png`, so inserting
    between two references meant renaming a run of files — which is what
    `curate renumber` existed to do, and what made the bible's `references:` map
    go out of step with the folder.

    `after` takes the midpoint of two `order` values, so an insert is one write.
    """
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    first = _uploaded(empty_api, pool, "a.webp")
    second = _uploaded(empty_api, pool, "b.webp")
    middle = _uploaded(empty_api, pool, "c.webp")

    for node in (first, second):
        empty_api.post(
            f"/api/characters/{character['id']}/references",
            json={"node": node["node_id"], "group": "face"},
        )
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": middle["node_id"], "group": "face", "after": first["node_id"]},
    )

    entries = catalog.references(character["id"])
    assert [entry["node"] for entry in entries] == [
        first["node_id"],
        middle["node_id"],
        second["node_id"],
    ]
    assert [entry["order"] for entry in entries] == [1000, 1500, 2000]


def test_regrouping_is_one_write_and_moves_no_object(empty_api):
    """`curate regroup` used to move files between four pool folders.

    It is a `PATCH` on one row now, and the file does not move — which is the
    same claim as `attach`, made about the operation that used to be the most
    expensive one.
    """
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face"},
    )
    before = catalog.node(picture["node_id"])

    resp = empty_api.patch(
        f"/api/characters/{character['id']}/references/{picture['node_id']}",
        json={"group": "body"},
    )

    assert resp.status_code == 200
    assert catalog.references(character["id"])[0]["group"] == "body"
    assert catalog.node(picture["node_id"]) == before


def test_describing_many_references_is_one_transaction(empty_api):
    """`describe-refs` was twelve rewrites of one YAML document.

    Each one re-read an `updated_at` and refused if it had moved, so writing them
    concurrently was a conflict dance rather than a write. Now it is one
    transaction over twelve rows and two descriptions cannot fight.
    """
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    nodes = [_uploaded(empty_api, pool, f"{index}.webp") for index in range(3)]

    resp = empty_api.patch(
        f"/api/characters/{character['id']}/references",
        json={
            "entries": [
                {"node": node["node_id"], "group": "face", "description": f"shot {index}"}
                for index, node in enumerate(nodes)
            ]
        },
    )

    assert resp.status_code == 200
    # Two rows per entry — the set's `REF#` half and the file's own — written in
    # the same transaction, so the descriptions land on the nodes.
    assert [entry["description"] for entry in resp.get_json()["entries"]] == [
        "shot 0",
        "shot 1",
        "shot 2",
    ]
    assert [
        catalog.node(entry["node"])["description"]
        for entry in catalog.references(character["id"])
    ] == ["shot 0", "shot 1", "shot 2"]


def test_detaching_takes_the_node_out_of_the_default_set(empty_api):
    """The root cause of a set that names images nothing points at.

    Detaching only deleted the `REF#` row. The id stayed in `default_set`, where
    the selection route filtered it out without a word — so a re-shot reference
    left a stale id behind and a default shoot sent fewer images than somebody
    chose. Production carried four of these on one character.
    """
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    kept = _uploaded(empty_api, pool, "kept.webp")
    dropped = _uploaded(empty_api, pool, "dropped.webp")
    for node in (kept, dropped):
        empty_api.post(
            f"/api/characters/{character['id']}/references",
            json={"node": node["node_id"], "group": "face"},
        )
    empty_api.patch(
        f"/api/characters/{character['id']}/default-set",
        json={"nodes": [kept["node_id"], dropped["node_id"]], "rev": 1},
    )

    resp = empty_api.delete(
        f"/api/characters/{character['id']}/references/{dropped['node_id']}"
    )

    assert resp.status_code == 200
    assert resp.get_json()["default_set"] == [kept["node_id"]]
    assert catalog.entity(catalog.ENTITY_CHARACTER, character["id"])["default_set"] == [
        kept["node_id"]
    ]


def test_detaching_something_the_default_set_never_named_says_nothing(empty_api):
    """The key is present only when it changed, so a client need not diff."""
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    picture = _uploaded(empty_api, pool, "loose.webp")
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face"},
    )

    resp = empty_api.delete(
        f"/api/characters/{character['id']}/references/{picture['node_id']}"
    )

    assert resp.status_code == 200
    assert "default_set" not in resp.get_json()


def test_the_default_set_refuses_a_node_that_is_not_a_reference(empty_api):
    """The check that was missing is the one that would have caught the drift.

    The set names what a generation is SHOWN. A member with no `REF#` row is an
    image the selection route drops, so accepting one here is accepting a set
    that does not mean what it says.
    """
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    loose = _uploaded(empty_api, pool, "loose.webp")

    resp = empty_api.patch(
        f"/api/characters/{character['id']}/default-set",
        json={"nodes": [loose["node_id"]], "rev": 1},
    )

    assert resp.status_code == 400
    assert "not a reference" in resp.get_data(as_text=True)


def test_a_stale_default_set_is_refused_rather_than_quietly_shortened(empty_api):
    """Same rule as the cap refusal, and the same reason.

    Handing a model three of the seven images somebody chose is a result nobody
    can explain afterwards. The refusal names which ids went stale so the set can
    be re-pointed rather than guessed at.
    """
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    nodes = [_uploaded(empty_api, pool, f"{index}.webp") for index in range(2)]
    for node in nodes:
        empty_api.post(
            f"/api/characters/{character['id']}/references",
            json={"node": node["node_id"], "group": "face"},
        )
    empty_api.patch(
        f"/api/characters/{character['id']}/default-set",
        json={"nodes": [node["node_id"] for node in nodes], "rev": 1},
    )
    # Straight to the catalog: the route now refuses to CREATE this state, which
    # is the point — what is being tested is the read path over a library that
    # already carries it.
    record = catalog.entity(catalog.ENTITY_CHARACTER, character["id"])
    catalog.update_entity(
        catalog.ENTITY_CHARACTER, record, record["rev"],
        {"default_set": [nodes[0]["node_id"], "node-vanished"]},
    )

    resp = empty_api.get(f"/api/characters/{character['id']}/selection")

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "stale_default_set"
    assert [entry["node"] for entry in body["stale"]] == ["node-vanished"]


def test_a_tag_written_on_the_file_selects_it_as_a_reference(empty_api):
    """One store, two doors.

    Tags are the file's, so tagging a picture in the browser and tagging it in
    the reference grid have to be the same act — otherwise `--pick-tag` answers
    one of them and a person cannot tell which. This writes through the node
    route and selects through the character route.
    """
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    picture = _uploaded(empty_api, pool, "plate.webp")
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face"},
    )

    empty_api.patch(f"/api/nodes/{picture['node_id']}", json={"tags": ["Poolside"]})

    body = empty_api.get(
        f"/api/characters/{character['id']}/selection?tag=poolside"
    ).get_json()
    assert [entry["node"] for entry in body["selection"]] == [picture["node_id"]]


def test_attaching_the_same_node_twice_is_409(empty_api):
    """"Attach" and "describe" are different requests.

    The second is a `PATCH` on the same address and does not reset a group
    somebody has already chosen, so an overwrite here would silently undo it.
    """
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    body = {"node": picture["node_id"], "group": "face"}
    empty_api.post(f"/api/characters/{character['id']}/references", json=body)

    resp = empty_api.post(f"/api/characters/{character['id']}/references", json=body)

    assert resp.status_code == 409


def test_detaching_leaves_the_file_where_it_is(empty_api):
    """Detach removes an opinion about a file, not the file."""
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face"},
    )

    assert empty_api.delete(
        f"/api/characters/{character['id']}/references/{picture['node_id']}"
    ).status_code == 200

    assert catalog.references(character["id"]) == []
    assert catalog.node(picture["node_id"])["name"] == "a.webp"


def test_a_folder_cannot_be_a_reference(empty_api):
    character = _create(empty_api)

    resp = empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": _child(character["root"], "seed")["node_id"], "group": "face"},
    )

    assert resp.status_code == 400


def test_a_reference_survives_renaming_the_file_it_names(empty_api):
    """**The row names the node id, so the file can be called anything.**

    `<slug>_face_1.png` is dead: group and order are attributes and the
    description is a row, so a rename changes one name and nothing else.
    """
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face", "description": "kept"},
    )

    empty_api.patch(f"/api/nodes/{picture['node_id']}", json={"name": "anything-at-all.webp"})

    entries = catalog.references(character["id"])
    assert entries[0]["node"] == picture["node_id"]
    assert catalog.node(picture["node_id"])["description"] == "kept"


# ──────────────────────────── selection ────────────────────────────


def _with_references(empty_api, count, group="face", tags=("face",)):
    character = _create(empty_api)
    pool = _child(character["root"], "reference")["node_id"]
    for index in range(count):
        node = _uploaded(empty_api, pool, f"{index}.webp")
        empty_api.post(
            f"/api/characters/{character['id']}/references",
            json={"node": node["node_id"], "group": group, "tags": list(tags)},
        )
    return character


def test_selection_numbers_slots_from_one(empty_api):
    """Slot N still means "position N in the resolved selection".

    The definition did not change; the resolving moved into the API so the CLI
    and the SPA cannot disagree about what a model was shown.
    """
    character = _with_references(empty_api, 3)

    body = empty_api.get(f"/api/characters/{character['id']}/selection?tag=face").get_json()

    assert [entry["slot"] for entry in body["selection"]] == [1, 2, 3]
    assert body["source"] == "tag"


def test_an_over_cap_selection_is_refused_with_the_index_in_the_body(empty_api):
    """**Refused, never truncated**, and that is the behaviour being centralised.

    Silently handing a model the first seven of eighteen references is a shoot
    whose result nobody can explain afterwards. The refusal carries every
    candidate so the caller can choose rather than guess, and it carries a
    machine-readable code because the UI has to render a chooser rather than a
    sentence.
    """
    character = _with_references(empty_api, 3)

    resp = empty_api.get(f"/api/characters/{character['id']}/selection?tag=face&limit=2")

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "over_cap"
    assert len(body["index"]) == 3
    assert {entry["group"] for entry in body["index"]} == {"face"}


def test_an_engine_resolves_its_own_cap(empty_api):
    """The caps are a property of the engine family, not of one model id.

    The registry spells a family several ways — `nano-banana-pro`,
    `nano-banana-2` — and matching on a prefix is what keeps a new member of a
    family from silently losing its cap.
    """
    character = _with_references(empty_api, 8)

    assert empty_api.get(
        f"/api/characters/{character['id']}/selection?tag=face&engine=kling"
    ).status_code == 409
    assert empty_api.get(
        f"/api/characters/{character['id']}/selection?tag=face&engine=nano-banana-pro"
    ).status_code == 200


def test_a_selection_with_no_cap_named_cannot_be_refused(empty_api):
    """A caller that did not say what it was feeding cannot be told it fed too much."""
    character = _with_references(empty_api, 30)

    assert empty_api.get(
        f"/api/characters/{character['id']}/selection?tag=face"
    ).status_code == 200


def test_the_default_set_is_the_source_when_nothing_is_filtered(empty_api):
    """Small, **ordered**, and read on every generation — three properties a set
    of flags spread over forty rows has none of, which is why it is on the record.
    """
    character = _with_references(empty_api, 3)
    entries = catalog.references(character["id"])
    chosen = [entries[2]["node"], entries[0]["node"]]

    empty_api.patch(
        f"/api/characters/{character['id']}/default-set", json={"nodes": chosen, "rev": 1}
    )

    body = empty_api.get(f"/api/characters/{character['id']}/selection").get_json()
    assert body["source"] == "default"
    assert [entry["node"] for entry in body["selection"]] == chosen


# ──────────────────────────── the profile ────────────────────────────


def test_an_unknown_profile_section_is_refused(empty_api):
    """The shape is studio's now, so the SPA can render a form rather than a textarea.

    Validated by *section* and not field by field: what goes inside `face` is a
    description a person writes for a model to read, and a service enforcing its
    keys would refuse a character somebody wanted to describe differently.
    """
    character = _create(empty_api)

    resp = empty_api.patch(
        f"/api/characters/{character['id']}/profile",
        json={"profile": {"vibes": {}}, "rev": 1},
    )

    assert resp.status_code == 400


def test_a_section_that_is_a_string_where_a_map_belongs_is_refused(empty_api):
    """The one thing a client can get wrong without noticing.

    A merge of a paragraph over a structure is silent, and the next read hands the
    SPA a form field it cannot draw.
    """
    character = _create(empty_api)

    assert empty_api.patch(
        f"/api/characters/{character['id']}/profile",
        json={"profile": {"face": "a paragraph"}, "rev": 1},
    ).status_code == 400


def test_patching_the_profile_merges_at_section_level(empty_api):
    """Shallow on purpose — the deep merge is unreachable, not unimplemented.

    A deep merge would make *removing* a field impossible without a whole-document
    replace, which is the other half of this same route.
    """
    character = _create(
        empty_api, profile={"face": {"eyes": "green", "hair": "dark"}, "body": {"posture": "x"}}
    )

    empty_api.patch(
        f"/api/characters/{character['id']}/profile",
        json={"patch": {"face": {"eyes": "grey"}}, "rev": 1},
    )

    profile = empty_api.get(f"/api/characters/{character['id']}").get_json()["profile"]
    assert profile["face"] == {"eyes": "grey"}
    assert profile["body"] == {"posture": "x"}


def test_replacing_the_profile_takes_the_whole_document(empty_api):
    """The `studio character edit` round trip: read, edit a file, write it back."""
    character = _create(empty_api, profile={"face": {"eyes": "green"}})

    empty_api.patch(
        f"/api/characters/{character['id']}/profile",
        json={"profile": {"body": {"posture": "upright"}}, "rev": 1},
    )

    profile = empty_api.get(f"/api/characters/{character['id']}").get_json()["profile"]
    assert profile == {"body": {"posture": "upright"}}


def test_sending_a_replace_and_a_merge_together_is_400(empty_api):
    """Two operations on one address, told apart by which key the body carries.

    Sending both has two plausible orderings with different outcomes, and picking
    one silently is how somebody's paragraph disappears.
    """
    character = _create(empty_api)

    assert empty_api.patch(
        f"/api/characters/{character['id']}/profile",
        json={"profile": {}, "patch": {}, "rev": 1},
    ).status_code == 400


def test_the_textblock_is_served_on_its_own(empty_api):
    """A prompt fetches the paragraph without pulling the whole bible with it."""
    character = _create(
        empty_api, profile={"text_identity_block": "A tall figure in a grey coat."}
    )

    body = empty_api.get(f"/api/characters/{character['id']}/textblock").get_json()

    assert body["text"] == "A tall figure in a grey coat."
    # Nothing to compress from — the paragraph is already written.
    assert body["raw"] == {}


def test_an_unauthored_textblock_answers_with_the_raw_sections(empty_api):
    """The documented half of this route, which did not exist.

    `studio character textblock` reads `raw` and has since it was written; this
    route sent `{id, text}` alone, so the command printed `{}` and instructions.
    Only the authored path above was tested, which is how it survived.

    `rendering` and `voice` stay out: the paragraph exists for an engine with no
    reference system, and it is spent on what the character LOOKS like.
    """
    character = _create(
        empty_api,
        profile={
            "identity": {"apparent_age": "40s"},
            "face": {"eyes": "green"},
            "body": {"silhouette": "three heads at the shoulder"},
            "wardrobe": {"palette": "muted"},
            "consistency": {"must": ["the scar"]},
            "voice": {"accent": "flat"},
            "rendering": {"default_style": "Realistic"},
        },
    )

    body = empty_api.get(f"/api/characters/{character['id']}/textblock").get_json()

    assert body["text"] == ""
    assert set(body["raw"]) == {"identity", "face", "body", "wardrobe", "consistency"}
    assert body["raw"]["body"] == {"silhouette": "three heads at the shoulder"}


def test_the_unfilled_template_block_counts_as_no_block(empty_api):
    """`<>` is what the blank template leaves, and it must not reach a prompt.

    The CLI made this call itself, so the SPA was free to make the opposite one
    and paste a literal `<>` into a model. It is the route's decision now.
    """
    character = _create(
        empty_api,
        profile={"text_identity_block": "<>", "face": {"eyes": "green"}},
    )

    body = empty_api.get(f"/api/characters/{character['id']}/textblock").get_json()

    assert body["text"] == ""
    assert body["raw"] == {"face": {"eyes": "green"}}


def test_the_profile_route_takes_patch_and_nothing_else(empty_api):
    """Both clients sent `PUT` here, and neither could ever have been answered.

    Replace and merge share one address and are told apart by the body's key, so
    `PATCH` is the only verb registered — and `PUT` is not in `CORS_METHODS`
    either, which is where the SPA's write actually died. Every test in this file
    calls the route directly with the right verb, so nothing here noticed that
    the clients did not.

    Asserted against the url map and the CORS list rather than by sending a
    request: the test client re-raises `MethodNotAllowed` instead of rendering
    it, so a `405` assertion would be testing Flask's error propagation. These
    two are the facts a client actually collides with.
    """
    app = empty_api.application
    rule = next(r for r in app.url_map.iter_rules()
                if str(r) == "/api/characters/<addressed>/profile")

    assert rule.methods & {"PATCH", "PUT"} == {"PATCH"}
    assert "PUT" not in app_factory.CORS_METHODS


# ──────────────────────────── delete ────────────────────────────


def test_deleting_refuses_while_a_project_or_a_run_names_it(empty_api):
    """Those rows are what make "every run of this subject" answerable.

    Deleting the character out from under them leaves two questions with wrong
    answers, so the refusal names both counts and `?force=1` is the explicit
    "yes, and drop the links".
    """
    character = _create(empty_api)
    project = empty_api.post(
        "/api/projects", json={"slug": "rooftop-teaser", "characters": [character["id"]]}
    ).get_json()
    empty_api.post(
        "/api/runs",
        json={
            "project": project["id"],
            "slug": "rooftop-portrait",
            "kind": "image",
            "model": "google/nano-banana-pro",
            "characters": [character["id"]],
        },
    )

    resp = empty_api.delete(f"/api/characters/{character['id']}")

    assert resp.status_code == 409
    assert len(resp.get_json()["projects"]) == 1
    assert len(resp.get_json()["runs"]) == 1

    assert empty_api.delete(f"/api/characters/{character['id']}?force=1").status_code == 200


def test_deleting_keeps_the_files_by_default(empty_api, catalog_table):
    """**The reverse default loses media to a typo**, and nothing this service can
    do to S3 is undoable.

    The folder is orphaned into the library root with its `entity` cleared — an
    ordinary folder somebody can browse, rename or delete by hand. Clearing the
    pointer first is what stops `DELETE /api/nodes` refusing it forever.
    """
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")

    assert empty_api.delete(f"/api/characters/{character['id']}").status_code == 200

    assert _item(catalog_table, f"CHAR#{character['id']}", "META") is None
    assert _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", "CHARSLUG#subject-a") is None
    root = catalog.node(character["root"])
    assert "entity" not in root
    assert catalog.node(picture["node_id"])["name"] == "a.webp"
    assert empty_api.delete(f"/api/nodes/{character['root']}").status_code == 200


def test_deleting_with_files_delete_takes_the_tree_and_the_blobs(empty_api, media_bucket):
    """The explicit request, and the only path that may remove an entity's root."""
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    media_bucket.put_object(
        Bucket=config.media_bucket(), Key=picture["blob_key"], Body=b"webp-bytes"
    )

    assert empty_api.delete(
        f"/api/characters/{character['id']}?files=delete"
    ).status_code == 200

    assert catalog.children(CATALOG_ROOT) == []
    assert media_bucket.list_objects_v2(
        Bucket=config.media_bucket(), Prefix=picture["blob_key"]
    ).get("KeyCount") == 0


def test_deleting_a_character_removes_its_reference_rows(empty_api, catalog_table):
    """Everything in the entity's own partition goes with it.

    A `REF#` row outliving its character is a row nothing can reach and nothing
    collects — and it would come back to life if the id were ever reused.
    """
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    empty_api.post(
        f"/api/characters/{character['id']}/references",
        json={"node": picture["node_id"], "group": "face"},
    )

    empty_api.delete(f"/api/characters/{character['id']}")

    assert _item(catalog_table, f"CHAR#{character['id']}", f"REF#{picture['node_id']}") is None


# ──────────────────── the questions that had no answer ────────────────────


def test_which_projects_involve_this_character(empty_api):
    """**A question with no answer before, at any price.**

    Read backwards on `by-sk`, which is why that index stops having one script as
    its only consumer.
    """
    character = _create(empty_api)
    project = empty_api.post(
        "/api/projects", json={"slug": "rooftop-teaser", "characters": [character["id"]]}
    ).get_json()

    body = empty_api.get(f"/api/characters/{character['id']}/projects").get_json()

    assert [entry["id"] for entry in body] == [project["id"]]
    assert body[0]["slug"] == "rooftop-teaser"


def test_the_listing_counts_references_without_a_counter_on_the_record(empty_api):
    """One query per character, which is the honest cost of showing it.

    The alternative is a counter every attach and detach has to keep in step,
    which is the class of drift the claim rows deliberately avoid.
    """
    character = _with_references(empty_api, 2)

    listed = empty_api.get("/api/characters").get_json()

    assert [entry["id"] for entry in listed] == [character["id"]]
    assert listed[0]["counts"]["references"] == 2


def test_the_listing_filters_on_slug_and_display_name(empty_api):
    _create(empty_api, "subject-a", display_name="Alpha")
    _create(empty_api, "subject-b", display_name="Beta")

    assert [entry["slug"] for entry in empty_api.get("/api/characters?q=beta").get_json()] == [
        "subject-b"
    ]
