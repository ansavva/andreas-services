"""Model defaults: one person's starting params per model, filed under the person.

The shape is a favorite's, and so are the two ways it could be silently wrong:
a default that a second member of the library can see, and a `DEFAULTS#` row
that `libraries_for` reads as a membership. Both are held up here, beside the
normalisation — three spellings of one model must land on one row, or the
create sheet (which keys on the Replicate id) never finds what was saved.
"""

from studio_core.services import catalog
from tests.conftest import CATALOG_LIBRARY, CATALOG_MEMBER, CATALOG_OWNER

MODEL = "openai/gpt-image-2"
PARAMS = {"quality": "high", "output_format": "jpeg", "output_compression": 90, "moderation": "low"}


def _held(api):
    return api.get("/api/defaults/models").get_json()["defaults"]


def _set(api, name, params):
    return api.post(f"/api/defaults/models/{name}", json={"params": params})


def test_nothing_set_is_an_empty_map(api):
    assert _held(api) == {}


def test_setting_defaults_files_them_under_the_replicate_id(api):
    resp = _set(api, MODEL, PARAMS)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["model"] == MODEL
    assert resp.get_json()["params"] == PARAMS
    assert _held(api) == {MODEL: PARAMS}


def test_the_key_and_the_id_are_one_row(api):
    """The registry key, and the Replicate id: whichever the request said,
    the row is the id's, because that is what the create sheet keys on."""
    _set(api, "gpt-image-2", {"quality": "low"})
    _set(api, MODEL, {"quality": "high"})
    assert _held(api) == {MODEL: {"quality": "high"}}


def test_setting_again_replaces_whole(api):
    _set(api, MODEL, PARAMS)
    _set(api, MODEL, {"quality": "low"})
    assert _held(api) == {MODEL: {"quality": "low"}}


def test_clearing_goes_back_to_the_model_and_is_idempotent(api):
    _set(api, MODEL, PARAMS)
    assert api.delete(f"/api/defaults/models/{MODEL}").status_code == 200
    assert _held(api) == {}
    assert api.delete(f"/api/defaults/models/{MODEL}").get_json() == {"model": MODEL, "cleared": True}


def test_an_unknown_model_has_nothing_to_default(api):
    assert _set(api, "nobody/no-such-model", PARAMS).status_code == 404
    assert api.delete("/api/defaults/models/nobody/no-such-model").status_code == 404


def test_the_wrong_shape_is_refused(api):
    assert _set(api, MODEL, "high").status_code == 400
    assert _set(api, MODEL, {"quality": {"nested": True}}).status_code == 400
    assert _set(api, MODEL, {"quality": ["a"]}).status_code == 400
    # The prompt and the images are sent beside the params, never in them.
    assert _set(api, MODEL, {"prompt": "x"}).status_code == 400
    assert _set(api, MODEL, {"input_images": "x"}).status_code == 400
    assert api.post(f"/api/defaults/models/{MODEL}", json=["quality"]).status_code == 400
    assert _held(api) == {}


def test_two_members_have_their_own_defaults(api, signed_in):
    _set(api, MODEL, PARAMS)

    signed_in.sub = CATALOG_MEMBER
    assert _held(api) == {}
    _set(api, MODEL, {"quality": "low"})

    signed_in.sub = CATALOG_OWNER
    assert _held(api) == {MODEL: PARAMS}


def test_a_default_does_not_read_as_a_membership(api):
    """A `DEFAULTS#` row sits in the partition memberships are read from."""
    _set(api, MODEL, PARAMS)
    assert [row["lib"] for row in catalog.libraries_for(CATALOG_OWNER)] == [CATALOG_LIBRARY]
