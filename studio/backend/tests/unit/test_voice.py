"""Elements and voice binding — Kling 3.0 Omni's half that Replicate's proxy hides.

**What is new here, and why it needed new machinery.** Every model in this
registry until now took a FLAT list of reference images: `{field: [url, …]}`,
which `bindings_of` produces and `dispatch` presigns in place. Kling on fal
takes a list of SUBJECTS instead — `elements`, each one `{frontal_image_url,
reference_image_urls, video_url, voice_id}`, cited in the prompt as
`@Element1` — and a voice is bound to a subject rather than to the run, by an
id minted from a 5–30 second sample.

Two things follow, and both are what these tests hold up:

1. **The grouping is derived, not authored.** `catalog.source_of` already says
   which character a bound image came from, because that is how a run page
   describes its inputs. An element is a character. So the elements are the
   sends grouped by that same answer — there is no second place to say which
   pictures belong to whom, and therefore no way for the two to disagree.
2. **A voice id is minted once and remembered.** The whole point of binding a
   voice is that the character sounds the same in the next clip; a fresh id per
   run would be a fresh voice per run, which is the feature backwards.

Nothing here bills. `STUDIO_FAL_MODE=fake` answers `create_voice` locally with
a deterministic id, and the socket guard sits behind it.
"""

import pytest

from studio_core.errors import ValidationError
from studio_core.services import catalog, generate, registry, schema

V3 = "fal-kling-v3-i2v"
O3 = "fal-kling-o3-r2v"


def _entry(key=V3):
    return registry.get(key)


def _send(node, role="reference", field="elements", **source):
    return {"field": field, "role": role, "node": node,
            "source": source or {"kind": "object"}}


# ── grouping: an element is a subject ───────────────────────────────────────


def test_each_character_becomes_one_element_in_bind_order():
    """`@Element1` is positional, so bind order is element order."""
    block = registry.elements(_entry())
    groups = generate.element_groups(block, [
        _send("node-a1", kind="character", character="char-a"),
        _send("node-a2", kind="character", character="char-a"),
        _send("node-b1", kind="character", character="char-b"),
    ])

    assert [group["subject"] for group in groups] == ["char-a", "char-b"]
    assert groups[0]["frontal"] == "node-a1"
    assert groups[0]["refs"] == ["node-a2"]
    assert groups[1]["frontal"] == "node-b1"


def test_a_location_is_a_subject_too():
    """A set is a thing the prompt points at, the same way a person is."""
    block = registry.elements(_entry())
    groups = generate.element_groups(block, [
        _send("node-1", kind="character", character="char-a"),
        _send("node-2", kind="location", location="loc-1"),
    ])
    assert [group["subject"] for group in groups] == ["char-a", "loc-1"]


def test_files_belonging_to_nobody_share_one_element():
    """**One loose bucket, not one element per picture.**

    Three stills dropped in from a folder are three views of one thing far
    more often than they are three subjects, and an element per file would
    burn the model's cap of four on a single character.
    """
    block = registry.elements(_entry())
    groups = generate.element_groups(block, [
        _send("node-1"), _send("node-2"), _send("node-3"),
    ])
    assert len(groups) == 1
    assert groups[0]["frontal"] == "node-1"
    assert groups[0]["refs"] == ["node-2", "node-3"]


def test_an_explicit_frontal_wins_and_displaces_rather_than_drops():
    """The first image is the main view only because nothing said otherwise."""
    block = registry.elements(_entry())
    groups = generate.element_groups(block, [
        _send("node-1", kind="character", character="char-a"),
        _send("node-2", role="frontal", kind="character", character="char-a"),
    ])
    assert groups[0]["frontal"] == "node-2"
    assert groups[0]["refs"] == ["node-1"]


def test_a_voice_lands_on_its_own_characters_element():
    """The binding the whole feature is: this character, in this voice."""
    block = registry.elements(_entry())
    groups = generate.element_groups(block, [
        _send("node-a1", kind="character", character="char-a"),
        _send("node-b1", kind="character", character="char-b"),
        _send("node-bv", role="voice", kind="character", character="char-b"),
    ])
    assert groups[0]["voice"] is None
    assert groups[1]["voice"] == "node-bv"


def test_a_send_on_another_field_is_not_an_element():
    """A start frame is the run's, not a subject's."""
    block = registry.elements(_entry())
    groups = generate.element_groups(block, [
        _send("node-start", role="start", field="start_image_url"),
        _send("node-a", kind="character", character="char-a"),
    ])
    assert len(groups) == 1 and groups[0]["frontal"] == "node-a"


# ── what the registry says, and what has to stay true of it ─────────────────


def test_both_kling_entries_are_registered_beside_the_replicate_one():
    """**The Replicate entry stays.** Two providers host this model family with
    different inputs and different bills, and the point of the provider prefix
    is that a person picking one can see which."""
    assert registry.get("replicate-kling")["model"] == "kwaivgi/kling-v3-omni-video"
    assert registry.get(V3)["model"] == "fal/fal-ai/kling-video/v3/pro/image-to-video"
    assert registry.get(O3)["model"] == "fal/fal-ai/kling-video/o3/pro/reference-to-video"


def test_the_replicate_entry_has_no_voice_input_because_the_proxy_exposes_none():
    """Not an omission. `kwaivgi/kling-v3-omni-video` takes `generate_audio`
    and no voice field at all — the audio is whatever the model invents."""
    assert registry.voice_field(registry.get("replicate-kling")) is None
    assert registry.elements(registry.get("replicate-kling")) is None


def test_a_voice_binds_to_the_elements_field_rather_than_one_of_its_own():
    """There is no top-level `voice_id` input to name: the id sits INSIDE the
    element, beside that subject's pictures. That is what makes the voice the
    character's rather than the run's."""
    entry = _entry()
    assert registry.voice_field(entry) == registry.elements(entry)["field"]
    assert registry.elements(entry)["voice"] == "voice_id"


def test_the_old_bare_names_still_resolve():
    """Every key gained a provider and every old key became an alias, which is
    what keeps a year of drafts, runs and skill pages working."""
    for alias, key in (("kling", "replicate-kling"),
                       ("gpt-image-2", "replicate-gpt-image-2"),
                       ("wan-3.0-i2v", "fal-wan-3.0-i2v"),
                       ("wan-3.0-openrouter", "openrouter-wan-3.0")):
        assert registry.get(alias)["key"] == key


# ── the preflight, which runs while the run is still a draft ────────────────


def test_a_voice_on_a_model_that_takes_none_is_refused_by_name():
    entry = registry.get("replicate-kling")
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(entry, [_send("node-v", role="voice")], {})
    assert "no voice input" in str(raised.value)
    assert V3 in str(raised.value)


def test_a_voice_with_the_audio_turned_off_is_refused():
    """**The one failure the provider would NOT report.** `generate_audio:
    false` renders a silent clip and the voice tier is billed anyway — it does
    not fail, it wastes the spend quietly."""
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(
            _entry(),
            [_send("node-a", kind="character", character="char-a"),
             _send("node-v", role="voice", kind="character", character="char-a")],
            {"generate_audio": False})
    assert "silent clip billed at the voice rate" in str(raised.value)


def test_more_subjects_than_the_model_takes_is_refused():
    sends = [_send(f"node-{n}", kind="character", character=f"char-{n}")
             for n in range(5)]
    with pytest.raises(schema.SchemaError) as raised:
        generate._check_elements(_entry(), sends, {})
    assert "at most 4 elements" in str(raised.value)


def test_more_views_of_one_subject_than_an_element_holds_is_refused():
    sends = [_send(f"node-{n}", kind="character", character="char-a")
             for n in range(5)]
    with pytest.raises(schema.SchemaError) as raised:
        generate._check_elements(_entry(), sends, {})
    assert "@Element1 carries 5 images" in str(raised.value)


def test_a_voice_with_nobody_to_speak_it_is_refused():
    """A sample bound with none of that character's pictures is an element
    that is a voice and nothing else — the provider takes it and there is
    nobody on screen it belongs to."""
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(
            _entry(), [_send("node-v", role="voice", kind="character", character="char-a")],
            {"generate_audio": True})
    assert "nobody to speak it" in str(raised.value)


def test_two_subjects_with_four_views_each_is_allowed():
    """The cap that used to be counted wrong. `max_refs` is FOUR on these
    entries and it counts elements, so reading it as four images would refuse
    a perfectly ordinary two-hander."""
    sends = [_send(f"node-{c}{n}", kind="character", character=f"char-{c}")
             for c in "ab" for n in range(4)]
    generate._check_elements(_entry(), sends, {"generate_audio": True})


# ── the payload, presigned, with the voice registered ───────────────────────


def _uploaded(api, parent_id, name, content_type="image/webp", body=b"bytes"):
    node = api.post("/api/nodes", json={"parent": parent_id, "name": name,
                                        "kind": "file"}).get_json()
    record = catalog.node(node["id"])
    return catalog.set_blob(node["id"], record["blob_key"], size=len(body),
                            content_type=content_type)


def test_the_elements_payload_is_built_with_presigned_urls_and_a_minted_voice(
        empty_api, media_bucket):
    project = empty_api.post("/api/projects", json={"name": "two-hander"}).get_json()
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    face = _uploaded(empty_api, root, "face.png", "image/png")
    side = _uploaded(empty_api, root, "side.png", "image/png")
    sample = _uploaded(empty_api, root, "take.mp3", "audio/mpeg")

    entry = _entry()
    built = generate.elements_payload(entry, registry.elements(entry), [
        _send(face["node_id"], kind="character", character="char-a"),
        _send(side["node_id"], kind="character", character="char-a"),
        _send(sample["node_id"], role="voice", kind="character", character="char-a"),
    ])

    assert len(built) == 1
    element = built[0]
    assert "X-Amz-Signature" in element["frontal_image_url"]
    assert len(element["reference_image_urls"]) == 1
    assert element["voice_id"].startswith("fake-voice-")


def test_a_voice_is_minted_once_and_reused(empty_api, media_bucket, monkeypatch):
    """**Cached because the identity is the point**, not because the call is
    slow. A second id would be a second voice for the same character."""
    project = empty_api.post("/api/projects", json={"name": "reuse"}).get_json()
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    sample = _uploaded(empty_api, root, "take.wav", "audio/wav")
    entry = _entry()

    first = generate.voice_id_for(entry, sample["node_id"])

    calls = []
    from studio_core.clients import fal
    monkeypatch.setattr(fal, "create_voice",
                        lambda model, url: calls.append(url) or "a-different-id")
    second = generate.voice_id_for(entry, sample["node_id"])

    assert second == first
    assert calls == []
    record = catalog.node(sample["node_id"])
    assert catalog.voice_id(record, registry.voice_endpoint(entry)) == first


def test_the_voice_id_is_keyed_by_the_endpoint_that_issued_it(empty_api, media_bucket):
    """A `voice_id` from Kling means nothing anywhere else, so the cache is a
    map rather than one slot."""
    project = empty_api.post("/api/projects", json={"name": "keyed"}).get_json()
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    sample = _uploaded(empty_api, root, "take.wav", "audio/wav")

    catalog.set_voice_id(sample["node_id"], "somewhere/else", "other-id")
    minted = generate.voice_id_for(_entry(), sample["node_id"])

    record = catalog.node(sample["node_id"])
    assert record["voices"]["somewhere/else"] == "other-id"
    assert record["voices"][registry.voice_endpoint(_entry())] == minted


def test_submitting_sends_elements_rather_than_a_flat_list(empty_api, media_bucket):
    """End to end through the route that spends: the draft binds pictures and a
    sample, and what goes out is one subject carrying both."""
    project = empty_api.post("/api/projects", json={"name": "kling-fal"}).get_json()
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    start = _uploaded(empty_api, root, "open.png", "image/png")
    face = _uploaded(empty_api, root, "face.png", "image/png")
    sample = _uploaded(empty_api, root, "take.mp3", "audio/mpeg")

    resp = empty_api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": V3,
        "model": registry.get(V3)["model"],
        "plan": {"version": 1, "origin": "authored",
                 "prompt": "@Element1 looks up and says hello",
                 "params": {"duration": "5", "generate_audio": True}},
        "sends": [
            {"field": "start_image_url", "role": "start", "node": start["node_id"]},
            {"field": "elements", "role": "reference", "node": face["node_id"]},
            {"field": "elements", "role": "voice", "node": sample["node_id"]},
        ],
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    run = resp.get_json()

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] in ("pending", "running")
    assert record["provider"] == registry.FAL
