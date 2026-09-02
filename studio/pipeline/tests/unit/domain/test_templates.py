"""`studio spec` — moving the reference spec between stacks through a file."""

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.domain import templates as SPEC

TEMPLATE = {
    "name": "Face, front",
    "prompt": "A studio portrait of the person, front on. {block.face_only}",
    "description": "Head and shoulders, front on.",
    "tags": ["face", "front"],
}


def _doc(tmp_path, blocks=None, templates=None):
    path = tmp_path / "spec.yaml"
    path.write_text(SPEC.document({"blocks": blocks or {"face_only": "Take the face from the images."},
                                   "templates": templates if templates is not None else [TEMPLATE]}),
                    encoding="utf-8")
    return str(path)


def _push(path, *extra):
    return CliRunner().invoke(cli.main, ["templates", "push", "--path", path, *extra])


def test_a_document_round_trips_through_yaml(tmp_path):
    """Prose has to survive the trip readable, or nobody will edit the file.

    A block is a paragraph. YAML's folded scalars turn one into a single long
    line as soon as it contains a colon, which every one of these does.
    """
    original = {"blocks": {"face_only": "THE FACE COMES FROM THE REFERENCE IMAGES.\nStudy the nose."},
                "templates": [TEMPLATE]}
    path = tmp_path / "spec.yaml"
    path.write_text(SPEC.document(original), encoding="utf-8")
    assert "|" in path.read_text(encoding="utf-8"), "prose was not dumped as a block scalar"
    assert SPEC.read_file(str(path)) == original


def test_compare_sorts_rows_into_new_same_and_differing():
    wanted = {"blocks": {"a": "one", "b": "two"}, "templates": [TEMPLATE]}
    held = {"blocks": {"a": "one", "b": "CHANGED"}, "templates": []}
    new, same, differing = SPEC.compare(wanted, held)
    assert [(k, n) for k, n, _w, _h in new] == [("template", "Face, front")]
    assert [(k, n) for k, n, _w, _h in same] == [("block", "a")]
    assert [(k, n) for k, n, _w, _h in differing] == [("block", "b")]


def test_a_push_writes_rows_the_destination_does_not_have(library, tmp_path):
    result = _push(_doc(tmp_path))
    assert result.exit_code == 0, result.output
    assert library.fake.spec_blocks["face_only"] == "Take the face from the images."
    assert library.fake.templates["Face, front"]["prompt"]


def test_a_push_refuses_a_row_that_differs_and_writes_NOTHING(library, tmp_path):
    """The one case where both sides might be right.

    Production may carry a fix nobody put back into dev. Overwriting reverts it
    silently; skipping reports success while the two stacks disagree. So it
    refuses — and it writes nothing AT ALL, not even the rows that were fine,
    because a half-applied spec is the state hardest to reason about.
    """
    library.fake.spec_blocks["face_only"] = "A FIX SOMEBODY MADE HERE."
    result = _push(_doc(tmp_path))

    assert result.exit_code == 1
    assert "A FIX SOMEBODY MADE HERE." in result.output      # the destination's side
    assert "Take the face from the images." in result.output  # the file's side
    assert "--force" in result.output
    # The block is untouched, AND the template that had no conflict was not written.
    assert library.fake.spec_blocks["face_only"] == "A FIX SOMEBODY MADE HERE."
    assert "Face, front" not in library.fake.templates


def test_force_overwrites_the_row_that_differed(library, tmp_path):
    library.fake.spec_blocks["face_only"] = "stale"
    result = _push(_doc(tmp_path), "--force")
    assert result.exit_code == 0, result.output
    assert library.fake.spec_blocks["face_only"] == "Take the face from the images."


def test_a_dry_run_writes_nothing(library, tmp_path):
    result = _push(_doc(tmp_path), "--dry-run")
    assert result.exit_code == 0, result.output
    assert not library.fake.spec_blocks
    assert not library.fake.templates


def test_a_push_never_deletes_a_row_the_file_does_not_mention(library, tmp_path):
    """A file states what it contains, not that nothing else exists.

    The destination is a live library somebody may have added an template to —
    the same reason `config sync` never deletes an angle image the repo has
    dropped.
    """
    library.fake.templates["Body, front"] = {"name": "Body, front"}
    result = _push(_doc(tmp_path))
    assert result.exit_code == 0, result.output
    assert "Body, front" in library.fake.templates


def test_pull_writes_what_the_stack_holds(library, tmp_path):
    library.fake.spec_blocks["face_only"] = "held text"
    library.fake.templates["Face, front"] = dict(TEMPLATE)
    path = tmp_path / "out.yaml"
    result = CliRunner().invoke(cli.main, ["templates", "pull", "--path", str(path)])
    assert result.exit_code == 0, result.output
    assert SPEC.read_file(str(path))["blocks"]["face_only"] == "held text"


def test_a_file_that_is_not_a_spec_is_refused_before_anything_is_sent(library, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("blocks:\n  face_only: 3\n", encoding="utf-8")
    result = _push(str(path))
    assert result.exit_code != 0
    assert not library.fake.spec_blocks


def test_an_angle_with_no_id_is_refused(library, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("templates:\n  - group: face\n", encoding="utf-8")
    result = _push(str(path))
    assert result.exit_code != 0
    assert "id" in result.output


def test_show_says_so_when_a_library_holds_no_templates(library):
    result = CliRunner().invoke(cli.main, ["templates", "show"])
    assert "no templates" in result.output


@pytest.mark.parametrize("field", ["prompt", "description", "tags"])
def test_every_template_field_that_changes_counts_as_a_difference(field):
    """A change to any of them has to be seen, not just the prompt.

    `description` and `tags` are what a promotion starts from when the image
    this makes becomes identity, so a stale one is a wrong caption on an
    identity image — exactly as damaging as a wrong prompt and far less visible.

    **`name` is not among them, because it is the KEY.** A template with a new
    name is a template the destination does not have, which `compare` reports as
    new rather than as differing — and a push writes it beside the old one
    rather than renaming, because a file states what it contains and never that
    nothing else exists.
    """
    changed = dict(TEMPLATE)
    changed[field] = ["other"] if field == "tags" else "other"
    _new, _same, differing = SPEC.compare(
        {"blocks": {}, "templates": [changed]}, {"blocks": {}, "templates": [TEMPLATE]})
    assert [n for _k, n, _w, _h in differing] == ["Face, front"]


def test_a_renamed_template_is_NEW_rather_than_a_difference():
    """The name is the key, so changing it is not a change to a row.

    A push states what a file contains and never that nothing else exists — the
    same reason it does not delete a row the file stops mentioning — so renaming
    in the file and pushing leaves both, and dropping the old one is a delete
    somebody performs deliberately.
    """
    renamed = {**TEMPLATE, "name": "Face, straight on"}
    new, _same, differing = SPEC.compare(
        {"blocks": {}, "templates": [renamed]}, {"blocks": {}, "templates": [TEMPLATE]})

    assert [n for _k, n, _w, _h in new] == ["Face, straight on"]
    assert differing == []
