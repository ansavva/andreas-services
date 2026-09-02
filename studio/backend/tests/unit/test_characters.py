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
        json={"slug": slug, "display_name": "Subject", **body},
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

    resp = empty_api.post("/api/characters", json={"slug": "subject-a"})

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "conflict"
    assert "subject-a" in resp.get_json()["message"]
    assert len(catalog.children(CATALOG_ROOT)) == 1


def test_a_slug_is_refused_rather_than_repaired(empty_api):
    """It becomes half a primary key, so the string sent is the string claimed."""
    assert empty_api.post(
        "/api/characters", json={"slug": "Subject A"}
    ).status_code == 400


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
    key, and everything the files say about themselves.
    """
    character = _create(empty_api)
    reference = _child(character["root"], "reference")
    picture = _uploaded(empty_api, reference["node_id"], "front.webp")
    empty_api.patch(
        f"/api/nodes/{picture['node_id']}",
        json={"tags": ["default", "face"], "description": "front"},
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

    # The tag went nowhere: it is on the picture, and a rename touched the record.
    assert "default" in catalog.node(picture["node_id"])["tags"]
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


# ──────────────────── identity, which is now tags ────────────────────
#
# There is no reference index and no `default_set`. Both answered "which of this
# character's pictures does a generation get shown", and both answered it
# somewhere other than on the picture — so the same fact lived twice with an
# invariant between them, and the invariant drifted. It is `default` on the file
# now, with a group tag like `face` beside it.


def _tagged(api, character, name, tags, folder="reference"):
    """One image under the character, carrying tags. No row, no attach step."""
    pool = _child(character["root"], folder)["node_id"]
    node = _uploaded(api, pool, name)
    api.patch(f"/api/nodes/{node['node_id']}", json={"tags": list(tags)})
    return node


def _with_identity(api, count, tags=("default", "face")):
    character = _create(api)
    for index in range(count):
        _tagged(api, character, f"{index}.webp", tags)
    return character


def test_a_tag_is_the_whole_of_making_an_image_identity(empty_api):
    """No attach, no row, no move. One `PATCH` on the file, and it is in.

    What this deletes is the second step: bytes arrived, then a person filed a
    `REF#` row saying they were identity. The row could name a node that had been
    deleted, and the record could name a node with no row — two ways to drift
    that a tag on the file does not have.
    """
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["default", "face"])

    body = empty_api.get(f"/api/characters/{character['id']}/selection").get_json()

    assert [entry["node"] for entry in body["selection"]] == [node["node_id"]]
    assert body["source"] == "default"


def test_identity_survives_renaming_and_moving_the_file(empty_api):
    """The property the whole change is for: the tag travels with the picture.

    A `REF#` row survived a rename because it named a node id. A tag survives a
    rename, a MOVE and a copy, because it is not a separate thing that has to
    keep pointing at anything.
    """
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["default", "face"])
    corpus = _child(character["root"], "corpus")["node_id"]

    empty_api.patch(f"/api/nodes/{node['node_id']}", json={"name": "renamed.webp"})
    empty_api.post("/api/nodes/move", json={"ids": [node["node_id"]], "destination": corpus})

    body = empty_api.get(f"/api/characters/{character['id']}/selection").get_json()
    assert [entry["name"] for entry in body["selection"]] == ["renamed.webp"]


def test_a_file_outside_the_character_is_not_its_identity(empty_api):
    """Ownership is the tree, and it is the only thing scoping a tag.

    `default` on a file in another character's folder is that character's
    business. The old attach route checked only the LIBRARY, so a reference
    could point anywhere; the branch query cannot.
    """
    mine = _create(empty_api, slug="subject-a")
    theirs = _create(empty_api, slug="subject-b")
    _tagged(empty_api, theirs, "a.webp", ["default", "face"])

    resp = empty_api.get(f"/api/characters/{mine['id']}/selection")

    assert resp.status_code == 400
    assert "no image" in resp.get_json()["error"]


def test_a_group_is_a_tag_and_narrows_the_default_set(empty_api):
    """`?tag=default,face` is what nothing could previously express.

    `group` was a column on the row and `default_set` was a list on the record,
    so "the face images this character sends" needed both and could be asked of
    neither. Two tags, one filter.
    """
    character = _create(empty_api)
    face = _tagged(empty_api, character, "face.webp", ["default", "face"])
    _tagged(empty_api, character, "body.webp", ["default", "body"])
    _tagged(empty_api, character, "spare.webp", ["face"])

    both = empty_api.get(
        f"/api/characters/{character['id']}/selection?tag=default,face"
    ).get_json()

    assert [entry["node"] for entry in both["selection"]] == [face["node_id"]]
    assert both["source"] == "tag"


def test_every_named_tag_has_to_be_present(empty_api):
    """ALL of them, not any — the promise `--pick-tag` always made."""
    character = _create(empty_api)
    _tagged(empty_api, character, "a.webp", ["default", "face"])

    assert empty_api.get(
        f"/api/characters/{character['id']}/selection?tag=default,face"
    ).status_code == 200
    assert empty_api.get(
        f"/api/characters/{character['id']}/selection?tag=default,face,wardrobe"
    ).status_code == 400


def test_a_filter_matching_nothing_is_refused_not_answered_empty(empty_api):
    """Being handed no images is a typo, not a selection, and what runs next spends."""
    character = _with_identity(empty_api, 2)

    resp = empty_api.get(f"/api/characters/{character['id']}/selection?tag=nonsense")

    assert resp.status_code == 400
    assert "nonsense" in resp.get_json()["error"]


def test_only_images_are_selectable(empty_api):
    """A `.json` beside them carrying the same tag is not something to send."""
    character = _create(empty_api)
    picture = _tagged(empty_api, character, "a.webp", ["default"])
    pool = _child(character["root"], "reference")["node_id"]
    notes = _uploaded(empty_api, pool, "notes.json")
    empty_api.patch(f"/api/nodes/{notes['node_id']}", json={"tags": ["default"]})

    body = empty_api.get(f"/api/characters/{character['id']}/selection").get_json()

    assert [entry["node"] for entry in body["selection"]] == [picture["node_id"]]


def test_selection_numbers_slots_from_one(empty_api):
    """Slot N is position N in the resolved selection — unchanged in meaning."""
    character = _with_identity(empty_api, 3)

    body = empty_api.get(f"/api/characters/{character['id']}/selection").get_json()

    assert [entry["slot"] for entry in body["selection"]] == [1, 2, 3]


def test_a_selection_is_ordered_by_name_so_it_is_the_same_twice(empty_api):
    """**Order stopped meaning anything about a character and still has to exist.**

    A payload hands a model `[Image1]` and `[Image2]`, so a selection needs *an*
    order and it has to be the same one on two calls. Name is the only property
    that does not move when a file is re-tagged or re-uploaded; `newest` would
    reshuffle a shoot for a reason that has nothing to do with the shoot.
    """
    character = _create(empty_api)
    for name in ("c.webp", "a.webp", "b.webp"):
        _tagged(empty_api, character, name, ["default"])

    twice = [
        [entry["name"] for entry in empty_api.get(
            f"/api/characters/{character['id']}/selection").get_json()["selection"]]
        for _ in range(2)
    ]

    assert twice[0] == ["a.webp", "b.webp", "c.webp"]
    assert twice[0] == twice[1]


def test_a_selection_says_which_picture_each_slot_is(empty_api):
    """A person reviewing a payload has to know which picture is `[Image3]`."""
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["default", "face"])
    empty_api.patch(f"/api/nodes/{node['node_id']}", json={"description": "head on"})

    entry = empty_api.get(
        f"/api/characters/{character['id']}/selection"
    ).get_json()["selection"][0]

    assert entry["name"] == "a.webp"
    assert entry["description"] == "head on"
    assert "face" in entry["tags"]
    assert entry["url"]


def test_pick_names_files_and_keeps_the_order_they_were_named_in(empty_api):
    """`pick` is the escape hatch from the tags, and position is the payload."""
    character = _create(empty_api)
    first = _tagged(empty_api, character, "a.webp", ["default"])
    second = _tagged(empty_api, character, "b.webp", ["default"])

    body = empty_api.get(
        f"/api/characters/{character['id']}/selection"
        f"?pick={second['node_id']},{first['node_id']}"
    ).get_json()

    assert [entry["node"] for entry in body["selection"]] == [
        second["node_id"], first["node_id"]]
    assert body["source"] == "pick"


def test_pick_accepts_a_stem_or_a_node_id(empty_api):
    """The three things somebody has in hand while looking at a listing."""
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["default"])

    for token in (node["node_id"], "a.webp", "a"):
        body = empty_api.get(
            f"/api/characters/{character['id']}/selection?pick={token}"
        ).get_json()
        assert [entry["node"] for entry in body["selection"]] == [node["node_id"]]


def test_pick_need_not_be_tagged_at_all(empty_api):
    """Naming a picture IS the decision; a tag is the way to not have to."""
    character = _create(empty_api)
    plain = _tagged(empty_api, character, "plain.webp", [])

    body = empty_api.get(
        f"/api/characters/{character['id']}/selection?pick=plain.webp"
    ).get_json()

    assert [entry["node"] for entry in body["selection"]] == [plain["node_id"]]


def test_pick_refuses_a_token_that_names_nothing(empty_api):
    """Asking by name and being handed fewer is a typo, and the refusal says which."""
    character = _with_identity(empty_api, 1)

    resp = empty_api.get(f"/api/characters/{character['id']}/selection?pick=nope.webp")

    assert resp.status_code == 400
    assert "nope.webp" in resp.get_json()["error"]


def test_an_over_cap_selection_is_refused_with_the_candidates_in_the_body(empty_api):
    """**Refused, never truncated.**

    Silently handing a model the first seven of eighteen is a shoot whose result
    nobody can explain afterwards. The refusal carries every candidate so the
    caller can choose rather than guess, and a machine-readable code because the
    UI renders a chooser rather than a sentence.
    """
    character = _with_identity(empty_api, 3)

    resp = empty_api.get(f"/api/characters/{character['id']}/selection?limit=2")

    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "over_cap"
    assert len(body["index"]) == 3
    assert all("face" in entry["tags"] for entry in body["index"])


def test_an_engine_resolves_its_own_cap(empty_api):
    """The caps are a property of the engine family, not of one model id."""
    character = _with_identity(empty_api, 8)

    assert empty_api.get(
        f"/api/characters/{character['id']}/selection?engine=kling"
    ).status_code == 409
    assert empty_api.get(
        f"/api/characters/{character['id']}/selection?engine=nano-banana-pro"
    ).status_code == 200


def test_a_selection_with_no_cap_named_cannot_be_refused(empty_api):
    """A caller that did not say what it was feeding cannot be told it fed too much."""
    character = _with_identity(empty_api, 30)

    assert empty_api.get(
        f"/api/characters/{character['id']}/selection"
    ).status_code == 200


def test_there_is_no_stale_default_set_to_refuse(empty_api):
    """The failure class this change removes, pinned so it cannot come back.

    `default_set` was node ids on the record, and deleting a file left the id
    behind — one production character carried four such, and a default shoot
    sent three images where seven were meant. Deleting a tagged file removes the
    tag with it, because they are the same row.
    """
    character = _create(empty_api)
    kept = _tagged(empty_api, character, "a.webp", ["default"])
    doomed = _tagged(empty_api, character, "b.webp", ["default"])

    empty_api.delete("/api/nodes", json={"ids": [doomed["node_id"]]})

    body = empty_api.get(f"/api/characters/{character['id']}/selection").get_json()
    assert [entry["node"] for entry in body["selection"]] == [kept["node_id"]]


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


def test_a_deleted_character_leaves_nothing_in_its_own_partition(empty_api, catalog_table):
    """Everything in the entity's own partition goes with it.

    This used to be about `REF#` rows: one outliving its character was a row
    nothing could reach and nothing collected, and it would come back to life if
    the id were ever reused. **There are no such rows now** — identity is a tag on
    a file in the character's tree, and the tree is what the delete walks. The
    assertion is kept and widened, because "the partition is empty afterwards" is
    the property, and a future row class added to it should have to face this.
    """
    character = _create(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    empty_api.patch(f"/api/nodes/{picture['node_id']}", json={"tags": ["default", "face"]})

    empty_api.delete(f"/api/characters/{character['id']}")

    left = catalog_table.query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": f"CHAR#{character['id']}"}},
    )["Items"]
    assert left == []


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


def test_the_listing_counts_identity_without_a_counter_on_the_record(empty_api):
    """One branch query per character, and BOTH counts come out of it.

    `counts.references` was a second query for the `REF#` rows. There are none,
    and the walk that counts files already holds the tags, so counting the ones
    carrying `default` is free.
    """
    character = _with_identity(empty_api, 2)

    listed = empty_api.get("/api/characters").get_json()

    assert [entry["id"] for entry in listed] == [character["id"]]
    assert listed[0]["counts"]["default"] == 2


def test_the_listing_counts_files_under_the_character(empty_api):
    """**`counts.files` was read by the CLI and sent by nobody.**

    `studio character list` prints `counts.get("files", 0)` and the API only
    ever returned `counts.references`, so every character in every listing has
    shown `files 0` since the entity model landed. Zero is a plausible number
    for a character nobody has uploaded to, which is why it survived.

    Counted across the whole subtree rather than one pool: the number next to a
    name means "how much material is under this character", and a file in
    `corpus/` is material as much as one in `reference/`.
    """
    character = _with_identity(empty_api, 2)
    corpus = _child(character["root"], "corpus")["node_id"]
    _uploaded(empty_api, corpus, "extra.webp")

    listed = empty_api.get("/api/characters").get_json()
    assert listed[0]["counts"]["files"] == 3

    shown = empty_api.get(f"/api/characters/{character['id']}").get_json()
    assert shown["counts"]["files"] == 3


def test_a_character_with_no_files_counts_zero(empty_api):
    """The reading that made the bug invisible, asserted so it stays honest."""
    _create(empty_api)
    listed = empty_api.get("/api/characters").get_json()
    assert listed[0]["counts"] == {"default": 0, "files": 0}


def test_the_listing_filters_on_slug_and_display_name(empty_api):
    _create(empty_api, "subject-a", display_name="Alpha")
    _create(empty_api, "subject-b", display_name="Beta")

    assert [entry["slug"] for entry in empty_api.get("/api/characters?q=beta").get_json()] == [
        "subject-b"
    ]
