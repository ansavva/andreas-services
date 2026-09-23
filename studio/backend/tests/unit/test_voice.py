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
3. **A voice binds only to an element carrying a video.** fal's page for
   `fal-ai/kling-video/v3/pro/image-to-video`, under Custom Elements and Known
   Limitations: "Voice binding is only supported for video elements, not image
   elements." A character's pictures alone make an image element, so a voice
   beside them is refused while the run is a draft; and since "a request can
   only have one element with a video", one voice at most. Without a bound
   voice, `generate_audio: true` has Kling invent one — the path for now.

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


def _named(monkeypatch, names):
    """`catalog.node` answering file names, for the extension check."""
    monkeypatch.setattr(catalog, "node",
                        lambda node_id: {"id": node_id, "name": names.get(node_id, "x.bin")})


def _speaking(voice="node-v", clip="node-c"):
    """A subject bound the one way fal takes a voice: pictures, a clip, a voice."""
    return [_send("node-a", kind="character", character="char-a"),
            _send(clip, role="clip", kind="character", character="char-a"),
            _send(voice, role="voice", kind="character", character="char-a")]


def test_a_voice_with_the_audio_turned_off_is_refused(monkeypatch):
    """**The one failure the provider would NOT report.** `generate_audio:
    false` renders a silent clip and the voice tier is billed anyway — it does
    not fail, it wastes the spend quietly."""
    _named(monkeypatch, {"node-v": "take.mp3"})
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(_entry(), _speaking(), {"generate_audio": False})
    assert "silent clip billed at the voice rate" in str(raised.value)


@pytest.mark.parametrize("key", [V3, O3])
def test_a_voice_on_an_image_element_is_refused_in_fals_own_words(key):
    """**The rule that was missing.** A character's pictures alone make an
    IMAGE element, and fal refuses a voice on one — after `pending`, as a
    provider error. Refused here instead, while the run is still a draft, with
    fal's sentence and the two ways out."""
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(
            _entry(key),
            [_send("node-a", kind="character", character="char-a"),
             _send("node-v", role="voice", kind="character", character="char-a")],
            {"generate_audio": True})
    message = str(raised.value)
    assert ("Voice binding is only supported for video elements, "
            "not image elements.") in message
    assert "@Element1" in message
    assert "Kling invents the voice" in message
    assert "short video of that subject" in message


def test_a_voice_on_an_element_with_a_clip_passes(monkeypatch):
    """The one shape fal takes a voice in: the element carries a `video_url`."""
    _named(monkeypatch, {"node-v": "take.mp3"})
    generate._check_elements(_entry(), _speaking(), {"generate_audio": True})


def test_the_voice_on_another_subjects_element_does_not_borrow_its_clip():
    """The clip has to be on the SAME element. A voice grouped under one
    character and a clip under another is still a voice on an image element."""
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(
            _entry(),
            [_send("node-a", kind="character", character="char-a"),
             _send("node-c", role="clip", kind="character", character="char-a"),
             _send("node-b", kind="character", character="char-b"),
             _send("node-v", role="voice", kind="character", character="char-b")],
            {"generate_audio": True})
    assert "@Element2" in str(raised.value)
    assert "only supported for video elements" in str(raised.value)


def test_two_clips_are_refused():
    """"A request can only have one element with a video" — which is also why
    a request carries one voice at most."""
    with pytest.raises(schema.SchemaError) as raised:
        generate._check_elements(
            _entry(),
            [_send("node-a", kind="character", character="char-a"),
             _send("node-ac", role="clip", kind="character", character="char-a"),
             _send("node-b", kind="character", character="char-b"),
             _send("node-bc", role="clip", kind="character", character="char-b")],
            {"generate_audio": True})
    assert "ONE element with a video" in str(raised.value)


@pytest.mark.parametrize("key", [V3, O3])
def test_the_voice_formats_are_the_ones_fal_lists(key):
    """fal's create-voice: "Supports .mp3/.wav audio or .mp4/.mov video." The
    registry once listed `.m4a` and `.flac` too, which fal does not take."""
    assert registry.voice_accepts_ext(_entry(key)) == {".mp3", ".wav", ".mp4", ".mov"}


def test_a_sample_fal_will_not_read_is_refused(monkeypatch):
    _named(monkeypatch, {"node-v": "take.m4a"})
    with pytest.raises(schema.SchemaError) as raised:
        generate._check_elements(_entry(), _speaking(), {"generate_audio": True})
    assert "clones a voice from" in str(raised.value)


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
    """A sample bound with neither a picture nor a clip of its subject is an
    element that is a voice and nothing else — there is nobody on screen it
    belongs to, and no video for fal to bind it to."""
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(
            _entry(), [_send("node-v", role="voice", kind="character", character="char-a")],
            {"generate_audio": True})
    assert "nobody to speak it" in str(raised.value)
    assert "Kling invents the voice" in str(raised.value)


# ── the floor: an image element is two pictures, not one ────────────────────
#
# fal's server refused a lone frontal on 2026-09-23 (a 422 on `body.elements.2`,
# no charge), and its OpenAPI document does not say so:
#
#     Either frontal_image_url and reference_image_urls or video_url must be
#     provided.


@pytest.mark.parametrize("key", [V3, O3])
def test_the_registry_puts_a_floor_of_two_under_an_element(key):
    assert registry.elements(_entry(key))["min_images_each"] == 2


@pytest.mark.parametrize("key", [V3, O3])
def test_a_single_image_element_is_refused_in_fals_own_words(key):
    with pytest.raises(ValidationError) as raised:
        generate._check_elements(
            _entry(key),
            [_send("node-a1", kind="character", character="char-a"),
             _send("node-a2", kind="character", character="char-a"),
             _send("node-room", kind="location", location="loc-1")],
            {"generate_audio": True})
    message = str(raised.value)
    assert ("Either frontal_image_url and reference_image_urls or video_url "
            "must be provided.") in message
    assert "@Element2 carries 1 image(s)" in message
    assert "second view" in message
    assert "location's folder" in message


def test_a_two_image_element_passes():
    generate._check_elements(
        _entry(),
        [_send("node-a1", kind="character", character="char-a"),
         _send("node-a2", kind="character", character="char-a")],
        {"generate_audio": True})


def test_a_clip_only_element_passes():
    """A video element carries the subject without any picture."""
    generate._check_elements(
        _entry(), [_send("node-c", role="clip", kind="character", character="char-a")],
        {"generate_audio": True})


def test_one_picture_and_a_clip_passes():
    generate._check_elements(
        _entry(),
        [_send("node-a", kind="character", character="char-a"),
         _send("node-c", role="clip", kind="character", character="char-a")],
        {"generate_audio": True})


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
    clip = _uploaded(empty_api, root, "move.mp4", "video/mp4")
    sample = _uploaded(empty_api, root, "take.mp3", "audio/mpeg")

    entry = _entry()
    built = generate.elements_payload(entry, registry.elements(entry), [
        _send(face["node_id"], kind="character", character="char-a"),
        _send(side["node_id"], kind="character", character="char-a"),
        _send(clip["node_id"], role="clip", kind="character", character="char-a"),
        _send(sample["node_id"], role="voice", kind="character", character="char-a"),
    ])

    assert len(built) == 1
    element = built[0]
    assert "X-Amz-Signature" in element["frontal_image_url"]
    assert len(element["reference_image_urls"]) == 1
    assert "X-Amz-Signature" in element["video_url"]
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


def _kling_draft(api, *, clip: bool, cached_voice: str | None = None):
    """A fal Kling draft binding a start frame, a picture, a voice and
    (optionally) a clip. Returns the run and the node ids by name."""
    project = api.post("/api/projects", json={"name": "kling-fal"}).get_json()
    root = api.get(f"/api/projects/{project['id']}").get_json()["root"]
    nodes = {
        "start": _uploaded(api, root, "open.png", "image/png")["node_id"],
        "face": _uploaded(api, root, "face.png", "image/png")["node_id"],
        "voice": _uploaded(api, root, "take.mp3", "audio/mpeg")["node_id"],
    }
    sends = [
        {"field": "start_image_url", "role": "start", "node": nodes["start"]},
        {"field": "elements", "role": "reference", "node": nodes["face"]},
    ]
    if clip:
        nodes["clip"] = _uploaded(api, root, "move.mp4", "video/mp4")["node_id"]
        sends.append({"field": "elements", "role": "clip", "node": nodes["clip"]})
    sends.append({"field": "elements", "role": "voice", "node": nodes["voice"]})
    if cached_voice:
        catalog.set_voice_id(nodes["voice"], registry.voice_endpoint(_entry()),
                             cached_voice)
    resp = api.post("/api/runs", json={
        "project": project["id"], "kind": "video", "engine": V3,
        "model": registry.get(V3)["model"],
        "plan": {"version": 1, "origin": "authored",
                 "prompt": "@Element1 looks up and says hello",
                 "params": {"duration": "5", "generate_audio": True}},
        "sends": sends,
    })
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json(), nodes


def test_submitting_sends_elements_rather_than_a_flat_list(empty_api, media_bucket):
    """End to end through the route that spends: the draft binds a picture, a
    clip and a sample, and what goes out is one subject carrying all three."""
    run, _ = _kling_draft(empty_api, clip=True)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    record = catalog.entity(catalog.ENTITY_RUN, run["id"])
    assert record["status"] in ("pending", "running")
    assert record["provider"] == registry.FAL


def test_submitting_a_voice_on_an_image_element_leaves_the_draft(empty_api, media_bucket):
    """The refusal happens before `pending`, so nothing is sent, nothing is
    billed, and the run is still the editable draft it was."""
    run, _ = _kling_draft(empty_api, clip=False)

    resp = empty_api.post(f"/api/runs/{run['id']}/submit")
    assert 400 <= resp.status_code < 500, resp.get_data(as_text=True)
    assert "only supported for video elements" in resp.get_data(as_text=True)
    assert catalog.entity(catalog.ENTITY_RUN, run["id"])["status"] == "draft"


# ── the preview a person reads before sending (hard rule #2) ────────────────


def test_the_preview_shows_elements_in_the_shape_they_go_out_in(empty_api, media_bucket):
    """**The preview used to show `elements` as the flat list it is stored
    as** — node ids, voice sample among them — while the wire carries one
    object per subject. Now it is the same assembly as `dispatch`, with node
    ids where URLs will be and a placeholder where a voice id will be minted."""
    run, nodes = _kling_draft(empty_api, clip=True)

    resp = empty_api.get(f"/api/runs/{run['id']}/payload")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    request = resp.get_json()["request"]

    assert request["elements"] == [{
        "frontal_image_url": nodes["face"],
        "video_url": nodes["clip"],
        "voice_id": generate.VOICE_PENDING,
    }]
    assert request["start_image_url"] == nodes["start"]
    assert request["prompt"] == "@Element1 looks up and says hello"
    text = resp.get_data(as_text=True)
    assert "X-Amz" not in text and "https://" not in text


def test_the_preview_shows_a_voice_id_already_cached(empty_api, media_bucket, monkeypatch):
    """A voice registered by an earlier run is the id that WILL go out, so it
    is shown — read off the node, never minted: reading a page must not call
    the provider."""
    from studio_core.clients import fal
    monkeypatch.setattr(fal, "create_voice",
                        lambda *a, **k: pytest.fail("the preview registered a voice"))
    run, _ = _kling_draft(empty_api, clip=True, cached_voice="voice-from-before")

    request = empty_api.get(f"/api/runs/{run['id']}/payload").get_json()["request"]

    assert request["elements"][0]["voice_id"] == "voice-from-before"


def test_replacing_the_bytes_drops_the_cached_voice(empty_api, media_bucket):
    """**A cached id names the recording it came from.**

    Re-uploading over a node is the one way other bytes get behind the same
    row, and a voice id that survived it would bind a character to a sample
    the library no longer holds — silently, in every later clip.
    """
    project = empty_api.post("/api/projects", json={"name": "recut"}).get_json()
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    sample = _uploaded(empty_api, root, "take.wav", "audio/wav")
    catalog.set_blob(sample["node_id"], sample["blob_key"], checksum="first")
    minted = generate.voice_id_for(_entry(), sample["node_id"])
    assert catalog.voice_id(catalog.node(sample["node_id"]),
                            registry.voice_endpoint(_entry())) == minted

    catalog.set_blob(sample["node_id"], sample["blob_key"], checksum="second")

    assert "voices" not in catalog.node(sample["node_id"])


def test_the_same_bytes_keep_their_voice(empty_api, media_bucket):
    """A confirm that re-states the same checksum is not a new recording."""
    project = empty_api.post("/api/projects", json={"name": "same"}).get_json()
    root = empty_api.get(f"/api/projects/{project['id']}").get_json()["root"]
    sample = _uploaded(empty_api, root, "take.wav", "audio/wav")
    catalog.set_blob(sample["node_id"], sample["blob_key"], checksum="one")
    minted = generate.voice_id_for(_entry(), sample["node_id"])

    catalog.set_blob(sample["node_id"], sample["blob_key"], checksum="one")

    assert catalog.voice_id(catalog.node(sample["node_id"]),
                            registry.voice_endpoint(_entry())) == minted
