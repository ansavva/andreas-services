"""`engine/registry` — the registry read over the wire, not off disk.

**These tests undo a fixture on purpose, and that is the point of the file.**
`conftest._registry_is_a_copy` pre-fills `registry._load` from the committed
`models.json`, so the hundred-odd tests that only want a cap or a field name do
not each need a signed-in fake. That convenience would otherwise mean nothing in
the suite ever proved the registry is fetched at all — the CLI could have gone on
reading a packaged file and every test would still pass.

So each test here replaces the primed loader with the real one and lets it reach
`fake_api`, which serves `GET /api/models` from the same committed bytes the
backend ships.
"""

from __future__ import annotations

import pytest

from studio_pipeline.adapters import api, entities
from studio_pipeline.engine import registry as REG

#: Captured at import, before conftest's autouse fixture swaps it for the
#: committed-file reader. This is the function that actually makes the call.
_real_models = entities.models


@pytest.fixture
def over_the_wire(library, monkeypatch):
    """Undo conftest's wire fake, so the fetch is a real call into `fake_api`.

    `library` brings the signed-in fake up; restoring `entities.models` puts the
    HTTP call back; clearing the memo makes this test's first read do it.
    """
    monkeypatch.setattr(entities, "models", _real_models)
    REG._load.cache_clear()
    return library


def test_the_registry_is_fetched_from_the_api(over_the_wire):
    """The whole move, in one assertion: the entries come from the service."""
    entries = REG.all()
    assert "gpt-image-2" in entries
    assert entries["gpt-image-2"]["model"] == "openai/gpt-image-2"


def test_an_alias_and_a_replicate_id_both_resolve(over_the_wire):
    """`get` follows aliases; `by_model_id` answers the `owner/name` spelling."""
    assert REG.get("gpt-image-2")["key"] == "gpt-image-2"
    assert REG.by_model_id("openai/gpt-image-2")["key"] == "gpt-image-2"


def test_an_unknown_model_names_the_registered_ones(over_the_wire):
    """The error a person acts on. A bare KeyError names nothing to try next."""
    with pytest.raises(REG.RegistryError) as raised:
        REG.get("no-such-model")
    assert "no-such-model" in str(raised.value)
    assert "gpt-image-2" in str(raised.value)


def test_one_fetch_serves_a_whole_command(over_the_wire, monkeypatch):
    """The memo, which is what makes an HTTP-backed registry usable at all.

    A single `studio run` asks the registry a dozen times. Without this each of
    `accepts_ext`, `field` and `of_kind` would be a round trip for a document
    that cannot change under a running command.
    """
    calls = {"n": 0}
    real = api.get

    def counted(route, **params):
        if route == "/api/models":
            calls["n"] += 1
        return real(route, **params)

    monkeypatch.setattr(api, "get", counted)

    REG.all()
    REG.get("gpt-image-2")
    REG.videos()
    REG.keys()

    assert calls["n"] == 1


def test_an_unreachable_api_says_what_to_do_about_it(over_the_wire, monkeypatch):
    """Reading the registry needs a session now, so the refusal has to teach.

    A bare transport error here reads as a bug in the registry rather than as
    "you are not signed in", which is what it usually means.
    """
    def refuse(*_a, **_k):
        raise api.ApiError("Unauthorized", 401)

    monkeypatch.setattr(entities, "models", refuse)
    REG._load.cache_clear()

    with pytest.raises(REG.RegistryError) as raised:
        REG.all()
    assert "studio login" in str(raised.value)
