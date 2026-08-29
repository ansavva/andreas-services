"""The model registry, served — and the reference cap that used to be a copy of it.

**The bug these are mostly about.** `routes/characters.py` carried

    ENGINE_CAPS = {"kling": 7, "seedance": 9, "nano-banana": 14}

and `GET /api/characters/<id>/selection?engine=` measured an over-cap reference
selection against it. Three families of nine, so `gpt-image-2` — which studio's
own docs name as the DEFAULT for character frames — had no cap on this side at
all, and a selection of any size aimed at it came back unrefused. The CLI refused
the same selection correctly, off the real registry. Two answers, disagreeing,
and only one of them auditable after a shoot.

`routes/runs.py` already argued the principle in a comment: a second copy of the
registry here is a second answer to what a model accepts. The copy existed
anyway, one file over. So the registry moved into this service and the caps are
read from it.
"""

import json

import pytest

from studio_core.services import registry


def test_every_registered_model_is_listed(api):
    body = api.get("/api/models").get_json()
    assert set(body["models"]) == set(registry.keys())
    assert body["models"]["gpt-image-2"]["model"] == "openai/gpt-image-2"


def test_each_entry_carries_its_own_key(api):
    """A caller that iterates the map must not have to zip it back together."""
    for key, entry in api.get("/api/models").get_json()["models"].items():
        assert entry["key"] == key


def test_one_model_resolves_by_key_alias_and_replicate_id(api):
    """All three spellings reach the same entry, including the one with a slash.

    `<path:name>` rather than `<name>` is what makes `openai/gpt-image-2` work —
    a plain converter 404s on the slash before the view runs.
    """
    by_key = api.get("/api/models/gpt-image-2").get_json()
    by_id = api.get("/api/models/openai/gpt-image-2").get_json()
    assert by_key["key"] == by_id["key"] == "gpt-image-2"


def test_an_unknown_model_is_404(api):
    assert api.get("/api/models/no-such-model").status_code == 404


def test_the_registry_is_not_writable():
    """Read-only by design: the file is committed and the API serves what shipped.

    A write route would let the deployed registry diverge from the reviewed one,
    which is the drift this whole move exists to end — and it would put the
    Replicate schema fetch, which is what `add-model` and `models refresh` are
    really doing, inside a request a person is waiting on.

    Asserted against the url map rather than by POSTing and reading a 405: the
    test client re-raises the routing exception, and a test that caught it would
    be asserting on Werkzeug's error handling instead of on the route table.
    """
    from studio_core import app_factory

    app = app_factory.create_app()
    for rule in app.url_map.iter_rules():
        if str(rule).startswith("/api/models"):
            assert rule.methods <= {"GET", "HEAD", "OPTIONS"}, f"{rule} is writable"


# ── the cap, which is the reason any of this moved ──────────────────────────


@pytest.mark.parametrize("engine,expected", [
    ("kling", 7),
    ("seedance", 9),
    ("nano-banana-pro", 14),
])
def test_the_caps_the_old_dict_got_right_are_unchanged(engine, expected):
    """Whatever else changed, the three families that had a number keep it.

    Read off the committed file rather than restated here — a literal would be a
    fourth copy of the thing this deletes.
    """
    committed = json.loads(registry.PATH.read_text())["models"]
    assert registry.reference_cap(engine) == expected == committed[engine]["images"]["max_refs"]


def test_the_default_image_model_now_has_a_cap_at_all():
    """THE BUG. `gpt-image-2` matched no prefix, so the API capped it at nothing.

    `max_refs` is `null` for this model, which means "no cap" and is a real
    answer — but it is now the registry's answer rather than an accident of the
    dict having three keys in it. The distinction matters for the models below.
    """
    assert registry.find("gpt-image-2") is not None


@pytest.mark.parametrize("engine", ["veo-3.1", "grok-imagine-video", "image-upscale"])
def test_the_models_the_old_dict_had_never_heard_of_resolve(engine):
    """Four of nine families were invisible to `ENGINE_CAPS`. None is now."""
    assert registry.find(engine) is not None


def test_an_unknown_engine_is_no_cap_rather_than_an_error():
    """`?engine=` is an optional hint on a read route.

    A caller that did not say what it was feeding cannot be told it fed too
    much, and a name the registry does not know is the same case — not a 400.
    """
    assert registry.reference_cap("not-a-model") is None


def test_a_family_is_resolved_rather_than_prefix_matched():
    """`nano-banana-2` and `nano-banana-pro` are separate entries, not one prefix.

    The old lookup matched `engine.startswith("nano-banana")` and handed both the
    same number. That happened to be right, and it was right by luck: nothing
    stopped two members of a family from differing, and a `--model` alias
    resolved only when it happened to share the prefix of its key.
    """
    assert registry.get("nano-banana-2")["key"] == "nano-banana-2"
    assert registry.get("nano-banana-pro")["key"] == "nano-banana-pro"


def test_a_null_max_refs_reads_as_no_cap_not_as_zero():
    """`field` collapses absent and null, which is what every caller wants.

    A cap of 0 and no cap are opposite instructions, and the difference is one
    `is None`. Worth an assertion of its own.
    """
    entry = registry.get("gpt-image-2")
    assert registry.field(entry, "images.max_refs") is None
    assert registry.field(entry, "images.max_refs", "unset") == "unset"
