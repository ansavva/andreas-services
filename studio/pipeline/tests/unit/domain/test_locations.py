"""`studio location` — the second subject, on the same commands as a character.

`domain/subjects.py` builds both command trees, so a location gets a
character's `list`, `show`, `create`, `edit`, `selection` and the rest by
construction; `test_characters.py` pins how those behave. What this module
pins is what a location has of its OWN, and the one place the two subjects
meet: **a run binds both, and records both.**

* The record is `loc-…`, in its own listing, seeded from its own template —
  a bible of `space`, `lighting` and `palette`, with no `face`.
* `--location` on `studio run` adds the location's `default` images to the
  reference list AFTER the characters', narrowed by `--location-tag`, and the
  draft records `locations` beside `characters`.
* `runs list --location` and `runs find --location` are one query each.
"""
from __future__ import annotations

import json

import yaml
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E, store
from studio_pipeline.domain import locations as LOCATION


def _run(*args):
    return CliRunner().invoke(cli.main, ["location", *args])


def _a_room(fake, name="dev-kitchen"):
    """A location with two `default` views and one untagged snapshot."""
    record = E.create_subject(E.LOCATIONS, name)
    reference = fake._create_node(record["root"], "reference", "folder")
    wide = fake.put_file(reference["id"], "wide-from-door.png", b"png-w")["id"]
    reverse = fake.put_file(reference["id"], "reverse-to-window.png", b"png-rr")["id"]
    scrap = fake.put_file(reference["id"], "phone-snap.png", b"png-s")["id"]
    store.describe_node(wide, description="wide from the door", tags=["default", "wide"])
    store.describe_node(reverse, description="reverse to the window",
                        tags=["default", "reverse"])
    store.describe_node(scrap, description="a phone snapshot", tags=["scrap"])
    return record, {"wide": wide, "reverse": reverse, "scrap": scrap}


# ── the record ──────────────────────────────────────────────────────────────


def test_a_location_is_its_own_kind(library):
    """`loc-`, listed apart from characters, and never resolvable as one."""
    result = _run("create", "dev-kitchen")
    assert result.exit_code == 0, result.output
    record = LOCATION.resolve("dev-kitchen")
    assert record["id"].startswith("loc-")
    assert library.fake._children(record["root"]) == []

    listed = _run("list")
    assert "dev-kitchen" in listed.output
    assert record["id"] not in {c["id"] for c in E.list_characters()}
    assert CliRunner().invoke(cli.main, ["character", "show", "dev-kitchen"]).exit_code == 1


def test_a_location_starts_from_the_location_template(library):
    """Seeded from `templates/location.yaml`, and the bible reads as one document."""
    _run("create", "dev-kitchen")
    shown = _run("show", "dev-kitchen", "--profile")
    assert shown.exit_code == 0, shown.output
    document = yaml.safe_load(shown.output)
    assert document["name"] == "dev-kitchen"
    assert set(document) == set(LOCATION.PROFILE_KEYS)
    assert "face" not in document
    assert "vantages" in document["rendering"]


def test_a_pushed_bible_is_held_to_the_location_schema(library, tmp_path):
    """A character's bible pushed at a location is refused: no `space` in it."""
    _run("create", "dev-kitchen")
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text(yaml.safe_dump({"name": "dev-kitchen", "identity": {}, "face": {}}))
    result = _run("set-profile", "dev-kitchen", str(wrong))
    assert result.exit_code == 1
    assert "space" in result.output
    assert "location.yaml" in result.output


def test_the_edit_round_trip_writes_the_location_back(library, tmp_path, monkeypatch):
    monkeypatch.setattr(LOCATION.SUBJECT, "local_dir", str(tmp_path))
    _run("create", "dev-kitchen")

    pulled = _run("edit", "dev-kitchen")
    assert pulled.exit_code == 0, pulled.output
    local = tmp_path / "dev-kitchen.yaml"
    document = yaml.safe_load(local.read_text())
    document["space"]["layout"] = "an L, the door on the short leg"
    local.write_text(yaml.safe_dump(document, sort_keys=False))

    pushed = _run("edit", "dev-kitchen")
    assert pushed.exit_code == 0, pushed.output
    assert LOCATION.load_profile("dev-kitchen")["space"]["layout"] == \
        "an L, the door on the short leg"


# ── the selection ───────────────────────────────────────────────────────────


def test_a_vantage_is_a_tag(library):
    record, views = _a_room(library.fake)
    everything = LOCATION.selection_nodes(record)
    assert [e["node"] for e in everything] == [views["reverse"], views["wide"]]
    assert [e["node"] for e in LOCATION.selection_nodes(record, tags=["wide"])] == [views["wide"]]

    result = _run("selection", "dev-kitchen", "--tag", "wide")
    assert result.exit_code == 0, result.output
    assert "wide-from-door.png" in result.output or views["wide"] in result.output


# ── a run binds both subjects ───────────────────────────────────────────────


def test_a_run_binds_the_location_after_the_characters(library, monkeypatch):
    """The location's `default` views join the reference list after the cast's.

    Order is the contract: the prompt cites `[Image1]`, and the person reading
    the payload has to know the room's wide is `[Image3]` and not the face.
    """
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")
    record, views = _a_room(library.fake)

    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "subject-a at the counter", "--character", "subject-a",
        "--location", "dev-kitchen", "--location-tag", "wide", "--dry-run",
    ])
    assert result.exit_code == 0, result.output

    draft = E.get_run(E.query_runs(project=library.project, status="draft")["runs"][0]["id"])
    assert [s["node"] for s in draft["sends"]] == [library.face_1, library.face_2, views["wide"]]
    assert draft["characters"] == [library.character]
    assert draft["locations"] == [record["id"]]


def test_a_location_alone_is_enough_to_bind(library, monkeypatch):
    """A set with nobody in it is a legitimate frame — no `--character` needed."""
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")
    record, views = _a_room(library.fake)

    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "the empty kitchen at dawn", "--location", "dev-kitchen", "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    draft = E.get_run(E.query_runs(project=library.project, status="draft")["runs"][0]["id"])
    assert sorted(s["node"] for s in draft["sends"]) == sorted([views["wide"], views["reverse"]])
    assert draft["characters"] == []
    assert draft["locations"] == [record["id"]]


def test_an_unknown_location_is_refused_before_anything_is_drafted(library, monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")
    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "nowhere", "--location", "no-such-room", "--dry-run",
    ])
    assert result.exit_code == 1
    assert "no-such-room" in result.output
    assert E.query_runs(project=library.project, status="draft")["runs"] == []


def test_runs_are_found_by_location(library, monkeypatch):
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")
    record, _views = _a_room(library.fake)
    CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "the kitchen", "--location", "dev-kitchen", "--dry-run",
    ])
    draft = E.query_runs(project=library.project, status="draft")["runs"][0]
    E.patch_run(draft["id"], status="succeeded")

    found = CliRunner().invoke(cli.main, ["runs", "find", "--location", "dev-kitchen", "--json"])
    assert found.exit_code == 0, found.output
    assert [r["id"] for r in json.loads(found.output)] == [draft["id"]]

    listed = CliRunner().invoke(cli.main, [
        "runs", "list", "porch-teaser", "--location", record["id"], "--json"])
    assert listed.exit_code == 0, listed.output
    assert [r["id"] for r in json.loads(listed.output)] == [draft["id"]]

    neither = CliRunner().invoke(cli.main, ["runs", "find"])
    assert neither.exit_code == 1
    assert "exactly one" in neither.output
