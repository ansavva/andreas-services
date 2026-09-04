"""`SEND#` rows and the plan digest — what a run sends, and what makes it "the same".

A run recorded WHAT it sent (`bindings`, a `{field: [node, …]}` map) and lost
WHY. `engine/submit.py::gather` decides that an image is a start frame or a
reference, and which character group it came from, and then throws that away. A
send row keeps it, and it is to a run exactly what a `SHOT#` row is to a scene:
an ordered child, existing in the plan before anything has been submitted.

**The order is what these tests are most careful about.** A model is handed a
list and the prompt cites positions in it, so a send that came back in the wrong
place makes plate *n* the wrong plate. That is why the sort key is zero-padded
and why `put_sends` renumbers rather than merging.

The digest is the hash under the submission fingerprint — the duplicate guard —
so what it includes is the definition of "the same payload".
"""

from studio_core import config
from studio_core.services import catalog


def _items(client, run_id):
    """The raw rows. The catalog's own reader is not trusted to prove ordering."""
    response = client.query(
        TableName=config.catalog_table(),
        KeyConditionExpression="pk = :pk AND begins_with(sk, :send)",
        ExpressionAttributeValues={
            ":pk": {"S": f"RUN#{run_id}"},
            ":send": {"S": catalog.SEND_PREFIX},
        },
    )
    return response["Items"]


def _send(node, role="reference", field="input_images", **source):
    return {"field": field, "role": role, "node": node,
            "source": source or {"kind": "object"}}


# ──────────────────────────── order is the meaning ────────────────────────────


def test_sends_come_back_in_bind_order_past_ten(catalog_table):
    """**Ten is where a naive key breaks, so the test goes past it.**

    `SEND#10` sorts before `SEND#2` as a string. That is the same `-10`-before-`-2`
    failure the run outputs had when their order came from a filename, and it
    would silently hand a prompt citing "the third image" a different image.
    """
    entries = [_send(f"node-{n:02d}") for n in range(1, 13)]
    catalog.put_sends("run-order", entries)

    assert [entry["node"] for entry in catalog.sends("run-order")] == [
        f"node-{n:02d}" for n in range(1, 13)
    ]
    assert [item["sk"]["S"] for item in _items(catalog_table, "run-order")][:3] == [
        "SEND#0001", "SEND#0002", "SEND#0003"
    ]


def test_sends_carry_the_order_they_were_written_in(catalog_table):
    catalog.put_sends("run-o", [_send("node-a"), _send("node-b")])
    assert [entry["order"] for entry in catalog.sends("run-o")] == [1, 2]


# ──────────────────────────── replace, never merge ────────────────────────────


def test_a_shorter_list_deletes_the_tail(catalog_table):
    """**The one way `put_sends` differs from `put_shots`, and it is deliberate.**

    A shot carries recorded work, so a revision merges onto it. Every field of a
    send is authored, so a merge would only make position ambiguous — a dropped
    send surviving at position 3 would leave the list describing an order the
    model was never given.
    """
    catalog.put_sends("run-cut", [_send(f"node-{n}") for n in range(1, 6)])
    catalog.put_sends("run-cut", [_send("node-1"), _send("node-2")])

    assert [entry["node"] for entry in catalog.sends("run-cut")] == ["node-1", "node-2"]
    assert [item["sk"]["S"] for item in _items(catalog_table, "run-cut")] == [
        "SEND#0001", "SEND#0002"
    ]


def test_replacing_renumbers_from_one(catalog_table):
    catalog.put_sends("run-re", [_send("node-a"), _send("node-b"), _send("node-c")])
    catalog.put_sends("run-re", [_send("node-c")])

    rows = catalog.sends("run-re")
    assert [(entry["order"], entry["node"]) for entry in rows] == [(1, "node-c")]


def test_a_send_keeps_why_it_was_sent(catalog_table):
    """`source` is the half `bindings` could never hold."""
    catalog.put_sends("run-why", [
        _send("node-face", role="reference", kind="character",
              character="char-1", group="face"),
    ])
    (entry,) = catalog.sends("run-why")
    assert entry["role"] == "reference"
    assert entry["source"] == {"kind": "character", "character": "char-1",
                               "group": "face"}


def test_no_sends_is_an_empty_list_not_an_error(catalog_table):
    assert catalog.sends("run-none") == []


# ──────────────────────────────── the digest ────────────────────────────────


def test_the_digest_changes_when_the_prompt_changes():
    sends = [_send("node-a")]
    before = catalog.plan_digest({"prompt": "a rooftop"}, sends)
    after = catalog.plan_digest({"prompt": "a rooftop at dusk"}, sends)
    assert before != after


def test_the_digest_changes_when_a_param_changes():
    plan = {"prompt": "x", "params": {"aspect_ratio": "9:16"}}
    other = {"prompt": "x", "params": {"aspect_ratio": "16:9"}}
    assert catalog.plan_digest(plan, []) != catalog.plan_digest(other, [])


def test_the_digest_changes_when_an_image_changes():
    plan = {"prompt": "x"}
    assert catalog.plan_digest(plan, [_send("node-a")]) != catalog.plan_digest(
        plan, [_send("node-b")]
    )


def test_the_digest_changes_when_two_images_swap_places():
    """**Reordering is a real edit, not a cosmetic one.**

    A prompt that says "the FIRST image is an existing plate" means something
    different after a swap, so an approval taken before it must not survive it.
    """
    plan = {"prompt": "the first image is the plate"}
    forwards = catalog.plan_digest(plan, [_send("node-a"), _send("node-b")])
    backwards = catalog.plan_digest(plan, [_send("node-b"), _send("node-a")])
    assert forwards != backwards


def test_the_digest_changes_when_a_role_changes():
    """A start frame and a reference are not the same payload."""
    plan = {"prompt": "x"}
    assert catalog.plan_digest(plan, [_send("node-a", role="start")]) != (
        catalog.plan_digest(plan, [_send("node-a", role="reference")])
    )


def test_the_digest_ignores_source():
    """**Provenance is for a reader, and re-deriving it must not void approval.**

    `source` says which character group an image came from. Nothing about the
    payload changes if a later backfill describes that more accurately, so an
    approval taken before must survive it.
    """
    plan = {"prompt": "x"}
    one = catalog.plan_digest(plan, [_send("node-a", kind="object")])
    two = catalog.plan_digest(plan, [_send("node-a", kind="character",
                                           character="char-1", group="face")])
    assert one == two


def test_the_digest_survives_a_round_trip_through_dynamodb(catalog_table):
    """**The failure this exists to prevent is an approval that goes stale by
    being read back.**

    Every number comes out of the table as a `Decimal`, and `Decimal("0.5")`
    does not serialise like `0.5`. Without the normalisation, approving a run
    and then reloading it would compute a different digest for an identical
    payload, and every submit would be refused as stale.
    """
    plan = {"prompt": "x", "params": {"guidance": 0.5, "steps": 30}}
    entries = [_send("node-a", role="start", field="image")]
    catalog.put_sends("run-trip", entries)

    stored = catalog.sends("run-trip")
    assert catalog.plan_digest(plan, entries) == catalog.plan_digest(plan, stored)


def test_a_plan_of_none_hashes_and_does_not_raise():
    assert catalog.plan_digest(None, []).startswith("sha256:")
