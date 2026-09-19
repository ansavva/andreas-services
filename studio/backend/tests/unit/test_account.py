"""The account: one person's name and picture, filed under the person.

The shape is a favorite's, and so are the two ways it could be silently wrong:
a name that a second member of the library can read as their own, and an
`ACCOUNT` row that `libraries_for` reads as a membership. Both are held up
here. The picture's half is what the route promised: whatever came in, what
lands in the bucket is a square JPEG with no metadata, and the previous one is
gone once the row has moved on.
"""

import base64
import io

from PIL import Image

from studio_core.clients.aws import s3
from studio_core.media import imaging
from tests.conftest import CATALOG_MEMBER


def _png(width: int, height: int, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (width, height), (200, 30, 30) if mode == "RGB" else (200, 30, 30, 128)).save(buf, "PNG")
    return buf.getvalue()


def _data_url(body: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(body).decode()}"


def _account(api):
    return api.get("/api/account").get_json()


def _upload(api, body: bytes, mime: str = "image/png"):
    return api.post("/api/account/avatar", json={"image": _data_url(body, mime)})


def _stored_key(api) -> str:
    """The key behind the URL, read off the presigned URL's path.

    moto signs path-style, so the path is `/<bucket>/<key>`; the key is
    everything from `accounts/` on, which is where every one of them starts.
    """
    from urllib.parse import urlparse

    path = urlparse(_account(api)["avatar_url"]).path
    return path[path.index("accounts/"):]


def test_nothing_set_is_an_empty_account(api):
    assert _account(api) == {"name": None, "avatar_url": None, "updated_at": None}


def test_the_name_is_set_trimmed_and_read_back(api):
    resp = api.patch("/api/account", json={"name": "  Ada   Lovelace "})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["name"] == "Ada Lovelace"
    assert _account(api)["name"] == "Ada Lovelace"
    assert _account(api)["updated_at"]


def test_a_blank_name_clears_it(api):
    api.patch("/api/account", json={"name": "Ada"})
    assert api.patch("/api/account", json={"name": "   "}).get_json()["name"] is None
    api.patch("/api/account", json={"name": "Ada"})
    assert api.patch("/api/account", json={"name": None}).get_json()["name"] is None


def test_the_wrong_shape_of_name_is_refused(api):
    assert api.patch("/api/account", json={}).status_code == 400
    assert api.patch("/api/account", json={"name": 3}).status_code == 400
    assert api.patch("/api/account", json={"name": "x" * 101}).status_code == 400
    assert api.patch("/api/account", json=["Ada"]).status_code == 400
    assert _account(api)["name"] is None


def test_a_picture_lands_as_a_square_jpeg_under_the_person(api, signed_in):
    resp = _upload(api, _png(300, 120))
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["avatar_url"]

    key = _stored_key(api)
    assert key.startswith(f"accounts/{signed_in.sub}/")
    assert key.endswith(".jpg")
    stored = Image.open(io.BytesIO(s3.get_body(key, 10 * 1024 * 1024)))
    assert stored.format == "JPEG"
    assert stored.size == (imaging.AVATAR_SIZE, imaging.AVATAR_SIZE)
    assert s3.head(key)["ContentType"] == "image/jpeg"


def test_a_transparent_png_and_a_webp_both_become_a_jpeg(api):
    assert _upload(api, _png(64, 64, "RGBA")).status_code == 200
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (0, 0, 200)).save(buf, "WEBP")
    assert _upload(api, buf.getvalue(), "image/webp").status_code == 200
    assert _stored_key(api).endswith(".jpg")


def test_replacing_the_picture_discards_the_previous_object(api):
    _upload(api, _png(64, 64))
    first = _stored_key(api)
    _upload(api, _png(64, 64))
    second = _stored_key(api)
    assert first != second
    assert s3.head(second)
    try:
        s3.head(first)
    except Exception:
        pass
    else:
        raise AssertionError("the previous picture is still in the bucket")


def test_removing_the_picture_goes_back_to_initials_and_is_idempotent(api):
    _upload(api, _png(64, 64))
    key = _stored_key(api)
    assert api.delete("/api/account/avatar").get_json()["avatar_url"] is None
    assert _account(api)["avatar_url"] is None
    try:
        s3.head(key)
    except Exception:
        pass
    else:
        raise AssertionError("the removed picture is still in the bucket")
    assert api.delete("/api/account/avatar").status_code == 200


def test_the_name_survives_the_picture_and_the_picture_the_name(api):
    api.patch("/api/account", json={"name": "Ada"})
    _upload(api, _png(64, 64))
    assert _account(api)["name"] == "Ada"
    api.patch("/api/account", json={"name": "Ada L"})
    assert _account(api)["avatar_url"]
    api.delete("/api/account/avatar")
    assert _account(api)["name"] == "Ada L"


def test_what_is_not_a_picture_is_refused(api):
    assert api.post("/api/account/avatar", json={}).status_code == 400
    assert api.post("/api/account/avatar", json={"image": "not a data url"}).status_code == 400
    assert api.post("/api/account/avatar", json={"image": "data:image/png;base64,!!!"}).status_code == 400
    assert api.post("/api/account/avatar", json={"image": "data:image/png;base64,"}).status_code == 400
    # The declared type is not trusted: these bytes are text, whatever the prefix says.
    assert _upload(api, b"hello there", "image/png").status_code == 400
    # A GIF is an image Pillow reads and not one a picture may be.
    buf = io.BytesIO()
    Image.new("P", (8, 8)).save(buf, "GIF")
    assert api.post("/api/account/avatar", json={"image": _data_url(buf.getvalue(), "image/png")}).status_code == 400
    assert _account(api)["avatar_url"] is None


def test_too_large_is_refused_before_it_is_decoded(api, monkeypatch):
    from studio_core.media import imaging as module

    monkeypatch.setattr(module, "avatar", lambda body: (_ for _ in ()).throw(AssertionError("decoded")))
    oversized = b"x" * (3 * 1024 * 1024 + 1)
    assert _upload(api, oversized).status_code == 400


def test_two_members_have_their_own_account(api, signed_in):
    api.patch("/api/account", json={"name": "Owner"})
    _upload(api, _png(64, 64))

    signed_in.sub = CATALOG_MEMBER
    assert _account(api) == {"name": None, "avatar_url": None, "updated_at": None}
    api.patch("/api/account", json={"name": "Member"})
    assert _account(api)["name"] == "Member"

    # The account row is filed under `USER#`, beside the memberships — and is
    # not one. Both libraries lists are unchanged.
    assert [lib["id"] for lib in api.get("/api/libraries").get_json()]


def test_the_account_is_answered_without_a_library(api, signed_in):
    """A caller in no library at all still has a name. The gate draws it."""
    signed_in.sub = "sub-nobody"
    assert api.get("/api/account").status_code == 200
    assert api.patch("/api/account", json={"name": "Nobody"}).status_code == 200
    assert _upload(api, _png(64, 64)).status_code == 200
    assert api.delete("/api/account/avatar").status_code == 200
