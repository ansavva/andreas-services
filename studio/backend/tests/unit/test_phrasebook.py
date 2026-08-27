"""The phrasebook: a per-model list of avoid/use pairs, and why it stopped being a file.

It was `phrasebook/wording.yaml` — one document at the top of the bucket
belonging to no character and no project, with no catalog node. That is not a
small detail: it was the **sole reason** `GET /api/asset?key=` still took a raw
S3 key, and therefore the sole reason `keys.clean_key` and the traversal rules
under it survived #312. Making it rows retired all of it.

`LIB#<lib>` / `TERM#<model>#<avoid>`. The model comes first in the sort key even
though the *pair* is what makes a term unique, because reading one model's list
is the common request and `begins_with` is cheaper than a filter.
"""

from studio_core import config
from tests.conftest import CATALOG_LIBRARY


def _item(client, pk, sk):
    response = client.get_item(
        TableName=config.catalog_table(), Key={"pk": {"S": pk}, "sk": {"S": sk}}
    )
    return response.get("Item")


MODEL = "google/nano-banana-pro"


def test_a_first_term_needs_no_document_to_exist_first(empty_api, catalog_table):
    """**`phrasebook add` can no longer fail on a library that has never held one.**

    It used to read a YAML document, edit it and write it back, so the first add
    in a fresh library hit a 404 on a file nobody had created. There is no
    document — a first term is just a first row.
    """
    resp = empty_api.post(
        "/api/phrasebook", json={"model": MODEL, "avoid": "sultry", "use": "composed"}
    )

    assert resp.status_code == 201
    assert _item(
        catalog_table, f"LIB#{CATALOG_LIBRARY}", f"TERM#{MODEL}#sultry"
    )["use"]["S"] == "composed"


def test_a_duplicate_pair_is_409_rather_than_an_overwrite(empty_api):
    """The pair *is* the key, so "already there" is a condition failure.

    Never a read somebody raced — which is the same argument every claim in this
    service makes, applied to the smallest row in it.
    """
    body = {"model": MODEL, "avoid": "sultry", "use": "composed"}
    empty_api.post("/api/phrasebook", json=body)

    resp = empty_api.post("/api/phrasebook", json={**body, "use": "different"})

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "conflict"


def test_reading_one_models_list_is_a_begins_with_and_not_a_filter(empty_api):
    """Which is why the model comes first in the sort key.

    A term is unique on the *pair*, so a key of `TERM#<avoid>#<model>` would be
    equally correct and would make the common read a scan of every model's list.
    """
    empty_api.post(
        "/api/phrasebook", json={"model": MODEL, "avoid": "sultry", "use": "composed"}
    )
    empty_api.post(
        "/api/phrasebook", json={"model": "kling/v2", "avoid": "cinematic", "use": "plain"}
    )

    body = empty_api.get(f"/api/phrasebook?model={MODEL}").get_json()

    assert [term["avoid"] for term in body["terms"]] == ["sultry"]
    assert len(empty_api.get("/api/phrasebook").get_json()["terms"]) == 2


def test_a_term_is_deleted_by_a_model_id_that_contains_a_slash(empty_api, catalog_table):
    """`<path:model>` because a model id is `google/nano-banana-pro`.

    Werkzeug matches the converter greedily and leaves the final segment to
    `avoid`, so the split falls on the last slash — which is where the word
    begins. Worth pinning: the obvious `<string:model>` would 404 on every real
    model id this service has.
    """
    empty_api.post(
        "/api/phrasebook", json={"model": MODEL, "avoid": "sultry", "use": "composed"}
    )

    resp = empty_api.delete(f"/api/phrasebook/{MODEL}/sultry")

    assert resp.status_code == 200
    assert resp.get_json() == {"model": MODEL, "avoid": "sultry", "deleted": True}
    assert _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", f"TERM#{MODEL}#sultry") is None


def test_a_hash_in_a_model_or_a_word_is_refused(empty_api):
    """`#` is the key separator, so a term holding one is ambiguous.

    Refused rather than escaped: escaping would make the key unreadable in the
    console for a character no word needs, and the ambiguity it prevents is a
    term that reads as a different model's.
    """
    assert empty_api.post(
        "/api/phrasebook", json={"model": "a#b", "avoid": "x", "use": "y"}
    ).status_code == 400
    assert empty_api.post(
        "/api/phrasebook", json={"model": MODEL, "avoid": "a#b", "use": "y"}
    ).status_code == 400


def test_replicate_is_stored_and_read_back(empty_api, catalog_table):
    """It was accepted by the route and dropped before the write.

    `phrasebook show` reads `replicate` to head each model's section and
    `phrasebook models` prints it in a column, so both showed nothing for the
    whole life of the migration. Not caught because the pipeline's fake API
    stored the field the real one discarded — which is why this test is here
    and not beside the CLI.
    """
    empty_api.post("/api/phrasebook", json={
        "model": MODEL, "avoid": "sultry", "use": "composed",
        "replicate": "google/nano-banana-pro"})

    item = _item(catalog_table, f"LIB#{CATALOG_LIBRARY}", f"TERM#{MODEL}#sultry")

    assert item["replicate"]["S"] == "google/nano-banana-pro"
    terms = empty_api.get(f"/api/phrasebook?model={MODEL}").get_json()["terms"]
    assert terms[0]["replicate"] == "google/nano-banana-pro"


def test_a_term_carries_created_and_not_the_documents_added(empty_api):
    """The row's stamp is `created`, like every other row in this table.

    Pinned because the CLI's `show` asked for `added` — the YAML document's
    field name — and so printed no date at all against a real library.
    """
    empty_api.post(
        "/api/phrasebook", json={"model": MODEL, "avoid": "sultry", "use": "composed"}
    )

    term = empty_api.get(f"/api/phrasebook?model={MODEL}").get_json()["terms"][0]

    assert "added" not in term
    assert term["created"]


def test_every_field_but_the_note_is_required(empty_api):
    for missing in ("model", "avoid", "use"):
        body = {"model": MODEL, "avoid": "sultry", "use": "composed"}
        del body[missing]
        assert empty_api.post("/api/phrasebook", json=body).status_code == 400, missing
