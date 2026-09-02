"""The template library as rows, and filling one from a run's cast.

What made a prompt reachable from the app: the prose lives in the catalog rather
than in the pipeline package, and one fill turns a template into the words a
model is sent.

**These were reference TEMPLATES.** They held one orientation of one character's
standard set, carried a `group` that had to be `face` or `body`, and only a
turnaround could use one. What is left is the part that was always general — a
prompt somebody wrote, filled from the characters a run binds.
"""

import pytest

from studio_core import config
from studio_core.errors import ValidationError
from tests.conftest import CATALOG_LIBRARY

BLOCK = "THE FACE COMES FROM THE REFERENCE IMAGES. Study the nose."

TEMPLATE = {
    "prompt": "A studio portrait, front on. {block.face_only} {character.1.top}",
    "description": "Head and shoulders, front on.",
    "tags": ["face", "front"],
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


def _library(api):
    api.patch("/api/templates/blocks/face_only", json={"text": BLOCK})
    return api.patch("/api/templates/Face, front", json=TEMPLATE)


# ───────────────────────────── the rows ─────────────────────────────


def test_a_first_block_needs_no_document_to_exist_first(empty_api, catalog_table):
    """The same property the phrasebook gained by becoming rows.

    A spec held as one YAML blob has to be created before it can be edited, so
    the first write in a fresh library is a special case. A first block is just
    a first row.
    """
    resp = empty_api.patch("/api/templates/blocks/face_only", json={"text": BLOCK})

    assert resp.status_code == 200
    assert _item(catalog_table, f"LIB#{CATALOG_LIBRARY}",
                 "SPEC#BLOCK#face_only")["text"]["S"] == BLOCK


def test_the_whole_spec_comes_back_in_one_read(empty_api):
    _library(empty_api)
    got = empty_api.get("/api/templates").get_json()

    assert got["blocks"]["face_only"] == BLOCK
    assert [a["name"] for a in got["templates"]] == ["Face, front"]
    assert got["templates"][0]["tags"] == ["face", "front"]


def test_an_angle_must_carry_a_description_and_tags(empty_api):
    """They are written onto a promoted image by `add-refs --from-run`.

    An angle missing them promotes UNDESCRIBED, which is the state the described
    index exists to prevent — and nobody notices until a selection by tag comes
    back short.
    """
    for missing in ("description", "tags"):
        body = {k: v for k, v in TEMPLATE.items() if k != missing}
        resp = empty_api.patch("/api/templates/face_front", json=body)
        assert resp.status_code == 400, missing
        assert missing in resp.get_json()["error"].lower()


def test_a_name_holding_the_key_separator_is_refused(empty_api):
    resp = empty_api.patch("/api/templates/blocks/face%23only", json={"text": "x"})
    assert resp.status_code == 400


def test_templates_come_back_by_name(empty_api):
    empty_api.patch("/api/templates/Body, front", json=TEMPLATE)
    empty_api.patch("/api/templates/Face, front", json=TEMPLATE)
    got = empty_api.get("/api/templates").get_json()
    assert [a["name"] for a in got["templates"]] == ["Body, front", "Face, front"]


# ────────────────────────── assembling a prompt ──────────────────────────


def test_assembly_fills_a_template_from_the_bible(empty_api):
    from studio_core.services import template as tmpl

    text = tmpl.expand(TEMPLATE["prompt"], [PROFILE], {"face_only": BLOCK},
                       identity_positions=[1, 2])
    assert BLOCK in text
    assert "plain white polo shirt" in text


def test_a_template_citing_a_block_nobody_wrote_names_what_was_available():
    """The likeliest failure now that the spec is editable.

    Somebody deletes a block an angle still cites. The useful answer is the list
    of names they could have meant, not a stack trace.
    """
    from studio_core.errors import ValidationError
    from studio_core.services import template as tmpl

    try:
        tmpl.expand("{no_such_block}", [PROFILE], {})
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
    from studio_core.services import template as tmpl

    for broken in ("a { b", "a } b", "{}"):
        try:
            tmpl.expand(broken, [PROFILE], {})
        except ValidationError:
            pass
        else:
            raise AssertionError(f"{broken!r} should be refused")


def test_the_slots_phrase_reads_as_english():
    from studio_core.services import template as tmpl

    assert tmpl.slots_phrase([2]) == "[Image2]"
    assert tmpl.slots_phrase([2, 3]) == "[Image2] and [Image3]"
    assert tmpl.slots_phrase([2, 3, 4]) == "[Image2], [Image3] and [Image4]"


def test_a_face_angle_leaves_out_what_sits_below_the_crop():
    """A face angle crops at mid-chest, so legs and body hair are noise in it."""
    from studio_core.services import template as tmpl

    profile = {**PROFILE, "body": {"silhouette": "Broad.", "lower_body": "Heavy thighs.",
                                   "body_hair": "Dark."}}
    assert "Heavy thighs." not in tmpl.build_text(profile, "face")
    assert "Heavy thighs." in tmpl.build_text(profile, "body")


def test_the_height_number_is_sent_and_comes_first():
    """The one proportion the bible states as a NUMBER, and it was never sent.

    The build clause read the `body:` block alone, so a corrected `height_read`
    sat unused while the prompt argued the point in adjectives. A figure on a
    plain backdrop has no scale of its own.
    """
    from studio_core.services import template as tmpl

    # Labelled and first — see `test_the_build_arrives_as_one_LABELLED_line_per_field`
    # for why every field is now on a line of its own.
    assert tmpl.build_text(PROFILE, "face").startswith("- Height: 5'10\"")


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
    from studio_core.services import template as tmpl

    text = tmpl.build_text({
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
    from studio_core.services import template as tmpl

    text = tmpl.build_text({"body": {"scars": "A pale line above the left knee"}},
                                "body")
    assert "- Scars: A pale line above the left knee" in text


def test_a_face_angle_still_sees_nothing_below_the_crop():
    """A face angle crops at mid-chest, so a leg is noise in its prompt."""
    from studio_core.services import template as tmpl

    text = tmpl.build_text({"body": {"chest_and_shoulders": "Full square chest",
                                          "lower_body": "Heavy thighs"}}, "face")
    assert "Chest and shoulders" in text
    assert "Lower body" not in text


# ─────────────────────── namespaced placeholders ───────────────────────


def _assemble(template, blocks=None, **kw):
    from studio_core.services import template as tmpl
    return tmpl.expand(template, [PROFILE],
                       blocks if blocks is not None else {"face_only": BLOCK}, **kw)


def test_a_namespaced_placeholder_says_where_it_comes_from():
    """**The point of the dotted spelling.** A reader of an assembled prompt
    wants to know which words they can go and change, and a bare `{top}` does
    not say whether that is a block or the character's bible."""
    text = _assemble("{block.face_only} | {character.1.style} | {slot.identity}",
                     identity_positions=[2, 3])
    assert text == f"{BLOCK} | Realistic. | [Image2] and [Image3]"


def test_a_bare_name_resolves_to_nothing_at_all_now():
    """**The flat namespace is gone rather than disambiguated.**

    Blocks were spread into one flat mapping and the computed values overwrote
    them, so a block named `top` lost to the bible every time and nothing said
    so. The bare spelling was kept for a while because every template written so
    far used it; it is not kept now, because there is one template library and
    one way to write a citation in it.
    """
    with pytest.raises(ValidationError):
        _assemble("{face_only}")


def test_a_character_is_cited_by_POSITION_and_the_refusal_says_so():
    """`{character.top}` was the one-character spelling. There is no such thing.

    A template is filled from the characters a RUN binds, so a character is
    named by its position — the same number `[Image1]` counts. A slug would be
    the other candidate and is worse: it is an attribute a rename swaps, and the
    prompt would be quietly wrong afterwards.
    """
    with pytest.raises(ValidationError) as refusal:
        _assemble("{character.top}")
    assert "{character.1.top}" in str(refusal.value)


def test_a_block_that_collides_with_a_field_name_is_simply_fine():
    """Nothing shares a namespace any more, so nothing can collide.

    A block called `top` and the bible's `top` are `{block.top}` and
    `{character.1.top}`; both resolve, and neither can win an argument the other
    did not know it was having.
    """
    text = _assemble("{block.top} :: {character.1.top}", {"top": "A BLOCK CALLED TOP"})
    assert text.startswith("A BLOCK CALLED TOP :: Wearing a plain")


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
        _assemble("{block.tops}")
    assert "tops" in str(refusal.value)
    # And it says what the namespace DOES hold.
    assert "block has:" in str(refusal.value)


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
    from studio_core.services import template as tmpl

    template = "First line.\n\nSecond paragraph. {block.face_only}\n\nThird."
    text = tmpl.expand(template, [PROFILE], {"face_only": BLOCK})
    assert text.count("\n\n") == 2
    assert text.startswith("First line.")


def test_trailing_space_on_a_line_still_goes():
    """Invisible, never deliberate, and it would move the approval digest.

    Two prompts that read identically must hash identically, or an approval
    fails over something nobody can see on screen.
    """
    from studio_core.services import template as tmpl

    text = tmpl.expand("One.   \nTwo.  ", [PROFILE], {})
    assert text == "One.\nTwo."


def test_a_bible_FIELD_is_still_flattened():
    """The opposite case, and it stays the opposite.

    A bible field is a sentence or two typed into a form; the line breaks in it
    are the textarea's rather than the author's. The TEMPLATE is what somebody
    laid out deliberately.
    """
    from studio_core.services import template as tmpl

    profile = {**PROFILE, "identity": {"apparent_age": "Late\n30s", "height_read": "5'10\""}}
    assert tmpl.age_text(profile) == "Late 30s"





# ────────────────────── the name IS the key ──────────────────────


def test_a_template_is_addressed_by_its_name(empty_api):
    """**No id, and none generated.**

    Every character, project and run carries a UUID because a rename would
    otherwise strand every row that named it. A run copies a template's WORDS
    rather than pointing at the row, so there is nothing to strand — and a
    generated id would be a second name that can drift from the first. This is
    the arrangement a block already has, for the same reason.
    """
    _library(empty_api)

    got = empty_api.get("/api/templates").get_json()["templates"][0]

    assert got["name"] == "Face, front"
    assert "id" not in got


def test_renaming_writes_the_new_key_and_drops_the_old(empty_api):
    """One transaction, so the library can never hold the template twice."""
    _library(empty_api)

    resp = empty_api.patch("/api/templates/Face, front",
                           json={**TEMPLATE, "name": "Face, straight on"})

    assert resp.status_code == 200
    assert [t["name"] for t in empty_api.get("/api/templates").get_json()["templates"]] == [
        "Face, straight on"]


def test_a_rename_keeps_the_prompt_it_was_given(empty_api):
    _library(empty_api)

    empty_api.patch("/api/templates/Face, front",
                    json={**TEMPLATE, "name": "Renamed", "prompt": "{block.face_only} only"})

    (kept,) = empty_api.get("/api/templates").get_json()["templates"]
    assert kept["prompt"] == "{block.face_only} only"


def test_a_name_carrying_the_key_separator_is_refused(empty_api):
    """`#` separates every key segment in this table, so it cannot be in one."""
    resp = empty_api.patch("/api/templates/Face, front",
                           json={**TEMPLATE, "name": "face#front"})

    assert resp.status_code == 400
    assert "#" in resp.get_json()["error"]


def test_a_blank_name_is_refused_rather_than_stored(empty_api):
    resp = empty_api.patch("/api/templates/Face, front", json={**TEMPLATE, "name": "   "})

    assert resp.status_code == 400


def test_a_name_is_whitespace_folded_the_way_it_is_displayed(empty_api):
    """`  Face,   front ` and `Face, front` are one template, not two keys."""
    empty_api.patch("/api/templates/  Face,   front ", json=TEMPLATE)

    assert [t["name"] for t in empty_api.get("/api/templates").get_json()["templates"]] == [
        "Face, front"]


def test_a_rename_needs_only_the_new_name(empty_api):
    """**A PATCH may carry one field**, and this is the one that proved it.

    It required the prompt, the description and the tags on every write, so a
    rename could not be sent on its own. The obvious retry — assemble the whole
    body from what the caller remembers — overwrites the prose with a stale copy
    of it, which is a worse failure than the refusal and a quiet one.
    """
    _library(empty_api)

    resp = empty_api.patch("/api/templates/Face, front", json={"name": "Renamed"})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    (kept,) = empty_api.get("/api/templates").get_json()["templates"]
    assert kept["name"] == "Renamed"
    assert kept["prompt"] == TEMPLATE["prompt"]
    assert kept["tags"] == TEMPLATE["tags"]


def test_a_new_template_still_has_to_say_what_it_is(empty_api):
    """The fallback is what is STORED, so a create has nothing to fall back to."""
    assert empty_api.patch("/api/templates/Brand new", json={}).status_code == 400
