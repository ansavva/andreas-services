"""Authenticated page endpoints, scoped to the calling teacher.

Every handler reads its teacher from the verified Cognito claims rather than
from anything in the request body, so one teacher cannot address another
teacher's pages by guessing an id.

A page's CONTENT does not pass through here. The browser uploads it straight to
S3 with presigned URLs and CloudFront serves it; what these routes do is sign
those uploads and move the files between the draft and live prefixes. See
``repositories/lessons``.
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


@bp.get("/<page_id>/files")
def list_files(page_id):
    """What she has uploaded for this page, whether or not it is published."""
    teacher = current_teacher()
    files = pages.draft_files(teacher["id"], page_id)
    return ok({"files": files}) if files is not None else not_found("page not found")


@bp.post("/<page_id>/uploads")
def start_upload(page_id):
    """Sign a PUT per file. The browser sends the bytes; this never sees them.

    Direct-to-S3 because a zipped worksheet with its images runs to tens of
    megabytes and API Gateway stops at 10MB — routing content through here
    would fail on exactly the files that matter most.
    """
    teacher = current_teacher()
    result = pages.start_upload(teacher["id"], page_id, body())
    return ok(result) if result else not_found("page not found")


@bp.post("/<page_id>/uploads/complete")
def finish_upload(page_id):
    """Called once the browser's PUTs have all succeeded."""
    teacher = current_teacher()
    result = pages.finish_upload(teacher["id"], page_id)
    return ok(result) if result else not_found("page not found")


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
