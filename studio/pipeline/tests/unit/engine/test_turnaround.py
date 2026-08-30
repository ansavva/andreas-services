"""The turnaround: the spec, the prompts, and what reaches the model.

Three classes of thing are worth pinning here, and they are the three that would
fail silently rather than loudly:

  * `config/` being a legal binding root. `check_bindings` refuses a key outside
    the known roots, so without that entry every turnaround fails at record time and
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
from types import SimpleNamespace

import pytest
import yaml
from click.testing import CliRunner

from studio_pipeline import STUDIO_DIR, cli
from studio_pipeline.domain import paths as P
from studio_pipeline.domain import runs as R
from studio_pipeline.engine import registry as REG
from studio_pipeline.engine import turnaround as TURN
from studio_pipeline.engine import submit as SUB

REPO_CONFIG = os.path.join(
    str(STUDIO_DIR), "config"
)


@pytest.fixture
def spec():
    return TURN.load_spec()


# --- the spec ---------------------------------------------------------------

def test_spec_loads_and_every_slot_is_complete(spec):
    assert spec["angles"], "the spec defines no angles"
    for angle in spec["angles"]:
        assert angle["group"] in P.ANGLE_GROUPS
        assert angle["angle_image"].startswith(P.CONFIG + "/")
        assert angle["description"].strip()
        assert angle["tags"]


def test_default_set_is_slots_and_fits_the_smallest_cap(spec):
    ids = {s["id"] for s in spec["angles"]}
    assert set(spec["default_set"]) <= ids
    # Kling takes 7 reference images and is the tightest cap a character's
    # default selection meets.
    assert len(spec["default_set"]) <= 7


def test_every_pose_image_exists_in_the_repo(spec):
    """The plates are committed, so an angle naming a missing one is a broken spec.

    They reach the bucket from this directory via dev-setup.sh, which cannot copy
    out a file that was never committed.
    """
    missing = [
        angle["angle_image"] for angle in spec["angles"]
        if not os.path.isfile(os.path.join(REPO_CONFIG, angle["angle_image"].split("/", 1)[1]))
    ]
    assert not missing, f"angle image(s) not in studio/config/: {missing}"


def test_opposite_slots_carry_opposite_frame_directions(spec):
    """The defect this standard exists to prevent, asserted.

    A live set had two "three-quarter" face frames turned the same way, and the
    first turnaround reproduced it — because the prompt said "turned to THEIR LEFT so
    the viewer sees the LEFT side of the face", which instructs two opposite
    rotations at once. Direction is now stated only as the edge of frame the
    face points toward, so an angle and its twin must name opposite edges.
    """
    by_id = {s["id"]: s for s in spec["angles"]}
    for group in P.ANGLE_GROUPS:
        for pair in ("three_quarter", "profile", "three_quarter_back"):
            left, right = f"{group}_{pair}_left", f"{group}_{pair}_right"
            # A pair may be absent — the body front three-quarters were dropped
            # when their plate turned out to be unrenderable. What must never
            # happen is HALF a pair, which is how a one-sided set looks like
            # coverage.
            if left not in by_id and right not in by_id:
                continue
            assert left in by_id and right in by_id, f"{group} has half of the {pair} pair"
            assert "LEFT edge" in by_id[left]["prompt"], left
            assert "RIGHT edge" not in by_id[left]["prompt"], left
            assert "RIGHT edge" in by_id[right]["prompt"], right
            assert "LEFT edge" not in by_id[right]["prompt"], right


def test_back_three_quarter_slots_turn_the_shoulders_and_forbid_a_profile(spec):
    """Both back three-quarters came back as a PROFILE HEAD ON A FLAT BACK.

    "Turned about 135 degrees away" named no subject, so the model rotated the
    head to 90 degrees and left the shoulders square to the lens — which is the
    profile angle with a back body, not a three-quarter back. Two things fix it,
    and both are asserted here because either alone was already true of the
    wording that failed:

      * the rotation clause says what turns — the head AND the shoulders;
      * a prohibition rules out the profile reading. On this model the negative
        clauses are what bind: "no waist, no hips and no legs" held on all
        eight angles of a live turnaround while the positive "CROPPED AT MID-CHEST"
        drifted wider on nearly every one.
    """
    backs = [s for s in spec["angles"] if "three_quarter_back" in s["id"]]
    assert len(backs) == 2 * len(P.ANGLE_GROUPS), "expected a back pair per group"
    for angle in backs:
        text = angle["prompt"]
        assert "SHOULDERS TOGETHER" in text, f"{angle['id']} does not turn the torso"
        assert "NOT A PROFILE" in text, f"{angle['id']} permits a profile"
        assert "not square" in text.lower(), angle["id"]


def test_face_back_three_quarters_bind_a_torso_guide(spec):
    """Wording alone did not rotate the torso, because the image disagreed.

    A face plate is cut from a head sheet and ends at a neck stump, so it shows
    no shoulder line — and a symmetric stump reads as square to the camera.
    Both back three-quarters came back with a correctly turned head on a flat
    back even after the prompt was rewritten to insist the shoulders turn. The
    fix is a second plate that actually depicts the angle, so these angles are
    the one place two guides are bound. The other six face angles need no such
    thing: their orientation is legible from the head alone.
    """
    face_backs = [s for s in spec["angles"]
                  if s["group"] == "face" and "three_quarter_back" in s["id"]]
    assert len(face_backs) == 2
    for angle in face_backs:
        torso = angle.get("torso_image")
        assert torso, f"{angle['id']} binds no torso guide"
        # Same orientation as the head plate, from the body set.
        assert torso == angle["angle_image"].replace("/face/", "/body/"), angle["id"]
        assert "{torso_slot}" in angle["prompt"], angle["id"]
    others = [s for s in spec["angles"] if s not in face_backs]
    assert not [s["id"] for s in others if s.get("torso_image")], \
        "only the face back three-quarters should need a second guide"


def test_every_slot_states_the_build_and_disowns_the_guides(spec):
    """A plate exists to record a person, and the first ones lost their build.

    The figure came back lean and narrow-shouldered with none of the bible's
    taper or arm mass, because the angle image is a mannequin with proportions of
    its own and `{guide}`'s "not its build, proportions" was one buried clause
    against a whole reference image. `{build}` puts the bible's own silhouette
    and arms in the foreground; the intro disowns the guide explicitly.

    Face angles carry it too. They were exempted at first — "cropped at
    mid-chest, so there is no build in frame to get wrong" — and a live front
    plate came back narrow-shouldered on a character whose bible calls broad
    shoulders on a medium frame his single most reliable cue. A mid-chest crop
    shows the neck, the traps, the shoulder line and the upper arm, which is
    most of what reads as build.
    """
    for angle in spec["angles"]:
        assert "{build}" in angle["prompt"], angle["id"]
        assert "{build_intro}" in angle["prompt"], angle["id"]
    intro = (spec["defaults"] or {}).get("build_intro", "")
    assert "NOT THE GUIDE" in intro, "the intro must disown the pose guide by name"


def test_the_face_and_the_build_name_different_authorities(spec):
    """A reference pool is mostly head-and-shoulders, so the two differ.

    The face is the best-evidenced thing about a character — photographs of it,
    from several angles — so the images lead. The build usually is not evidenced
    at all, and telling a model to take proportions "from the reference images"
    pointed it at pictures that do not contain the answer, so it invented one.
    Both clauses now say which source wins, and they must not say the same
    thing: a live face came back finer-boned than every photograph of it while
    the prompt was giving images and prose equal weight.
    """
    face = (spec["defaults"] or {}).get("face_intro", "")
    build = (spec["defaults"] or {}).get("build_intro", "")
    assert "the images win" in face, "the face clause must give the images priority"
    assert "WIDTH of the jaw and chin" in face, "face width is the drift this catches"
    assert "THIS DESCRIPTION first" in build, "the build clause must give the text priority"
    for angle in spec["angles"]:
        assert "{face_intro}" in angle["prompt"], angle["id"]


def test_a_plate_wears_the_bibles_stated_colour_when_it_has_one():
    """The schema files colour under `detail` — which the plate discards.

    `detail` is dropped on purpose: it names embroidery and graphics a model
    renders differently every time, which would make a group inconsistent. But
    colour lives in that same field, so dropping it whole threw the colour away
    too, and a live plate came back in a colour nobody picked. `colour:` is the
    one word a plate may take, kept apart from the prose around it.
    """
    worn = TURN._first_top(
        {"wardrobe": {"tops": [{"item": "Short-sleeve polo shirt", "colour": "White",
                                "detail": "with a navy chest crest and embroidery"}]}})
    assert "plain white short-sleeve polo shirt" in worn
    assert "crest" not in worn, "detail must not leak into the plate"
    # Optional: a bible naming the colour inside `item` already read correctly.
    plain = TURN._first_top({"wardrobe": {"tops": [{"item": "White ribbed tank top"}]}})
    assert "plain white ribbed tank top" in plain


def test_a_body_plate_gets_the_whole_body_block_and_a_face_plate_does_not():
    """Four of the bible's six body fields were never read.

    `_build_text` began as silhouette + arms, which left `chest_and_shoulders`,
    `neck`, `lower_body_and_hands` and `body_hair` unused — the last of those
    written expressly to defeat the smooth fitness-model default a generator
    produces when nobody says otherwise, and unused on the one plate that
    strips the wardrobe back to shorts.

    A face plate crops at mid-chest, so legs and body hair are not in frame and
    would only be noise; it takes what shows above the crop.
    """
    profile = {"identity": {"height_read": "HEIGHT."}, "body": {
        "silhouette": "SIL.", "chest_and_shoulders": "CHEST.", "neck": "NECK.",
        "arms": "ARMS.", "lower_body_and_hands": "LEGS.", "body_hair": "HAIR."}}
    body = TURN._build_text(profile, "body")
    face = TURN._build_text(profile, "face")
    for part in ("SIL.", "CHEST.", "NECK.", "ARMS."):
        assert part in body and part in face, part
    # Height is the one proportion stated as a NUMBER, and it lives in
    # `identity`, so the body block alone never carried it. Both groups need it:
    # a figure has no scale of its own against a plain backdrop.
    assert body.startswith("HEIGHT.") and face.startswith("HEIGHT.")
    for part in ("LEGS.", "HAIR."):
        assert part in body, f"a body plate must carry {part}"
        assert part not in face, f"a face plate must not carry {part}"
    # A bible missing any of them still renders.
    assert TURN._build_text({"body": {"arms": "ARMS."}}, "body") == "ARMS."


def test_a_body_field_the_tuple_never_heard_of_still_reaches_the_prompt():
    """`body:` is a free-form map, so the named tuples cannot be exhaustive.

    They were treated as though they were, and it rotted in the one way that
    leaves no trace in the payload: `back`, `hands` and `midsection` were
    written into a bible and read by nothing, while a rename of
    `lower_body_and_hands` dropped the legs clause out of every body plate
    without an error. So anything the tuples miss is swept up.
    """
    profile = {"body": {"silhouette": "SIL.", "back": "BACK.", "hands": "HANDS.",
                        "midsection": "MID.", "lower_body": "LEGS.",
                        "shoulder_freckles": "NOVEL."}}
    body = TURN._build_text(profile, "body")
    for part in ("SIL.", "BACK.", "HANDS.", "MID.", "LEGS.", "NOVEL."):
        assert part in body, part

    # The face/body split survives the sweep: a face plate crops at mid-chest,
    # so what sits below the crop stays out of it even when unnamed.
    face = TURN._build_text(profile, "face")
    assert "BACK." in face and "HANDS." in face
    for part in ("MID.", "LEGS."):
        assert part not in face, f"a face plate must not carry {part}"


def test_the_legacy_spelling_is_still_read():
    """A bible written before the split is still a valid bible."""
    body = TURN._build_text({"body": {"lower_body_and_hands": "LEGS."}}, "body")
    assert "LEGS." in body


def test_posture_is_not_swept_into_the_build_text():
    """It is a rendering direction with its own clause, not a description of
    the build; sweeping it in would put it in the prompt twice."""
    body = TURN._build_text({"body": {"arms": "ARMS.", "posture": "POSTURE."}}, "body")
    assert "ARMS." in body and "POSTURE." not in body


def test_the_build_text_comes_from_the_bible_not_the_spec(spec):
    """Hard rule 1: proportions are character specifics, so the spec may only
    name the placeholder. A bible with no `body:` block must still render."""
    filled = TURN._build_text({"body": {"silhouette": "Sil.", "arms": "Arms."}})
    assert filled == "Sil. Arms."
    assert TURN._build_text({}) == ""
    text = yaml.safe_dump(spec)
    for leak in ("head-width", "V-taper", "biceps"):
        assert leak not in text, f"the spec hardcodes {leak!r}"


def test_every_slot_states_the_age_and_says_it_beats_the_references(spec):
    """Seed pools span years, and nothing decided which year to render.

    One live identity set held the same person roughly a decade apart, with no
    clause naming an age — so the model was free to average them. Unlike the
    crop or the build, this cannot be left to the reference images, because the
    references are precisely what disagree. `identity.apparent_age` has been in
    the bible all along; the prompt now reads it and says it outranks them.
    """
    for angle in spec["angles"]:
        assert "{age_intro} {age}" in angle["prompt"], angle["id"]
    intro = (spec["defaults"] or {}).get("age_intro", "")
    assert "do not all agree" in intro, "the intro must say the references conflict"
    assert "take the AGE from here" in intro


def test_the_age_text_comes_from_the_bible_not_the_spec(spec):
    """Hard rule 1 again: an age is a character specific."""
    assert TURN._age_text({"identity": {"apparent_age": "Mid-30s"}}) == "Mid-30s"
    assert TURN._age_text({}) == ""
    text = yaml.safe_dump(spec)
    for leak in ("30s", "40s", "50s", "years old"):
        assert leak not in text, f"the spec hardcodes {leak!r}"


def test_no_prompt_describes_direction_from_the_subjects_own_side(spec):
    """"Their left" is unresolvable without also knowing what the viewer sees,
    and pairing the two is how the contradiction got in. Frame edges only."""
    for angle in spec["angles"]:
        text = angle["prompt"].lower()
        for banned in ("their left", "their right", "his left", "his right"):
            assert banned not in text, f"{angle['id']} says {banned!r}"


def test_every_face_slot_states_the_crop(spec):
    """"Head-and-shoulders studio portrait" did not bind — one angle came back as
    a full-body figure and framing drifted wider angle by angle."""
    for angle in spec["angles"]:
        if angle["group"] == "face":
            assert "CROPPED AT MID-CHEST" in angle["prompt"], angle["id"]
            assert "no legs" in angle["prompt"], angle["id"]


def test_face_slots_hold_the_head_at_one_scale(spec):
    """A turnaround is read by comparing its plates, so scale must be constant.

    "CROPPED AT MID-CHEST" fixes the bottom edge and says nothing about how big
    the head is. A live set came back with some heads half again the size of
    others, which reads as several sessions rather than one turn.
    """
    for angle in spec["angles"]:
        if angle["group"] == "face":
            assert "{scale_face}" in angle["prompt"], angle["id"]
    scale = (spec["defaults"] or {}).get("scale_face", "")
    assert "SCALE" in scale and "upper third" in scale, "scale must be stated checkably"


def test_three_quarter_slots_say_what_forty_five_degrees_looks_like(spec):
    """"Turned about 45 degrees, eyes returning to the lens" did not bind.

    It came back nearer 30 with the gaze wandering off camera, on two different
    characters. A model cannot check an angle, but it can check what is in the
    picture: the far ear out of view, the far cheek behind the nose, both eyes
    on the lens.
    """
    tqs = [s for s in spec["angles"]
           if s["id"].endswith(("three_quarter_left", "three_quarter_right"))
           and "back" not in s["id"]]
    assert tqs, "expected front three-quarter angles"
    for angle in tqs:
        assert "{turn_check}" in angle["prompt"], angle["id"]
    check = (spec["defaults"] or {}).get("turn_check", "")
    assert "far ear is out of view" in check
    assert "BOTH eyes look directly into the lens" in check


def test_the_set_covers_the_orientations_each_group_can_render(spec):
    """Face covers all eight. Body covers six.

    The body front three-quarters are gone, and deliberately: their angle image
    is a figure gpt-image-2 refuses (four refusals across two models, both as an
    upscale subject and as a guide), so the angles could not be rendered at all.
    An angle nobody can render is worse than an absent one — it reads as coverage
    and fails at spend time, and one refusal aborts the whole batch around it.
    """
    counts = {g: len([s for s in spec["angles"] if s["group"] == g]) for g in P.ANGLE_GROUPS}
    assert counts == {"face": 8, "body": 6}, counts
    gone = {"body_three_quarter_left", "body_three_quarter_right"}
    assert not gone & {s["id"] for s in spec["angles"]}


def test_every_body_slot_demands_the_whole_figure(spec):
    """Four images in a live set claimed "full body" and cropped at mid-thigh."""
    for angle in spec["angles"]:
        if angle["group"] == "body":
            assert "HEAD TO FEET" in angle["prompt"], angle["id"]
            assert "full-body" in angle["tags"], angle["id"]


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
    for angle in spec["angles"]:
        # An angle binding a second guide gets a position for it; one that does
        # not must render without ever being handed a `torso_slot` to fill.
        torso = 2 if angle.get("torso_image") else None
        text = TURN.build_prompt(angle, spec, PROFILE, 1, [3, 4], torso)
        assert not re.search(r"\{[a-z_]+\}", text), f"{angle['id']} has an unfilled placeholder"
        assert "A long straight nose" in text, angle["id"]
        # A face plate wears the bible's usual top; a body plate strips back to
        # shorts so the silhouette reads. Each group names only its own.
        if angle["group"] == "face":
            assert "polo shirt" in text.lower(), angle["id"]
        else:
            assert "shorts" in text.lower(), angle["id"]


def test_a_body_prompt_says_its_wardrobe_overrides_the_bible(spec):
    """The bible's `must` can say "Dressed — polo"; a body plate strips back to
    shorts. Both appear in the prompt, so the prompt has to say which wins."""
    angle = next(s for s in spec["angles"] if s["group"] == "body")
    text = TURN.build_prompt(angle, spec, PROFILE, 1, [2])
    assert "wardrobe named above governs" in text


def test_an_unknown_placeholder_is_refused_by_name(spec):
    angle = dict(spec["angles"][0], prompt="see {nonesuch}")
    with pytest.raises(TURN.TurnaroundError, match="nonesuch"):
        TURN.build_prompt(angle, spec, PROFILE, 1, [2])


@pytest.mark.parametrize("positions,expected", [
    ([2], "[Image2]"),
    ([2, 3], "[Image2] and [Image3]"),
    ([2, 3, 4], "[Image2], [Image3] and [Image4]"),
])
def test_identity_citations_read_as_a_list(positions, expected):
    assert TURN._slots_phrase(positions) == expected


# --- the invariant the feature rests on ------------------------------------

def test_a_plate_binds_as_a_node_like_every_other_image(library, spec):
    """An angle image is recorded now, and that is the point of the change.

    It used to be the one image a run could be shown and not remember: plates
    had no node, so they travelled under a `shared:<key>` marker that was
    stripped before the record was written. Both halves are gone — the plate is
    an ordinary node under `config/`, so it binds and records like anything
    else.
    """
    _seed_plates(library.fake, spec)
    plate = library.fake._resolve(TURN.angle_key(spec["angles"][0]))["id"]
    assert R.check_bindings({"input_images": [plate]}) == {"input_images": [plate]}


def test_a_plates_path_is_refused_like_any_other_path(library, spec):
    """`KEY_ROOTS` is gone with the keys it allow-listed.

    The old rule was "a binding must sit under a known root", which let a
    `config/` path through and rejected `elsewhere/`. The rule is now simply
    that a binding is a node id — a path is invalidated by any rename, which is
    what left records dangling before — so being under `config/` earns nothing.
    """
    _seed_plates(library.fake, spec)
    with pytest.raises(R.RunError, match="not a node id"):
        R.check_bindings({"input_images": [TURN.angle_key(spec["angles"][0])]})
    with pytest.raises(R.RunError, match="not a node id"):
        R.check_bindings({"input_images": ["elsewhere/front.png"]})


def test_pose_key_rejects_a_group_that_is_not_one():
    with pytest.raises(P.PathError):
        P.angle_key("wardrobe", "front.png")


# --- the model override ----------------------------------------------------

def test_spec_defaults_are_portable_across_every_image_model(spec):
    """`--model` is only usable if the defaults are vocabulary all of them share.

    Asserted against the registry snapshots so that a `studio models refresh`
    which drops a value fails here, not at submit time on someone's turnaround.
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
    angle = next(s for s in spec["angles"] if s["id"] == "face_front")
    opts = SimpleNamespace(model="nano-banana-pro", project="p", extra=None,
                           aspect_ratio=None, dry_run=True, yes=False, dest=None,
                           expires=3600)
    args = TURN.angle_args(angle, spec, REG.get("nano-banana-pro"), "subject-a", opts)
    extra = json.loads(args.extra)
    assert "quality" not in extra and "moderation" not in extra
    assert extra["output_format"] == "png"


def test_model_precedence_is_cli_then_angle_then_default(spec):
    from types import SimpleNamespace
    angle = dict(next(s for s in spec["angles"]), model="nano-banana-2")
    base = dict(project="p", extra=None, aspect_ratio=None, dry_run=True, yes=False,
                dest=None, expires=3600)
    cli_wins = TURN.angle_args(angle, spec, REG.get("gpt-image-1.5"), "subject-a",
                               SimpleNamespace(model="gpt-image-1.5", **base))
    assert cli_wins.model == "gpt-image-1.5"
    angle_wins = TURN.angle_args(angle, spec, REG.get("nano-banana-2"), "subject-a",
                                SimpleNamespace(model=None, **base))
    assert angle_wins.model == "nano-banana-2"
    default_wins = TURN.angle_args(dict(angle, model=None), spec,
                                   REG.get(spec["defaults"]["model"]), "subject-a",
                                   SimpleNamespace(model=None, **base))
    assert default_wins.model == spec["defaults"]["model"]


# --- angle selection --------------------------------------------------------

def test_group_and_slot_filters(spec):
    assert {s["group"] for s in TURN.select_angles(spec, "face", ())} == {"face"}
    assert [s["id"] for s in TURN.select_angles(spec, "all", ("body_back",))] == ["body_back"]
    assert len(TURN.select_angles(spec, "all", ())) == len(spec["angles"])


def test_an_unknown_slot_lists_the_real_ones(spec):
    with pytest.raises(TURN.TurnaroundError, match="face_front"):
        TURN.select_angles(spec, "all", ("no_such_slot",))


# --- against the bucket ----------------------------------------------------

def _seed_plates(fake, spec):
    """Every plate the spec names, as a node under the library's `config/`.

    Plates were shared material with no node and were seeded straight into the
    bucket; they are ordinary nodes now, which is what lets `check_angles` ask
    the catalog like everything else. `put_shared` still carries the name
    because they belong to the library rather than to any entity.
    """
    # Deduped: a torso guide is shared by several face angles, and `put_shared`
    # would otherwise make a second node with the same name in the same folder.
    for key in dict.fromkeys(k for angle in spec["angles"] for k in TURN.angle_keys(angle)):
        fake.put_shared(key, b"png-bytes")


def _seed_pool(fake, library, *names: str):
    """Put image nodes in subject-a's `seed/` pool and return their ids.

    The `library` fixture seeds references and an input pool but no seed
    photographs, because most of the suite has no use for them. A shoot does:
    seed material is what it prefers, precisely so a shoot is not driven by
    earlier model output.
    """
    seed = fake._child(library.character_root, "seed")
    return [fake.put_file(seed["id"], name, b"webp-" + name.encode())["id"]
            for name in names]


def test_missing_plates_point_at_dev_setup(library, spec):
    with pytest.raises(TURN.TurnaroundError, match="dev-setup"):
        TURN.check_angles(spec["angles"])


def test_plates_present_pass_the_check(library, spec):
    """The check asks the catalog, so a plate has to be a node to be found.

    It asked `store.exists` on a name path while plates had none, which answered
    False for every plate that was actually there — a refusal naming a script
    the user had already run. That is why this test seeds nodes rather than
    objects.
    """
    _seed_plates(library.fake, spec)
    TURN.check_angles(spec["angles"])  # no raise


def test_identity_prefers_seed_over_generated_references(library):
    seeded = _seed_pool(library.fake, library, "subject-a_1.webp")
    nodes, source = TURN.identity_nodes("subject-a", "auto", None, None)
    assert source == "seed"
    assert nodes == seeded


def test_identity_falls_back_to_references_when_seed_is_empty(library):
    nodes, source = TURN.identity_nodes("subject-b", "auto", None, None)
    assert source == "reference"
    assert nodes == [library.b_face_1]


def test_identity_seed_explicitly_refuses_to_substitute(library):
    with pytest.raises(TURN.TurnaroundError, match="seed/"):
        TURN.identity_nodes("subject-b", "seed", None, None)


def test_an_oversized_identity_pool_is_refused_not_truncated(library):
    """Sorted order is not quality order, and `[:limit]` hides that.

    One character's seed pool opens with a poster, a launch graphic, a collage
    and a wide shot of him across a room — the four worst images in it for
    carrying a face, and exactly the four a silent truncation would have sent.
    `reference/` already refuses an over-cap selection for this reason; seed now
    does too.
    """
    with pytest.raises(TURN.TurnaroundError) as exc:
        TURN.identity_nodes("subject-a", "refs", None, None, limit=1)
    assert "holds" in str(exc.value)          # says how many it found
    # And lists them BY FILENAME. A refusal that printed node ids would be
    # asking a person to choose between images they cannot tell apart, which is
    # why `_label` prefers `name` over any id.
    assert "front-neutral.webp" in str(exc.value)
    assert "three-quarter.webp" in str(exc.value)


def test_seed_pick_names_the_identity_images(library):
    first, _second = _seed_pool(library.fake, library,
                                "subject-a_1.webp", "subject-a_2.webp")
    nodes, source = TURN.identity_nodes("subject-a", "seed", None, None,
                                         limit=4, seed_pick="subject-a_1.webp")
    assert source == "seed"
    assert nodes == [first]


def test_seed_pick_rejects_a_file_that_is_not_there(library):
    _seed_pool(library.fake, library, "subject-a_1.webp")
    with pytest.raises(TURN.TurnaroundError, match="not in"):
        TURN.identity_nodes("subject-a", "seed", None, None,
                             seed_pick="nope.webp")


def test_citations_match_where_the_plate_actually_lands(library, spec):
    """`{angle_slot}` must come from the RESOLVED order, never be assumed.

    `gather` de-dupes, filters by what the model accepts and orders by category,
    so it is the only authority on where the plate ended up. This is the test
    that fails if someone hard-codes a number into a prompt.
    """
    from types import SimpleNamespace
    _seed_plates(library.fake, spec)
    seed, = _seed_pool(library.fake, library, "subject-a_1.webp")
    angle = next(s for s in spec["angles"] if s["id"] == "face_front")
    entry = REG.get(spec["defaults"]["model"])
    opts = SimpleNamespace(model=None, project=library.project, extra=None,
                           aspect_ratio=None, dry_run=True, yes=False, dest=None,
                           expires=3600, identity=[seed])
    args = TURN.angle_args(angle, spec, entry, "subject-a", opts)
    args.key = [TURN.angle_key(angle), *opts.identity]
    bindings = SUB.gather(entry, args)
    ordered = bindings[entry["images"]["refs"]]
    plate = library.fake._resolve(TURN.angle_key(angle))["id"]

    assert len(ordered) == 2, ordered
    plate_position = ordered.index(plate) + 1
    # The shoot passes the plate as its first explicit key, so it comes out
    # first — an outcome of how the keys are ordered, which is exactly why the
    # citation is read back from `ordered` rather than written into the prompt.
    assert plate_position == 1
    identity_positions = [i + 1 for i, k in enumerate(ordered) if k != plate]
    text = TURN.build_prompt(angle, spec, PROFILE, plate_position, identity_positions)
    assert f"[Image{plate_position}] is a POSE GUIDE" in text
    for n in identity_positions:
        assert f"[Image{n}]" in text.split("show the person")[0]


def test_the_run_records_the_character_it_is_of(library, spec):
    """The shoot resolves its own keys, so it passes no --character.

    `record_characters` is what keeps `runs find --character` working; without it
    a shoot's runs would be associated with nobody.
    """
    from types import SimpleNamespace
    angle = spec["angles"][0]
    opts = SimpleNamespace(model=None, project=library.project, extra=None,
                           aspect_ratio=None, dry_run=True, yes=False, dest=None,
                           expires=3600)
    args = TURN.angle_args(angle, spec, REG.get(spec["defaults"]["model"]), "subject-a", opts)
    assert args.character == ()
    assert args.record_characters == ("subject-a",)


def test_turnaround_dry_run_renders_every_angle_and_submits_nothing(library, spec, monkeypatch):
    """The approval gate: nine payloads on screen, no prediction created."""
    _seed_plates(library.fake, spec)
    entry = REG.get(spec["defaults"]["model"])
    props = {f: {} for f in ("prompt", "aspect_ratio", "output_format", "quality",
                             "moderation", entry["images"]["refs"])}
    monkeypatch.setattr("studio_pipeline.engine.schema.fetch", lambda *a, **k: (props, {}))

    # **"Must not submit", which is stronger than "must not bill".** The seam
    # used to be `adapters.replicate.create_prediction`; the CLI holds no
    # provider client now, so it is the API route the CLI would call.
    library.fake.submits_refused = True

    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser", "--dry-run"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    for angle in spec["angles"]:
        assert f"angle {angle['id']}" in result.output
    assert "nothing billed" in result.output


def test_turnaround_needs_a_project(library, spec):
    result = CliRunner().invoke(cli.main, ["character", "turnaround", "subject-a", "--dry-run"])
    assert result.exit_code != 0
    assert "project" in result.output.lower()


def test_turnaround_refuses_an_unregistered_model(library, spec):
    _seed_plates(library.fake, spec)
    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser",
        "--model", "not-a-model", "--dry-run"])
    assert result.exit_code != 0


def test_turnaround_refuses_a_video_model(library, spec):
    _seed_plates(library.fake, spec)
    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser",
        "--model", "kling", "--dry-run"])
    assert result.exit_code != 0
    assert "still" in result.output


def test_create_turnaround_refuses_the_blank_template(library):
    result = CliRunner().invoke(cli.main, [
        "character", "create", "subject-c", "--turnaround", "--project", "porch-teaser"])
    assert result.exit_code != 0
    assert "--from-profile" in result.output


# --- the crop script -------------------------------------------------------

def test_the_pose_sheet_split_is_deterministic(tmp_path):
    """Same sheet in, same boxes out — the split is measured, not hand-tuned."""
    from PIL import Image

    from scripts.split_angle_sheet import find_figures

    sheet = Image.new("L", (400, 200), color=40)
    for x0 in (20, 140, 260):                      # three figures, evenly spaced
        for x in range(x0, x0 + 60):
            for y in range(30, 170):
                sheet.putpixel((x, y), 200)
    first = find_figures(sheet)
    assert len(first) == 3
    assert find_figures(sheet) == first


# --- the human gates -------------------------------------------------------
#
# Both of these were breached in practice before they were enforced: a shoot was
# submitted on the strength of a menu answer rather than a shown payload, and its
# result was written into a character's reference library without anyone
# agreeing to that. The rules now live in the code, and here.

def test_there_is_no_flag_that_approves_spending():
    """`--yes` is gone, from `turnaround` and from `create --turnaround`.

    An approval flag is the door an agent walks through while believing some
    earlier exchange counted as approval. It has to come from the person
    reading the payload, so nothing may answer the prompt on their behalf.
    """
    import click

    from studio_pipeline import cli

    character = cli.main.get_command(None, "character")
    for name in ("turnaround", "create"):
        command = character.get_command(None, name)
        flags = {flag for p in command.params for flag in getattr(p, "opts", [])}
        assert "--yes" not in flags, f"studio character {name} can self-approve"
        assert not any(isinstance(p, click.Option) and "approve" in p.name for p in command.params)


def test_a_turnaround_never_writes_into_the_character(library, spec, monkeypatch):
    """Rendering is not the same decision as changing who a character IS.

    The turnaround leaves results in their runs. Whatever it does, the character's
    reference folder and its index must look exactly as they did before.
    """
    _seed_plates(library.fake, spec)
    entry = REG.get(spec["defaults"]["model"])
    props = {f: {} for f in ("prompt", "aspect_ratio", "output_format", "quality",
                             "moderation", entry["images"]["refs"])}
    monkeypatch.setattr("studio_pipeline.engine.schema.fetch", lambda *a, **k: (props, {}))

    from studio_pipeline.adapters import entities as E
    before_entries = E.reference_entries(library.character)
    before_profile = E.get_character(library.character)["profile"]

    CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser", "--dry-run"])

    assert E.reference_entries(library.character) == before_entries
    assert E.get_character(library.character)["profile"] == before_profile
    # And the module must not be able to: the filing helpers were removed
    # outright rather than left behind a flag.
    assert not hasattr(TURN, "file_output")
    assert not hasattr(TURN, "set_default_set")


def test_promoting_a_run_output_is_a_separate_command(library):
    """`add-refs --from-run` is the second gate, and it copies rather than moves."""
    from studio_pipeline.adapters import entities as E

    before = {e["node"] for e in E.reference_entries(library.character)}
    result = CliRunner().invoke(cli.main, [
        "character", "add-refs", "subject-a", "--to", "face",
        "--from-run", "porch-teaser/latest#1"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"

    added = {e["node"] for e in E.reference_entries(library.character)} - before
    assert len(added) == 1, added
    # A copy, not a move: the run still owns its output, and the promoted node
    # is a different one. Every record that cited the run's output still does.
    assert added != {library.run_output}
    assert E.get_run(library.run)["outputs"][0]["node"] == library.run_output


def test_pick_and_seed_pick_combine_into_one_identity_set(library):
    """Naming references used to silence --seed-pick outright.

    That made the safer choice inexpressible: curated reference frames give
    clean, consistent angles, and a couple of seed photographs anchor them to
    the real source so a shoot is not driven purely by earlier model output.
    The two pools now concatenate, references first, in the order named.
    """
    seed, = _seed_pool(library.fake, library, "subject-a_1.webp")
    nodes, source = TURN.identity_nodes(
        "subject-a", "auto",
        "front-neutral.webp", None, limit=4, seed_pick="subject-a_1")
    assert source == "reference+seed"
    # References first, in the order named, then the seed picks — the ordering
    # is what the prompt's `[ImageN]` citations are read against.
    assert nodes == [library.face_1, seed]


def test_combining_pools_still_respects_the_cap(library):
    """The combined set is what is checked, not each pool separately."""
    _seed_pool(library.fake, library, "subject-a_1.webp")
    with pytest.raises(TURN.TurnaroundError) as exc:
        TURN.identity_nodes(
            "subject-a", "auto",
            "front-neutral.webp", None, limit=1, seed_pick="subject-a_1")
    assert "--identity-max" in str(exc.value)


def test_promoting_a_shot_run_carries_the_specs_description_and_tags(library, spec):
    """The spec's `description`/`tags` were dead data for a while.

    `turnaround` stopped filing its own output once promotion became a separate
    human gate, and `add-refs` had no idea which angle a run came from — so both
    fields sat in the repo unread and every promotion retyped them by hand.
    Fourteen descriptions were copied out of this file twice before it was
    noticed. The angle id now rides in the run record and is read back here.
    """
    from studio_pipeline.adapters import entities as E

    angle = next(s for s in spec["angles"] if s["id"] == "face_front")
    # The angle rides on the run record, which is where `turnaround` puts it.
    library.fake.runs[library.run].setdefault("extra", {})["reference_angle"] = "face_front"

    before = {e["node"] for e in E.reference_entries(library.character)}
    result = CliRunner().invoke(cli.main, [
        "character", "add-refs", "subject-a", "--to", "face",
        "--from-run", "porch-teaser/latest#1"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"

    entries = E.reference_entries(library.character)
    added = [e for e in entries if e["node"] not in before]
    assert added, entries
    assert added[-1]["description"] == " ".join(angle["description"].split())
    assert added[-1]["tags"] == list(angle["tags"])


def test_a_run_recorded_before_the_rename_still_promotes_described(library, spec):
    """Runs made before the rename wrote `reference_slot`, and they are in prod.

    The field was renamed with the concept; the records were not, and cannot be
    without rewriting production run rows. So the read accepts both spellings.
    Dropping the old one would silently un-describe every image rendered before
    the rename — the exact failure the lookup exists to prevent, reintroduced by
    the fix for it.
    """
    from studio_pipeline.adapters import entities as E

    angle = next(s for s in spec["angles"] if s["id"] == "face_front")
    library.fake.runs[library.run].setdefault("extra", {})["reference_slot"] = "face_front"

    before = {e["node"] for e in E.reference_entries(library.character)}
    result = CliRunner().invoke(cli.main, [
        "character", "add-refs", "subject-a", "--to", "face",
        "--from-run", "porch-teaser/latest#1"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"

    added = [e for e in E.reference_entries(library.character) if e["node"] not in before]
    assert added, "the run did not promote at all"
    assert added[-1]["description"] == " ".join(angle["description"].split())
    assert added[-1]["tags"] == list(angle["tags"])


def test_promoting_a_run_that_was_not_shot_leaves_it_undescribed(library):
    """Provenance is a bonus, never a requirement: a run with no angle recorded
    must still promote, and must not borrow some other angle's description."""
    from studio_pipeline.adapters import entities as E

    before = {e["node"] for e in E.reference_entries(library.character)}
    result = CliRunner().invoke(cli.main, [
        "character", "add-refs", "subject-a", "--to", "face",
        "--from-run", "porch-teaser/latest#1"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    added = [e for e in E.reference_entries(library.character) if e["node"] not in before]
    assert added and not (added[-1].get("description") or "").strip()


def test_a_turnaround_records_the_slot_each_run_came_from(spec):
    """The seam the promotion above depends on, asserted at the source."""
    args = TURN.angle_args(spec["angles"][0], spec, REG.get(spec["defaults"]["model"]),
                           "subject-a", SimpleNamespace(
                               model=None, project="p", extra=None, aspect_ratio=None,
                               dry_run=True, dest=None, expires=3600))
    assert args.record_extra == {"reference_angle": spec["angles"][0]["id"]}


def test_add_refs_with_nothing_to_add_says_so(library):
    result = CliRunner().invoke(cli.main, ["character", "add-refs", "subject-a", "--to", "face"])
    assert result.exit_code != 0
    assert "--from-run" in result.output


# --- style comes from the character, not from this repo --------------------

def test_style_is_taken_from_the_bible_not_hardcoded(spec):
    """A character drawn in ink must not be rendered as a photograph.

    The spec used to assert "photographic, no stylisation" for every angle, which
    silently converted a pen-and-ink character into a medium he has never
    existed in — and fought the reference images passed alongside.
    """
    angle = spec["angles"][0]
    ink = dict(PROFILE, rendering={"default_style": "Vintage ink comic — pen-and-ink"})
    photo = dict(PROFILE, rendering={"default_style": "Realistic"})
    assert "pen-and-ink" in TURN.build_prompt(angle, spec, ink, 1, [2])
    assert "Realistic" in TURN.build_prompt(angle, spec, photo, 1, [2])
    assert "photographic" not in TURN.build_prompt(angle, spec, ink, 1, [2]).lower()


def test_no_slot_prompt_hardcodes_a_medium(spec):
    for angle in spec["angles"]:
        assert "photograph" not in angle["prompt"].lower(), angle["id"]


def test_style_falls_back_when_a_bible_names_none(spec):
    angle = spec["angles"][0]
    text = TURN.build_prompt(angle, spec, dict(PROFILE, rendering={}), 1, [2])
    assert "same medium" in text.lower()


# --- seeing what is sent ---------------------------------------------------

def test_review_sheet_labels_images_in_the_order_the_model_gets_them(library, spec, tmp_path):
    """A payload names its images; a name is not a look.

    Captions must be `[ImageN]` in binding order, so the sheet and the prompt's
    citations can be read against each other — the sheet is worthless if it
    natural-sorts the tiles the way a pool listing would.
    """
    from PIL import Image
    Image.new("RGB", (40, 60), "grey").save(tmp_path / "src.png")
    png = (tmp_path / "src.png").read_bytes()

    plate = library.fake.put_shared("config/angle/face/front.png", png)["id"]
    seed = library.fake._child(library.character_root, "seed")
    photo = library.fake.put_file(seed["id"], "subject-a_1.png", png)["id"]

    out = TURN.review_sheet("face_front", [plate, photo], str(tmp_path / "sheet"), {})
    assert os.path.isfile(out)
    assert out.endswith("face_front.png")


def test_review_sheet_downloads_each_image_once(library, spec, tmp_path):
    """Identity images repeat across angles; the cache is what stops re-fetching."""
    from PIL import Image
    Image.new("RGB", (40, 60), "grey").save(tmp_path / "src.png")
    seed = library.fake._child(library.character_root, "seed")
    node = library.fake.put_file(seed["id"], "subject-a_1.png",
                                 (tmp_path / "src.png").read_bytes())["id"]

    cache: dict = {}
    TURN.review_sheet("a", [node], str(tmp_path / "s"), cache)
    first = dict(cache)
    TURN.review_sheet("b", [node], str(tmp_path / "s"), cache)
    assert cache == first, "the second angle re-downloaded an image it already had"


def test_contact_sheet_still_sorts_and_labels_by_name_without_captions(tmp_path):
    """The browsing caller is unchanged by the review caller's needs."""
    from PIL import Image

    from studio_pipeline.domain import contact_sheet as SHEET
    paths = []
    for n in (10, 2):
        p = tmp_path / f"subject-a_{n}.png"
        Image.new("RGB", (30, 30), "grey").save(p)
        paths.append(str(p))
    out = SHEET.build(paths, str(tmp_path / "sheet.png"), cols=2, cell=60, quiet=True)
    assert os.path.isfile(out)


# --- the image budget ------------------------------------------------------

def test_a_start_frame_counts_toward_the_total_image_cap():
    """One model caps TOTAL images, not just the reference list.

    Kling advertises `reference_images` "up to 7" and separately allows a start
    frame beside them, which reads as 7 + 1 and is not — the prediction fails
    outright with error 1201. It bites hardest with a character whose
    `default_set` holds exactly seven, the shape a shoot produces, because
    binding that plus a start frame is over by exactly one.
    """
    entry = REG.get("kling")
    images = entry["images"]
    assert images.get("start_counts_toward_max_refs"), "the registry must record this"
    cap = images["max_refs"]

    over = {images["refs"]: [f"k{i}" for i in range(cap)], images["start"]: "start"}
    with pytest.raises(SUB.SubmitError) as exc:
        SUB._check_image_budget(entry, over)
    assert "IN TOTAL" in str(exc.value)
    assert "--pick" in str(exc.value), "the error must name the fix"

    # Exactly at the cap, and a bare reference set, both pass.
    SUB._check_image_budget(entry, {images["refs"]: [f"k{i}" for i in range(cap - 1)],
                                    images["start"]: "start"})
    SUB._check_image_budget(entry, {images["refs"]: [f"k{i}" for i in range(cap)]})


def test_models_without_the_flag_are_unaffected():
    """The rule is registry-driven, not named per model: an image model with no
    such cap must not start refusing reference sets."""
    entry = REG.get("gpt-image-2")
    field = entry["images"]["refs"]
    SUB._check_image_budget(entry, {field: [f"k{i}" for i in range(12)]})


def test_a_start_frame_is_format_checked_like_every_other_image(library, monkeypatch):
    """The rule used to live inside the reference-list branch, so a `.webp`
    start frame reached a model that rejects `.webp` and failed at the provider
    — after the submit, and in the provider's words rather than ones that name
    `studio convert`. A start frame is the commonest thing to hand straight from
    an image run, which is exactly where `.webp` comes from.
    """
    entry = REG.get("kling")
    images = entry["images"]
    # `gather` sizes whatever it bound, to warn about an oversized payload.
    # These keys are invented, so the sizing is stubbed out rather than sent —
    # not because it may not run, but because it is a different subject and has
    # its own tests in `test_board`. This used to be a `None` s3 client passed
    # positionally, which turned a test's need into a production parameter.
    monkeypatch.setattr("studio_pipeline.adapters.store.size", lambda _node: 0)
    args = SimpleNamespace(
        start_key=library.input_1, start_run=None,
        end_key=None, end_run=None, image_run=None, character=(), ref_run=(),
        input_=(), input=(), key=[], pick=None, pick_tag=None, slots=None,
        project=library.project, no_refs=True,
    )
    with pytest.raises(SUB.SubmitError) as exc:
        SUB.gather(entry, args)
    assert ".webp" in str(exc.value)
    assert "studio convert" in str(exc.value), "the error must name the fix"

    # A legal start frame, with no references at all, still passes. The pool
    # holds a `.png` for exactly this: the video engines reject `.webp`.
    args.start_key = library.input_3
    assert SUB.gather(entry, args)[images["start"]] == library.input_3


# --- the plates, as provisioning actually creates them ----------------------

def test_a_turnaround_finds_the_plates_that_config_sync_pushed(library, spec, monkeypatch):
    """**The gap between the check and the thing that fills the library.**

    `check_angles` resolves each plate as a name path, so a plate needs a node.
    Nothing gave it one: `dev-shared-material.sh` pushed the plates in with
    `aws s3 sync` — correct while they were addressed by raw key — and the
    backend named a `config` folder constant that no route ever called. So a
    freshly provisioned stack refused every shoot with "angle image(s) missing",
    naming the script that had just run.

    It went unnoticed because this suite's own fixture creates plates as nodes,
    which made the fake more correct than provisioning. This test closes that by
    filling the library the way `studio config sync` does and then asking the
    shoot, rather than seeding nodes by hand.
    """
    from studio_pipeline.objects import config_sync

    monkeypatch.setattr(config_sync, "local_angle_images",
                        lambda: [(TURN.angle_key(angle), "/dev/null")
                                 for angle in spec["angles"]])
    monkeypatch.setattr(config_sync.store, "upload",
                        lambda path, _src, **kw: library.fake.put_shared(path, b"png-bytes"))

    assert config_sync.missing(config_sync.local_angle_images()), "nothing to push — the test is hollow"
    result = CliRunner().invoke(cli.main, ["config", "sync", "--apply"])
    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"

    TURN.check_angles(spec["angles"])          # the refusal this existed to stop
    assert not config_sync.missing(config_sync.local_angle_images())


def test_config_sync_is_a_dry_run_without_apply(library, spec, monkeypatch):
    from studio_pipeline.objects import config_sync

    monkeypatch.setattr(config_sync, "local_angle_images",
                        lambda: [(TURN.angle_key(spec["angles"][0]), "/dev/null")])
    result = CliRunner().invoke(cli.main, ["config", "sync"])
    assert result.exit_code == 0
    assert "--apply" in result.output
    with pytest.raises(TURN.TurnaroundError, match="dev-setup"):
        TURN.check_angles(spec["angles"])
