"""An in-memory studio API: entities, nodes, and presigned bytes onto moto.

**This replaces a shim that pretended a node's id was its S3 key.** That fiction
was cheap and it was load-bearing in the wrong direction: the suite monkeypatched
`adapters/store` operation by operation, so every test asserted what the *store*
was asked for and none asserted what the *CLI actually sends*. A route name, a
body field or a query parameter could be wrong in every domain module at once and
the suite would stay green — which is precisely the failure mode a restructure
produces, and precisely what `pipeline/tests/` exists to catch.

So this fake sits one layer lower, at `adapters.api.request`. Everything above it
runs for real: `adapters/entities.py` builds the route and the body, `store.py`
walks the tree by id, and the domain modules go through both. The seam is HTTP,
which is the seam the backend is on the other side of, and the shapes here are
`docs/ENTITY_MODEL_EXAMPLE.md` §2 read literally.

## What is real and what is not

**Real.** Node ids are `node-<uuid4>`, entity ids are `<kind>-<uuid4>`, and
nothing derives one from anything. A name is unique among a folder's children and
a duplicate is a 409. A slug is unique per entity kind per library and a duplicate
is a 409. `rev` is compare-and-swap and a stale one is a 409. Reference `order`
is gapped by 1000 and `after` takes the midpoint. Deleting a node that is an
entity's `root` is refused.

**Not real.** There is no authorisation, no library membership check, no
pagination and no cursor. Every one of those is the backend's to enforce and the
smoke suite's to exercise; imitating them here would test this file.

## The bytes

`store` PUTs and GETs presigned URLs with `urllib`, which has nothing to talk to
in-process. So the signed URL is `memory://<blob_key>` and `store._put` /
`store._fetch` are pointed at the same moto bucket the old fixture used. Bytes
stay real — `curate dedupe` hashes them, `frames` runs ffmpeg over them — and only
the transport is short-circuited.

## Blob keys

`<owner_kind>/<owner_id>/<node_id>.<ext>`, stamped once at creation from the
owner the parent already resolves to, never parsed and never re-derived. It is
here rather than left as an unmodelled detail because `catalog reseat` exists to
fix drift in exactly this string, and a fake that ignored the scheme would let
the reseat tests assert against nothing.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import itertools
import json
import mimetypes
import re
import urllib.parse
import uuid

from studio_pipeline import STUDIO_DIR
from studio_pipeline.adapters import api

BUCKET = "studio-prod-media-us-east-1"

#: Content types that earn the sparse reel key (D5). Folders, entity rows and
#: documents stay out of `by-recent` entirely, which is the pollution the
#: attribute was introduced to end.
REEL_TYPES = ("image/", "video/")

ORDER_GAP = 1000


@functools.lru_cache(maxsize=1)
def _backend_service(name: str):
    """A backend `services/<name>.py`, loaded by path. **Not a copy of it.**

    Two modules are shared this way — `storyboard` and `prompt` — and both are
    written to import neither Flask nor boto3 so that a unit test needs neither.
    What they hold is judgement the API now owns: whether a plan is coherent,
    whether a prompt will render well. A fake that approximated either would let
    the CLI's tests pass against answers the real service does not give, which is
    the failure this fake exists to prevent. `_plan_digest` above is the
    cautionary case — a second implementation with a comment admitting nothing
    holds the two together.

    Imported through `backend/` on `sys.path` rather than by file path, because
    `prompt` reads the registry and a path-loaded module cannot resolve
    `studio_core.services.registry` for itself. `studio_core/__init__.py`,
    `services/__init__.py` and `errors.py` are all empty or import-free, so this
    reaches nothing heavier than `json` and `pathlib`.

    If either module ever grows a dependency this fails loudly at import, which
    is the right way for it to stop working.
    """
    import importlib
    import sys

    root = str(STUDIO_DIR / "backend")
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(f"studio_core.services.{name}")


def _storyboard():
    """The BACKEND's plan module, loaded by path. **Not a copy of it.**

    Normalising a plan, validating it and deriving a shot's status are the API's
    now, so a fake that did not do them would let the CLI's tests pass against
    shapes the real service refuses — which is the failure this fake exists to
    prevent. `_plan_digest` above is the cautionary case: a second implementation
    with a comment admitting nothing holds the two together.

    Loaded from the file rather than imported as a package because the pipeline
    does not depend on the backend and must not start to. `services/storyboard.py`
    has no imports of its own beyond `__future__`, so this pulls in no Flask, no
    boto3, and nothing that would make a unit test need either. If that ever
    stops being true this will fail loudly at import, which is the right way for
    it to stop working.
    """
    return _backend_service("storyboard")


@functools.lru_cache(maxsize=1)
def _committed_registry() -> dict:
    """`backend/studio_core/models.json`, each entry carrying its own key.

    Reached through `STUDIO_DIR` rather than a count of `".."` segments, for the
    reason that constant exists: a count is right for exactly one file's depth.
    """
    path = STUDIO_DIR / "backend" / "studio_core" / "models.json"
    models = json.loads(path.read_text())["models"]
    return {key: {**entry, "key": key} for key, entry in models.items()}


class FakeError(Exception):
    """Raised with an HTTP status so `_dispatch` can turn it into an api error."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


#: The statuses that come before a submission. **Mirrors
#: `catalog.UNSUBMITTED_RUN_STATUSES`**, and a copy rather than an import because
#: the pipeline does not depend on the backend package and never has.
UNSUBMITTED = frozenset({"draft", "approved", "discarded"})

#: Every word a run's status may be. **The fake validated none of them**, which
#: is how `studio runs adopt` came to write `adopted` — a status the real route
#: rejects with a 400 — and pass its tests for as long as it has existed.
RUN_STATUSES = frozenset({"draft", "approved", "pending", "running", "succeeded",
                          "failed", "cancelled", "discarded", "adopted"})


def _plan_digest(plan, sends) -> str:
    """A hash over what a person approves: the plan AND the ordered images.

    **A second implementation of `catalog.plan_digest`, and it has to agree with
    it.** Nothing can hold the two together automatically — the pipeline does not
    import the backend, which is the same reason `derive.extension` is a copy of
    `keys.extension` — so the shape is stated in both places and the integration
    suite is what actually exercises the real one.

    What it hashes is the reason it exists: the sends by `(field, role, node)` in
    order, so reordering two references is a real edit, and `source` excluded, so
    describing an image's provenance more accurately later does not void an
    approval nobody's payload changed.
    """
    payload = {
        "plan": plan or {},
        "sends": [{"field": s.get("field"), "role": s.get("role"),
                   "node": s.get("node")} for s in sends or []],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def _fingerprint(model, plan, sends) -> str:
    """`catalog.submission_fingerprint`, restated for the same reason as above.

    Derived from `_plan_digest` rather than hashed independently, which is what
    the service does — so if the two digests agree, these agree too, and there
    is one thing to keep in step rather than two.
    """
    material = f"{model or ''}\n{_plan_digest(plan, sends)}"
    return "sha256:" + hashlib.sha256(material.encode()).hexdigest()[:32]


def _placeholder_image() -> bytes:
    """A real, decodable image that is visibly not a render.

    Real because the pipeline does real work on outputs — `contact_sheet` builds
    sheets from them, `frames` decodes them, `curate dedupe` hashes them — and
    magic bytes with a PNG header on the front fail all of that in ways that
    look like pipeline bugs. Visibly a placeholder because a fake left on has to
    be obvious on sight.

    Lifted verbatim from `adapters/replicate.py`'s fake, which is deleted. The
    provider client left this package; the property it defended did not.
    """
    import io

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (512, 512), (255, 0, 220))
    draw = ImageDraw.Draw(image)
    for offset in range(-512, 512, 64):
        draw.line([(offset, 0), (offset + 512, 512)], fill=(0, 0, 0), width=8)
    draw.text((16, 16), "STUDIO FAKE\nnot a render", fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _now(counter=itertools.count()) -> str:
    """A monotonic ISO timestamp with microsecond resolution.

    Monotonic rather than `datetime.now()`, and this is not cosmetic: `rev` and
    `updated` are what optimistic concurrency is checked on, and two writes in
    the same microsecond would make a stale-write test pass by accident. The
    counter guarantees strict ordering without a sleep.
    """
    return (dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
            + dt.timedelta(microseconds=next(counter))).isoformat()


def _ext(name: str) -> str:
    _, _, tail = name.rpartition(".")
    return f".{tail}" if tail and tail != name else ""


class FakeApi:
    """One library, its tree, and its entity records."""

    def __init__(self, s3) -> None:
        self.s3 = s3
        self.lib = "lib-" + str(uuid.uuid4())
        self.nodes: dict[str, dict] = {}
        self.characters: dict[str, dict] = {}
        self.projects: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.scenes: dict[str, dict] = {}
        self.movies: dict[str, dict] = {}
        #: char_id -> [entry], each naming a node id. The `REF#` rows.
        self.refs: dict[str, list[dict]] = {}
        #: scene_id -> [shot]. The `SHOT#` rows.
        self.shots: dict[str, list[dict]] = {}
        self.terms: list[dict] = []
        #: The reference spec, as the two row classes the catalog keeps it in.
        self.spec_blocks: dict[str, str] = {}
        self.spec_angles: dict[str, dict] = {}
        #: render-<uuid> -> the job row. The `RENDER#` rows.
        self.renders: dict[str, dict] = {}
        #: Set it and `POST /api/renders` refuses. The seam that proves a dry
        #: run enqueues NOTHING, exactly as `submits_refused` proves it bills
        #: nothing — "no render happened" is stronger than "the render was
        #: harmless", and a fake would answer one perfectly happily.
        self.renders_refused: str | None = None

        # ── the submission knobs ────────────────────────────────────────────
        #
        # Three, and each replaces a `monkeypatch.setattr` that used to reach
        # into `adapters/replicate.py`. That module is deleted: the CLI holds no
        # provider client to stub, so what a test controls now is how the API
        # behaves when asked to submit.

        #: run id -> what its prediction will do, applied by `reconcile`. A
        #: submission does not settle at the moment it is made, because the real
        #: one does not either — something else closes the run afterwards, and a
        #: fake that skipped that would leave `submit.wait_for` untested.
        self.pending: dict[str, str] = {}

        #: What the NEXT submission's prediction will do. Reset to `succeeded`
        #: after each use, so a test asking for one failure gets exactly one.
        self.next_outcome = "succeeded"

        #: What `POST /runs/<id>/submit` reports as the closing mechanism.
        #: `poll` by default, which is what a machine with no callback receiver
        #: sees and what makes `wait_for` drive `reconcile` deterministically.
        #: A test exercising the webhook branch sets `"webhook"`.
        self.callback = "poll"

        #: **"Nothing may submit", which is stronger than "nothing may bill".**
        #: `test_board` and `test_turnaround` assert that a dry run does not
        #: reach the provider AT ALL — the fake would answer a submission
        #: perfectly happily, and a board that submitted on a dry run would pass
        #: every other check in those files.
        self.submits_refused = False

        #: Raw keys with no node, reached by `GET /api/asset` — the angle images.
        self.root = self._node(None, "", "folder")
        self.root["path"] = "/"

    # ── the tree ────────────────────────────────────────────────────────────

    def _node(self, parent_id: str | None, name: str, kind: str, **extra) -> dict:
        node_id = "node-" + str(uuid.uuid4())
        parent = self.nodes.get(parent_id) if parent_id else None
        record = {
            "id": node_id, "node_id": node_id, "parent_id": parent_id,
            "lib": self.lib, "name": name, "kind": kind,
            "path": (parent["path"] + parent_id + "/") if parent else "/",
            "created_at": _now(), "updated_at": _now(), **extra,
        }
        self.nodes[node_id] = record
        return record

    def _children(self, node_id: str) -> list[dict]:
        return sorted((n for n in self.nodes.values() if n["parent_id"] == node_id),
                      key=lambda n: n["name"])

    def _child(self, node_id: str, name: str) -> dict | None:
        return next((n for n in self._children(node_id) if n["name"] == name), None)

    def _owner(self, node_id: str | None) -> dict | None:
        """Walk up to the nearest entity root. Derived, never stored on the file."""
        while node_id:
            node = self.nodes.get(node_id)
            if node is None:
                return None
            entity = node.get("entity")
            if entity:
                for kind, table in (("character", self.characters),
                                    ("project", self.projects)):
                    if entity in table:
                        return {"kind": kind, "id": entity,
                                "slug": table[entity]["slug"]}
            node_id = node["parent_id"]
        return None

    def _blob_key(self, node: dict) -> str:
        owner = self._owner(node["parent_id"])
        if owner is None:
            prefix = f"libraries/{self.lib}"
        else:
            prefix = f"{'characters' if owner['kind'] == 'character' else 'projects'}/{owner['id']}"
        return f"{prefix}/{node['id']}{_ext(node['name'])}"

    def _view(self, node: dict) -> dict:
        """What a node route returns. **No `blob_key`, no `path`** — as today."""
        view = {"id": node["id"], "name": node["name"], "kind": node["kind"],
                "created_at": node["created_at"], "updated_at": node["updated_at"]}
        # `checksum` is the MD5 of the bytes — the ETag of the single PUT that
        # wrote them. It is in the view rather than fetched per node because
        # `curate dedupe` compares whole pools, and the alternative was a
        # download each. Mirrors `routes/support.VIEW_FIELDS`.
        for field in ("size", "content_type", "checksum", "description", "tags"):
            if node.get(field) is not None:
                view[field] = node[field]
        owner = self._owner(node["id"])
        if owner:
            view["owner"] = owner
        return view

    def _create_node(self, parent_id: str, name: str, kind: str) -> dict:
        if parent_id not in self.nodes:
            raise FakeError(404, f"no such parent: {parent_id}")
        if self._child(parent_id, name):
            raise FakeError(409, f"{name!r} already exists here")
        node = self._node(parent_id, name, kind)
        if kind == "file":
            node["blob_key"] = self._blob_key(node)
        return node

    def _resolve(self, path: str) -> dict:
        node = self.root
        for segment in [p for p in (path or "").strip("/").split("/") if p]:
            found = self._child(node["id"], segment)
            if found is None:
                raise FakeError(404, f"no such path: {path}")
            node = found
        return node

    def _delete_node(self, node_id: str) -> int:
        node = self.nodes.get(node_id)
        if node is None:
            return 0
        for entity_table in (self.characters, self.projects):
            for entity in entity_table.values():
                if entity.get("root") == node_id:
                    raise FakeError(
                        409,
                        f"{node['name']!r} is {entity['slug']}'s root folder; "
                        "delete the entity instead")
        removed = 0
        for child in list(self._children(node_id)):
            removed += self._delete_node(child["id"])
        if node.get("blob_key"):
            self.s3.delete_object(Bucket=BUCKET, Key=node["blob_key"])
        del self.nodes[node_id]
        return removed + 1

    # ── entity helpers ──────────────────────────────────────────────────────

    def _entity(self, table: dict, ref: str, what: str) -> dict:
        if ref.startswith("slug:"):
            slug = ref[len("slug:"):]
            found = next((e for e in table.values() if e["slug"] == slug), None)
        else:
            found = table.get(ref)
        if found is None:
            raise FakeError(404, f"no such {what}: {ref}")
        return found

    def _claim(self, table: dict, slug: str, what: str) -> None:
        if any(e["slug"] == slug for e in table.values()):
            raise FakeError(409, f"a {what} called {slug!r} already exists")

    def _bump(self, record: dict, rev: int | None) -> None:
        """Compare-and-swap on `rev`, which is what closed the `updated_at` window."""
        if rev is not None and int(rev) != int(record["rev"]):
            raise FakeError(409, f"the record was changed by someone else "
                                 f"(rev {rev} → {record['rev']}); re-read and retry")
        record["rev"] += 1
        record["updated"] = _now()

    def _layout(self, root_id: str, names) -> None:
        for name in names:
            self._create_node(root_id, name, "folder")

    def _folder_under(self, root_id: str, name: str) -> dict:
        """The conventional folder, made if someone renamed or deleted it.

        Self-healing on purpose: a route that cannot find its conventional
        folder makes one and never guesses, and every record that already
        exists still names its own folder node id.
        """
        return self._child(root_id, name) or self._create_node(root_id, name, "folder")

    # ── dispatch ────────────────────────────────────────────────────────────

    def request(self, method: str, route: str, payload=None, **params):
        """**Both sides of this boundary are round-tripped through JSON.**

        A real call serializes the request and parses the response, so the caller
        and the service never share an object: whatever the caller sends is a
        snapshot, and whatever comes back is new. This fake passed dicts straight
        through in both directions, so a caller that mutated a dict it had already
        handed over — or one it got back — saw its change land in the service's
        own state for free.

        That is not a smaller version of the real behaviour, it is the opposite
        of it, and it hid a live bug: `scenes board` captured its panels before
        the submit loop, and after the first write the real API's response had
        replaced them with fresh dicts, so twelve of thirteen rendered panels
        were recorded into orphans. Under this fake all thirteen "worked".
        """
        params = {k: v for k, v in params.items() if v is not None}
        try:
            return json.loads(json.dumps(
                self._dispatch(method, route, json.loads(json.dumps(payload or {})), params),
                default=str))
        except FakeError as error:
            status = error.status
            message = str(error)
            if status == 404:
                raise api.NotFound(message, status) from error
            if status == 409:
                raise api.Conflict(message, status) from error
            if status == 403:
                raise api.Forbidden(message, status) from error
            raise api.ApiError(message, status) from error

    def _dispatch(self, method, route, body, params):
        # **No `/api` route takes PUT, so the fake refuses it everywhere.**
        #
        # `docs/ENTITY_MODEL.md` spells six whole-collection replaces as PUT and
        # the service registers PATCH for all six — see `app_factory` for why the
        # verb is not available. The adapter sent PUT to every one of them and
        # this fake answered, so the suite proved the adapter agreed with itself
        # rather than with the API. One refusal here is worth more than six
        # handlers each remembering to make it.
        if method == "PUT":
            raise FakeError(405, f"PUT {route}: no /api route takes PUT — use PATCH")
        for pattern, handler in self._routes():
            match = re.fullmatch(pattern, route)
            if match:
                return handler(method, body, params, *match.groups())
        raise FakeError(404, f"no route {method} {route}")

    def _routes(self):
        return [
            (r"/api/libraries", self._r_libraries),
            (r"/api/models", self._r_models),
            (r"/api/prompt", self._r_prompt),
            (r"/api/models/(.+)/schema", self._r_model_schema),
            (r"/api/models/(.+)/readme", self._r_model_readme),
            (r"/api/models/(.+)", self._r_model),
            (r"/api/resolve", self._r_resolve),
            (r"/api/asset", self._r_asset),
            (r"/api/nodes", self._r_nodes),
            (r"/api/nodes/move", self._r_node_move),
            (r"/api/nodes/copy", self._r_node_copy),
            (r"/api/nodes/([^/]+)/download-url", self._r_download_url),
            (r"/api/nodes/([^/]+)/upload-url", self._r_upload_url),
            (r"/api/nodes/([^/]+)/confirm-upload", self._r_confirm),
            (r"/api/nodes/([^/]+)/text", self._r_text),
            (r"/api/nodes/([^/]+)/owner", self._r_node_owner),
            (r"/api/nodes/([^/]+)", self._r_node),
            (r"/api/characters", self._r_characters),
            (r"/api/characters/([^/]+)/references", self._r_references),
            (r"/api/characters/([^/]+)/references/([^/]+)", self._r_reference),
            (r"/api/characters/([^/]+)/default-set", self._r_default_set),
            (r"/api/characters/([^/]+)/selection", self._r_selection),
            (r"/api/characters/([^/]+)/textblock", self._r_textblock),
            (r"/api/characters/([^/]+)/profile", self._r_profile),
            (r"/api/characters/([^/]+)/runs", self._r_character_runs),
            (r"/api/characters/([^/]+)/projects", self._r_character_projects),
            (r"/api/characters/([^/]+)", self._r_character),
            (r"/api/projects", self._r_projects),
            (r"/api/projects/([^/]+)/characters", self._r_project_characters),
            (r"/api/projects/([^/]+)/inputs", self._r_project_inputs),
            (r"/api/projects/([^/]+)/runs", self._r_project_runs),
            (r"/api/projects/([^/]+)/scenes", self._r_project_scenes),
            (r"/api/projects/([^/]+)/movies", self._r_project_movies),
            (r"/api/projects/([^/]+)", self._r_project),
            (r"/api/runs", self._r_runs),
            (r"/api/runs/resolve", self._r_resolve_run),
            (r"/api/runs/([^/]+)/outputs", self._r_run_outputs),
            (r"/api/runs/([^/]+)/response", self._r_run_response),
            (r"/api/runs/([^/]+)/plan", self._r_run_plan),
            (r"/api/runs/([^/]+)/sends", self._r_run_sends),
            (r"/api/runs/([^/]+)/approve", self._r_run_approve),
            (r"/api/runs/([^/]+)/submit", self._r_run_submit),
            (r"/api/runs/([^/]+)/reconcile", self._r_run_reconcile),
            (r"/api/runs/([^/]+)", self._r_run),
            (r"/api/scenes", self._r_scenes),
            (r"/api/scenes/([^/]+)/shots", self._r_shots),
            (r"/api/scenes/([^/]+)/shots/([^/]+)", self._r_shot),
            (r"/api/scenes/([^/]+)/output", self._r_scene_output),
            (r"/api/scenes/([^/]+)", self._r_scene),
            (r"/api/movies", self._r_movies),
            (r"/api/movies/([^/]+)/scenes", self._r_movie_scenes),
            (r"/api/movies/([^/]+)/output", self._r_movie_output),
            (r"/api/movies/([^/]+)", self._r_movie),
            (r"/api/renders", self._r_renders),
            (r"/api/renders/([^/]+)", self._r_render),
            (r"/api/images/convert", self._r_image_convert),
            (r"/api/images/crop", self._r_image_crop),
            (r"/api/phrasebook", self._r_phrasebook),
            (r"/api/phrasebook/([^/]+)/([^/]+)", self._r_phrasebook_term),
            (r"/api/reference-spec", self._r_reference_spec),
            (r"/api/reference-spec/blocks/([^/]+)", self._r_spec_block),
            (r"/api/reference-spec/angles/([^/]+)", self._r_spec_angle),
        ]

    # ── node routes ─────────────────────────────────────────────────────────

    def _r_prompt(self, method, body, params):
        """`POST /api/prompt` — the backend's own assembler, over this library."""
        if method != "POST":
            raise FakeError(405, f"{method} /api/prompt")
        service = _backend_service("prompt")
        engine = body.get("engine") or "seedance"
        if engine not in service.engines():
            raise FakeError(400, f"unknown engine {engine!r}")
        if not isinstance(body.get("object"), dict):
            raise FakeError(400, "object must be an object")
        return service.assemble(
            body["object"], engine,
            emit=body.get("emit") or "both",
            compact=bool(body.get("compact")),
            overrides=body.get("overrides") or {},
            terms_lookup=lambda model: [
                {"avoid": term["avoid"], "use": term["use"]}
                for term in self.terms if term["model"] == model
            ],
        )

    def _r_models(self, method, body, params):
        """`GET /api/models` — served from the committed file the API ships.

        **Read off disk rather than hand-written here**, which is the opposite
        of what the rest of this fake does and is deliberate. Every other route
        answers from the in-memory library because the SHAPE is the thing under
        test. The registry is different: it is real data that the pipeline's
        `field` reads pick apart by dotted path, and a stub of it would let a
        test pass against a model whose caps and field names nobody had checked
        against the ones that ship. It is also the file the API itself loads, so
        reading it here is the same source rather than a copy of it.
        """
        if method != "GET":
            raise FakeError(405, f"{method} /api/models")
        return {"models": _committed_registry()}

    def _r_model_schema(self, method, body, params, name):
        """`GET /api/models/<name>/schema` — the LIVE schema, which the fake has none of.

        **Empty, and that is the honest answer.** The real route proxies
        Replicate; nothing here reaches a provider, so there is no schema to
        return and `engine/schema.check` reads two empty maps as "could not
        fetch" and reports a skipped validation rather than inventing a pass.

        A test that needs validation to actually happen patches
        `studio_pipeline.engine.schema.fetch` with the properties it cares
        about — which is what `test_board`'s `no_network` fixture does, and what
        it did when this fetch went to Replicate directly.
        """
        if method != "GET":
            raise FakeError(405, f"{method} /api/models/{name}/schema")
        return {"model": name, "props": {}, "schemas": {}}

    def _r_model_readme(self, method, body, params, name):
        """`GET /api/models/<name>/readme` — prose the fake does not have either."""
        if method != "GET":
            raise FakeError(405, f"{method} /api/models/{name}/readme")
        return {"model": name, "readme": f"# fake\n\nNo README was fetched. {name}\n"}

    def _r_model(self, method, body, params, name):
        if method != "GET":
            raise FakeError(405, f"{method} /api/models/{name}")
        models = _committed_registry()
        for key, entry in models.items():
            if name in (key, entry.get("model"), *(entry.get("aliases") or [])):
                return {**entry, "key": key}
        raise FakeError(404, f"no model {name}")

    def _r_libraries(self, method, body, params):
        return [{"id": self.lib, "name": "Studio", "root": self.root["id"]}]

    def _r_resolve(self, method, body, params):
        return self._view(self._resolve(params.get("path", "")))

    def _r_asset(self, method, body, params):
        """`?node=` only. `?key=` went with shared material getting nodes."""
        node = self.nodes.get(params.get("node"))
        if node is None or not node.get("blob_key"):
            raise FakeError(404, f"no such asset: {params.get('node')}")
        return {"url": f"memory://{node['blob_key']}"}

    def _r_nodes(self, method, body, params):
        if method == "GET":
            parent = params.get("parent") or self.root["id"]
            if parent not in self.nodes:
                raise FakeError(404, f"no such node: {parent}")
            return [self._view(n) for n in self._children(parent)]
        if method == "POST":
            return self._view(self._create_node(body["parent"], body["name"],
                                                body.get("kind", "file")))
        if method == "DELETE":
            return {"deleted": sum(self._delete_node(i) for i in body.get("ids", []))}
        raise FakeError(405, method)

    def _r_node(self, method, body, params, node_id):
        node = self.nodes.get(node_id)
        if node is None:
            raise FakeError(404, f"no such node: {node_id}")
        if method == "GET":
            return self._view(node)
        if method == "DELETE":
            return {"deleted": self._delete_node(node_id)}
        if method == "PATCH":
            describing = "description" in body or "tags" in body
            asked = [g for g in ("name" in body, "parent" in body, describing) if g]
            if len(asked) > 1:
                raise FakeError(400, "name, or parent, or description/tags — one of the three")
            if not asked:
                raise FakeError(400, "send name, parent, or description/tags")
            if describing:
                if "description" in body:
                    text = (body["description"] or "").strip()
                    if text:
                        node["description"] = text
                    else:
                        node.pop("description", None)
                if "tags" in body:
                    folded = self._fold_tags(body["tags"])
                    if folded:
                        node["tags"] = folded
                    else:
                        node.pop("tags", None)
            elif "name" in body:
                if self._child(node["parent_id"], body["name"]) not in (None, node):
                    raise FakeError(409, f"{body['name']!r} already exists here")
                node["name"] = body["name"]
            elif "parent" in body:
                if self._child(body["parent"], node["name"]):
                    raise FakeError(409, f"{node['name']!r} already exists there")
                node["parent_id"] = body["parent"]
                self._repath(node)
            node["updated_at"] = _now()
            return self._view(node)
        raise FakeError(405, method)

    @staticmethod
    def _fold_tags(raw) -> list[str]:
        """Trimmed, lower-cased, de-duplicated — as `catalog.clean_tags` does.

        Mirrored rather than approximated: a fake that stored `Poolside` while
        the service stored `poolside` would let a `--pick-tag` test pass here and
        return nothing in prod.
        """
        seen, out = set(), []
        for entry in raw or []:
            tag = " ".join(str(entry).split()).lower()
            if tag and tag not in seen:
                seen.add(tag)
                out.append(tag)
        return out

    def _repath(self, node: dict) -> None:
        parent = self.nodes.get(node["parent_id"])
        node["path"] = (parent["path"] + parent["id"] + "/") if parent else "/"
        for child in self._children(node["id"]):
            self._repath(child)

    def _r_node_move(self, method, body, params):
        for node_id in body["ids"]:
            self._r_node("PATCH", {"parent": body["destination"]}, {}, node_id)
        return {"moved": len(body["ids"])}

    def _r_node_copy(self, method, body, params):
        made = []
        for node_id in body["ids"]:
            source = self.nodes[node_id]
            copy = self._create_node(body["destination"], source["name"], source["kind"])
            if source.get("blob_key"):
                copy["size"] = source.get("size")
                copy["content_type"] = source.get("content_type")
                # A copy IS byte-identical, so it carries the source's hash —
                # which is what a server-side `CopyObject` does to the ETag too.
                copy["checksum"] = source.get("checksum")
                copy["reel"] = source.get("reel")
                self.s3.put_object(
                    Bucket=BUCKET, Key=copy["blob_key"],
                    Body=self.s3.get_object(Bucket=BUCKET,
                                            Key=source["blob_key"])["Body"].read())
            made.append(self._view(copy))
        return {"nodes": made}

    def _r_download_url(self, method, body, params, node_id):
        node = self.nodes.get(node_id)
        if node is None or not node.get("blob_key"):
            raise FakeError(404, f"no bytes for {node_id}")
        return {"url": f"memory://{node['blob_key']}"}

    def _r_upload_url(self, method, body, params, node_id):
        node = self.nodes[node_id]
        node["pending"] = {"size": body["size"], "content_type": body["content_type"]}
        return {"url": f"memory://{node['blob_key']}",
                "headers": {"Content-Type": body["content_type"],
                            "Content-Length": str(body["size"])}}

    def _r_confirm(self, method, body, params, node_id):
        """Finalise a placeholder — and 404 if the bytes are not actually there.

        **The head is not decoration.** The real route runs `HeadObject` and
        writes the row from what S3 reports, so a confirm on a node whose PUT
        never happened is a 404 rather than a row promising bytes that are
        absent. This fake used to skip that and take the pending values on
        trust, which made it agree with a caller that had uploaded nothing —
        the exact divergence that lets an upload bug pass a green suite.
        """
        node = self.nodes[node_id]
        try:
            head = self.s3.head_object(Bucket=BUCKET, Key=node["blob_key"])
        except Exception:
            raise FakeError(404, f"no object at {node['blob_key']}") from None
        pending = node.pop("pending", None) or {}
        # The MD5 of the bytes, exactly as the API records it: an ETag is the
        # content hash for a single PUT, and every upload here is one. Served so
        # `curate dedupe` compares two values instead of downloading two files.
        etag = (head.get("ETag") or "").strip('"')
        if etag and "-" not in etag:
            node["checksum"] = etag
        node["size"] = pending.get("size")
        node["content_type"] = pending.get("content_type")
        # The sparse reel key (D5): images and videos only, so folders, entity
        # rows and run documents stop consuming the reel's enumeration.
        if str(node["content_type"] or "").startswith(REEL_TYPES):
            node["reel"] = self.lib
        else:
            node.pop("reel", None)
        node["updated_at"] = _now()
        return self._view(node)

    def _r_text(self, method, body, params, node_id):
        node = self.nodes[node_id]
        if method == "GET":
            return {"content": self.s3.get_object(
                Bucket=BUCKET, Key=node["blob_key"])["Body"].read().decode()}
        encoded = body["content"].encode()
        self.s3.put_object(Bucket=BUCKET, Key=node["blob_key"], Body=encoded)
        node["size"] = len(encoded)
        node["checksum"] = hashlib.md5(encoded).hexdigest()
        node["updated_at"] = _now()
        return self._view(node)

    def _r_node_owner(self, method, body, params, node_id):
        return self._owner(node_id) or {}

    # ── characters ──────────────────────────────────────────────────────────

    def _char_view(self, record: dict) -> dict:
        counts = {"references": len(self.refs.get(record["id"], [])),
                  "files": sum(1 for n in self.nodes.values()
                               if n["kind"] == "file"
                               and (self._owner(n["id"]) or {}).get("id") == record["id"])}
        return {**{k: v for k, v in record.items() if k != "_"}, "counts": counts}

    def _r_characters(self, method, body, params):
        if method == "GET":
            query = params.get("q")
            return [self._char_view(c) for c in self.characters.values()
                    if not query or query in c["slug"]]
        if method != "POST":
            raise FakeError(405, method)
        slug = body["slug"]
        self._claim(self.characters, slug, "character")
        root = self._create_node(self.root["id"], slug, "folder")
        char_id = "char-" + str(uuid.uuid4())
        root["entity"] = char_id
        self._layout(root["id"], ("reference", "corpus", "seed", "archive"))
        record = {"id": char_id, "lib": self.lib, "slug": slug,
                  "display_name": body.get("display_name") or slug,
                  "schema_version": 2, "rev": 1,
                  "created": _now(), "updated": _now(),
                  "root": root["id"], "hero": None, "default_set": [],
                  "profile": self._clean_profile(body.get("profile"))}
        self.characters[char_id] = record
        self.refs[char_id] = []
        return self._char_view(record)

    def _r_character(self, method, body, params, ref):
        record = self._entity(self.characters, ref, "character")
        if method == "GET":
            return self._char_view(record)
        if method == "PATCH":
            if "slug" in body and body["slug"] != record["slug"]:
                self._claim(self.characters, body["slug"], "character")
                self.nodes[record["root"]]["name"] = body["slug"]
            self._bump(record, body.get("rev"))
            for field in ("slug", "display_name", "hero"):
                if field in body:
                    record[field] = body[field]
            return self._char_view(record)
        if method == "DELETE":
            if params.get("files") == "delete":
                self.characters.pop(record["id"])
                self._delete_node(record["root"])
            else:
                self.characters.pop(record["id"])
                self.nodes[record["root"]].pop("entity", None)
            self.refs.pop(record["id"], None)
            return {"deleted": record["id"]}
        raise FakeError(405, method)

    #: What `clean_profile` accepts, mirrored from `backend/studio_core/routes/
    #: characters.py`. Validated here for the same reason the PUT refusal is: a
    #: fake looser than the service cannot fail the way the service does, and
    #: `schema_version` rode back out in the `edit` round trip for exactly as
    #: long as the verb kept the request from ever being read.
    PROFILE_SECTIONS = ("identity", "face", "body", "wardrobe", "voice",
                        "rendering", "consistency", "text_identity_block")

    def _clean_profile(self, raw):
        if raw is None:
            return {}
        unknown = sorted(set(raw) - set(self.PROFILE_SECTIONS))
        if unknown:
            raise FakeError(400, f"profile has no section called {unknown[0]!r}")
        return raw

    def _r_profile(self, method, body, params, ref):
        """Replace or merge, told apart by the body's key — never by the verb.

        **This used to accept `PUT` for the replace**, which is how the adapter
        came to send one: the fake answered it, every test passed, and the real
        route registers `PATCH` alone. A fake that is more permissive than the
        API it stands in for cannot fail the one way that matters, so the two
        refusals below are the point of this handler rather than trimmings.
        """
        record = self._entity(self.characters, ref, "character")
        if method != "PATCH":
            raise FakeError(405, method)
        replacing, merging = "profile" in body, "patch" in body
        if replacing and merging:
            raise FakeError(400, "send profile to replace, or patch to merge, not both")
        if not replacing and not merging:
            raise FakeError(400, "send profile to replace, or patch to merge")
        self._bump(record, body.get("rev"))
        record["profile"] = (self._clean_profile(body["profile"]) if replacing
                             else {**record["profile"],
                                   **self._clean_profile(body["patch"])})
        return self._char_view(record)

    def _ref_file(self, entry: dict) -> dict:
        node = self.nodes.get(entry["node"])
        if node is None:
            return {}
        return {"name": node["name"], "size": node.get("size"),
                "content_type": node.get("content_type"),
                "url": f"memory://{node.get('blob_key')}"}

    def _describe(self, node_id: str, spec: dict) -> None:
        """The node half of a reference write, as the service does it.

        A caption sent to a reference route lands on the FILE. The row keeps
        `group` and `order`, which are facts about this character's set; the
        words are a fact about the picture and are true of it in `corpus/` too.
        """
        node = self.nodes.get(node_id)
        if node is None:
            return
        if "description" in spec:
            text = (spec["description"] or "").strip()
            node["description"] = text if text else None
            if not text:
                node.pop("description", None)
        if "tags" in spec:
            folded = self._fold_tags(spec["tags"])
            if folded:
                node["tags"] = folded
            else:
                node.pop("tags", None)

    def _ref_entry(self, record: dict, entry: dict) -> dict:
        node = self.nodes.get(entry["node"]) or {}
        return {**entry,
                "description": node.get("description"),
                "tags": list(node.get("tags") or []),
                "default": entry["node"] in (record.get("default_set") or []),
                "file": self._ref_file(entry)}

    def _r_references(self, method, body, params, ref):
        record = self._entity(self.characters, ref, "character")
        entries = self.refs.setdefault(record["id"], [])
        if method == "GET":
            wanted = params.get("group")
            groups: dict[str, list] = {}
            for entry in sorted(entries, key=lambda e: (e["group"], e["order"])):
                if wanted and entry["group"] != wanted:
                    continue
                groups.setdefault(entry["group"], []).append(
                    self._ref_entry(record, entry))
            counts: dict[str, int] = {}
            for entry in entries:
                counts[entry["group"]] = counts.get(entry["group"], 0) + 1
            return {"groups": groups, "counts": counts}
        if method == "POST":
            if body["node"] not in self.nodes:
                raise FakeError(404, f"no such node: {body['node']}")
            if any(e["node"] == body["node"] for e in entries):
                raise FakeError(409, "already a reference")
            entry = {"node": body["node"], "group": body["group"],
                     "order": self._order(entries, body["group"], body.get("after")),
                     "created": _now()}
            entries.append(entry)
            self._describe(body["node"], body)
            return self._ref_entry(record, entry)
        if method == "PATCH":
            by_node = {e["node"]: e for e in entries}
            unknown = [e["node"] for e in body["entries"] if e["node"] not in by_node]
            if unknown:
                raise FakeError(404, f"not references: {', '.join(unknown[:8])}")
            for spec in body["entries"]:
                entry = by_node[spec["node"]]
                if "group" in spec:
                    entry["group"] = spec["group"]
                self._describe(spec["node"], spec)
            return {"described": len(body["entries"])}
        raise FakeError(405, method)

    def _order(self, entries: list[dict], group: str, after: str | None) -> int:
        """Gapped by 1000; `after` takes the midpoint. One write, no neighbours."""
        in_group = sorted((e for e in entries if e["group"] == group),
                          key=lambda e: e["order"])
        if after:
            for index, entry in enumerate(in_group):
                if entry["node"] == after:
                    following = in_group[index + 1]["order"] if index + 1 < len(in_group) \
                        else entry["order"] + 2 * ORDER_GAP
                    return (entry["order"] + following) // 2
            raise FakeError(404, f"no reference {after}")
        return (in_group[-1]["order"] + ORDER_GAP) if in_group else ORDER_GAP

    def _r_reference(self, method, body, params, ref, node_id):
        record = self._entity(self.characters, ref, "character")
        entries = self.refs.setdefault(record["id"], [])
        entry = next((e for e in entries if e["node"] == node_id), None)
        if entry is None:
            raise FakeError(404, f"{node_id} is not a reference of {record['slug']}")
        if method == "DELETE":
            entries.remove(entry)
            # **And out of the default set, in the same act** — as the service
            # does. Detaching used to leave the id sitting there, where the
            # selection route filtered it out silently; production carried four
            # of those on one character before anyone counted.
            before = record.get("default_set") or []
            after = [each for each in before if each != node_id]
            answer = {"detached": node_id, "node": node_id}
            if len(after) != len(before):
                record["default_set"] = after
                answer["default_set"] = after
            return answer
        if method != "PATCH":
            raise FakeError(405, method)
        if "group" in body:
            entry["group"] = body["group"]
            entry["order"] = self._order([e for e in entries if e is not entry],
                                         body["group"], None)
        self._describe(node_id, body)
        if body.get("after"):
            entry["order"] = self._order([e for e in entries if e is not entry],
                                         entry["group"], body["after"])
        return self._ref_entry(record, entry)

    def _r_default_set(self, method, body, params, ref):
        record = self._entity(self.characters, ref, "character")
        if method == "PATCH" and isinstance(body.get("nodes"), list):
            # The route compare-and-swaps the record like every other write on
            # it, and the adapter did not send `rev` — which only became visible
            # once the verb fix let the request reach the API.
            self._bump(record, body.get("rev"))
            attached = {e["node"] for e in self.refs.get(record["id"], [])}
            stray = [n for n in body["nodes"] if n not in attached]
            if stray:
                raise FakeError(400, f"{stray[0]} is not a reference of {record['slug']}")
        known = {e["node"] for e in self.refs.get(record["id"], [])}
        unknown = [n for n in body["nodes"] if n not in known]
        if unknown:
            raise FakeError(404, f"not references: {', '.join(unknown)}")
        record["default_set"] = list(body["nodes"])
        return {"default_set": record["default_set"]}

    def _r_selection(self, method, body, params, ref):
        """Resolution order: pick > tag > default_set > everything.

        The refusal is the interesting half: over-cap comes back 409 with the
        index in the body rather than truncated, because which images a
        generation saw must not be decided by whatever a listing returned.
        """
        record = self._entity(self.characters, ref, "character")
        # Folded with the FILE's description and tags before anything filters on
        # them, exactly as the route does: `?tag=` selects on tags and tags are
        # the file's, so the files have to be in hand first.
        entries = [
            {**entry,
             "description": (self.nodes.get(entry["node"]) or {}).get("description"),
             "tags": list((self.nodes.get(entry["node"]) or {}).get("tags") or [])}
            for entry in sorted(self.refs.get(record["id"], []),
                                key=lambda e: (e["group"], e["order"]))
        ]
        by_node = {e["node"]: e for e in entries}
        pick = [p for p in (params.get("pick") or "").split(",") if p]
        tags = [t for t in (params.get("tag") or "").split(",") if t]
        if pick:
            chosen, source = [], "pick"
            for want in pick:
                hit = by_node.get(want) or next(
                    (e for e in entries
                     if self.nodes.get(e["node"], {}).get("name") == want), None)
                if hit is None:
                    raise FakeError(404, f"{record['slug']} has no reference {want!r}")
                chosen.append(hit)
        elif tags:
            wanted = set(tags)
            chosen = [e for e in entries if wanted <= set(e["tags"])]
            source = "tag"
            if not chosen:
                have = sorted({t for e in entries for t in e["tags"]})
                raise FakeError(404, f"no reference of {record['slug']} carries all of "
                                     f"{sorted(wanted)}. Tags in use: {have or '(none)'}")
        elif record.get("default_set"):
            # Refused, never filtered — as the route does. A generation shown
            # three of the seven images somebody chose is a result nobody can
            # explain, which is the same rule the cap refusal already follows.
            stale = [n for n in record["default_set"] if n not in by_node]
            if stale:
                raise FakeError(409, f"{len(stale)} of {len(record['default_set'])} in "
                                     f"{record['slug']}'s default set are not references "
                                     f"any more: {', '.join(stale[:4])}")
            chosen = [by_node[n] for n in record["default_set"]]
            source = "default_set"
        else:
            chosen, source = list(entries), "all"

        limit = params.get("limit")
        if limit is not None and len(chosen) > int(limit):
            raise FakeError(409,
                            f"{len(chosen)} references match; this model accepts {limit}")
        return {"selection": [
            {"slot": n, "node": e["node"], "group": e["group"],
             "description": e["description"], "tags": e["tags"],
             "name": self.nodes.get(e["node"], {}).get("name"),
             "url": f"memory://{self.nodes.get(e['node'], {}).get('blob_key')}"}
            for n, e in enumerate(chosen, 1)],
            "cap": limit, "source": source}

    def _r_textblock(self, method, body, params, ref):
        record = self._entity(self.characters, ref, "character")
        profile = record.get("profile") or {}
        # `<>` is the blank template's unfilled block, and the route empties it
        # before answering so that a caller never has to know the placeholder.
        authored = (profile.get("text_identity_block") or "").strip()
        if authored.startswith("<"):
            authored = ""
        return {"id": record["id"], "text": authored,
                "raw": {} if authored else
                       {k: profile[k] for k in
                        ("identity", "face", "body", "wardrobe", "consistency")
                        if profile.get(k)}}

    def _r_character_runs(self, method, body, params, ref):
        record = self._entity(self.characters, ref, "character")
        return {"runs": [self._run_row(r) for r in self._sorted_runs()
                         if record["id"] in (r.get("characters") or [])],
                "cursor": None}

    def _r_character_projects(self, method, body, params, ref):
        record = self._entity(self.characters, ref, "character")
        return [self._project_view(p) for p in self.projects.values()
                if record["id"] in (p.get("characters") or [])]

    # ── projects ────────────────────────────────────────────────────────────

    def _project_view(self, record: dict) -> dict:
        counts = {
            "runs": sum(1 for r in self.runs.values() if r["project"] == record["id"]),
            "scenes": sum(1 for s in self.scenes.values() if s["project"] == record["id"]),
            "movies": sum(1 for m in self.movies.values() if m["project"] == record["id"]),
        }
        # `characters` EXPANDED, exactly as `GET /api/projects/<id>` answers —
        # `{id, slug, display_name}` per link. This used to invent a
        # `character_slugs` list of bare slugs, which the real API has never
        # returned; the CLI read it, printed `—` for every project in
        # production, and the suite passed because the double agreed with the
        # bug rather than with the service.
        return {**record, "counts": counts,
                "characters": [
                    {"id": c,
                     "slug": self.characters[c]["slug"],
                     "display_name": self.characters[c].get("display_name")}
                    for c in record.get("characters") or []
                    if c in self.characters
                ]}

    def _r_projects(self, method, body, params):
        if method == "GET":
            return [self._project_view(p) for p in self.projects.values()]
        if method != "POST":
            raise FakeError(405, method)
        slug = body["slug"]
        self._claim(self.projects, slug, "project")
        root = self._create_node(self.root["id"], slug, "folder")
        proj_id = "proj-" + str(uuid.uuid4())
        root["entity"] = proj_id
        self._layout(root["id"], ("runs", "scenes", "movies", "chains", "input"))
        record = {"id": proj_id, "lib": self.lib, "slug": slug,
                  "title": body.get("title") or "", "rev": 1,
                  "description": body.get("description") or "",
                  "created": _now(), "updated": _now(), "root": root["id"],
                  "hero": None, "characters": list(body.get("characters") or [])}
        self.projects[proj_id] = record
        return self._project_view(record)

    def _r_project(self, method, body, params, ref):
        record = self._entity(self.projects, ref, "project")
        if method == "GET":
            return self._project_view(record)
        if method == "PATCH":
            if "slug" in body and body["slug"] != record["slug"]:
                self._claim(self.projects, body["slug"], "project")
                self.nodes[record["root"]]["name"] = body["slug"]
            self._bump(record, body.get("rev"))
            for field in ("slug", "title", "description", "hero"):
                if field in body:
                    record[field] = body[field]
            return self._project_view(record)
        if method == "DELETE":
            # `cascade` takes the children with it; `force` deletes the project
            # and ORPHANS them. Both are modelled because the API offers both,
            # and a fake that knew only one would make a test pass over the
            # behaviour it did not know about.
            holds = [r for r in self.runs.values() if r["project"] == record["id"]]
            cascade = params.get("cascade") in ("1", 1, "true", True)
            if holds and not cascade and not params.get("force"):
                raise FakeError(409, f"{record['slug']} holds {len(holds)} run(s) — "
                                     "pass ?cascade=1 to delete them with it")
            removed = {}
            if cascade:
                for run in holds:
                    self.runs.pop(run["id"], None)
                    if params.get("files") == "delete":
                        self._delete_node(run["folder"])
                if holds:
                    removed["run"] = len(holds)
            self.projects.pop(record["id"])
            if params.get("files") == "delete":
                self._delete_node(record["root"])
            else:
                self.nodes[record["root"]].pop("entity", None)
            return {"deleted": record["id"], "id": record["id"], "removed": removed}
        raise FakeError(405, method)

    def _r_project_characters(self, method, body, params, ref):
        record = self._entity(self.projects, ref, "project")
        unknown = [c for c in body["characters"] if c not in self.characters]
        if unknown:
            raise FakeError(404, f"no such character(s): {', '.join(unknown)}")
        record["characters"] = list(body["characters"])
        return self._project_view(record)

    def _r_project_inputs(self, method, body, params, ref):
        """`{folder, inputs}`, as the route answers — NOT a bare array.

        This returned the array directly, which is the one shape the real route
        does not use. `_as_list` answers `[]` for anything that is not a list,
        so against the service the pool read as empty every time while every
        test here passed.
        """
        record = self._entity(self.projects, ref, "project")
        pool = self._folder_under(record["root"], "input")
        return {"folder": pool["id"],
                "inputs": [{**self._view(n), "position": i}
                           for i, n in enumerate(
                               sorted((c for c in self._children(pool["id"])
                                       if c["kind"] == "file"),
                                      key=lambda n: _natural(n["name"])), 1)]}

    def _r_project_runs(self, method, body, params, ref):
        record = self._entity(self.projects, ref, "project")
        return self._r_runs("GET", {}, {**params, "project": record["id"]})

    def _r_project_scenes(self, method, body, params, ref):
        record = self._entity(self.projects, ref, "project")
        return [self._scene_view(s) for s in self.scenes.values()
                if s["project"] == record["id"]]

    def _r_project_movies(self, method, body, params, ref):
        record = self._entity(self.projects, ref, "project")
        return [self._movie_view(m) for m in self.movies.values()
                if m["project"] == record["id"]]

    # ── runs ────────────────────────────────────────────────────────────────

    def _sorted_runs(self) -> list[dict]:
        return sorted(self.runs.values(), key=lambda r: r["created"], reverse=True)

    def _run_row(self, record: dict) -> dict:
        """**Exactly the fields the real listing row carries. No more.**

        This used to project `slug` and `cost` straight off the full record, so
        the suite was green over a contract the API does not honour: a listing
        row is `{lib, id, created, status, model, kind, thumb}` and never held
        either. `studio runs list` raised `KeyError: 'slug'` against production
        while passing here. A fake more generous than the thing it fakes hides
        the bug it exists to catch.
        """
        outputs = record.get("outputs") or []
        return {"id": record["id"], "project": record["project"],
                "status": record["status"], "kind": record["kind"],
                "model": record["model"], "created": record["created"],
                "thumb": {"node": outputs[0]} if outputs else None}

    def _backlinks(self, holders: dict, matches) -> list[dict]:
        """The `{id, slug, title}` rows `support.holders` sends, sorted by slug.

        The real API answers these off `by-sk` edge rows. What matters to a
        double is not how they are stored but that the FIELD EXISTS and has the
        service's shape — a fake that omits one lets a client read `undefined`
        forever and the suite stay green. That is not a hypothetical: this file
        used to invent a `character_slugs` field the API has never sent, and it
        kept three real bugs hidden behind 1000 passing tests.
        """
        return sorted(
            ({"id": h["id"], "slug": h.get("slug"), "title": h.get("title")}
             for h in holders.values() if matches(h)),
            key=lambda entry: entry.get("slug") or "",
        )

    def _run_view(self, record: dict) -> dict:
        return {**record,
                "scenes": self._backlinks(
                    self.scenes,
                    lambda sc: any(shot.get("run") == record["id"]
                                   for shot in self.shots.get(sc["id"], []))),
                "outputs": [{"node": n, "name": self.nodes.get(n, {}).get("name"),
                             "size": self.nodes.get(n, {}).get("size"),
                             "url": f"memory://{self.nodes.get(n, {}).get('blob_key')}"}
                            for n in record.get("outputs") or []],
                # **Derived from the sends, exactly as the real route derives
                # them.** The map was an attribute once; keeping both would be
                # two spellings of one relationship.
                "bindings": self._bindings_of(record),
                "sends": [{**send,
                           "name": self.nodes.get(send["node"], {}).get("name")}
                          for send in record.get("sends") or []],
                "output_nodes": list(record.get("outputs") or [])}

    @staticmethod
    def _bindings_of(record: dict) -> dict:
        bindings: dict[str, list[str]] = {}
        for send in record.get("sends") or []:
            bindings.setdefault(send["field"], []).append(send["node"])
        return bindings

    def _r_resolve_run(self, method, body, params):
        """`GET /api/runs/resolve` — a runref to the run it names.

        `index` is reported and never applied: the caller filters by extension
        first and then takes the Nth of what is left, so narrowing here would
        change which file `#2` means.
        """
        if method != "GET":
            raise FakeError(405, f"{method} /api/runs/resolve")
        ref = (params.get("ref") or "").strip()
        if not ref:
            raise FakeError(400, "ref is required")

        head, _, raw_index = ref.partition("#")
        index = None
        if raw_index:
            if not raw_index.isdigit() or int(raw_index) < 1:
                raise FakeError(400, f"runref index must be a positive integer: {ref!r}")
            index = int(raw_index)

        if "/" in head:
            project_ref, _, run_ref = head.partition("/")
        else:
            project_ref, run_ref = params.get("project"), head

        if run_ref.startswith("run-"):
            record = self.runs.get(run_ref)
            if record is None:
                raise FakeError(404, f"no run {run_ref}")
        else:
            if not project_ref:
                raise FakeError(400, f"runref {ref!r} has no project and none was supplied")
            if run_ref not in ("latest", "last"):
                raise FakeError(400, f"{run_ref!r} is not a runref")
            addressed = (project_ref if project_ref.startswith("proj-")
                         else f"slug:{project_ref}")
            project = self._entity(self.projects, addressed, "project")
            # `HIDDEN_RUN_STATUSES`, not `UNSUBMITTED`: an APPROVED run is
            # visible in a listing and only `draft` and `discarded` are not.
            hidden = (frozenset() if params.get("include") == "drafts"
                      else frozenset({"draft", "discarded"}))
            live = [r for r in self._sorted_runs()
                    if r["project"] == project["id"] and r["status"] not in hidden]
            if not live:
                raise FakeError(404, f"no runs in project {project_ref}")
            record = self.runs[live[0]["id"]]
        return {**self._run_view(record), "ref": ref, "index": index}

    def _r_runs(self, method, body, params):
        if method == "GET":
            found = self._sorted_runs()
            if params.get("project"):
                project = self._entity(self.projects, params["project"], "project")
                found = [r for r in found if r["project"] == project["id"]]
            if params.get("character"):
                char = self._entity(self.characters, params["character"], "character")
                found = [r for r in found
                         if char["id"] in (r.get("characters") or [])]
            for field in ("model", "status", "fingerprint"):
                if params.get(field):
                    found = [r for r in found if r.get(field) == params[field]]
            if params.get("since"):
                found = [r for r in found if r["created"] >= params["since"]]
            if params.get("limit"):
                found = found[:int(params["limit"])]
            return {"runs": [self._run_row(r) for r in found], "cursor": None}
        if method != "POST":
            raise FakeError(405, method)

        project = self._entity(self.projects, body["project"], "project")
        bindings = body.get("bindings") or {}
        for field, value in bindings.items():
            for one in (value if isinstance(value, list) else [value]):
                if not isinstance(one, str) or "://" in one:
                    raise FakeError(400, f"bindings.{field} is a URL; bindings name "
                                         "nodes. S3 is the only origin.")
                if one not in self.nodes:
                    raise FakeError(404, f"bindings.{field} names no node: {one}")

        runs_folder = self._folder_under(project["root"], "runs")
        run_id = "run-" + str(uuid.uuid4())
        # A run has no slug; its folder is named for its id, which cannot
        # collide — so no `_unique` dance here, unlike a scene or a movie.
        folder = self._create_node(runs_folder["id"], run_id, "folder")
        self._create_node(folder["id"], "output", "folder")
        payload = {"request": self._document(folder["id"], "request.json",
                                             json.dumps(body.get("input") or {})),
                   "response": None, "prompt": None}
        if body.get("prompt") is not None:
            payload["prompt"] = self._document(folder["id"], "prompt.json",
                                               json.dumps(body["prompt"]))
        sends = body.get("sends")
        if sends is None:
            sends = [{"field": field, "role": None, "node": node}
                     for field, value in bindings.items()
                     for node in (value if isinstance(value, list) else [value])]
        for index, send in enumerate(sends):
            if "://" in send["node"]:
                raise FakeError(400, f"sends[{index}].node is a URL; a send names "
                                     "a node. S3 is the only origin.")
            if send["node"] not in self.nodes:
                raise FakeError(404, f"sends[{index}].node names no node")
            send.setdefault("source", {"kind": "object"})

        record = {"id": run_id, "lib": self.lib, "project": project["id"],
                  # **A draft, exactly as the real route creates one.** The
                  # record is written when the run is PLANNED, not when it is
                  # submitted, which is what gives an approval something to
                  # attach to.
                  "status": "draft", "kind": body["kind"],
                  "engine": body["engine"], "model": body["model"],
                  "plan": body.get("plan"), "approval": None, "counted": False,
                  "sends": sends,
                  "prediction_id": None, "created": _now(), "submitted": None,
                  "completed": None,
                  "characters": list(body.get("characters") or []),
                  "folder": folder["id"], "outputs": [],
                  "cost": None, "error": None, "payload": payload,
                  # **A filename, not an identity**, and an envelope field rather
                  # than part of the plan — `plan_digest` hashes the plan, so a
                  # rename would void an approval over something the provider is
                  # never sent. Recorded at draft time because the callback that
                  # names the output file arrives with no request body.
                  "output_name": body.get("name"),
                  "input": body.get("input") or {}}
        record["plan_digest"] = _plan_digest(record["plan"], sends)
        record["fingerprint"] = _fingerprint(record.get("model"), record["plan"], sends)
        self.runs[run_id] = record
        return self._run_view(record)

    def _document(self, parent_id: str, name: str, text: str) -> str:
        """A payload blob. **Stored as text and never decoded by studio.**"""
        node = self._create_node(parent_id, name, "file")
        self.s3.put_object(Bucket=BUCKET, Key=node["blob_key"], Body=text.encode())
        node["size"] = len(text.encode())
        node["content_type"] = "text/plain; charset=utf-8"
        return node["id"]

    def _r_run(self, method, body, params, run_id):
        record = self.runs.get(run_id)
        if record is None:
            raise FakeError(404, f"no such run: {run_id}")
        if method == "GET":
            return self._run_view(record)
        if method == "PATCH":
            # **The gate, and it is on LEAVING the unsubmitted states.** Not on
            # reaching `pending`: `engine/submit.py` writes `running` when it
            # does not poll and `succeeded` when it does, so a check naming one
            # status would be enforced here and bypassed in practice.
            if "status" in body:
                if body["status"] not in RUN_STATUSES:
                    raise FakeError(400, f"status must be one of "
                                         f"{', '.join(sorted(RUN_STATUSES))}")
                leaving = (record["status"] in UNSUBMITTED
                           and body["status"] not in UNSUBMITTED
                           # An adoption files an artifact that already existed.
                           # Nothing was submitted, so nothing was approved.
                           and body["status"] != "adopted")
                if leaving:
                    if record["status"] != "approved":
                        raise FakeError(409, f"run {run_id} is {record['status']} "
                                             "and has not been approved")
                    current = _plan_digest(record.get("plan"), record["sends"])
                    if (record.get("approval") or {}).get("digest") != current:
                        raise FakeError(409, "the payload changed after it was "
                                             "approved; approve it again")
            for field in ("status", "prediction_id", "error", "cost", "completed",
                          "submitted", "outputs"):
                if field in body:
                    record[field] = body[field]
            return self._run_view(record)
        if method == "DELETE":
            self.runs.pop(run_id)
            if params.get("files") == "delete":
                self._delete_node(record["folder"])
            return {"deleted": run_id}
        raise FakeError(405, method)

    def _r_run_plan(self, method, body, params, run_id):
        record = self._draft(run_id)
        record["plan"] = body["plan"]
        return self._revised(record)

    def _r_run_sends(self, method, body, params, run_id):
        record = self._draft(run_id)
        for send in body["sends"]:
            send.setdefault("source", {"kind": "object"})
        record["sends"] = body["sends"]
        return self._revised(record)

    def _r_run_approve(self, method, body, params, run_id):
        record = self.runs[run_id]
        if method == "DELETE":
            record["approval"] = None
            record["status"] = "draft"
            return self._run_view(record)
        if record["status"] not in ("draft", "approved"):
            raise FakeError(409, f"run {run_id} is {record['status']}; only a "
                                 "draft is approved")
        current = _plan_digest(record.get("plan"), record["sends"])
        if body.get("digest") != current:
            raise FakeError(409, "the plan changed after the payload you approved "
                                 "was rendered; review it again")
        # `via` mirrors the real route, INCLUDING its refusal of a third word.
        # The fake validating nothing is what let `studio runs adopt` write a
        # status the real route rejects and pass its tests for months.
        via = body.get("via", "interactive")
        if via not in ("interactive", "relayed"):
            raise FakeError(400, "via must be 'interactive' or 'relayed'")
        record["approval"] = {"by": "sub-fake", "at": _now(), "digest": current,
                              "via": via}
        record["status"] = "approved"
        return self._run_view(record)

    # ── the submission, and the callback that closes it ─────────────────────
    #
    # **This is what replaced `adapters/replicate.py`'s fake.** The pipeline used
    # to hold the provider client, so the suite faked Replicate; the API holds it
    # now, so the suite fakes the API's submit route instead. The same three
    # properties are preserved, because they are what made the old one safe:
    #
    #   * **Deterministic.** A prediction id is a hash of the run, so two
    #     identical submissions in a test produce the same id.
    #   * **Nothing sleeps and no socket opens.** The prediction settles the
    #     moment it is asked about.
    #   * **The media is real and visibly a placeholder.** Things downstream do
    #     real work on an output — `contact_sheet` reads its dimensions, `frames`
    #     decodes it — so magic bytes fail in ways that look like pipeline bugs.

    def _r_run_submit(self, method, body, params, run_id):
        """`POST /api/runs/<id>/submit` — the gate, then a prediction.

        The gate is the real route's, spelled out rather than shared, for the
        reason this whole file exists: a fake more generous than the thing it
        fakes hides the bug it was written to catch. An unapproved run is a 409
        here exactly as it is in production.
        """
        if method != "POST":
            raise FakeError(405, f"{method} /api/runs/{run_id}/submit")
        record = self.runs.get(run_id)
        if record is None:
            raise FakeError(404, f"no such run: {run_id}")

        if self.submits_refused:
            # The stronger property `test_board`'s `no_network` fixture asserts:
            # not "this did not bill" but "this did not submit AT ALL". A dry run
            # that submitted would otherwise pass every other check in the file.
            raise AssertionError("nothing may submit in this suite")

        if record["status"] not in UNSUBMITTED:
            raise FakeError(409, f"run {run_id} is {record['status']}; it has "
                                 "already been sent")
        if record["status"] != "approved":
            raise FakeError(409, f"run {run_id} is {record['status']} and has "
                                 "not been approved")
        current = _plan_digest(record.get("plan"), record["sends"])
        if (record.get("approval") or {}).get("digest") != current:
            raise FakeError(409, "the payload changed after it was approved; "
                                 "review and approve it again")

        record["status"] = "running"
        record["submitted"] = _now()
        record["counted"] = True
        record["prediction_id"] = "fake" + hashlib.sha256(
            run_id.encode()).hexdigest()[:20]
        # Queued rather than applied: the real submission returns as soon as the
        # provider has accepted it, and the run is closed later by something
        # else. A fake that closed it here would make `wait_for` untested.
        self.pending[run_id] = self.next_outcome
        self.next_outcome = "succeeded"
        return {**self._run_view(record), "callback": self.callback}

    def _r_run_reconcile(self, method, body, params, run_id):
        """`POST /api/runs/<id>/reconcile` — ask, and close on the answer.

        Idempotent, like the real one: a run already finished comes back
        untouched rather than growing a second copy of its output.
        """
        if method != "POST":
            raise FakeError(405, f"{method} /api/runs/{run_id}/reconcile")
        record = self.runs.get(run_id)
        if record is None:
            raise FakeError(404, f"no such run: {run_id}")
        return self._run_view(self._close(record))

    def _close(self, record: dict) -> dict:
        """Apply whatever the queued prediction did. **The fake's callback.**"""
        if record["status"] in ("succeeded", "failed", "cancelled", "discarded"):
            return record
        outcome = self.pending.pop(record["id"], None)
        if outcome is None:
            return record
        if outcome != "succeeded":
            record["status"] = outcome
            record["completed"] = _now()
            record["error"] = f"the fake provider reported {outcome}"
            return record

        folder = self._child(record["folder"], "output") or self._create_node(
            record["folder"], "output", "folder")
        stem = record.get("output_name") or record["kind"]
        # `.png` for an image, because that is what the extension is taken off
        # in production: `generate._output_names` reads it from the output URL
        # rather than from the registry, and Replicate's image models deliver
        # PNGs. A fake that named the file `.jpg` would quietly disagree with
        # every real run.
        ext = ".png" if record["kind"] == "image" else ".mp4"
        node = self._create_node(folder["id"], f"{stem}{ext}", "file")
        body = _placeholder_image() if record["kind"] == "image" else b"studio-fake-clip"
        self.s3.put_object(Bucket=BUCKET, Key=node["blob_key"], Body=body)
        node["size"] = len(body)
        node["content_type"] = mimetypes.guess_type(node["name"])[0] or "application/octet-stream"

        record["outputs"] = [*(record.get("outputs") or []), node["id"]]
        record["status"] = "succeeded"
        record["completed"] = _now()
        record["cost"] = {"amount": None, "currency": None, "predict_time": 0.0}
        record["payload"] = {**(record.get("payload") or {}),
                             "response": self._document(
                                 record["folder"], "response.json",
                                 json.dumps({"id": record["prediction_id"],
                                             "status": "succeeded"}, indent=2))}
        return record

    def _draft(self, run_id: str) -> dict:
        record = self.runs[run_id]
        if record["status"] not in UNSUBMITTED:
            raise FakeError(409, f"run {run_id} has been submitted; its plan is "
                                 "what was sent and cannot be rewritten")
        return record

    def _revised(self, record: dict) -> dict:
        """Any plan or sends edit clears the approval. Hard rule #2, mechanically."""
        record["plan_digest"] = _plan_digest(record.get("plan"), record["sends"])
        record["fingerprint"] = _fingerprint(record.get("model"), record.get("plan"),
                                             record["sends"])
        record["approval"] = None
        record["status"] = "draft"
        return self._run_view(record)

    def _r_run_outputs(self, method, body, params, run_id):
        record = self.runs[run_id]
        folder = self._folder_under(record["folder"], "output")
        node = self._create_node(folder["id"], body["name"], "file")
        node["pending"] = {"size": body["size"], "content_type": body["content_type"]}
        record["outputs"].append(node["id"])
        return {"node": node["id"], "url": f"memory://{node['blob_key']}",
                "headers": {"Content-Type": body["content_type"],
                            "Content-Length": str(body["size"])}}

    def _r_run_response(self, method, body, params, run_id):
        record = self.runs[run_id]
        text = body["body"] if isinstance(body["body"], str) else json.dumps(body["body"])
        record["payload"]["response"] = self._document(record["folder"],
                                                       "result.json", text)
        return {"response": record["payload"]["response"]}

    # ── scenes and movies ───────────────────────────────────────────────────

    def _scene_view(self, record: dict) -> dict:
        return {**record,
                "shots": sorted(self.shots.get(record["id"], []),
                                key=lambda s: s["order"]),
                "movies": self._backlinks(
                    self.movies,
                    lambda m: record["id"] in (m.get("scenes") or []))}

    def _r_scenes(self, method, body, params):
        if method == "GET":
            found = list(self.scenes.values())
            if params.get("project"):
                project = self._entity(self.projects, params["project"], "project")
                found = [s for s in found if s["project"] == project["id"]]
            return {"scenes": [self._scene_view(s) for s in
                               sorted(found, key=lambda s: s["created"])],
                    "cursor": None}
        if method != "POST":
            raise FakeError(405, method)
        project = self._entity(self.projects, body["project"], "project")
        if any(s["project"] == project["id"] and s["slug"] == body["slug"]
               for s in self.scenes.values()):
            raise FakeError(409, f"scene {body['slug']!r} already exists")
        scenes_folder = self._folder_under(project["root"], "scenes")
        folder = self._create_node(scenes_folder["id"], body["slug"], "folder")
        scene_id = "scene-" + str(uuid.uuid4())
        record = {"id": scene_id, "lib": self.lib, "project": project["id"],
                  "slug": body["slug"], "title": body.get("title") or "",
                  "setting": body.get("setting") or "",
                  "defaults": body.get("defaults") or {},
                  "status": "planned", "created": _now(), "updated": _now(),
                  "folder": folder["id"], "characters": [], "output": None,
                  "stitch": None, "assembled": None}
        self.scenes[scene_id] = record
        self.shots[scene_id] = []
        if body.get("shots"):
            self._merge_shots(scene_id, body["shots"], body)
        self._restate(scene_id)
        return self._scene_view(record)

    def _merge_shots(self, scene_id: str, shots: list[dict], plan: dict | None = None) -> None:
        """Normalise, validate, merge by shot id, and derive each shot's status.

        **All four are the API's**, and this mirrors it rather than approximating
        it: `_storyboard()` is the backend's own module, loaded by path. A fake
        that merged without normalising would accept a raw plan the real service
        turns into something else, and every test would agree with the fake.
        """
        SB = _storyboard()
        scene = self.scenes[scene_id]
        envelope = plan or {}
        doc = SB.normalise(
            {**{k: envelope.get(k, scene.get(k)) for k in ("setting", "defaults")},
             "shots": shots},
            scene.get("slug") or scene_id,
        )
        SB.validate(doc)

        existing = {s["id"]: s for s in self.shots.setdefault(scene_id, [])}
        merged = []
        for order, spec in enumerate(doc["shots"], 1):
            shot_id = spec["id"]
            previous = existing.get(shot_id, {})
            row = {**previous, **spec,
                   "id": shot_id, "order": spec.get("order") or order * ORDER_GAP}
            deeper = SB.merge_panels(previous, spec)
            if deeper is not None:
                row["panels"] = deeper
            row.setdefault("run", None)
            row.setdefault("panel", None)
            if not row.get("opens_on"):
                row["opens_on"] = {"node": None, "from_run": None}
            row["status"] = SB.shot_status(row)
            merged.append(row)
        self.shots[scene_id] = merged

    def _restate(self, scene_id: str) -> None:
        """Re-derive the scene's status from its shots, as every write route does."""
        SB = _storyboard()
        record = self.scenes[scene_id]
        record["status"] = SB.scene_status(
            {**record, "shots": self.shots.get(scene_id, [])})

    def _r_scene(self, method, body, params, scene_id):
        record = self.scenes.get(scene_id)
        if record is None:
            raise FakeError(404, f"no such scene: {scene_id}")
        if method == "GET":
            return self._scene_view(record)
        if method == "PATCH":
            record.update(body)
            record["updated"] = _now()
            return self._scene_view(record)
        if method == "DELETE":
            self.scenes.pop(scene_id)
            self.shots.pop(scene_id, None)
            if params.get("files") == "delete":
                self._delete_node(record["folder"])
            return {"deleted": scene_id}
        raise FakeError(405, method)

    def _r_shots(self, method, body, params, scene_id):
        if scene_id not in self.scenes:
            raise FakeError(404, f"no such scene: {scene_id}")
        if method == "GET":
            return {"shots": sorted(self.shots.get(scene_id, []),
                                    key=lambda s: s["order"])}
        if method != "PATCH":
            raise FakeError(405, method)
        self._merge_shots(scene_id, body["shots"])
        self._restate(scene_id)
        return self._scene_view(self.scenes[scene_id])

    def _r_shot(self, method, body, params, scene_id, shot_id):
        shot = next((s for s in self.shots.get(scene_id, []) if s["id"] == shot_id), None)
        if shot is None:
            raise FakeError(404, f"no shot {shot_id} in {scene_id}")
        shot.update(body)
        shot["status"] = _storyboard().shot_status(shot)
        self._restate(scene_id)
        return shot

    def _r_scene_output(self, method, body, params, scene_id):
        record = self.scenes[scene_id]
        folder = self._folder_under(record["folder"], "output")
        node = self._child(folder["id"], body["name"]) or \
            self._create_node(folder["id"], body["name"], "file")
        node["pending"] = {"size": body["size"], "content_type": body["content_type"]}
        return {"node": node["id"], "url": f"memory://{node['blob_key']}",
                "headers": {"Content-Type": body["content_type"],
                            "Content-Length": str(body["size"])}}

    def _movie_view(self, record: dict) -> dict:
        """`scenes` EXPANDED, in order, exactly as `GET /api/movies/<id>` sends.

        This returned the raw id list off the record. The real route resolves
        each cut to `{id, slug, title, status, output, thumb}` — so a client
        written against this double and run against the service would read a
        string where it expected a row. The same divergence, one entity over,
        that `character_slugs` already cost three bugs for.

        Duplicates and order survive because the list is what carries them: a
        movie may cut one scene twice as a reprise.
        """
        rows = []
        for scene_id in record.get("scenes") or []:
            scene = self.scenes.get(scene_id) or {}
            # `output` is `{"node": id}` now and a bare id on everything written
            # before it was — `support.output_node` normalises both on the way
            # out, and a double that read only one of them would crash on rows
            # the service serves happily.
            stored = scene.get("output")
            node = stored.get("node") if isinstance(stored, dict) else stored
            drawable = None
            if node:
                drawable = {"node": node,
                            "name": self.nodes.get(node, {}).get("name"),
                            "url": f"memory://{self.nodes.get(node, {}).get('blob_key')}"}
            rows.append({"id": scene_id, "slug": scene.get("slug"),
                         "title": scene.get("title"), "status": scene.get("status"),
                         "output": drawable, "thumb": drawable})
        return {**record, "scenes": rows}

    def _r_movies(self, method, body, params):
        if method == "GET":
            found = list(self.movies.values())
            if params.get("project"):
                project = self._entity(self.projects, params["project"], "project")
                found = [m for m in found if m["project"] == project["id"]]
            return {"movies": [self._movie_view(m) for m in
                               sorted(found, key=lambda m: m["created"])],
                    "cursor": None}
        if method != "POST":
            raise FakeError(405, method)
        project = self._entity(self.projects, body["project"], "project")
        movies_folder = self._folder_under(project["root"], "movies")
        folder = self._create_node(movies_folder["id"], _unique(
            self, movies_folder["id"], body["slug"]), "folder")
        movie_id = "movie-" + str(uuid.uuid4())
        record = {"id": movie_id, "lib": self.lib, "project": project["id"],
                  "slug": body["slug"], "title": body.get("title") or "",
                  "status": "planned", "created": _now(), "updated": _now(),
                  "folder": folder["id"], "scenes": list(body.get("scenes") or []),
                  "characters": [], "output": None, "stitch": None}
        self.movies[movie_id] = record
        return self._movie_view(record)

    def _r_movie(self, method, body, params, movie_id):
        record = self.movies.get(movie_id)
        if record is None:
            raise FakeError(404, f"no such movie: {movie_id}")
        if method == "GET":
            return self._movie_view(record)
        if method == "PATCH":
            record.update(body)
            record["updated"] = _now()
            return self._movie_view(record)
        if method == "DELETE":
            self.movies.pop(movie_id)
            if params.get("files") == "delete":
                self._delete_node(record["folder"])
            return {"deleted": movie_id}
        raise FakeError(405, method)

    def _r_movie_scenes(self, method, body, params, movie_id):
        record = self.movies[movie_id]
        # Every entry is validated as a scene id, as the route does. This used
        # to store whatever it was handed, so the CLI passing a list of dicts
        # round-tripped happily here and 500'd against the service.
        for scene_id in body["scenes"]:
            if not isinstance(scene_id, str):
                raise FakeError(400, f"scenes must be ids, got {type(scene_id).__name__}")
            if scene_id not in self.scenes:
                raise FakeError(404, f"no such scene: {scene_id}")
        record["scenes"] = list(body["scenes"])
        return self._movie_view(record)

    def _r_movie_output(self, method, body, params, movie_id):
        record = self.movies[movie_id]
        folder = self._folder_under(record["folder"], "output")
        node = self._child(folder["id"], body["name"]) or \
            self._create_node(folder["id"], body["name"], "file")
        node["pending"] = {"size": body["size"], "content_type": body["content_type"]}
        return {"node": node["id"], "url": f"memory://{node['blob_key']}",
                "headers": {"Content-Type": body["content_type"],
                            "Content-Length": str(body["size"])}}

    # ── renders ─────────────────────────────────────────────────────────────
    #
    # **SYNCHRONOUS, AND THAT IS THE ONE PLACE THIS FAKE IS NOT THE SERVICE.**
    #
    # In production a render is a row plus a message plus a worker Lambda with
    # ffmpeg in its image. Here the work happens inside the POST and the row
    # comes back already `succeeded`, so the CLI's poll loop reads a terminal
    # status on its first `GET` and the suite runs in milliseconds.
    #
    # What that still proves is everything this package is responsible for: that
    # the right kind was asked for, with the parts in the right ORDER, resolved
    # to node ids, against the right destination — and that the record the worker
    # writes is the record the CLI then reads back rather than one it asserted
    # for itself. What it cannot prove is the encode, which is the backend's
    # suite's job and not this one's.
    #
    # No ffmpeg here, deliberately: this package does not depend on it any more,
    # and installing it to test a wheel that has dropped it would defeat the
    # change. A cut is a placeholder file with a real size.

    def _render_result(self, kind, params):
        if kind == "assemble":
            return self._render_assemble(params)
        if kind in ("frame", "grid"):
            return self._render_still(kind, params)
        if kind == "sheet":
            return self._render_sheet(params)
        raise FakeError(400, f"'{kind}' is not a render kind")

    def _render_parts(self, params):
        parts = params.get("parts")
        if not isinstance(parts, list) or not parts:
            raise FakeError(400, "parts must be a non-empty list")
        for part in parts:
            if not isinstance(part, dict) or part.get("node") not in self.nodes:
                raise FakeError(404, f"no such node: {(part or {}).get('node')}")
        return parts

    def _render_asset(self, node):
        record = self.nodes[node]
        return {"node": node, "name": record["name"],
                "size": record.get("size") or 0,
                "content_type": record.get("content_type")}

    def _render_assemble(self, params):
        target = params.get("target") or ""
        parts = self._render_parts(params)
        store, child, stem, label = (
            (self.scenes, "shots", "shot", "shots") if target.startswith("scene-")
            else (self.movies, "scenes", "scene", "scenes"))
        record = store.get(target)
        if record is None:
            raise FakeError(404, f"no such target: {target}")

        folder = self._folder_under(record["folder"], child)
        for n, part in enumerate(parts, 1):
            name = self.nodes[part["node"]]["name"]
            ext = ("." + name.rsplit(".", 1)[-1]) if "." in name else ".mp4"
            part["n"] = n
            part["duration"] = 5.0
            # A real copy, not a second node on one blob: copy-on-write is what
            # the CLI's own comment says this must not be.
            part["copy"] = self.put_file(
                folder["id"], _unique_file(self, folder["id"], f"{stem}-{n:02d}{ext}"),
                b"fake cut part")["id"]

        info = {"method": "concat demuxer, stream copy (no re-encode)",
                f"uniform_{label}": True,
                "cuts": [{"n": p["n"], "node": p["copy"], "duration": p["duration"],
                          **{k: p[k] for k in ("run", "scene", "shot", "slug") if k in p}}
                         for p in parts]}

        slug = record.get("slug") or record["id"]
        was = record.get("output")
        was_node = was.get("node") if isinstance(was, dict) else was
        take = len(record.get("cuts") or []) + (1 if was_node else 0) + 1
        name = f"{slug}.mp4" if take == 1 else f"{slug}-{take}.mp4"
        out_folder = self._folder_under(record["folder"], "output")["id"]
        output = self.put_file(out_folder, _unique_file(self, out_folder, name),
                               b"fake stitched cut")

        cuts = list(record.get("cuts") or [])
        if was_node and was_node != output["id"] and \
                not any(c.get("node") == was_node for c in cuts):
            stored = {} if isinstance(was, str) else dict(was or {})
            cuts = [{**stored, "node": was_node}, *cuts]

        record.update({"output": {"node": output["id"], "duration": 10.0},
                       "stitch": info, "cuts": cuts, "assembled": _now(),
                       "status": "assembled", "updated": _now()})
        if params.get("characters") is not None:
            record["characters"] = sorted(set(params["characters"]))

        # The shot rows the worker writes back. A part with no `shot` was
        # appended with `--shot <runref>` against a scene with no plan; there is
        # no row to update and nothing is invented for it.
        for part in parts:
            if not part.get("shot"):
                continue
            for shot in self.shots.get(target) or []:
                if shot.get("id") == part["shot"]:
                    shot.update({"n": part["n"], "node": part["node"],
                                 "shot_node": part["copy"],
                                 "duration": part["duration"]})
        return {"output": self._render_asset(output["id"]), "stitch": info,
                "target": target, "re_encoded": False}

    def _render_still(self, kind, params):
        node = params.get("node")
        if node not in self.nodes:
            raise FakeError(404, f"no such node: {node}")
        dest = self.nodes.get(params.get("dest") or "")
        if dest is None or dest["kind"] != "folder":
            raise FakeError(400, f"{params.get('dest')} is not a folder")
        # `create_numbered`, as the service uses — a produced file whose name is
        # taken lands beside the first rather than 409ing a job that would then
        # fail identically on every redrive.
        made = self.put_file(
            dest["id"], _unique_file(self, dest["id"], params.get("name") or "frame.png"),
            _placeholder_image(), content_type="image/png")
        if kind == "frame":
            return {"frame": self._render_asset(made["id"])}
        return {"grid": self._render_asset(made["id"]),
                "sampled_at": [round(i + 0.5, 2) for i in range(params.get("count") or 4)]}

    def _render_sheet(self, params):
        parts = self._render_parts(params)
        dest = self.nodes.get(params.get("dest") or "")
        if dest is None or dest["kind"] != "folder":
            raise FakeError(400, f"{params.get('dest')} is not a folder")
        # **Given captions are kept in the order they were given.** A board reads
        # in shot order and a payload review's tile N is what a prompt cites as
        # `[ImageN]`; sorting them would renumber the thing the sheet says.
        captions = [part.get("caption") or self.nodes[part["node"]]["name"]
                    for part in parts]
        made = self.put_file(
            dest["id"], _unique_file(self, dest["id"], params.get("name") or "sheet.png"),
            _placeholder_image(), content_type="image/png")
        cols = params.get("cols") or 5
        cell = params.get("cell") or 300
        rows = (len(parts) + cols - 1) // cols
        return {"sheet": self._render_asset(made["id"]),
                "width": cols * cell, "height": rows * (cell + max(20, cell // 12)),
                "tiles": len(parts), "cols": cols, "cell": cell,
                "captions": captions, "unreadable": []}

    def _r_renders(self, method, body, params):
        if method != "POST":
            raise FakeError(405, method)
        if self.renders_refused:
            raise FakeError(500, self.renders_refused)
        kind = body.get("kind") or ""
        render_id = "render-" + str(uuid.uuid4())
        row = {"id": render_id, "lib": self.lib, "kind": kind,
               "params": body.get("params") or {}, "status": "queued",
               "result": None, "error": None, "created": _now(), "updated": _now()}
        self.renders[render_id] = row
        try:
            row["result"] = self._render_result(kind, body.get("params") or {})
        except FakeError:
            raise
        row.update({"status": "succeeded", "updated": _now()})
        return row

    def _r_render(self, method, body, params, render_id):
        if method != "GET":
            raise FakeError(405, method)
        row = self.renders.get(render_id)
        if row is None:
            raise FakeError(404, f"no such render: {render_id}")
        return row

    # ── images ──────────────────────────────────────────────────────────────
    #
    # Synchronous in the service too, so this fake is doing what the route does:
    # read the bytes, run Pillow, write a new node. The source is never modified.

    def _image_source(self, body):
        node = self.nodes.get(body.get("node") or "")
        if node is None or node["kind"] != "file":
            raise FakeError(404, f"no such node: {body.get('node')}")
        data = self.s3.get_object(Bucket=BUCKET, Key=node["blob_key"])["Body"].read()
        return node, data

    def _image_target(self, body, node):
        wanted = body.get("to")
        ext_for = {"png": ".png", "jpg": ".jpg", "jpeg": ".jpg", "webp": ".webp"}
        formats = {".png": "PNG", ".jpg": "JPEG", ".webp": "WEBP"}
        if wanted:
            if wanted not in ext_for:
                raise FakeError(400, f"cannot convert to '{wanted}'")
            ext = ext_for[wanted]
        else:
            found = ("." + node["name"].rsplit(".", 1)[-1].lower()) \
                if "." in node["name"] else ""
            ext = found if found in formats else ".png"
        dest = body.get("dest") or node["parent_id"]
        if dest not in self.nodes or self.nodes[dest]["kind"] != "folder":
            raise FakeError(400, f"{dest} is not a folder")
        stem = node["name"].rsplit(".", 1)[0] if "." in node["name"] else node["name"]
        return ext, formats[ext], dest, (body.get("name") or f"{stem}{ext}")

    def _image_write(self, dest, name, data, ext):
        types = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
        made = self.put_file(dest, _unique_file(self, dest, name), data,
                             content_type=types.get(ext))
        return {"node": made["id"], "name": made["name"], "size": len(data),
                "content_type": types.get(ext)}

    def _r_image_convert(self, method, body, params):
        if method != "POST":
            raise FakeError(405, method)
        import io

        from PIL import Image

        node, data = self._image_source(body)
        ext, fmt, dest, name = self._image_target(body, node)
        image = Image.open(io.BytesIO(data))
        if ext == ".jpg" and image.mode in ("RGBA", "P", "LA"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, fmt, **({"quality": body.get("quality") or 95}
                                   if ext in (".jpg", ".webp") else {}))
        out = buffer.getvalue()
        return {"image": self._image_write(dest, name, out, ext),
                "source": {"node": node["id"], "bytes": len(data)},
                "bytes": len(out)}

    def _r_image_crop(self, method, body, params):
        if method != "POST":
            raise FakeError(405, method)
        import io

        from PIL import Image

        node, data = self._image_source(body)
        ext, fmt, dest, name = self._image_target(body, node)
        try:
            wanted = tuple(int(float(v)) for v in str(body.get("box") or "").split(","))
        except ValueError:
            raise FakeError(400, "box must be four numbers") from None
        if len(wanted) != 4:
            raise FakeError(400, "box takes four numbers, LEFT,TOP,RIGHT,BOTTOM")
        image = Image.open(io.BytesIO(data))
        inside = (max(0, min(wanted[0], image.width)),
                  max(0, min(wanted[1], image.height)),
                  max(0, min(wanted[2], image.width)),
                  max(0, min(wanted[3], image.height)))
        if inside[2] <= inside[0] or inside[3] <= inside[1]:
            raise FakeError(400, f"box {','.join(str(v) for v in wanted)} is entirely "
                                 f"outside the {image.width}x{image.height} image.")
        cut = image.crop(inside)
        if ext == ".jpg" and cut.mode in ("RGBA", "P", "LA"):
            cut = cut.convert("RGB")
        buffer = io.BytesIO()
        cut.save(buffer, fmt, **({"quality": body.get("quality") or 95}
                                 if ext in (".jpg", ".webp") else {}))
        out = buffer.getvalue()
        return {"image": self._image_write(dest, name, out, ext),
                "source": {"node": node["id"], "bytes": len(data),
                           "width": image.width, "height": image.height},
                "requested": list(wanted), "box": list(inside),
                "clamped": inside != wanted,
                "width": cut.width, "height": cut.height}

    # ── phrasebook ──────────────────────────────────────────────────────────

    def _r_phrasebook(self, method, body, params):
        if method == "GET":
            model = params.get("model")
            # `{"terms": [...]}`, which is what the route returns. This answered
            # a BARE LIST, and the difference is the whole reason the CLI read an
            # empty phrasebook against every real library while the suite passed:
            # `entities.phrasebook` sent the response through `_as_list`, which
            # answers `[]` for anything that is not a list.
            return {"terms": [t for t in self.terms
                              if not model or t["model"] == model]}
        if method != "POST":
            raise FakeError(405, method)
        if any(t["model"] == body["model"] and t["avoid"] == body["avoid"]
               for t in self.terms):
            raise FakeError(409, f"{body['avoid']!r} is already recorded for "
                                 f"{body['model']}")
        # `created`, matching `catalog.add_term`. This said `added` and a
        # date-only stamp, which the real backend has never written — the fake
        # was the more capable of the two, so the suite passed while
        # `phrasebook show` printed no dates at all against a real library.
        term = {"model": body["model"], "avoid": body["avoid"], "use": body["use"],
                "note": body.get("note") or "", "replicate": body.get("replicate"),
                "created": _now()}
        self.terms.append(term)
        return term

    def _r_phrasebook_term(self, method, body, params, model, avoid):
        model = urllib.parse.unquote(model)
        avoid = urllib.parse.unquote(avoid)
        term = next((t for t in self.terms
                     if t["model"] == model and t["avoid"] == avoid), None)
        if term is None:
            raise FakeError(404, f"no phrasebook term {avoid!r} for {model}")
        self.terms.remove(term)
        return {"deleted": avoid}

    # ── the reference spec ──────────────────────────────────────────────────
    #
    # `{"blocks": {...}, "angles": [...]}`, which is the shape the route returns.
    # Answering a bare list here is the exact mistake the phrasebook handler
    # above records: the fake was more forgiving than the service, so the suite
    # passed while the CLI read nothing.

    def _r_reference_spec(self, method, body, params):
        if method != "GET":
            raise FakeError(405, method)
        angles = sorted(self.spec_angles.values(),
                        key=lambda a: (a.get("order") or 0, a["id"]))
        return {"blocks": dict(self.spec_blocks), "angles": angles}

    def _r_spec_block(self, method, body, params, name):
        name = urllib.parse.unquote(name)
        if method == "PATCH":
            self.spec_blocks[name] = body["text"]
            return {"name": name, "text": body["text"], "updated": _now()}
        if method == "DELETE":
            self.spec_blocks.pop(name, None)
            return {"name": name, "deleted": True}
        raise FakeError(405, method)

    def _r_spec_angle(self, method, body, params, angle_id):
        angle_id = urllib.parse.unquote(angle_id)
        if method == "PATCH":
            record = {k: v for k, v in body.items() if k != "id"}
            self.spec_angles[angle_id] = {"id": angle_id, **record}
            return self.spec_angles[angle_id]
        if method == "DELETE":
            self.spec_angles.pop(angle_id, None)
            return {"id": angle_id, "deleted": True}
        raise FakeError(405, method)

    # ── seeding ─────────────────────────────────────────────────────────────

    def put_file(self, parent_id: str, name: str, body: bytes,
                 content_type: str | None = None) -> dict:
        """Create a confirmed file node with bytes. For fixtures only.

        **Confirmed means the checksum too.** A fixture that set `size` and not
        the hash would look confirmed to a listing and unconfirmed to
        `curate dedupe`, which would quietly fall back to downloading — and the
        test asserting it does not download would be the one that broke.
        """
        node = self._create_node(parent_id, name, "file")
        node["size"] = len(body)
        node["checksum"] = hashlib.md5(body).hexdigest()
        node["content_type"] = (content_type
                                or mimetypes.guess_type(name)[0]
                                or "application/octet-stream")
        if node["content_type"].startswith(REEL_TYPES):
            node["reel"] = self.lib
        self.s3.put_object(Bucket=BUCKET, Key=node["blob_key"], Body=body)
        return node

    def put_shared(self, key: str, body: bytes) -> dict:
        """An angle image, as the ordinary node it now is.

        Named `put_shared` still because "shared" is what these are — they
        belong to the library rather than to any character or project — but
        there is nothing special about how they are stored. The key is a name
        path under `config/`, every folder in it is created, and the result is a
        node like any other. It used to write a side dict the fake served from
        `GET /api/asset?key=`, which is the parameter the entity model deleted.
        """
        parts = [p for p in key.strip("/").split("/") if p]
        parent = self.root["id"]
        for segment in parts[:-1]:
            existing = self._child(parent, segment)
            parent = (existing or self._create_node(parent, segment, "folder"))["id"]
        return self.put_file(parent, parts[-1], body)


_NUM_RE = re.compile(r"(\d+)")


def _natural(name: str):
    return [int(p) if p.isdigit() else p.lower() for p in _NUM_RE.split(name)]


def _unique_file(fake: FakeApi, parent_id: str, name: str) -> str:
    """A file name free in this parent, as `catalog.create_numbered` produces.

    `frame (2).png`, not `frame-2.png`: a clash on a produced file is resolved by
    the catalog's own numbering, and a double that spelled it differently would
    let a test assert a name the service never writes.
    """
    if not fake._child(parent_id, name):
        return name
    stem, dot, ext = name.rpartition(".")
    stem, ext = (stem, dot + ext) if dot else (name, "")
    for n in itertools.count(2):
        candidate = f"{stem} ({n}){ext}"
        if not fake._child(parent_id, candidate):
            return candidate
    raise AssertionError("unreachable")


def _unique(fake: FakeApi, parent_id: str, name: str) -> str:
    """A folder name free in this parent.

    A scene or a movie is named for its slug, which is a human label and need
    not be unique, so two may legitimately want the same folder name. The API
    disambiguates; the record names the folder either way, so nothing downstream
    notices. A RUN does not come through here — it has no slug and its folder is
    named for its id.
    """
    if not fake._child(parent_id, name):
        return name
    for n in itertools.count(2):
        candidate = f"{name}-{n}"
        if not fake._child(parent_id, candidate):
            return candidate
    raise AssertionError("unreachable")
