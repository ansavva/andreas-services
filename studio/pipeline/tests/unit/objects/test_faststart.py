"""`studio faststart` — the library-wide clip backfill, over the fake API."""

from __future__ import annotations

import json

from click.testing import CliRunner

from studio_pipeline import cli


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def test_faststart_queues_every_unmarked_clip_once(library, fake_api):
    # The fixture holds pictures only; two clips beside them, one already marked.
    folder = next(n for n in fake_api.nodes.values() if n.get("kind") == "folder"
                  and n.get("parent_id"))
    clip = fake_api.put_file(folder["id"], "take-01.mp4", b"fake clip")
    done = fake_api.put_file(folder["id"], "take-02.mp4", b"fake clip")
    done["faststart"] = True
    clips = [clip]

    first = _run("faststart", "--json")
    assert first.exit_code == 0, first.output
    assert sorted(json.loads(first.output)["queued"]) == sorted(n["id"] for n in clips)

    again = _run("faststart")
    assert again.exit_code == 0, again.output
    assert again.output.startswith("0 clips queued")
