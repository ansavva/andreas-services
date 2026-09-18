"""`studio posters` — the library-wide backfill, over the fake API.

One call, and the fake answers the way the real route does: every image and
video without a poster is queued, everything else is passed over, and a second
sweep finds nothing left. What is under test is the command layer — that it
calls the sweep once and says what came back.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from studio_pipeline import cli


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def test_posters_queues_every_uncovered_picture_once(library, fake_api):
    media = [n for n in fake_api.nodes.values()
             if n.get("kind") == "file" and fake_api._entry_kind(n) in fake_api.MEDIA_KINDS]
    assert media, "the fixture holds pictures"

    first = _run("posters", "--json")
    assert first.exit_code == 0, first.output
    report = json.loads(first.output)
    assert sorted(report["queued"]) == sorted(n["id"] for n in media)

    again = _run("posters")
    assert again.exit_code == 0, again.output
    assert again.output.startswith("0 posters queued")


def test_posters_says_how_many(library):
    result = _run("posters")
    assert result.exit_code == 0, result.output
    assert " posters queued, " in result.output
    assert "already covered" in result.output
