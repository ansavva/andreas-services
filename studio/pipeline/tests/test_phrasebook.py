"""`studio phrasebook` — shared material, read by key and written by PATCH (#305).

**The phrasebook has no catalog node**, deliberately: `catalog_seed.py` records
neither it nor the pose plates, because they belong to no character and no
project. So the two directions use different routes from the rest of the
pipeline — `GET /api/asset` to read, `PATCH /api/text` to write — and the tests
here stub `api` itself rather than `store`, because which route is taken is the
thing under test.

The write is also the one place in this migration where behaviour genuinely
changed: `put_object` could create a file and `PATCH /api/text` cannot.
"""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import api, store
from studio_pipeline.domain import phrasebook


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


@pytest.fixture
def patched(monkeypatch):
    """Record every `PATCH`, or raise a scripted failure instead."""
    calls = []
    outcome = {"raises": None}

    def _patch(route, payload, **params):
        calls.append((route, payload, params))
        if outcome["raises"] is not None:
            raise outcome["raises"]
        return {"key": payload["key"], "bytes": len(payload["content"])}

    monkeypatch.setattr(api, "patch", _patch)
    return calls, outcome


# ─────────────────────────────── reading ───────────────────────────────


def test_the_phrasebook_is_read_by_key_and_never_resolved(monkeypatch):
    """**The load-bearing one.** Resolving shared material 404s in a real library.

    Driven through the real `store`, deliberately without the moto fixture: that
    shim's node ids ARE keys, so `store.read` answers correctly under it and
    404s against the API. Asserting the route is the only way to tell them
    apart. Same shape as `test_paths`' pose-plate check.
    """
    seen = {}

    def _get(route, **params):
        seen["route"], seen["params"] = route, params
        return {"url": "https://signed.example/wording.yaml"}

    monkeypatch.setattr(api, "get", _get)
    monkeypatch.setattr(store, "_fetch", lambda _url: (
        b"models:\n  <model>:\n    entries:\n"
        b"      - avoid: a phrase\n        use: another phrase\n"
    ))

    assert phrasebook.terms("<model>") == [{"avoid": "a phrase", "use": "another phrase"}]
    assert seen["route"] == "/api/asset"
    assert seen["params"]["key"] == "phrasebook/wording.yaml"


def test_a_missing_phrasebook_reads_as_an_empty_one(monkeypatch):
    """A library that has never held one is not an error — nothing to substitute."""
    def missing(_key):
        raise api.NotFound("No such object", 404)

    monkeypatch.setattr(store, "shared_read", missing)

    assert phrasebook.load() == {"version": 1, "models": {}}
    assert phrasebook.terms("kling") == []


def test_a_refused_phrasebook_is_not_an_empty_one(monkeypatch):
    """A 403 must not read as "no substitutions apply".

    The version this replaced caught every exception and grepped the message for
    `NoSuchKey`, so a refusal reported a draft as checked against a list it
    never read.
    """
    def refused(_key):
        raise api.Forbidden("not a member of this library", 403)

    monkeypatch.setattr(store, "shared_read", refused)

    with pytest.raises(api.Forbidden):
        phrasebook.terms("kling")


def test_an_empty_document_is_not_shared_between_reads(monkeypatch):
    """Every caller mutates what `load` returns, so it cannot hand out one dict."""
    monkeypatch.setattr(store, "shared_read", lambda _key: b"")

    first = phrasebook.load()
    first["models"]["<model>"] = {"entries": []}

    assert phrasebook.load()["models"] == {}


# ─────────────────────────────── writing ───────────────────────────────


def test_add_writes_the_whole_document_through_patch_text(media_bucket, patched):
    """One PATCH, carrying the file the read returned plus the new entry."""
    calls, _ = patched

    result = _run("phrasebook", "add", "--model", "kling",
                  "--avoid", "a phrase", "--use", "another phrase")

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    route, payload, _params = calls[0]
    assert route == "/api/text"
    assert payload["key"] == "phrasebook/wording.yaml"

    entries = yaml.safe_load(payload["content"])["models"]["kling"]["entries"]
    # The two already in the fixture survive: this is a whole-document replace,
    # so anything dropped from the payload is deleted from the file.
    assert [e["avoid"] for e in entries] == ["bare chest", "shirtless", "a phrase"]
    assert entries[-1]["use"] == "another phrase"


def test_add_reports_the_path_and_not_a_bucket(media_bucket, patched):
    """The CLI knows no bucket name; one it guessed would be worse than none."""
    result = _run("phrasebook", "add", "--model", "kling",
                  "--avoid", "a phrase", "--use", "another phrase")

    assert "recorded -> phrasebook/wording.yaml" in result.output
    assert "s3://" not in result.output


def test_add_to_a_library_with_no_phrasebook_says_what_that_takes(media_bucket, patched):
    """**The behaviour change.** `put_object` could create the file; PATCH cannot.

    The refusal has to name the fix, because the CLI has no way to perform it —
    the fix is `dev-setup.sh`, which copies the repo's seed copy in when the key
    is absent (#425).
    """
    _calls, outcome = patched
    outcome["raises"] = api.NotFound("phrasebook/wording.yaml", 404)

    result = _run("phrasebook", "add", "--model", "kling",
                  "--avoid", "a phrase", "--use", "another phrase")

    assert result.exit_code == 1
    assert "cannot create one" in result.output
    assert "phrasebook/wording.yaml" in result.output


def test_reading_commands_write_nothing(media_bucket, patched):
    """`show`, `terms`, `check` and `models` are reads. A PATCH from one is a bug."""
    calls, _ = patched

    for argv in (["phrasebook", "models"],
                 ["phrasebook", "show"],
                 ["phrasebook", "terms", "--model", "kling"],
                 ["phrasebook", "check", "--model", "kling", "--text", "nothing here"]):
        assert _run(*argv).exit_code == 0, argv

    assert calls == []
