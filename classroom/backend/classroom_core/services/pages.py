"""Page lifecycle: create, edit, publish, withdraw, delete.

Routes stay thin; the rules about what a page *is* live here. Missing required
fields raise KeyError and invalid values raise ValueError, both of which
app_factory maps to 400.
"""

from classroom_core import config
from classroom_core.repositories import lessons, store

MAX_TITLE_CHARS = 200


def _clean_title(raw_title) -> str:
    title = (raw_title or "").strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > MAX_TITLE_CHARS:
        raise ValueError(f"title must be {MAX_TITLE_CHARS} characters or fewer")
    return title


def serialize(item: dict) -> dict:
    """A page item as the API returns it.

    The DynamoDB key attributes are internal and never leave the service.

    **There is no `html` field any more.** A page's content is a directory of
    files in S3, not a column here; this table holds only what a directory
    cannot — the title, the publication state and the timestamps.
    """
    return {
        "id": item["page_id"],
        "title": item["title"],
        "published": bool(item.get("published")),
        "file_count": int(item.get("file_count", 0) or 0),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "share_url": share_url(item["page_id"]) if item.get("published") else None,
        # Only once staged, so the UI never offers a link to nothing.
        "preview_url": (
            lesson_url(item["preview_id"]) if item.get("preview_id") else None
        ),
    }


def lesson_url(lesson_id: str) -> str:
    """A URL under the student host for anything served from `lesson/<id>/`."""
    base = config.public_site_base()
    return f"{base}/lesson/{lesson_id}/" if base else f"/lesson/{lesson_id}/"


def share_url(page_id: str) -> str:
    """The link a teacher hands to students.

    Built on the PAGE ID rather than the slug, and pointed at the student host
    rather than the app. CloudFront maps this URL straight onto the S3 key
    `lesson/<id>/index.html` with no lookup, which is what lets her images and
    stylesheets resolve by relative path exactly as they did on her machine.
    """
    return lesson_url(page_id)


def list_pages(teacher_id: str) -> list[dict]:
    return [serialize(item) for item in store.list_pages_for_teacher(teacher_id)]


def get_page(teacher_id: str, page_id: str) -> dict | None:
    item = store.get_page(teacher_id, page_id)
    return serialize(item) if item else None


def create_page(teacher: dict, payload: dict) -> dict:
    title = _clean_title(payload.get("title"))
    timestamp = store.now_iso()
    item = store.put_page(
        {
            "page_id": store.new_id(),
            "teacher_id": teacher["id"],
            "teacher_email": teacher.get("email", ""),
            "title": title,
            # A page starts empty and unpublished: it has no files until she
            # uploads some, and nothing to serve until she does.
            "published": False,
            "file_count": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    return serialize(item)


def update_page(teacher_id: str, page_id: str, payload: dict) -> dict | None:
    """Apply a partial update. Returns None when the page does not exist.

    A page's URL never changes, because it is built from the page id — which is
    assigned once and never reissued. Renaming a lesson cannot break a link a
    teacher has already written on a whiteboard.
    """
    item = store.get_page(teacher_id, page_id)
    if item is None:
        return None

    if "title" in payload:
        item["title"] = _clean_title(payload.get("title"))
    if "published" in payload:
        # Publication is a change to what EXISTS in S3, not just a flag: see
        # `repositories/lessons`. The flag records the outcome.
        if payload.get("published"):
            item["file_count"] = lessons.publish(page_id)
        else:
            lessons.withdraw(page_id)
        item["published"] = bool(payload.get("published"))

    item["updated_at"] = store.now_iso()
    return serialize(store.put_page(item))


def delete_page(teacher_id: str, page_id: str) -> bool:
    """Delete a page and every file uploaded for it. False when it did not exist.

    S3 first, then the row. The other order can leave a directory in the bucket
    that nothing points at any more — billable, servable if it was published,
    and invisible to the teacher who thought she had deleted it.
    """
    if store.get_page(teacher_id, page_id) is None:
        return False
    lessons.delete_everything(page_id, store.get_page(teacher_id, page_id).get("preview_id", ""))
    store.delete_page(teacher_id, page_id)
    return True


def start_upload(teacher_id: str, page_id: str, payload: dict) -> dict | None:
    """Sign a PUT for each file the browser is about to send.

    The browser has already turned all three upload shapes — a single `.html`,
    an unpacked `.zip`, a chosen folder — into one list of relative paths, so
    there is a single code path here.

    **The draft is emptied first.** An upload REPLACES a lesson rather than
    merging into it: a file she deleted or renamed in her authoring tool must
    not survive in the copy her students open.
    """
    if store.get_page(teacher_id, page_id) is None:
        return None

    paths = payload.get("paths")
    if not isinstance(paths, list) or not paths:
        raise ValueError("paths must be a non-empty list")
    if len(paths) > lessons.MAX_FILES_PER_LESSON:
        raise ValueError(
            f"a lesson may hold at most {lessons.MAX_FILES_PER_LESSON} files"
        )

    # Validate every path BEFORE signing any of them, so a single bad entry
    # cannot leave half a lesson uploaded against half a set of URLs.
    cleaned = [lessons.clean_path(path) for path in paths]
    if lessons.INDEX_FILE not in cleaned:
        raise ValueError(
            f"a lesson needs an {lessons.INDEX_FILE} at the top level of what you upload"
        )

    lessons.clear_draft(page_id)
    return {"uploads": [lessons.presign_upload(page_id, path) for path in cleaned]}


def finish_upload(teacher_id: str, page_id: str) -> dict | None:
    """Record what actually landed, once the browser reports its PUTs done.

    Read back from S3 rather than trusted from the request: the count that
    matters is what is in the bucket, and a browser that failed halfway should
    not be able to claim otherwise.
    """
    item = store.get_page(teacher_id, page_id)
    if item is None:
        return None

    files = lessons.list_draft_files(page_id)
    item["file_count"] = len(files)
    item["updated_at"] = store.now_iso()

    # A re-upload invalidates what students are being served, so a published
    # lesson is re-published from the new draft. Doing nothing would leave her
    # class reading the previous version with no indication anything had changed.
    if item.get("published"):
        item["file_count"] = lessons.publish(page_id)

    saved = serialize(store.put_page(item))
    saved["files"] = files
    return saved


def stage_preview(teacher_id: str, page_id: str) -> dict | None:
    """Put the current draft somewhere she can look at it, and return the link.

    **Not `lesson/<page-id>/`.** Previewing an edit to a lesson that is already
    live must not push that edit to the class holding its link, so the preview
    goes to its own unguessable id — minted once and kept, so the link stays
    stable across previews and she can leave the tab open.

    Restaged on every call: the point of a preview is to show what is uploaded
    NOW.
    """
    item = store.get_page(teacher_id, page_id)
    if item is None:
        return None

    preview_id = item.get("preview_id") or store.new_id()
    files = lessons.stage_preview(page_id, preview_id)

    item["preview_id"] = preview_id
    item["updated_at"] = store.now_iso()
    saved = serialize(store.put_page(item))
    saved["file_count"] = files
    return saved


def draft_files(teacher_id: str, page_id: str) -> list[str] | None:
    """What is currently uploaded, for the page screen to list."""
    if store.get_page(teacher_id, page_id) is None:
        return None
    return lessons.list_draft_files(page_id)

