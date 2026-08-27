"""`studio catalog confirm-outputs` — the repair for the uploads that never confirmed.

The command exists because `store.upload_to_url` PUT an entity's output and
stopped, leaving every run, scene and movie output a placeholder: bytes in S3, a
row with no `size`, and `browse.is_abandoned_upload` keeping it out of every
listing and out of the reel. 170 of them in prod.

What these tests hold it to: it finds the hidden rows without being able to list
them, it repairs only what is genuinely unconfirmed, it is idempotent, and it
never invents a size for bytes that are not there.
"""
from __future__ import annotations

from click.testing import CliRunner

from studio_pipeline import cli
from studio_pipeline.adapters import entities as E
from studio_pipeline.adapters import store
from tests.support.fake_api import BUCKET


def _run(*args):
    return CliRunner().invoke(cli.main, ["catalog", "confirm-outputs", *args])


def _unconfirmed(fake, run_id: str, name: str = "stranded.png") -> str:
    """An output exactly as the broken `upload_to_url` left it: bytes, no confirm."""
    signed = E.add_run_output(run_id, name, 4, "image/png")
    fake.s3.put_object(Bucket=BUCKET,
                       Key=signed["url"].removeprefix("memory://"), Body=b"png!")
    return signed["node"]


def test_a_dry_run_finds_the_rows_no_listing_can_show(library, fake_api):
    """**The defect is that these are hidden, so discovery cannot use a listing.**

    It walks the entities that NAME their outputs instead — which is also the
    narrower question, because a genuinely abandoned browser upload is a
    placeholder that should stay hidden and no entity names one.
    """
    node = _unconfirmed(fake_api, library.run)

    result = _run()

    assert result.exit_code == 0
    assert "1 already confirmed, 1 unconfirmed" in result.output
    assert node in result.output
    # Nothing written: still a placeholder, still hidden.
    assert "size" not in store.node(node)


def test_apply_confirms_and_the_size_comes_from_s3(library, fake_api):
    """The length is read off the object, never off what the client once claimed."""
    node = _unconfirmed(fake_api, library.run)

    result = _run("--apply")

    assert result.exit_code == 0
    assert "1 repaired" in result.output
    record = store.node(node)
    assert record["size"] == 4
    assert record["content_type"] == "image/png"


def test_it_leaves_an_already_confirmed_output_alone(library):
    """The fixture's own output is confirmed, so a clean library is a no-op.

    Says "nothing to do" rather than reporting a repair — a command whose report
    cannot tell the two apart is one nobody can use to check their work. The
    node's recorded size is asserted unchanged, so a "repair" that rewrote a
    healthy row would fail here rather than passing quietly.
    """
    before = store.node(library.run_output)["size"]

    result = _run("--apply")

    assert result.exit_code == 0
    assert "every output that still exists is confirmed" in result.output
    assert store.node(library.run_output)["size"] == before


def test_a_second_apply_reports_nothing_left(library, fake_api):
    """Idempotent, which is what makes it safe to run again after a partial failure."""
    _unconfirmed(fake_api, library.run)
    _run("--apply")

    result = _run("--apply")

    assert "every output that still exists is confirmed" in result.output


def test_an_output_with_no_bytes_is_reported_rather_than_invented(library):
    """**The one state worse than the bug**: a row promising bytes that are absent.

    `confirm-upload` heads the object first, so this cannot be repaired with a
    plausible size — it is reported as an upload that genuinely failed, which is
    the case where the media really is gone and a re-run is the only fix.
    """
    # Signed but never PUT: the node exists, the object does not.
    E.add_run_output(library.run, "never-arrived.png", 4, "image/png")

    result = _run("--apply")

    assert "no object behind the key" in result.output
    assert "0 repaired, 1 with no bytes behind them" in result.output


def test_a_scene_output_is_found_too(library, fake_api):
    """Runs are where the damage is; scenes and movies took the same code path.

    Prod holds no scene yet, so this is the only place the scene half of the walk
    is exercised at all — and it is the half that would otherwise rot unnoticed
    until the first scene was cut.
    """
    scene = E.create_scene(project=library.project, slug="porch", title="Porch")
    signed = E.scene_output(scene["id"], "porch.mp4", 4, "video/mp4")
    fake_api.s3.put_object(Bucket=BUCKET,
                           Key=signed["url"].removeprefix("memory://"), Body=b"mp4!")
    E.patch_scene(scene["id"], output={"node": signed["node"]})

    result = _run("--apply")

    assert "scene output" in result.output
    assert store.node(signed["node"])["size"] == 4
