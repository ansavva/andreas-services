"""Admin label endpoints over the three independent taxonomies."""

from flask import Blueprint

from scout_core.repositories import store
from scout_core.routes._shared import bad_request, body, created, ok
from scout_core.services import labels

bp = Blueprint("labels", __name__, url_prefix="/api/admin/labels")

_TAXONOMY = {
    "source": store.SOURCE_LABEL,
    "event": store.EVENT_LABEL,
    "location": store.LOCATION_LABEL,
}


@bp.get("/<taxonomy>")
def list_labels(taxonomy):
    tax = _TAXONOMY.get(taxonomy)
    if tax is None:
        return bad_request(f"unknown label taxonomy: {taxonomy}")
    return ok({"labels": labels.list_labels(tax)})


@bp.post("/<taxonomy>")
def create_label(taxonomy):
    tax = _TAXONOMY.get(taxonomy)
    if tax is None:
        return bad_request(f"unknown label taxonomy: {taxonomy}")
    return created(labels.create_label(tax, body().get("name")))


@bp.put("/<taxonomy>/<label_id>")
def rename_label(taxonomy, label_id):
    tax = _TAXONOMY.get(taxonomy)
    if tax is None:
        return bad_request(f"unknown label taxonomy: {taxonomy}")
    return ok(labels.rename_label(tax, label_id, body().get("name")))


@bp.delete("/<taxonomy>/<label_id>")
def delete_label(taxonomy, label_id):
    tax = _TAXONOMY.get(taxonomy)
    if tax is None:
        return bad_request(f"unknown label taxonomy: {taxonomy}")
    labels.delete_label(tax, label_id)
    return ok({"deleted": label_id})
