"""
Location service layer.

Locations are venues (name, address, IANA timezone) stored at PK=LOC#<id>,
SK=META and listed via GSI1 partition LOC#ALL ordered by normalized name. An
event/sub-event that has a location also writes a lightweight pointer item
(SK=EVT#<id> / SUB#<id>) into the location partition so "events at location X"
is a single Query — which also drives the location-merge reassignment.

Fuzzy matching (difflib over normalized names) backs the admin's
"associate with an existing location?" review. Merge reassigns every reference
to a target location and soft-deletes the source locations.
"""

import difflib

from scout_core.domain import labels
from scout_core.adapters import store
from scout_core.common import taxonomy as tax

_LISTING_PK = "LOC#ALL"


def _listing_sk(name_norm, loc_id):
    return f"{name_norm}#{loc_id}"


# ---------------------------------------------------------------------------
# Location CRUD
# ---------------------------------------------------------------------------

def create_location(name, address="", timezone="UTC"):
    name = (name or "").strip()
    if not name:
        raise ValueError("location name is required")
    loc_id = store.new_id()
    norm = tax.normalize_name(name)
    item = store.base_item(
        store.location_pk(loc_id), "META", store.LOCATION,
        location_id=loc_id,
        name=name,
        name_norm=norm,
        address=address or "",
        timezone=timezone or "UTC",
        GSI1PK=_LISTING_PK,
        GSI1SK=_listing_sk(norm, loc_id),
    )
    return store.put(item)


def get_location(loc_id):
    return store.get(store.location_pk(loc_id), "META")


def list_locations():
    """All live locations, ordered by normalized name."""
    return store.query_index_all("GSI1", _LISTING_PK, ascending=True)


def update_location(loc_id, fields):
    updates = {}
    if "name" in fields and (fields["name"] or "").strip():
        name = fields["name"].strip()
        norm = tax.normalize_name(name)
        updates.update({
            "name": name,
            "name_norm": norm,
            "GSI1SK": _listing_sk(norm, loc_id),
        })
    if "address" in fields:
        updates["address"] = fields["address"] or ""
    if "timezone" in fields:
        updates["timezone"] = fields["timezone"] or "UTC"
    store.set_attrs(store.location_pk(loc_id), "META", updates)
    return get_location(loc_id)


def delete_location(loc_id):
    """Soft-delete a location. Cascade to its events (with opt-out) is handled
    by the deletion layer in a later phase; this only removes the location."""
    store.soft_delete(store.location_pk(loc_id), "META", store.LOCATION)


def restore_location(loc_id):
    pk = store.location_pk(loc_id)
    loc = store.get(pk, "META")
    if loc is None:
        return None
    store.restore(pk, "META")
    norm = loc.get("name_norm", "")
    store.set_attrs(pk, "META", {
        "GSI1PK": _LISTING_PK,
        "GSI1SK": _listing_sk(norm, loc_id),
    })
    return get_location(loc_id)


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def fuzzy_match(name, *, threshold=0.85, limit=5):
    """Existing live locations whose normalized name is similar to `name`,
    best match first. Backs the admin location-association review."""
    norm = tax.normalize_name(name)
    if not norm:
        return []
    scored = []
    for loc in list_locations():
        ratio = difflib.SequenceMatcher(None, norm, loc.get("name_norm", "")).ratio()
        if ratio >= threshold:
            scored.append((ratio, loc))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("name", "")))
    return [loc for _, loc in scored[:limit]]


# ---------------------------------------------------------------------------
# Location <-> event reference pointers
# ---------------------------------------------------------------------------

def link_event_to_location(loc_id, target_type, target_id):
    """Record that an event/sub-event references this location (pointer item)."""
    pk = store.location_pk(loc_id)
    sk = store.entity_ref(target_type, target_id)
    item = store.base_item(
        pk, sk, "loc_event_link",
        location_id=loc_id,
        target_type=target_type,
        target_id=target_id,
    )
    return store.put(item)


def unlink_event_from_location(loc_id, target_type, target_id):
    store.delete(store.location_pk(loc_id), store.entity_ref(target_type, target_id))


def events_at_location(loc_id):
    """Pointer items for events/sub-events referencing a location."""
    pk = store.location_pk(loc_id)
    return (store.query_all(pk, sk_begins_with="EVT#")
            + store.query_all(pk, sk_begins_with="SUB#"))


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge_locations(target_id, source_ids):
    """Reassign every reference from `source_ids` to `target_id`, then
    soft-delete the source locations (stamped with merged_into)."""
    if get_location(target_id) is None:
        raise ValueError(f"target location {target_id!r} not found")

    moved = 0
    merged = []
    for source_id in source_ids:
        if source_id == target_id:
            continue
        for ptr in events_at_location(source_id):
            target_type, target = ptr["target_type"], ptr["target_id"]
            if target_type == store.EVENT:
                store.set_attrs(store.event_pk(target), "META",
                                {"location_id": target_id})
            store.delete(store.location_pk(source_id), ptr["SK"])
            link_event_to_location(target_id, target_type, target)
            moved += 1
        store.soft_delete(store.location_pk(source_id), "META", store.LOCATION)
        store.set_attrs(store.location_pk(source_id), "META",
                        {"merged_into": target_id})
        merged.append(source_id)

    return {"target_id": target_id, "merged_sources": merged, "references_moved": moved}


# ---------------------------------------------------------------------------
# Label inheritance helper
# ---------------------------------------------------------------------------

def location_label_ids(loc_id):
    """Location-label ids carried by a location. Events inherit these at query
    time (the foundation for location->event label inheritance)."""
    return labels.label_ids_of(store.LOCATION, loc_id, taxonomy=store.LOCATION_LABEL)
