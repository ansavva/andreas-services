"""The feed projection on `GET /api/runs?view=feed`, and the prompt search `?q=`.

The runs feed draws one row per run — the plan, what went in, what came out,
the cost, the timings — from a single list call. The plain listing cannot feed
it: a listing row is a deliberate projection (status, model, kind, one
thumbnail) precisely so that the grid, the CLI and the duplicate-submission
check never read an envelope. So the feed **asks** for the wider shape, and
these tests hold the two apart: the plain listing stays cheap, the feed row
carries everything the SPA's `RunFeedRow` declares, and neither leaks the
approval.

`?q=` is a post-filter over envelopes because the catalog has no text index.
What these tests defend is that its paging **terminates** — every call moves
the cursor on, bounded by `config.max_search_scan` — and that a match is
returned exactly once however the scan cap and the page size fall.
"""

from studio_core.services import catalog, layout


def _project(api, name="rooftop-teaser", **body):
    return api.post("/api/projects", json={"name": name, **body}).get_json()


def _character(api, name="subject-a"):
    return api.post("/api/characters", json={"name": name}).get_json()


def _child(parent_id, name):
    return catalog.node(catalog.child_by_name(parent_id, name)["node_id"])


def _uploaded(api, parent_id, name, body=b"webp-bytes"):
    node = api.post(
        "/api/nodes", json={"parent": parent_id, "name": name, "kind": "file"}
    ).get_json()
    record = catalog.node(node["id"])
    return catalog.set_blob(
        node["id"], record["blob_key"], size=len(body), content_type="image/webp"
    )


def _create(api, project, prompt="a wave", **body):
    resp = api.post(
        "/api/runs",
        json={
            "project": project["id"],
            "kind": "image",
            "engine": "nano-banana-pro",
            "model": "google/nano-banana-pro",
            "plan": {"version": 1, "origin": "authored", "prompt": prompt,
                     "params": {"aspect_ratio": "3:4", "outputs": 4}},
            **body,
        },
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _listed(api, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    resp = api.get(f"/api/runs?{query}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()


# ───────────────────────────── the projection ─────────────────────────────


# The fields the SPA's `RunFeedRow` declares required, in
# `studio/frontend/src/types/index.ts`. A literal on purpose, for the same
# reason `test_runs.RUN_SUMMARY_REQUIRED` is one: the two halves cannot import
# from each other, so the contract is asserted here rather than shared.
RUN_FEED_REQUIRED = {
    "id", "project", "status", "kind", "model", "engine", "created", "updated",
    "submitted", "completed", "cost", "error", "plan", "characters", "cast",
    "sends", "outputs", "thumb",
}


def test_a_feed_row_carries_every_field_the_spa_declares(empty_api):
    project = _project(empty_api)
    _create(empty_api, project)

    (row,) = _listed(empty_api, project=project["id"], include="drafts",
                     view="feed")["runs"]

    missing = RUN_FEED_REQUIRED - set(row)
    assert not missing, f"the feed row is missing {sorted(missing)}"
    # The approval is the run page's business and a gate the feed never
    # operates; a row carrying it would have to be kept in step with one.
    assert "approval" not in row and "plan_digest" not in row and "stale" not in row


def test_a_feed_row_expands_sends_outputs_and_cast_from_one_list_call(empty_api):
    """**The point.** No `GET /api/runs/<id>` per row."""
    character = _character(empty_api)
    project = _project(empty_api)
    picture = _uploaded(empty_api, _child(character["root"], "reference")["node_id"], "a.webp")
    run = _create(
        empty_api, project,
        sends=[{"field": "image_input", "role": "reference", "node": picture["node_id"]}],
    )
    output = empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "frame.png", "size": 3, "content_type": "image/png"},
    ).get_json()
    empty_api.patch(f"/api/runs/{run['id']}",
                    json={"cost": {"currency": "USD", "amount": 0.14}})

    (row,) = _listed(empty_api, project=project["id"], include="drafts",
                     view="feed")["runs"]

    assert row["plan"]["prompt"] == "a wave"
    assert row["plan"]["params"] == {"aspect_ratio": "3:4", "outputs": 4}
    assert row["engine"] == "nano-banana-pro"
    assert row["cost"] == {"currency": "USD", "amount": 0.14}

    (send,) = row["sends"]
    assert send["role"] == "reference"
    assert send["source"] == {"kind": "character", "character": character["id"]}
    assert send["node"] == picture["node_id"]
    assert send["name"] == "a.webp" and send["url"]

    (out,) = row["outputs"]
    assert out["node"] == output["node"] and out["name"] == "frame.png" and out["url"]
    # The thumbnail is the first output, so a row never has to reconcile two.
    assert row["thumb"] == {"node": out["node"], "url": out["url"]}

    # The cast by NAME, derived from the sends' provenance when the record
    # names nobody — the same answer `_cast` gives, without a read per image.
    assert row["characters"] == []
    assert row["cast"] == [{"id": character["id"], "name": "subject-a"}]


def test_a_feed_row_names_the_records_own_cast_first(empty_api):
    character = _character(empty_api, name="subject-b")
    project = _project(empty_api)
    _create(empty_api, project, characters=[character["id"]])

    (row,) = _listed(empty_api, project=project["id"], include="drafts",
                     view="feed")["runs"]

    assert row["characters"] == [character["id"]]
    assert row["cast"] == [{"id": character["id"], "name": "subject-b"}]


def test_a_run_with_nothing_bound_and_nothing_made_still_has_a_row(empty_api):
    project = _project(empty_api)
    _create(empty_api, project)

    (row,) = _listed(empty_api, project=project["id"], include="drafts",
                     view="feed")["runs"]

    assert row["sends"] == [] and row["outputs"] == [] and row["cast"] == []
    assert row["thumb"] is None and row["submitted"] is None


def test_a_feed_row_carries_a_fingerprint_only_when_the_run_has_one(empty_api):
    """The listing row's rule, kept: present as a string or absent, never null,
    so `RunFeedRow` can extend `RunSummary` without widening the field."""
    from studio_core.routes.runs import _feed_row

    project = _project(empty_api)
    _create(empty_api, project)
    (row,) = _listed(empty_api, project=project["id"], include="drafts",
                     view="feed")["runs"]
    assert row["fingerprint"].startswith("sha256:")

    bare = _feed_row({"id": "run-x", "created": "2026-01-01T00:00:00+00:00"}, {}, [], {})
    assert "fingerprint" not in bare


def test_the_plain_listing_stays_the_projection(empty_api):
    """The grid, the CLI and the fingerprint check read a row, not an envelope.

    A default that expanded every row would make the duplicate-submission
    check read fifty envelopes and sign two hundred URLs to answer a yes/no.
    """
    project = _project(empty_api)
    _create(empty_api, project)

    (row,) = _listed(empty_api, project=project["id"], include="drafts")["runs"]

    assert "plan" not in row and "sends" not in row and "outputs" not in row


def test_a_feed_over_a_characters_runs_draws_the_same_shape(empty_api):
    """`?character=` answers with envelopes and `?project=` with rows; the feed
    projects both to one shape, so a screen cannot tell which it was given."""
    character = _character(empty_api)
    project = _project(empty_api)
    _create(empty_api, project, characters=[character["id"]])

    by_character = _listed(empty_api, character=character["id"], include="drafts",
                           view="feed")["runs"]
    by_project = _listed(empty_api, project=project["id"], include="drafts",
                         view="feed")["runs"]

    assert by_character == by_project
    assert "approval" not in by_character[0]


def test_a_feed_page_is_clamped_and_continues(empty_api, monkeypatch):
    """A larger `limit` is clamped, not refused — a page of a project is allowed
    to be shorter than the project — and `cursor` says there is more."""
    monkeypatch.setenv("STUDIO_MAX_FEED_ROWS", "2")
    project = _project(empty_api)
    made = [_create(empty_api, project)["id"] for _ in range(3)]

    first = _listed(empty_api, project=project["id"], include="drafts",
                    view="feed", limit=10)
    assert [row["id"] for row in first["runs"]] == [made[2], made[1]]
    assert first["cursor"] == "2"

    second = _listed(empty_api, project=project["id"], include="drafts",
                     view="feed", cursor=first["cursor"])
    assert [row["id"] for row in second["runs"]] == [made[0]]
    assert second["cursor"] is None


def test_a_view_that_is_not_feed_is_refused(empty_api):
    project = _project(empty_api)
    resp = empty_api.get(f"/api/runs?project={project['id']}&view=grid")
    assert resp.status_code == 400


# ───────────────────────────── the prompt search ─────────────────────────────


def test_q_matches_the_prompt_case_insensitively_within_the_scope(empty_api):
    here = _project(empty_api, name="here")
    there = _project(empty_api, name="there")
    wave = _create(empty_api, here, prompt="A slow WAVE at dusk")
    _create(empty_api, here, prompt="a rooftop at noon")
    _create(empty_api, there, prompt="another wave")

    found = _listed(empty_api, project=here["id"], include="drafts", q="wave")

    assert [row["id"] for row in found["runs"]] == [wave["id"]]
    assert found["cursor"] is None


def test_q_searches_a_structured_prompts_words_not_its_keys(empty_api):
    """A video prompt is a JSON document whose keys are the schema's words —
    matching on `camera` would match every one ever written."""
    project = _project(empty_api)
    run = _create(empty_api, project,
                  prompt={"camera": "slow push-in", "beats": [{"action": "turns"}]})

    assert _listed(empty_api, project=project["id"], include="drafts",
                   q="camera")["runs"] == []
    assert [row["id"] for row in _listed(empty_api, project=project["id"],
                                         include="drafts", q="push-in")["runs"]] \
        == [run["id"]]
    assert [row["id"] for row in _listed(empty_api, project=project["id"],
                                         include="drafts", q="turns")["runs"]] \
        == [run["id"]]


def test_q_pages_terminate_however_rare_the_match(empty_api, monkeypatch):
    """**Every call advances.** With the scan capped at two rows over five runs
    where only the oldest matches, the first two pages are empty with a cursor
    still set — "keep going" — and the third finds it and ends."""
    monkeypatch.setenv("STUDIO_MAX_SEARCH_SCAN", "2")
    project = _project(empty_api)
    needle = _create(empty_api, project, prompt="the one with the needle")
    for _ in range(4):
        _create(empty_api, project, prompt="hay")

    pages, cursor, found = 0, None, []
    while True:
        page = _listed(empty_api, project=project["id"], include="drafts", q="needle",
                       **({"cursor": cursor} if cursor else {}))
        pages += 1
        found += [row["id"] for row in page["runs"]]
        cursor = page["cursor"]
        if cursor is None or pages > 10:
            break

    assert pages == 3
    assert found == [needle["id"]]


def test_q_fills_a_limit_without_skipping_or_repeating(empty_api, monkeypatch):
    """When the page fills mid-scan the cursor points just past the last row
    returned, so the rows the scan had read past it are looked at again next
    time rather than lost."""
    monkeypatch.setenv("STUDIO_MAX_SEARCH_SCAN", "10")
    project = _project(empty_api)
    ids = []
    for index in range(6):
        run = _create(empty_api, project,
                      prompt="wave" if index % 2 == 0 else "hay")
        if index % 2 == 0:
            ids.append(run["id"])

    seen, cursor = [], None
    for _ in range(10):
        page = _listed(empty_api, project=project["id"], include="drafts", q="wave",
                       limit=1, **({"cursor": cursor} if cursor else {}))
        seen += [row["id"] for row in page["runs"]]
        cursor = page["cursor"]
        if cursor is None:
            break

    assert seen == list(reversed(ids))
    assert cursor is None


def test_q_composes_with_the_other_filters_and_the_feed(empty_api):
    project = _project(empty_api)
    wave = _create(empty_api, project, prompt="a wave")
    _create(empty_api, project, prompt="a wave", model="openai/gpt-image-2")

    found = _listed(empty_api, project=project["id"], status="draft", q="WAVE",
                    model="google/nano-banana-pro", view="feed")

    (row,) = found["runs"]
    assert row["id"] == wave["id"]
    assert row["plan"]["prompt"] == "a wave"


def test_q_over_a_characters_runs_reads_no_envelope_twice(empty_api):
    """`?character=` already holds the envelopes; the search uses them as they are."""
    character = _character(empty_api)
    project = _project(empty_api)
    wave = _create(empty_api, project, prompt="a wave", characters=[character["id"]])
    _create(empty_api, project, prompt="hay", characters=[character["id"]])

    found = _listed(empty_api, character=character["id"], include="drafts", q="wave")

    assert [row["id"] for row in found["runs"]] == [wave["id"]]


def test_q_over_the_whole_library_walks_every_project(empty_api):
    one = _create(empty_api, _project(empty_api, name="one"), prompt="a wave")
    two = _create(empty_api, _project(empty_api, name="two"), prompt="the wave")
    _create(empty_api, _project(empty_api, name="three"), prompt="hay")

    found = _listed(empty_api, include="drafts", q="wave")

    assert {row["id"] for row in found["runs"]} == {one["id"], two["id"]}


def test_the_output_folder_is_where_the_feed_finds_outputs(empty_api):
    """Sanity on the layout the feed relies on: an output is a node under the
    run's `output/`, and the feed reports it by node rather than by path."""
    project = _project(empty_api)
    run = _create(empty_api, project)
    output = empty_api.post(
        f"/api/runs/{run['id']}/outputs",
        json={"name": "clip.mp4", "size": 3, "content_type": "video/mp4"},
    ).get_json()

    folder = _child(run["folder"], layout.OUTPUT_FOLDER)
    assert catalog.node(output["node"])["parent_id"] == folder["node_id"]
    (row,) = _listed(empty_api, project=project["id"], include="drafts",
                     view="feed")["runs"]
    assert row["outputs"][0]["node"] == output["node"]
