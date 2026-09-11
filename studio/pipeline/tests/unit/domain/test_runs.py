"""`domain/runs` — the run store, now an envelope in a row.

**These run against the in-memory API, not against a stubbed store.** The old
suite scripted `api.get`/`api.post` per route and asserted the request bodies,
which proved the module was self-consistent and nothing else. Everything here
goes through `adapters/entities` and `adapters/store` for real, so a route name
or a field spelling that drifted from the backend fails here.
"""

from __future__ import annotations

from studio_pipeline.domain import paths as P

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E
from studio_pipeline.domain import runs as R
from tests.support.fake_api import add_run_output


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

    `status` is `draft` and there are no outputs — the run exists, and the
    submission has not happened. A store that recorded nothing until success
    would lose exactly the runs worth investigating; a store that recorded
    nothing until the submission would leave the payload a person is supposed
    to read with no address.
    """
    record = R.record_request(library.project, kind="image",
                              engine="nano-banana-pro",
                              model="google/nano-banana-pro",
                              input={"prompt": "a porch"},
                              bindings={"image_input": [library.face_1]},
                              characters=[library.character])
    assert record["status"] == "draft"
    assert record["outputs"] == []
    assert "approval" not in record and "plan_digest" not in record
    assert record["fingerprint"].startswith("sha256:")
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

def _output(library, name: str, body: bytes = b"jpeg-out"):
    """An output on a run, put there the way the API puts one there.

    **`R.upload_output` is gone and this is not a replacement for it.** That
    function downloaded a provider's file and pushed it up from this machine; the
    API does both now, off a callback. What survives is the route it used —
    `POST /api/runs/<id>/outputs` — spelled by the suite's own helper rather
    than the adapter, because filing an output is the API's act and all these
    tests need is a run that has produced something.
    """
    from tests.conftest import _confirm

    signed = add_run_output(library.run, name, len(body),
                            "image/png" if name.endswith(".png") else "image/jpeg")
    _confirm(library.fake, signed, body)
    return signed["node"]


def test_outputs_come_back_in_the_order_the_run_recorded(library):
    """**Order is the record's, not a listing's**, and that is a real change.

    It was a natural sort over `output/`'s children because the folder was the
    only source — which is why `-10` sorting before `-2` was a live hazard. The
    row holds the order they were written in, so there is nothing to re-derive.
    """
    _output(library, "out-10.png", b"png")
    _output(library, "out-2.png", b"png")
    assert [o["name"] for o in R.run_outputs(library.run)] == [
        "output-1.jpeg", "out-10.png", "out-2.png"]


def test_a_run_that_never_produced_output_has_none(library):
    """A failure or a timeout legitimately has none, and that is not an error."""
    record = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})
    assert R.run_outputs(record["id"]) == []


# ── completion ──────────────────────────────────────────────────────────────

# **The two tests that were here are deleted, and the deletion is the point.**
#
# They exercised `R.record_result` — `PATCH` the envelope closed, store the
# provider's response beside it, stringify an exception on the way in. That
# function is gone: a run is closed by the API, off a callback, in
# `services/generate.close_from_prediction`, and a second closing implementation
# reachable from a terminal is exactly what this change was for.
#
# What they asserted is asserted in `backend/tests/unit/test_generate.py`, where
# the code now lives. What is tested from THIS side is that a submission reaches
# a closed run at all, which is `test_submitting_a_draft_closes_the_run` below.


def test_submitting_a_draft_closes_the_run(library):
    """**One call submits, and something else closes it.** The whole change.

    `studio runs submit` used to create the prediction, poll it, download every
    output and patch the row — in this process, so a 15-minute video meant a
    terminal nobody could close. It is `POST /api/runs/<id>/submit` and a
    callback now: this waits, and the run finishes whether it waits or not.

    The wait is driven by whichever mechanism the API says will close the run —
    here `poll`, so `reconcile` does it, which is what a machine with no callback
    receiver provisioned sees.
    """
    record = R.record_request(library.project, kind="image", engine="e",
                              model="google/nano-banana-pro",
                              input={"prompt": "a porch"}, bindings={},
                              name="a-porch")

    from studio_pipeline.engine import resubmit

    closed = resubmit.submit_draft(E.get_run(record["id"]))

    assert closed["status"] == "succeeded"
    assert closed["prediction_id"], "a submitted run names its prediction"
    assert len(closed["outputs"]) == 1
    # The name was recorded on the DRAFT, because the thing that downloads the
    # file arrives with no request body and could not otherwise know it.
    assert closed["outputs"][0]["name"] == "a-porch.png"


def test_a_submission_that_is_never_answered_is_closed_by_reconcile(library):
    """`studio runs reconcile` — for a callback that did not arrive.

    A generation is closed by something else now, and that something else can
    fail to happen: a deploy landing mid-flight, a signature the API refused, a
    queue nobody drained. The run sits at `running` with a prediction id, which
    is legible and never resolves. This is what resolves it, and it is safe to
    repeat.
    """
    record = R.record_request(library.project, kind="image", engine="e",
                              model="google/nano-banana-pro",
                              input={"prompt": "a porch"}, bindings={})
    sent = E.submit_run(record["id"])
    assert sent["status"] == "running", "submitted, and not yet closed"

    closed = E.reconcile_run(record["id"])
    assert closed["status"] == "succeeded"

    # Idempotent: a webhook is at-least-once and a person may run this twice.
    again = E.reconcile_run(record["id"])
    assert again["status"] == "succeeded"
    assert len(again["outputs"]) == 1, "a repeat must not upload the output twice"


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
    assert [r["id"] for r in R.find_runs(character=P.by_name(E.list_characters(), "subject-a", "character")["id"])] == [
        library.run]


def test_a_character_that_was_not_used_finds_nothing(library):
    assert R.find_runs(character=P.by_name(E.list_characters(), "subject-b", "character")["id"]) == []


def test_listing_filters_on_model_and_status(library):
    """**New filters, free from the row.** Neither existed at any price before."""
    assert R.list_runs(library.project, model="google/nano-banana-pro")
    assert R.list_runs(library.project, model="nope") == []
    assert R.list_runs(library.project, status="succeeded")
    assert R.list_runs(library.project, status="failed") == []


def test_listing_accepts_a_slug_a_person_typed(library):
    assert R.list_runs(P.by_name(E.list_projects(), "porch-teaser", "project")["id"])


# ── runrefs ─────────────────────────────────────────────────────────────────

def _submit(record: dict) -> None:
    """Move a draft to `succeeded`. No approve step stands in the way."""
    E.patch_run(record["id"], status="succeeded")


def test_latest_resolves_to_the_newest_run(library):
    newest = R.record_request(library.project, kind="image", engine="e",
                              model="m", input={}, bindings={})
    _submit(newest)
    assert R.resolve_run("porch-teaser/latest")["id"] == newest["id"]


def test_latest_skips_a_draft(library):
    """**A fake/API divergence this move exposed.**

    `record_request` creates a DRAFT, and this file used to assert that `latest`
    found one — which passed only because the fake's run listing never hid them
    and the real `GET /api/runs` always has. So the assertion described the
    fake's behaviour rather than the service's, and the same call against
    production would have raised "no runs in project".

    Skipping is the right answer on its merits too: `latest` is overwhelmingly
    asked in order to chain off something, and a draft has no output to chain
    from.
    """
    submitted = R.record_request(library.project, kind="image", engine="e",
                                 model="m", input={}, bindings={})
    _submit(submitted)
    R.record_request(library.project, kind="image", engine="e",
                     model="m", input={}, bindings={})

    assert R.resolve_run("porch-teaser/latest")["id"] == submitted["id"]


def test_a_draft_can_be_asked_for_explicitly(library):
    """`include=drafts`, the same opt-in `GET /api/runs` already takes."""
    draft = R.record_request(library.project, kind="image", engine="e",
                             model="m", input={}, bindings={})
    found = E.resolve_run(f"{library.project}/latest", include="drafts")
    assert found["id"] == draft["id"]


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


def test_an_index_picks_one_output(library):
    second = _output(library, "second.png", b"png")
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
    off presigned URLs: no schema validation, no payload render, no run
    records. `owner/name` now takes the ordinary path with an entry inferred in
    memory — and writes nothing to `models.json`, because onboarding is a
    separate decision with a skill page attached.
    """
    from studio_pipeline.engine import runner as RUNNER

    # **No token to patch any more.** The schema is read through
    # `GET /api/models/<name>/schema`, so what a test stubs is the fetch rather
    # than a credential the CLI no longer holds.
    monkeypatch.setattr(RUNNER.MS, "fetch", lambda model: (
        {"image": {"type": "string", "format": "uri"},
         "upscale_factor": {"type": "string"}}, {}))
    monkeypatch.setattr(RUNNER.AM, "readme", lambda model: "an upscaler")

    entry = RUNNER._ephemeral_entry("vendor/an-upscaler")

    assert entry["key"] == "vendor/an-upscaler"
    assert entry["model"] == "vendor/an-upscaler"
    assert entry["prompt"] is None, "no prompt input in the schema"
    assert entry["images"]["start"] == "image"


# ── submitting a draft, from this side of the wire ──────────────────────────
#
# Hard rule #2 — nothing runs unless a person tells it to — is met by who
# types `studio runs submit`, not by a recorded yes. Decision 2026-09-04: the
# approve step is gone everywhere; the submit command is the act.


def _draft_with_a_plan(library, prompt):
    return R.record_request(library.project, kind="image", engine="e",
                            model="google/nano-banana-pro",
                            input={"prompt": prompt},
                            plan={"prompt": prompt,
                                  "params": {"output_format": "png"}},
                            sends=[{"field": "image_input", "role": "reference",
                                    "node": library.face_1}],
                            bindings={"image_input": [library.face_1]})


def test_there_is_no_approve_command(library):
    """`studio runs approve` is gone, `--relayed` with it."""
    record = _draft_with_a_plan(library, "a porch at dawn")
    result = CliRunner().invoke(cli.main, ["runs", "approve", record["id"]])
    assert result.exit_code != 0
    assert "No such command" in result.output
    assert E.get_run(record["id"])["status"] == "draft"


def test_submit_takes_a_draft_straight_out(library):
    """No approve step: a draft submits, and the command is the act."""
    record = _draft_with_a_plan(library, "a porch at dawn")

    result = CliRunner().invoke(cli.main, ["runs", "submit", record["id"]])

    assert result.exit_code == 0, result.output
    assert E.get_run(record["id"])["status"] == "succeeded"


def test_submit_refuses_a_run_that_already_went_out(library):
    record = _draft_with_a_plan(library, "a porch at dawn")
    E.patch_run(record["id"], status="succeeded")

    result = CliRunner().invoke(cli.main, ["runs", "submit", record["id"]])

    assert result.exit_code != 0
    assert "not a draft" in result.output


def test_submit_has_no_yes_flag():
    """No flag on a command that spends stands in for a person."""
    submit = cli.main.commands["runs"].commands["submit"]
    names = {opt for param in submit.params for opt in param.opts}
    assert names == {"runref", "--project"}, names


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


# ── editing a draft ─────────────────────────────────────────────────────────
#
# The routes have existed since a run gained a plan and nothing called them, so
# a typo in a prompt meant discarding the draft and drafting it again. What each
# of these holds up is that an edit writes only what moved, and that an edited
# draft is still a draft — a payload to read again before saying to send it.


def _draft(library, **over):
    """A draft with a plan and one bound image — what `--dry-run` leaves."""
    fields = {"kind": "image", "engine": "e", "model": "google/nano-banana-pro",
              "input": {"prompt": "a porch at dawn"},
              "plan": {"prompt": "a porch at dawn",
                       "params": {"output_format": "png"}},
              "sends": [{"field": "image_input", "role": "reference",
                         "node": library.face_1},
                        {"field": "image_input", "role": "reference",
                         "node": library.face_2}],
              "bindings": {"image_input": [library.face_1, library.face_2]}}
    return R.record_request(library.project, **{**fields, **over})


def _edit(run_id: str, document: dict):
    return CliRunner().invoke(
        cli.main, ["runs", "edit", run_id, "--file", "-"],
        input=json.dumps(document))


def test_editing_a_prompt_rewrites_the_plan_and_leaves_the_images(library):
    """Two routes, so only what moved is written."""
    record = _draft(library)
    document = R.editable(E.get_run(record["id"]))
    document["prompt"] = "a porch at dusk"

    result = _edit(record["id"], document)

    assert result.exit_code == 0, result.output
    updated = E.get_run(record["id"])
    assert updated["plan"]["prompt"] == "a porch at dusk"
    assert updated["plan"]["params"] == {"output_format": "png"}, "untouched"
    assert [s["node"] for s in updated["sends"]] == [library.face_1, library.face_2]


def test_reordering_the_images_is_a_real_edit(library):
    """**The order is the payload.** A prompt citing "the first image" cites this
    list, so swapping two sends changes what the model is told as surely as
    rewording the sentence does."""
    record = _draft(library)
    document = R.editable(E.get_run(record["id"]))
    document["sends"] = list(reversed(document["sends"]))

    result = _edit(record["id"], document)

    assert result.exit_code == 0, result.output
    updated = E.get_run(record["id"])
    assert [s["node"] for s in updated["sends"]] == [library.face_2, library.face_1]
    assert updated["plan"]["prompt"] == "a porch at dawn", "untouched"


def test_an_edit_leaves_a_draft_and_says_to_read_it_again(library):
    """An edited draft is a payload nobody has read yet.

    Hard rule #2 says show it again; the command ends by naming the two
    commands that do — `runs show`, then `runs submit` once told to.
    """
    record = _draft(library)

    document = R.editable(E.get_run(record["id"]))
    document["params"] = {"output_format": "webp"}
    result = _edit(record["id"], document)

    assert result.exit_code == 0, result.output
    updated = E.get_run(record["id"])
    assert updated["status"] == "draft"
    assert "approval" not in updated
    assert "runs show" in result.output and "runs submit" in result.output


def test_a_document_naming_only_one_field_leaves_the_rest_alone(library):
    """What makes `echo '{"prompt": "…"}' | studio runs edit … --file -` legal."""
    record = _draft(library)

    result = _edit(record["id"], {"prompt": "a porch at noon"})

    assert result.exit_code == 0, result.output
    updated = E.get_run(record["id"])
    assert updated["plan"]["prompt"] == "a porch at noon"
    assert updated["plan"]["params"] == {"output_format": "png"}
    assert len(updated["sends"]) == 2


def test_an_unchanged_document_writes_nothing(library):
    """Saving an editor without touching it is not an edit, and must not move
    the fingerprint as though it were."""
    record = _draft(library)
    before = E.get_run(record["id"])["fingerprint"]

    result = _edit(record["id"], R.editable(E.get_run(record["id"])))

    assert result.exit_code == 0, result.output
    assert "no changes" in result.output
    assert E.get_run(record["id"])["fingerprint"] == before


def test_a_submitted_run_cannot_be_edited(library):
    """Its plan is what was sent. Refused here as well as by the API — the point
    is not to reach the route, it is not to open an editor over a document that
    cannot be written back."""
    result = CliRunner().invoke(
        cli.main, ["runs", "edit", library.run, "--file", "-"], input="{}")

    assert result.exit_code != 0
    assert "cannot be rewritten" in result.output


def test_an_unknown_role_is_named_rather_than_round_tripped(library):
    record = _draft(library)
    document = R.editable(E.get_run(record["id"]))
    document["sends"][0]["role"] = "backdrop"

    result = _edit(record["id"], document)

    assert result.exit_code != 0
    assert "reference" in result.output, "the legal roles are listed"


def test_invalid_json_changes_nothing_and_says_how_to_retry(library):
    """The editor buffer is gone by the time this is discovered, so the message
    has to be enough to act on."""
    record = _draft(library)

    result = CliRunner().invoke(
        cli.main, ["runs", "edit", record["id"], "--file", "-"], input="{not json")

    assert result.exit_code != 0
    assert "valid JSON" in result.output
    assert E.get_run(record["id"])["plan"]["prompt"] == "a porch at dawn"


def test_dump_prints_the_document_and_changes_nothing(library):
    """The non-interactive half: dump, edit, pipe back."""
    record = _draft(library)

    result = CliRunner().invoke(cli.main, ["runs", "edit", record["id"], "--dump"])

    assert result.exit_code == 0, result.output
    document = json.loads(result.output)
    assert document["prompt"] == "a porch at dawn"
    assert [s["node"] for s in document["sends"]] == [library.face_1, library.face_2]
    assert "source" not in document["sends"][0], "derived, and not the digest's"


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


def test_a_dry_run_leaves_a_draft_that_can_be_submitted(library, monkeypatch):
    """**The flow this whole change exists for, end to end.**

    `--dry-run` rendered a payload to a terminal and kept nothing, so the thing
    hard rule #2 asks a person to read had no address: it could not be opened in
    the app, linked to, or submitted later. It leaves a draft now, and the draft
    is what `runs submit` acts on.

    Two commands, deliberately. Reading a payload and sending it are different
    acts, and they can happen in different places — a terminal, or a browser.
    There is no third: the submit command is the act, and no approve step
    stands between the two (decision 2026-09-04).
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
    assert "studio runs submit" in dry.output, "the dry run names the next act"

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
    assert "approval" not in draft
