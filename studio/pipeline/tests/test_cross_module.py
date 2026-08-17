"""The calls one part of the pipeline makes into another.

These three used to shell out through `uv run <script> --json` and parse
stdout, because no two scripts shared an interpreter. They are ordinary
function calls now, and these tests pin the behaviour that survived the change:
the same keys, in the same order, with the same refusals.
"""

import pytest

from studio_pipeline.domain import phrasebook, projects
from studio_pipeline.engine import refs


# --------------------------------------------------------------------------
# refs -> character
# --------------------------------------------------------------------------
def test_reference_selection_resolves(media_bucket):
    """The whole reference set, in index order."""
    keys = refs.character_ref_keys("subject-a")
    assert keys == [
        "characters/subject-a/reference/face/subject-a_1.webp",
        "characters/subject-a/reference/face/subject-a_2.webp",
        "characters/subject-a/reference/body/subject-a_1.webp",
    ]


def test_reference_selection_by_tag(media_bucket):
    """`--pick-tag face` is a selection over the described index."""
    keys = refs.character_ref_keys("subject-a", tags=["face"])
    assert keys == [
        "characters/subject-a/reference/face/subject-a_1.webp",
        "characters/subject-a/reference/face/subject-a_2.webp",
    ]


def test_reference_selection_by_slot_uses_position_not_filename(media_bucket):
    """Slot N is position N in the resolved list.

    Filename numbers are only unique within a subfolder — `face/subject-a_1`
    and `body/subject-a_1` both exist — so slots must index the selection.
    """
    keys = refs.character_ref_keys("subject-a", slots=[3])
    assert keys == ["characters/subject-a/reference/body/subject-a_1.webp"]


def test_reference_cap_is_refused_not_truncated(media_bucket):
    """Over the model's cap, the caller refuses rather than silently dropping."""
    with pytest.raises(refs.RefError) as exc:
        refs.character_ref_keys("subject-a", cap=2, cap_name="kling")
    assert "3 image(s) but kling takes 2" in str(exc.value)
    # The message has to say how to narrow it, or it is not actionable.
    assert "--pick-tag" in str(exc.value)


def test_unknown_character_raises_referror(media_bucket):
    with pytest.raises(refs.RefError):
        refs.character_ref_keys("no-such-subject")


def test_character_pool_keys(media_bucket):
    """corpus/, seed/ and archive/ are material, not identity."""
    assert refs.character_pool_keys("subject-a", "seed") == [
        "characters/subject-a/seed/subject-a_1.webp"
    ]
    assert refs.character_pool_keys("subject-a", "corpus") == [
        "characters/subject-a/corpus/IMG_1966_Original.JPG"
    ]


# --------------------------------------------------------------------------
# refs -> projects
# --------------------------------------------------------------------------
def test_project_input_keys_resolve_in_the_order_asked_for(media_bucket):
    assert refs.project_input_keys("subject-a", [2, 1]) == [
        "projects/subject-a/input/subject-a_2.webp",
        "projects/subject-a/input/subject-a_1.webp",
    ]


def test_missing_input_number_names_what_is_available(media_bucket):
    with pytest.raises(refs.RefError) as exc:
        refs.project_input_keys("subject-a", [7])
    assert "[7]" in str(exc.value) and "[1, 2]" in str(exc.value)


# --------------------------------------------------------------------------
# build -> phrasebook
# --------------------------------------------------------------------------
def test_phrasebook_terms(media_bucket):
    assert phrasebook.terms(media_bucket, "kling") == [
        {"avoid": "bare chest", "use": "chest"},
        {"avoid": "shirtless", "use": "omit entirely"},
    ]


def test_phrasebook_terms_for_unknown_model_is_empty_not_an_error(media_bucket):
    """A model with no section must not break prompt authoring."""
    assert phrasebook.terms(media_bucket, "no-such-model") == []


def test_prompt_authoring_survives_an_unreachable_phrasebook(monkeypatch):
    """Authoring must keep working without credentials.

    A fetch failure degrades to a warning saying the list was not read, which
    is honest — rather than reporting a draft as checked when it was not.
    """
    from studio_pipeline.domain import prompt as build

    def boom(*_a, **_k):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(build.PHRASEBOOK, "terms", boom)
    terms, reason = build.phrasebook_terms("kling")
    assert terms == []
    assert reason and "phrasebook" in reason.lower()


# --------------------------------------------------------------------------
# frames -> projects
# --------------------------------------------------------------------------
def test_add_inputs_returns_the_key_it_wrote(media_bucket, tmp_path):
    """The caller needs the real key back.

    This used to scrape a log line with a regex and rebuild the key by
    re-appending the extension, which yielded None whenever the message shape
    changed — and only after the upload had already happened.
    """
    src = tmp_path / "frame.jpeg"
    src.write_bytes(b"jpeg-bytes")
    added = projects.add_inputs(media_bucket, "subject-a", [str(src)])
    assert len(added) == 1
    assert added[0]["key"].startswith("projects/subject-a/input/")
    assert added[0]["key"].endswith(".jpeg")
    # It is really there.
    media_bucket.head_object(Bucket="xharness-prod-media-us-east-1", Key=added[0]["key"])


def test_editing_a_bible_writes_it_back_where_it_was_read_from(media_bucket, tmp_path):
    """`edit --push` must write through `paths`, not a hand-built key.

    It used to build `f"{name}/profile.yaml"` — the pre-migration layout — so a
    push landed in the bucket ROOT, reported success, and updated the local
    sidecars as though it had worked. The bible was untouched and nothing said
    so, which is the worst shape a save bug can take.
    """
    from studio_pipeline.domain import characters as CHARACTER
    from studio_pipeline.domain import paths as P

    local = tmp_path / "subject-a.yaml"
    base = tmp_path / ".subject-a.base.yaml"
    etag = tmp_path / ".subject-a.etag"

    original = CHARACTER.load_profile(media_bucket, "subject-a")
    base.write_text("name: Subject A\n")
    local.write_text("name: Subject A\ndescription: edited\n")
    etag.write_text(CHARACTER.remote_etag(media_bucket, "subject-a") or "")

    # The schema check guards writes; this test is about WHERE the bytes land.
    CHARACTER.check_profile = lambda *a, **k: None
    CHARACTER.do_push(media_bucket, "subject-a", False, str(local), str(base), str(etag))

    written = CHARACTER.load_profile(media_bucket, "subject-a")
    assert written != original, "the profile the reader loads was not updated"
    assert written.get("description") == "edited"

    keys = [o["Key"] for o in media_bucket.list_objects_v2(
        Bucket=P.s3c.BUCKET).get("Contents", [])]
    assert "subject-a/profile.yaml" not in keys, "wrote to the bucket root"
    assert P.profile_key("subject-a") in keys
