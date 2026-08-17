"""The reference shoot: the spec, the prompts, and what reaches the model.

Three classes of thing are worth pinning here, and they are the three that would
fail silently rather than loudly:

  * `config/` being a legal binding root. `check_bindings` refuses a key outside
    the known roots, so without that entry every shoot fails at record time and
    the feature simply does not exist.
  * The CITATION positions. A prompt says "[Image1] is a pose guide, take only
    the stance from it"; if that number does not match where the plate actually
    landed in the resolved list, the instruction is aimed at the character's own
    face. Nothing errors — the render is just quietly wrong.
  * The spec's defaults being PORTABLE. `--model` overrides them, and an input
    field one model has and another does not is rejected at preflight. A test
    against the registry catches that when a snapshot changes, rather than when
    someone tries the override.
"""

from __future__ import annotations

import json
import os
import re

import pytest
import yaml
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.domain import paths as P
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import shoot as SHOOT
from studio_pipeline.engine import submit as SUB

REPO_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config"
)


@pytest.fixture
def spec():
    return SHOOT.load_spec()


# --- the spec ---------------------------------------------------------------

def test_spec_loads_and_every_slot_is_complete(spec):
    assert spec["slots"], "the spec defines no slots"
    for slot in spec["slots"]:
        assert slot["group"] in P.POSE_GROUPS
        assert slot["pose_image"].startswith(P.CONFIG + "/")
        assert slot["description"].strip()
        assert slot["tags"]


def test_default_set_is_slots_and_fits_the_smallest_cap(spec):
    ids = {s["id"] for s in spec["slots"]}
    assert set(spec["default_set"]) <= ids
    # Kling takes 7 reference images and is the tightest cap a character's
    # default selection meets.
    assert len(spec["default_set"]) <= 7


def test_every_pose_image_exists_in_the_repo(spec):
    """The plates are committed, so a slot naming a missing one is a broken spec.

    They reach the bucket from this directory via dev-setup.sh, which cannot copy
    out a file that was never committed.
    """
    missing = [
        slot["pose_image"] for slot in spec["slots"]
        if not os.path.isfile(os.path.join(REPO_CONFIG, slot["pose_image"].split("/", 1)[1]))
    ]
    assert not missing, f"pose plate(s) not in studio/config/: {missing}"


def test_both_three_quarters_exist_and_face_opposite_ways(spec):
    """The defect this standard exists to prevent, asserted.

    A live reference set had two "three-quarter" face frames that turned the same
    way — coverage on paper, one angle in fact.
    """
    for group in P.POSE_GROUPS:
        ids = {s["id"] for s in spec["slots"] if s["group"] == group}
        assert f"{group}_three_quarter_left" in ids
        assert f"{group}_three_quarter_right" in ids
    for slot in spec["slots"]:
        if slot["id"].endswith("_three_quarter_left"):
            assert "THEIR LEFT" in slot["prompt"]
        if slot["id"].endswith("_three_quarter_right"):
            assert "THEIR RIGHT" in slot["prompt"]


def test_every_body_slot_demands_the_whole_figure(spec):
    """Four images in a live set claimed "full body" and cropped at mid-thigh."""
    for slot in spec["slots"]:
        if slot["group"] == "body":
            assert "HEAD TO FEET" in slot["prompt"], slot["id"]
            assert "full-body" in slot["tags"], slot["id"]


def test_no_character_name_leaks_into_the_spec(spec):
    """Hard rule 1. The spec is generic; the bible supplies the specifics."""
    text = yaml.safe_dump(spec)
    for name in ("subject-a", "subject-b"):
        assert name not in text


# --- the prompt ------------------------------------------------------------

PROFILE = {
    "wardrobe": {"tops": [{"item": "Short-sleeve polo shirt", "detail": "with embroidery"}]},
    "consistency": {"must": ["A long straight nose", "Dressed — polo or tee"]},
    "text_identity_block": "A compact man in his forties.",
}


def test_prompts_fill_completely_and_carry_the_bible(spec):
    for slot in spec["slots"]:
        text = SHOOT.build_prompt(slot, spec, PROFILE, 1, [2, 3])
        assert not re.search(r"\{[a-z_]+\}", text), f"{slot['id']} has an unfilled placeholder"
        assert "A long straight nose" in text, slot["id"]
        # A face plate wears the bible's usual top; a body plate strips back to
        # shorts so the silhouette reads. Each group names only its own.
        if slot["group"] == "face":
            assert "polo shirt" in text.lower(), slot["id"]
        else:
            assert "shorts" in text.lower(), slot["id"]


def test_a_body_prompt_says_its_wardrobe_overrides_the_bible(spec):
    """The bible's `must` can say "Dressed — polo"; a body plate strips back to
    shorts. Both appear in the prompt, so the prompt has to say which wins."""
    slot = next(s for s in spec["slots"] if s["group"] == "body")
    text = SHOOT.build_prompt(slot, spec, PROFILE, 1, [2])
    assert "wardrobe named above governs" in text


def test_an_unknown_placeholder_is_refused_by_name(spec):
    slot = dict(spec["slots"][0], prompt="see {nonesuch}")
    with pytest.raises(SHOOT.ShootError, match="nonesuch"):
        SHOOT.build_prompt(slot, spec, PROFILE, 1, [2])


@pytest.mark.parametrize("positions,expected", [
    ([2], "[Image2]"),
    ([2, 3], "[Image2] and [Image3]"),
    ([2, 3, 4], "[Image2], [Image3] and [Image4]"),
])
def test_identity_citations_read_as_a_list(positions, expected):
    assert SHOOT._slots_phrase(positions) == expected


# --- the invariant the feature rests on ------------------------------------

def test_config_is_a_legal_binding_root():
    key = P.pose_key("body", "front.png")
    assert R.check_bindings({"input_images": [key]}) == {"input_images": [key]}


def test_a_key_outside_the_known_roots_is_still_refused():
    with pytest.raises(R.RunError):
        R.check_bindings({"input_images": ["elsewhere/front.png"]})


def test_pose_key_rejects_a_group_that_is_not_one():
    with pytest.raises(P.PathError):
        P.pose_key("wardrobe", "front.png")


# --- the model override ----------------------------------------------------

def test_spec_defaults_are_portable_across_every_image_model(spec):
    """`--model` is only usable if the defaults are vocabulary all of them share.

    Asserted against the registry snapshots so that a `studio models refresh`
    which drops a value fails here, not at submit time on someone's shoot.
    """
    aspect = spec["defaults"]["aspect_ratio"]
    fmt = spec["defaults"]["extra"]["output_format"]
    for key, entry in REG.all().items():
        if entry.get("kind") != "image":
            continue
        snap = entry.get("snapshot") or {}
        assert aspect in (snap.get("aspect_ratio") or {}).get("enum", [aspect]), (
            f"{key} does not accept aspect_ratio={aspect!r}")
        assert fmt in (snap.get("output_format") or {}).get("enum", [fmt]), (
            f"{key} does not accept output_format={fmt!r}")


def test_per_model_blocks_name_registered_models(spec):
    for key in (spec.get("per_model") or {}):
        REG.get(key)  # raises RegistryError if it is not in the registry


def test_only_the_resolved_models_extras_are_sent(spec):
    """A gpt-only knob must not travel with a Nano Banana override."""
    from types import SimpleNamespace
    slot = next(s for s in spec["slots"] if s["id"] == "face_front")
    opts = SimpleNamespace(model="nano-banana-pro", project="p", extra=None,
                           aspect_ratio=None, dry_run=True, yes=False, dest=None,
                           expires=3600)
    args = SHOOT.slot_args(slot, spec, REG.get("nano-banana-pro"), "subject-a", opts)
    extra = json.loads(args.extra)
    assert "quality" not in extra and "moderation" not in extra
    assert extra["output_format"] == "png"


def test_model_precedence_is_cli_then_slot_then_default(spec):
    from types import SimpleNamespace
    slot = dict(next(s for s in spec["slots"]), model="nano-banana-2")
    base = dict(project="p", extra=None, aspect_ratio=None, dry_run=True, yes=False,
                dest=None, expires=3600)
    cli_wins = SHOOT.slot_args(slot, spec, REG.get("gpt-image-1.5"), "subject-a",
                               SimpleNamespace(model="gpt-image-1.5", **base))
    assert cli_wins.model == "gpt-image-1.5"
    slot_wins = SHOOT.slot_args(slot, spec, REG.get("nano-banana-2"), "subject-a",
                                SimpleNamespace(model=None, **base))
    assert slot_wins.model == "nano-banana-2"
    default_wins = SHOOT.slot_args(dict(slot, model=None), spec,
                                   REG.get(spec["defaults"]["model"]), "subject-a",
                                   SimpleNamespace(model=None, **base))
    assert default_wins.model == spec["defaults"]["model"]


# --- slot selection --------------------------------------------------------

def test_group_and_slot_filters(spec):
    assert {s["group"] for s in SHOOT.select_slots(spec, "face", ())} == {"face"}
    assert [s["id"] for s in SHOOT.select_slots(spec, "all", ("body_back",))] == ["body_back"]
    assert len(SHOOT.select_slots(spec, "all", ())) == len(spec["slots"])


def test_an_unknown_slot_lists_the_real_ones(spec):
    with pytest.raises(SHOOT.ShootError, match="face_front"):
        SHOOT.select_slots(spec, "all", ("no_such_slot",))


# --- against the bucket ----------------------------------------------------

def _seed_plates(s3, spec):
    for slot in spec["slots"]:
        s3.put_object(Bucket=os.environ["XHARNESS_S3_BUCKET"],
                      Key=slot["pose_image"], Body=b"png-bytes")


def test_missing_plates_point_at_dev_setup(media_bucket, spec):
    with pytest.raises(SHOOT.ShootError, match="dev-setup"):
        SHOOT.check_plates(media_bucket, spec["slots"])


def test_plates_present_pass_the_check(media_bucket, spec):
    _seed_plates(media_bucket, spec)
    SHOOT.check_plates(media_bucket, spec["slots"])  # no raise


def test_identity_prefers_seed_over_generated_references(media_bucket):
    keys, source = SHOOT.identity_keys(media_bucket, "subject-a", "auto", None, None)
    assert source == "seed"
    assert all("/seed/" in k for k in keys)


def test_identity_falls_back_to_references_when_seed_is_empty(media_bucket):
    keys, source = SHOOT.identity_keys(media_bucket, "subject-b", "auto", None, None)
    assert source == "reference"
    assert keys


def test_identity_seed_explicitly_refuses_to_substitute(media_bucket):
    with pytest.raises(SHOOT.ShootError, match="seed/"):
        SHOOT.identity_keys(media_bucket, "subject-b", "seed", None, None)


def test_identity_is_capped(media_bucket):
    keys, _ = SHOOT.identity_keys(media_bucket, "subject-a", "refs", None, None, limit=1)
    assert len(keys) == 1


def test_citations_match_where_the_plate_actually_lands(media_bucket, spec):
    """`{pose_slot}` must come from the RESOLVED order, never be assumed.

    `gather` de-dupes, filters by what the model accepts and orders by category,
    so it is the only authority on where the plate ended up. This is the test
    that fails if someone hard-codes a number into a prompt.
    """
    from types import SimpleNamespace
    _seed_plates(media_bucket, spec)
    slot = next(s for s in spec["slots"] if s["id"] == "face_front")
    entry = REG.get(spec["defaults"]["model"])
    opts = SimpleNamespace(model=None, project="subject-a", extra=None, aspect_ratio=None,
                           dry_run=True, yes=False, dest=None, expires=3600,
                           identity=["characters/subject-a/seed/subject-a_1.webp"])
    args = SHOOT.slot_args(slot, spec, entry, "subject-a", opts)
    args.key = [SHOOT.plate_key(slot), *opts.identity]
    bindings = SUB.gather(entry, media_bucket, args)
    ordered = bindings[entry["images"]["refs"]]

    assert len(ordered) == 2, ordered
    plate_position = ordered.index(SHOOT.plate_key(slot)) + 1
    # The shoot passes the plate as its first explicit key, so it comes out
    # first — an outcome of how the keys are ordered, which is exactly why the
    # citation is read back from `ordered` rather than written into the prompt.
    assert plate_position == 1
    identity_positions = [i + 1 for i, k in enumerate(ordered) if k != SHOOT.plate_key(slot)]
    text = SHOOT.build_prompt(slot, spec, PROFILE, plate_position, identity_positions)
    assert f"[Image{plate_position}] is a POSE GUIDE" in text
    for n in identity_positions:
        assert f"[Image{n}]" in text.split("show the person")[0]


def test_the_run_records_the_character_it_is_of(media_bucket, spec):
    """The shoot resolves its own keys, so it passes no --character.

    `record_characters` is what keeps `runs find --character` working; without it
    a shoot's runs would be associated with nobody.
    """
    from types import SimpleNamespace
    slot = spec["slots"][0]
    opts = SimpleNamespace(model=None, project="p", extra=None, aspect_ratio=None,
                           dry_run=True, yes=False, dest=None, expires=3600)
    args = SHOOT.slot_args(slot, spec, REG.get(spec["defaults"]["model"]), "subject-a", opts)
    assert args.character == ()
    assert args.record_characters == ("subject-a",)


def test_shoot_dry_run_renders_every_slot_and_submits_nothing(media_bucket, spec, monkeypatch):
    """The approval gate: nine payloads on screen, no prediction created."""
    _seed_plates(media_bucket, spec)
    entry = REG.get(spec["defaults"]["model"])
    props = {f: {} for f in ("prompt", "aspect_ratio", "output_format", "quality",
                             "moderation", entry["images"]["refs"])}
    monkeypatch.setattr("studio_pipeline.engine.schema.fetch", lambda *a, **k: (props, {}))

    def refuse(*a, **k):
        raise AssertionError("a dry run must not create a prediction")

    monkeypatch.setattr("studio_pipeline.adapters.replicate.create_prediction", refuse)

    result = CliRunner().invoke(cli.main, [
        "character", "shoot", "subject-a", "--project", "subject-a", "--dry-run"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    for slot in spec["slots"]:
        assert f"slot {slot['id']}" in result.output
    assert "nothing billed" in result.output


def test_shoot_needs_a_project(media_bucket, spec):
    result = CliRunner().invoke(cli.main, ["character", "shoot", "subject-a", "--dry-run"])
    assert result.exit_code != 0
    assert "project" in result.output.lower()


def test_shoot_refuses_an_unregistered_model(media_bucket, spec):
    _seed_plates(media_bucket, spec)
    result = CliRunner().invoke(cli.main, [
        "character", "shoot", "subject-a", "--project", "subject-a",
        "--model", "not-a-model", "--dry-run"])
    assert result.exit_code != 0


def test_shoot_refuses_a_video_model(media_bucket, spec):
    _seed_plates(media_bucket, spec)
    result = CliRunner().invoke(cli.main, [
        "character", "shoot", "subject-a", "--project", "subject-a",
        "--model", "kling", "--dry-run"])
    assert result.exit_code != 0
    assert "still" in result.output


def test_create_shoot_refuses_the_blank_template(media_bucket):
    result = CliRunner().invoke(cli.main, [
        "character", "create", "subject-c", "--shoot", "--project", "subject-a"])
    assert result.exit_code != 0
    assert "--from-profile" in result.output


# --- the crop script -------------------------------------------------------

def test_the_pose_sheet_split_is_deterministic(tmp_path):
    """Same sheet in, same boxes out — the split is measured, not hand-tuned."""
    from PIL import Image

    from scripts.split_pose_sheet import find_figures

    sheet = Image.new("L", (400, 200), color=40)
    for x0 in (20, 140, 260):                      # three figures, evenly spaced
        for x in range(x0, x0 + 60):
            for y in range(30, 170):
                sheet.putpixel((x, y), 200)
    first = find_figures(sheet)
    assert len(first) == 3
    assert find_figures(sheet) == first
