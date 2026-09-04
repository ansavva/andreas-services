"""Runs: the envelope studio owns, the payload it does not, and hard rule #3.

A run used to be a folder named `<ts>_<hint>` holding three JSON documents nobody
was allowed to parse. Two things followed, and both are what these tests are
about:

* the app could show a run as a folder and nothing else, and
* `runs find --character` meant listing every project, listing every run in each,
  reading `request.json` for each, and grepping.

**The split that makes a run presentable without making this service a liar** is
the envelope — status, model, timings, bindings as node ids, outputs, cost —
beside a payload that is stored verbatim and never decoded. The old rule
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


def _project(api, name="rooftop-teaser", **body):
    return api.post("/api/projects", json={"name": name, **body}).get_json()


def _character(api, name="subject-a"):
    return api.post("/api/characters", json={"name": name}).get_json()


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


def _submitted(api, project, **body):
    """A run that has actually been submitted — draft, then pending.

    Every test that wants a run in a post-submission state moves it through the
    same transition the clients use, because that transition is where a run is
    counted.
    """
    run = _create(api, project, **body)
    resp = api.patch(f"/api/runs/{run['id']}", json={"status": "pending"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return run


# ──────────────────────── the envelope, in one write ────────────────────────


def test_creating_a_run_writes_envelope_listing_row_folder_and_output(empty_api, catalog_table):
    """**One transaction: the envelope, the project's listing row, and the tree.**

    A run is recorded *before* it is submitted, which is the reason
    `request.json` and `result.json` were two writes and are two calls here: a
    prediction that times out, or a process that is killed, leaves an envelope
    with the exact input beside it rather than nothing at all.

    **It is recorded before the decision to send, which is why it starts at
    `draft`.** That gives the payload an address: it can be read, edited and
    hashed before it bills.
    """
    project = _project(empty_api)

    run = _create(empty_api, project, input={"prompt": "a rooftop", "aspect_ratio": "9:16"})

    envelope = _item(catalog_table, f"RUN#{run['id']}", "META")
    assert envelope["status"]["S"] == "draft"
    assert envelope["project"]["S"] == project["id"]
    assert envelope["model"]["S"] == "google/nano-banana-pro"

    listing = catalog.project_entities(project["id"], catalog.ENTITY_RUN)
    assert [row["id"] for row in listing] == [run["id"]]
    assert listing[0]["status"] == "draft"

    # **A run has no slug, so its folder is named for its id.** The record names
    # the folder's node id either way, which is what stops a rename above it
    # stranding anything. The label it used to carry was `<timestamp>_<hint>` —
    # unique only by embedding `created`, a column the row already has.
    assert "name" not in envelope, "a run envelope carries no slug"
    folder = catalog.node(run["folder"])
    assert folder["name"] == run["id"]
    assert folder["entity"] == run["id"]
    assert _child(run["folder"], layout.OUTPUT_FOLDER)["kind"] == "folder"


def test_the_listing_row_is_the_one_deliberate_projection(empty_api):
    """Safe **because a run is immutable once it completes.**

    There is nothing left to keep in step, and the runs grid would otherwise need
    a `BatchGetItem` over hundreds of envelopes to draw thumbnails. Do not copy
    this reasoning onto a name claim, where the opposite is true.
    """
    project = _project(empty_api)
    _create(empty_api, project)

    row = catalog.project_entities(project["id"], catalog.ENTITY_RUN)[0]

    assert set(row) >= {"id", "status", "model", "kind", "created", "lib"}
    # Not the whole envelope: no bindings and no payload.
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
    run = _submitted(empty_api, project)
    empty_api.patch(f"/api/runs/{run['id']}", json={"status": "succeeded",
                                                    "cost": {"currency": "USD",
                                                             "amount": 0.032}})

    rows = empty_api.get(f"/api/runs?project={project['id']}").get_json()["runs"]

    assert len(rows) == 1
    missing = RUN_SUMMARY_REQUIRED - set(rows[0])
    assert not missing, (
        f"the runs listing row is missing {sorted(missing)}, which RunSummary "
        "declares required — the SPA renders them and the CLI indexes them")
    assert "name" not in rows[0], "a run has no slug; nothing may render one"


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

    second = _create(empty_api, project)

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
            "name": "rooftop-portrait",
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
            "name": "rooftop-portrait",
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
            "name": "rooftop-portrait",
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

    # **The node id lives on a `SEND#` row now, not in a map on the envelope.**
    # `bindings` was a `{field: [node, …]}` attribute; it is derived from these
    # rows on the way out, so the response shape is unchanged and there is one
    # truth rather than two spellings of it.
    send = _item(catalog_table, f"RUN#{run['id']}", "SEND#0001")
    assert send["node"]["S"] == picture["node_id"]
    assert send["field"]["S"] == "image_input"

    fetched = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert fetched["bindings"]["image_input"][0]["name"] == "renamed.webp"
    assert fetched["sends"][0]["node"] == picture["node_id"]


def test_an_expanded_binding_and_output_name_their_node_as_node(empty_api):
    """`node`, because that is what a pointer to a node is called everywhere else.

    This expansion said `id`, and the cost was not a naming quibble: the SPA
    reads `node`, so every output tile and every binding tile on a run page
    navigated to `/o/undefined` and the API answered `No such object: undefined`.
    The pipeline reads `node` too — `test_shoot` asserts it off the fake — so the
    fake and the thing it fakes disagreed and only the browser could tell.
    """
    character = _character(empty_api)
    project = _project(empty_api)
    reference = _child(character["root"], "reference")
    picture = _uploaded(empty_api, reference["node_id"], "front.webp")

    run = _create(empty_api, project, bindings={"image_input": [picture["node_id"]]})
    output = empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "output-1.png", "size": 10, "content_type": "image/png"},
    ).get_json()

    fetched = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert fetched["bindings"]["image_input"][0]["node"] == picture["node_id"]
    assert fetched["outputs"][0]["node"] == output["node"]
    assert "id" not in fetched["outputs"][0]


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
    run = _submitted(empty_api, project)

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
    run = _submitted(empty_api, project)

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
    run = _submitted(empty_api, project)

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
    run = _submitted(empty_api, project)

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
    assert empty_api.get(f"/api/runs/{run['id']}").get_json()["outputs"][0]["node"] == first["node"]


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
        body = empty_api.get(f"/api/nodes?under={output_folder}").get_json()
        return [entry["name"] for entry in body["entries"]]

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
    mine = _submitted(empty_api, project, characters=[character["id"]])
    _submitted(empty_api, project, characters=[other["id"]])

    body = empty_api.get(f"/api/runs?character={character['id']}").get_json()

    assert [run["id"] for run in body["runs"]] == [mine["id"]]


def test_runs_filter_on_status_model_and_since(empty_api):
    """Filters run in memory over one query's worth of rows.

    A GSI per filter would be four indexes for one screen, and every one of them
    is a second copy of a mutable attribute to keep in step.
    """
    project = _project(empty_api)
    succeeded = _submitted(empty_api, project)
    empty_api.patch(f"/api/runs/{succeeded['id']}", json={"status": "succeeded"})
    _submitted(empty_api, project)

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
    first = _create(empty_api, project)
    second = _create(empty_api, project)

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
            "name": {"S": "borrowed"},
        },
    )

    assert empty_api.get("/api/runs/run-elsewhere").status_code == 403
    assert CATALOG_LIBRARY != "lib-0002"


# ─────────────────── the draft, and what leaving it means ───────────────────
#
# There is no approve step. Hard rule #2 — nothing runs unless a person tells it
# to — is kept by the clients, and the API's part is that a draft is a plan with
# an address, readable and editable until the moment it is sent, and sent once.


def test_a_draft_is_submitted_on_its_own_say_so(empty_api):
    """No approval, no digest to match: the transition out of `draft` is the act.

    The route that used to refuse this (`not_approved`) is gone, and this holds
    it gone — a gate reintroduced by accident would fail here first.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)
    assert "approval" not in run and "plan_digest" not in run

    resp = empty_api.patch(f"/api/runs/{run['id']}", json={"status": "pending"})

    assert resp.status_code == 200
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "pending"
    read = empty_api.get(f"/api/runs/{run['id']}").get_json()
    assert "approval" not in read and "plan_digest" not in read and "stale" not in read


def test_the_payload_preview_follows_the_plan(empty_api):
    """**What a person reads before anything is sent.**

    Hard rule #2 asks a person to read the full payload, and a draft has no
    `request.json` to read — that document records what was actually sent and is
    written after dispatch. So the payload a draft would send was unreadable in
    the app, and editing the plan appeared to change nothing.

    It is the same assembly `submit` uses, so an edit moves it.
    """
    project = _project(empty_api)
    run = _create(empty_api, project, plan={"prompt": "a rooftop at dawn"})

    before = empty_api.get(f"/api/runs/{run['id']}/payload").get_json()
    assert before["request"]["prompt"] == "a rooftop at dawn"

    empty_api.patch(f"/api/runs/{run['id']}/plan", json={"plan": {"prompt": "a rooftop at dusk"}})

    after = empty_api.get(f"/api/runs/{run['id']}/payload").get_json()
    assert after["request"]["prompt"] == "a rooftop at dusk", "the preview is rebuilt, not stored"


def test_the_payload_preview_is_refused_once_the_run_has_been_submitted(empty_api):
    """Once something has gone out, the honest answer is `request.json`.

    Computing a fresh payload for a submitted run would invite comparing it
    against one the provider was never given — the same dishonesty `_draftable`
    refuses a plan edit to prevent.
    """
    project = _project(empty_api)
    run = _create(empty_api, project, plan={"prompt": "a rooftop at dawn"})
    empty_api.patch(f"/api/runs/{run['id']}", json={"status": "pending"})

    resp = empty_api.get(f"/api/runs/{run['id']}/payload")
    assert resp.status_code == 409


def test_editing_the_images_replaces_the_sends(empty_api):
    """A payload is its prompt **and** its pictures.

    Swapping a reference image changes what the model is shown as surely as
    rewording the prompt does, and the run stays a draft with the new picture.
    """
    project = _project(empty_api)
    character = _character(empty_api)
    reference = _child(character["root"], "reference")
    first = _uploaded(empty_api, reference["node_id"], "a.webp")
    second = _uploaded(empty_api, reference["node_id"], "b.webp")

    run = _create(empty_api, project, bindings={"image_input": [first["node_id"]]})

    resp = empty_api.patch(
        f"/api/runs/{run['id']}/sends",
        json={"sends": [{"field": "image_input", "role": "reference",
                         "node": second["node_id"]}]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "draft"
    assert [send["node"] for send in resp.get_json()["sends"]] == [second["node_id"]]


def test_reordering_the_images_moves_the_fingerprint(empty_api):
    """**A reorder is a real edit**, because position is cited by the prompt.

    A production prompt in this library reads "the FIRST image is an existing
    plate of him". Swapping two references changes which picture that sentence
    is about, so the reordered draft is a different submission.
    """
    project = _project(empty_api)
    character = _character(empty_api)
    reference = _child(character["root"], "reference")
    one = _uploaded(empty_api, reference["node_id"], "a.webp")
    two = _uploaded(empty_api, reference["node_id"], "b.webp")

    run = _create(
        empty_api, project,
        bindings={"image_input": [one["node_id"], two["node_id"]]},
    )

    resp = empty_api.patch(
        f"/api/runs/{run['id']}/sends",
        json={"sends": [
            {"field": "image_input", "role": "reference", "node": two["node_id"]},
            {"field": "image_input", "role": "reference", "node": one["node_id"]},
        ]},
    )
    assert resp.get_json()["fingerprint"] != run["fingerprint"]
    assert resp.get_json()["status"] == "draft"


def test_the_approve_routes_are_gone(empty_api):
    """Decision 2026-09-04: no approve step anywhere. The routes 404 or 405."""
    project = _project(empty_api)
    run = _create(empty_api, project)

    assert empty_api.post(f"/api/runs/{run['id']}/approve", json={}).status_code in (404, 405)
    assert empty_api.delete(f"/api/runs/{run['id']}/approve").status_code in (404, 405)
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "draft"


def test_a_submitted_runs_plan_cannot_be_rewritten(empty_api):
    """**What was sent is what the record says was sent.**

    `request.json` holds exactly what the provider was given. A plan edited after
    the submission would sit beside it describing something that never happened,
    and the run page would draw the two as though they agreed.
    """
    project = _project(empty_api)
    run = _submitted(empty_api, project, plan={"prompt": "a rooftop"})

    resp = empty_api.patch(f"/api/runs/{run['id']}/plan", json={"plan": {"prompt": "edited"}})

    assert resp.status_code == 409


def test_drafts_are_hidden_from_a_listing_and_askable_for(empty_api):
    """A grid mixing intentions with submissions is a grid nobody can read.

    Hiding them is what keeps the runs screen answering the question it is opened
    to answer — what was actually made — while `?status=draft` is how the screen
    that wants the other answer gets it.
    """
    project = _project(empty_api)
    submitted = _submitted(empty_api, project)
    draft = _create(empty_api, project)

    listed = empty_api.get(f"/api/runs?project={project['id']}").get_json()["runs"]
    assert [run["id"] for run in listed] == [submitted["id"]]

    drafts = empty_api.get(f"/api/runs?project={project['id']}&status=draft").get_json()
    assert [run["id"] for run in drafts["runs"]] == [draft["id"]]

    both = empty_api.get(f"/api/runs?project={project['id']}&include=drafts").get_json()
    assert {run["id"] for run in both["runs"]} == {submitted["id"], draft["id"]}


def test_a_send_records_why_the_image_was_sent(empty_api):
    """The half `bindings` never held.

    `engine/submit.py::gather` decides an image is a start frame, or the third
    face reference of a named character, and then throws that away. A run page
    that can only say "six images were sent" is the consequence.
    """
    project = _project(empty_api)
    character = _character(empty_api)
    reference = _child(character["root"], "reference")
    picture = _uploaded(empty_api, reference["node_id"], "front.webp")

    run = _create(
        empty_api, project,
        sends=[{"field": "image_input", "role": "reference", "node": picture["node_id"],
                "source": {"kind": "character", "character": character["id"],
                           }}],
    )

    (send,) = empty_api.get(f"/api/runs/{run['id']}").get_json()["sends"]
    assert send["role"] == "reference"
    assert send["source"]["kind"] == "character"
    assert send["name"] == "front.webp", "a send expands into something drawable"


def test_a_write_answers_the_same_shape_a_read_does(empty_api):
    """**One shape for a run, whichever route returned it.**

    The four write routes each answered `{**record, "sends": <raw rows>}` — the
    stored row rather than the document `GET` builds — and the SPA swaps a
    write's response straight into the page rather than re-reading, deliberately:
    a re-GET would re-sign every URL to show one badge change. So saving an edit
    replaced four drawable images with four placeholders, and submitting a
    run would have done the same to its outputs. Found by saving an edit on a
    dev stack and looking at it.
    """
    project = _project(empty_api)
    character = _character(empty_api)
    reference = _child(character["root"], "reference")
    picture = _uploaded(empty_api, reference["node_id"], "front.webp")

    run = _create(
        empty_api, project,
        plan={"prompt": "a porch at dawn", "params": {}},
        sends=[{"field": "image_input", "role": "reference", "node": picture["node_id"]}],
    )

    read = empty_api.get(f"/api/runs/{run['id']}").get_json()
    written = empty_api.patch(
        f"/api/runs/{run['id']}/plan",
        json={"plan": {"prompt": "a porch at dusk", "params": {}}},
    ).get_json()

    assert written["sends"][0]["name"] == read["sends"][0]["name"]
    assert written["sends"][0]["url"], "a send comes back drawable"
    assert written["sends"][0]["source"] == read["sends"][0]["source"]
    assert set(written) == set(read), "the same keys, so a page can swap one in"


def test_a_send_naming_a_url_is_refused(empty_api):
    """Hard rule #3, on the new path. S3 is the only origin."""
    project = _project(empty_api)

    resp = empty_api.post(
        "/api/runs",
        json={"project": project["id"], "kind": "image", "model": "google/nano-banana-pro",
              "sends": [{"field": "image_input", "role": "reference",
                         "node": "https://example.com/a.png"}]},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_binding"


def test_a_send_with_an_unknown_role_is_refused(empty_api):
    project = _project(empty_api)
    character = _character(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")

    resp = empty_api.post(
        "/api/runs",
        json={"project": project["id"], "kind": "image", "model": "google/nano-banana-pro",
              "sends": [{"field": "image_input", "role": "sample", "node": picture["node_id"]}]},
    )

    # `sample` is a storyboard PANEL role — a picture for a person to look at,
    # which binds to nothing. It cannot be a send, because a send is by
    # definition something the model was handed.
    assert resp.status_code == 400


def test_counting_is_on_leaving_the_draft_states_not_on_reaching_pending(empty_api):
    """**The near-miss this test exists to hold shut.**

    A caller may write `running` or `succeeded` straight onto a draft and never
    pass through `pending`. A count that keyed on `pending` would be enforced by
    the test suite and missed by such a caller — the worst possible outcome,
    because it reads as working.
    """
    project = _project(empty_api)

    for status in ("running", "succeeded", "failed"):
        run = _create(empty_api, project)
        resp = empty_api.patch(f"/api/runs/{run['id']}", json={"status": status})
        assert resp.status_code == 200, f"{status} was refused"

    counts = empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]
    assert counts["runs"] == 3


def test_a_submitted_run_moves_on(empty_api):
    """Once it has gone out, the statuses are the machine reporting facts."""
    project = _project(empty_api)
    run = _submitted(empty_api, project)

    assert empty_api.patch(
        f"/api/runs/{run['id']}", json={"status": "running"}
    ).status_code == 200
    assert empty_api.patch(
        f"/api/runs/{run['id']}", json={"status": "succeeded"}
    ).status_code == 200


def test_a_run_is_counted_once_however_many_statuses_it_moves_through(empty_api):
    project = _project(empty_api)
    run = _create(empty_api, project)

    for status in ("running", "succeeded"):
        empty_api.patch(f"/api/runs/{run['id']}", json={"status": status})

    counts = empty_api.get(f"/api/projects/{project['id']}").get_json()["counts"]
    assert counts["runs"] == 1


def test_a_send_learns_where_its_image_came_from_without_being_told(empty_api):
    """**Provenance is derived, so a backfilled run says the same words.**

    The pipeline knows it picked a face reference, but the pipeline is not the
    only thing that creates runs — and a run reconstructed from history has no
    `gather` behind it at all. Deriving it from where the node sits means one
    implementation and one vocabulary.
    """
    character = _character(empty_api)
    project = _project(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    empty_api.patch(
        f"/api/nodes/{picture['node_id']}", json={"tags": ["default", "face"]}
    )

    run = _create(empty_api, project, bindings={"image_input": [picture["node_id"]]})

    (send,) = empty_api.get(f"/api/runs/{run['id']}").get_json()["sends"]
    assert send["source"]["kind"] == "character"
    assert send["source"]["character"] == character["id"]
    # **No group.** What the picture IS is on the picture — `tags` on the node,
    # which every listing already carries — so provenance saying it a second time
    # would be a second copy of a fact with one home.
    assert "group" not in send["source"]


def test_a_send_from_the_input_pool_records_its_position(empty_api):
    """**`--input N` IS a position**, so a send that lost it would lose the part
    a person actually typed."""
    project = _project(empty_api)
    pool = _child(project["root"], layout.INPUT_FOLDER)
    _uploaded(empty_api, pool["node_id"], "a-first.webp")
    second = _uploaded(empty_api, pool["node_id"], "b-second.webp")

    run = _create(empty_api, project, bindings={"image_input": [second["node_id"]]})

    (send,) = empty_api.get(f"/api/runs/{run['id']}").get_json()["sends"]
    assert send["source"] == {"kind": "input-pool", "project": project["id"], "position": 2}


def test_a_send_chained_off_an_earlier_run_names_that_run(empty_api):
    """The deepest entity wins, so a frame under a run's `output/` reports the
    run rather than the project it sits in — which is what makes a chain
    readable backwards from the images alone."""
    project = _project(empty_api)
    earlier = _submitted(empty_api, project)
    frame = empty_api.post(
        f"/api/runs/{earlier['id']}/outputs",
        json={"name": "frame.webp", "size": 4, "content_type": "image/webp"},
    ).get_json()

    run = _create(empty_api, project,
                  bindings={"image_input": [frame["node"]]})

    (send,) = empty_api.get(f"/api/runs/{run['id']}").get_json()["sends"]
    assert send["source"]["kind"] == "run"
    assert send["source"]["run"] == earlier["id"]
    assert send["source"]["output"] == 1


def test_a_run_from_before_send_rows_still_reports_its_bindings(empty_api, catalog_table):
    """**Every run that existed before this change is this case.**

    They carry `bindings` as an attribute and no `SEND#` row. Deriving the map
    unconditionally answered `{}` for all of them — a run page reading "Nothing
    was bound" over a generation that plainly bound six images. Written here as
    the raw row a legacy run actually has, not through the create route, because
    the create route cannot produce this state any more.
    """
    project = _project(empty_api)
    character = _character(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    run = _create(empty_api, project)

    # Strip the send rows and put the old-shaped attribute back.
    catalog_table.delete_item(
        TableName=config.catalog_table(),
        Key={"pk": {"S": f"RUN#{run['id']}"}, "sk": {"S": "SEND#0001"}},
    )
    catalog_table.update_item(
        TableName=config.catalog_table(),
        Key={"pk": {"S": f"RUN#{run['id']}"}, "sk": {"S": "META"}},
        UpdateExpression="SET #b = :b",
        ExpressionAttributeNames={"#b": "bindings"},
        ExpressionAttributeValues={
            ":b": {"M": {"image_input": {"L": [{"S": picture["node_id"]}]}}}
        },
    )

    fetched = empty_api.get(f"/api/runs/{run['id']}").get_json()

    assert fetched["bindings"]["image_input"][0]["node"] == picture["node_id"]
    assert fetched["bindings"]["image_input"][0]["name"] == "a.webp", (
        "the fallback expands into something drawable, like the derived path does"
    )


def test_deleting_a_run_takes_its_send_rows_with_it(empty_api, catalog_table):
    """**A new child of the run partition, so the sweep has to cover it.**

    `_entity_rows` queries the whole partition with no sort-key filter, which is
    what makes this true without anything being taught about sends — but the
    property is worth a test rather than an inspection, because the failure is
    invisible: orphan `SEND#` rows pointing at a run that no longer exists, found
    later by a scan and by nothing else.
    """
    project = _project(empty_api)
    character = _character(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    run = _create(empty_api, project, bindings={"image_input": [picture["node_id"]]})
    assert _item(catalog_table, f"RUN#{run['id']}", "SEND#0001") is not None

    empty_api.delete(f"/api/runs/{run['id']}")

    assert _item(catalog_table, f"RUN#{run['id']}", "SEND#0001") is None
    assert _item(catalog_table, f"RUN#{run['id']}", "META") is None


def test_a_send_with_no_recorded_source_gets_one_derived_on_read(empty_api, catalog_table):
    """**Every send the backfill wrote is this case.**

    `catalog backfill-plans` runs outside this service and cannot call
    `source_of`; reimplementing provenance pipeline-side would be a second
    dialect, which is the exact thing deriving it was meant to avoid. So the row
    carries what only the pipeline knew — field, role, order — and the read fills
    in what only the catalog knows.
    """
    character = _character(empty_api)
    project = _project(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    empty_api.patch(
        f"/api/nodes/{picture['node_id']}", json={"tags": ["default", "body"]}
    )
    run = _create(empty_api, project, bindings={"image_input": [picture["node_id"]]})

    # Strip the source the create path derived, leaving the row as a backfill
    # writes one.
    catalog_table.update_item(
        TableName=config.catalog_table(),
        Key={"pk": {"S": f"RUN#{run['id']}"}, "sk": {"S": "SEND#0001"}},
        UpdateExpression="REMOVE #s",
        ExpressionAttributeNames={"#s": "source"},
    )

    (send,) = empty_api.get(f"/api/runs/{run['id']}").get_json()["sends"]

    assert send["source"]["kind"] == "character"
    assert "group" not in send["source"]


# ── the runref resolver ─────────────────────────────────────────────────────


def test_a_run_id_resolves_with_no_project(empty_api):
    """The property the entity model is for: an id is self-sufficient."""
    project = _project(empty_api)
    run = _create(empty_api, project)
    found = empty_api.get(f"/api/runs/resolve?ref={run['id']}").get_json()
    assert found["id"] == run["id"]


def test_latest_resolves_to_the_newest_submitted_run(empty_api):
    project = _project(empty_api)
    first = _create(empty_api, project, plan={"params": {}, "prompt": "one"})
    empty_api.patch(f"/api/runs/{first['id']}", json={"status": "succeeded"})

    found = empty_api.get(
        f"/api/runs/resolve?ref={project['id']}/latest").get_json()
    assert found["id"] == first["id"]


def test_latest_skips_a_draft_unless_it_is_asked_for(empty_api):
    """`GET /api/runs` hides drafts by default and so does this.

    `latest` is overwhelmingly asked in order to chain off something —
    `--start-run <project>/latest` — and a draft has no output to chain from.
    """
    project = _project(empty_api)
    submitted = _create(empty_api, project, plan={"params": {}, "prompt": "one"})
    empty_api.patch(f"/api/runs/{submitted['id']}", json={"status": "succeeded"})
    draft = _create(empty_api, project, plan={"params": {}, "prompt": "two"})

    ref = f"{project['id']}/latest"
    assert empty_api.get(f"/api/runs/resolve?ref={ref}").get_json()["id"] == submitted["id"]
    assert empty_api.get(
        f"/api/runs/resolve?ref={ref}&include=drafts").get_json()["id"] == draft["id"]


def test_the_project_segment_is_an_id(empty_api):
    """**It took a bare slug, and slugs are gone.**

    The argument for the bare form was that it is what a person types — every
    other route wanted `slug:<slug>` or an id, and requiring the prefix here
    would have meant typing `slug:porch-teaser/latest`. A name is a free-text
    label now and two projects may share one, so there is nothing to resolve.
    """
    project = _project(empty_api, name="porch-teaser")
    run = _create(empty_api, project)
    empty_api.patch(f"/api/runs/{run['id']}", json={"status": "succeeded"})

    assert empty_api.get(
        f"/api/runs/resolve?ref={project['id']}/latest").status_code == 200
    assert empty_api.get(
        "/api/runs/resolve?ref=porch-teaser/latest").status_code == 400


def test_an_index_is_reported_and_not_applied(empty_api):
    """**`#2` narrows nothing server-side, deliberately.**

    `resolve_output_nodes` filters by extension first — "the mp4 this run made" —
    and then takes the Nth of what is left. An API that had already dropped the
    others would silently change which file `#2` means.
    """
    project = _project(empty_api)
    run = _create(empty_api, project)
    # `%23`, because a bare `#` in a URL is a fragment and never reaches the
    # server. The CLI sends the ref as a query value and urllib encodes it.
    found = empty_api.get(f"/api/runs/resolve?ref={run['id']}%232").get_json()
    assert found["index"] == 2
    assert "outputs" in found


@pytest.mark.parametrize("ref,reason", [
    ("", "ref is required"),
    ("proj/latest%230", "positive integer"),
    ("proj/latest%23x", "positive integer"),
    ("latest", "no project"),
])
def test_a_malformed_runref_is_refused_saying_why(empty_api, ref, reason):
    resp = empty_api.get(f"/api/runs/resolve?ref={ref}")
    assert resp.status_code == 400
    assert reason in resp.get_json()["error"]


def test_a_name_is_not_a_runref(empty_api):
    """A run has no label at all. Its slug read `<timestamp>_<hint>` — 29 collapsed to 19."""
    project = _project(empty_api)
    resp = empty_api.get(f"/api/runs/resolve?ref={project['id']}/my-nice-run")
    assert resp.status_code == 400
    assert "not a runref" in resp.get_json()["error"]


# ─────────────────── a plan's template, and its cast ───────────────────


def _run_with_cast(api, count=1):
    """A draft bound to `count` character(s), each with a wardrobe."""
    project = api.post("/api/projects", json={"name": "cast"}).get_json()
    ids = []
    for n, top in enumerate(("crew-neck tee", "work jacket")[:count]):
        made = api.post("/api/characters", json={
            "name": f"subject-{'ab'[n]}",
            "profile": {"wardrobe": {"tops": [{"item": top, "colour": "charcoal"}]},
                        "rendering": {"default_style": "Realistic"}},
        }).get_json()
        ids.append(made["id"])
    return _create(api, project, characters=ids,
                   plan={"version": 1, "origin": "authored",
                         "prompt": "x", "params": {}})


def test_a_plan_TEMPLATE_is_expanded_at_save_and_kept_beside_the_prompt(api):
    """**Expanded at save, and the plan keeps both.**

    A template expanded at SUBMIT would mean the payload a person read is not
    the payload that gets sent, and the fingerprint would be hashing the wrong
    string. The template is kept beside the prompt so the prompt stays
    re-editable: without it, filling one in once leaves the next editor a wall
    of finished prose with no way back to what was written.
    """
    run = _run_with_cast(api)
    got = api.patch(f"/api/runs/{run['id']}/plan", json={"plan": {
        "version": 1, "origin": "authored", "params": {},
        "template": "He wears {character.1.top}.",
    }}).get_json()

    assert got["plan"]["template"] == "He wears {character.1.top}."
    assert got["plan"]["prompt"].startswith("He wears Wearing a plain charcoal crew-neck tee")


def test_a_plan_WITHOUT_a_template_is_written_exactly_as_it_arrives(api):
    """Every run authored before this carries a prompt and no template, and
    must keep opening and saving as the sentence it is."""
    run = _run_with_cast(api)
    got = api.patch(f"/api/runs/{run['id']}/plan", json={"plan": {
        "version": 1, "origin": "authored", "params": {},
        "prompt": "A literal sentence with no {braces} expanded.",
    }}).get_json()
    assert got["plan"]["prompt"] == "A literal sentence with no {braces} expanded."
    assert "template" not in got["plan"]


def test_the_cast_is_numbered_by_the_runs_own_binding(api):
    """`{character.1}` is the first character bound to THIS run.

    Numbered rather than named: a slug is an attribute a rename swaps, and every
    record here names entity ids for that reason. A prompt citing a name would
    be quietly wrong the moment somebody renamed the character.
    """
    run = _run_with_cast(api, count=2)
    got = api.patch(f"/api/runs/{run['id']}/plan", json={"plan": {
        "version": 1, "origin": "authored", "params": {},
        "template": "{character.1.top} :: {character.2.top}",
    }}).get_json()
    assert "crew-neck tee" in got["plan"]["prompt"].split("::")[0]
    assert "work jacket" in got["plan"]["prompt"].split("::")[1]


def test_citing_a_character_the_run_does_not_bind_is_a_400_naming_the_range(api):
    run = _run_with_cast(api)
    resp = api.patch(f"/api/runs/{run['id']}/plan", json={"plan": {
        "version": 1, "origin": "authored", "params": {},
        "template": "{character.4.top}",
    }})
    assert resp.status_code == 400
    assert "1 character(s)" in resp.get_json()["error"]


def test_the_preview_expands_and_writes_NOTHING(api):
    """It is called on every change, which is why it cannot be the save."""
    run = _run_with_cast(api)
    before = api.get(f"/api/runs/{run['id']}").get_json()["plan"]

    got = api.post(f"/api/runs/{run['id']}/plan/preview",
                   json={"template": "He wears {character.1.top}."}).get_json()

    assert got["characters"] == 1
    assert "crew-neck tee" in got["prompt"]
    assert api.get(f"/api/runs/{run['id']}").get_json()["plan"] == before


def test_a_run_that_records_no_character_still_has_a_CAST(api):
    """**`characters` is written at creation and nowhere else.**

    A run built by adding a character's references in the editor binds six of
    that character's photographs and records nobody — so `{character.1.top}`
    had nothing to fill from on exactly the runs most likely to want it. A
    reference image belongs to a character by its ancestry, which `owner_of`
    already resolves for every listing, so the answer is there to be read.
    """
    project = api.post("/api/projects", json={"name": "cast-derived"}).get_json()
    made = api.post("/api/characters", json={
        "name": "subject-a",
        "profile": {"wardrobe": {"tops": [{"item": "crew-neck tee", "colour": "charcoal"}]},
                    "rendering": {"default_style": "Realistic"}},
    }).get_json()
    # `_uploaded` returns the catalog row, whose id key is `node_id`.
    photo = _uploaded(api, made["root"], "face.png")["node_id"]

    # Created with NO characters, then given one of that character's images.
    run = _create(api, project, characters=[],
                  plan={"version": 1, "origin": "authored", "prompt": "x", "params": {}})
    api.patch(f"/api/runs/{run['id']}/sends",
              json={"sends": [{"field": "image_input", "role": "reference",
                               "node": photo}]})

    got = api.get(f"/api/runs/{run['id']}").get_json()
    assert got["characters"] == []
    assert got["cast"] == [made["id"]]

    # And the template can fill from it.
    filled = api.patch(f"/api/runs/{run['id']}/plan", json={"plan": {
        "version": 1, "origin": "authored", "params": {},
        "template": "He wears {character.1.top}.",
    }}).get_json()
    assert "crew-neck tee" in filled["plan"]["prompt"]


def test_the_records_OWN_characters_win_when_it_has_them(api):
    """Deriving is the fallback, not the rule: a run that says who it is about
    is answering the question itself."""
    project = api.post("/api/projects", json={"name": "cast-named"}).get_json()
    named = api.post("/api/characters", json={"name": "subject-a"}).get_json()
    run = _create(api, project, characters=[named["id"]],
                  plan={"version": 1, "origin": "authored", "prompt": "x", "params": {}})
    assert api.get(f"/api/runs/{run['id']}").get_json()["cast"] == [named["id"]]
