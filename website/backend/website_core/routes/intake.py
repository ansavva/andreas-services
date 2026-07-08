from flask import Blueprint, jsonify, request

from website_core.services import intake

bp = Blueprint("intake", __name__, url_prefix="/api")


@bp.post("/intake")
def create_submission():
    body = request.get_json(silent=True) or {}
    item = intake.create_submission(body, source_page=body.get("source_page"))
    return jsonify(item), 201


@bp.get("/admin/submissions")
def list_submissions():
    return jsonify(
        intake.list_submissions(
            limit=request.args.get("page_size", 50),
            cursor=request.args.get("cursor"),
        )
    ), 200
