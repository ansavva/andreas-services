"""`studio character rename` — the one command that moves a whole record.

A rename touches three things that are easy to get individually right and hard
to keep in step: the objects, the bible that indexes them, and the records that
cite them. Each test here is one of the ways that went wrong by hand before the
command existed.
"""

import json

import pytest
from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.domain import rewrite
from tests.conftest import BUCKET

OLD, NEW = "subject-a", "subject-c"

# Richer than the shared fixture's bible: a rename has to carry `display_name`,
# `default_set` and a non-reference pool index, and the shared one has none of
# them. Written here rather than into conftest so the other suites keep the
# miniature they were written against.
BIBLE = """\
schema_version: 1
name: subject-a
display_name: Subject A
references:
- file: face/subject-a_1.webp
  description: front, neutral
  tags: [face]
- file: face/subject-a_2.webp
  description: three-quarter
  tags: [face, profile]
- file: body/subject-a_1.webp
  description: full length
  tags: [body]
corpus:
- file: subject-a_in_4.png
  description: a collected still
  tags: [scene]
default_set:
- face/subject-a_1.webp
- body/subject-a_1.webp
text_identity_block: A person, described in prose that mentions no filename.
"""

# A run that cites a reference image by key. Nothing in the shared fixture does,
# and the citing records are exactly what a rename strands.
CITING_RUN = "projects/subject-a/runs/2026-08-05_09-00-00_ref-shot/request.json"


@pytest.fixture
def bucket(media_bucket):
    """The miniature tree, with a full bible and a record that cites a ref."""
    media_bucket.put_object(Bucket=BUCKET, Key=f"characters/{OLD}/profile.yaml",
                            Body=BIBLE.encode())
    media_bucket.put_object(Bucket=BUCKET, Key=CITING_RUN, Body=json.dumps({
        "model": "nano-banana-pro",
        "characters": [OLD],
        "bindings": {"image_input": [f"characters/{OLD}/reference/face/{OLD}_1.webp"]},
    }).encode())
    # An undescribed reference image: in the folder, absent from the index.
    media_bucket.put_object(Bucket=BUCKET,
                            Key=f"characters/{OLD}/reference/face/{OLD}_in_9.webp",
                            Body=b"webp-bytes")
    return media_bucket


def run(*argv):
    result = CliRunner().invoke(cli.main, ["character", "rename", *argv])
    return result


def keys_under(s3, prefix):
    got = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return sorted(o["Key"] for o in got.get("Contents", []))


def profile(s3, name):
    import yaml
    body = s3.get_object(Bucket=BUCKET, Key=f"characters/{name}/profile.yaml")["Body"]
    return yaml.safe_load(body.read())


def doc(s3, key):
    return json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())


# ── the dry run ─────────────────────────────────────────────────────────────

def test_dry_run_changes_nothing(bucket):
    before = keys_under(bucket, "characters/")
    result = run(OLD, NEW)
    assert result.exit_code == 0, result.output
    assert "WOULD RENAME" in result.output
    assert "DRY RUN" in result.output
    assert keys_under(bucket, "characters/") == before
    assert doc(bucket, "projects/subject-a/project.json")["characters"] == [OLD]


# ── the objects ─────────────────────────────────────────────────────────────

def test_apply_moves_every_object_and_renames_basenames(bucket):
    before = keys_under(bucket, f"characters/{OLD}/")
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert keys_under(bucket, f"characters/{OLD}/") == []
    after = keys_under(bucket, f"characters/{NEW}/")
    assert len(after) == len(before)
    assert f"characters/{NEW}/reference/face/{NEW}_1.webp" in after
    assert f"characters/{NEW}/seed/{NEW}_1.webp" in after
    assert f"characters/{NEW}/archive/{NEW}_9.webp" in after


def test_a_basename_without_the_slug_is_left_alone(bucket):
    """`corpus/` keeps upload basenames — renaming one throws away what it recorded."""
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert f"characters/{NEW}/corpus/IMG_1966_Original.JPG" in keys_under(
        bucket, f"characters/{NEW}/corpus/")


def test_a_folder_marker_survives(bucket):
    """A zero-byte marker is a folder the app shows; dropping one deletes it."""
    bucket.put_object(Bucket=BUCKET, Key=f"characters/{OLD}/favourites/", Body=b"")
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert f"characters/{NEW}/favourites/" in keys_under(bucket, f"characters/{NEW}/")


# ── the bible ───────────────────────────────────────────────────────────────

def test_the_bible_follows(bucket):
    assert run(OLD, NEW, "--apply").exit_code == 0
    data = profile(bucket, NEW)
    assert data["name"] == NEW
    assert data["display_name"] == "Subject C"
    assert [e["file"] for e in data["references"]] == [
        f"face/{NEW}_1.webp", f"face/{NEW}_2.webp", f"body/{NEW}_1.webp"]
    assert data["default_set"] == [f"face/{NEW}_1.webp", f"body/{NEW}_1.webp"]
    assert data["corpus"][0]["file"] == f"{NEW}_in_4.png"
    # Descriptions survive the move — they are what an index is for.
    assert data["references"][0]["description"] == "front, neutral"


def test_display_name_can_be_given(bucket):
    assert run(OLD, NEW, "--display-name", "Someone Else", "--apply").exit_code == 0
    assert profile(bucket, NEW)["display_name"] == "Someone Else"


def test_prose_is_not_rewritten(bucket):
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert profile(bucket, NEW)["text_identity_block"].startswith("A person")


def test_an_undescribed_image_moves_but_does_not_enter_the_index(bucket):
    """`sync-refs` is a separate decision; a rename must not make it silently."""
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert f"characters/{NEW}/reference/face/{NEW}_in_9.webp" in keys_under(
        bucket, f"characters/{NEW}/reference/")
    assert len(profile(bucket, NEW)["references"]) == 3


# ── the records ─────────────────────────────────────────────────────────────

def test_a_record_citing_a_reference_key_follows(bucket):
    assert run(OLD, NEW, "--apply").exit_code == 0
    moved = CITING_RUN
    assert doc(bucket, moved)["bindings"]["image_input"] == [
        f"characters/{NEW}/reference/face/{NEW}_1.webp"]


def test_the_character_name_follows_into_every_record(bucket):
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert doc(bucket, CITING_RUN)["characters"] == [NEW]
    assert doc(bucket, "projects/subject-a/project.json")["characters"] == [NEW]
    scene = doc(bucket, "projects/subject-a/scenes/board-test/scene.json")
    assert scene["characters"] == [NEW]
    assert scene["shots"][0]["panels"][0]["references"]["characters"] == [NEW]


def test_a_project_sharing_the_name_is_not_renamed(bucket):
    """The reason the name pass cannot ride along with the key mapping."""
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert doc(bucket, "projects/subject-a/project.json")["project"] == "subject-a"
    scene = doc(bucket, "projects/subject-a/scenes/board-test/scene.json")
    assert scene["project"] == "subject-a"
    assert scene["scene"] == "subject-a/board-test"


def test_no_record_dangles_afterwards(bucket):
    assert run(OLD, NEW, "--apply").exit_code == 0
    assert rewrite.check(bucket)["dangling"] == []


# ── the refusals ────────────────────────────────────────────────────────────

def test_refuses_an_existing_destination(bucket):
    result = run(OLD, "subject-b", "--apply")
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert keys_under(bucket, f"characters/{OLD}/") != []


def test_refuses_an_unknown_character(bucket):
    result = run("nobody", NEW, "--apply")
    assert result.exit_code != 0
    assert "no character" in result.output


def test_refuses_a_no_op(bucket):
    result = run(OLD, OLD, "--apply")
    assert result.exit_code != 0
    assert "same name" in result.output
