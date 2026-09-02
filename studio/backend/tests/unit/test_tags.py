"""The two tag vocabularies: derived, separate, and renameable everywhere at once.

A tag used to be free text on one item — typed into a box, comma-separated, and
invisible to whoever typed the next one. That is a vocabulary nobody can see,
which is a vocabulary everybody spells differently.
"""

from studio_core.services import catalog


def _create(api, slug="subject-a"):
    resp = api.post("/api/characters", json={"slug": slug, "display_name": "Subject"})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _tagged(api, character, name, tags):
    pool = catalog.node(catalog.child_by_name(character["root"], "reference")["node_id"])
    node = api.post(
        "/api/nodes", json={"parent": pool["node_id"], "name": name, "kind": "file"}
    ).get_json()
    record = catalog.node(node["id"])
    catalog.set_blob(node["id"], record["blob_key"], size=8, content_type="image/webp")
    api.patch(f"/api/nodes/{node['id']}", json={"tags": list(tags)})
    return node["id"]


def _template(api, template_id, tags):
    resp = api.patch(f"/api/templates/{template_id}", json={
        "name": template_id, "prompt": "{block.x}",
        "description": "what it makes", "tags": list(tags),
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)


def _tags(api, scope):
    return api.get(f"/api/tags?scope={scope}").get_json()["tags"]


# ──────────────────────── the vocabulary is what is used ────────────────────────


def test_a_tag_exists_because_something_carries_it(empty_api):
    """**Derived, not stored**, which is what makes the deletion rule honest.

    There is no `TAG#` row, so "a tag with nothing carrying it" is not a state
    that can be reached — and "delete a tag when nothing references it" is the
    definition rather than a sweep that can fall behind.
    """
    character = _create(empty_api)
    _tagged(empty_api, character, "a.webp", ["default", "face"])

    assert [tag["name"] for tag in _tags(empty_api, "file")] == ["default", "face"]


def test_the_count_is_how_many_things_carry_it(empty_api):
    """What makes a delete answerable before it happens.

    "Remove `studio` from 43 files" is a different press from "remove it from
    1", and the list is where that number has to be.
    """
    character = _create(empty_api)
    _tagged(empty_api, character, "a.webp", ["face"])
    _tagged(empty_api, character, "b.webp", ["face", "body"])

    assert _tags(empty_api, "file") == [
        {"name": "body", "count": 1},
        {"name": "face", "count": 2},
    ]


def test_files_and_templates_keep_separate_vocabularies(empty_api):
    """**`face` on a picture and `face` on a template are different things.**

    One says what a photograph shows; the other says what a prompt is for.
    Offering a file's words while somebody edits a template would suggest a
    vocabulary that means nothing there.
    """
    character = _create(empty_api)
    _tagged(empty_api, character, "a.webp", ["photographed"])
    _template(empty_api, "face_front", ["authored"])

    assert [tag["name"] for tag in _tags(empty_api, "file")] == ["photographed"]
    assert [tag["name"] for tag in _tags(empty_api, "template")] == ["authored"]


def test_a_scope_nobody_named_is_refused(empty_api):
    """Not defaulted. The two lists are different, so guessing one is a wrong answer."""
    assert empty_api.get("/api/tags").status_code == 400
    assert empty_api.get("/api/tags?scope=everything").status_code == 400


# ──────────────────────────────── renaming ────────────────────────────────


def test_a_rename_reaches_every_carrier(empty_api):
    """**The name is the identity**, so half a rename is two tags.

    A filter passes the name, the CLI passes it, a stored row holds it — there
    is no id underneath to re-point. Leaving one carrier behind would leave
    somebody believing they have one tag while the filter finds half of it.
    """
    character = _create(empty_api)
    first = _tagged(empty_api, character, "a.webp", ["face"])
    second = _tagged(empty_api, character, "b.webp", ["face", "studio"])

    resp = empty_api.patch("/api/tags/face?scope=file", json={"name": "portrait"})

    assert resp.status_code == 200
    assert resp.get_json()["changed"] == 2
    assert catalog.node(first)["tags"] == ["portrait"]
    assert catalog.node(second)["tags"] == ["portrait", "studio"]


def test_a_rename_onto_an_existing_tag_merges_rather_than_duplicating(empty_api):
    """Renaming `face` to `body` on something already carrying `body` leaves one."""
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["face", "body"])

    empty_api.patch("/api/tags/face?scope=file", json={"name": "body"})

    assert catalog.node(node)["tags"] == ["body"]


def test_a_rename_is_folded_the_way_every_other_tag_is(empty_api):
    """`Face ` and `face` are the same tag, or the filter finds one and not the other."""
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["face"])

    empty_api.patch("/api/tags/face?scope=file", json={"name": "  Three  Quarter "})

    assert catalog.node(node)["tags"] == ["three quarter"]


def test_a_rename_does_not_cross_scopes(empty_api):
    """The two lists never touch, and this is where that would break first."""
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["face"])
    _template(empty_api, "face_front", ["face"])

    empty_api.patch("/api/tags/face?scope=template", json={"name": "portrait"})

    assert catalog.node(node)["tags"] == ["face"]
    assert [tag["name"] for tag in _tags(empty_api, "template")] == ["portrait"]


def test_renaming_a_tag_nothing_carries_changes_nothing(empty_api):
    _create(empty_api)
    resp = empty_api.patch("/api/tags/nobody?scope=file", json={"name": "somebody"})
    assert resp.status_code == 200
    assert resp.get_json()["changed"] == 0


# ──────────────────────────────── deleting ────────────────────────────────


def test_deleting_a_tag_is_taking_it_off_everything(empty_api):
    """**That is the whole of the delete.**

    The vocabulary is what is in use, so there is no row left to collect and no
    state where the tag exists and nothing has it.
    """
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["face", "studio"])

    resp = empty_api.delete("/api/tags/studio?scope=file")

    assert resp.status_code == 200
    assert resp.get_json()["changed"] == 1
    assert catalog.node(node)["tags"] == ["face"]
    assert [tag["name"] for tag in _tags(empty_api, "file")] == ["face"]


def test_the_last_carrier_losing_a_tag_deletes_it(empty_api):
    """The rule, stated as the thing that happens rather than as a sweep."""
    character = _create(empty_api)
    node = _tagged(empty_api, character, "a.webp", ["face", "only-here"])
    assert "only-here" in [tag["name"] for tag in _tags(empty_api, "file")]

    empty_api.patch(f"/api/nodes/{node}", json={"tags": ["face"]})

    assert "only-here" not in [tag["name"] for tag in _tags(empty_api, "file")]


def test_a_template_tag_survives_deleting_the_file_tag_of_the_same_name(empty_api):
    character = _create(empty_api)
    _tagged(empty_api, character, "a.webp", ["face"])
    _template(empty_api, "face_front", ["face"])

    empty_api.delete("/api/tags/face?scope=file")

    assert _tags(empty_api, "file") == []
    assert [tag["name"] for tag in _tags(empty_api, "template")] == ["face"]
