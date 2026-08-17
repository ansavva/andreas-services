"""The write half of the API: create, rename and delete.

Split from `routes/browse` rather than appended to it so that "what can this
service change" is answerable by reading one file. Every route here is behind
the same Cognito authorizer as the read routes — there is no second tier of
permission, because the pool is admin-create-only and everyone in it is the
owner of the library.
"""

from flask import Blueprint, jsonify, request

from studio_core.services import manage

bp = Blueprint("manage", __name__, url_prefix="/api")


def _body() -> dict:
    """The JSON body, or an empty dict.

    `silent=True` because a malformed body should surface as the missing-field
    ValidationError the service raises — a 400 naming the field beats Flask's
    generic parse failure.
    """
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


@bp.post("/folder")
def create_folder():
    """Create an empty folder under a prefix."""
    payload = _body()
    return jsonify(manage.create_folder(payload.get("prefix"), payload.get("name"))), 201


@bp.patch("/object")
def rename_object():
    """Rename one object in place."""
    payload = _body()
    return jsonify(manage.rename_object(payload.get("key"), payload.get("name"))), 200


@bp.patch("/folder")
def rename_folder():
    """Rename a folder and everything beneath it."""
    payload = _body()
    return jsonify(manage.rename_folder(payload.get("prefix"), payload.get("name"))), 200


@bp.delete("/objects")
def delete_objects():
    """Delete one or many objects.

    A body on a DELETE, which is unusual but well-defined and passed through
    intact by API Gateway's Lambda proxy integration. The alternative — repeated
    `?key=` parameters — runs into URL length limits on exactly the case this
    exists for, which is a grid selection of a few hundred files.
    """
    return jsonify(manage.delete_objects(_body().get("keys"))), 200


@bp.delete("/folder")
def delete_folder():
    """Delete a folder and everything beneath it."""
    prefix = _body().get("prefix") or request.args.get("prefix")
    return jsonify(manage.delete_folder(prefix)), 200
