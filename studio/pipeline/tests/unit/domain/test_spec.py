"""`studio spec` — moving the reference spec between stacks through a file."""

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.domain import spec as SPEC

ANGLE = {
    "id": "face_front",
    "group": "face",
    "prompt": "A studio portrait of the person, front on. {face_only}",
    "description": "Head and shoulders, front on.",
    "tags": ["face", "front"],
    "order": 1000,
}


def _doc(tmp_path, blocks=None, angles=None):
    path = tmp_path / "spec.yaml"
    path.write_text(SPEC.document({"blocks": blocks or {"face_only": "Take the face from the images."},
                                   "angles": angles if angles is not None else [ANGLE]}),
                    encoding="utf-8")
    return str(path)


def _push(path, *extra):
    return CliRunner().invoke(cli.main, ["spec", "push", "--path", path, *extra])


def test_a_document_round_trips_through_yaml(tmp_path):
    """Prose has to survive the trip readable, or nobody will edit the file.

    A block is a paragraph. YAML's folded scalars turn one into a single long
    line as soon as it contains a colon, which every one of these does.
    """
    original = {"blocks": {"face_only": "THE FACE COMES FROM THE REFERENCE IMAGES.\nStudy the nose."},
                "angles": [ANGLE]}
    path = tmp_path / "spec.yaml"
    path.write_text(SPEC.document(original), encoding="utf-8")
    assert "|" in path.read_text(encoding="utf-8"), "prose was not dumped as a block scalar"
    assert SPEC.read_file(str(path)) == original


def test_compare_sorts_rows_into_new_same_and_differing():
    wanted = {"blocks": {"a": "one", "b": "two"}, "angles": [ANGLE]}
    held = {"blocks": {"a": "one", "b": "CHANGED"}, "angles": []}
    new, same, differing = SPEC.compare(wanted, held)
    assert [(k, n) for k, n, _w, _h in new] == [("angle", "face_front")]
    assert [(k, n) for k, n, _w, _h in same] == [("block", "a")]
    assert [(k, n) for k, n, _w, _h in differing] == [("block", "b")]


def test_a_push_writes_rows_the_destination_does_not_have(library, tmp_path):
    result = _push(_doc(tmp_path))
    assert result.exit_code == 0, result.output
    assert library.fake.spec_blocks["face_only"] == "Take the face from the images."
    assert library.fake.spec_angles["face_front"]["group"] == "face"


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
    # The block is untouched, AND the angle that had no conflict was not written.
    assert library.fake.spec_blocks["face_only"] == "A FIX SOMEBODY MADE HERE."
    assert "face_front" not in library.fake.spec_angles


def test_force_overwrites_the_row_that_differed(library, tmp_path):
    library.fake.spec_blocks["face_only"] = "stale"
    result = _push(_doc(tmp_path), "--force")
    assert result.exit_code == 0, result.output
    assert library.fake.spec_blocks["face_only"] == "Take the face from the images."


def test_a_dry_run_writes_nothing(library, tmp_path):
    result = _push(_doc(tmp_path), "--dry-run")
    assert result.exit_code == 0, result.output
    assert not library.fake.spec_blocks
    assert not library.fake.spec_angles


def test_a_push_never_deletes_a_row_the_file_does_not_mention(library, tmp_path):
    """A file states what it contains, not that nothing else exists.

    The destination is a live library somebody may have added an angle to —
    the same reason `config sync` never deletes an angle image the repo has
    dropped.
    """
    library.fake.spec_angles["body_front"] = {"id": "body_front", "group": "body"}
    result = _push(_doc(tmp_path))
    assert result.exit_code == 0, result.output
    assert "body_front" in library.fake.spec_angles


def test_pull_writes_what_the_stack_holds(library, tmp_path):
    library.fake.spec_blocks["face_only"] = "held text"
    library.fake.spec_angles["face_front"] = dict(ANGLE)
    path = tmp_path / "out.yaml"
    result = CliRunner().invoke(cli.main, ["spec", "pull", "--path", str(path)])
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
    path.write_text("angles:\n  - group: face\n", encoding="utf-8")
    result = _push(str(path))
    assert result.exit_code != 0
    assert "id" in result.output


def test_show_says_so_when_a_library_holds_no_spec(library):
    result = CliRunner().invoke(cli.main, ["spec", "show"])
    assert "no reference spec" in result.output


@pytest.mark.parametrize("field", ["prompt", "description", "tags", "group"])
def test_every_angle_field_that_changes_counts_as_a_difference(field):
    """A change to any of them has to be seen, not just the prompt.

    `description` and `tags` are written onto a promoted image by
    `add-refs --from-run`, so a stale one is a wrong caption on a reference —
    exactly as damaging as a wrong prompt and far less visible.
    """
    changed = dict(ANGLE)
    changed[field] = ["other"] if field == "tags" else "other"
    _new, _same, differing = SPEC.compare(
        {"blocks": {}, "angles": [changed]}, {"blocks": {}, "angles": [ANGLE]})
    assert [n for _k, n, _w, _h in differing] == ["face_front"]
