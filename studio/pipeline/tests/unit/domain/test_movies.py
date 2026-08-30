"""`domain/movies.py` — the tier above a scene.

**This module was patched in both #489 and #490 and had no test file**, and the
coverage run that arrived with the tooling put it at 56% — the thinnest of the
board/panel cluster by a clear margin, against `storyboard.py` at 95%. The gap
was almost all of `create`: the half that moves bytes and writes the record.

A movie is DERIVED — its scenes name their runs and the runs are the history —
so the only thing it actually contributes is the ORDER. That is what most of
this file is about.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E
from studio_pipeline.adapters import store
from studio_pipeline.domain import movies as MV
from studio_pipeline.domain import projects as PROJECTS
from studio_pipeline.domain import scenes as SC


def _run(*args):
    return CliRunner().invoke(cli.main, ["movies", *args])


def _plan(tmp_path, name="plan.json", **over):
    doc = {
        "defaults": {"model": "kling", "panel_model": "nano-banana-pro", "duration": 5},
        "shots": [{"beat": "one", "panels": [{"prompt": "a"}],
                   "motion": {"prompt": "m1"}}],
    }
    doc.update(over)
    path = tmp_path / name
    path.write_text(json.dumps(doc))
    return str(path)


@pytest.fixture
def cut_scene(library, tmp_path):
    """A scene with an `output` node on it — i.e. one that has been assembled.

    Built by hand rather than by running `scenes assemble`, which would stitch
    with ffmpeg: what is under test here is the MOVIE, and a real encode per
    test buys nothing this file asserts.
    """
    def make(slug, characters=()):
        project = PROJECTS.resolve("porch-teaser")
        scene = SC.new_scene(project, slug, _plan(tmp_path, f"{slug}.json"))
        folder = SC.scene_folder(scene, "output")
        node = store.upload_into(folder, f"{slug}.mp4", _clip(tmp_path, slug),
                                 content_type="video/mp4")
        return E.patch_scene(scene["id"], status="assembled",
                             characters=list(characters),
                             output={"node": node["id"], "duration": 5.0})
    return make


def _clip(tmp_path, slug):
    """Bytes that stand in for a rendered cut. Never decoded by these tests."""
    path = tmp_path / f"{slug}-source.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)
    return path


# ── resolving ───────────────────────────────────────────────────────────────


def test_a_movie_resolves_by_id_by_slug_and_by_fragment(library):
    """Three spellings, one record. The id needs no project at all — a movie
    names its scenes by id, so nothing has to remember which project it is in."""
    record = E.create_movie(project=library.project, slug="the-cut")

    assert MV.resolve_movie(record["id"])["id"] == record["id"]
    assert MV.resolve_movie("porch-teaser/the-cut")["id"] == record["id"]
    assert MV.resolve_movie("the-cut", library.project)["id"] == record["id"]
    assert MV.resolve_movie("porch-teaser/he-cu")["id"] == record["id"]


def test_latest_reads_created_off_the_row(library):
    """It used to be `ids[-1]` over folder names, which was only chronological
    because every id happened to start with a timestamp."""
    E.create_movie(project=library.project, slug="first")
    second = E.create_movie(project=library.project, slug="second")

    assert MV.resolve_movie("porch-teaser/latest")["id"] == second["id"]
    assert MV.resolve_movie("porch-teaser/last")["id"] == second["id"]


def test_a_bare_slug_with_no_project_is_a_clean_refusal(library):
    """Not a traceback, and it names the spelling that would work."""
    with pytest.raises(SystemExit):
        MV.resolve_movie("the-cut")


def test_an_ambiguous_fragment_names_the_candidates(library):
    """Rather than picking one. Both would be a plausible answer, which is
    exactly when guessing is worst."""
    E.create_movie(project=library.project, slug="cut-one")
    E.create_movie(project=library.project, slug="cut-two")

    with pytest.raises(SystemExit):
        MV.resolve_movie("porch-teaser/cut-")


def test_a_project_with_no_movies_says_so_rather_than_indexing_nothing(library):
    with pytest.raises(SystemExit):
        MV.resolve_movie("porch-teaser/latest")


def test_a_movie_id_that_is_not_there_is_refused_by_id(library):
    with pytest.raises(SystemExit):
        MV.resolve_movie("movie-00000000-0000-0000-0000-000000000000")


# ── what a movie is made of ─────────────────────────────────────────────────


def test_scene_characters_is_read_off_the_row_and_never_recomputed(library):
    """A scene records this when it is assembled, from the runs behind its
    shots. The walk this used to fall back to has nowhere left to come from."""
    assert MV.scene_characters({"characters": ["char-1", "char-2"]}) == ["char-1", "char-2"]
    assert MV.scene_characters({}) == []
    assert MV.scene_characters({"characters": None}) == []


def test_a_movie_folder_is_named_by_the_row_not_derived_from_the_slug(library):
    """So renaming a movie strands nothing."""
    record = E.create_movie(project=library.project, slug="the-cut")
    inner = MV.movie_folder(record, "scenes")

    assert store.node(inner)["name"] == "scenes"
    # Idempotent: asking twice is the same folder, not a second one.
    assert MV.movie_folder(record, "scenes") == inner


# ── create ──────────────────────────────────────────────────────────────────


def test_every_unassembled_scene_is_reported_at_once(library, tmp_path):
    """A scene can exist as a plan, so "not assembled" is an ordinary state.

    One per attempt would be one round trip per missing scene.
    """
    project = PROJECTS.resolve("porch-teaser")
    SC.new_scene(project, "one", _plan(tmp_path, "one.json"))
    SC.new_scene(project, "two", _plan(tmp_path, "two.json"))

    result = _run("new", "porch-teaser", "--slug", "the-cut",
                  "--scene", "porch-teaser/one", "--scene", "porch-teaser/two")

    assert result.exit_code == 1
    assert "one" in result.output and "two" in result.output
    assert "scenes assemble" in result.output


def test_nothing_is_created_when_a_scene_is_not_cut(library, tmp_path):
    """The refusal happens before `create_movie`, so a failed attempt leaves no
    half-movie behind for somebody to find later and wonder about."""
    project = PROJECTS.resolve("porch-teaser")
    SC.new_scene(project, "one", _plan(tmp_path, "one.json"))

    _run("new", "porch-teaser", "--slug", "the-cut", "--scene", "porch-teaser/one")

    assert MV.list_movies(PROJECTS.resolve("porch-teaser")) == []


def test_a_movie_records_the_order_it_was_given(library, cut_scene, tmp_path,
                                               monkeypatch):
    """**The order is the only thing a movie contributes.**

    Its scenes name their runs and the runs are the history, so everything else
    about it can be rebuilt. `scenes` on the row is a list of scene IDS, which
    survive every rename of every scene in it.
    """
    second = cut_scene("second")
    first = cut_scene("first")

    record = MV.create(PROJECTS.resolve("porch-teaser"), "the-cut",
                       ["porch-teaser/second", "porch-teaser/first"])

    # `scenes` is the cut list in order, as the API sends it: a row per cut.
    #
    # This used to assert the resolved ENTRIES the CLI had built — `{scene, n,
    # node, duration}` — because it PATCHed those straight onto the
    # relationship and the fake stored them. The service validates every entry
    # as a scene id and answers 500, so `movies new` had been dying at that call
    # against the real API, after the whole cut had been stitched and uploaded.
    assert [row["id"] for row in record["scenes"]] == [second["id"], first["id"]]
    assert record["status"] == "assembled"

    # The per-cut detail did not go away — it moved to the stitch report, next
    # to the rest of what the encoder recorded.
    assert [cut["n"] for cut in record["stitch"]["cuts"]] == [1, 2]
    assert [cut["scene"] for cut in record["stitch"]["cuts"]] == [second["id"], first["id"]]


def test_the_cut_is_a_render_job_naming_node_ids_in_order(
        library, cut_scene, tmp_path, monkeypatch):
    """**This asserted the opposite and the reversal is the whole change.**

    It said ffmpeg ships in this wheel and the Lambda has none, so `create`
    downloads each scene, stitches HERE and uploads the result — and it checked
    that the stitcher was handed LOCAL paths. It is handed node ids now, in one
    `POST /api/renders`, and the worker does the download, the copy, the stitch
    and the record.

    What is still this package's responsibility, and what this therefore asserts:
    the right kind, the parts in CUT ORDER, resolved to nodes, and the record
    read back from the service rather than asserted here.
    """
    cut_scene("one")

    record = MV.create(PROJECTS.resolve("porch-teaser"), "the-cut",
                       ["porch-teaser/one"])

    job = list(library.fake.renders.values())[-1]
    assert job["kind"] == "assemble"
    assert job["params"]["target"] == record["id"]
    # The scene's own cut, by node id — not the scene id, and not a URL.
    scene = library.fake.scenes[record["scenes"][0]["id"]]
    assert [part["node"] for part in job["params"]["parts"]] == [scene["output"]["node"]]
    assert [part["scene"] for part in job["params"]["parts"]] == [scene["id"]]
    assert record["output"]["node"]
    assert record["stitch"]["uniform_scenes"] is True


def test_each_scene_is_copied_in_rather_than_referenced(library, cut_scene, monkeypatch):
    """A movie stays playable and re-cuttable while its scenes are rebuilt.

    A second node on one blob is copy-on-write (#334) and the API's delete route
    destroys the shared bytes when either row goes — so this is a read plus a
    write where it was once a server-side copy.
    """
    scene = cut_scene("one")

    record = MV.create(PROJECTS.resolve("porch-teaser"), "the-cut", ["porch-teaser/one"])

    copied = store.children_of(MV.movie_folder(record, "scenes"))
    assert [node["name"] for node in copied] == ["scene-01.mp4"]
    # A different node from the scene's own output — the copy, not a pointer.
    assert copied[0]["id"] != scene["output"]["node"]


def test_the_characters_are_the_union_of_the_scenes(library, cut_scene, monkeypatch):
    """Read off each scene's row, deduplicated and sorted."""
    cut_scene("one", characters=["char-b", "char-a"])
    cut_scene("two", characters=["char-a"])

    record = MV.create(PROJECTS.resolve("porch-teaser"), "the-cut",
                       ["porch-teaser/one", "porch-teaser/two"])

    assert record["characters"] == ["char-a", "char-b"]


# `_local_stitch` used to live here — a `monkeypatch.setattr(MV, "stitch", …)`
# standing in for ffmpeg, because a real encode per case cost seconds and proved
# nothing about the record. There is nothing left to stand in for: `MV.stitch`
# does not exist, the encode is a render job, and `tests/support/fake_api.py`
# answers `POST /api/renders` by doing the record-keeping half synchronously.


# ── the CLI half ────────────────────────────────────────────────────────────


def test_list_says_so_when_a_project_has_no_movies(library):
    result = _run("list", "porch-teaser")
    assert result.exit_code == 0, result.output
    assert "no movies" in result.output


def test_list_shows_every_movie_newest_first(library):
    E.create_movie(project=library.project, slug="first")
    E.create_movie(project=library.project, slug="second")

    result = _run("list", "porch-teaser")

    assert result.exit_code == 0, result.output
    assert result.output.index("second") < result.output.index("first")


def test_show_reports_a_movie_that_is_not_there(library):
    result = _run("show", "porch-teaser/nothing")
    assert result.exit_code == 1
