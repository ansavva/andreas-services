"""Admin soft-delete views + restore (cross-entity, so kept off the resource
Blueprints)."""

from flask import Blueprint

from scout_core.repositories import store
from scout_core.routes._shared import bad_request, body, not_found, ok
from scout_core.services import deletion

bp = Blueprint("deleted", __name__, url_prefix="/api/admin")

_DELETED_TYPES = {
    "source": store.SOURCE, "event": store.EVENT, "subevent": store.SUBEVENT,
    "location": store.LOCATION, "source_label": store.SOURCE_LABEL,
    "event_label": store.EVENT_LABEL, "location_label": store.LOCATION_LABEL,
}


@bp.get("/deleted/<entity_type>")
def list_deleted(entity_type):
    entity = _DELETED_TYPES.get(entity_type)
    if entity is None:
        return bad_request(f"unknown entity type: {entity_type}")
    return ok({"items": store.query_deleted(entity)})


@bp.post("/restore")
def restore():
    b = body()
    result = deletion.restore(b["pk"], b["sk"])
    return ok(result) if result else not_found("Item not found")
