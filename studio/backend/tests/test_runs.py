"""Runs: the envelope studio owns, the payload it does not, and hard rule #3.

A run used to be a folder named `<ts>_<slug>` holding three JSON documents nobody
was allowed to parse. Two things followed, and both are what these tests are
about:

* the app could show a run as a folder and nothing else, and
* `runs find --character` meant listing every project, listing every run in each,
  reading `request.json` for each, and grepping.

**The split that makes a run presentable without making this service a liar** is
the envelope — status, model, timings, bindings as node ids, outputs, lineage,
cost — beside a payload that is stored verbatim and never decoded. The old rule
is not weakened; it is moved to where it is actually true.

**Hard rule #3 moved here with the bindings.** S3 is the only origin: anything
sent to a model must already be an S3 object. That was enforced in the pipeline's
`runs.py`, which only the CLI goes through; it is enforced at the API now, which
is the only thing *both* halves of studio pass through.
"""

import pytest

from studio_core import config
from studio_core.services import catalog, layout
from tests.conftest import CATALOG_LIBRARY


def _item(client, pk, sk):
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


def _project(api, slug="rooftop-teaser", **body):
    return api.post("/api/projects", json={"slug": slug, **body}).get_json()


def _character(api, slug="subject-a"):
    return api.post("/api/characters", json={"slug": slug, "fictional": True}).get_json()


def _uploaded(api, parent_id, name, body=b"webp-bytes"):
    node = api.post(
        "/api/nodes", json={"parent": parent_id, "name": name, "kind": "file"}
    ).get_json()
    record = catalog.node(node["id"])
    return catalog.set_blob(
        node["id"], record["blob_key"], size=len(body), content_type="image/webp"
    )


def _create(api, project, **body):
    resp = api.post(
        "/api/runs",
        json={
            **{
                "project": project["id"],
                "kind": "image",
                "engine": "nano-banana-pro",
                "model": "google/nano-banana-pro",
            },
            **body,
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _child(parent_id, name):
    return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])


# ──────────────────────── the envelope, in one write ────────────────────────


def test_creating_a_run_writes_envelope_listing_row_folder_and_output(empty_api, catalog_table):
    """**One transaction: the envelope, the project's listing row, and the tree.**

    A run is recorded *before* it is submitted, which is the reason
    `request.json` and `result.json` were two writes and are two calls here: a
    prediction that times out, or a process that is killed, leaves an envelope
    saying `pending` with the exact input beside it rather than nothing at all.
    """
    project = _project(empty_api)

    run = _create(empty_api, project, input={"prompt": "a rooftop", "aspect_ratio": "9:16"})

    envelope = _item(catalog_table, f"RUN#{run['id']}", "META")
    assert envelope["status"]["S"] == "pending"
    assert envelope["project"]["S"] == project["id"]
    assert envelope["model"]["S"] == "google/nano-banana-pro"

    listing = catalog.project_entities(project["id"], catalog.ENTITY_RUN)
    assert [row["id"] for row in listing] == [run["id"]]
    assert listing[0]["status"] == "pending"

    # **A run has no slug, so its folder is named for its id.** The record names
    # the folder's node id either way, which is what stops a rename above it
    # stranding anything. The label it used to carry was `<timestamp>_<hint>` —
    # unique only by embedding `created`, a column the row already has.
    assert "slug" not in envelope, "a run envelope carries no slug"
    folder = catalog.node(run["folder"])
    assert folder["name"] == run["id"]
    assert folder["entity"] == run["id"]
    assert _child(run["folder"], layout.OUTPUT_FOLDER)["kind"] == "folder"


def test_the_listing_row_is_the_one_deliberate_projection(empty_api):
    """Safe **because a run is immutable once it completes.**

    There is nothing left to keep in step, and the runs grid would otherwise need
    a `BatchGetItem` over hundreds of envelopes to draw thumbnails. Do not copy
    this reasoning onto a slug claim, where the opposite is true.
    """
    project = _project(empty_api)
    _create(empty_api, project)

    row = catalog.project_entities(project["id"], catalog.ENTITY_RUN)[0]

    assert set(row) >= {"id", "status", "model", "kind", "created", "lib"}
    # Not the whole envelope: no bindings, no payload, no lineage.
    assert "bindings" not in row and "payload" not in row


# The fields the SPA's `RunSummary` declares required, in
# `studio/frontend/src/types/index.ts`. Kept here as a literal on purpose: the
# two halves cannot import from each other, so the contract is asserted rather
# than shared, and a field added to one without the other fails right here.
RUN_SUMMARY_REQUIRED = {"id", "project", "status", "kind", "model", "created"}


def test_the_listing_row_carries_every_field_the_spa_declares(empty_api):
    """**The row and `RunSummary` must not drift. They did, and it reached prod.**

    `RunSummary` declared `slug` and the projection never wrote one, so
    `studio runs list` raised `KeyError: 'slug'` against the real API and the
    web runs grid rendered an empty label column. Nothing failed, because the
    only thing exercising a listing row in tests was a fake that projected off
    the full record — more generous than the API it stood in for.

    So this asserts against the API's own output, over a run driven through its
    real transitions, and it is the check that was missing.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)
    empty_api.patch(f"/api/runs/{run['id']}", json={"status": "succeeded",
                                                    "cost": {"currency": "USD",
                                                             "amount": 0.032}})

    rows = empty_api.get(f"/api/runs?project={project['id']}").get_json()["runs"]

    assert len(rows) == 1
    missing = RUN_SUMMARY_REQUIRED - set(rows[0])
    assert not missing, (
        f"the runs listing row is missing {sorted(missing)}, which RunSummary "
        "declares required — the SPA renders them and the CLI indexes them")
    assert "slug" not in rows[0], "a run has no slug; nothing may render one"


def test_the_character_usage_rows_are_written_in_the_same_transaction(empty_api, catalog_table):
    """A link written afterwards is a link a crash can lose.

    "Which runs used this character" has to be true the moment the run exists,
    because it is the query that replaces a walk over every run folder.
    """
    character = _character(empty_api)
    project = _project(empty_api, characters=[character["id"]])

    run = _create(empty_api, project, characters=[character["id"]])

    assert _item(catalog_table, f"RUN#{run['id']}", f"CHAR#{character['id']}") is not None


def test_the_run_folder_is_resolved_by_name_and_made_if_absent(empty_api):
    """**Self-healing, and every existing run stays reachable.**

    If somebody renamed `runs/` last week a new one appears — and the run
    recorded before it is still perfectly reachable, because its record names its
    own folder node id rather than a path. That is the property the whole
    "layout is convention" reading rests on.
    """
    project = _project(empty_api)
    first = _create(empty_api, project)
    runs_folder = _child(project["root"], layout.RUN_PARENT)
    empty_api.patch(f"/api/nodes/{runs_folder['node_id']}", json={"name": "old-runs"})

    second = _create(empty_api, project, slug="second-portrait")

    remade = _child(project["root"], layout.RUN_PARENT)
    assert remade["node_id"] != runs_folder["node_id"]
    assert catalog.node(second["folder"])["parent_id"] == remade["node_id"]
    assert empty_api.get(f"/api/runs/{first['id']}").status_code == 200


# ──────────────────── hard rule #3: S3 is the only origin ────────────────────


@pytest.mark.parametrize(
    "binding",
    [
        "https://replicate.delivery/pbxt/abc/out.png",
        "http://example.com/x.png",
        "s3://bucket/key.png",
        "data:image/png;base64,AAAA",
    ],
)
def test_a_url_shaped_binding_is_refused(empty_api, binding):
    """**The rule moved from the CLI to the API, which is a strengthening.**

    It used to live in the pipeline's `runs.py`, which only the CLI goes through;
    the API is the only thing both halves of studio pass through, so the SPA is
    covered by it now too.

    The check is deliberately coarse — anything with a scheme separator — because
    a narrow `^https?://` would pass `data:` and `s3://`, and none of those is a
    node id either. The refusal carries a machine-readable code because the client
    has to act on it: upload the bytes first.
    """
    project = _project(empty_api)

    resp = empty_api.post(
        "/api/runs",
        json={
            "project": project["id"],
            "slug": "rooftop-portrait",
            "kind": "image",
            "model": "google/nano-banana-pro",
            "bindings": {"image_input": [binding]},
        },
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_binding"
    assert "image_input[0]" in resp.get_json()["message"]


def test_a_refused_binding_writes_nothing(empty_api):
    """Validated before the transaction, so a bad request leaves no half-run.

    A run folder with no envelope behind it is exactly the orphaned state the
    single transaction exists to prevent.
    """
    project = _project(empty_api)
    empty_api.post(
        "/api/runs",
        json={
            "project": project["id"],
            "slug": "rooftop-portrait",
            "kind": "image",
            "model": "google/nano-banana-pro",
            "bindings": {"image_input": ["https://example.com/x.png"]},
        },
    )

    assert catalog.children(_child(project["root"], layout.RUN_PARENT)["node_id"]) == []
    assert catalog.project_entities(project["id"], catalog.ENTITY_RUN) == []


def test_a_binding_naming_no_node_is_refused(empty_api):
    """The honest second half of the rule.

    A binding naming nothing is a run that fails at submission with a message
    from the provider rather than from here — which is a diagnosis a person has
    to work backwards from.
    """
    project = _project(empty_api)

    resp = empty_api.post(
        "/api/runs",
        json={
            "project": project["id"],
            "slug": "rooftop-portrait",
            "kind": "image",
            "model": "google/nano-banana-pro",
            "bindings": {"image_input": ["node-nobody"]},
        },
    )

    assert resp.status_code == 400
    assert "names no node" in resp.get_json()["error"]


def test_bindings_are_stored_as_node_ids(empty_api, catalog_table):
    """Node ids, so renaming or moving the file they name strands nothing.

    That is the property `domain/rewrite.py` existed to patch up and no longer
    can be needed for.
    """
    character = _character(empty_api)
    project = _project(empty_api)
    reference = _child(character["root"], "reference")
    picture = _uploaded(empty_api, reference["node_id"], "front.webp")

    run = _create(empty_api, project, bindings={"image_input": [picture["node_id"]]})
    empty_api.patch(f"/api/nodes/{picture['node_id']}", json={"name": "renamed.webp"})

    envelope = _item(catalog_table, f"RUN#{run['id']}", "META")
    assert [entry["S"] for entry in envelope["bindings"]["M"]["image_input"]["L"]] == [
        picture["node_id"]
    ]
    fetched = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert fetched["bindings"]["image_input"][0]["name"] == "renamed.webp"


# ─────────────────────── the payload, never decoded ───────────────────────


def test_the_request_document_is_stored_verbatim_and_served_as_text(empty_api):
    """**Studio re-encodes the input it was handed and never reads a key inside.**

    The pipeline owns the shape of `request.json` and changes it freely, so
    anything here that parsed one would become wrong without notice. It comes
    back through `GET /api/nodes/<id>/text`, which is the path with no code that
    could decode it.
    """
    project = _project(empty_api)

    run = _create(empty_api, project, input={"prompt": "a rooftop", "resolution": "4k"})

    assert run["payload"]["request"] is not None
    text = empty_api.get(f"/api/nodes/{run['payload']['request']}/text").get_json()
    assert text["name"] == "request.json"
    assert '"prompt": "a rooftop"' in text["content"]
    # `text/plain`, not `application/json`: a JSON content type is an invitation
    # to a browser — or a future contributor — to decode it.
    assert catalog.node(run["payload"]["request"])["content_type"].startswith("text/plain")


def test_the_provider_response_is_stored_as_its_own_blob(empty_api):
    """Its own route because it is bytes rather than an envelope field.

    It is the half of a run this service is forbidden to have an opinion about.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)

    resp = empty_api.post(
        f"/api/runs/{run['id']}/response", json={"body": {"output": ["https://x/y.png"]}}
    )

    assert resp.status_code == 201
    node = resp.get_json()["node"]
    assert "https://x/y.png" in empty_api.get(f"/api/nodes/{node}/text").get_json()["content"]
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["payload"]["response"] == node


# ──────────────────────── moving a run forward ────────────────────────


def test_patching_a_run_updates_the_listing_row_in_the_same_transaction(empty_api):
    """A grid must never show `pending` for a run whose envelope says `succeeded`.

    Two writes that could be interrupted between them would produce exactly that,
    on the screen a person looks at most.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)

    resp = empty_api.patch(
        f"/api/runs/{run['id']}",
        json={"status": "succeeded", "prediction_id": "s7k2m9x4qwe1"},
    )

    assert resp.status_code == 200
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["status"] == "succeeded"
    assert catalog.project_entities(project["id"], catalog.ENTITY_RUN)[0]["status"] == "succeeded"


def test_a_run_takes_no_rev_and_that_is_deliberate(empty_api):
    """**A run is written by the machine that submitted it, in a fixed sequence.**

    A character is edited by a person, twice at once, and losing somebody's
    paragraph is what optimistic concurrency exists to prevent. The only
    concurrent writer of a run is a second attempt at the same transition —
    demanding a `rev` there would make the CLI re-read a record to report that a
    prediction finished.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)

    assert empty_api.patch(
        f"/api/runs/{run['id']}", json={"status": "running"}
    ).status_code == 200
    assert empty_api.patch(
        f"/api/runs/{run['id']}", json={"status": "succeeded"}
    ).status_code == 200


def test_an_unknown_status_is_refused(empty_api):
    """Studio owns this word — the one thing about a submission it has an opinion on."""
    project = _project(empty_api)
    run = _create(empty_api, project)

    assert empty_api.patch(
        f"/api/runs/{run['id']}", json={"status": "probably-fine"}
    ).status_code == 400


def test_a_float_cost_round_trips_exactly(empty_api):
    """**DynamoDB refuses a Python float outright, and this is where one arrives.**

    `TypeSerializer` will not guess a binary-float rounding, so `{"amount": 0.032}`
    from a JSON body has to be converted — through `Decimal(str(...))`, so 0.032
    is stored as 0.032 and not as the seventeen digits its binary representation
    actually is. Nothing in this table held a float until a run started recording
    what a prediction cost.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)

    resp = empty_api.patch(
        f"/api/runs/{run['id']}",
        json={"status": "succeeded", "cost": {"currency": "USD", "amount": 0.032}},
    )

    assert resp.status_code == 200
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["cost"] == {
        "currency": "USD",
        "amount": 0.032,
    }


# ──────────────────────────── outputs ────────────────────────────


def test_an_output_gets_a_placeholder_under_the_run_and_a_presigned_put(empty_api):
    """The bytes never transit the Lambda — a video would blow the 6 MB limit.

    The key is the project's, because a run lives inside a project and its bytes
    are the project's: three prefixes in the bucket and no more.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)

    resp = empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "output-1.png", "size": 3980112, "content_type": "image/png"},
    )

    assert resp.status_code == 201
    body = resp.get_json()
    node = catalog.node(body["node"])
    assert node["parent_id"] == _child(run["folder"], layout.OUTPUT_FOLDER)["node_id"]
    assert node["blob_key"] == f"projects/{project['id']}/{node['node_id']}.png"
    assert body["headers"] == {"Content-Length": "3980112", "Content-Type": "image/png"}


def test_the_first_output_becomes_the_listing_rows_thumbnail(empty_api):
    """What lets the runs grid draw without reading an envelope per tile."""
    project = _project(empty_api)
    run = _create(empty_api, project)

    first = empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "output-1.png", "size": 10, "content_type": "image/png"},
    ).get_json()
    empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "output-2.png", "size": 10, "content_type": "image/png"},
    )

    row = catalog.project_entities(project["id"], catalog.ENTITY_RUN)[0]
    assert row["thumb"] == first["node"]
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["outputs"][0]["id"] == first["node"]


def test_an_output_lists_in_its_folder_once_the_upload_is_confirmed(empty_api, media_bucket):
    """**The whole upload, ending where a person actually looks: the folder.**

    Every other test here stops at the placeholder, and that is exactly how the
    bug shipped. `POST /outputs` creates a node and signs a PUT; only
    `confirm-upload` heads the object and records `size`, and
    `browse.is_abandoned_upload` hides any file row without one. The pipeline PUT
    the bytes and never confirmed, so all 170 run outputs in prod were in S3,
    named by their run, drawn on the run page — and absent from the `output/`
    folder they lived in.

    So this asserts both halves in the order they happen: hidden before the
    confirm, listed after it. An assertion on only the second would still pass if
    the filter were deleted, which is the other way to make this folder wrong.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)

    signed = empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "output-1.png", "size": 4, "content_type": "image/png"},
    ).get_json()
    output_folder = _child(run["folder"], layout.OUTPUT_FOLDER)["node_id"]

    def listed():
        body = empty_api.get(f"/api/tree?node={output_folder}").get_json()
        return [entry["name"] for entry in body["files"]]

    # The bytes land — the presigned PUT goes straight to S3, so the test writes
    # them the same way, without the API in between.
    media_bucket.put_object(
        Bucket=config.media_bucket(),
        Key=catalog.node(signed["node"])["blob_key"],
        Body=b"png!",
    )
    assert listed() == [], "a row with no recorded size is a placeholder and must stay hidden"

    assert empty_api.post(f"/api/nodes/{signed['node']}/confirm-upload").status_code == 200

    assert listed() == ["output-1.png"]
    assert catalog.node(signed["node"])["size"] == 4


def test_an_oversized_output_is_refused_at_signing(empty_api):
    """Refused by the signature rather than discovered after the bytes have moved."""
    project = _project(empty_api)
    run = _create(empty_api, project)

    assert empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "huge.mp4", "size": 6 * 1024**3, "content_type": "video/mp4"},
    ).status_code == 400


# ──────────────────── the query that replaces a walk ────────────────────


def test_runs_by_character_is_one_reverse_query(empty_api):
    """**`runs find --character` was a walk over every run folder in the library**,
    reading three JSON documents each. It is one `by-sk` query for the ids and one
    batched read for the envelopes.
    """
    character = _character(empty_api)
    other = _character(empty_api, "subject-b")
    project = _project(empty_api)
    mine = _create(empty_api, project, characters=[character["id"]])
    _create(empty_api, project, slug="other-portrait", characters=[other["id"]])

    body = empty_api.get(f"/api/runs?character={character['id']}").get_json()

    assert [run["id"] for run in body["runs"]] == [mine["id"]]


def test_runs_filter_on_status_model_and_since(empty_api):
    """Filters run in memory over one query's worth of rows.

    A GSI per filter would be four indexes for one screen, and every one of them
    is a second copy of a mutable attribute to keep in step.
    """
    project = _project(empty_api)
    succeeded = _create(empty_api, project)
    empty_api.patch(f"/api/runs/{succeeded['id']}", json={"status": "succeeded"})
    _create(empty_api, project, slug="pending-portrait")

    body = empty_api.get(
        f"/api/runs?project={project['id']}&status=succeeded"
    ).get_json()
    assert [run["id"] for run in body["runs"]] == [succeeded["id"]]

    assert empty_api.get(
        f"/api/runs?project={project['id']}&model=nothing-like-it"
    ).get_json()["runs"] == []
    assert len(
        empty_api.get(f"/api/runs?project={project['id']}&since=2000-01-01").get_json()["runs"]
    ) == 2


def test_a_projects_runs_come_back_newest_first(empty_api):
    """`ScanIndexForward=False` over `RUN#<created>#<id>`, which is real pagination.

    The timestamp comes first in the sort key so the range is chronological, and
    the id follows so two runs created in the same microsecond are still two rows.
    """
    project = _project(empty_api)
    first = _create(empty_api, project, slug="first-portrait")
    second = _create(empty_api, project, slug="second-portrait")

    body = empty_api.get(f"/api/projects/{project['id']}/runs").get_json()

    assert [row["id"] for row in body["runs"]] == [second["id"], first["id"]]


# ──────────────────────────── delete ────────────────────────────


def test_deleting_a_run_keeps_its_files_by_default(empty_api, catalog_table):
    project = _project(empty_api)
    run = _create(empty_api, project)

    assert empty_api.delete(f"/api/runs/{run['id']}").status_code == 200

    assert _item(catalog_table, f"RUN#{run['id']}", "META") is None
    assert catalog.project_entities(project["id"], catalog.ENTITY_RUN) == []
    assert "entity" not in catalog.node(run["folder"])


def test_deleting_a_run_with_files_delete_takes_the_folder(empty_api):
    project = _project(empty_api)
    run = _create(empty_api, project)
    folder = run["folder"]

    assert empty_api.delete(f"/api/runs/{run['id']}?files=delete").status_code == 200

    assert catalog.children(_child(project["root"], layout.RUN_PARENT)["node_id"]) == []
    assert catalog.records([folder]) == {}


def test_a_run_in_another_library_is_403(empty_api, catalog_table):
    catalog_table.put_item(
        TableName=config.catalog_table(),
        Item={
            "pk": {"S": "RUN#run-elsewhere"},
            "sk": {"S": "META"},
            "id": {"S": "run-elsewhere"},
            "lib": {"S": "lib-0002"},
            "slug": {"S": "borrowed"},
        },
    )

    assert empty_api.get("/api/runs/run-elsewhere").status_code == 403
    assert CATALOG_LIBRARY != "lib-0002"
