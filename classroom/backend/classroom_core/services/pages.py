"""Page lifecycle: create, edit, publish, withdraw, delete.

Routes stay thin; the rules about what a page *is* live here. Missing required
fields raise KeyError and invalid values raise ValueError, both of which
app_factory maps to 400.
"""

from classroom_core import config
from classroom_core.repositories import store
from classroom_core.utils import html

MAX_TITLE_CHARS = 200

# A generous ceiling on a single page's HTML. DynamoDB's own item limit is
# 400KB and the item carries more than just the body, so this leaves room and
# fails with a readable message instead of a ValidationException from boto3.
MAX_HTML_BYTES = 256 * 1024


def _clean_title(raw_title) -> str:
    title = (raw_title or "").strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > MAX_TITLE_CHARS:
        raise ValueError(f"title must be {MAX_TITLE_CHARS} characters or fewer")
    return title


def _clean_html(raw_html) -> str:
    body = raw_html or ""
    if len(body.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError(
            f"page content must be {MAX_HTML_BYTES // 1024}KB or smaller"
        )
    return html.sanitize(body)


def serialize(item: dict, include_html: bool = True) -> dict:
    """A page item as the API returns it.

    The DynamoDB key attributes are internal and never leave the service.
    """
    page = {
        "id": item["page_id"],
        "title": item["title"],
        "slug": item["slug"],
        "published": bool(item.get("published")),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "share_url": share_url(item["slug"]) if item.get("published") else None,
    }
    if include_html:
        page["html"] = item.get("html", "")
    return page


def share_url(slug: str) -> str:
    """The link a teacher hands to students."""
    base = config.public_site_base()
    return f"{base}/p/{slug}" if base else f"/p/{slug}"


def list_pages(teacher_id: str) -> list[dict]:
    return [
        serialize(item, include_html=False)
        for item in store.list_pages_for_teacher(teacher_id)
    ]


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
            "slug": store.slugify(title),
            "html": _clean_html(payload.get("html")),
            "published": bool(payload.get("published")),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )
    return serialize(item)


def update_page(teacher_id: str, page_id: str, payload: dict) -> dict | None:
    """Apply a partial update. Returns None when the page does not exist.

    The slug is deliberately stable across edits: it is already written on a
    whiteboard or pasted into a class message by the time anyone edits the
    page, and silently reissuing it would break every link already handed out.
    """
    item = store.get_page(teacher_id, page_id)
    if item is None:
        return None

    if "title" in payload:
        item["title"] = _clean_title(payload.get("title"))
    if "html" in payload:
        item["html"] = _clean_html(payload.get("html"))
    if "published" in payload:
        item["published"] = bool(payload.get("published"))

    item["updated_at"] = store.now_iso()
    return serialize(store.put_page(item))


def delete_page(teacher_id: str, page_id: str) -> bool:
    """Delete a page. Returns False when it did not exist."""
    if store.get_page(teacher_id, page_id) is None:
        return False
    store.delete_page(teacher_id, page_id)
    return True


def get_published_page(slug: str) -> dict | None:
    """A published page for an anonymous student reader."""
    item = store.get_published_page_by_slug(slug)
    if item is None:
        return None
    return {
        "title": item["title"],
        "html": item.get("html", ""),
        "updated_at": item.get("updated_at"),
    }
