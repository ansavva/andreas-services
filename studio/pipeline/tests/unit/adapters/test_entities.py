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

from studio_pipeline.adapters import api, entities as E, store as S

ADAPTERS = pathlib.Path(E.__file__).parent

#: Every route the pipeline may call, as a literal. Diff this against the
#: backend's route table; nothing else in the package builds one.
WIRE_SURFACE = {
    # session / library
    "/api/libraries",
    # Authoring a prompt: the rules need the registry and the phrasebook, both
    # of which are the API's. Writes nothing — safe to call per keystroke.
    "/api/prompt",
    # the model registry, which is the backend's now — `engine/registry.py`
    # reads it from here rather than off a file this package ships, so the API
    # and the SPA measure a reference selection against the same entries the
    # CLI does. `routes/characters.py` used to hold a three-family copy.
    "/api/models",
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
    # A runref — `<project>/latest#2` — to the run it names. The sibling of
    # `/api/resolve`, which does the same for a name path: both turn what a
    # person types into the thing it names.
    "/api/runs/resolve",
    "/api/runs/<id>",
    "/api/runs/<id>/outputs",
    # NOT `/api/runs/<id>/response`. Storing the provider's reply verbatim was
    # this package's job while this package was what received one; a callback
    # consumer receives it now (#536), and the wrapper that spelled the route
    # outlived its last caller by two PRs.
    # The plan and its approval. `plan` and `sends` are the authored half a run
    # gained; `approve` is the one that carries a digest, so that a yes names the
    # payload it was a yes to and dies when that payload changes.
    #
    # POST only. The SPA withdraws an approval — `DELETE` on the same route —
    # and nothing at a terminal does: `runs edit` writes the plan or the sends,
    # and the API voids the approval as a consequence of the write rather than
    # as a second call somebody has to remember to make.
    "/api/runs/<id>/plan",
    "/api/runs/<id>/sends",
    "/api/runs/<id>/approve",
    # **The route that spends money**, and the two either side of it. Generation
    # moved into the API, so the CLI asks it to submit rather than calling
    # Replicate itself — and reads a model's live schema and README through it
    # too, which is what removed `REPLICATE_API_TOKEN` from this package.
    "/api/runs/<id>/submit",
    "/api/runs/<id>/reconcile",
    "/api/models/<id>/schema",
    "/api/models/<id>/readme",
    # scenes
    "/api/scenes",
    "/api/scenes/<id>",
    "/api/scenes/<id>/shots",
    "/api/scenes/<id>/shots/<id>",
    # movies
    "/api/movies",
    "/api/movies/<id>",
    "/api/movies/<id>/scenes",
    # NOT `/api/scenes/<id>/output` and NOT `/api/movies/<id>/output`. Both
    # minted an upload URL for a take this process had just encoded, and this
    # process encodes nothing since #537 — the render worker files its own
    # output. The backend still serves both; the CLI has no reason to call
    # either, and a wrapper spelling one would put a route in this table that
    # nothing reconciles.
    # renders — where ~1,360 lines of local media processing went. A job is
    # enqueued and polled; the worker has ffmpeg in its image and this package
    # does not.
    "/api/renders",
    "/api/renders/<id>",
    # the two operations that are NOT on that queue. Both are sub-second on a
    # single image, so a queue round trip would cost more than the work — see
    # `backend/studio_core/routes/images.py`.
    "/api/images/convert",
    "/api/images/crop",
    # phrasebook
    "/api/phrasebook",
    "/api/phrasebook/<id>/<id>",
    # The reference spec: the prose a turnaround fills. Blocks and angles are
    # separate rows, so they are separate routes — editing one is one write.
        "/api/templates",
    "/api/templates/<id>",
    "/api/templates/blocks/<id>",
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
    # Every image is still the same node, untouched by the rename — and so
    # are its tags: they are attributes of it, not a second record that had
    # to be re-pointed.
    assert {e["id"] for e in E.character_images(record["id"])} == {
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


# ── identity, which is tags ─────────────────────────────────────────────────


def test_a_characters_images_are_its_whole_branch_not_an_index(library):
    """**Wider than the reference index ever was, on purpose.**

    That listed the pictures somebody had filed a row for, so an image dropped
    into the tree by hand was invisible to it — which is how twelve files in the
    production library ended up with no description anywhere. This is every image
    under the character; the tags say which are identity.
    """
    found = E.character_images(library.character)

    assert {entry["id"] for entry in found} == {
        library.face_1, library.face_2, library.body_1}


def test_images_filter_on_every_named_tag(library):
    """ALL of them, not any."""
    assert [e["id"] for e in E.character_images(library.character, ["default", "face"])] == [
        library.face_1, library.face_2]
    assert E.character_images(library.character, ["default", "body"]) == []


def test_tagging_is_the_whole_write_path(library):
    """One `PATCH` on the file. No attach, no row, no second record to drift.

    `add_reference`, `put_references`, `delete_reference` and `put_default_set`
    are gone; `store.describe_node` is what remains, and it was already the place
    a description lived.
    """
    S.describe_node(library.body_1, tags=["default", "body"])

    # By NAME: front-neutral, full-length, three-quarter. Order stopped meaning
    # anything about a character, so the listing needs one that is stable rather
    # than one that is meaningful.
    assert [e["id"] for e in E.character_images(library.character, ["default"])] == [
        library.face_1, library.body_1, library.face_2]


def test_untagging_takes_an_image_out_without_touching_the_file(library):
    """What `detach` was. The bytes and the node id are untouched either way."""
    S.describe_node(library.face_1, tags=["face"])

    assert library.face_1 not in {
        e["id"] for e in E.character_images(library.character, ["default"])}
    assert S.node(library.face_1)["name"] == "front-neutral.webp"


# ── selection ───────────────────────────────────────────────────────────────


def test_selection_falls_back_to_the_default_tag(library):
    """No `pick` and no `tag` is the character's `default` images.

    That is what `default_set` said, moved onto the pictures — so there is no
    list on the record that can name a node nothing points at any more.
    """
    found = E.selection(library.character)

    assert found["source"] == "default"
    assert [entry["node"] for entry in found["selection"]] == [
        library.face_1, library.face_2]


def test_selection_by_tag_requires_every_tag(library):
    """`?tag=default,face` — the face images this character sends."""
    found = E.selection(library.character, tag=["default", "face"])

    assert found["source"] == "tag"
    assert [entry["node"] for entry in found["selection"]] == [
        library.face_1, library.face_2]


def test_a_tag_nothing_carries_says_which_tags_are_in_use(library):
    """A filter matching nothing is refused, and the refusal is useful.

    Being handed no images is a typo, not a selection, and what runs next spends
    money on it — so it comes back as an error naming the tags that exist.
    """
    with pytest.raises(api.ApiError) as caught:
        E.selection(library.character, tag=["wardrobe"])

    assert "wardrobe" in str(caught.value)
    assert "face" in str(caught.value)


def test_over_cap_is_refused_rather_than_truncated(library):
    """**Refused, never truncated**, and refused as `Conflict` so callers act.

    The refusal used to live in `engine/refs.py`, where only the CLI passed
    through it. It is the route's now, so the SPA cannot be lenient where the
    CLI is strict.
    """
    with pytest.raises(api.Conflict):
        E.selection(library.character, limit=1)


def test_selection_by_pick_accepts_a_filename_a_person_read_off_a_listing(library):
    """An id is the real address; a name is what is on the screen."""
    found = E.selection(library.character, pick=["full-length.webp"])

    assert [entry["node"] for entry in found["selection"]] == [library.body_1]


def test_pick_does_not_require_the_image_to_be_tagged(library):
    """Naming a picture IS the decision; a tag is the way to not have to."""
    found = E.selection(library.character, pick=[library.body_1])

    assert [entry["node"] for entry in found["selection"]] == [library.body_1]


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
