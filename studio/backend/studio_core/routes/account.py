"""The signed-in person's name and picture: what the sidebar draws for them.

Humbugg's profile, in studio's shape. Cognito holds the address and the
password, and the SPA reads the address off the ID token; this is the rest of
"who is this" — a display name, and a picture with initials standing in when
there is none. It is filed under the person (`USER#<sub>` / `ACCOUNT`) like a
favorite or a model default, because it is a fact about them and not about any
library, which is also why every path here is in `LIBRARY_UNSCOPED_PATHS`: an
account in two libraries and no header is still one person.

**Nothing is required.** An account with no row answers `{name: null,
avatar_url: null}` and the SPA draws initials off the email. There is no
"complete your profile" step, because there is no sign-up flow that could hold
one — an account here is made by an invite code or an admin — so the name is
something a person adds from the account menu when they feel like it.

**The picture comes in as a data URL and leaves as a JPEG this route wrote.**
Not the presigned-PUT path every other upload takes: that path lands the bytes
the browser sent, verbatim, and a picture that will be drawn beside a person's
name on every screen should be a known size, a known format, and stripped of
whatever a phone wrote into it. `media/imaging.avatar` does that, in the API
image, which carries Pillow for `convert` and `crop` already. Three megabytes
is the cap on what is sent, which is four as base64 — comfortably under the
Lambda's six.

`PATCH` for the name rather than PUT: `app_factory.py` says why PUT is allowed
nowhere. `POST` and `DELETE` for the picture, like a favorite.
"""

import base64
import binascii
import logging
import re

from flask import Blueprint, g, jsonify, request

from studio_core.clients.aws import s3
from studio_core.errors import ValidationError
from studio_core.media import imaging
from studio_core.services import catalog

logger = logging.getLogger(__name__)

bp = Blueprint("account", __name__, url_prefix="/api")

#: The most a picture may be before it is decoded, and the base64 that carries it.
AVATAR_MAX_BYTES = 3 * 1024 * 1024
_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|jpg|webp));base64,(.+)$", re.DOTALL)


def _view(row: dict) -> dict:
    """The row as the SPA reads it: the key is opaque, the URL is what it draws."""
    key = row.get("avatar_key")
    return {
        "name": row.get("name"),
        "avatar_url": s3.presign(key) if key else None,
        "updated_at": row.get("updated_at"),
    }


def _name(body) -> str | None:
    """The name a PATCH may set, or a 400 saying why not. Blank clears it."""
    if not isinstance(body, dict):
        raise ValidationError("a JSON object is required")
    if "name" not in body:
        raise ValidationError("name is required")
    name = body["name"]
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValidationError("name must be a string")
    name = " ".join(name.split())
    if not name:
        return None
    if len(name) > catalog.ACCOUNT_NAME_MAX:
        raise ValidationError(f"name must be {catalog.ACCOUNT_NAME_MAX} characters or fewer")
    return name


def _image(body) -> bytes:
    """The bytes behind a data URL, size-checked before they are decoded."""
    if not isinstance(body, dict) or not isinstance(body.get("image"), str):
        raise ValidationError("image is required, as a data URL")
    match = _DATA_URL.match(body["image"].strip())
    if not match:
        raise ValidationError("upload a PNG, JPEG or WebP image")
    payload = match.group(2)
    # Checked on the encoded length first, so an oversized upload costs a
    # length comparison rather than a decode of four megabytes into memory.
    if len(payload) > AVATAR_MAX_BYTES // 3 * 4 + 4:
        raise ValidationError(f"the image must be {AVATAR_MAX_BYTES // (1024 * 1024)} MB or smaller")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError("the image is not valid base64") from None
    if len(raw) > AVATAR_MAX_BYTES:
        raise ValidationError(f"the image must be {AVATAR_MAX_BYTES // (1024 * 1024)} MB or smaller")
    if not raw:
        raise ValidationError("the image is empty")
    return raw


@bp.get("/account")
def get_account():
    """Who the caller is, as far as this row knows. Empty is a 200."""
    return jsonify(_view(catalog.account(g.caller_sub))), 200


@bp.patch("/account")
def patch_account():
    """Set the display name. `{name: ""}` or `{name: null}` clears it."""
    name = _name(request.get_json(silent=True))
    return jsonify(_view(catalog.set_account_name(g.caller_sub, name))), 200


@bp.post("/account/avatar")
def upload_avatar():
    """Replace the picture. The previous object goes best-effort, after the row moved."""
    raw = _image(request.get_json(silent=True))
    encoded = imaging.avatar(raw)
    previous = catalog.account(g.caller_sub).get("avatar_key")
    key = catalog.avatar_key_for(g.caller_sub)
    s3.put_text(key, encoded, "image/jpeg")
    row = catalog.set_account_avatar(g.caller_sub, key)
    _discard(previous, keep=key)
    return jsonify(_view(row)), 200


@bp.delete("/account/avatar")
def remove_avatar():
    """Back to initials. Removing what was never there is 200 too."""
    previous = catalog.account(g.caller_sub).get("avatar_key")
    row = catalog.set_account_avatar(g.caller_sub, None)
    _discard(previous, keep=None)
    return jsonify(_view(row)), 200


def _discard(key: str | None, *, keep: str | None) -> None:
    """Delete the picture the row no longer points at. A failure is logged, not raised.

    The row has already moved, so the person is consistent whatever happens
    here; what a failure leaves behind is one orphaned object, which is not
    worth failing their upload over.
    """
    if not key or key == keep:
        return
    try:
        s3.delete([key])
    except Exception as exc:  # noqa: BLE001 — best-effort, by design
        logger.warning("Could not discard the previous picture %s: %s", key, exc)
