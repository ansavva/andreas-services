"""
Event/sub-event image management.

Images attach to an event (PK=EVT#<id>, SK=IMG#<image_id>) or a sub-event
(PK=EVT#<parent_id>, SK=SUBIMG#<sub_id>#<image_id>). Admin-uploaded images are
approved on creation; agent-extracted images carry approved=false and must be
approved by an admin before they are visible publicly — an approval flag
independent of the owning event's review status. Binary uploads live in the
images S3 bucket (s3_ref); agent images reference a source url.
"""

from scout_core.adapters import store

ADMIN = "admin"
AGENT = "agent"

ENTITY_TYPE = "event_image"


def _keys(owner_type, owner_id, image_id, parent_event_id=None):
    if owner_type == store.EVENT:
        return store.event_pk(owner_id), f"IMG#{image_id}"
    if owner_type == store.SUBEVENT:
        if not parent_event_id:
            raise ValueError("parent_event_id is required for sub-event images")
        return store.event_pk(parent_event_id), f"SUBIMG#{owner_id}#{image_id}"
    raise ValueError(f"images cannot attach to a {owner_type}")


def _prefix(owner_type, owner_id):
    return "IMG#" if owner_type == store.EVENT else f"SUBIMG#{owner_id}#"


def add_image(owner_type, owner_id, *, s3_ref, url=None, source=ADMIN,
              parent_event_id=None, image_id=None):
    """Attach an image. Admin uploads are auto-approved; agent images await
    admin approval before becoming publicly visible.

    Every image must have an `s3_ref` — we only serve images we own, streamed
    from the private images bucket under our own domain. The optional `url`
    is kept only as provenance (the original source link).

    Callers may pre-generate `image_id` so they can put image bytes to S3
    under that id before the DynamoDB record exists — keeps the on-disk and
    in-DB views consistent on the success path.
    """
    if not s3_ref:
        raise ValueError("image requires an s3_ref")
    image_id = image_id or store.new_id()
    pk, sk = _keys(owner_type, owner_id, image_id, parent_event_id)
    item = store.base_item(
        pk, sk, ENTITY_TYPE,
        image_id=image_id,
        owner_type=owner_type,
        owner_id=owner_id,
        parent_event_id=parent_event_id,
        url=url,
        s3_ref=s3_ref,
        source=source,
        approved=(source == ADMIN),
    )
    return store.put(item)


def list_images(owner_type, owner_id, *, parent_event_id=None,
                approved_only=False, include_deleted=False):
    pk = (store.event_pk(owner_id) if owner_type == store.EVENT
          else store.event_pk(parent_event_id))
    items = store.query_all(pk, sk_begins_with=_prefix(owner_type, owner_id),
                            live_only=not include_deleted)
    if approved_only:
        items = [i for i in items if i.get("approved")]
    return items


def approve_image(owner_type, owner_id, image_id, *, parent_event_id=None):
    pk, sk = _keys(owner_type, owner_id, image_id, parent_event_id)
    store.set_attrs(pk, sk, {"approved": True})
    return store.get(pk, sk)


def delete_image(owner_type, owner_id, image_id, *, parent_event_id=None):
    pk, sk = _keys(owner_type, owner_id, image_id, parent_event_id)
    store.soft_delete(pk, sk, ENTITY_TYPE)
