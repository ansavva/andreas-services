"""Calls that cross a module boundary — the joins a restructure breaks.

Each of these is one module reaching into another: the engine asking the
character store what a model should be shown, the engine asking the project
store for a pool position, an author asking the phrasebook what to avoid. They
are the wiring `--help` never touches and the reason the suite is weighted to
execution rather than to surface.

The vocabulary they cross with is **node ids** now, where it was S3 keys. That
is the change with the widest blast radius in this package, so the assertions
below are on ids deliberately: a test that still compared paths would pass
against code that had quietly gone back to building them.
"""

import pytest

from studio_pipeline.adapters import entities as E
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain import phrasebook as PB
from studio_pipeline.domain import projects as PROJECTS
from studio_pipeline.engine import refs as REFS


# ── the engine reading a character ──────────────────────────────────────────

def test_reference_selection_resolves_to_node_ids(library):
    """With no selector, the bible's `default_set` decides — not the folder.

    `reference/` is a library, not a set to send whole, and the fallback to
    everything is a fallback rather than a default worth relying on.
    """
    assert REFS.character_ref_nodes("subject-a") == [library.face_1, library.face_2]


def test_reference_selection_by_tag(library):
    assert REFS.character_ref_nodes("subject-a", tags=["face"]) == [
        library.face_1, library.face_2]


def test_reference_selection_by_slot_uses_position_not_a_filename_number(library):
    """**Slot N is position N in the RESOLVED SELECTION.**

    It used to be the trailing number in a filename, which is unique only within
    a group once `reference/` has subfolders — so two images could answer to
    slot 1 and which one a model saw depended on the listing.
    """
    assert REFS.character_ref_nodes("subject-a", tags=["face"], slots=[2]) == [
        library.face_2]


def test_reference_cap_is_refused_not_truncated(library):
    """The refusal moved server-side and its message had to survive the move.

    Truncating would let a folder listing decide which images a generation saw.
    The message is the useful half — it says how to narrow the set — so it is
    asserted rather than just the exception type.
    """
    with pytest.raises(REFS.RefError) as raised:
        REFS.character_ref_nodes("subject-a", cap=1, cap_name="this model")
    assert "--pick-tag" in str(raised.value)


def test_unknown_character_raises_referror(library):
    with pytest.raises(REFS.RefError):
        REFS.character_ref_nodes("nobody")


def test_character_pool_nodes(library):
    """`corpus/`, `seed/` and `archive/` are material, addressed explicitly."""
    record = CHARACTER.resolve("subject-a")
    node = library.fake.put_file(
        CHARACTER.pool_folder(record, "seed")["id"], "source.jpg", b"jpg")
    # Node RECORDS, not bare ids. Every caller picks out of these pools by name
    # — `--seed-pick` names a file, and the refusal that lists an oversized pool
    # has to print something a person recognises. A uuid is neither.
    found = REFS.character_pool_nodes("subject-a", "seed")
    assert [(n["id"], n["name"]) for n in found] == [(node["id"], "source.jpg")]
    assert REFS.character_pool_nodes("subject-a", "corpus") == []


# ── the engine reading a project ────────────────────────────────────────────

def test_project_input_numbers_resolve_in_the_order_asked_for(library):
    """`--input 3 --input 1` sends the third image first. Order is the caller's.

    It takes the project RECORD, not a slug: every caller has already resolved
    one — `--project` is required and never inferred — and re-resolving here
    would be a round trip to learn something the caller is holding.
    """
    record = PROJECTS.resolve("porch-teaser")
    assert REFS.project_input_nodes(record, [3, 1]) == [
        library.input_1, library.input_3]


def test_a_missing_input_number_says_how_big_the_pool_is(library):
    record = PROJECTS.resolve("porch-teaser")
    with pytest.raises(REFS.RefError) as raised:
        REFS.project_input_nodes(record, [9])
    assert "9" in str(raised.value)


# ── an author reading the phrasebook ────────────────────────────────────────

def test_phrasebook_terms(library):
    E.add_phrasebook_term("kling", "bare chest", "chest")
    E.add_phrasebook_term("kling", "shirtless", "omit entirely")
    assert PB.terms("kling") == [
        {"avoid": "bare chest", "use": "chest"},
        {"avoid": "shirtless", "use": "omit entirely"},
    ]


def test_phrasebook_terms_for_an_unknown_model_is_empty_not_an_error(library):
    """A model with no wording list is an ordinary state, not a failure."""
    assert PB.terms("seedance") == []


def test_a_library_that_has_never_held_a_phrasebook_still_answers(library):
    """**The failure that disappeared with the YAML document.**

    `add` wrote through a route that overwrites and cannot create, so the first
    entry in a fresh library was refused. Reading was never affected — a missing
    phrasebook read as an empty one — but writing was, and both halves are rows
    now.
    """
    assert PB.terms("kling") == []
    E.add_phrasebook_term("kling", "bare chest", "chest")
    assert PB.terms("kling") == [{"avoid": "bare chest", "use": "chest"}]


# ── the character store reading the project store ───────────────────────────

def test_add_inputs_returns_the_node_it_wrote(library, tmp_image):
    """The caller gets an id, because an id is what a record may hold."""
    record = PROJECTS.resolve("porch-teaser")
    added = PROJECTS.add_inputs(record, [str(tmp_image)])
    assert added[0]["node"].startswith("node-")
    assert added[0]["node"] in [entry["id"] for entry in PROJECTS.input_pool(record)]


# ── the bible round trip ────────────────────────────────────────────────────

def test_editing_a_bible_writes_it_back_onto_the_record(library, tmp_path, monkeypatch):
    """`edit` pulls to `local/characters/<slug>.yaml` and pushes it back.

    The bible is a record field now, so the push is one `PUT` with a `rev` —
    there is no `profile.yaml` object anywhere, and the pre-migration bug where
    a push landed at `<slug>/profile.yaml` in the bucket root and reported
    success cannot recur, because there is no path to get wrong.
    """
    from click.testing import CliRunner

    from studio_pipeline import cli

    monkeypatch.setattr(CHARACTER, "LOCAL_DIR", str(tmp_path))
    monkeypatch.setattr("studio_pipeline.domain.characters.profile.LOCAL_DIR",
                        str(tmp_path))

    pulled = CliRunner().invoke(cli.main, ["character", "edit", "subject-a"])
    assert pulled.exit_code == 0, f"{pulled.output}\n{pulled.exception!r}"

    local = tmp_path / "subject-a.yaml"
    local.write_text(local.read_text().replace("Realistic", "Painterly"))

    pushed = CliRunner().invoke(cli.main, ["character", "edit", "subject-a"])
    assert pushed.exit_code == 0, f"{pushed.output}\n{pushed.exception!r}"
    assert E.get_character(library.character)["profile"]["rendering"][
        "default_style"] == "Painterly"


def test_pushing_a_stale_bible_is_refused(library, tmp_path, monkeypatch):
    """**`rev` closed a window that check-then-write left open.**

    The guard used to re-read the node's `updated_at` and compare — two
    operations with a gap between them, in which someone else's write lands and
    is lost. A `ConditionExpression` on `rev` is compare-and-swap, so the
    refusal is the API's and there is no gap to lose a write in.
    """
    from click.testing import CliRunner

    from studio_pipeline import cli

    monkeypatch.setattr("studio_pipeline.domain.characters.profile.LOCAL_DIR",
                        str(tmp_path))

    pulled = CliRunner().invoke(cli.main, ["character", "edit", "subject-a"])
    assert pulled.exit_code == 0, pulled.output
    local = tmp_path / "subject-a.yaml"
    before = local.read_text()
    local.write_text(before.replace("Realistic", "Painterly"))
    assert local.read_text() != before, "the working copy did not change"

    # Somebody else writes in the meantime, moving the rev on.
    record = E.get_character(library.character)
    E.put_profile(record["id"], {**record["profile"], "voice": {"accent": "new"}},
                  record["rev"])

    pushed = CliRunner().invoke(cli.main, ["character", "edit", "subject-a"])
    assert pushed.exit_code == 1, pushed.output
    assert "changed" in pushed.output
