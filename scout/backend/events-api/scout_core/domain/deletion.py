"""
Cascade soft-delete and recursive restore.

All deletes are soft. A delete may cascade to children (with admin opt-out); the
preview_* helpers report what would cascade so the admin sees an upfront warning.
Every item removed in one operation shares a cascade_id, and a CASCADE#<id>
partition records the members so restore reverses exactly that operation —
children that were cascaded with a parent are restored alongside it.

Cascade rules (§7.2):
- source  -> events (opt-out); its runs are always soft-deleted alongside.
- location-> events (opt-out).
- event   -> sub-events (opt-out).
- label   -> no cascade (handled in labels.delete_label; references removed only).
"""

from scout_core.domain import events
from scout_core.domain import locations
from scout_core.domain import runs
from scout_core.domain import sources
from scout_core.adapters import store

# Per-entity hot index attributes to strip on soft-delete (so the row leaves its
# listing/visibility/dedup paths). GSI5 (deleted view) is added by store.soft_delete.
_HOT = {
    store.EVENT: ("GSI1PK", "GSI1SK", "GSI3PK", "GSI3SK", "GSI4PK", "GSI4SK"),
    store.SUBEVENT: ("GSI1PK", "GSI1SK", "GSI3PK", "GSI3SK", "GSI4PK", "GSI4SK"),
    store.SOURCE: ("GSI1PK", "GSI1SK", "GSI4PK", "GSI4SK"),
    store.LOCATION: ("GSI1PK", "GSI1SK"),
    store.RUN: ("GSI1PK", "GSI1SK"),
}


def _record_member(cascade_id, pk, sk, entity_type):
    store.put({
        "PK": f"CASCADE#{cascade_id}", "SK": f"M#{pk}#{sk}",
        "entity_type": "cascade_member",
        "member_pk": pk, "member_sk": sk, "member_type": entity_type,
    })


def _soft_delete(cascade_id, pk, sk, entity_type, *, via_cascade, parent_ref=None):
    store.soft_delete(pk, sk, entity_type, cascade_id=cascade_id,
                      via_cascade=via_cascade, parent_ref=parent_ref,
                      hot_index_attrs=_HOT.get(entity_type, store.HOT_INDEX_ATTRS))
    _record_member(cascade_id, pk, sk, entity_type)


def _events_of_source(source_id):
    return [e for e in store.scan_by_type(store.EVENT)
            if e.get("source_id") == source_id]


def _cascade_delete_event(cascade_id, event_id, *, parent_ref):
    """Soft-delete an event and all its sub-events under one cascade. Returns the
    number of sub-events removed."""
    pk = store.event_pk(event_id)
    if store.get(pk, "META") is None:
        return 0
    _soft_delete(cascade_id, pk, "META", store.EVENT,
                 via_cascade=True, parent_ref=parent_ref)
    removed = 0
    for sub in events.list_subevents(event_id):
        _soft_delete(cascade_id, pk, sub["SK"], store.SUBEVENT,
                     via_cascade=True, parent_ref=f"EVT#{event_id}")
        removed += 1
    return removed


# ---------------------------------------------------------------------------
# Previews (upfront cascade warnings)
# ---------------------------------------------------------------------------

def preview_delete_source(source_id):
    evs = _events_of_source(source_id)
    subs = sum(len(events.list_subevents(e["event_id"])) for e in evs)
    return {"events": len(evs), "subevents": subs, "runs": len(runs.list_runs(source_id))}


def preview_delete_location(location_id):
    refs = [p for p in locations.events_at_location(location_id)
            if p["target_type"] == store.EVENT]
    subs = sum(len(events.list_subevents(p["target_id"])) for p in refs)
    return {"events": len(refs), "subevents": subs}


def preview_delete_event(event_id):
    return {"subevents": len(events.list_subevents(event_id))}


# ---------------------------------------------------------------------------
# Cascade deletes
# ---------------------------------------------------------------------------

def delete_source(source_id, *, cascade_events=True):
    if sources.get_source(source_id) is None:
        return None
    cascade_id = store.new_id()
    src_pk = store.source_pk(source_id)
    _soft_delete(cascade_id, src_pk, "META", store.SOURCE, via_cascade=False)

    for run in runs.list_runs(source_id):
        _soft_delete(cascade_id, src_pk, run["SK"], store.RUN,
                     via_cascade=True, parent_ref=f"SRC#{source_id}")

    events_removed = subs_removed = 0
    if cascade_events:
        for event in _events_of_source(source_id):
            subs_removed += _cascade_delete_event(
                cascade_id, event["event_id"], parent_ref=f"SRC#{source_id}")
            events_removed += 1
    return {"cascade_id": cascade_id, "events": events_removed,
            "subevents": subs_removed}


def delete_location(location_id, *, cascade_events=True):
    if locations.get_location(location_id) is None:
        return None
    cascade_id = store.new_id()
    _soft_delete(cascade_id, store.location_pk(location_id), "META",
                 store.LOCATION, via_cascade=False)

    events_removed = subs_removed = 0
    if cascade_events:
        for ptr in locations.events_at_location(location_id):
            if ptr["target_type"] == store.EVENT:
                subs_removed += _cascade_delete_event(
                    cascade_id, ptr["target_id"], parent_ref=f"LOC#{location_id}")
                events_removed += 1
    return {"cascade_id": cascade_id, "events": events_removed,
            "subevents": subs_removed}


def delete_event(event_id, *, cascade_subs=True):
    pk = store.event_pk(event_id)
    if store.get(pk, "META") is None:
        return None
    cascade_id = store.new_id()
    _soft_delete(cascade_id, pk, "META", store.EVENT, via_cascade=False)

    subs_removed = 0
    if cascade_subs:
        for sub in events.list_subevents(event_id):
            _soft_delete(cascade_id, pk, sub["SK"], store.SUBEVENT,
                         via_cascade=True, parent_ref=f"EVT#{event_id}")
            subs_removed += 1
    return {"cascade_id": cascade_id, "subevents": subs_removed}


# ---------------------------------------------------------------------------
# Recursive restore
# ---------------------------------------------------------------------------

_RESTORE_ORDER = {store.SOURCE: 0, store.LOCATION: 0, store.EVENT: 1,
                  store.SUBEVENT: 2, store.RUN: 3}


def _restore_member(member_type, pk, sk):
    if member_type == store.SOURCE:
        sources.restore_source(pk.split("#", 1)[1])
    elif member_type == store.LOCATION:
        locations.restore_location(pk.split("#", 1)[1])
    elif member_type == store.EVENT:
        events.restore_event(pk.split("#", 1)[1])
    elif member_type == store.SUBEVENT:
        item = store.get(pk, sk)
        events.restore_subevent(pk.split("#", 1)[1], item["subevent_id"])
    else:  # runs and anything else: clear delete markers only
        store.restore(pk, sk)


def restore_cascade(cascade_id):
    """Restore every item recorded under a cascade, parents before children, then
    drop the cascade bookkeeping."""
    members = store.query_all(f"CASCADE#{cascade_id}", sk_begins_with="M#",
                              live_only=False)
    members.sort(key=lambda m: _RESTORE_ORDER.get(m["member_type"], 5))
    for member in members:
        _restore_member(member["member_type"], member["member_pk"], member["member_sk"])
    for member in members:
        store.delete(member["PK"], member["SK"])
    return {"cascade_id": cascade_id, "restored": len(members)}


def restore(pk, sk):
    """Restore a soft-deleted item. If it was removed as part of a cascade, the
    whole cascade is restored alongside it."""
    item = store.get(pk, sk)
    if item is None:
        return None
    cascade_id = item.get("cascade_id")
    if cascade_id:
        return restore_cascade(cascade_id)
    _restore_member(item.get("entity_type"), pk, sk)
    return {"restored": 1}
