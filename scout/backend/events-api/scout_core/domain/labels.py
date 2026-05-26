"""
Label taxonomy service layer.

Three independent taxonomies — source-labels, event-labels, location-labels —
each a separate keyspace (PK prefix) in the scout-core table. A label's META
item lives at PK=<NS>#<id>, SK=META; its M2M associations are junction items in
the same partition (SK=LINK#<ref>) so "entities with label X" is one Query,
while GSI2 indexes the reverse "labels of entity Y" direction.

Labels are listed via GSI1 partition LBL#<taxonomy> ordered by normalized name;
soft-deleting a label drops it out of that listing (and reverse-direction
queries via the live-only filter) without cascading to the tagged entities.
"""

from scout_core.adapters import store
from scout_core.common import taxonomy as tax

TAXONOMIES = (store.SOURCE_LABEL, store.EVENT_LABEL, store.LOCATION_LABEL)

# entity_type stamped on a junction item, per taxonomy.
_LINK_TYPE = {
    store.SOURCE_LABEL: store.SOURCE_LABEL_LINK,
    store.EVENT_LABEL: store.EVENT_LABEL_LINK,
    store.LOCATION_LABEL: store.LOCATION_LABEL_LINK,
}

# entity types each taxonomy is allowed to tag.
_TARGETS = {
    store.SOURCE_LABEL: {store.SOURCE},
    store.EVENT_LABEL: {store.EVENT, store.SUBEVENT},
    store.LOCATION_LABEL: {store.LOCATION},
}


def _check_taxonomy(taxonomy):
    if taxonomy not in TAXONOMIES:
        raise ValueError(f"unknown label taxonomy: {taxonomy!r}")


def _listing_pk(taxonomy):
    return f"LBL#{taxonomy}"


def _listing_sk(name_norm, label_id):
    return f"{name_norm}#{label_id}"


# ---------------------------------------------------------------------------
# Label CRUD
# ---------------------------------------------------------------------------

def create_label(taxonomy, name):
    _check_taxonomy(taxonomy)
    name = (name or "").strip()
    if not name:
        raise ValueError("label name is required")
    label_id = store.new_id()
    norm = tax.normalize_name(name)
    item = store.base_item(
        store.label_pk(taxonomy, label_id), "META", taxonomy,
        label_id=label_id,
        name=name,
        name_norm=norm,
        GSI1PK=_listing_pk(taxonomy),
        GSI1SK=_listing_sk(norm, label_id),
    )
    return store.put(item)


def get_label(taxonomy, label_id):
    return store.get(store.label_pk(taxonomy, label_id), "META")


def list_labels(taxonomy):
    """All live labels of a taxonomy, ordered by normalized name."""
    _check_taxonomy(taxonomy)
    return store.query_index_all("GSI1", _listing_pk(taxonomy), ascending=True)


def rename_label(taxonomy, label_id, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("label name is required")
    norm = tax.normalize_name(name)
    store.set_attrs(store.label_pk(taxonomy, label_id), "META", {
        "name": name,
        "name_norm": norm,
        "GSI1SK": _listing_sk(norm, label_id),
    })
    return get_label(taxonomy, label_id)


def delete_label(taxonomy, label_id):
    """Soft-delete a label and its associations. No cascade to tagged entities —
    the references are simply removed (soft-deleted junctions drop out of
    live-only label queries)."""
    pk = store.label_pk(taxonomy, label_id)
    for link in store.query_all(pk, sk_begins_with="LINK#"):
        store.soft_delete(pk, link["SK"], _LINK_TYPE[taxonomy])
    store.soft_delete(pk, "META", taxonomy)


def restore_label(taxonomy, label_id):
    """Restore a soft-deleted label's META back into the listing. Associations
    are not auto-restored (label deletion never cascaded them)."""
    pk = store.label_pk(taxonomy, label_id)
    label = store.get(pk, "META")
    if label is None:
        return None
    store.restore(pk, "META")
    norm = label.get("name_norm", "")
    store.set_attrs(pk, "META", {
        "GSI1PK": _listing_pk(taxonomy),
        "GSI1SK": _listing_sk(norm, label_id),
    })
    return get_label(taxonomy, label_id)


# ---------------------------------------------------------------------------
# Associations (junction items)
# ---------------------------------------------------------------------------

def attach_label(taxonomy, label_id, target_type, target_id):
    """Tag an entity with a label. Idempotent (same edge overwrites)."""
    _check_taxonomy(taxonomy)
    if target_type not in _TARGETS[taxonomy]:
        raise ValueError(
            f"{taxonomy} cannot tag a {target_type} entity"
        )
    pk = store.label_pk(taxonomy, label_id)
    sk = store.link_sk(target_type, target_id)
    item = store.base_item(
        pk, sk, _LINK_TYPE[taxonomy],
        label_id=label_id,
        target_type=target_type,
        target_id=target_id,
        GSI2PK=store.entity_ref(target_type, target_id),
        GSI2SK=f"LINK#{taxonomy}#{label_id}",
    )
    return store.put(item)


def detach_label(taxonomy, label_id, target_type, target_id):
    """Remove a single label->entity edge (admin un-tag)."""
    store.delete(store.label_pk(taxonomy, label_id),
                 store.link_sk(target_type, target_id))


def label_ids_of(target_type, target_id, taxonomy=None):
    """Label ids attached to an entity (live edges), optionally one taxonomy."""
    ref = store.entity_ref(target_type, target_id)
    sk_prefix = f"LINK#{taxonomy}#" if taxonomy else None
    links = store.query_index_all("GSI2", ref, sk_begins_with=sk_prefix)
    return [link["label_id"] for link in links]


def entities_with_label(taxonomy, label_id):
    """(target_type, target_id) pairs tagged with a label (live edges)."""
    pk = store.label_pk(taxonomy, label_id)
    links = store.query_all(pk, sk_begins_with="LINK#")
    return [(link["target_type"], link["target_id"]) for link in links]


def find_by_name(taxonomy, name):
    """First live label in a taxonomy whose normalized name matches, else None."""
    norm = tax.normalize_name(name)
    if not norm:
        return None
    for label in list_labels(taxonomy):
        if label.get("name_norm") == norm:
            return label
    return None


def find_or_create(taxonomy, name):
    """Resolve a label by name, creating it if it does not exist yet. Used when
    converting agent-suggested labels into records."""
    return find_by_name(taxonomy, name) or create_label(taxonomy, name)


def resolve_labels(taxonomy, label_ids):
    """Hydrate label ids into their (live) META items, preserving order."""
    out = []
    for label_id in label_ids:
        item = store.get(store.label_pk(taxonomy, label_id), "META")
        if item is not None and "deleted_at" not in item:
            out.append(item)
    return out
