"""`adapters/entities` — the entity routes, and the list of them as a contract.

Two jobs here, and the second is the unusual one.

**Behaviour.** Each wrapper is exercised against the in-memory API, because a
wrapper that builds the wrong body is indistinguishable from a correct one until
something calls it.

**The route table.** `test_the_route_table_is_the_whole_wire_surface` pins every
route string the pipeline can emit. It exists because the API half of studio is
written against the same spec by different hands: a route renamed on one side is
a 404 in production and nothing before production would say so. Keeping the list
in a test rather than in a comment means it cannot rot quietly — adding a route
to `entities.py` without adding it here fails, and so does the reverse.

If this list and the backend disagree, one of them is wrong and neither is
allowed to guess which.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from studio_pipeline.adapters import api, entities as E

ADAPTERS = pathlib.Path(E.__file__).parent

#: Every route the pipeline may call, as a literal. Diff this against the
#: backend's route table; nothing else in the package builds one.
WIRE_SURFACE = {
    # session / library
    "/api/libraries",
    # the file layer, addressed by id
    "/api/resolve",
    # `/api/asset` is deliberately absent. It was the pipeline's one
    # key-addressed call, for shared material with no node; the plates are
    # ordinary nodes now and the phrasebook is `TERM#` rows, so nothing here
    # asks for an object by key. The backend still serves it for the SPA's
    # tile refresh, node-addressed.
    "/api/nodes",
    "/api/nodes/move",
    "/api/nodes/copy",
    "/api/nodes/<id>",
    "/api/nodes/<id>/download-url",
    "/api/nodes/<id>/upload-url",
    "/api/nodes/<id>/confirm-upload",
    "/api/nodes/<id>/text",
    "/api/nodes/<id>/owner",
    # characters
    "/api/characters",
    "/api/characters/<id>",
    "/api/characters/<id>/profile",
    "/api/characters/<id>/references",
    "/api/characters/<id>/references/<id>",
    "/api/characters/<id>/default-set",
    "/api/characters/<id>/selection",
    "/api/characters/<id>/textblock",
    "/api/characters/<id>/runs",
    "/api/characters/<id>/projects",
    # projects
    "/api/projects",
    "/api/projects/<id>",
    "/api/projects/<id>/characters",
    "/api/projects/<id>/inputs",
    # NOT `/api/projects/<id>/runs`. The spec lists it, and the pipeline does
    # not call it: `GET /api/runs?project=` answers the same question with the
    # same filters, and one query route is easier to keep in step than two. The
    # backend may serve it for the SPA; nothing here will notice.
    "/api/projects/<id>/scenes",
    "/api/projects/<id>/movies",
    # runs
    "/api/runs",
    "/api/runs/<id>",
    "/api/runs/<id>/outputs",
    "/api/runs/<id>/response",
    # The plan and its approval. `plan` and `sends` are the authored half a run
    # gained; `approve` is the one that carries a digest, so that a yes names the
    # payload it was a yes to and dies when that payload changes.
    "/api/runs/<id>/plan",
    "/api/runs/<id>/sends",
    "/api/runs/<id>/approve",
    # scenes
    "/api/scenes",
    "/api/scenes/<id>",
    "/api/scenes/<id>/shots",
    "/api/scenes/<id>/shots/<id>",
    "/api/scenes/<id>/output",
    # movies
    "/api/movies",
    "/api/movies/<id>",
    "/api/movies/<id>/scenes",
    "/api/movies/<id>/output",
    # phrasebook
    "/api/phrasebook",
    "/api/phrasebook/<id>/<id>",
}

_SEGMENT = re.compile(r"\{[^}]+\}")


def _routes_in(path: pathlib.Path) -> set[str]:
    """Every `/api/...` string literal in a module, with substitutions blanked.

    Read out of the source rather than by calling anything: the point is to
    catch a route that exists and is never exercised, which a runtime probe by
    definition cannot see. F-string parts are joined and each substitution
    becomes `<id>`, so `f"/api/runs/{run_id}/outputs"` reads as
    `/api/runs/<id>/outputs`.
    """
    found: set[str] = set()
    tree = ast.parse(path.read_text())

    # An f-string's literal halves are `Constant` nodes *inside* the
    # `JoinedStr`, and `ast.walk` visits them too — so `f"/api/runs/{id}"` would
    # otherwise also register the fragment `/api/runs/` as a route of its own.
    # Collecting them first and skipping them is the whole of the difference
    # between a table with seven phantom entries in it and a usable one.
    inside_fstrings = {id(part)
                       for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)
                       for part in node.values}

    def literal(node) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return None if id(node) in inside_fstrings else node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(str(part.value) if isinstance(part, ast.Constant) else "<id>"
                           for part in node.values)
        return None

    for node in ast.walk(tree):
        text = literal(node)
        if text and text.startswith("/api/"):
            found.add(_SEGMENT.sub("<id>", text))
    return found


def test_the_route_table_is_the_whole_wire_surface():
    """**The list the backend must serve, and nothing beyond it.**

    Both directions are asserted on purpose. A route in the code and not in the
    list is a route nobody reconciled; a route in the list and not in the code
    is a stale expectation that would make the reconciliation look complete when
    it is not.
    """
    live = set().union(*(_routes_in(ADAPTERS / name)
                         for name in ("api.py", "entities.py", "store.py")))
    assert live == WIRE_SURFACE, (
        f"in the code but not in the table: {sorted(live - WIRE_SURFACE)}\n"
        f"in the table but not in the code: {sorted(WIRE_SURFACE - live)}"
    )


def test_no_route_string_lives_outside_the_adapters():
    """**The coordination rule, enforced rather than remembered.**

    Twenty modules each spelling a route is a reconciliation nobody can perform.
    `adapters/api.py` holds the transport, `entities.py` the entity routes and
    `store.py` the node routes; anything else naming one has bypassed all three.
    """
    package = ADAPTERS.parent
    offenders = {}
    for source in sorted(package.rglob("*.py")):
        if source.parent == ADAPTERS:
            continue
        found = _routes_in(source)
        if found:
            offenders[str(source.relative_to(package))] = sorted(found)
    assert not offenders, f"route strings outside adapters/: {offenders}"


# ── characters ──────────────────────────────────────────────────────────────

def test_creating_a_character_creates_its_starting_layout(library):
    record = E.create_character("subject-c", display_name="Subject C")
    children = {c["name"] for c in library.fake._children(record["root"])}
    assert children == {"reference", "corpus", "seed", "archive"}
    assert record["rev"] == 1
    assert record["default_set"] == []


def test_a_taken_slug_is_a_conflict(library):
    with pytest.raises(api.Conflict):
        E.create_character("subject-a")


def test_slug_addressing_is_the_one_place_a_name_is_accepted(library):
    assert E.resolve_character("subject-a")["id"] == library.character
    assert E.address("subject-a") == "slug:subject-a"


def test_a_rename_is_one_patch_and_moves_the_root_folder(library):
    record = E.resolve_character("subject-a")
    after = E.patch_character(record["id"], record["rev"], slug="subject-z")
    assert after["slug"] == "subject-z"
    assert library.fake.nodes[record["root"]]["name"] == "subject-z"
    # Every reference still names the same node, untouched by the rename.
    assert {e["node"] for e in E.reference_entries(record["id"])} == {
        library.face_1, library.face_2, library.body_1}


def test_a_stale_rev_is_refused(library):
    record = E.resolve_character("subject-a")
    E.patch_character(record["id"], record["rev"], display_name="moved on")
    with pytest.raises(api.Conflict, match="rev"):
        E.patch_character(record["id"], record["rev"], display_name="stale")


def test_the_profile_is_a_record_field(library):
    record = E.resolve_character("subject-a")
    E.put_profile(record["id"], {"identity": {"build": "new"}}, record["rev"])
    assert E.get_character(record["id"])["profile"] == {"identity": {"build": "new"}}


def test_patching_the_profile_merges_one_section(library):
    record = E.resolve_character("subject-a")
    E.patch_profile(record["id"], {"voice": {"accent": "changed"}}, record["rev"])
    profile = E.get_character(record["id"])["profile"]
    assert profile["voice"] == {"accent": "changed"}
    assert profile["face"]  # untouched


# ── references ──────────────────────────────────────────────────────────────

def test_order_is_gapped_so_an_insert_touches_no_neighbour(library):
    entries = {e["node"]: e["order"]
               for e in E.reference_entries(library.character, group="face")}
    assert sorted(entries.values()) == [1000, 2000]

    inserted = library.fake.put_file(library.face_folder, "profile-left.webp", b"x")
    E.add_reference(library.character, inserted["id"], "face", after=library.face_1)
    after = {e["node"]: e["order"]
             for e in E.reference_entries(library.character, group="face")}
    assert after[inserted["id"]] == 1500
    assert after[library.face_1] == 1000 and after[library.face_2] == 2000


def test_regrouping_is_one_write_and_no_object_moves(library):
    """`curate regroup` was a reparent plus a records sweep. It is an attribute."""
    before = library.fake.nodes[library.body_1]["parent_id"]
    E.patch_reference(library.character, library.body_1, group="face")
    assert library.fake.nodes[library.body_1]["parent_id"] == before
    assert {e["node"] for e in E.reference_entries(library.character, group="face")} == {
        library.face_1, library.face_2, library.body_1}


def test_a_bulk_describe_is_one_transaction(library):
    E.put_references(library.character, [
        {"node": library.face_1, "description": "first"},
        {"node": library.body_1, "description": "second", "tags": ["body", "wide"]},
    ])
    by_node = {e["node"]: e for e in E.reference_entries(library.character)}
    assert by_node[library.face_1]["description"] == "first"
    assert by_node[library.body_1]["tags"] == ["body", "wide"]


def test_describing_something_that_is_not_a_reference_is_refused(library):
    with pytest.raises(api.NotFound):
        E.put_references(library.character, [{"node": library.input_1,
                                              "description": "nope"}])


def test_detaching_a_reference_leaves_the_file_alone(library):
    E.delete_reference(library.character, library.body_1)
    assert library.body_1 in library.fake.nodes
    assert library.body_1 not in {e["node"]
                                 for e in E.reference_entries(library.character)}


def test_attaching_the_same_node_twice_is_refused(library):
    with pytest.raises(api.Conflict):
        E.add_reference(library.character, library.face_1, "face")


# ── selection ───────────────────────────────────────────────────────────────

def test_selection_falls_back_to_the_default_set(library):
    found = E.selection(library.character)
    assert found["source"] == "default_set"
    assert [s["node"] for s in found["selection"]] == [library.face_1, library.face_2]
    assert [s["slot"] for s in found["selection"]] == [1, 2]


def test_selection_by_tag_requires_every_tag(library):
    found = E.selection(library.character, tag=["face", "profile"])
    assert [s["node"] for s in found["selection"]] == [library.face_2]


def test_a_tag_nothing_carries_says_which_tags_are_in_use(library):
    with pytest.raises(api.NotFound, match="Tags in use"):
        E.selection(library.character, tag=["nonexistent"])


def test_over_cap_is_refused_rather_than_truncated(library):
    """**Which images a generation saw must not be decided by a listing.**

    The refusal used to live in `engine/refs.py`, where only the CLI passed
    through it. It is one route now, so the SPA cannot disagree with the CLI
    about what a model was shown.
    """
    with pytest.raises(api.Conflict, match="accepts 1"):
        E.selection(library.character, limit=1)


def test_selection_by_pick_accepts_a_filename_a_person_read_off_a_listing(library):
    found = E.selection(library.character, pick=["full-length.webp"])
    assert [s["node"] for s in found["selection"]] == [library.body_1]


# ── phrasebook ──────────────────────────────────────────────────────────────

def test_a_term_is_a_row_and_needs_no_document_to_exist_first(library):
    """**The failure that disappears.**

    `add` wrote through `PATCH /api/text`, which overwrites and cannot create —
    so a library that had never held `phrasebook/wording.yaml` refused the first
    entry anybody tried to record. A row has no such precondition, and this
    library has never held a phrasebook at all.
    """
    E.add_phrasebook_term("kling", "bare chest", "chest", note="from a refusal")
    (row,) = E.phrasebook(model="kling")
    # `created`, the stamp every row in this table carries. It read `added` —
    # the document's field name — which the backend has never written.
    assert row["created"].startswith("2026-01-01T")
    assert {k: v for k, v in row.items() if k != "created"} == {
        "model": "kling", "avoid": "bare chest", "use": "chest",
        "note": "from a refusal", "replicate": None}


def test_the_wrapped_listing_shape_is_unwrapped_and_not_silently_dropped(library):
    """`GET /api/phrasebook` answers `{"terms": [...]}`, not a bare array.

    Every other listing route this adapter calls answers an array, so the
    response went through `_as_list` — which returns `[]` for any shape that is
    not a list. The result was an empty phrasebook for every model in every
    library, indistinguishable from a library that genuinely held none, for the
    whole life of the migration. Prod held 16 terms and `phrasebook show`
    printed `{}`.

    It survived because the fake answered this one route with a bare list. That
    is fixed at the fake; this pins the adapter so a return to `_as_list` alone
    fails here rather than in a library nobody is looking at.
    """
    E.add_phrasebook_term("kling", "bare chest", "chest")

    assert [t["avoid"] for t in E.phrasebook(model="kling")] == ["bare chest"]
    assert [t["avoid"] for t in E.phrasebook()] == ["bare chest"]


def test_a_duplicate_pair_is_refused(library):
    E.add_phrasebook_term("kling", "bare chest", "chest")
    with pytest.raises(api.Conflict):
        E.add_phrasebook_term("kling", "bare chest", "torso")


def test_a_term_is_deletable_even_though_both_segments_need_quoting(library):
    """The model key carries a slash and the avoid phrase carries spaces.

    `quote` with the default `safe='/'` would split the model into two path
    segments and 404 — which is why `delete_phrasebook_term` passes `safe=''`.
    """
    E.add_phrasebook_term("google/nano-banana-pro", "bare chest", "chest")
    E.delete_phrasebook_term("google/nano-banana-pro", "bare chest")
    assert E.phrasebook() == []
