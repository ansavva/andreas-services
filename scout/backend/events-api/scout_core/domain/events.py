"""
Event and sub-event service layer.

Events (PK=EVT#<id>, SK=META) and their first-class sub-events
(PK=EVT#<parent_id>, SK=SUB#<date>#<sub_id>) carry independent status
dimensions as separate fields: review_status, publish_status, the admin-set
lifecycle_cancelled flag, and a materialized `past` boolean (refreshed by the
sweep from the stable effective_end_utc instant).

Indexes maintained here:
- GSI1 PUBVIS  — published, not cancelled, not deleted (and, for a sub, parent
  published); keyed by effective_end_utc so the public layer range-queries
  "in grace" and the public/dedup paths shed deleted items automatically.
- GSI3 DUP#<key> — live dedup lookup for re-extraction.
- GSI4 REVIEW#<status> — the admin review queue (newest-first).

Inheritance (location, event-labels, location-labels) is computed at query time;
a sub-event's overrides short-circuit it. Conversion from agent extraction
applies fuzzy location matching and the duplicate-detection rules.
"""

from datetime import datetime, timezone

from scout_core.domain import images
from scout_core.domain import labels
from scout_core.domain import locations
from scout_core.adapters import image_store
from scout_core.adapters import store
from scout_core.common import taxonomy
from scout_core.common import timeutil

REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_STATUSES = (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)

PUBLISHED = "published"
UNPUBLISHED = "unpublished"

_PUBVIS = "PUBVIS"
_FAR_FUTURE = "9999-12-31T23:59:59+00:00"


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------

def _pubvis_sk(effective_end, sk):
    return f"{effective_end or _FAR_FUTURE}#{sk}"


def _set_pubvis(pk, sk, effective_end):
    store.set_attrs(pk, sk, {"GSI1PK": _PUBVIS, "GSI1SK": _pubvis_sk(effective_end, sk)})


def _clear_pubvis(pk, sk):
    store.remove_attrs(pk, sk, ["GSI1PK", "GSI1SK"])


def _set_review_index(pk, sk, review_status, created_at):
    store.set_attrs(pk, sk, {"GSI4PK": f"REVIEW#{review_status}", "GSI4SK": created_at})


def _event_qualifies_pubvis(event):
    return (event.get("publish_status") == PUBLISHED
            and not event.get("lifecycle_cancelled")
            and not event.get("deleted_at"))


def _sub_qualifies_pubvis(sub, parent):
    return (sub.get("publish_status") == PUBLISHED
            and not sub.get("lifecycle_cancelled")
            and not sub.get("deleted_at")
            and parent is not None
            and parent.get("publish_status") == PUBLISHED
            and not parent.get("deleted_at"))


def _event_timezone(location_id, settings):
    if location_id:
        loc = locations.get_location(location_id)
        if loc and loc.get("timezone"):
            return loc["timezone"]
    return settings["fallback_timezone"]


def _sync_event_labels(target_type, target_id, desired_ids):
    """Reconcile an entity's event-label edges to exactly ``desired_ids``:
    detach removed labels, attach added ones (idempotent)."""
    current = set(labels.label_ids_of(target_type, target_id, store.EVENT_LABEL))
    desired = set(desired_ids)
    for label_id in current - desired:
        labels.detach_label(store.EVENT_LABEL, label_id, target_type, target_id)
    for label_id in desired - current:
        labels.attach_label(store.EVENT_LABEL, label_id, target_type, target_id)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def create_event(source_id, *, title, start_date, description="", start_time=None,
                 end_time=None, location_id=None, event_label_ids=None,
                 event_url=None,
                 review_status=REVIEW_PENDING, publish_status=UNPUBLISHED,
                 cancelled=False, auto_cancel_parent=False, auto_past_parent=True,
                 settings=None):
    settings = settings or store.get_settings()
    title = (title or "").strip()
    if not title:
        raise ValueError("event title is required")

    event_id = store.new_id()
    pk = store.event_pk(event_id)
    created = store.now_iso()
    tz = _event_timezone(location_id, settings)
    effective_end = timeutil.effective_end_utc(
        start_date, start_time, end_time, tz=tz, fallback_tz=settings["fallback_timezone"])
    dup = taxonomy.dup_key(title, start_date, location_id)

    item = store.base_item(
        pk, "META", store.EVENT,
        event_id=event_id, source_id=source_id,
        title=title, title_norm=taxonomy.normalize_title(title),
        description_md=description or "",
        event_url=event_url or "",
        start_date=start_date or "", start_time=start_time, end_time=end_time,
        location_id=location_id,
        review_status=review_status, publish_status=publish_status,
        lifecycle_cancelled=bool(cancelled),
        past=timeutil.is_past(effective_end, settings["past_grace_hours"]),
        effective_end_utc=effective_end, dup_key=dup, edited=False,
        auto_cancel_parent_on_all_subs_cancelled=bool(auto_cancel_parent),
        auto_past_parent_on_all_subs_past=bool(auto_past_parent),
        created_at=created,
        GSI3PK=f"DUP#{dup}", GSI3SK=f"EVT#{event_id}",
        GSI4PK=f"REVIEW#{review_status}", GSI4SK=created,
    )
    store.put(item)
    if location_id:
        locations.link_event_to_location(location_id, store.EVENT, event_id)
    for label_id in event_label_ids or []:
        labels.attach_label(store.EVENT_LABEL, label_id, store.EVENT, event_id)
    if _event_qualifies_pubvis(item):
        _set_pubvis(pk, "META", effective_end)
    return store.get(pk, "META")


def get_event(event_id):
    return store.get(store.event_pk(event_id), "META")


def admin_detail(event_id):
    """Event + its sub-events, each enriched with its own attached event-label
    ids. The stored rows don't carry label ids (labels live as separate edges),
    but the admin editor needs them to seed the label picker. Returns
    {"event", "subevents"} or None when the event is missing."""
    event = get_event(event_id)
    if event is None:
        return None
    event = {**event,
             "event_label_ids": labels.label_ids_of(store.EVENT, event_id, store.EVENT_LABEL)}
    subs = [{**s, "event_label_ids": labels.label_ids_of(
                store.SUBEVENT, s["subevent_id"], store.EVENT_LABEL)}
            for s in list_subevents(event_id)]
    return {"event": event, "subevents": subs}


def list_by_review(review_status, *, include_subevents=True):
    """Admin review queue for a status, newest-first (events and, by default,
    sub-events together — the flat pending-review queue)."""
    items = store.query_index_all("GSI4", f"REVIEW#{review_status}", ascending=False)
    if not include_subevents:
        items = [i for i in items if i.get("entity_type") == store.EVENT]
    return items


def list_by_review_page(review_status, *, include_subevents=True,
                        limit=None, start_key=None):
    """Cursor-paginated admin review queue. Returns (items, next_key)."""
    items, next_key = store.query_index_page(
        "GSI4", f"REVIEW#{review_status}", ascending=False,
        limit=limit, start_key=start_key,
    )
    if not include_subevents:
        items = [i for i in items if i.get("entity_type") == store.EVENT]
    return items, next_key


def list_review_groups(review_status, *, limit=None, start_key=None):
    """Parent-centric admin review queue, newest-first. Returns (groups, next_key).

    A parent event is surfaced when its own ``review_status`` matches OR any of
    its sub-events do; a surfaced parent always carries *all* its sub-events (each
    keeping its own status) so occurrences are shown in context, never as
    standalone rows. Each group is::

        {"event": <parent>, "parent_matches": bool, "subevents": [<all subs>]}

    ``parent_matches`` is False when the parent appears only because of its
    occurrences (its own state differs from the tab) — the client renders such a
    parent as a muted, non-actionable container. ``parent_matches`` is computed
    from the parent's own status, so it's stable no matter which row introduced
    the group; a parent split across pages re-emits the same group, which the
    client merges by ``event_id``.
    """
    rows, next_key = store.query_index_page(
        "GSI4", f"REVIEW#{review_status}", ascending=False,
        limit=limit, start_key=start_key,
    )
    groups = []
    seen = set()
    for row in rows:
        parent_id = (row["event_id"] if row.get("entity_type") == store.EVENT
                     else row.get("parent_event_id"))
        if not parent_id or parent_id in seen:
            continue
        seen.add(parent_id)
        parent = get_event(parent_id)
        if parent is None:
            continue
        groups.append({
            "event": parent,
            "parent_matches": parent.get("review_status") == review_status,
            "subevents": list_subevents(parent_id),
        })
    return groups, next_key


def update_event(event_id, fields):
    """Edit an event (marks it edited, which dedup honors) and reindex."""
    pk = store.event_pk(event_id)
    event = store.get(pk, "META")
    if event is None:
        return None
    settings = store.get_settings()

    updates = {"updated_at": store.now_iso(), "edited": True}
    for key, attr in (("title", "title"), ("description", "description_md"),
                      ("start_date", "start_date"), ("start_time", "start_time"),
                      ("end_time", "end_time")):
        if key in fields:
            updates[attr] = fields[key]
    new_location = fields.get("location_id", event.get("location_id")) \
        if "location_id" in fields else event.get("location_id")

    if "location_id" in fields and fields["location_id"] != event.get("location_id"):
        if event.get("location_id"):
            locations.unlink_event_from_location(event["location_id"], store.EVENT, event_id)
        if fields["location_id"]:
            locations.link_event_to_location(fields["location_id"], store.EVENT, event_id)
        updates["location_id"] = fields["location_id"]

    if "event_label_ids" in fields:
        _sync_event_labels(store.EVENT, event_id, fields["event_label_ids"] or [])

    merged = dict(event)
    merged.update(updates)
    if "title" in updates:
        updates["title_norm"] = taxonomy.normalize_title(updates["title"])
    tz = _event_timezone(new_location, settings)
    effective_end = timeutil.effective_end_utc(
        merged.get("start_date"), merged.get("start_time"), merged.get("end_time"),
        tz=tz, fallback_tz=settings["fallback_timezone"])
    dup = taxonomy.dup_key(merged.get("title", ""), merged.get("start_date"), new_location)
    updates.update({
        "effective_end_utc": effective_end,
        "past": timeutil.is_past(effective_end, settings["past_grace_hours"]),
        "dup_key": dup,
        "GSI3PK": f"DUP#{dup}", "GSI3SK": f"EVT#{event_id}",
    })
    store.set_attrs(pk, "META", updates)

    refreshed = store.get(pk, "META")
    if _event_qualifies_pubvis(refreshed):
        _set_pubvis(pk, "META", effective_end)
    else:
        _clear_pubvis(pk, "META")
    return refreshed


def set_review(event_id, review_status):
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"invalid review status: {review_status!r}")
    pk = store.event_pk(event_id)
    event = store.get(pk, "META")
    if event is None:
        return None
    store.set_attrs(pk, "META", {
        "review_status": review_status,
        "GSI4PK": f"REVIEW#{review_status}",
    })
    return store.get(pk, "META")


def bulk_review(event_ids, review_status):
    return [set_review(eid, review_status) for eid in event_ids]


def add_review_feedback(event_id, *, decision, text, author=None):
    """Append a reviewer's note to an event's append-only feedback history.

    Each entry records when it was left, the decision it accompanied, the note
    text and (optionally) who left it — an internal admin trail, never exposed
    on the public/preview shapes. Returns the refreshed event, or None."""
    pk = store.event_pk(event_id)
    if store.get(pk, "META") is None:
        return None
    entry = {"at": store.now_iso(), "decision": decision, "text": text}
    if author:
        entry["author"] = author
    store.append_to_list(pk, "META", "review_feedback", entry)
    return store.get(pk, "META")


def review_with_feedback(event_id, decision, *, feedback=None, author=None):
    """Apply an admin swipe decision to an event and all its occurrences.

    Approve -> review_status=approved and publish the event + every occurrence.
    Reject  -> review_status=rejected and unpublish the event + every occurrence
    (so a rejected event never lingers public). The decision is mirrored onto
    every sub-event so occurrences match their parent. An optional feedback note
    is appended to the event's review history. Returns {"event", "subevents"}
    with the refreshed records, or None when the event is missing."""
    if decision not in (REVIEW_APPROVED, REVIEW_REJECTED):
        raise ValueError(f"invalid decision: {decision!r}")
    pk = store.event_pk(event_id)
    if store.get(pk, "META") is None:
        return None

    publish = decision == REVIEW_APPROVED
    subs = list_subevents(event_id)

    # Review status on the parent and every occurrence.
    set_review(event_id, decision)
    for sub in subs:
        set_subevent_review(event_id, sub["subevent_id"], decision)

    # Publish state: the parent first (a sub can't be published while its parent
    # is unpublished), then cascade the same change to every occurrence.
    set_publish(event_id, publish)
    for sub in subs:
        set_subevent_publish(event_id, sub["subevent_id"], publish)

    if feedback:
        add_review_feedback(event_id, decision=decision, text=feedback, author=author)

    return {"event": store.get(pk, "META"), "subevents": list_subevents(event_id)}


def set_publish(event_id, published):
    """Publish/unpublish an event, cascading the visibility change to its
    sub-events (a sub can't be visible while its parent is unpublished)."""
    pk = store.event_pk(event_id)
    event = store.get(pk, "META")
    if event is None:
        return None
    status = PUBLISHED if published else UNPUBLISHED
    store.set_attrs(pk, "META", {"publish_status": status})
    event["publish_status"] = status
    if _event_qualifies_pubvis(event):
        _set_pubvis(pk, "META", event.get("effective_end_utc"))
    else:
        _clear_pubvis(pk, "META")
    for sub in list_subevents(event_id):
        _reindex_sub_pubvis(sub, event)
    return store.get(pk, "META")


def cancel_event(event_id):
    """Cancel an event and cascade cancellation to all its sub-events."""
    pk = store.event_pk(event_id)
    if store.get(pk, "META") is None:
        return None
    store.set_attrs(pk, "META", {"lifecycle_cancelled": True})
    _clear_pubvis(pk, "META")
    for sub in list_subevents(event_id):
        store.set_attrs(pk, sub["SK"], {"lifecycle_cancelled": True})
        _clear_pubvis(pk, sub["SK"])
    return store.get(pk, "META")


def restore_event(event_id):
    """Restore a soft-deleted event, re-establishing its review/dedup indexes and
    public visibility if it still qualifies."""
    pk = store.event_pk(event_id)
    if store.get(pk, "META") is None:
        return None
    store.restore(pk, "META")
    event = store.get(pk, "META")
    store.set_attrs(pk, "META", {
        "GSI4PK": f"REVIEW#{event['review_status']}", "GSI4SK": event["created_at"],
        "GSI3PK": f"DUP#{event['dup_key']}", "GSI3SK": f"EVT#{event_id}",
    })
    if _event_qualifies_pubvis(event):
        _set_pubvis(pk, "META", event.get("effective_end_utc"))
    return store.get(pk, "META")


def restore_subevent(parent_event_id, sub_id):
    sub = _get_sub(parent_event_id, sub_id)
    if sub is None:
        return None
    pk = store.event_pk(parent_event_id)
    store.restore(pk, sub["SK"])
    sub = _get_sub(parent_event_id, sub_id)
    store.set_attrs(pk, sub["SK"], {
        "GSI4PK": f"REVIEW#{sub['review_status']}", "GSI4SK": sub["created_at"],
        "GSI3PK": f"DUP#{sub['dup_key']}", "GSI3SK": f"SUB#{sub_id}",
    })
    _reindex_sub_pubvis(sub, get_event(parent_event_id))
    return _get_sub(parent_event_id, sub_id)


# ---------------------------------------------------------------------------
# Sub-events
# ---------------------------------------------------------------------------

def create_subevent(parent_event_id, *, start_date, start_time=None, end_time=None,
                    location_id_override=None, event_label_ids=None,
                    review_status=REVIEW_PENDING, publish_status=UNPUBLISHED,
                    cancelled=False, settings=None):
    settings = settings or store.get_settings()
    parent = get_event(parent_event_id)
    if parent is None:
        raise ValueError("parent event not found")

    sub_id = store.new_id()
    pk = store.event_pk(parent_event_id)
    sk = store.sub_sk(start_date or "", sub_id)
    created = store.now_iso()
    effective_location = location_id_override or parent.get("location_id")
    tz = _event_timezone(effective_location, settings)
    effective_end = timeutil.effective_end_utc(
        start_date, start_time, end_time, tz=tz, fallback_tz=settings["fallback_timezone"])
    dup = taxonomy.dup_key(parent.get("title", ""), start_date, effective_location)

    item = store.base_item(
        pk, sk, store.SUBEVENT,
        subevent_id=sub_id, parent_event_id=parent_event_id,
        start_date=start_date or "", start_time=start_time, end_time=end_time,
        location_id_override=location_id_override,
        event_labels_overridden=event_label_ids is not None,
        review_status=review_status, publish_status=publish_status,
        lifecycle_cancelled=bool(cancelled),
        past=timeutil.is_past(effective_end, settings["past_grace_hours"]),
        effective_end_utc=effective_end, dup_key=dup,
        created_at=created,
        GSI3PK=f"DUP#{dup}", GSI3SK=f"SUB#{sub_id}",
        GSI4PK=f"REVIEW#{review_status}", GSI4SK=created,
    )
    store.put(item)
    if location_id_override:
        locations.link_event_to_location(location_id_override, store.SUBEVENT, sub_id)
    for label_id in event_label_ids or []:
        labels.attach_label(store.EVENT_LABEL, label_id, store.SUBEVENT, sub_id)
    if _sub_qualifies_pubvis(item, parent):
        _set_pubvis(pk, sk, effective_end)
    return store.get(pk, sk)


def list_subevents(parent_event_id, *, include_deleted=False):
    return store.query_all(store.event_pk(parent_event_id), sk_begins_with="SUB#",
                           live_only=not include_deleted, ascending=True)


def _reindex_sub_pubvis(sub, parent):
    pk = store.event_pk(parent["event_id"])
    if _sub_qualifies_pubvis(sub, parent):
        _set_pubvis(pk, sub["SK"], sub.get("effective_end_utc"))
    else:
        _clear_pubvis(pk, sub["SK"])


def update_subevent(parent_event_id, sub_id, fields):
    """Edit a sub-event's date/time, location override and label overrides, then
    reindex. Mirrors :func:`update_event`. Because the sort key embeds the date
    (``SUB#<start_date>#<id>``), a start_date change moves the row to a new SK
    (put-new + delete-old); other edits update in place. Returns the refreshed
    sub-event, or None when the parent or sub is missing."""
    parent = get_event(parent_event_id)
    if parent is None:
        return None
    sub = _get_sub(parent_event_id, sub_id)
    if sub is None:
        return None
    settings = store.get_settings()
    pk = store.event_pk(parent_event_id)
    old_sk = sub["SK"]

    updates = {}
    for key in ("start_date", "start_time", "end_time", "location_id_override"):
        if key in fields:
            updates[key] = fields[key]

    old_override = sub.get("location_id_override")
    if "location_id_override" in fields and fields["location_id_override"] != old_override:
        if old_override:
            locations.unlink_event_from_location(old_override, store.SUBEVENT, sub_id)
        if fields["location_id_override"]:
            locations.link_event_to_location(fields["location_id_override"], store.SUBEVENT, sub_id)

    if "event_label_ids" in fields:
        _sync_event_labels(store.SUBEVENT, sub_id, fields["event_label_ids"] or [])
        updates["event_labels_overridden"] = True

    merged = dict(sub)
    merged.update(updates)
    effective_location = merged.get("location_id_override") or parent.get("location_id")
    tz = _event_timezone(effective_location, settings)
    effective_end = timeutil.effective_end_utc(
        merged.get("start_date"), merged.get("start_time"), merged.get("end_time"),
        tz=tz, fallback_tz=settings["fallback_timezone"])
    dup = taxonomy.dup_key(parent.get("title", ""), merged.get("start_date"), effective_location)
    updates.update({
        "effective_end_utc": effective_end,
        "past": timeutil.is_past(effective_end, settings["past_grace_hours"]),
        "dup_key": dup,
        "GSI3PK": f"DUP#{dup}", "GSI3SK": f"SUB#{sub_id}",
    })

    new_sk = store.sub_sk(merged.get("start_date") or "", sub_id)
    if new_sk == old_sk:
        store.set_attrs(pk, old_sk, updates)
    else:
        moved = dict(merged)
        moved.update(updates)
        moved["SK"] = new_sk
        store.put(moved)
        store.delete(pk, old_sk)

    refreshed = _get_sub(parent_event_id, sub_id)
    _reindex_sub_pubvis(refreshed, parent)
    return _get_sub(parent_event_id, sub_id)


def set_subevent_publish(parent_event_id, sub_id, published):
    parent = get_event(parent_event_id)
    if parent is None:
        return None
    sub = _get_sub(parent_event_id, sub_id)
    if sub is None:
        return None
    if published and parent.get("publish_status") != PUBLISHED:
        raise ValueError("cannot publish a sub-event while its parent is unpublished")
    sub["publish_status"] = PUBLISHED if published else UNPUBLISHED
    store.set_attrs(store.event_pk(parent_event_id), sub["SK"],
                    {"publish_status": sub["publish_status"]})
    _reindex_sub_pubvis(sub, parent)
    return _get_sub(parent_event_id, sub_id)


def set_subevent_review(parent_event_id, sub_id, review_status):
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"invalid review status: {review_status!r}")
    sub = _get_sub(parent_event_id, sub_id)
    if sub is None:
        return None
    store.set_attrs(store.event_pk(parent_event_id), sub["SK"], {
        "review_status": review_status,
        "GSI4PK": f"REVIEW#{review_status}",
    })
    return _get_sub(parent_event_id, sub_id)


def cancel_subevent(parent_event_id, sub_id):
    """Cancel a sub-event; if the parent is configured to auto-cancel and all its
    sub-events are now cancelled, cancel the parent too."""
    parent = get_event(parent_event_id)
    sub = _get_sub(parent_event_id, sub_id)
    if parent is None or sub is None:
        return None
    pk = store.event_pk(parent_event_id)
    store.set_attrs(pk, sub["SK"], {"lifecycle_cancelled": True})
    _clear_pubvis(pk, sub["SK"])

    if parent.get("auto_cancel_parent_on_all_subs_cancelled"):
        subs = list_subevents(parent_event_id)
        if subs and all(s.get("lifecycle_cancelled") for s in subs):
            cancel_event(parent_event_id)
    return _get_sub(parent_event_id, sub_id)


def _get_sub(parent_event_id, sub_id):
    for sub in list_subevents(parent_event_id, include_deleted=True):
        if sub.get("subevent_id") == sub_id:
            return sub
    return None


# ---------------------------------------------------------------------------
# Inheritance (computed at query time)
# ---------------------------------------------------------------------------

def effective_location_id(event, sub=None):
    if sub is not None and sub.get("location_id_override"):
        return sub["location_id_override"]
    return event.get("location_id")


def effective_event_label_ids(event, sub=None):
    if sub is not None and sub.get("event_labels_overridden"):
        return labels.label_ids_of(store.SUBEVENT, sub["subevent_id"], store.EVENT_LABEL)
    return labels.label_ids_of(store.EVENT, event["event_id"], store.EVENT_LABEL)


def effective_location_label_ids(event, sub=None):
    location_id = effective_location_id(event, sub)
    return locations.location_label_ids(location_id) if location_id else []


# ---------------------------------------------------------------------------
# Duplicate detection & re-extraction
# ---------------------------------------------------------------------------

def find_duplicate(dup_key):
    """First live event matching a dedup key, else None."""
    matches = store.query_index_all("GSI3", f"DUP#{dup_key}", live_only=True)
    for item in matches:
        if item.get("entity_type") == store.EVENT:
            return item
    return None


def resolve_extracted(dup_key):
    """Re-extraction decision for a candidate. Returns ('create', None) when
    there is no live duplicate; ('skip', existing) otherwise (a duplicate is
    never re-created — rejected stays rejected, edited is preserved, and an
    untouched match is left alone)."""
    existing = find_duplicate(dup_key)
    return ("create", None) if existing is None else ("skip", existing)


def _resolve_location(suggestion, settings):
    """Fuzzy-match an agent location suggestion to an existing location, or
    create a new one. Admin reviews the association later."""
    if not suggestion or not suggestion.get("name"):
        return None
    matches = locations.fuzzy_match(suggestion["name"])
    if matches:
        return matches[0]["location_id"]
    created = locations.create_location(
        suggestion["name"], address=suggestion.get("address", ""),
        timezone=suggestion.get("timezone") or settings["fallback_timezone"])
    return created["location_id"]


def convert_extraction(source_id, extracted_events, *, settings=None):
    """Convert the agent's extracted events into pending records, applying fuzzy
    location matching, label resolution, image attachment, and dedup. Duplicates
    are skipped per the re-extraction rules."""
    settings = settings or store.get_settings()
    created_ids = []
    skipped = 0

    for raw in extracted_events:
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        location_id = _resolve_location(raw.get("location"), settings)
        dup = taxonomy.dup_key(title, raw.get("start_date"), location_id)
        decision, _existing = resolve_extracted(dup)
        if decision == "skip":
            skipped += 1
            continue

        label_ids = [labels.find_or_create(store.EVENT_LABEL, name)["label_id"]
                     for name in raw.get("event_labels", [])]
        event = create_event(
            source_id, title=title, start_date=raw.get("start_date", ""),
            description=raw.get("description", ""),
            start_time=raw.get("start_time"), end_time=raw.get("end_time"),
            location_id=location_id, event_label_ids=label_ids,
            event_url=raw.get("event_url"), settings=settings)
        event_id = event["event_id"]
        created_ids.append(event_id)

        for url in raw.get("images", []):
            # We only attach images we successfully own. If the download fails
            # the image is dropped (no DB record); we never serve an external
            # url as a fallback because that's hostile to our own-domain model.
            try:
                data, content_type = image_store.download(url)
            except image_store.DownloadError:
                continue
            image_id = store.new_id()
            ref = image_store.put_bytes(image_id, data, content_type)
            images.add_image(
                store.EVENT, event_id, image_id=image_id,
                url=url, s3_ref=ref, source=images.AGENT)

        for sub in raw.get("sub_events", []):
            sub_location = _resolve_location(sub.get("location"), settings)
            sub_label_ids = None
            if sub.get("event_labels"):
                sub_label_ids = [labels.find_or_create(store.EVENT_LABEL, n)["label_id"]
                                 for n in sub["event_labels"]]
            create_subevent(
                event_id, start_date=sub.get("start_date", ""),
                start_time=sub.get("start_time"), end_time=sub.get("end_time"),
                location_id_override=sub_location, event_label_ids=sub_label_ids,
                settings=settings)

    return {"created": len(created_ids), "skipped": skipped, "event_ids": created_ids}


# ---------------------------------------------------------------------------
# Sweep: materialize past + parent auto-past
# ---------------------------------------------------------------------------

def sweep(now=None, settings=None):
    """Refresh the materialized `past` flag on events/sub-events and apply the
    per-event auto-past-when-all-subs-past rule. Returns the count changed."""
    settings = settings or store.get_settings()
    grace = settings["past_grace_hours"]
    now = now or datetime.now(timezone.utc)
    changed = 0

    subs_by_parent = {}
    for sub in store.scan_by_type(store.SUBEVENT):
        is_past = timeutil.is_past(sub.get("effective_end_utc"), grace, now)
        if bool(sub.get("past")) != is_past:
            store.set_attrs(sub["PK"], sub["SK"], {"past": is_past})
            changed += 1
        sub["past"] = is_past
        subs_by_parent.setdefault(sub["parent_event_id"], []).append(sub)

    for event in store.scan_by_type(store.EVENT):
        is_past = timeutil.is_past(event.get("effective_end_utc"), grace, now)
        subs = subs_by_parent.get(event["event_id"], [])
        if event.get("auto_past_parent_on_all_subs_past") and subs \
                and all(s["past"] for s in subs):
            is_past = True
        if bool(event.get("past")) != is_past:
            store.set_attrs(store.event_pk(event["event_id"]), "META", {"past": is_past})
            changed += 1

    return changed
