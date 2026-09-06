"""Favorites: one person's picks, filed under the person.

What these hold up is the half of the feature that is not the grid. A favorite
is per-caller, it is a row in the same `USER#<sub>` partition memberships live
in, and both of those are places where a plausible implementation is silently
wrong — a shared favorite looks identical until a second member signs in, and a
`FAV#` row in the membership partition breaks *library resolution* for everybody
who ever pressed the heart, on every route, not just on this one.
"""

import pytest

from studio_core import app_factory, config
from studio_core.services import catalog
from tests.conftest import CATALOG_LIBRARY, CATALOG_MEMBER, CATALOG_OWNER, node_id_at

IMAGE = "characters/subject-a/seed/subject-a_1.webp"
OTHER_IMAGE = "characters/subject-a/seed/subject-a_2.webp"
VIDEO = "projects/misc/runs/2026-08-14_16-32-11_kling-yqp1jqf5/output/kling.mp4"
TEXT = "characters/subject-a/profile.yaml"
FOLDER = "characters/subject-a/seed"


def _favorite(api, path):
    return api.post(f"/api/favorites/{node_id_at(path)}")


def _ids(api):
    return api.get("/api/favorites?view=ids").get_json()["ids"]


def _grid(api, query=""):
    resp = api.get(f"/api/favorites{query}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


# ─────────────────────────── the heart itself ───────────────────────────


def test_favoriting_a_picture_puts_it_on_the_list(api):
    assert _favorite(api, IMAGE).status_code == 201
    assert _ids(api) == [node_id_at(IMAGE)]


def test_pressing_twice_is_one_favorite_that_keeps_its_first_time(api):
    """**Idempotent, and stable.**

    A second press must not reorder the grid. The write is
    `if_not_exists(favorited_at, :now)` for exactly this: a double-tap on a
    phone is two requests, and a favorites screen that reshuffles under the
    second one looks broken in a way nobody can reproduce deliberately.
    """
    first = _favorite(api, IMAGE).get_json()
    second = _favorite(api, IMAGE).get_json()

    assert second["favorited_at"] == first["favorited_at"]
    assert _ids(api) == [node_id_at(IMAGE)]


def test_unfavoriting_something_that_was_never_favorited_is_fine(api):
    """A request that has already been satisfied. `tags.remove`'s rule."""
    resp = api.delete(f"/api/favorites/{node_id_at(IMAGE)}")

    assert resp.status_code == 200
    assert _ids(api) == []


def test_the_newest_pick_is_first(api):
    _favorite(api, IMAGE)
    _favorite(api, VIDEO)

    assert _ids(api) == [node_id_at(VIDEO), node_id_at(IMAGE)]


def test_a_video_can_be_favorited(api):
    """The request was "any video or image", and the video half is the one a
    kind check written from the reel's image cases would quietly drop."""
    assert _favorite(api, VIDEO).status_code == 201


def test_a_folder_cannot_be_favorited(api):
    resp = _favorite(api, FOLDER)

    assert resp.status_code == 400
    assert "folder" in resp.get_json()["error"]


def test_a_text_file_cannot_be_favorited(api):
    """The screen this feeds is a grid of media, and a favorite it cannot draw
    is a row that exists to disappoint whoever made it."""
    resp = _favorite(api, TEXT)

    assert resp.status_code == 400
    assert "image or a video" in resp.get_json()["error"]


# ─────────────────── filed under the person, not the library ───────────────────


def test_two_members_of_one_library_have_different_favorites(api, signed_in):
    """**The whole reason this is not a tag.**

    A tag is a fact about the picture and everyone sees it. A favorite is a fact
    about the person, and the second member of a shared library is entitled to
    an empty screen.
    """
    _favorite(api, IMAGE)

    signed_in.sub = CATALOG_MEMBER
    assert _ids(api) == []

    signed_in.sub = CATALOG_OWNER
    assert _ids(api) == [node_id_at(IMAGE)]


def test_a_favorite_does_not_read_as_a_membership(api, catalog_table):
    """**The failure this feature could most easily have shipped.**

    A favorite is filed under `USER#<sub>`, where the membership rows live, and
    `libraries_for` reads a library id off the sort key by splitting on the
    first `#`. Without `begins_with(sk, "LIB#")` a single favorite would make
    the caller appear to be a member of a library called `<lib>#<node_id>` —
    and `_resolve_library` refuses any request from a caller in more than one
    library that does not name which. So one press of the heart would 400 every
    subsequent request in the app, not just this route's.

    Read through `catalog` rather than through the route, because the route the
    bug breaks is *every other one*.
    """
    _favorite(api, IMAGE)

    assert [row["lib"] for row in catalog.libraries_for(CATALOG_OWNER)] == [CATALOG_LIBRARY]


def test_the_whole_app_still_answers_after_a_favorite(api):
    """The same failure, from the outside: a listing, after a heart."""
    _favorite(api, IMAGE)

    assert api.get("/api/nodes").status_code == 200


# ────────────────────────────── the grid ──────────────────────────────


def test_the_grid_draws_what_was_favorited(api):
    _favorite(api, IMAGE)
    page = _grid(api)

    assert page["total"] == 1
    entry = page["entries"][0]
    assert entry["id"] == node_id_at(IMAGE)
    assert entry["name"] == "subject-a_1.webp"
    assert entry["kind"] == "image"
    # Presigned, like every other listing entry — the grid draws the bytes.
    assert entry["url"]


def test_an_entry_carries_its_whole_name_path(api):
    """**`key` is the name path, built from the row's own ancestors.**

    Every other listing knows the folder it is about, so the prefix is in hand.
    A favorites grid has one row per pick from anywhere in the library, and the
    cheap wrong answer is to report the file's name alone — which is what
    `CopyKeyButton` would then put on somebody's clipboard for a `studio`
    command that cannot resolve it.
    """
    _favorite(api, IMAGE)

    assert _grid(api)["entries"][0]["key"] == IMAGE


def test_a_deleted_file_leaves_the_grid_rather_than_breaking_it(api):
    """A dead pointer is skipped on the way out, and the count says so.

    Anybody in the library can delete the node a favorite points at, and the row
    survives it — nothing collects it. What must not survive is a tile the grid
    cannot draw.
    """
    _favorite(api, IMAGE)
    _favorite(api, VIDEO)
    api.delete(f"/api/nodes/{node_id_at(IMAGE)}")

    page = _grid(api)
    assert page["total"] == 1
    assert [entry["id"] for entry in page["entries"]] == [node_id_at(VIDEO)]


def test_the_grid_pages_on_an_offset_cursor(api):
    """The same cursor `GET /api/nodes` uses — `browse.clean_cursor` is shared."""
    _favorite(api, IMAGE)
    _favorite(api, VIDEO)

    first = _grid(api, "?limit=1")
    assert len(first["entries"]) == 1
    assert first["next_cursor"] == "1"

    second = _grid(api, f"?limit=1&cursor={first['next_cursor']}")
    assert len(second["entries"]) == 1
    assert second["next_cursor"] is None
    assert second["entries"][0]["id"] != first["entries"][0]["id"]


def test_the_enumeration_is_capped_and_says_so(api, monkeypatch):
    """`truncated` is about the read, never about the page — `browse`'s word."""
    monkeypatch.setattr(config, "max_folder_objects", lambda: 1)
    _favorite(api, IMAGE)
    _favorite(api, VIDEO)

    page = _grid(api)
    assert page["truncated"] is True
    assert page["total"] == 1


def test_an_unknown_view_is_refused(api):
    assert api.get("/api/favorites?view=everything").status_code == 400


# ───────────────────────────── the guards ─────────────────────────────


def test_a_node_in_another_library_cannot_be_favorited(api, catalog_table):
    """Membership is checked against the NODE's library, which is
    `routes/support`'s rule everywhere: a node id is shareable."""
    catalog_table.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": "NODE#node-elsewhere"},
            "sk": {"S": "META"},
            "node_id": {"S": "node-elsewhere"},
            "lib": {"S": "lib-0002"},
            "name": {"S": "somebody-elses.webp"},
            "kind": {"S": "file"},
            "path": {"S": "/node-other-root/"},
            "blob_key": {"S": "blobs/node-elsewhere"},
            "size": {"N": "8"},
            "created_at": {"S": "2026-08-19T12:00:00.000000+00:00"},
        },
    )

    assert api.post("/api/favorites/node-elsewhere").status_code == 403


def test_favoriting_a_node_that_does_not_exist_is_a_404(api):
    assert api.post("/api/favorites/node-nope").status_code == 404


@pytest.mark.parametrize("method,path", [("get", "/api/favorites"),
                                         ("post", "/api/favorites/node-001"),
                                         ("delete", "/api/favorites/node-001")])
def test_every_route_needs_a_caller(catalog_tree, signed_in, method, path):
    """No unauthenticated path past `before_request`, on this blueprint either."""
    signed_in.authenticated = False
    client = app_factory.create_app().test_client()

    assert getattr(client, method)(path).status_code == 401
