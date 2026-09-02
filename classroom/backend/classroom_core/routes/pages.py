"""Authenticated page endpoints, scoped to the calling teacher.

Every handler reads its teacher from the verified Cognito claims rather than
from anything in the request body, so one teacher cannot address another
teacher's pages by guessing an id.
"""

from flask import Blueprint

from classroom_core.auth import current_teacher
from classroom_core.routes._shared import body, created, not_found, ok
from classroom_core.services import pages

bp = Blueprint("pages", __name__, url_prefix="/api/pages")


@bp.get("")
def list_pages():
    teacher = current_teacher()
    return ok({"pages": pages.list_pages(teacher["id"])})


@bp.post("")
def create_page():
    teacher = current_teacher()
    return created(pages.create_page(teacher, body()))


@bp.get("/<page_id>")
def get_page(page_id):
    teacher = current_teacher()
    page = pages.get_page(teacher["id"], page_id)
    return ok(page) if page else not_found("page not found")


@bp.put("/<page_id>")
def update_page(page_id):
    teacher = current_teacher()
    page = pages.update_page(teacher["id"], page_id, body())
    return ok(page) if page else not_found("page not found")


@bp.delete("/<page_id>")
def delete_page(page_id):
    teacher = current_teacher()
    if not pages.delete_page(teacher["id"], page_id):
        return not_found("page not found")
    return ok({"deleted": page_id})
