"""The write half of the API: create, rename, move, copy, delete and edit.

Split from `routes/browse` rather than appended to it so that "what can this
service change" is answerable by reading one file. Every route here is behind
the same Cognito authorizer as the read routes.

**This used to say "there is no second tier of permission, because the pool is
admin-create-only and everyone in it is the owner of the library". Both halves
are now false.** Being in the pool grants nothing — `GET /api/libraries` can
answer with an empty list, and `before_request` refuses a caller who is in no
library — and membership carries a `role`, so "owner" is one value it can hold
rather than a description of everyone. The authorizer is still the outer gate;
what decides whether a *particular* node may be changed is the membership check,
and it happens in the API rather than in IAM. See `routes/libraries.py` and
`app_factory`'s request hook.

**These routes address the catalog now** (#316, #317, #319). What they take is
unchanged — `prefix`, `key`, `keys`, `destination` — because it was never an S3
key from the client's point of view: it is the slash-joined **name path** that
`GET /api/tree` hands back and that every share link ever issued is made of.
`services.manage` resolves it against the catalog one `NAME#` lookup per
segment. For material written before the catalog the two strings happen to be
equal, which is what let the read path move first (#309); nothing here assumes
it.

**So the split from `routes/nodes.py` is no longer about which storage a handler
talks to** — both write the same table — and `routes/nodes.py` says what it is
about instead: these routes take a name path, those take a node id, and #313
moves the SPA from the first to the second. The files stay apart until it does.

`g.library` is `before_request`'s, resolved and membership-checked once per
request. Nothing here checks it again, for `/api/resolve`'s reason: every walk
starts at that library's root and every step is a child of the step before it.

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

from flask import Blueprint, g, jsonify, request

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
    """Create an empty folder under a prefix. One row, no objects."""
    payload = _body()
    return jsonify(
        manage.create_folder(g.library, payload.get("prefix"), payload.get("name"))
    ), 201


@bp.patch("/object")
def rename_object():
    """Rename one file in place."""
    payload = _body()
    return jsonify(
        manage.rename_object(g.library, payload.get("key"), payload.get("name"))
    ), 200


@bp.patch("/folder")
def rename_folder():
    """Rename a folder. Everything beneath it comes along without moving."""
    payload = _body()
    return jsonify(
        manage.rename_folder(g.library, payload.get("prefix"), payload.get("name"))
    ), 200


@bp.post("/objects/move")
def move_objects():
    """Move one or many files into another folder.

    A POST rather than a PATCH because the request names a set of objects and a
    destination rather than patching one addressable resource — and because
    `PATCH /api/object` already means "rename", which is the operation this one
    exists to stay distinct from.
    """
    payload = _body()
    return jsonify(
        manage.move_objects(g.library, payload.get("keys"), payload.get("destination"))
    ), 200


@bp.post("/folder/move")
def move_folder():
    """Move a folder and everything beneath it under a different parent."""
    payload = _body()
    return jsonify(
        manage.move_folder(g.library, payload.get("prefix"), payload.get("destination"))
    ), 200


@bp.post("/objects/copy")
def copy_objects():
    """Copy one or many files into another folder, leaving the sources alone.

    The same body as `/objects/move` and a POST for the same reasons. 201 rather
    than 200 because something new exists afterwards, which is the one thing
    that distinguishes it from the move beside it.
    """
    payload = _body()
    return jsonify(
        manage.copy_objects(g.library, payload.get("keys"), payload.get("destination"))
    ), 201


@bp.patch("/text")
def update_text():
    """Overwrite a text file's contents. See the module docstring for the verb."""
    payload = _body()
    return jsonify(
        manage.update_text(g.library, payload.get("key"), payload.get("content"))
    ), 200


@bp.delete("/objects")
def delete_objects():
    """Delete one or many files.

    A body on a DELETE, which is unusual but well-defined and passed through
    intact by API Gateway's Lambda proxy integration. The alternative — repeated
    `?key=` parameters — runs into URL length limits on exactly the case this
    exists for, which is a grid selection of a few hundred files.
    """
    return jsonify(manage.delete_objects(g.library, _body().get("keys"))), 200


@bp.delete("/folder")
def delete_folder():
    """Delete a folder and everything beneath it."""
    prefix = _body().get("prefix") or request.args.get("prefix")
    return jsonify(manage.delete_folder(g.library, prefix)), 200
