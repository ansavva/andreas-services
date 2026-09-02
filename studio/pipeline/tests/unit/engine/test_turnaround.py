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

import os
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from studio_pipeline import STUDIO_DIR, cli
from studio_pipeline.adapters import store
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


















































# --- the prompt ------------------------------------------------------------

PROFILE = {
    "wardrobe": {"tops": [{"item": "Short-sleeve polo shirt", "detail": "with embroidery"}]},
    "consistency": {"must": ["A long straight nose", "Dressed — polo or tee"]},
    "text_identity_block": "A compact man in his forties.",
}










# --- the invariant the feature rests on ------------------------------------







# --- the model override ----------------------------------------------------









# --- angle selection --------------------------------------------------------





# --- against the bucket ----------------------------------------------------





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


def _seed_subfolder(fake, library, folder: str, *names: str):
    """Put image nodes one level down in `seed/<folder>/` and return their ids.

    A seed pool is a tree as soon as anyone files it — `original/`, `restored/`,
    a folder per age. `_seed_pool` builds the loose-in-the-root case; this
    builds the filed one, which is what a shoot could not see.
    """
    seed = fake._child(library.character_root, "seed")
    child = fake._create_node(seed["id"], folder, "folder")
    return [fake.put_file(child["id"], name, b"webp-" + name.encode())["id"]
            for name in names]






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


def test_seed_identity_sees_files_filed_in_subfolders(library):
    """A filed seed photograph was absent from the pool, not refused.

    `_seed_nodes` read the pool ROOT, so tidying `seed/` into subfolders removed
    every photograph in them from a shoot's view — silently, which is worse than
    an error: the shoot went on resolving identity from whatever was still loose
    in the root and reported nothing wrong.
    """
    loose, = _seed_pool(library.fake, library, "subject-a_1.webp")
    filed = _seed_subfolder(library.fake, library, "restored",
                            "subject-a_9.webp")
    nodes, source = TURN.identity_nodes("subject-a", "seed", None, None, limit=4)
    assert source == "seed"
    assert set(nodes) == {loose, *filed}


def test_seed_pick_names_a_file_by_its_subfolder_path(library):
    _seed_pool(library.fake, library, "subject-a_1.webp")
    filed, = _seed_subfolder(library.fake, library, "restored",
                             "subject-a_9.webp")
    nodes, _ = TURN.identity_nodes("subject-a", "seed", None, None, limit=4,
                                    seed_pick="restored/subject-a_9.webp")
    assert nodes == [filed]


def test_seed_pick_takes_a_subfolder_file_by_bare_name_when_unambiguous(library):
    """The path is the unambiguous spelling; a bare name still works alone.

    A person reading `character pool <name> seed --group restored` types what
    they see, and refusing that when exactly one file answers to it would be
    pedantry rather than safety.
    """
    filed, = _seed_subfolder(library.fake, library, "restored",
                             "subject-a_9.webp")
    nodes, _ = TURN.identity_nodes("subject-a", "seed", None, None, limit=4,
                                    seed_pick="subject-a_9")
    assert nodes == [filed]


def test_seed_pick_refuses_a_basename_two_folders_share(library):
    """Sort order must not decide which photograph carries an identity.

    Two folders holding a `front.webp` is ordinary — an original and its
    restoration keep the same name. Resolving to whichever the walk reached
    first would pick one silently, which is the mistake `_too_many` exists to
    prevent one level up.
    """
    _seed_subfolder(library.fake, library, "original", "front.webp")
    _seed_subfolder(library.fake, library, "restored", "front.webp")
    with pytest.raises(TURN.TurnaroundError) as exc:
        TURN.identity_nodes("subject-a", "seed", None, None, limit=4,
                             seed_pick="front.webp")
    assert "original/front.webp" in str(exc.value)
    assert "restored/front.webp" in str(exc.value)


def test_an_oversized_seed_pool_lists_files_by_their_path(library):
    """A refusal a person cannot type back is not a choice.

    `_label` prints the pool-relative path for seed entries so the names in the
    listing are exactly the ones `--seed-pick` accepts.
    """
    _seed_pool(library.fake, library, "subject-a_1.webp")
    _seed_subfolder(library.fake, library, "restored",
                    "subject-a_9.webp", "subject-a_10.webp")
    with pytest.raises(TURN.TurnaroundError) as exc:
        TURN.identity_nodes("subject-a", "seed", None, None, limit=2)
    assert "restored/subject-a_9.webp" in str(exc.value)
    assert "subject-a_1.webp" in str(exc.value)










def test_app_origin_drops_the_api_label(monkeypatch):
    monkeypatch.setattr("studio_pipeline.adapters.auth.api_url",
                        lambda: "https://studio-api.andreas.services")
    assert TURN.app_origin() == "https://studio.andreas.services"


def test_app_origin_is_none_for_a_host_that_is_not_that_shape(monkeypatch):
    """A dev API on localhost has no app at a guessable port.

    The caller prints bare run ids then, which is what `runs show` and
    `runs approve` take anyway — a wrong link is worse than no link.
    """
    monkeypatch.setattr("studio_pipeline.adapters.auth.api_url",
                        lambda: "http://localhost:8000")
    assert TURN.app_origin() is None








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








def test_the_browsing_caller_still_natural_sorts_where_the_review_caller_does_not():
    """The browsing caller is unchanged by the review caller's needs.

    Two orders, one layout engine. A pool listing wants `_2` before `_10`, which
    is `natural_key`; a payload review wants the binding order left alone,
    because tile N is what the prompt cites as `[ImageN]`. `SHEET.build` is in
    the render worker's image now, so the sorting rule is asserted where it lives
    — `backend/tests/unit/test_media.py`. What is still this package's is which
    of the two it asks for, and `contact-sheet` asks by handing captions off the
    natural-sorted pool walk.
    """
    names = ["subject-a_10.png", "subject-a_2.png"]
    assert sorted(names, key=store.natural_key) == \
        ["subject-a_2.png", "subject-a_10.png"]


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





# ─────────────── against the API, where the spec now lives ───────────────
#
# WHAT THESE REPLACED, AND WHAT IS SIMPLY GONE.
#
# Fifty-seven tests here asserted the CONTENTS of
# `domain/templates/reference_angles.yaml` — that every face angle stated its
# crop, that opposite angles faced opposite ways, that no character name had
# leaked into the prose. That file no longer exists: the spec is rows a stack
# holds and a person edits, so those are assertions about DATA and there is no
# data in the repo to assert them against.
#
# **That is a real loss and it is not covered anywhere yet.** The name-leak
# check in particular was hard rule #1 enforced mechanically, and the spec is
# now editable from a browser. The right home for them is a `studio spec lint`
# that runs against a stack rather than a file; until that exists, nothing
# checks a block for a character's name.
#
# What survives here is what still has a subject: which images carry identity
# (the judgement the route deliberately refuses to make), and the wiring
# between this command and the route.


def _spec_in(fake, angle_id="face_front", group="face"):
    fake.spec_blocks["face_only"] = "Take the face from the reference images."
    fake.spec_angles[angle_id] = {
        "id": angle_id, "group": group,
        "prompt": "A studio portrait. {face_only}",
        "description": "Head and shoulders.", "tags": [group], "order": 1000,
    }


def test_the_cli_sends_the_identity_it_resolved_and_lets_the_api_assemble(library):
    """The division of labour, asserted at the seam.

    Which photographs carry identity is resolved HERE — it is the one judgement
    the route refuses to make. Everything downstream of that, the prompt
    included, is the API's, so the CLI must send node ids and nothing about
    wording.
    """
    _spec_in(library.fake)
    seeded = _seed_pool(library.fake, library, "subject-a_1.webp")
    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    sent = library.fake.turnarounds[-1]
    assert sent["identity"] == seeded
    assert "prompt" not in sent and "blocks" not in sent


def test_a_dry_run_previews_and_records_nothing(library):
    _spec_in(library.fake)
    _seed_pool(library.fake, library, "subject-a_1.webp")
    before = len(library.fake.runs)
    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser", "--dry-run"])

    assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
    assert library.fake.turnarounds[-1]["preview"] is True
    assert len(library.fake.runs) == before
    assert "nothing recorded" in result.output


def test_the_payload_shown_is_the_one_the_api_assembled(library):
    """Rendered from the plan that came back, never assembled a second time.

    Two assemblies are two chances to differ, and the one that matters is the
    one the row holds. Hard rule #2 is about approving what will actually be
    sent.
    """
    _spec_in(library.fake)
    _seed_pool(library.fake, library, "subject-a_1.webp")
    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser", "--dry-run"])

    assert "PROMPT" in result.output and "INPUT" in result.output
    assert "Take the face from the reference images." in result.output


def test_a_group_filter_reaches_the_route_rather_than_being_applied_here(library):
    _spec_in(library.fake, "body_front", "body")
    _seed_pool(library.fake, library, "subject-a_1.webp")
    CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser",
        "--group", "body", "--dry-run"])
    assert library.fake.turnarounds[-1]["group"] == "body"


def test_all_is_not_sent_as_a_group(library):
    """`--group all` is this CLI's word for "no filter", not a group the API has.

    Sending it would ask the route for angles whose group is the literal string
    `all`, which is none of them — an empty turnaround reported as a success.
    """
    _spec_in(library.fake)
    _seed_pool(library.fake, library, "subject-a_1.webp")
    CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser", "--dry-run"])
    assert "group" not in library.fake.turnarounds[-1]


def test_an_angle_the_route_refused_is_reported_and_fails_the_command(library):
    _spec_in(library.fake)
    _seed_pool(library.fake, library, "subject-a_1.webp")
    library.fake.turnaround_failures = [{"angle": "face_front", "error": "no such block"}]
    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser"])

    assert result.exit_code == 1
    assert "NOT DRAFTED" in result.output and "no such block" in result.output


def test_extra_and_aspect_ratio_travel_together_as_model_inputs(library):
    _spec_in(library.fake)
    _seed_pool(library.fake, library, "subject-a_1.webp")
    CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser",
        "--extra", '{"moderation": "low"}', "--aspect-ratio", "3:4", "--dry-run"])
    assert library.fake.turnarounds[-1]["extra"] == {"moderation": "low",
                                                     "aspect_ratio": "3:4"}


def test_malformed_extra_is_refused_before_anything_is_asked_for(library):
    _spec_in(library.fake)
    _seed_pool(library.fake, library, "subject-a_1.webp")
    result = CliRunner().invoke(cli.main, [
        "character", "turnaround", "subject-a", "--project", "porch-teaser",
        "--extra", "not json"])
    assert result.exit_code != 0
    assert not library.fake.turnarounds



