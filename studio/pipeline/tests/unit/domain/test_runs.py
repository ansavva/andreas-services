"""`domain/runs` — the run store, now an envelope in a row.

**These run against the in-memory API, not against a stubbed store.** The old
suite scripted `api.get`/`api.post` per route and asserted the request bodies,
which proved the module was self-consistent and nothing else. Everything here
goes through `adapters/entities` and `adapters/store` for real, so a route name
or a field spelling that drifted from the backend fails here.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E
from studio_pipeline.adapters import store
from studio_pipeline.domain import runs as R


# ── the invariant ───────────────────────────────────────────────────────────

def test_a_url_shaped_binding_is_refused_before_anything_is_sent():
    """Hard rule #3's enforcement point on this side of the wire.

    The API refuses one too, which is the strengthening — the SPA never went
    through this function. Both refusing is the point: this one lets
    `submit.py` decline to submit at all rather than discovering it after a
    round trip.
    """
    with pytest.raises(R.RunError, match="URL"):
        R.check_bindings({"image": ["https://example.test/x.png"]})


def test_a_path_shaped_binding_is_refused_too():
    """**New, and the whole reason `rewrite.py` is deleted.**

    A path was legal here until records named nodes. It resolves today and
    dangles after the first rename, which is exactly how sixty-nine records went
    bad — so accepting one silently is the failure mode, not a kindness.
    """
    with pytest.raises(R.RunError, match="not a node id"):
        R.check_bindings({"image": ["characters/subject-a/reference/face/x.png"]})


def test_a_node_id_binding_is_kept_shape_and_all(library):
    assert R.check_bindings({"image": [library.face_1], "start": library.face_2}) == {
        "image": [library.face_1], "start": library.face_2}


# ── recording ───────────────────────────────────────────────────────────────

def test_recording_a_run_creates_the_envelope_before_the_submission(library):
    """The ordering that leaves a record behind when a prediction times out.

    `status` is `draft` and there are no outputs — the run exists, and neither
    the approval nor the submission has happened. A store that recorded nothing
    until success would lose exactly the runs worth investigating; a store that
    recorded nothing until the approval would leave the payload a person is
    supposed to read with no address.
    """
    record = R.record_request(library.project, kind="image",
                              engine="nano-banana-pro",
                              model="google/nano-banana-pro",
                              input={"prompt": "a porch"},
                              bindings={"image_input": [library.face_1]},
                              characters=[library.character])
    assert record["status"] == "draft"
    assert record["outputs"] == []
    assert record["approval"] is None
    assert record["plan_digest"].startswith("sha256:")
    assert record["folder"].startswith("node-")
    assert record["payload"]["request"].startswith("node-")
    assert record["payload"]["response"] is None


def test_a_structured_prompt_is_recorded_beside_the_request(library):
    """`prompt.json` exists so the authored source survives, not just the string."""
    record = R.record_request(library.project, kind="image",
                              engine="e", model="m", input={"prompt": "x"},
                              bindings={}, prompt_source={"subject": "a porch"})
    assert record["payload"]["prompt"].startswith("node-")


def test_the_bindings_land_on_the_row_as_node_ids(library):
    record = R.record_request(library.project, kind="image",
                              engine="e", model="m", input={},
                              bindings={"image_input": [library.face_1, library.face_2]})
    assert E.get_run(record["id"])["bindings"] == {
        "image_input": [library.face_1, library.face_2]}


def test_the_api_refuses_a_binding_that_names_no_node(library):
    """The second half of hard rule #3, enforced where both callers pass.

    `check_bindings` cannot know whether `node-…` exists — only the catalog
    does. A typo that is shaped like an id therefore has to fail server-side,
    and it does.
    """
    from studio_pipeline.adapters import api

    with pytest.raises(api.ApiError):
        E.create_run(project=library.project, kind="image", engine="e", model="m",
                     input={},
                     bindings={"image_input": ["node-00000000-0000-0000-0000-000000000000"]})


def test_a_run_has_no_slug_and_its_folder_is_named_for_its_id(library):
    """**A run is a machine event, so it carries no label at all.**

    The slug it used to carry read `<timestamp>_<hint>`: unique only because it
    embedded `created`, which is already a column and already what sorting and
    `--since` read. Strip the timestamp and production's 29 runs collapsed to 19
    labels. Nothing keyed on it and no claim row enforced it.

    Two runs a second apart used to need the API to disambiguate their folder
    names. Named for the id, they cannot collide.
    """
    first = R.record_request(library.project, kind="image", engine="e",
                             model="m", input={}, bindings={})
    second = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})
    assert "slug" not in first, "a run record carries no slug"
    assert first["id"] != second["id"]
    assert first["folder"] != second["folder"]


# ── outputs ─────────────────────────────────────────────────────────────────

def test_an_output_lands_in_the_runs_output_folder_and_on_the_row(library, tmp_path):
    """One call mints the node and the presigned PUT together.

    Deliberately not `store.write_into`: that would create a second node beside
    the one the route already made, and the run's `outputs` list would name the
    wrong one.
    """
    local = tmp_path / "frame.png"
    local.write_bytes(b"png-bytes")
    node = R.upload_output(library.run, str(local))
    assert node.startswith("node-")
    assert node in [o["node"] for o in R.run_outputs(library.run)]
    # The row holds it, so the ORDER is the record's rather than a listing's.
    assert R.run_outputs(library.run)[-1]["node"] == node


def test_an_output_is_confirmed_so_its_folder_can_list_it(library, tmp_path):
    """**The call that was missing, and the whole reason `output/` looked empty.**

    An upload is create, PUT, confirm. The entity route does the create and signs
    the PUT; only the confirm records `size`, and the API hides any file row that
    has none — a placeholder is a key with nothing proven behind it, so listing
    one draws a tile that will not load.

    `upload_output` stopped after the PUT. Every output studio had ever produced
    was therefore invisible in the folder it lived in, while the run page drew it
    perfectly: that page expands `outputs` by id and presigns off `blob_key`,
    neither of which consults a listing. 170 outputs in prod were in that state.

    So the assertion is on the node's own record rather than on the run's — the
    run named the node all along, which is exactly why the run page lied.
    """
    local = tmp_path / "frame.png"
    local.write_bytes(b"png-bytes")

    node = R.upload_output(library.run, str(local))

    record = store.node(node)
    assert "size" in record, "unconfirmed: the API will hide this from every listing"
    assert record["size"] == len(b"png-bytes")
    assert record["content_type"] == "image/png"


def test_outputs_come_back_in_the_order_the_run_recorded(library, tmp_path):
    """**Order is the record's, not a listing's**, and that is a real change.

    It was a natural sort over `output/`'s children because the folder was the
    only source — which is why `-10` sorting before `-2` was a live hazard. The
    row holds the order they were written in, so there is nothing to re-derive.
    """
    for name in ("out-10.png", "out-2.png"):
        local = tmp_path / name
        local.write_bytes(b"png")
        R.upload_output(library.run, str(local))
    assert [o["name"] for o in R.run_outputs(library.run)] == [
        "output-1.jpeg", "out-10.png", "out-2.png"]


def test_a_run_that_never_produced_output_has_none(library):
    """A failure or a timeout legitimately has none, and that is not an error."""
    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})
    assert R.run_outputs(record["id"]) == []


# ── completion ──────────────────────────────────────────────────────────────

def test_recording_a_result_patches_the_row_and_stores_the_response(library):
    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})
    # Through the gate, not around it: the API refuses to move a run out of the
    # unsubmitted states without an approval naming its exact payload.
    E.approve_run(record["id"], record["plan_digest"])
    R.record_result(record["id"], prediction_id="pred-1", status="succeeded",
                    outputs=[], source_urls=["https://replicate.test/x"])
    after = E.get_run(record["id"])
    assert after["status"] == "succeeded"
    assert after["prediction_id"] == "pred-1"
    assert after["payload"]["response"].startswith("node-")


def test_an_exception_is_recorded_rather_than_raising_on_the_way_in(library):
    """`json.dumps` refuses an exception, which turned a failed prediction into
    a `TypeError` on the way to recording that it failed."""
    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})
    E.approve_run(record["id"], record["plan_digest"])
    R.record_result(record["id"], prediction_id=None, status="failed",
                    error=RuntimeError("the provider said no"))
    assert E.get_run(record["id"])["error"] == "the provider said no"


def test_the_payload_documents_read_back_verbatim(library):
    """Studio stores these and does not decode them. This reads text, not JSON."""
    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={"prompt": "a porch"}, bindings={})
    documents = R.payload_documents(E.get_run(record["id"]))
    assert "request" in documents
    assert json.loads(documents["request"])["prompt"] == "a porch"


# ── querying ────────────────────────────────────────────────────────────────

def test_finding_by_character_is_one_query(library):
    """What `runs find --character` became.

    It used to list every project, list every run in each, read three documents
    per run and grep. The link is a row, so this is a single query — and it
    finds the fixture run, which named the character explicitly.
    """
    assert [r["id"] for r in R.find_runs(character=E.address("subject-a"))] == [
        library.run]


def test_a_character_that_was_not_used_finds_nothing(library):
    assert R.find_runs(character=E.address("subject-b")) == []


def test_listing_filters_on_model_and_status(library):
    """**New filters, free from the row.** Neither existed at any price before."""
    assert R.list_runs(library.project, model="google/nano-banana-pro")
    assert R.list_runs(library.project, model="nope") == []
    assert R.list_runs(library.project, status="succeeded")
    assert R.list_runs(library.project, status="failed") == []


def test_listing_accepts_a_slug_a_person_typed(library):
    assert R.list_runs(E.address("porch-teaser"))


# ── runrefs ─────────────────────────────────────────────────────────────────

def test_latest_resolves_to_the_newest_run(library):
    newest = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})
    assert R.resolve_run("porch-teaser/latest")["id"] == newest["id"]


def test_a_run_id_resolves_with_no_project_at_all(library):
    """**The property the whole entity model is for.**

    A record that stored a run id is self-sufficient: nothing has to remember
    which project it was in, and nothing is stranded when the project is
    renamed.
    """
    assert R.resolve_run(library.run)["id"] == library.run


def test_a_runref_that_is_not_latest_or_an_id_is_refused_with_the_options(library):
    """There is no name to guess at, so it says so and lists what is there.

    This replaces the exact-match, substring-fallback, ambiguity-error ladder
    that existed only to prop up a label that was never unique.
    """
    for _ in range(2):
        R.record_request(library.project, kind="image", engine="e",
                         model="m", input={}, bindings={})
    with pytest.raises(R.RunError, match="not a runref"):
        R.resolve_run("porch-teaser/twice")


def test_resolving_output_nodes_returns_ids_not_paths(library):
    """The whole of #420 in one assertion.

    A later run binds these. A binding that named a path would be stranded by
    any rename of the file it named; an id survives both by construction.
    """
    assert R.resolve_output_nodes("porch-teaser/latest") == [library.run_output]


def test_an_index_picks_one_output(library, tmp_path):
    local = tmp_path / "second.png"
    local.write_bytes(b"png")
    second = R.upload_output(library.run, str(local))
    assert R.resolve_output_nodes(f"{library.run}#2") == [second]


def test_asking_for_a_kind_the_run_has_none_of_says_what_it_holds(library):
    with pytest.raises(R.RunError, match="jpeg"):
        R.resolve_output_nodes(library.run, kinds={".mp4"})


def test_an_output_keyed_id_resolves_like_one_keyed_node(library, monkeypatch):
    """The live API spells it `id`; this module only read `node`.

    Every runref binding — `--ref-run`, `--image-run`, `--start-run`,
    `--end-run` and `character add-refs --from-run` — died on `KeyError:
    'node'` against a real record, while this suite stayed green because the
    in-memory API happens to write `node`. So the double, not the module, was
    what the old assertions described.
    """
    record = dict(R.resolve_run(library.run))
    record["outputs"] = [{"id": library.run_output, "name": "output-1.jpeg"}]
    monkeypatch.setattr(R, "resolve_run", lambda *a, **k: record)

    assert R.resolve_output_nodes(library.run) == [library.run_output]
    assert R.resolve_output_nodes(f"{library.run}#1") == [library.run_output]


def test_an_output_carrying_neither_spelling_says_so(library, monkeypatch):
    record = dict(R.resolve_run(library.run))
    record["outputs"] = [{"name": "output-1.jpeg"}]
    monkeypatch.setattr(R, "resolve_run", lambda *a, **k: record)

    with pytest.raises(R.RunError, match="no node id"):
        R.resolve_output_nodes(library.run)


# ── adoption ────────────────────────────────────────────────────────────────

def test_adopting_moves_the_node_and_keeps_its_id(library):
    """A move rewrites one row, so anything already naming the file still does.

    The copy-and-delete this replaced produced a different object and destroyed
    the original, which no share link survived.
    """
    from studio_pipeline.adapters import store

    loose = library.fake.put_file(library.project_root, "stray.mp4", b"mp4-bytes")
    record = R.adopt(library.project, loose["id"])
    assert record["status"] == "adopted"
    assert [o["node"] for o in record["outputs"]] == [loose["id"]]
    assert store.node(loose["id"])["name"] == "stray.mp4"


def test_adopting_something_that_is_not_there_is_refused(library):
    with pytest.raises(R.RunError, match="no such node"):
        R.adopt(library.project, "node-00000000-0000-0000-0000-000000000000")


# ── the CLI ─────────────────────────────────────────────────────────────────

def test_runs_list_prints_the_envelope(library):
    result = CliRunner().invoke(cli.main, ["runs", "list", "porch-teaser"])
    assert result.exit_code == 0, result.output
    assert "google/nano-banana-pro" in result.output
    assert "succeeded" in result.output


def test_runs_find_prints_the_hit(library):
    result = CliRunner().invoke(cli.main, ["runs", "find", "--character", "subject-a"])
    assert result.exit_code == 0, result.output
    assert library.run in result.output


def test_runs_show_prints_the_envelope_without_the_payload(library):
    result = CliRunner().invoke(cli.main, ["runs", "show", "porch-teaser/latest"])
    assert result.exit_code == 0, result.output
    assert "prediction_id" in result.output
    assert "as the provider wrote it" not in result.output


def test_runs_show_payload_prints_the_documents_verbatim(library):
    """`--payload` is the only way to see these, and studio never decodes them."""
    result = CliRunner().invoke(
        cli.main, ["runs", "show", "porch-teaser/latest", "--payload"])
    assert result.exit_code == 0, result.output
    assert "as the provider wrote it" in result.output
    assert '"prompt": "a porch"' in result.output


def test_runs_outputs_can_presign(library):
    """**`--presign` raised `TypeError` for as long as it existed.**

    The flag's parameter shadows the module function of the same name, so
    `presign(...)` called `True`. `--help` printed happily and nothing invoked
    it. Renaming the dest is not available — `cli_surface_reference.json`
    records it.
    """
    result = CliRunner().invoke(
        cli.main, ["runs", "outputs", "porch-teaser/latest", "--presign"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert "memory://" in result.output


def test_runs_delete_resolves_latest_and_prints_the_id_it_removed(library):
    """`latest` names a different run tomorrow, so the id has to come back."""
    result = CliRunner().invoke(cli.main, ["runs", "delete", "porch-teaser/latest"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert library.run in result.output
    assert library.run not in library.fake.runs


def test_runs_delete_keeps_the_folder_by_default(library):
    """The default that does not lose generated media to a typo."""
    result = CliRunner().invoke(cli.main, ["runs", "delete", library.run])
    assert result.exit_code == 0, result.output
    assert "files: keep" in result.output
    assert library.run_output in library.fake.nodes


def test_runs_delete_with_files_delete_takes_the_output_with_it(library):
    result = CliRunner().invoke(
        cli.main, ["runs", "delete", library.run, "--files", "delete"])
    assert result.exit_code == 0, result.output
    assert library.run not in library.fake.runs
    assert library.run_output not in library.fake.nodes


def test_runs_delete_reports_a_run_that_is_not_there(library):
    """A dead id is a message and a non-zero exit, not a traceback."""
    result = CliRunner().invoke(
        cli.main, ["runs", "delete", "run-00000000-0000-0000-0000-000000000000"])
    assert result.exit_code != 0
    assert "run-00000000" in result.output


# ── an unregistered model, for evaluating one before onboarding it ──────────

def test_a_registry_typo_still_fails_rather_than_reaching_a_provider(library):
    """The guard on the live-model path: a registry key never contains a slash,
    so a misspelt one cannot be mistaken for `owner/name`."""
    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-bannana-pro", "--project", "porch-teaser",
        "--prompt", "x", "--no-refs", "--dry-run"])

    assert result.exit_code != 0
    assert "nano-bannana-pro" in result.output


def test_an_owner_slash_name_is_inferred_from_the_live_schema(library, monkeypatch):
    """**Evaluating a model used to mean leaving the harness entirely.**

    A four-way upscaler comparison ran three models straight against Replicate
    off presigned URLs: no schema validation, no approval render, no run
    records. `owner/name` now takes the ordinary path with an entry inferred in
    memory — and writes nothing to `models.json`, because onboarding is a
    separate decision with a skill page attached.
    """
    from studio_pipeline.engine import runner as RUNNER

    monkeypatch.setattr(RUNNER.RA, "load_token", lambda: "r8_test")
    monkeypatch.setattr(RUNNER.MS, "fetch", lambda model, token: (
        {"image": {"type": "string", "format": "uri"},
         "upscale_factor": {"type": "string"}}, {}))
    monkeypatch.setattr(RUNNER.AM, "readme", lambda model, token: "an upscaler")

    entry = RUNNER._ephemeral_entry("vendor/an-upscaler")

    assert entry["key"] == "vendor/an-upscaler"
    assert entry["model"] == "vendor/an-upscaler"
    assert entry["prompt"] is None, "no prompt input in the schema"
    assert entry["images"]["start"] == "image"


# ── the approval gate, from this side of the wire ───────────────────────────
#
# Hard rule #2 says never submit without approval of the full payload, and
# re-approve after any edit. Until now that was a `click.confirm` in a terminal
# and nothing else: it left no trace, so nothing could check that the payload
# somebody said yes to was the payload that went out.


def test_a_draft_cannot_be_submitted_until_it_is_approved(library):
    """The refusal comes from the API, so it binds the app as well as the CLI."""
    from studio_pipeline.adapters import api

    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={"prompt": "a porch"}, bindings={})

    with pytest.raises(api.ApiError):
        E.patch_run(record["id"], status="running")


def test_approving_then_rewording_the_prompt_refuses_the_submission(library):
    """**Approve-then-edit, the failure the digest exists to catch.**

    A payload is approved, a prompt is reworded, and the run goes out carrying
    words nobody read. The rule said not to; nothing checked it.
    """
    from studio_pipeline.adapters import api

    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={"prompt": "a porch"}, bindings={})
    E.approve_run(record["id"], record["plan_digest"])

    E.patch_run_plan(record["id"], {"prompt": "a porch at dusk"})

    with pytest.raises(api.ApiError):
        E.patch_run(record["id"], status="running")


def test_the_cli_approves_a_draft_only_after_showing_its_payload(library):
    """`runs approve` re-renders the payload and asks. **There is no `--yes`.**

    An approval flag is the door an agent walks through while believing some
    earlier exchange counted as approval — the sentence `board.py` and
    `shoot.py` both already carry. It matters more here, because what this
    writes is a durable record that somebody said yes.
    """
    # A plan, because that is what `submit.draft` writes — the render reads what
    # is STORED rather than rebuilding a payload from arguments, so a run with no
    # plan has nothing to show and that is the honest answer.
    record = R.record_request(library.project, kind="image", engine="e",
                              model="google/nano-banana-pro",
                              input={"prompt": "a porch at dawn"},
                              plan={"prompt": "a porch at dawn",
                                    "params": {"output_format": "png"}},
                              sends=[{"field": "image_input", "role": "reference",
                                      "node": library.face_1}],
                              bindings={"image_input": [library.face_1]})

    result = CliRunner().invoke(cli.main, ["runs", "approve", record["id"]], input="y\n")

    assert result.exit_code == 0, result.output
    assert "a porch at dawn" in result.output, "the payload is shown before the ask"
    assert "IMAGES" in result.output, "the pictures are part of the payload"
    assert E.get_run(record["id"])["status"] == "approved"


def test_declining_the_cli_gate_approves_nothing(library):
    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={"prompt": "a porch"}, bindings={})

    result = CliRunner().invoke(cli.main, ["runs", "approve", record["id"]], input="n\n")

    assert result.exit_code == 1
    assert E.get_run(record["id"])["status"] == "draft"


def test_discarding_a_draft_removes_it_and_its_folder(library):
    """**`--files delete` by default, the opposite of `runs delete`.**

    A submitted run's folder holds media somebody paid for. A draft's holds two
    payload documents and an empty `output/` — nothing was ever made — so keeping
    it by default would leave an orphan per abandoned idea.
    """
    from studio_pipeline.adapters import api

    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})

    result = CliRunner().invoke(cli.main, ["runs", "discard", record["id"]])

    assert result.exit_code == 0, result.output
    with pytest.raises(api.NotFound):
        E.get_run(record["id"])


def test_a_submitted_run_cannot_be_discarded(library):
    """`discard` is for work that never happened; `delete` is for work that did."""
    result = CliRunner().invoke(cli.main, ["runs", "discard", library.run])

    assert result.exit_code != 0
    assert "delete" in result.output


def test_the_sends_carry_the_role_the_registry_gives_them(library):
    """The half `bindings` threw away.

    `gather` decides an image is a start frame or a reference and then records a
    `{field: [node, …]}` map, so a run page could say six images went out and
    never which was which.
    """
    from studio_pipeline.engine import registry as REG
    from studio_pipeline.engine import submit as SUB

    entry = REG.get("kling")
    sends = SUB.sends_for(entry, {"start_image": library.input_3,
                                  "reference_images": [library.face_1, library.face_2]})

    assert [(s["field"], s["role"]) for s in sends] == [
        ("start_image", "start"),
        ("reference_images", "reference"),
        ("reference_images", "reference"),
    ]


def test_the_plan_is_the_prompt_and_the_params_and_no_images(library):
    """**`plan` is studio's; `request.json` is the provider's.**

    The line is the same one a scene already holds — a shot's `motion.prompt` is
    authored and queryable while the run it renders into keeps the provider
    payload as an undecoded blob. It carries no image fields at all: those are
    sends, presigned in at the last moment.
    """
    from studio_pipeline.engine import registry as REG
    from studio_pipeline.engine import submit as SUB

    plan = SUB.plan_of(REG.get("nano-banana-pro"),
                       {"prompt": "a porch", "aspect_ratio": "9:16",
                        "output_format": "png"})

    assert plan["prompt"] == "a porch"
    assert plan["params"] == {"aspect_ratio": "9:16", "output_format": "png"}
    assert plan["origin"] == "authored"


def test_a_dry_run_leaves_a_draft_that_can_be_approved_and_submitted(library, monkeypatch):
    """**The flow this whole change exists for, end to end.**

    `--dry-run` rendered a payload to a terminal and kept nothing, so the thing
    hard rule #2 asks a person to read had no address: it could not be opened in
    the app, linked to, or approved later. It leaves a draft now, and the draft
    is what `runs approve` and `runs submit` act on.

    The three steps are deliberately three commands. Reading a payload and
    sending it are different acts, and the whole point of recording an approval
    is that they can happen in different places — a terminal, or a browser.
    """
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")

    dry = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "a porch at dawn", "--key", library.face_1, "--dry-run",
    ])
    assert dry.exit_code == 0, dry.output

    drafts = E.query_runs(project=library.project, status="draft")["runs"]
    assert len(drafts) == 1, "a dry run leaves exactly one draft"
    draft = E.get_run(drafts[0]["id"])
    assert draft["status"] == "draft"
    assert draft["plan"]["prompt"] == "a porch at dawn"
    assert [s["role"] for s in draft["sends"]] == ["reference"]

    approved = CliRunner().invoke(cli.main, ["runs", "approve", draft["id"]], input="y\n")
    assert approved.exit_code == 0, approved.output

    submitted = CliRunner().invoke(cli.main, ["runs", "submit", draft["id"]])
    assert submitted.exit_code == 0, submitted.output

    after = E.get_run(draft["id"])
    assert after["status"] == "succeeded"
    assert after["outputs"], "the submitted draft produced its output"


def test_a_dry_run_bills_nothing(library, monkeypatch):
    """A draft costs a row and no bytes. **Nothing reaches the provider.**"""
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r8_fake")

    result = CliRunner().invoke(cli.main, [
        "run", "--model", "nano-banana-pro", "--project", "porch-teaser",
        "--prompt", "a porch", "--key", library.face_1, "--dry-run",
    ])

    assert result.exit_code == 0, result.output
    draft = E.get_run(E.query_runs(project=library.project, status="draft")["runs"][0]["id"])
    assert draft["prediction_id"] is None
    assert draft["outputs"] == []
    assert draft["approval"] is None
