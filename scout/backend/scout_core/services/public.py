"""
Public read/query layer.

The single source of truth for what end users see, shared by every public UI
endpoint. An event/sub-event is visible iff it is published, not cancelled, not
deleted, and within the past-event grace period; a sub-event additionally needs
its parent published (enforced by PUBVIS index membership). A parent with
sub-events but none currently visible still appears, with no_upcoming_dates set.

Filtering is AND-only: the (optional) location must match, and every selected
event-label and location-label must be present (inherited location-labels are
honored). Search matches event title, description, or location name. Results are
app-paginated with an opaque cursor. Public serialization never exposes source
attribution or run references.
"""

import base64
from datetime import datetime, timezone

from scout_core.services import events
from scout_core.services import images
from scout_core.services import labels
from scout_core.services import locations
from scout_core.repositories import store
from scout_core import config
from scout_core.utils import timeutil

_PUBVIS = "PUBVIS"
MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 20

SORT_DATE = "date"
SORT_RECENT = "recent"


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

def _in_grace(item, grace_hours, now):
    return not timeutil.is_past(item.get("effective_end_utc"), grace_hours, now)


def _visible_events(now, settings):
    """Visible parent events paired with their currently-visible sub-events.

    Returns a list of (event_item, [visible_sub_items]). A parent is included if
    it is itself in-grace, or if it has at least one in-grace sub-event."""
    grace = settings["past_grace_hours"]
    rows = store.query_index_all("GSI1", _PUBVIS, live_only=True)

    events_in_grace = {}
    subs_by_parent = {}
    for row in rows:
        if not _in_grace(row, grace, now):
            continue
        if row.get("entity_type") == store.EVENT:
            events_in_grace[row["event_id"]] = row
        elif row.get("entity_type") == store.SUBEVENT:
            subs_by_parent.setdefault(row["parent_event_id"], []).append(row)

    visible = dict(events_in_grace)
    for parent_id in subs_by_parent:
        if parent_id in visible:
            continue
        parent = events.get_event(parent_id)
        if (parent and not parent.get("deleted_at")
                and parent.get("publish_status") == events.PUBLISHED
                and not parent.get("lifecycle_cancelled")):
            visible[parent_id] = parent

    result = []
    for event_id, event in visible.items():
        subs = sorted(subs_by_parent.get(event_id, []),
                      key=lambda s: s.get("start_date") or "")
        result.append((event, subs))
    return result


# ---------------------------------------------------------------------------
# Filtering & search (AND-only)
# ---------------------------------------------------------------------------

def _matches_filters(event, *, location_id, event_label_ids, location_label_ids):
    if location_id and events.effective_location_id(event) != location_id:
        return False
    if event_label_ids:
        owned = set(events.effective_event_label_ids(event))
        if not set(event_label_ids).issubset(owned):
            return False
    if location_label_ids:
        owned = set(events.effective_location_label_ids(event))
        if not set(location_label_ids).issubset(owned):
            return False
    return True


def _matches_search(event, query):
    query = query.lower()
    if query in (event.get("title") or "").lower():
        return True
    if query in (event.get("description_md") or "").lower():
        return True
    location_id = event.get("location_id")
    if location_id:
        location = locations.get_location(location_id)
        if location and query in (location.get("name") or "").lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Serialization (source attribution intentionally omitted)
# ---------------------------------------------------------------------------

def _serialize_location(location_id):
    if not location_id:
        return None
    location = locations.get_location(location_id)
    if not location:
        return None
    return {"name": location.get("name", ""), "address": location.get("address", "")}


def _serialize_labels(taxonomy, label_ids):
    out = []
    for label in labels.resolve_labels(taxonomy, label_ids):
        out.append({"id": label["label_id"], "name": label["name"]})
    return out


def _serialize_images(owner_type, owner_id, *, parent_event_id=None,
                      approved_only=True):
    """Serialize each image to its public-route URL. Every image we keep has
    an `s3_ref`; the route streams the bytes from our private bucket under
    our own domain, so the client only ever sees our-domain URLs."""
    base = config.public_api_base()
    return [
        {"url": f"{base}/public/images/{image['image_id']}"}
        for image in images.list_images(
            owner_type, owner_id, parent_event_id=parent_event_id,
            approved_only=approved_only,
        )
    ]


def _serialize_admin_image(image):
    """Admin-console shape: enough to render a thumbnail and act on it. The
    bytes route (`/public/images/<id>`) streams regardless of approval, so the
    same url previews unapproved images too."""
    base = config.public_api_base()
    return {
        "image_id": image["image_id"],
        "url": f"{base}/public/images/{image['image_id']}",
        "approved": bool(image.get("approved")),
        "source": image.get("source"),
    }


def admin_images(event_id):
    """Every live image attached to an event, in admin shape, so the review UI
    can curate which ones go public. Agent extraction only ever attaches images
    at the event level, so event-scoped listing covers them all. Returns None
    for a missing or deleted event."""
    event = events.get_event(event_id)
    if event is None or event.get("deleted_at"):
        return None
    return {"images": [_serialize_admin_image(i)
                       for i in images.list_images(store.EVENT, event_id)]}


def _serialize_sub(sub, parent, *, approved_only=True):
    return {
        "subevent_id": sub["subevent_id"],
        "start_date": sub.get("start_date", ""),
        "start_time": sub.get("start_time"),
        "end_time": sub.get("end_time"),
        "location": _serialize_location(events.effective_location_id(parent, sub)),
        "event_labels": _serialize_labels(
            store.EVENT_LABEL, events.effective_event_label_ids(parent, sub)),
        "location_labels": _serialize_labels(
            store.LOCATION_LABEL, events.effective_location_label_ids(parent, sub)),
        "images": _serialize_images(store.SUBEVENT, sub["subevent_id"],
                                    parent_event_id=parent["event_id"],
                                    approved_only=approved_only),
    }


def _serialize_event(event, visible_subs, *, approved_only=True):
    return {
        "event_id": event["event_id"],
        "title": event.get("title", ""),
        "description": event.get("description_md", ""),
        "start_date": event.get("start_date", ""),
        "start_time": event.get("start_time"),
        "end_time": event.get("end_time"),
        "location": _serialize_location(events.effective_location_id(event)),
        "event_labels": _serialize_labels(
            store.EVENT_LABEL, events.effective_event_label_ids(event)),
        "location_labels": _serialize_labels(
            store.LOCATION_LABEL, events.effective_location_label_ids(event)),
        "images": _serialize_images(store.EVENT, event["event_id"],
                                    approved_only=approved_only),
        "sub_events": [_serialize_sub(s, event, approved_only=approved_only)
                       for s in visible_subs],
    }


# ---------------------------------------------------------------------------
# Cursor pagination
# ---------------------------------------------------------------------------

def _encode_cursor(offset):
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_cursor(cursor):
    if not cursor:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cursor.encode()).decode()))
    except (ValueError, TypeError):
        return 0


def _sort(pairs, sort):
    if sort == SORT_RECENT:
        pairs.sort(key=lambda p: p[0].get("created_at", ""), reverse=True)
    else:
        pairs.sort(key=lambda p: (p[0].get("start_date") or "9999-99-99",
                                  p[0].get("title", "")))
    return pairs


# ---------------------------------------------------------------------------
# Public API surface (consumed by the UI's backend endpoints)
# ---------------------------------------------------------------------------

def feed(*, location_id=None, event_label_ids=None, location_label_ids=None,
         search=None, sort=SORT_DATE, cursor=None, page_size=DEFAULT_PAGE_SIZE,
         now=None, settings=None):
    """Paginated feed of visible events (parents only; sub-events are nested)."""
    now = now or datetime.now(timezone.utc)
    settings = settings or store.get_settings()
    page_size = min(max(1, int(page_size)), MAX_PAGE_SIZE)

    pairs = _visible_events(now, settings)
    pairs = [(e, s) for (e, s) in pairs
             if _matches_filters(e, location_id=location_id,
                                 event_label_ids=event_label_ids,
                                 location_label_ids=location_label_ids)]
    if search:
        pairs = [(e, s) for (e, s) in pairs if _matches_search(e, search)]
    _sort(pairs, sort)

    offset = _decode_cursor(cursor)
    window = pairs[offset:offset + page_size]
    serialized = [_serialize_event(e, s) for (e, s) in window]
    next_cursor = (_encode_cursor(offset + page_size)
                   if offset + page_size < len(pairs) else None)
    return {"events": serialized, "next_cursor": next_cursor, "total": len(pairs)}


def event_detail(event_id, *, now=None, settings=None):
    """A single visible event with its currently-visible sub-events, or None.
    A parent with sub-events but none visible is returned with
    no_upcoming_dates=True."""
    now = now or datetime.now(timezone.utc)
    settings = settings or store.get_settings()
    grace = settings["past_grace_hours"]

    event = events.get_event(event_id)
    if (event is None or event.get("deleted_at")
            or event.get("publish_status") != events.PUBLISHED
            or event.get("lifecycle_cancelled")):
        return None

    all_subs = events.list_subevents(event_id)
    visible_subs = sorted(
        [s for s in all_subs
         if s.get("publish_status") == events.PUBLISHED
         and not s.get("lifecycle_cancelled")
         and _in_grace(s, grace, now)],
        key=lambda s: s.get("start_date") or "")

    if not _in_grace(event, grace, now) and not visible_subs:
        return None

    data = _serialize_event(event, visible_subs)
    data["no_upcoming_dates"] = bool(all_subs) and not visible_subs
    return data


def preview_detail(event_id):
    """Admin preview of an event in the public-detail shape, ignoring publish
    and grace visibility so a pending/unpublished event renders exactly as its
    public page would. Includes every non-deleted sub-event (date-sorted) and
    every non-deleted image (approved or not) — admins are previewing what's
    about to be published, so unapproved agent images belong in the view.
    Returns None only for a missing or deleted event."""
    event = events.get_event(event_id)
    if event is None or event.get("deleted_at"):
        return None
    subs = sorted(events.list_subevents(event_id),
                  key=lambda s: s.get("start_date") or "")
    data = _serialize_event(event, subs, approved_only=False)
    data["no_upcoming_dates"] = False
    return data


def facets(*, now=None, settings=None):
    """Filter options derived from the currently-visible feed: the locations,
    event-labels and location-labels that appear on visible events."""
    now = now or datetime.now(timezone.utc)
    settings = settings or store.get_settings()

    location_ids, event_label_ids, location_label_ids = set(), set(), set()
    for event, _subs in _visible_events(now, settings):
        loc = events.effective_location_id(event)
        if loc:
            location_ids.add(loc)
        event_label_ids.update(events.effective_event_label_ids(event))
        location_label_ids.update(events.effective_location_label_ids(event))

    return {
        "locations": [
            {"id": lid, **(_serialize_location(lid) or {})}
            for lid in location_ids if _serialize_location(lid)
        ],
        "event_labels": _serialize_labels(store.EVENT_LABEL, list(event_label_ids)),
        "location_labels": _serialize_labels(store.LOCATION_LABEL,
                                             list(location_label_ids)),
    }
