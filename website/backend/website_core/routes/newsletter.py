from flask import Blueprint, jsonify, request

from website_core.services import newsletter

bp = Blueprint("newsletter", __name__, url_prefix="/api")


@bp.post("/subscribe")
def subscribe():
    body = request.get_json(silent=True) or {}
    return jsonify(newsletter.subscribe(body)), 201
