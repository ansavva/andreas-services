"""The scene store, once a scene can exist before it is cut.

A scene used to be created only at the moment it was assembled, so "a scene"
and "a finished video" were the same thing and no code had to tell them apart.
Now a scene is planned first and cut later, which makes three things newly
breakable — and all three break quietly:

  * **`latest`.** It was `ids[-1]`, correct only while every id began with a
    timestamp. Slug-keyed ids sort after timestamped ones, so the old rule would
    have kept working and silently meant "alphabetically last".
  * **The scenes already in the bucket.** They are keyed `<timestamp>_<slug>`
    and have no plan behind them. They must keep resolving, and `movies` must
    keep cutting them, or a real finished piece becomes unreachable.
  * **A planned scene reaching `movies`.** `resolve_scene_output` reads the
    manifest's output key; a plan has none. The failure has to name the fix.
"""

from __future__ import annotations

import json

import pytest

from studio_pipeline.adapters.s3 import BUCKET
from studio_pipeline.domain import movies as MOV
from studio_pipeline.domain import scenes as SC
from studio_pipeline.domain import storyboard as SB

LEGACY = "2026-08-16_07-40-22_old-cut"
PLANNED = "board-test"


# --- addressing ------------------------------------------------------------

def test_a_slug_keyed_scene_resolves(media_bucket):
    assert SC.resolve_scene(media_bucket, f"subject-a/{PLANNED}") == ("subject-a", PLANNED)


def test_a_timestamped_scene_from_before_plans_still_resolves(media_bucket):
    """Not deprecation scaffolding — to this resolver both are directory names,
    and the scenes carrying the old shape are finished cuts worth keeping."""
    assert SC.resolve_scene(media_bucket, f"subject-a/{LEGACY}") == ("subject-a", LEGACY)


def test_a_unique_fragment_still_resolves(media_bucket):
    assert SC.resolve_scene(media_bucket, "subject-a/old-cut") == ("subject-a", LEGACY)


def test_latest_reads_the_manifests_rather_than_sorting_the_ids(media_bucket):
    """The fixture is built so the two rules disagree.

    `board-test` sorts last lexically but was created in January; the legacy
    scene sorts first but was created in December. `ids[-1]` would answer
    `board-test`, which is wrong — and would have been wrong silently, including
    for `studio movies new --scene <p>/latest`.
    """
    ids = SC.list_scenes(media_bucket, "subject-a")
    assert ids[-1] == PLANNED, "the fixture only means something if this holds"
    assert SC.resolve_scene(media_bucket, "subject-a/latest") == ("subject-a", LEGACY)


def test_an_unreadable_manifest_does_not_break_latest(media_bucket):
    """`latest` is a convenience; it must not be what stops you reaching the
    scene you actually named."""
    media_bucket.put_object(Bucket=BUCKET,
                            Key="projects/subject-a/scenes/broken/scene.json",
                            Body=b"{not json")
    assert SC.resolve_scene(media_bucket, "subject-a/latest") == ("subject-a", LEGACY)


def test_a_scene_folder_with_no_manifest_does_not_break_latest(media_bucket):
    media_bucket.put_object(Bucket=BUCKET,
                            Key="projects/subject-a/scenes/empty/shots/shot-01.mp4",
                            Body=b"mp4-bytes")
    assert SC.resolve_scene(media_bucket, "subject-a/latest") == ("subject-a", LEGACY)


# --- the manifest ----------------------------------------------------------

def test_read_manifest_returns_none_for_a_scene_that_is_not_there(media_bucket):
    assert SC.read_manifest(media_bucket, "subject-a", "nope") is None


def test_a_planned_scene_is_not_assembled(media_bucket):
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    assert m["output"] is None
    assert SC.is_assembled(m) is False
    assert SC.scene_output_key(m) is None


def test_a_legacy_scene_is_assembled(media_bucket):
    m = SC.read_manifest(media_bucket, "subject-a", LEGACY)
    assert SC.is_assembled(m) is True
    assert SC.scene_output_key(m).endswith("output/old-cut.mp4")


def test_writing_a_manifest_refreshes_the_derived_status(media_bucket):
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    m["shots"][1]["run"] = "subject-a/2026-08-18_10-00-00_shot-02"
    SC.write_manifest(media_bucket, m)

    back = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    assert back["shots"][1]["status"] == "rendered"
    assert back["status"] == "shooting"
    assert back["updated"] != "2026-01-01T00:00:00+00:00"


def test_a_manifest_is_written_back_where_it_came_from(media_bucket):
    """A legacy scene's directory is `<timestamp>_<slug>` while its `slug` field
    is the bare slug. Keying the write off `slug` would file it somewhere that
    does not exist and leave the original untouched."""
    m = SC.read_manifest(media_bucket, "subject-a", LEGACY)
    SC.write_manifest(media_bucket, m)

    assert SC.read_manifest(media_bucket, "subject-a", LEGACY) is not None
    assert SC.read_manifest(media_bucket, "subject-a", "old-cut") is None


# --- the contract movies depends on ----------------------------------------

def test_a_planned_scene_cut_into_a_movie_says_how_to_fix_it(media_bucket):
    with pytest.raises(SystemExit):
        MOV.resolve_scene_output(media_bucket, "subject-a", PLANNED)


def test_movies_reports_every_unassembled_scene_at_once(media_bucket, capsys):
    """One round trip per missing scene is the thing worth avoiding — a movie is
    cut from several scenes and they are typically planned together."""
    media_bucket.put_object(
        Bucket=BUCKET, Key="projects/subject-a/scenes/second-plan/scene.json",
        Body=json.dumps({"scene": "subject-a/second-plan", "project": "subject-a",
                         "slug": "second-plan", "shots": [], "output": None}).encode())

    with pytest.raises(SystemExit):
        MOV.create(media_bucket, "subject-a", "whole-thing",
                   [f"subject-a/{PLANNED}", "subject-a/second-plan"])

    err = capsys.readouterr().err
    assert "2 scene(s) are planned but not assembled" in err
    assert PLANNED in err and "second-plan" in err
    assert "studio scenes assemble" in err


def test_a_legacy_scene_still_cuts_into_a_movie(media_bucket):
    key, manifest = MOV.resolve_scene_output(media_bucket, "subject-a", LEGACY)
    assert key.endswith("output/old-cut.mp4")
    assert MOV.scene_characters(media_bucket, manifest) == ["subject-a"]


# --- the plan, read back off the record ------------------------------------

def test_the_stored_plan_survives_a_round_trip_through_the_rules(media_bucket):
    """The fixture is hand-written JSON standing in for a real `scene.json`; if
    the plan module cannot read it, every assertion built on it is hollow."""
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    SB.validate(m)

    assert SB.shot_status(m["shots"][0]) == "boarded"
    assert SB.shot_status(m["shots"][1]) == "planned"
    assert SB.scene_status(m) == "boarding"
    assert SB.sheet_captions(m) == [
        ("projects/subject-a/scenes/board-test/storyboard/shot-01-p1.png",
         "shot-01 p1 [start]"),
    ]


def test_the_second_shot_expects_a_handoff_and_does_not_have_one_yet(media_bucket):
    """Its panels cannot be resolved into a start frame until the shot before it
    has rendered — which is why `render` refuses a shot whose handoff is
    missing rather than quietly starting from a panel."""
    m = SC.read_manifest(media_bucket, "subject-a", PLANNED)
    r = SB.resolve_roles(m["shots"][1])
    assert m["shots"][1]["chain"]["use_handoff"] is True
    assert r["handoff"] is None
    assert r["start_panel"] == 0, "with no handoff recorded, the panel still holds the slot"
    assert r["end_panel"] == 1
