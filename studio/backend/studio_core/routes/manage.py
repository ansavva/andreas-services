"""The write half of the API: create, rename, move, delete and edit.

Split from `routes/browse` rather than appended to it so that "what can this
service change" is answerable by reading one file. Every route here is behind
the same Cognito authorizer as the read routes — there is no second tier of
permission, because the pool is admin-create-only and everyone in it is the
owner of the library.

**Every verb used here is already in the CORS method list, and that is not an
accident.** The browser's preflight is answered by API Gateway's MOCK
integration, not by Flask, so a verb this file introduces has to be added in
four places at once (`app_factory`, the preflight, and both gateway responses in
`modules/api_gateway`) or it fails as an opaque CORS error with no status. So
saving a text file is `PATCH /api/text` rather than the `PUT` you might expect:
PATCH is already allowed everywhere, PUT is allowed nowhere, and the difference
between the two verbs here is worth less than a four-file agreement to keep in
step. Add PUT properly if a future route genuinely wants it.
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


@bp.post("/objects/move")
def move_objects():
    """Move one or many objects into another folder.

    A POST rather than a PATCH because the request names a set of objects and a
    destination rather than patching one addressable resource — and because
    `PATCH /api/object` already means "rename", which is the operation this one
    exists to stay distinct from.
    """
    payload = _body()
    return jsonify(manage.move_objects(payload.get("keys"), payload.get("destination"))), 200


@bp.post("/folder/move")
def move_folder():
    """Move a folder and everything beneath it under a different parent."""
    payload = _body()
    return jsonify(manage.move_folder(payload.get("prefix"), payload.get("destination"))), 200


@bp.post("/favorites")
def add_favorites():
    """Copy one or many objects into their own project's favorites folder.

    A POST with no destination, which is the shape of the operation: the folder
    is derived from each key rather than supplied, so this route cannot be talked
    into putting a file somewhere else the way `POST /api/objects/move` can. 201
    for the same reason `POST /api/folder` is — something new exists afterwards.
    """
    return jsonify(manage.favorite_objects(_body().get("keys"))), 201


@bp.patch("/text")
def update_text():
    """Overwrite a text file's contents. See the module docstring for the verb."""
    payload = _body()
    return jsonify(manage.update_text(payload.get("key"), payload.get("content"))), 200


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
