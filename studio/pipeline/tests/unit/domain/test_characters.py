"""`domain/characters` — the record, the bible, and the `REF#` index.

**The concurrency half of this file is the part that changed most.** It used to
guard a `profile.yaml` object in the bucket: that the version was the node's
`updated_at`, that a missing bible had no version, that a 403 was not read as a
missing one, and that a write with a stale version was refused. All four existed
because the check was *check-then-write* — read the version, compare it here,
then PUT — with a window in between where somebody else's write lands and is
lost. `profile.py` said so and called closing it "a route change and not this
one".

That route change is this one. The bible is a field on the record and the write
is `PUT /api/characters/<id>/profile {profile, rev}`, which the API applies under
a `ConditionExpression` on `rev`. There is no window, and no version to read
first. The tests that guarded the read are therefore gone — not weakened —
and what replaced them asserts the compare-and-swap directly.

The reference half changed for a different reason: `reference/` stopped being
structural. An image is identity because a `REF#` row says so, not because of the
folder it sits in, so the recursive walk that had to find `face/<name>_1.png`
inside a group folder has nothing left to find.
"""

from __future__ import annotations

from studio_pipeline.domain import paths as P


import pytest
import yaml
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, entities as E, store
from studio_pipeline.domain import characters as CHARACTER
from studio_pipeline.domain.characters import profile as PROFILE


def _run(*args):
    return CliRunner().invoke(cli.main, ["character", *args])


# ── the record ──────────────────────────────────────────────────────────────

def test_creating_a_character_makes_its_layout_in_one_act(library):
    """The four pools are part of the create transaction, not lazily discovered.

    They used to appear on whatever write happened to need one first, so a
    character could exist with no `seed/` — and `add-to <name> seed` was the
    command that found out.
    """
    result = _run("create", "subject-c")
    assert result.exit_code == 0, result.output
    record = CHARACTER.resolve("subject-c")
    assert {c["name"] for c in library.fake._children(record["root"])} == {
        "reference", "corpus", "seed", "archive"}
    for pool in ("reference", "corpus", "seed", "archive"):
        assert f"{pool}/" in result.output


def test_a_name_another_character_has_is_allowed(library):
    """It was refused: a slug was claimed, so a create could collide.

    A name is a label now. Two characters called `subject-a` are two rows that
    look alike in a list, and `resolve` refuses the AMBIGUOUS LOOKUP rather than
    the create — which is the right place for the question, because it is asked
    by somebody who can answer it.
    """
    assert _run("create", "subject-a").exit_code == 0

    with pytest.raises(api.NotFound, match="not unique"):
        CHARACTER.resolve("subject-a")


def test_resolving_a_name_returns_the_whole_record(library):
    record = CHARACTER.resolve("subject-a")
    assert record["id"] == library.character
    assert record["root"] == library.character_root
    # 1: the fixture tags the FILES, and tagging a file is not a write on the
    # character's record. The `default_set` write that used to bump this is gone.
    assert record["rev"] == 1


def test_an_unknown_character_is_a_clean_refusal(library):
    result = _run("show", "nobody")
    assert result.exit_code == 1
    assert "nobody" in result.output


def test_show_lists_the_folders_the_character_actually_has(library):
    """Built from the root's children, not from a fixed list of five blessed names.

    A folder somebody made by hand is a folder like any other — that is what
    "the layout is convention, not schema" means in practice.
    """
    library.fake._create_node(library.character_root, "my-notes", "folder")
    result = _run("show", "subject-a")
    assert result.exit_code == 0, result.output
    assert "my-notes" in result.output


# ── the bible ───────────────────────────────────────────────────────────────

def test_the_bible_reads_as_one_map_with_the_promoted_fields_merged_back(library):
    """`load_profile` is the reader every engine uses, and its shape is pinned.

    `name` was promoted OUT of the document onto the record — `domain/prompt.py`
    reads it by that name, so the reader merges it back in rather than making
    four modules learn where it lives now. There were TWO: the record carried a
    claimed `slug` beside a `display_name` for prose, and both are one `name`.
    """
    data = CHARACTER.load_profile("subject-a")
    assert data["name"] == "subject-a"
    assert "display_name" not in data
    assert data["consistency"]["must"] == ["<…>"]


def test_a_write_with_the_current_rev_goes_through(library):
    record = CHARACTER.resolve("subject-a")
    document = PROFILE.document(record)
    document["rendering"]["default_style"] = "Painterly"
    PROFILE.save_profile(record, document, record["rev"])
    assert E.get_character(record["id"])["profile"]["rendering"][
        "default_style"] == "Painterly"


def test_a_write_with_a_stale_rev_is_refused(library, capsys):
    """**Compare-and-swap, so there is no window to lose a write in.**

    The refusal is the API's condition expression, not a comparison this side of
    the wire. Under the old check-then-write a second writer landing between the
    read and the PUT was silently overwritten; here the second PUT fails, and
    `save_profile` turns that into the one-line refusal a person acts on.
    """
    record = CHARACTER.resolve("subject-a")
    document = PROFILE.document(record)
    PROFILE.save_profile(record, document, record["rev"])
    with pytest.raises(SystemExit):
        PROFILE.save_profile(record, document, record["rev"])
    assert "written by someone else" in capsys.readouterr().err


def test_no_rev_means_the_records_own_rather_than_no_check(library):
    """`None` is "use what this record says", not "skip the check".

    There is no unchecked write left. `create` passes the record it just made,
    whose `rev` is current by construction; `edit --push` passes the sidecar's,
    which is the one that can be stale. Either way the API compares.
    """
    record = CHARACTER.resolve("subject-a")
    PROFILE.save_profile(record, PROFILE.document(record), None)
    # The record in hand is now stale, and a second write through it is refused
    # exactly as an explicit stale `rev` would be.
    with pytest.raises(SystemExit):
        PROFILE.save_profile(record, PROFILE.document(record), None)


def test_the_rev_of_a_character_that_is_not_there_is_none(library):
    """None, and only for a 404. A refusal is a different fact."""
    assert PROFILE.remote_rev("nobody") is None
    assert PROFILE.remote_rev("subject-a") == 1


def test_a_refusal_is_not_a_missing_character(library, monkeypatch):
    """**This used to catch every exception, and the consequence was not a wrong
    answer but a disabled guard.**

    The conflict check was written `if recorded and current and …`, so a `None`
    from a swallowed 403 turned the check OFF rather than reporting it.
    """
    def refused(_name):
        raise api.Forbidden("not a member of this library", 403)

    monkeypatch.setattr(PROFILE, "resolve", refused)
    with pytest.raises(api.Forbidden):
        PROFILE.remote_rev("subject-a")


def test_a_bible_missing_a_schema_key_is_refused_on_the_way_in(library, tmp_path):
    """A bible with no `consistency` block silently stops being checked against."""
    thin = tmp_path / "thin.yaml"
    thin.write_text(yaml.safe_dump({"name": "subject-c", "identity": {}}))
    result = _run("create", "subject-c", "--from-profile", str(thin))
    assert result.exit_code == 1
    assert "missing required key" in result.output


# ── rename ──────────────────────────────────────────────────────────────────

def test_a_rename_is_one_write_and_strands_nothing(library):
    """**The command that changes character most.**

    It was a `PATCH` per slugged basename across four pools, a rewrite of the
    bible's index to match, and a sweep over every run document in every project
    rewriting the paths they had recorded. It is one conditional write, and the
    references, the runs and the default set all still name the same nodes.

    **The root folder does not move either**, which it used to: it was named by
    the slug, and a rename carried it along so a person browsing the tree saw
    the new name. Entity roots are named by their id now.
    """
    result = _run("rename", "subject-a", "subject-z")
    assert result.exit_code == 0, result.output
    assert "0 objects copied" in result.output

    record = CHARACTER.resolve("subject-z")
    assert record["id"] == library.character
    assert library.fake.nodes[library.character_root]["name"] == library.character
    assert {e["id"] for e in E.character_images(record["id"])} == {
        library.face_1, library.face_2, library.body_1}
    # And the tags are where they were: a rename touches the record and the root
    # folder's name, and nothing a picture says about itself.
    assert "default" in store.node(library.face_1)["tags"]
    # The run recorded the character by id, so it is still that character's run.
    assert E.query_runs(character=P.by_name(E.list_characters(), "subject-z", "character")["id"])["runs"]


def test_renaming_onto_a_name_another_character_has_is_allowed(library):
    """Refused while the slug was claimed; ordinary now.

    What it costs is that `resolve` can no longer answer for either of them —
    which is a question asked by a person who can pick, not a write that has to
    be stopped.
    """
    assert _run("rename", "subject-a", "subject-b").exit_code == 0

    with pytest.raises(api.NotFound, match="not unique"):
        CHARACTER.resolve("subject-b")


# ── identity, which is tags ─────────────────────────────────────────────────


def test_images_lists_the_whole_branch_not_an_index(library):
    """**Wider than `refs` ever was, on purpose.**

    `character refs` listed the images somebody had filed a `REF#` row for, so a
    picture dropped into the tree by hand was invisible to it — which is how
    twelve files in the production library ended up with no description
    anywhere. Every image under the character is here.
    """
    result = _run("images", "subject-a")

    assert result.exit_code == 0, result.output
    for node in (library.face_1, library.face_2, library.body_1):
        assert node in result.output


def test_images_marks_the_ones_a_generation_is_shown(library):
    """The `default` tag is the whole distinction, and the listing says so."""
    result = _run("images", "subject-a")

    marked = [line for line in result.output.splitlines() if line.startswith("*")]
    assert len(marked) == 2
    assert library.body_1 not in "".join(marked)


def test_images_filters_on_every_named_tag(library):
    """ALL of them, which is what the filter promises everywhere else."""
    result = _run("images", "subject-a", "--tag", "default,face")

    assert library.face_1 in result.output
    assert library.body_1 not in result.output


def test_tagging_an_image_is_what_makes_it_identity(library):
    """`studio describe` is the only way in, and it already existed.

    Eight commands wrote to the index — `add-refs`, `set-ref-desc`,
    `describe-refs`, `order`, `regroup`, `detach`, `default-set` — and all of
    them are gone. What is left is a tag on a file.
    """
    store.describe_node(library.body_1, tags=["default", "body"])

    chosen = CHARACTER.selection_nodes(CHARACTER.resolve("subject-a"))

    assert library.body_1 in [entry["node"] for entry in chosen]


# ── selection ───────────────────────────────────────────────────────────────

def test_selection_resolves_server_side(library):
    """One route, so the CLI and the SPA cannot disagree about what a model saw."""
    record = CHARACTER.resolve("subject-a")
    chosen = CHARACTER.selection_nodes(record)
    assert [e["node"] for e in chosen] == [library.face_1, library.face_2]
    assert [e["slot"] for e in chosen] == [1, 2]


def test_selection_with_no_filter_is_the_default_tag(library):
    """What `default_set` used to be, said on the pictures instead."""
    record = CHARACTER.resolve("subject-a")

    assert [e["node"] for e in CHARACTER.selection_nodes(record)] == [
        library.face_1, library.face_2]
    assert library.body_1 not in [
        e["node"] for e in CHARACTER.selection_nodes(record)]


def test_slots_pick_positions_within_the_resolved_selection(library):
    """Slot N is position N in THIS list — not a trailing file number."""
    record = CHARACTER.resolve("subject-a")
    assert [e["node"] for e in CHARACTER.selection_nodes(record, slots=[2])] == [
        library.face_2]


def test_an_over_cap_selection_is_refused_with_a_way_to_narrow_it(library):
    """Refused, never truncated, and the message says what to do about it."""
    result = _run("selection", "subject-a", "--limit", "1")
    assert result.exit_code == 1
    assert "--pick" in result.output or "describe" in result.output


def test_selection_can_presign(library):
    result = _run("selection", "subject-a", "--presign")
    assert result.exit_code == 0, result.output
    assert "memory://" in result.output


# ── the non-reference pools ─────────────────────────────────────────────────

def test_add_to_keeps_the_basename_it_arrived_with(library, tmp_image):
    """Renaming a source photo throws away whatever its filename recorded."""
    result = _run("add-to", "subject-a", "seed", str(tmp_image))
    assert result.exit_code == 0, result.output
    record = CHARACTER.resolve("subject-a")
    assert [n["name"] for n in CHARACTER.pool_nodes(record, "seed")] == ["plate.png"]


def test_pool_lists_a_non_reference_pool(library, tmp_image):
    _run("add-to", "subject-a", "corpus", str(tmp_image))
    result = _run("pool", "subject-a", "corpus")
    assert result.exit_code == 0, result.output
    assert "plate.png" in result.output


def test_pool_can_presign(library, tmp_image):
    _run("add-to", "subject-a", "corpus", str(tmp_image))
    result = _run("pool", "subject-a", "corpus", "--presign")
    assert result.exit_code == 0, result.output
    assert "memory://" in result.output


def test_the_archive_pool_warns_that_it_is_retired_material(library, tmp_image):
    """`archive/` is never fed to a model unless it was asked for by name — the
    whole point of it having a name."""
    _run("add-to", "subject-a", "archive", str(tmp_image))
    result = _run("pool", "subject-a", "archive")
    assert result.exit_code == 0, result.output
    assert "archive/" in result.output


def test_pool_lists_the_reference_folder_it_used_to_refuse(library):
    """**The folder and the index are different questions.**

    `reference` was excluded from this command because references are identity
    rather than material — true of the ROWS, and not of the folder they happen
    to sit in. With `character refs` reading the index and this command refusing
    the pool, nothing in the CLI could answer "what files are actually in
    reference/?" — which is how twelve files sat in one library's `reference/`
    subfolders, named by no row, unnoticed.
    """
    result = _run("pool", "subject-a", "reference", "--group", "face")

    assert result.exit_code == 0, result.output
    assert "front-neutral.webp" in result.output


def test_pool_unreferenced_finds_a_file_no_row_names(library, tmp_image):
    """The set difference is over NODE IDS, not filenames — which is why it is
    reliable where a name comparison would not be."""
    stray = library.fake.put_file(library.face_folder, "stray.webp", b"loose")

    listed = _run("pool", "subject-a", "reference", "--group", "face")
    only = _run("pool", "subject-a", "reference", "--group", "face", "--unreferenced")

    assert "front-neutral.webp" in listed.output
    assert only.exit_code == 0, only.output
    assert stray["id"] in only.output
    assert "front-neutral.webp" not in only.output


def test_pool_group_reaches_into_a_subfolder(library, tmp_image):
    """A pool is a tree now — `seed/` with an `original/` and a folder per age."""
    _run("add-to", "subject-a", "seed", str(tmp_image))
    record = CHARACTER.resolve("subject-a")
    seed = CHARACTER.pool_folder(record, "seed")
    deep = store.ensure_child_folder(seed["id"], "current")
    library.fake.put_file(deep["id"], "tucked-away.webp", b"deep")

    root = _run("pool", "subject-a", "seed")
    grouped = _run("pool", "subject-a", "seed", "--group", "current")

    assert "plate.png" in root.output and "tucked-away" not in root.output
    assert "tucked-away.webp" in grouped.output and "plate.png" not in grouped.output


def test_textblock_prints_the_raw_sections_when_none_is_authored(library):
    """The half of the command that was documented, coded for, and never worked.

    `cmd_textblock` has always read `found["raw"]` for this case and the route
    has always answered `{id, text}` alone, so an un-authored character got
    `{}` and a paragraph of instructions on how to compress it. Only the
    authored path had a test — on either side of the wire.
    """
    record = CHARACTER.resolve("subject-a")
    PROFILE.save_profile(record, {**PROFILE.document(record), "text_identity_block": ""})

    result = _run("textblock", "subject-a")

    assert result.exit_code == 0, result.output
    assert "{}" not in result.output
    # The identity-bearing sections, as raw material to compress.
    assert "silhouette" in result.output and "structure" in result.output
    # `rendering` and `voice` are not identity-bearing: a text-only engine is
    # being told what the character looks like, not what medium or accent.
    assert "default_style" not in result.output


def test_textblock_treats_the_unfilled_template_as_no_block(library):
    """`<>` is what `create` leaves behind, and it must never reach a prompt.

    The CLI used to make this judgement itself, which left the SPA free to make
    the opposite one and paste a literal `<>` into a model.
    """
    record = CHARACTER.resolve("subject-a")
    PROFILE.save_profile(record, {**PROFILE.document(record), "text_identity_block": "<>"})

    result = _run("textblock", "subject-a")

    assert result.exit_code == 0, result.output
    assert "<>" not in result.output
    assert "silhouette" in result.output





