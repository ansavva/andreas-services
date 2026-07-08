"""Admin event endpoints: review queue, event CRUD, review/publish/decide,
images, and first-class sub-events.

Reviewer identity (``author``) came from the API Gateway Cognito authorizer
claims; those are not propagated through the WSGI request, so it resolves to
None here — matching the prior Flask + Mangum behaviour.
"""

from flask import Blueprint, request

from scout_core.repositories import store
from scout_core.routes._shared import body, created, not_found, ok
from scout_core.services import deletion
from scout_core.services import events
from scout_core.services import images
from scout_core.services import public

bp = Blueprint("events", __name__, url_prefix="/api/admin/events")


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

@bp.get("")
def list_events():
    review = request.args.get("review", events.REVIEW_PENDING)
    limit = int(request.args.get("page_size", "20"))
    start_key = store.decode_cursor(request.args.get("cursor"))
    groups, next_key = events.list_review_groups(review, limit=limit, start_key=start_key)
    return ok({"groups": groups, "next_cursor": store.encode_cursor(next_key)})


@bp.post("/review")
def bulk_review():
    b = body()
    return ok({"updated": len(events.bulk_review(b.get("ids", []), b["status"]))})


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

@bp.get("/<event_id>")
def get_event(event_id):
    detail = events.admin_detail(event_id)
    return ok(detail) if detail else not_found("Event not found")


@bp.get("/<event_id>/preview")
def preview_event(event_id):
    detail = public.preview_detail(event_id)
    return ok(detail) if detail else not_found("Event not found")


@bp.put("/<event_id>")
def update_event(event_id):
    ev = events.update_event(event_id, body())
    return ok(ev) if ev else not_found("Event not found")


@bp.delete("/<event_id>")
def delete_event(event_id):
    result = deletion.delete_event(
        event_id, cascade_subs=request.args.get("cascade", "true") != "false")
    return ok(result) if result else not_found("Event not found")


@bp.post("/<event_id>/review")
def review_event(event_id):
    return ok(events.set_review(event_id, body()["status"]))


@bp.post("/<event_id>/decide")
def decide_event(event_id):
    b = body()
    result = events.review_with_feedback(
        event_id, b["decision"],
        feedback=(b.get("feedback") or "").strip() or None,
        author=b.get("_actor"))
    return ok(result) if result else not_found("Event not found")


@bp.post("/<event_id>/feedback")
def event_feedback(event_id):
    b = body()
    result = events.add_review_feedback(
        event_id, decision=b.get("decision", ""),
        text=b["text"], author=b.get("_actor"))
    return ok(result) if result else not_found("Event not found")


@bp.post("/<event_id>/publish")
def publish_event(event_id):
    return ok(events.set_publish(event_id, body().get("published", True)))


@bp.post("/<event_id>/cancel")
def cancel_event(event_id):
    return ok(events.cancel_event(event_id))


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

@bp.get("/<event_id>/images")
def list_images(event_id):
    result = public.admin_images(event_id)
    return ok(result) if result is not None else not_found("Event not found")


@bp.post("/<event_id>/images")
def add_image(event_id):
    b = body()
    return created(images.add_image(
        store.EVENT, event_id, url=b.get("url"), s3_ref=b.get("s3_ref"),
        source=b.get("source", images.ADMIN)))


@bp.delete("/<event_id>/images/<image_id>")
def delete_image(event_id, image_id):
    images.delete_image(store.EVENT, event_id, image_id)
    return ok({"deleted": image_id})


@bp.post("/<event_id>/images/<image_id>/approve")
def approve_image(event_id, image_id):
    return ok(images.set_image_approved(store.EVENT, event_id, image_id, True))


@bp.post("/<event_id>/images/<image_id>/reject")
def reject_image(event_id, image_id):
    return ok(images.set_image_approved(store.EVENT, event_id, image_id, False))


# ---------------------------------------------------------------------------
# Sub-events
# ---------------------------------------------------------------------------

@bp.post("/<event_id>/subevents")
def create_subevent(event_id):
    b = body()
    return created(events.create_subevent(
        event_id, start_date=b.get("start_date", ""),
        start_time=b.get("start_time"), end_time=b.get("end_time"),
        location_id_override=b.get("location_id_override"),
        event_label_ids=b.get("event_label_ids")))


@bp.put("/<event_id>/subevents/<subevent_id>")
def update_subevent(event_id, subevent_id):
    result = events.update_subevent(event_id, subevent_id, body())
    return ok(result) if result else not_found("Sub-event not found")


@bp.delete("/<event_id>/subevents/<subevent_id>")
def delete_subevent(event_id, subevent_id):
    result = deletion.delete_subevent(event_id, subevent_id)
    return ok(result) if result else not_found("Sub-event not found")


@bp.post("/<event_id>/subevents/<subevent_id>/review")
def review_subevent(event_id, subevent_id):
    return ok(events.set_subevent_review(event_id, subevent_id, body()["status"]))


@bp.post("/<event_id>/subevents/<subevent_id>/publish")
def publish_subevent(event_id, subevent_id):
    return ok(events.set_subevent_publish(event_id, subevent_id, body().get("published", True)))


@bp.post("/<event_id>/subevents/<subevent_id>/cancel")
def cancel_subevent(event_id, subevent_id):
    return ok(events.cancel_subevent(event_id, subevent_id))
