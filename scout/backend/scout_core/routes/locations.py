"""Admin location endpoints: CRUD, fuzzy match, and merge."""

from flask import Blueprint, request

from scout_core.routes._shared import body, created, not_found, ok
from scout_core.services import deletion
from scout_core.services import locations

bp = Blueprint("locations", __name__, url_prefix="/api/admin/locations")


@bp.get("")
def list_locations():
    return ok({"locations": locations.list_locations()})


@bp.post("")
def create_location():
    b = body()
    return created(locations.create_location(
        b.get("name"), address=b.get("address", ""),
        timezone=b.get("timezone", "UTC")))


@bp.post("/merge")
def merge_locations():
    b = body()
    return ok(locations.merge_locations(b["target_id"], b.get("source_ids", [])))


@bp.get("/match")
def match_locations():
    return ok({"matches": locations.fuzzy_match(request.args.get("name", ""))})


@bp.get("/<location_id>")
def get_location(location_id):
    loc = locations.get_location(location_id)
    return ok(loc) if loc else not_found("Location not found")


@bp.put("/<location_id>")
def update_location(location_id):
    return ok(locations.update_location(location_id, body()))


@bp.delete("/<location_id>")
def delete_location(location_id):
    result = deletion.delete_location(
        location_id, cascade_events=request.args.get("cascade", "true") != "false")
    return ok(result) if result else not_found("Location not found")
