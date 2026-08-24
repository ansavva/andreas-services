"""`studio curate` — what survives, and what has nothing left to do.

**Two of this file's four subjects were deleted, and the reason is the same one
in both cases.** `renumber` closed holes in a reference group's numbering,
because order was the trailing number in a filename; `order` is an attribute of
a `REF#` row now, gapped by 1000, so there are no holes. `regroup` moved images
into a purpose subfolder and rewrote every record citing them; a group is an
attribute of the same row, so it moved to `studio character regroup` where it is
one `PATCH` and writes no object.

Their tests are not deleted quietly. `test_the_deleted_commands_are_gone_and_say
_where_to_go` keeps the fact that they existed, and the two tests below it assert
the behaviour that replaced each — because "this command was removed" is only
half a claim without "and this is what does it now".

What survives is `dedupe`, `move` and `groups`, and every one of them lost its
final pass over `rewrite.apply_moves`. Records name node ids; nothing can
dangle. The one exception is asserted directly: `dedupe` DESTROYS bytes, and a
`REF#` row pointing at a node that no longer exists is the one dangling this
model can still produce.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E, store
from studio_pipeline.domain import curate
from studio_pipeline.domain import characters as CHARACTER


def _run(*args):
    return CliRunner().invoke(cli.main, ["curate", *args])


# ── what is gone ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("gone", ["renumber", "regroup", "set-refs"])
def test_the_deleted_commands_are_gone(library, gone):
    """Kept as a test rather than dropped, so the removal is a recorded fact.

    A command that quietly stops existing reads as a broken install to whoever
    typed it from muscle memory.
    """
    assert gone not in curate.main.commands


def test_what_replaced_renumber_needs_no_renumbering(library):
    """Order is a row attribute, so there are no holes to close.

    Deleting the middle of three references leaves the other two at 1000 and
    3000, and nothing anywhere cares — a gap in `order` is not a defect, it is
    the whole point of gapping by 1000.
    """
    third = library.fake.put_file(library.face_folder, "profile-left.webp", b"x")
    E.add_reference(library.character, third["id"], "face")
    E.delete_reference(library.character, library.face_2)

    orders = [e["order"]
              for e in E.reference_entries(library.character, group="face")]
    assert orders == [1000, 3000]
    chosen = CHARACTER.selection_nodes(CHARACTER.resolve("subject-a"),
                                       tags=None, pick=None)
    assert [e["slot"] for e in chosen] == list(range(1, len(chosen) + 1))


def test_what_replaced_regroup_writes_no_object(library):
    """One `PATCH` on the row, and the file does not move.

    `curate regroup` reparented the node AND swept every run, scene and chain
    document that cited its old path. Neither half is needed: a group is an
    attribute, and a record names the node.
    """
    parent_before = library.fake.nodes[library.body_1]["parent_id"]
    blob_before = library.fake.nodes[library.body_1]["blob_key"]

    result = CliRunner().invoke(cli.main, ["character", "regroup", "subject-a",
                                           library.body_1, "--to", "face"])

    assert result.exit_code == 0, result.output
    assert library.fake.nodes[library.body_1]["parent_id"] == parent_before
    assert library.fake.nodes[library.body_1]["blob_key"] == blob_before


# ── dedupe ──────────────────────────────────────────────────────────────────

def test_size_is_checked_before_any_byte_is_read(library, monkeypatch):
    """**Two files of different sizes cannot be identical.**

    Exact rather than a heuristic, and it matters more than it did: a read is an
    HTTPS round trip out of the bucket now, so hashing a forty-image pool to
    find no duplicates was about to become forty downloads.
    """
    read = []
    monkeypatch.setattr(curate, "digest", lambda node: read.append(node) or node)

    record = CHARACTER.resolve("subject-a")
    curate.duplicate_pairs(curate.images(record, "reference", "face"))
    assert read == []          # the two face images differ in size


def test_same_size_candidates_are_read_and_compared(library):
    """Same size is a candidate, not a duplicate — the bytes still decide.

    `other.webp` is the same LENGTH as `front-neutral.webp` and different in
    content, so it reaches the hash and is then correctly not a duplicate. That
    is the case a size-only rule would destroy.
    """
    same = library.fake.put_file(library.face_folder, "zz-copy.webp", b"webp-1")
    different = library.fake.put_file(library.face_folder, "other.webp", b"webp-9")

    record = CHARACTER.resolve("subject-a")
    pairs = curate.duplicate_pairs(curate.images(record, "reference", "face"))

    # The keeper is whichever came first in the listing, which is why the copy
    # is named to sort last — "keeps the first" is the promise, and a fixture
    # that sorted the other way would assert the opposite by accident.
    assert [(dupe["id"], keeper["id"]) for dupe, keeper in pairs] == [
        (same["id"], library.face_1)]
    assert different["id"] not in [d["id"] for d, _ in pairs]


def test_dedupe_is_a_dry_run_without_apply(library):
    library.fake.put_file(library.face_folder, "zz-copy.webp", b"webp-1")
    result = _run("dedupe", "subject-a", "--group", "face")

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert store.node(library.face_1)


def test_dedupe_removes_the_duplicate_and_keeps_the_first(library):
    copy = library.fake.put_file(library.face_folder, "zz-copy.webp", b"webp-1")
    result = _run("dedupe", "subject-a", "--group", "face", "--apply")

    assert result.exit_code == 0, result.output
    assert copy["id"] not in library.fake.nodes
    assert library.face_1 in library.fake.nodes


def test_dedupe_detaches_the_row_of_an_image_it_destroys(library):
    """**The one dangling this model can still produce.**

    A node id survives a rename, a reparent and a regroup — but not a delete,
    and `dedupe` is the only command here that deletes bytes. So the `REF#` row
    has to come off in the same act, or the index points at a node that is gone.
    """
    copy = library.fake.put_file(library.face_folder, "zz-copy.webp", b"webp-1")
    E.add_reference(library.character, copy["id"], "face")
    assert copy["id"] in {e["node"] for e in E.reference_entries(library.character)}

    result = _run("dedupe", "subject-a", "--group", "face", "--apply")

    assert result.exit_code == 0, result.output
    assert copy["id"] not in {e["node"]
                              for e in E.reference_entries(library.character)}


# ── move ────────────────────────────────────────────────────────────────────

def test_move_between_pools_is_a_reparent(library):
    """One row update. The blob keeps its key, its bytes and its node id.

    Under S3 a key IS the location, so this was a copy and a delete — a
    different object, and every record naming the first one stranded.
    """
    blob_before = library.fake.nodes[library.body_1]["blob_key"]

    result = _run("move", "subject-a", library.body_1,
                  "--from", "reference", "--to", "archive", "--apply")

    assert result.exit_code == 0, result.output
    record = CHARACTER.resolve("subject-a")
    archive = CHARACTER.pool_folder(record, "archive")
    assert library.fake.nodes[library.body_1]["parent_id"] == archive["id"]
    assert library.fake.nodes[library.body_1]["blob_key"] == blob_before


def test_a_moved_reference_is_still_a_reference(library):
    """**Because a row says so, not because of the folder it sits in.**

    This is the coupling the entity model removes, seen from the sharpest angle:
    the image is now in `archive/` and is still identity, and a person who wants
    it demoted detaches the row rather than moving the file.
    """
    _run("move", "subject-a", library.body_1,
         "--from", "reference", "--to", "archive", "--apply")

    assert library.body_1 in {e["node"]
                              for e in E.reference_entries(library.character)}


def test_move_is_a_dry_run_without_apply(library):
    before = library.fake.nodes[library.body_1]["parent_id"]
    result = _run("move", "subject-a", library.body_1,
                  "--from", "reference", "--to", "archive")

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert library.fake.nodes[library.body_1]["parent_id"] == before


def test_move_onto_an_identical_copy_deletes_the_source(library):
    """The one case that destroys bytes, and it says so.

    Nothing is preserved twice: a byte-identical copy is already waiting, so the
    source is removed rather than moved. It is also the only case whose records
    cannot follow anywhere.
    """
    record = CHARACTER.resolve("subject-a")
    archive = CHARACTER.pool_folder(record, "archive")
    library.fake.put_file(archive["id"], "full-length.webp", b"webp-333")

    result = _run("move", "subject-a", library.body_1,
                  "--from", "reference", "--to", "archive", "--apply")

    assert result.exit_code == 0, result.output
    assert "identical" in result.output
    assert library.body_1 not in library.fake.nodes


def test_move_names_a_file_that_is_not_in_the_pool(library):
    result = _run("move", "subject-a", "nothing.webp", "--from", "seed")
    assert result.exit_code == 1
    assert "not in" in result.output


def test_move_accepts_a_group_relative_name_a_person_would_type(library):
    """`reference/face/front-neutral.webp` is what a listing shows."""
    result = _run("move", "subject-a", "face/front-neutral.webp",
                  "--from", "reference", "--to", "archive")
    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output


# ── groups ──────────────────────────────────────────────────────────────────

def test_groups_counts_off_the_rows_not_the_folders(library):
    """A group is an attribute, so the count is a row count.

    It used to list `reference/`'s subfolders and count the images in each,
    which disagreed with the index the moment anything was described in one
    group and filed in another.
    """
    result = _run("groups", "subject-a")
    assert result.exit_code == 0, result.output
    assert "face" in result.output and "body" in result.output
    assert "TOTAL" in result.output


def test_groups_warns_when_the_set_exceeds_every_engine_cap(library):
    """`reference/` is a library, not a set to send whole."""
    for n in range(20):
        node = library.fake.put_file(library.face_folder, f"extra-{n}.webp", b"x" * (n + 1))
        E.add_reference(library.character, node["id"], "face")

    result = _run("groups", "subject-a")
    assert result.exit_code == 0, result.output
    assert "kling 7" in result.output


def test_move_into_a_group_lands_in_the_subfolder(library):
    """**The destination could only ever be a pool root.**

    The FILE argument has always reached into a subfolder — `face/front.webp` —
    so a pool could be organised one way and never reorganised. `--from seed
    --to seed`, the shape of every "it is in the wrong subfolder" fix, moved the
    file OUT of its subfolder and into the root beside the originals.
    """
    result = _run("move", "subject-a", library.body_1,
                  "--from", "reference", "--to", "archive",
                  "--to-group", "superseded", "--apply")

    assert result.exit_code == 0, result.output
    record = CHARACTER.resolve("subject-a")
    archive = CHARACTER.pool_folder(record, "archive")
    parent = library.fake.nodes[library.body_1]["parent_id"]
    assert parent != archive["id"], "landed in the pool root, not the group"
    assert library.fake.nodes[parent]["name"] == "superseded"
    assert library.fake.nodes[parent]["parent_id"] == archive["id"]


def test_the_duplicate_check_looks_inside_the_group(library):
    """Byte-identical *where it is going* — which is the subfolder now.

    Against the pool root it would compare with the wrong set: a file already in
    `archive/superseded/` is not a reason to destroy one heading for
    `archive/crops/`, and a file loose in `archive/` is not a reason to spare it.
    """
    record = CHARACTER.resolve("subject-a")
    archive = CHARACTER.pool_folder(record, "archive")
    group = store.ensure_child_folder(archive["id"], "superseded")
    source = library.fake.put_file(library.face_folder, "twin.webp", b"identical")
    library.fake.put_file(group["id"], "twin.webp", b"identical")

    result = _run("move", "subject-a", source["id"],
                  "--from", "reference", "--to", "archive",
                  "--to-group", "superseded", "--apply")

    assert result.exit_code == 0, result.output
    assert "byte-identical copy is already in archive/superseded/" in result.output
    assert source["id"] not in library.fake.nodes


def test_drop_is_a_dry_run_until_told_otherwise(library):
    stray = library.fake.put_file(library.face_folder, "spare.webp", b"spare")

    result = _run("drop", "subject-a", stray["id"], "--pool", "reference")

    assert result.exit_code == 0, result.output
    assert "DRY RUN" in result.output
    assert stray["id"] in library.fake.nodes


def test_drop_refuses_an_image_a_row_still_names(library):
    """**It refuses rather than detaching, and that is the difference from
    `dedupe`.**

    `dedupe` detaches in the same act because it is removing a duplicate of
    something the character still has. Dropping removes the thing itself, and
    whether a character still IS what that image shows is hard rule #2b's
    question — a person's, not a command's.
    """
    assert library.body_1 in {e["node"] for e in E.reference_entries(library.character)}

    result = _run("drop", "subject-a", library.body_1, "--pool", "reference", "--apply")

    assert result.exit_code != 0
    assert "REF# row still names" in result.output
    assert "studio character detach" in result.output
    assert library.body_1 in library.fake.nodes, "refused, and nothing destroyed"


def test_drop_destroys_what_it_named(library):
    """The gap it closes: a mistaken upload was previously permanent — it could
    be moved between pools forever and never removed."""
    stray = library.fake.put_file(library.face_folder, "never-meant-this.webp", b"oops")

    result = _run("drop", "subject-a", stray["id"], "--pool", "reference", "--apply")

    assert result.exit_code == 0, result.output
    assert "APPLIED" in result.output
    assert stray["id"] not in library.fake.nodes
    assert library.face_1 in library.fake.nodes, "took only what it was given"
