"""Public read endpoints (no auth): the event feed, detail, facets, images."""

from flask import Blueprint, request

from scout_core.repositories import image_store
from scout_core.routes._shared import binary, csv_param, not_found, ok
from scout_core.services import public

bp = Blueprint("public", __name__, url_prefix="/api/public")


@bp.get("/events")
def feed():
    page = public.feed(
        location_id=request.args.get("location_id"),
        event_label_ids=csv_param("event_labels"),
        location_label_ids=csv_param("location_labels"),
        search=request.args.get("q"),
        sort=request.args.get("sort", public.SORT_DATE),
        cursor=request.args.get("cursor"),
        page_size=int(request.args.get("page_size", public.DEFAULT_PAGE_SIZE)),
    )
    return ok(page)


@bp.get("/events/<event_id>")
def event_detail(event_id):
    detail = public.event_detail(event_id)
    return ok(detail) if detail else not_found("Event not found")


@bp.get("/facets")
def facets():
    return ok(public.facets())


@bp.get("/images/<image_id>")
def image(image_id):
    data, content_type = image_store.get_bytes(image_id)
    if data is None:
        return not_found("Image not found")
    return binary(data, content_type)
