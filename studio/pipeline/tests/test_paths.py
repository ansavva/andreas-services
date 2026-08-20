"""What `domain/paths` builds, and what it is allowed to call (#303).

Two claims, and the second is the one worth having:

1. Entity paths are **name paths** — no bucket, no prefix, nothing an S3 client
   would need. They go to `adapters/store`, which resolves them.
2. The three **shared** builders — phrasebook, config, pose — never resolve
   anything. They address material that has no catalog node, and a resolve on
   one would 404 at the moment a reference shoot needs its pose plate.

The second claim is easy to break and impossible to notice: wiring `pose_key`
through the catalog fails only on a real stack, only on a shoot, and looks like
a missing file rather than a wrong call.
"""
from __future__ import annotations

import pytest

from studio_pipeline.adapters import api, store
from studio_pipeline.domain import paths as P


# ── entity paths are name paths ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "built,expected",
    [
        (lambda: P.character_key("subject-a", "profile.yaml"),
         "characters/subject-a/profile.yaml"),
        (lambda: P.profile_key("subject-a"), "characters/subject-a/profile.yaml"),
        (lambda: P.char_pool_prefix("subject-a", "reference"),
         "characters/subject-a/reference"),
        (lambda: P.project_json_key("proj"), "projects/proj/project.json"),
        (lambda: P.run_key("proj", "r1", "request.json"),
         "projects/proj/runs/r1/request.json"),
        (lambda: P.scene_key("proj", "s1", "scene.json"),
         "projects/proj/scenes/s1/scene.json"),
        (lambda: P.movie_key("proj", "m1", "movie.json"),
         "projects/proj/movies/m1/movie.json"),
        (lambda: P.chain_key("proj", "slug"), "projects/proj/chains/slug.json"),
        (lambda: P.input_key("proj", 3, ".png"), "projects/proj/input/proj_in_3.png"),
    ],
)
def test_entity_paths_carry_no_prefix(built, expected):
    assert built() == expected


def test_the_cli_has_no_bucket_prefix_to_apply(monkeypatch):
    """`STUDIO_S3_PREFIX` is gone from this half of studio, not defaulted.

    It used to prepend to every key built here. The API owns the root prefix
    now (`STUDIO_MEDIA_ROOT_PREFIX`), and two authorities that merely happened
    to agree is the failure this removal prevents.
    """
    monkeypatch.setenv("STUDIO_S3_PREFIX", "somewhere-else/")
    assert P.profile_key("subject-a") == "characters/subject-a/profile.yaml"


# ── listings go through the catalog ─────────────────────────────────────────

def _entries(*pairs):
    return [{"id": n, "name": n, "kind": k} for n, k in pairs]


def test_list_projects_asks_the_store_for_the_projects_folder(monkeypatch):
    asked = []

    def fake_children(path):
        asked.append(path)
        return _entries(("alpha", "folder"), ("beta", "folder"))

    monkeypatch.setattr(store, "children", fake_children)
    assert P.list_projects() == ["alpha", "beta"]
    assert asked == ["projects"]


def test_a_listing_returns_folders_only(monkeypatch):
    """`project.json` is not a project.

    The delimiter used to make this structural — `list_objects_v2` reported
    folders in a different field from objects. The catalog returns both in one
    list, so the filter is now a line of code that can be deleted.
    """
    monkeypatch.setattr(
        store, "children",
        lambda path: _entries(("alpha", "folder"), ("project.json", "file")),
    )
    assert P.list_characters() == ["alpha"]


def test_a_missing_folder_lists_as_empty_not_as_an_error(monkeypatch):
    """A library with no `characters/` yet is empty, not broken.

    The paginator this replaced answered with zero `CommonPrefixes`; `resolve`
    answers with a 404. Callers ask "what is there" and none of them tell the
    two apart, so neither does this.
    """
    def raise_not_found(path):
        raise api.NotFound(f"No such object: {path}", 404)

    monkeypatch.setattr(store, "children", raise_not_found)
    assert P.list_characters() == []
    assert P.list_projects() == []
    assert P.list_ids("projects/proj/runs") == []


def test_a_real_api_failure_is_not_swallowed(monkeypatch):
    """Only 404 means empty. A 403 is a different fact and must surface."""
    def raise_forbidden(path):
        raise api.Forbidden("nope", 403)

    monkeypatch.setattr(store, "children", raise_forbidden)
    with pytest.raises(api.Forbidden):
        P.list_characters()


def test_folder_names_sort_naturally(monkeypatch):
    """`_2` before `_10`, which lexical ordering gets backwards."""
    monkeypatch.setattr(
        store, "children",
        lambda path: _entries(("shot_10", "folder"), ("shot_2", "folder")),
    )
    assert P.list_characters() == ["shot_2", "shot_10"]


def test_ids_sort_chronologically(monkeypatch):
    """Run and scene ids start with a timestamp, so plain sort is oldest-first."""
    monkeypatch.setattr(
        store, "children",
        lambda path: _entries(
            ("20260819-120000-b", "folder"), ("20260818-090000-a", "folder")
        ),
    )
    assert P.list_ids("projects/proj/runs") == [
        "20260818-090000-a",
        "20260819-120000-b",
    ]


# ── shared material never touches the catalog ───────────────────────────────

SHARED = [
    (P.phrasebook_key, (), "phrasebook/wording.yaml"),
    (P.config_key, ("pose", "body", "stand.png"), "config/pose/body/stand.png"),
    (P.pose_key, ("face", "three-quarter.png"), "config/pose/face/three-quarter.png"),
]


@pytest.mark.parametrize("builder,args,expected", SHARED)
def test_shared_builders_never_resolve(builder, args, expected, monkeypatch):
    """The load-bearing one. See the module docstring.

    `dev-setup.sh` syncs these into the bucket and `catalog_seed.py` records
    neither, so there is no node to resolve. Anything reached here must be a
    plain string, computed without a round trip.
    """
    def forbidden(*a, **k):
        raise AssertionError(
            "shared material was resolved through the catalog; it has no node"
        )

    monkeypatch.setattr(store, "resolve", forbidden)
    monkeypatch.setattr(store, "children", forbidden)
    monkeypatch.setattr(api, "get", forbidden)
    assert builder(*args) == expected


def test_shared_material_is_read_by_key_through_the_api(monkeypatch):
    """`store.shared_read` goes to `/api/asset`, not to boto3 and not to resolve."""
    calls = {}

    def fake_get(route, **params):
        calls["route"] = route
        calls["params"] = params
        return {"url": "https://signed.example/plate.png"}

    monkeypatch.setattr(api, "get", fake_get)
    monkeypatch.setattr(store, "_fetch", lambda url: b"plate-bytes")

    assert store.shared_read(P.pose_key("body", "stand.png")) == b"plate-bytes"
    assert calls["route"] == "/api/asset"
    assert calls["params"]["key"] == "config/pose/body/stand.png"
