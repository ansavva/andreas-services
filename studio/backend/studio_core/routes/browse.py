from flask import Blueprint, jsonify, request

from studio_core.services import browse

bp = Blueprint("browse", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.get("/tree")
def tree():
    """Immediate contents of one folder."""
    return jsonify(browse.list_folder(request.args.get("prefix"))), 200


@bp.get("/reel")
def reel():
    """Images and videos beneath a prefix, recursively and paginated."""
    return jsonify(
        browse.reel_items(
            request.args.get("prefix"),
            request.args.get("cursor"),
            request.args.get("page_size"),
        )
    ), 200


@bp.get("/asset")
def asset():
    """A fresh presigned URL for one object — refreshes and downloads."""
    return jsonify(
        browse.asset_url(request.args.get("key"), request.args.get("disposition"))
    ), 200


@bp.get("/text")
def text():
    """A JSON/markdown/text object's contents, for the read-only viewer."""
    return jsonify(browse.text_object(request.args.get("key"))), 200
