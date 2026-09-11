"""`domain/projects` — the project record, and the pool that stopped being numbered.

Against the in-memory API, so the routes and field names these commands send are
what is checked rather than a stubbed store's idea of them.
"""

from __future__ import annotations

from studio_pipeline.domain import paths as P

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, entities as E
from studio_pipeline.domain import projects as PROJECTS


# ── the record ──────────────────────────────────────────────────────────────

def test_creating_a_project_makes_its_layout_in_one_act(library):
    """**All of it or none of it**, where the subfolders used to appear lazily.

    A project could exist with no `runs/` until whatever write happened to need
    one first created it. They are part of the create transaction now.
    """
    record = E.create_project("second-teaser")
    children = {c["name"] for c in library.fake._children(record["root"])}
    assert children == {"runs", "scenes", "movies", "chains", "input"}


def test_a_duplicate_name_is_allowed_and_makes_the_name_unresolvable(library):
    """**The trade, stated in one test.**

    A slug was claimed, so this raised. A name is a label: the create goes
    through, and what breaks is the client-side LOOKUP — which is the right
    place for it, because it is a question asked by somebody who can answer it.
    """
    E.create_project("porch-teaser")

    with pytest.raises(P.PathError, match="not unique"):
        PROJECTS.resolve("porch-teaser")


def test_resolving_a_name_returns_the_whole_record(library):
    record = PROJECTS.resolve("porch-teaser")
    assert record["id"] == library.project
    assert record["root"] == library.project_root
    assert record["rev"] == 1


def test_resolving_an_id_skips_the_name_lookup(library):
    assert PROJECTS.resolve(library.project)["name"] == "porch-teaser"


def test_a_missing_project_lists_what_exists(library):
    result = CliRunner().invoke(cli.main, ["projects", "show", "nope"])
    assert result.exit_code == 1
    assert "no project called 'nope'" in result.output


# ── rename ──────────────────────────────────────────────────────────────────

def test_renaming_a_project_touches_nothing_else(library):
    """**New, and trivial — it was impossible before.**

    Every run, scene and movie names the project by id, so the rename is one
    conditional write — and NOT a folder-node rename any more: an entity root is
    named by its id. The run recorded before it is still in the project after.
    """
    from studio_pipeline.domain import runs as R

    result = CliRunner().invoke(cli.main, ["projects", "rename", "porch-teaser",
                                           "launch-teaser"])
    assert result.exit_code == 0, result.output
    assert "0 objects copied" in result.output
    assert library.fake.nodes[library.project_root]["name"] == library.project
    assert PROJECTS.resolve(library.project)["name"] == "launch-teaser"
    assert [r["id"] for r in R.list_runs(library.project)] == [library.run]


def test_renaming_onto_a_name_another_project_has_is_allowed(library):
    E.create_project("taken")
    result = CliRunner().invoke(cli.main, ["projects", "rename", "porch-teaser",
                                           "taken"])
    assert result.exit_code == 0, result.output


def test_a_stale_rev_is_refused(library):
    """`rev` is compare-and-swap, not check-then-write. There is no window."""
    record = PROJECTS.resolve("porch-teaser")
    E.patch_project(record["id"], record["rev"], name="moved on")
    with pytest.raises(api.Conflict):
        E.patch_project(record["id"], record["rev"], name="stale")


# ── involvement ─────────────────────────────────────────────────────────────

def test_linking_a_character_records_it_on_the_project(library):
    """Involvement is a row on the project, not a folder somewhere."""
    result = CliRunner().invoke(cli.main, ["projects", "link", "porch-teaser",
                                           "subject-b"])
    assert result.exit_code == 0, result.output
    assert library.character_b in {c["id"] for c in E.get_project(library.project)["characters"]}


def test_unlinking_leaves_the_files_and_the_runs_alone(library):
    from studio_pipeline.domain import runs as R

    result = CliRunner().invoke(cli.main, ["projects", "unlink", "porch-teaser",
                                           "subject-a"])
    assert result.exit_code == 0, result.output
    assert library.character not in {c["id"] for c in E.get_project(library.project)["characters"]}
    # The run recorded that it USED the character; involvement is a separate
    # fact about the project, and unlinking one must not rewrite the other.
    assert R.find_runs(character=P.by_name(E.list_characters(), "subject-a", "character")["id"])


def test_unlinking_something_that_is_not_linked_says_so(library):
    result = CliRunner().invoke(cli.main, ["projects", "unlink", "porch-teaser",
                                           "subject-b"])
    assert result.exit_code == 1
    assert "not linked" in result.output


def test_linking_an_unknown_character_is_refused(library):
    result = CliRunner().invoke(cli.main, ["projects", "link", "porch-teaser",
                                           "nobody"])
    assert result.exit_code == 1
    assert "no character" in result.output


# ── the input pool ──────────────────────────────────────────────────────────

def test_the_pool_is_positional_and_the_names_are_left_alone(library):
    """**`--input N` is position N in this listing.**

    Basenames used to be `<project>_in_<n>`, so a deletion either renumbered
    every file — rewriting every record citing one — or left a hole that
    silently changed what `--input 3` meant.
    """
    pool = PROJECTS.input_pool(PROJECTS.resolve("porch-teaser"))
    assert [entry["name"] for entry in pool] == [
        "porch-plate.png", "porch-plate.webp", "street-plate.webp"]
    assert [entry["position"] for entry in pool] == [1, 2, 3]


def test_input_numbers_resolve_to_node_ids_in_the_order_asked_for(library):
    record = PROJECTS.resolve("porch-teaser")
    assert PROJECTS.input_nodes(record, [3, 1]) == [library.input_1, library.input_3]


def test_a_position_the_pool_does_not_have_says_how_many_it_holds(library):
    record = PROJECTS.resolve("porch-teaser")
    with pytest.raises(KeyError, match="holds 3"):
        PROJECTS.input_nodes(record, [9])


def test_adding_an_input_keeps_its_own_basename(library, tmp_image):
    record = PROJECTS.resolve("porch-teaser")
    added = PROJECTS.add_inputs(record, [str(tmp_image)])
    assert added[0]["name"] == "plate.png"
    assert added[0]["node"] in [e["id"] for e in PROJECTS.input_pool(record)]


def test_the_pool_folder_is_recreated_if_someone_removed_it(library, tmp_image):
    """Self-healing, per the layout section: a route that cannot find its
    conventional folder makes one and never guesses."""
    record = PROJECTS.resolve("porch-teaser")
    del library.fake.nodes[library.input_pool]
    added = PROJECTS.add_inputs(record, [str(tmp_image)])
    assert added[0]["node"] in [e["id"] for e in PROJECTS.input_pool(record)]


def test_a_non_image_is_refused_from_the_pool(library, tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("not an image")
    result = CliRunner().invoke(cli.main, ["projects", "add-inputs", str(doc),
                                           "porch-teaser"])
    assert result.exit_code == 1
    assert "the input pool holds images" in result.output


# ── the CLI ─────────────────────────────────────────────────────────────────

def test_projects_list_shows_the_counts_off_the_record(library):
    result = CliRunner().invoke(cli.main, ["projects", "list"])
    assert result.exit_code == 0, result.output
    assert "porch-teaser" in result.output
    assert "runs 1" in result.output


def test_projects_list_does_not_claim_to_know_who_is_involved(library):
    """`GET /api/projects` does not send involvement, so the listing cannot show it.

    It used to print a `characters:` column read off `character_slugs` — a field
    no route has ever returned — so the value was `—` for every project in the
    library. Printing nothing beats printing a falsehood; `show` has the answer.
    """
    result = CliRunner().invoke(cli.main, ["projects", "list"])
    assert "characters" not in result.output
    assert "subject-a" not in result.output


def test_projects_show_names_the_characters_involved(library):
    """The regression: this printed `—` for every project, forever.

    `GET /api/projects/<id>` resolves involvement to `{id, slug, display_name}`
    objects. The CLI read a flat `character_slugs` list instead and always found
    nothing — and the suite passed because the fake API invented that field.
    """
    result = CliRunner().invoke(cli.main, ["projects", "show", "porch-teaser"])
    assert result.exit_code == 0, result.output
    assert "characters  subject-a" in result.output


def test_projects_show_prints_the_pool_size(library):
    result = CliRunner().invoke(cli.main, ["projects", "show", "porch-teaser"])
    assert result.exit_code == 0, result.output
    assert "input pool  3 image(s)" in result.output


def test_projects_inputs_shows_positions(library):
    result = CliRunner().invoke(cli.main, ["projects", "inputs", "porch-teaser"])
    assert result.exit_code == 0, result.output
    assert "  1  " in result.output
    assert "street-plate.webp" in result.output


def test_projects_inputs_can_presign(library):
    """The same shadowing trap `runs outputs --presign` fell into."""
    result = CliRunner().invoke(cli.main, ["projects", "inputs", "porch-teaser",
                                           "--presign"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "memory://" in result.output


def test_deleting_a_project_that_holds_runs_is_refused_and_names_cascade(library):
    """The refusal points at the flag that does the right thing, not `--force`.

    `--force` deletes the project and leaves its runs naming a project id that
    is gone. `--cascade` takes them with it.
    """
    result = CliRunner().invoke(cli.main, ["projects", "delete", "porch-teaser"])
    assert result.exit_code == 1
    assert "--cascade" in result.output


def test_cascade_deletes_the_runs_with_the_project(library):
    """One command, and nothing is left naming the project afterwards."""
    result = CliRunner().invoke(cli.main, ["projects", "delete", "porch-teaser",
                                           "--cascade"])
    assert result.exit_code == 0, result.output
    assert "run(s)" in result.output
    assert library.run not in library.fake.runs


def test_deleting_with_force_keeps_the_folder_by_default(library):
    result = CliRunner().invoke(cli.main, ["projects", "delete", "porch-teaser",
                                           "--force"])
    assert result.exit_code == 0, result.output
    assert library.project_root in library.fake.nodes
