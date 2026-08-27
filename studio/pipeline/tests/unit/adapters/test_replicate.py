"""`adapters/replicate.py` — the whole billing surface, and how a test avoids it.

Nothing here opens a socket, which is the point: the suite-wide guards these
tests describe are the reason every OTHER test in the tree cannot bill either.
"""
from __future__ import annotations

import pathlib

import pytest

from studio_pipeline.adapters import replicate as RA
from studio_pipeline.engine import registry as REG


# ── the switch ──────────────────────────────────────────────────────────────


def test_live_is_the_default_when_nothing_is_set(monkeypatch):
    """**The direction of the default is the whole safety argument.**

    `fake` is set by `conftest.py` and by nothing else, so an ordinary shell
    gets `live` and `studio run` bills exactly as it always did. A default of
    `fake` would mean a real job silently rendering a placeholder.
    """
    monkeypatch.setattr(RA, "env_value", lambda _name: None)
    assert RA.mode() == RA.LIVE


def test_an_unrecognised_mode_is_refused_rather_than_guessed(monkeypatch):
    """Neither fallback is safe: to `live` a typo becomes a bill, to `fake` it
    becomes a job that never rendered."""
    monkeypatch.setattr(RA, "env_value", lambda _name: "fak")
    with pytest.raises(RA.ReplicateError, match="STUDIO_REPLICATE_MODE"):
        RA.mode()


def test_the_suite_runs_in_fake_mode():
    """Asserted directly, because everything below is only true if it holds."""
    assert RA.mode() == RA.FAKE


def test_fake_mode_needs_no_provider_token(monkeypatch):
    """A missing `REPLICATE_API_TOKEN` is not an error offline."""
    monkeypatch.setattr(RA, "env_value",
                        lambda name: "fake" if name == "STUDIO_REPLICATE_MODE" else None)
    assert RA.load_token()


# ── what the fake answers ───────────────────────────────────────────────────


def test_a_prediction_id_is_derived_from_what_was_asked_for():
    """Deterministic, so a run journal diffs and a test can assert on the id."""
    first = RA.create_prediction("google/nano-banana-pro", {"prompt": "a"}, "t")
    same = RA.create_prediction("google/nano-banana-pro", {"prompt": "a"}, "t")
    other = RA.create_prediction("google/nano-banana-pro", {"prompt": "b"}, "t")

    assert first["id"] == same["id"] != other["id"]
    assert first["status"] == "starting"


def test_polling_settles_immediately_and_never_sleeps():
    settled = RA.poll("fakeabc", "t", interval=30, timeout=600)
    assert settled["status"] == "succeeded"
    assert settled["output"] == ["https://fake.invalid/fakeabc/0.png"]


def test_the_output_host_is_reserved_so_a_live_download_cannot_reach_anyone():
    """RFC 2606 reserves `.invalid`. A fake output URL fetched in `live` mode
    fails DNS immediately instead of resolving to somebody's server."""
    assert RA.poll("x", "t", 1, 1)["output"][0].startswith("https://fake.invalid/")


def test_a_downloaded_image_is_a_real_decodable_file(tmp_path):
    """Not magic bytes. The pipeline hashes outputs, reads their dimensions and
    builds contact sheets from them, and a PNG header with zeros after it fails
    all of that in ways that look like pipeline bugs."""
    from PIL import Image

    dest = tmp_path / "out.png"
    RA.download("https://fake.invalid/x/0.png", str(dest))

    with Image.open(dest) as image:
        assert image.format == "PNG"
        assert image.size == (512, 512)


def test_a_canned_output_directory_wins_over_the_generated_one(tmp_path, monkeypatch):
    """The escape hatch for the one thing the fake will not invent — a real clip."""
    canned = tmp_path / "canned"
    canned.mkdir()
    (canned / "output.mp4").write_bytes(b"a-real-clip")
    monkeypatch.setenv(RA.FAKE_DIR_VAR, str(canned))

    dest = tmp_path / "out.mp4"
    RA.download("https://fake.invalid/x/0.mp4", str(dest))
    assert dest.read_bytes() == b"a-real-clip"


def test_the_fake_says_so_on_every_call(capsys):
    """A `fake` left on has to be obvious inside one command."""
    RA.create_prediction("google/nano-banana-pro", {"prompt": "a"}, "t")
    assert "[replicate:FAKE]" in capsys.readouterr().err


# ── the backstops ───────────────────────────────────────────────────────────


def test_a_test_cannot_open_a_socket_to_the_outside():
    """The guard a config switch cannot be.

    `STUDIO_REPLICATE_MODE` only fakes calls that go through this module. It
    says nothing about a paid call reached indirectly — through an adapter, a
    dependency, or a subprocess — and `test_dev_seed`'s source scan admits the
    same blind spot about itself. This closes it at the socket.
    """
    import socket

    with pytest.raises(RuntimeError, match="tried to open a socket"):
        socket.socket().connect(("api.replicate.com", 443))


def test_the_committed_registry_is_never_the_one_a_test_writes():
    """`studio models refresh` rewrites `models.json` in place, and
    `test_every_subcommand_dispatches` invokes every leaf command there is.

    It only ever survived because the schema fetch went to the network and got
    a 401 — the suite depended on a live provider call FAILING. When the fake
    made it succeed with an empty body, the refresh wrote an empty snapshot over
    every model and deleted 391 lines of hand-verified schema.
    """
    assert pathlib.Path(REG.PATH).name == "models.json"
    assert "studio_pipeline/engine" not in REG.PATH.replace("\\", "/")
