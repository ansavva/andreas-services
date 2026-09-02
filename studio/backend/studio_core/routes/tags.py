"""The two tag vocabularies, and CRUD on them.

`?scope=file` is what a picture shows and what it is for; `?scope=template` is
what a prompt makes. They are separate lists on purpose — see `services/tags.py`
— and nothing here can address both at once.

There is no create. A tag exists because something carries it, so creating one
is tagging something, which is `PATCH /api/nodes/<id>` or a template write. What
this route adds is the two operations that cannot be done one item at a time:
renaming a word everywhere it appears, and removing it everywhere it appears.
"""

import logging

from flask import Blueprint, g, jsonify, request

from studio_core.errors import ValidationError
from studio_core.routes import support
from studio_core.services import tags as tag_service

logger = logging.getLogger(__name__)

bp = Blueprint("tags", __name__, url_prefix="/api")


@bp.get("/tags")
def list_tags():
    """One vocabulary, by name, with how many things carry each tag.

    The count is what makes a delete answerable before it happens: "remove
    `studio` from 43 files" is a different press from "remove it from 1".
    """
    held = support.memberships()
    support.member_of(g.library, held)
    scope = tag_service.clean_scope(request.args.get("scope"))
    return jsonify({"scope": scope, "tags": tag_service.used(g.library, scope)}), 200


@bp.patch("/tags/<path:name>")
def rename_tag(name: str):
    """Rename one tag everywhere in its scope.

    **A bulk write behind a single-item address**, which is the honest shape:
    the name is the identity, so there is nothing else to address, and renaming
    half the carriers would leave two tags where somebody believes there is one.
    """
    held = support.memberships()
    support.member_of(g.library, held)
    body = support.body()
    scope = tag_service.clean_scope(request.args.get("scope"))

    replacement = body.get("name")
    if not isinstance(replacement, str):
        raise ValidationError("name is required")
    changed = tag_service.rename(g.library, scope, name, replacement)
    return jsonify({"scope": scope, "name": replacement, "changed": changed}), 200


@bp.delete("/tags/<path:name>")
def delete_tag(name: str):
    """Take one tag off everything in its scope, which is what deleting it IS.

    The vocabulary is what is in use, so there is no row to remove afterwards
    and no state where the tag exists but nothing carries it.
    """
    held = support.memberships()
    support.member_of(g.library, held)
    scope = tag_service.clean_scope(request.args.get("scope"))
    changed = tag_service.remove(g.library, scope, name)
    return jsonify({"scope": scope, "name": name, "changed": changed}), 200
