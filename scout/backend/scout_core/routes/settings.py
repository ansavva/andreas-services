"""Admin settings singleton endpoints."""

from flask import Blueprint

from scout_core.repositories import store
from scout_core.routes._shared import body, ok

bp = Blueprint("settings", __name__, url_prefix="/api/admin/settings")


@bp.get("")
def get_settings():
    return ok(store.get_settings())


@bp.put("")
def update_settings():
    return ok(store.put_settings(body()))
