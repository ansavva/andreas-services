"""Subjects: a character or a location — a record, a bible, and the images that say what it is.

**One module builds both blueprints**, because a character and a location are
the same rows with a different bible. Each is `<KIND>#<id>` / `META`, with a
`LIB#<lib>` / `<KIND>#<id>` index row beside it, a root folder named by the id,
a validated `profile` map, and images under the root whose `default` tag says
which ones a generation is shown. Four things follow from that, for both:

* **A rename is one field on one row.** The name is a free-text label, the index
  row is keyed on the id, and the root folder is named by the id.
* **What a picture is and what it is for are tags on the file**, so nothing has
  to be renumbered or regrouped and no bytes move.
* **A description is on the file's row**, so writing twelve of them is twelve
  row writes rather than twelve rewrites of one document racing each other.
* **"Which projects involve this subject" has an answer**, and "every run that
  used it" is one query.

`routes/characters.py` and `routes/locations.py` each hold one `Subject` and
the blueprint this module builds from it. A route that has to know about one
kind — what its bible's sections are, what its CLI is called — reads the spec;
a route that has to know about two is in the wrong module.

## The two things this module decides rather than stores

**The profile schema.** `profile` is the bible: a handful of sections and one
paragraph, named by the spec. Which of a subject's pictures a generation is
shown is not in it — that is the `default` tag and a group tag on the node. The
sections are validated here — nowhere else in the service has an opinion about
the shape of a bible.

**What a model will actually be shown.** `GET /api/<kind>s/<id>/selection` is
a route rather than a function in each half of studio precisely so the CLI and
the SPA cannot disagree about it, and so the over-cap refusal happens in one
place. Slot N means "position N in the resolved selection".

## Hard rule #1 lives here too

No production character is named anywhere in this repository, and that includes
the S3 keys this module's uploads produce: an identity image is
`<kind>s/<id>/<node_id>.<ext>`, so a listing of the media bucket is a list of
UUIDs. **The catalog's folder tree says nothing either**: a subject's root
folder is named by its id, so the name lives on one row.
"""

import dataclasses
import logging

from flask import Blueprint, g, jsonify, request

from studio_core.errors import ConflictError, ValidationError
from studio_core.routes import projects as project_routes
from studio_core.routes import support
from studio_core import config
from studio_core.services import browse, catalog, keys, manage, profile_template, registry

logger = logging.getLogger(__name__)

#: What a selection asks for when nobody says otherwise.
DEFAULT_TAG = "default"

#: A selection is images. A `.json` beside them in the same folder carrying the
#: same tag is not something to hand a model.
SELECTABLE = "image"

#: The one paragraph every bible ends in — the same key for a character and a
#: location, deliberately. The word is "identity" because that is what studio
#: calls what a subject IS; a room has one as much as a person does, and one
#: key means one code path in the form, the CLI and the textblock route.
TEXT_BLOCK = "text_identity_block"


@dataclasses.dataclass(frozen=True)
class Subject:
    """Everything that differs between a character and a location.

    `kind` is the catalog's entity kind and `segment` the URL's plural —
    `/api/characters`. `sections` is what `clean_profile` admits; a section
    outside it is refused rather than stored. `identity_bearing` is the subset
    `GET .../textblock` hands back as raw material when nobody has authored
    the paragraph: the sections that say what the thing looks like, with the
    ones about medium or manner left out.

    `cli` is the `studio` command group a refusal names, because a person
    reading "see what it has" has to be told which command to type.
    """
    kind: str
    segment: str
    sections: tuple
    identity_bearing: tuple
    cli: str

    @property
    def noun(self) -> str:
        return self.kind


# **There is no cap table here.** `services/registry.py` is the registry, served
# at `GET /api/models`, and a second copy here would be a second answer to what
# a model accepts — one that drifts the moment a model is added.
#
# **A cap is refused rather than applied**: silently handing a model the first
# seven of eighteen references is a shoot whose result nobody can explain, so
# the request fails and the whole index comes back in the body so the caller
# can choose.


def clean_profile(spec: Subject, raw) -> dict:
    """A bible, validated by section.

    Validated as *sections* and not field by field, deliberately. What goes
    inside `face` or `space` is a description a person writes for a model to
    read, and a service that enforced its keys would be a service that refuses
    a subject somebody wanted to describe differently. What is enforced is the
    thing a client can get wrong without noticing: a section that is a string
    where a map belongs, which would make `PATCH .../profile` merge a paragraph
    over a structure.

    An absent profile is `{}` and not an error: `POST /api/<kind>s` takes one
    optionally, because a subject is created before anybody has written a word
    about it and `studio <kind> edit` is the next command either way.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("profile must be an object")

    unknown = sorted(set(raw) - set(spec.sections) - {TEXT_BLOCK})
    if unknown:
        raise ValidationError(f"profile has no section called {unknown[0]!r}")
    for section in spec.sections:
        if section in raw and not isinstance(raw[section], dict):
            raise ValidationError(f"profile.{section} must be an object")
    if TEXT_BLOCK in raw and not isinstance(raw[TEXT_BLOCK], str):
        raise ValidationError(f"profile.{TEXT_BLOCK} must be a string")
    return raw


def _node_in(record: dict, node_id: str, label: str) -> dict:
    """One node the request names, proved to be in the subject's own library.

    **Checked against the subject rather than against the caller**, and the
    difference matters: the caller may be in two libraries, and a `hero` or a
    reference pointing at a node in the *other* one would be a record that
    presigns bytes its own library does not hold.
    """
    node = catalog.node(node_id)
    if node["lib"] != record["lib"]:
        raise ValidationError(f"{label} names a node in another library")
    return node


def _hero(record: dict, nodes: dict[str, dict]) -> dict | None:
    """The card image, presigned, or nothing — `support.hero` says how."""
    return support.hero(nodes.get(record.get("hero") or ""), nodes)


def file_counts(records: list[dict]) -> dict[str, dict[str, int]]:
    """`entity id -> {files, default}`, batched then one branch query each.

    **Both numbers come out of one walk.** `counts.default` is the files under
    this subject carrying `default`, which the walk that counts files already
    has in hand.

    One `BatchGetItem` for the roots and then one `branch` query per subject,
    which is defensible for the reason a counter on the record is not: a library
    holds tens of characters, not thousands, and a stored number is a second
    thing for every upload, move, delete and re-tag to keep in step.

    **A truncated branch is counted as what was read, not refused.** `subtree`
    turns the cap into a `ValidationError` because both its callers are writes
    and a half-finished move is worse than none; this is a number next to a name
    in a list, and refusing to draw the list because one subject has a lot of
    files in it would be the wrong trade.
    """
    roots = catalog.records([record["root"] for record in records if record.get("root")])
    cap = config.max_folder_objects()
    counts = {}
    for record in records:
        root = roots.get(record.get("root"))
        if not root:
            counts[record["id"]] = {"files": 0, "default": 0}
            continue
        nodes, _truncated = catalog.branch(g.library, catalog.child_path(root), cap)
        # A poster is a derivative beside a reference, not a reference:
        # `browse._admits` hides it from the pool, and the count agrees.
        files = [node for node in nodes
                 if node.get("kind") == catalog.KIND_FILE and not node.get("poster_of")]
        counts[record["id"]] = {
            "files": len(files),
            "default": sum(1 for node in files if DEFAULT_TAG in (node.get("tags") or [])),
        }
    return counts


def _identity(record: dict, tags: list[str]) -> list[dict]:
    """The subject's images carrying EVERY one of `tags`, by name.

    One branch query under the subject's root — the same read `counts` makes —
    filtered on tags by the listing itself.

    **Ordered by name, and that is a decision rather than a leftover.** Order
    means nothing about a subject's pictures, but a payload hands a model
    `[Image1]` and `[Image2]`, so the selection needs *an* order and it has to
    be the same one twice. Name is the only property of a file that does not
    change when somebody re-uploads or re-tags it; `newest` would reshuffle a
    shoot for a reason that has nothing to do with the shoot.
    """
    listed = browse.entries(
        record["lib"],
        under=record["root"],
        depth=browse.DEPTH_ALL,
        kinds=SELECTABLE,
        tags=",".join(tags),
        raw_sort="name",
        page_size=str(browse.MAX_PAGE_SIZE),
    )
    return listed["entries"]


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0]


def _picked(spec: Subject, record: dict, tokens: list[str]) -> list[dict]:
    """Exactly the images named, in the order they were named.

    A token is a node id or a filename, with or without its extension — the three
    things somebody has in hand when they are looking at a listing.

    **A token matching nothing is a refusal.** Asking for pictures by name and
    being handed fewer is not a selection, it is a typo, and the next thing down
    the pipe spends money on it.
    """
    listed = browse.entries(
        record["lib"], under=record["root"], depth=browse.DEPTH_ALL,
        kinds=SELECTABLE, raw_sort="name", page_size=str(browse.MAX_PAGE_SIZE),
    )["entries"]
    by_id = {entry["id"]: entry for entry in listed}
    by_name: dict[str, dict] = {}
    for entry in listed:
        by_name.setdefault(entry["name"], entry)
        by_name.setdefault(_stem(entry["name"]), entry)

    chosen, missing = [], []
    for token in tokens:
        found = by_id.get(token) or by_name.get(token) or by_name.get(_stem(token))
        if found is None:
            missing.append(token)
        else:
            chosen.append(found)
    if missing:
        raise ValidationError(
            f"{record['name']} has no image called {missing[0]!r}. "
            f"See what it has: studio {spec.cli} images {record['id']}")
    return chosen


def _csv(raw: str | None) -> list[str]:
    """A comma-separated query parameter as a list, blanks dropped.

    Every filter on `GET /selection` takes a list; a bare `request.args.get`
    compared whole would make `?tag=a,b` ask for a tag literally named `a,b`.
    """
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def _must_match(spec: Subject, chosen: list, record: dict, asked: str) -> None:
    """A filter that selected nothing is a refusal, not an empty selection.

    Being handed no images is not a selection, and what runs next spends money
    on it.
    """
    if not chosen:
        raise ValidationError(
            f"no image of {record['name']} carries {asked}. "
            f"See what it has: studio {spec.cli} images {record['id']}"
        )


def _cap(args) -> int | None:
    """The ceiling this selection is measured against, or none at all.

    `?limit=` is explicit and wins. `?engine=` is resolved against the registry,
    a real lookup rather than a prefix match: two members of one family may
    legitimately differ, and an alias resolves properly. Neither given means no
    cap, and no refusal — a caller that did not say what it was feeding cannot
    be told it fed too much, and an unknown engine name is the same case.
    """
    raw = args.get("limit")
    if raw not in (None, ""):
        try:
            limit = int(raw)
        except (TypeError, ValueError):
            raise ValidationError("limit must be an integer") from None
        if limit < 1:
            raise ValidationError("limit must be positive")
        return limit

    engine = args.get("engine") or ""
    return registry.reference_cap(engine) if engine else None


def blueprint(spec: Subject) -> Blueprint:
    """The routes for one subject kind, under `/api/<segment>`.

    Built per kind rather than written twice. Every route below closes over
    `spec` for the three things that differ — the entity kind, the bible's
    sections, and the CLI noun a refusal names — and over nothing else.
    """
    bp = Blueprint(spec.segment, __name__, url_prefix="/api")
    KIND = spec.kind
    noun = spec.noun
    prefix = f"/{spec.segment}"

    def _subject(addressed: str, held: dict) -> dict:
        return support.entity_at(KIND, g.library, addressed, held)

    def _profile(raw) -> dict:
        return clean_profile(spec, raw)

    @bp.get(prefix)
    def list_subjects():
        """Every subject of this kind in the library.

        **One query for the index rows, one batched read for the records, one
        batched read for the heroes and one for the roots.** Both counts come
        out of ONE branch query per subject — `counts.default` is the files
        under it carrying the `default` tag, which the walk that counts files
        already has in hand.

        `?q=` filters on the name, in memory. A library holds tens of these,
        not thousands; an index for this would be a second thing to keep
        correct for a substring match a client could do itself.
        """
        held = support.memberships()
        support.member_of(g.library, held)

        records = catalog.entities_in(g.library, KIND)
        query = (request.args.get("q") or "").strip().lower()
        if query:
            records = [record for record in records
                       if query in (record.get("name") or "").lower()]

        heroes = support.with_posters(
            catalog.records([record["hero"] for record in records if record.get("hero")]))
        files = file_counts(records)
        listed = [
            {
                "id": record["id"],
                "name": record.get("name"),
                "hero": _hero(record, heroes),
                # The one pointer into the file tree, so a picker can open a
                # subject without reading its whole record first.
                "root": record.get("root"),
                "counts": files.get(record["id"], {"files": 0, "default": 0}),
                "updated": record.get("updated"),
            }
            for record in records
        ]
        # By name, then by id — which is what makes the order STABLE now that two
        # subjects may share a name. A sort on the name alone would let two rows
        # swap places between reads for no reason a person could see.
        listed.sort(key=lambda entry: ((entry["name"] or "").lower(), entry["id"]))
        return jsonify(listed), 200

    @bp.post(prefix)
    def create_subject():
        """A subject, its index row and its root folder — one write, no pools.

        **201, and the whole of it exists or none of it does.** Four items in one
        `TransactWriteItems`; a create that timed out is a create a person can
        simply repeat.

        **No starting layout.** A character used to be created holding
        `reference/`, `corpus/`, `seed/` and `archive/`; it no longer is.
        Nothing ever required them to exist, and `pool_folder` on the pipeline
        side already resolves-or-creates one by name the first time something
        is filed into it — see `services/layout.py`.

        **There is no 409.** A name is a free-text label and both keys are
        minted UUIDs, so nothing here can collide and there is nothing for a
        client to recover from.
        """
        body = support.body()
        held = support.memberships()
        support.member_of(g.library, held)

        root = catalog.library(g.library)["root_node"]
        # **Seeded from the blank bible when the body says nothing about one.**
        # A subject made in the app used to start with `{}` — a form with
        # nothing in it — where one made by the CLI started from the yaml
        # template. `profile: {}` is still `{}`: that is a client asking for
        # empty.
        seeded = "profile" not in body
        record = catalog.create_subject(
            KIND,
            g.library,
            root,
            name=keys.clean_label(body.get("name")),
            profile=(profile_template.blank_profile(KIND) if seeded
                     else _profile(body.get("profile"))),
        )
        return jsonify(record), 201, {"Location": f"/api/{spec.segment}/{record['id']}"}

    @bp.get(f"{prefix}/profile-template")
    def get_profile_template():
        """The blank bible and a hint per field — what a new section is added from.

        Shares a prefix with `/<segment>/<addressed>`; Werkzeug ranks a literal
        segment above a converter whatever the registration order, and a
        subject could never be addressed as `profile-template` anyway — ids are
        UUIDs.
        """
        return jsonify(profile_template.template(KIND))

    @bp.get(f"{prefix}/<addressed>")
    def get_subject(addressed: str):
        """The full record, `profile` included. Addressed by id."""
        held = support.memberships()
        record = _subject(addressed, held)
        heroes = support.with_posters(
            catalog.records([record["hero"]] if record.get("hero") else []))
        return jsonify(
            {
                **record,
                "hero_url": _hero(record, heroes),
                "counts": file_counts([record]).get(record["id"], {"files": 0, "default": 0}),
            }
        ), 200

    @bp.patch(f"{prefix}/<addressed>")
    def update_subject(addressed: str):
        """Rename or re-hero — under a `rev`.

        **A stale `rev` is a 409 and never a silent overwrite**: the condition is
        in the write, so there is no gap between a check and the write it guards.

        **A rename is just one of the assignments.** There is no name claim to
        collide with.
        """
        body = support.body()
        held = support.memberships()
        record = _subject(addressed, held)
        rev = support.revision(body, record)

        assignments = {}
        if "name" in body:
            assignments["name"] = keys.clean_label(body["name"])
        if "hero" in body:
            assignments["hero"] = (
                _node_in(record, body["hero"], "hero")["node_id"] if body["hero"] else None
            )

        try:
            updated = catalog.update_entity(KIND, record, rev, assignments)
        except ConflictError as conflict:
            return support.structured("conflict", str(conflict), 409)
        return jsonify(updated), 200

    @bp.patch(f"{prefix}/<addressed>/profile")
    def write_profile(addressed: str):
        """Replace the whole bible, or merge one section onto it.

        **Two operations on one address, told apart by which key the body
        carries** — `{profile, rev}` replaces wholesale and `{patch, rev}`
        merges. That is how `docs/ENTITY_MODEL.md` already distinguishes them,
        so nothing about the wire is invented here; what it replaces is a `PUT`
        and a `PATCH` on the same path, which cannot both be PATCH. See
        `app_factory.CORS_METHODS` for why the verb is not available.

        **Sending both is a 400 rather than a guess**, the same refusal
        `PATCH /api/nodes/<id>` makes about `name` with `parent`: the two have
        different outcomes and picking one silently is how somebody's paragraph
        disappears.

        **The merge is section-level, not deep.** Sending `{"patch": {"face":
        {...}}}` replaces the whole of `face` and touches nothing else. A deep
        merge would make *removing* a field impossible without a whole-document
        replace, which is the other half of this same route — so the shallow
        one is the useful half of the pair rather than a simplification of it.
        """
        body = support.body()
        held = support.memberships()
        record = _subject(addressed, held)
        rev = support.revision(body, record)

        replacing = "profile" in body
        merging = "patch" in body
        if replacing and merging:
            raise ValidationError("send profile to replace, or patch to merge, not both")
        if not replacing and not merging:
            raise ValidationError("send profile to replace, or patch to merge")

        if replacing:
            assignments = {"profile": _profile(body.get("profile"))}
        else:
            patch = _profile(body.get("patch"))
            assignments = {"profile": {**(record.get("profile") or {}), **patch}}

        try:
            updated = catalog.update_entity(KIND, record, rev, assignments)
        except ConflictError as conflict:
            return support.structured("conflict", str(conflict), 409)
        return jsonify(updated), 200

    @bp.delete(f"{prefix}/<addressed>")
    def delete_subject(addressed: str):
        """Remove a subject. `?files=keep|delete`, and refuses while anything links it.

        **Files are kept by default and the folder is orphaned into the library
        root.** The reverse default loses media to a typo, and nothing this
        service can do to S3 is undoable.

        **The refusal is the interesting half.** A project involving this
        subject and a run that used it both hold rows pointing at it, and those
        rows are what make "every run of this subject" answerable — deleting
        it out from under them leaves two questions with wrong answers.
        `?force=1` is the explicit "yes, and drop the links".
        """
        held = support.memberships()
        record = _subject(addressed, held)

        files = request.args.get("files") or "keep"
        if files not in ("keep", "delete"):
            raise ValidationError("files must be 'keep' or 'delete'")

        if request.args.get("force") not in ("1", "true"):
            projects = catalog.linked(record["id"], catalog.ENTITY_PROJECT)
            runs = catalog.linked(record["id"], catalog.ENTITY_RUN)
            if projects or runs:
                return support.structured(
                    "conflict",
                    f"{len(projects)} project(s) and {len(runs)} run(s) still name this "
                    f"{noun} — pass ?force=1 to delete it and its links anyway",
                    409,
                    projects=projects,
                    runs=runs,
                )

        manage.drain(g.library)
        result = catalog.delete_entity(KIND, record, delete_files=files == "delete")
        manage.release(g.library, result["blob_keys"], result["sweeps"])
        return jsonify({"id": record["id"], "files": files}), 200

    # ─────────────────────────── identity ───────────────────────────
    #
    # **There is no reference index and no `default_set`.** Which of a
    # subject's many pictures a generation gets shown is answered on the
    # picture: `default` is the handful, a group tag like `face` or `wide`
    # narrows it, and both travel with the picture through a move, a copy or
    # a rename because they are attributes of the node. Nothing can drift
    # from anything, because there is only one copy.

    @bp.get(f"{prefix}/<addressed>/selection")
    def selection(addressed: str):
        """The ordered images a model would actually be shown, and the cap they face.

        **The one route both halves of studio must agree on**, which is why it
        is a route rather than a function in each. Slot N means "position N in
        the resolved selection"; the resolving happens here, so the CLI and the
        SPA cannot disagree about what a model was given.

        Two sources. `pick` names images; anything else is tags, and no tags at
        all means `default`. A group is a tag: `?tag=default,face` is the face
        images a character sends, `?tag=default,wide` a location's wides.

        **A filter that matches nothing is refused, never answered with an
        empty list.** Asking for images and being handed none is a typo, not a
        selection, and the next thing down the pipe spends money on it.

        **Over-cap is refused with the candidates in the body, never
        truncated.** Handing a model the first seven of eighteen silently is a
        shoot whose result nobody can explain afterwards. The refusal carries
        every candidate so the caller can choose rather than guess.
        """
        held = support.memberships()
        record = _subject(addressed, held)

        tags = _csv(request.args.get("tag"))
        pick = _csv(request.args.get("pick"))

        if pick:
            source = "pick"
            chosen = _picked(spec, record, pick)
        else:
            source = "tag" if tags else "default"
            asked = tags or [DEFAULT_TAG]
            chosen = _identity(record, asked)
            _must_match(spec, chosen, record, " + ".join(asked))

        cap = _cap(request.args)
        if cap is not None and len(chosen) > cap:
            return support.structured(
                "over_cap",
                f"{len(chosen)} images match; the cap is {cap}",
                409,
                index=[
                    {
                        "node": entry["id"],
                        "name": entry["name"],
                        "tags": entry.get("tags") or [],
                        "description": entry.get("description"),
                    }
                    for entry in chosen
                ],
            )

        return jsonify(
            {
                "selection": [
                    {
                        "slot": slot,
                        "node": entry["id"],
                        # A person reviewing a payload has to know which
                        # picture is `[Image3]`, and a node id does not say.
                        "name": entry["name"],
                        "tags": entry.get("tags") or [],
                        "description": entry.get("description"),
                        "url": entry.get("url"),
                    }
                    for slot, entry in enumerate(chosen, start=1)
                ],
                "cap": cap,
                "source": source,
            }
        ), 200

    @bp.get(f"{prefix}/<addressed>/textblock")
    def textblock(addressed: str):
        """The pasteable identity paragraph, on its own so a prompt can fetch it.

        Both keys are always present. A caller branches on `text` being empty,
        which is one rule; `raw` appearing only sometimes would be a second one.

        **The template's unfilled `<>` counts as absent**, and that decision is
        made here rather than in each client. Otherwise a subject created from
        the blank template and never written up hands one caller the raw
        sections and another a literal `<>` — which is the paragraph landing in
        a prompt.

        `raw` is the identity-bearing sections — for a character the ones that
        say what it looks like, for a location the ones that say what is fixed
        and where the light comes from — with medium and manner left out,
        because a text-only engine is being told what the subject LOOKS like.
        """
        held = support.memberships()
        record = _subject(addressed, held)
        profile = record.get("profile") or {}
        authored = (profile.get(TEXT_BLOCK) or "").strip()
        if authored.startswith("<"):
            authored = ""
        raw = {} if authored else {
            section: profile[section] for section in spec.identity_bearing
            if profile.get(section)
        }
        return jsonify({"id": record["id"], "text": authored, "raw": raw}), 200

    @bp.get(f"{prefix}/<addressed>/runs")
    def subject_runs(addressed: str):
        """Every run that used this subject, newest first.

        One `by-sk` query for the ids and one batched read for the envelopes.
        """
        held = support.memberships()
        record = _subject(addressed, held)
        return jsonify({"runs": catalog.runs_using(record["id"]), "cursor": None}), 200

    @bp.get(f"{prefix}/<addressed>/projects")
    def subject_projects(addressed: str):
        """Every project that involves this subject.

        **The same rows `GET /api/projects` sends**, from the one builder in
        `routes/projects.py`, so the SPA draws them with the card it draws every
        other project list with.
        """
        held = support.memberships()
        record = _subject(addressed, held)

        project_ids = catalog.linked(record["id"], catalog.ENTITY_PROJECT)
        found = catalog.entities_by_id(catalog.ENTITY_PROJECT, project_ids)
        return jsonify(project_routes.summary_rows(list(found.values()))), 200

    return bp
