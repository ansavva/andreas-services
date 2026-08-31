"""The reference spec as rows, and drafting a turnaround from them.

Both halves of what made a reference render reachable from the app: the prose
lives in the catalog rather than in the pipeline package, and there is a route
that assembles it against a character and writes the drafts.
"""

from studio_core import config
from tests.conftest import CATALOG_LIBRARY

BLOCK = "THE FACE COMES FROM THE REFERENCE IMAGES. Study the nose."

ANGLE = {
    "group": "face",
    "prompt": "A studio portrait, front on. {face_only} {top}",
    "description": "Head and shoulders, front on.",
    "tags": ["face", "front"],
    "order": 1000,
}

PROFILE = {
    "identity": {"apparent_age": "Late 30s", "height_read": "5'10\""},
    "wardrobe": {"tops": [{"item": "polo shirt", "colour": "white"}]},
    "body": {"silhouette": "Broad shoulders."},
    "consistency": {"must": ["A long straight nose"]},
    "rendering": {"default_style": "Realistic"},
}


def _item(client, pk, sk):
    return client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    ).get("Item")


def _spec(api):
    api.patch("/api/reference-spec/blocks/face_only", json={"text": BLOCK})
    return api.patch("/api/reference-spec/angles/face_front", json=ANGLE)


# ───────────────────────────── the rows ─────────────────────────────


def test_a_first_block_needs_no_document_to_exist_first(empty_api, catalog_table):
    """The same property the phrasebook gained by becoming rows.

    A spec held as one YAML blob has to be created before it can be edited, so
    the first write in a fresh library is a special case. A first block is just
    a first row.
    """
    resp = empty_api.patch("/api/reference-spec/blocks/face_only", json={"text": BLOCK})

    assert resp.status_code == 200
    assert _item(catalog_table, f"LIB#{CATALOG_LIBRARY}",
                 "SPEC#BLOCK#face_only")["text"]["S"] == BLOCK


def test_the_whole_spec_comes_back_in_one_read(empty_api):
    _spec(empty_api)
    got = empty_api.get("/api/reference-spec").get_json()

    assert got["blocks"]["face_only"] == BLOCK
    assert [a["id"] for a in got["angles"]] == ["face_front"]
    assert got["angles"][0]["tags"] == ["face", "front"]


def test_an_angle_must_carry_a_description_and_tags(empty_api):
    """They are written onto a promoted image by `add-refs --from-run`.

    An angle missing them promotes UNDESCRIBED, which is the state the described
    index exists to prevent — and nobody notices until a selection by tag comes
    back short.
    """
    for missing in ("description", "tags"):
        body = {k: v for k, v in ANGLE.items() if k != missing}
        resp = empty_api.patch("/api/reference-spec/angles/face_front", json=body)
        assert resp.status_code == 400, missing
        assert missing in resp.get_json()["error"].lower()


def test_a_name_holding_the_key_separator_is_refused(empty_api):
    resp = empty_api.patch("/api/reference-spec/blocks/face%23only", json={"text": "x"})
    assert resp.status_code == 400


def test_angles_come_back_in_the_order_they_are_shot(empty_api):
    empty_api.patch("/api/reference-spec/angles/body_front",
                    json={**ANGLE, "group": "body", "order": 2000})
    empty_api.patch("/api/reference-spec/angles/face_front", json=ANGLE)
    got = empty_api.get("/api/reference-spec").get_json()
    assert [a["id"] for a in got["angles"]] == ["face_front", "body_front"]


# ────────────────────────── assembling a prompt ──────────────────────────


def test_assembly_fills_a_template_from_the_bible(empty_api):
    from studio_core.services import reference

    text = reference.assemble({"id": "face_front", **ANGLE}, {"face_only": BLOCK},
                              PROFILE, identity_positions=[1, 2])
    assert BLOCK in text
    assert "plain white polo shirt" in text


def test_a_template_citing_a_block_nobody_wrote_names_what_was_available():
    """The likeliest failure now that the spec is editable.

    Somebody deletes a block an angle still cites. The useful answer is the list
    of names they could have meant, not a stack trace.
    """
    from studio_core.errors import ValidationError
    from studio_core.services import reference

    try:
        reference.assemble({"id": "face_front", "group": "face",
                            "prompt": "{no_such_block}"}, {}, PROFILE)
    except ValidationError as exc:
        assert "no_such_block" in str(exc)
        assert "Available:" in str(exc)
    else:
        raise AssertionError("a missing placeholder must be refused")


def test_a_stray_brace_in_edited_prose_is_a_400_not_a_500():
    """The whole input to this route is a person's typing.

    `vformat` raises IndexError/ValueError for a stray brace rather than
    KeyError, and unhandled those surface as a server error on the one route
    where a typo is the expected case.
    """
    from studio_core.errors import ValidationError
    from studio_core.services import reference

    for broken in ("a { b", "a } b", "{}"):
        try:
            reference.assemble({"id": "x", "group": "face", "prompt": broken},
                               {}, PROFILE)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"{broken!r} should be refused")


def test_the_slots_phrase_reads_as_english():
    from studio_core.services import reference

    assert reference.slots_phrase([2]) == "[Image2]"
    assert reference.slots_phrase([2, 3]) == "[Image2] and [Image3]"
    assert reference.slots_phrase([2, 3, 4]) == "[Image2], [Image3] and [Image4]"


def test_a_face_angle_leaves_out_what_sits_below_the_crop():
    """A face angle crops at mid-chest, so legs and body hair are noise in it."""
    from studio_core.services import reference

    profile = {**PROFILE, "body": {"silhouette": "Broad.", "lower_body": "Heavy thighs.",
                                   "body_hair": "Dark."}}
    assert "Heavy thighs." not in reference.build_text(profile, "face")
    assert "Heavy thighs." in reference.build_text(profile, "body")


def test_the_height_number_is_sent_and_comes_first():
    """The one proportion the bible states as a NUMBER, and it was never sent.

    The build clause read the `body:` block alone, so a corrected `height_read`
    sat unused while the prompt argued the point in adjectives. A figure on a
    plain backdrop has no scale of its own.
    """
    from studio_core.services import reference

    assert reference.build_text(PROFILE, "face").startswith("5'10\"")


# ─────────────────────── drafting a turnaround ───────────────────────


def _character_with_bible(api, slug="subject-a"):
    made = api.post("/api/characters", json={"slug": slug, "profile": PROFILE}).get_json()
    return made


def _seed_node(api, character, name="seed-1.jpg"):
    """One file node under the character, standing in for a seed photograph.

    Confirmed with a blob, because a send names a node the API will presign —
    `validate_sends` refuses one that has no bytes, which is hard rule #3 held
    at the moment it can actually be broken.
    """
    from studio_core.services import catalog as cat

    seed = api.post("/api/nodes",
                    json={"parent": character["root"], "name": "seedpool",
                          "kind": "folder"}).get_json()
    node = api.post("/api/nodes",
                    json={"parent": seed["id"], "name": name,
                          "kind": "file"}).get_json()
    record = cat.node(node["id"])
    cat.set_blob(node["id"], record["blob_key"], size=8, content_type="image/jpeg")
    return node["id"]


def test_a_turnaround_drafts_one_run_per_angle(empty_api):
    """The whole point: a reference render started by something that is not a terminal."""
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)

    resp = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "identity": [node]},
    )

    assert resp.status_code == 201, resp.get_json()
    drafted = resp.get_json()["drafted"]
    assert [d["angle"] for d in drafted] == ["face_front"]
    assert drafted[0]["status"] == "draft"
    assert not resp.get_json()["failed"]


def test_a_drafted_turnaround_is_unapproved_and_carries_the_assembled_prompt(empty_api):
    """Drafting is not approving, and hard rule #2 is untouched by this route."""
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)

    made = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "identity": [node]},
    ).get_json()["drafted"][0]

    run = empty_api.get(f"/api/runs/{made['id']}").get_json()
    assert run["status"] == "draft"
    assert run["approval"] is None
    assert BLOCK in run["plan"]["prompt"]
    assert "plain white polo shirt" in run["plan"]["prompt"]
    # The identity image is a SEND, never part of the plan — it is presigned in
    # at the last moment, which is hard rule #3.
    assert "identity" not in run["plan"]
    assert run["plan"]["params"]["aspect_ratio"] == "2:3"


def test_identity_images_are_given_never_guessed(empty_api):
    """Which photographs say who somebody is is not this route's decision."""
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()

    resp = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"]},
    )
    assert resp.status_code == 400
    assert "identity" in resp.get_json()["error"]


def test_a_turnaround_needs_a_project(empty_api):
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    node = _seed_node(empty_api, character)
    resp = empty_api.post(f"/api/characters/{character['id']}/turnaround",
                          json={"identity": [node]})
    assert resp.status_code == 400
    assert "project" in resp.get_json()["error"]


def test_one_bad_angle_does_not_cancel_the_rest(empty_api):
    """A failure is almost always a property of that angle alone.

    Aborting on the first cost a live turnaround six healthy angles once,
    because the failing one happened to sort first.
    """
    _spec(empty_api)
    empty_api.patch("/api/reference-spec/angles/face_broken",
                    json={**ANGLE, "prompt": "{no_such_block}", "order": 1500})
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)

    got = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "identity": [node]},
    ).get_json()

    assert [d["angle"] for d in got["drafted"]] == ["face_front"]
    assert [f["angle"] for f in got["failed"]] == ["face_broken"]
    assert "no_such_block" in got["failed"][0]["error"]


def test_a_group_filter_selects_only_that_half(empty_api):
    _spec(empty_api)
    empty_api.patch("/api/reference-spec/angles/body_front",
                    json={**ANGLE, "group": "body", "order": 2000})
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)

    got = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "identity": [node], "group": "body"},
    ).get_json()
    assert [d["angle"] for d in got["drafted"]] == ["body_front"]


def test_a_library_with_no_spec_says_so_rather_than_drafting_nothing(empty_api):
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)
    resp = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "identity": [node]},
    )
    assert resp.status_code == 404
    assert "spec push" in resp.get_json()["error"]
