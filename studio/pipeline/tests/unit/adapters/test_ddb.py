"""`adapters/ddb.py`'s marshalling, both directions.

The adapter had no suite of its own, which is how `from_item` shipped
converting only the top level: every row it read was flat until entity rows
arrived, and a node row's only number is `size`.
"""
from __future__ import annotations

import decimal
import json

from studio_pipeline.adapters import ddb as ddbc


def test_to_item_drops_nones_rather_than_writing_null():
    """A folder has no `blob_key`, and `attribute_not_exists` tests absence.

    Writing `{"NULL": true}` would make the attribute exist, which quietly
    defeats every uniqueness condition in the loader and the API alike.
    """
    item = ddbc.to_item({"pk": "NODE#1", "size": 12, "blob_key": None})
    assert item == {"pk": {"S": "NODE#1"}, "size": {"N": "12"}}


def test_from_item_converts_numbers_nested_at_any_depth():
    """**The bug: this used to convert the top level only.**

    DynamoDB deserialises every N to `Decimal`, which compares equal to an int,
    formats as `Decimal('2')` in a report, and is refused outright by
    `json.dumps`. A node row survived a shallow conversion because its numbers
    are top-level. An entity row does not: a character carries a nested
    `profile` and a project carries `counts`, so `dev-seed publish` read a
    `schema_version` two maps down and died writing the fixture.
    """
    item = {
        "pk": {"S": "CHAR#1"},
        "rev": {"N": "3"},
        "counts": {"M": {"runs": {"N": "1"}, "scenes": {"N": "0"}}},
        "profile": {"M": {
            "schema_version": {"N": "2"},
            "wardrobe": {"M": {"tops": {"L": [
                {"M": {"item": {"S": "<garment>"}, "weight": {"N": "1.5"}}}]}}},
        }},
        "default_set": {"L": [{"N": "7"}, {"S": "node-a"}]},
    }
    got = ddbc.from_item(item)

    assert got == {
        "pk": "CHAR#1", "rev": 3,
        "counts": {"runs": 1, "scenes": 0},
        "profile": {"schema_version": 2,
                    "wardrobe": {"tops": [{"item": "<garment>", "weight": 1.5}]}},
        "default_set": [7, "node-a"],
    }
    # The property that actually broke, asserted as itself: the document this
    # feeds is written with `json.dumps`.
    assert json.dumps(got)
    assert not _any_decimal(got)


def test_from_item_turns_a_set_into_a_sorted_list():
    """`json.dumps` refuses a `set` for the same reason it refuses a `Decimal`.

    Sorted rather than arbitrary so that a journal file diffs against itself.
    """
    got = ddbc.from_item({"tags": {"SS": ["face", "body"]},
                          "sizes": {"NS": ["3", "1"]}})
    assert got == {"tags": ["body", "face"], "sizes": [1, 3]}
    assert json.dumps(got)


def _any_decimal(value) -> bool:
    if isinstance(value, decimal.Decimal):
        return True
    if isinstance(value, dict):
        return any(_any_decimal(v) for v in value.values())
    if isinstance(value, list):
        return any(_any_decimal(v) for v in value)
    return False
