"""Admin in-app notification endpoints."""

from flask import Blueprint, request

from scout_core.routes._shared import ok
from scout_core.services import notifications

bp = Blueprint("notifications", __name__, url_prefix="/api/admin/notifications")


@bp.get("")
def list_notifications():
    return ok({"notifications": notifications.list_notifications(
        unread_only=request.args.get("unread") == "true")})


@bp.post("/<notification_id>/read")
def mark_read(notification_id):
    return ok(notifications.mark_read(notification_id))
