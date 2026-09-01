"""The reference spec as rows, and drafting a turnaround from them.

Both halves of what made a reference render reachable from the app: the prose
lives in the catalog rather than in the pipeline package, and there is a route
that assembles it against a character and writes the drafts.
"""

import pytest

from studio_core import config
from studio_core.errors import ValidationError
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

    # Labelled and first — see `test_the_build_arrives_as_one_LABELLED_line_per_field`
    # for why every field is now on a line of its own.
    assert reference.build_text(PROFILE, "face").startswith("- Height: 5'10\"")


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

    # Reused, not recreated: a second call would collide on the folder name and
    # the failure surfaces as a KeyError on the FILE, several lines away.
    made = api.post("/api/nodes",
                    json={"parent": character["root"], "name": "seedpool",
                          "kind": "folder"}).get_json()
    seed = made if "id" in made else next(
        n for n in api.get(f"/api/nodes?parent={character['root']}").get_json()
        if n["name"] == "seedpool")
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


def test_a_PREVIEW_needs_neither_a_project_nor_a_single_photograph(empty_api):
    """**Both guards are about drafting, and previewing is not drafting.**

    The SPA assembles a preview on every change so a person can read what an
    angle would say while they are still choosing. Requiring what a draft
    requires made that impossible: the words could not be seen until after every
    decision they exist to inform. A preview writes nothing, so there is no run
    to put in a project and no half-finished shoot to prevent — with no
    photographs the prompt simply cites no identity slots, which is a true
    answer to "what would this say so far".
    """
    _spec(empty_api)
    character = _character_with_bible(empty_api)

    resp = empty_api.post(f"/api/characters/{character['id']}/turnaround",
                          json={"preview": True})

    assert resp.status_code == 200
    got = resp.get_json()
    assert BLOCK in got["preview"][0]["plan"]["prompt"]
    assert got["preview"][0]["sends"] == []


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


def test_a_preview_assembles_and_writes_nothing(empty_api):
    """The CLI's `--dry-run` and the SPA's live editor ask the same question.

    Answering it twice would be two assemblies to keep in step. It stops before
    the write, so it is safe on every keystroke — the property
    `POST /api/prompt` is built around.
    """
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)

    resp = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "identity": [node], "preview": True},
    )

    assert resp.status_code == 200          # not 201: nothing was created
    got = resp.get_json()
    assert BLOCK in got["preview"][0]["plan"]["prompt"]
    assert "drafted" not in got
    # And no run exists.
    assert empty_api.get(f"/api/runs?project={project['id']}").get_json()["runs"] == []


def test_a_block_may_not_be_named_something_no_template_could_cite(empty_api):
    """**A block is cited as `{block.<name>}`, and a dot is attribute access.**

    `#` was the only refusal, which let somebody create `2fast` or `a-b`: rows
    that exist, appear in the insert menu, and fail the moment a template names
    them.
    """
    _spec(empty_api)
    # No `#`: it is a URL fragment, so it never reaches the route to be judged.
    for bad in ("2fast", "a-b", "Caps", "with space"):
        resp = empty_api.patch(f"/api/reference-spec/blocks/{bad}",
                               json={"text": "prose"})
        assert resp.status_code == 400, bad

    assert empty_api.patch("/api/reference-spec/blocks/_ok_1",
                           json={"text": "prose"}).status_code == 200


# ─────────────────────────── the anchor ───────────────────────────


def test_an_anchored_pass_binds_the_anchor_FIRST_for_every_angle(empty_api):
    """**A turnaround is not N independent shoots, and shooting it as one was
    what produced fourteen different shirts.**

    Every hand-authored production set was made as one anchor and then the rest
    chained off it, each binding the anchor's output first. `[Image1]` is what
    the `anchor` block names, so the position is part of the contract rather
    than a coincidence of ordering.
    """
    _spec(empty_api)
    empty_api.patch("/api/reference-spec/angles/face_back", json={**ANGLE, "order": 1500})
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)

    got = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "anchor": "node-anchor",
              "identity_by_angle": {"face_front": [node], "face_back": [node]},
              "preview": True},
    ).get_json()

    for entry in got["preview"]:
        assert [s["node"] for s in entry["sends"]] == ["node-anchor", node]


def test_the_anchor_is_not_bound_TWICE_when_it_is_also_picked(empty_api):
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    node = _seed_node(empty_api, character)

    got = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"anchor": node, "identity_by_angle": {"face_front": [node]},
              "preview": True},
    ).get_json()
    assert [s["node"] for s in got["preview"][0]["sends"]] == [node]


def test_the_anchor_SENTENCE_appears_only_on_an_anchored_pass(empty_api):
    """**Empty rather than absent, so one template is right in both phases.**

    The first shot of a set has no anchor and must not carry the sentence; every
    later one must. A template citing `{slot.anchor}` is correct either way, and
    the words are the `anchor` block's — the code decides only whether.
    """
    _spec(empty_api)
    empty_api.patch("/api/reference-spec/blocks/anchor",
                    json={"text": "Match the wardrobe and the background of [Image1]."})
    empty_api.patch("/api/reference-spec/angles/face_front",
                    json={**ANGLE, "prompt": "Front on. {slot.anchor}"})
    character = _character_with_bible(empty_api)
    node = _seed_node(empty_api, character)

    def prompt(**extra):
        got = empty_api.post(f"/api/characters/{character['id']}/turnaround",
                             json={"identity": [node], "preview": True, **extra}).get_json()
        return got["preview"][0]["plan"]["prompt"]

    assert prompt() == "Front on."
    assert prompt(anchor="node-anchor").endswith(
        "Match the wardrobe and the background of [Image1].")


def test_an_anchor_alone_is_enough_to_shoot(empty_api):
    """Phase two picks nothing new: the anchor IS the identity for the rest of
    the set, so requiring a per-angle selection as well would make the chained
    pass impossible to express."""
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()

    resp = empty_api.post(f"/api/characters/{character['id']}/turnaround",
                          json={"project": project["id"], "anchor": "node-anchor"})
    assert resp.status_code == 201


def test_a_malformed_anchor_is_refused(empty_api):
    _spec(empty_api)
    character = _character_with_bible(empty_api)
    resp = empty_api.post(f"/api/characters/{character['id']}/turnaround",
                          json={"anchor": "run-not-a-node", "preview": True})
    assert resp.status_code == 400
    assert "anchor" in resp.get_json()["error"]


# ──────────────────── the build, as labelled fields ────────────────────


def test_the_build_arrives_as_one_LABELLED_line_per_field():
    """**The run-on paragraph is what a turned body angle could not read.**

    This joined every body field with a space. The hand-authored body prompts
    that actually worked did not: each field arrived named and on its own line.
    Which field a sentence belongs to is information the bible has, and the
    run-on form threw it away — "the chest curves out in side view" only reads
    as an instruction about the chest when it is labelled as one, and a wall of
    unattributed sentences is what produced a flat side profile from a good
    front one.
    """
    from studio_core.services import reference

    text = reference.build_text({
        "identity": {"height_read": "A head above most people"},
        "body": {"silhouette": "A broad wedge",
                 "chest_and_shoulders": "Full square chest, capped deltoids",
                 "lower_body": "Heavy thighs"},
    }, "body")

    assert text.splitlines() == [
        "- Height: A head above most people",
        "- Silhouette: A broad wedge",
        "- Chest and shoulders: Full square chest, capped deltoids",
        "- Lower body: Heavy thighs",
    ]


def test_a_field_the_bible_gains_tomorrow_is_labelled_without_an_edit_here():
    """The label is the bible's own key. A hard-coded map would silently drop
    the field the day somebody writes a new one — which is the failure
    `_extra_body_fields` already exists to prevent."""
    from studio_core.services import reference

    text = reference.build_text({"body": {"scars": "A pale line above the left knee"}},
                                "body")
    assert "- Scars: A pale line above the left knee" in text


def test_a_face_angle_still_sees_nothing_below_the_crop():
    """A face angle crops at mid-chest, so a leg is noise in its prompt."""
    from studio_core.services import reference

    text = reference.build_text({"body": {"chest_and_shoulders": "Full square chest",
                                          "lower_body": "Heavy thighs"}}, "face")
    assert "Chest and shoulders" in text
    assert "Lower body" not in text


# ─────────────────────── namespaced placeholders ───────────────────────


def _assemble(template, blocks=None, **kw):
    from studio_core.services import reference
    return reference.assemble({"id": "face_front", "group": "face", "prompt": template},
                              blocks if blocks is not None else {"face_only": BLOCK},
                              PROFILE, **kw)


def test_a_namespaced_placeholder_says_where_it_comes_from():
    """**The point of the dotted spelling.** A reader of an assembled prompt
    wants to know which words they can go and change, and a bare `{top}` does
    not say whether that is a block or the character's bible."""
    text = _assemble("{block.face_only} | {character.style} | {slot.identity}",
                     identity_positions=[2, 3])
    assert text == f"{BLOCK} | Realistic. | [Image2] and [Image3]"


def test_the_bare_spelling_still_resolves_exactly_as_it_did():
    """Every template written so far uses it, and the assembled OUTPUT is
    identical either way — the digest hashes the prompt, not the template — so
    moving a template over stales no approval and there is no flag day."""
    assert _assemble("{face_only}") == _assemble("{block.face_only}")


def test_a_bare_name_TWO_things_answer_to_is_refused_rather_than_resolved():
    """**It used to resolve, and which one won was invisible.**

    Blocks were spread into one flat mapping and the computed values overwrote
    them, so a block named `top` lost to the bible every single time and nothing
    anywhere said so. The dotted spelling makes the question answerable, so the
    ambiguous bare one can be an error that names both readings.
    """
    with pytest.raises(ValidationError) as refusal:
        _assemble("{top}", {"top": "A BLOCK CALLED TOP"})
    assert "{block.top}" in str(refusal.value)
    assert "{character.top}" in str(refusal.value)


def test_the_two_readings_are_both_reachable_once_they_are_spelled_out():
    text = _assemble("{block.top} :: {character.top}", {"top": "A BLOCK CALLED TOP"})
    assert text.startswith("A BLOCK CALLED TOP :: Wearing a plain")


def test_a_block_that_collides_is_fine_as_long_as_no_angle_cites_it_bare():
    """The refusal is per TEMPLATE, not per block. A block named `top` that
    every angle addresses as `{block.top}` is unambiguous and works."""
    assert _assemble("{block.face_only}", {"face_only": BLOCK, "top": "unused"})


def test_there_is_no_plate_slot_left_to_collide_with():
    """**The nastiest collision, removed at the root rather than disambiguated.**

    `angle_slot` was added AFTER the blocks were spread in and only when the
    angle bound a plate, so a block of that name won on an angle with no plate
    and lost on one with a plate — the same words rendering differently for a
    reason nothing in the template mentioned. Plates are gone entirely (they
    distorted the thing they existed to record), so the slot they filled is gone
    with them and a block may be called `angle_slot` with nothing to fight.
    """
    assert _assemble("{block.angle_slot}", {"angle_slot": "A BLOCK"}) == "A BLOCK"
    with pytest.raises(ValidationError):
        _assemble("{slot.angle}")


def test_a_MISTYPED_member_is_a_refusal_and_not_a_500():
    """A dot in a format field is attribute access, so a missing member raises
    `AttributeError` where a missing key raises `KeyError`. Unhandled it reaches
    a person as a 500 on a route whose whole input is their own typing."""
    with pytest.raises(ValidationError) as refusal:
        _assemble("{character.tops}")
    assert "tops" in str(refusal.value)
    # And it says what the namespace DOES hold.
    assert "character has:" in str(refusal.value)


def test_a_namespace_that_does_not_exist_names_what_does():
    with pytest.raises(ValidationError) as refusal:
        _assemble("{wardrobe.top}")
    assert "wardrobe" in str(refusal.value)


# ─────────────────── whitespace, and per-angle identity ───────────────────


def test_the_prompt_keeps_its_newlines():
    """**They were being destroyed, and that cost the best prompt this repo has.**

    Assembly ended `" ".join(text.split())`, which collapses every newline into
    a space. Right while the source was a folded YAML scalar — a line break
    there is how the file wrapped, not something anybody chose — and wrong the
    moment the source became a row a person types into a box.

    The single best-performing reference render this repository has produced was
    authored by hand with six newlines in its prompt, separating the angle, the
    scale and the identity instruction into paragraphs. Assembled through the
    old path it came out as one wall of text, so the pipeline could not
    reproduce its own best result.
    """
    from studio_core.services import reference

    template = "First line.\n\nSecond paragraph. {face_only}\n\nThird."
    text = reference.assemble({"id": "x", "group": "face", "prompt": template},
                              {"face_only": BLOCK}, PROFILE)
    assert text.count("\n\n") == 2
    assert text.startswith("First line.")


def test_trailing_space_on_a_line_still_goes():
    """Invisible, never deliberate, and it would move the approval digest.

    Two prompts that read identically must hash identically, or an approval
    fails over something nobody can see on screen.
    """
    from studio_core.services import reference

    text = reference.assemble(
        {"id": "x", "group": "face", "prompt": "One.   \nTwo.  "}, {}, PROFILE)
    assert text == "One.\nTwo."


def test_a_bible_FIELD_is_still_flattened():
    """The opposite case, and it stays the opposite.

    A bible field is a sentence or two typed into a form; the line breaks in it
    are the textarea's rather than the author's. The TEMPLATE is what somebody
    laid out deliberately.
    """
    from studio_core.services import reference

    profile = {**PROFILE, "identity": {"apparent_age": "Late\n30s", "height_read": "5'10\""}}
    assert reference.age_text(profile) == "Late 30s"


def test_each_angle_can_be_given_its_OWN_photographs(empty_api):
    """A profile angle wants the profile shots; a front angle does not.

    `identity_by_angle` beats `identity`, which stays as the fallback — the CLI
    resolves one set from `--seed-pick` and means it for every angle, and a
    single shape would have made one of the two callers lie.
    """
    _spec(empty_api)
    empty_api.patch("/api/reference-spec/angles/face_profile_right",
                    json={**ANGLE, "order": 1500})
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    front = _seed_node(empty_api, character, "front.jpg")
    side = _seed_node(empty_api, character, "side.jpg")

    got = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"], "identity": [front],
              "identity_by_angle": {"face_profile_right": [side]},
              "preview": True},
    ).get_json()

    by_angle = {e["angle"]: [s["node"] for s in e["sends"]] for e in got["preview"]}
    assert by_angle["face_front"] == [front]
    assert by_angle["face_profile_right"] == [side]


def test_an_angle_nobody_picked_for_is_refused_BEFORE_anything_is_drafted(empty_api):
    """A shoot must not half-happen because the twelfth angle was the one missed."""
    _spec(empty_api)
    empty_api.patch("/api/reference-spec/angles/face_back", json={**ANGLE, "order": 1500})
    character = _character_with_bible(empty_api)
    project = empty_api.post("/api/projects", json={"slug": "refs"}).get_json()
    node = _seed_node(empty_api, character)

    resp = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"],
              "identity_by_angle": {"face_front": [node]}},
    )

    assert resp.status_code == 400
    assert "face_back" in resp.get_json()["error"]
    # And nothing was written for the angle that WAS picked for.
    assert empty_api.get(f"/api/runs?project={project['id']}").get_json()["runs"] == []

    # The same request as a PREVIEW is answered rather than refused — see
    # `test_a_PREVIEW_needs_neither_a_project_nor_a_single_photograph`.
    preview = empty_api.post(
        f"/api/characters/{character['id']}/turnaround",
        json={"project": project["id"],
              "identity_by_angle": {"face_front": [node]},
              "preview": True},
    )
    assert preview.status_code == 200
    assert {e["angle"] for e in preview.get_json()["preview"]} == {"face_front", "face_back"}
