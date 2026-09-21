"""`studio retype` — the library-wide content-type backfill, over the fake API."""

from __future__ import annotations

import json

from click.testing import CliRunner

from studio_pipeline import cli


def _run(*argv):
    return CliRunner().invoke(cli.main, list(argv))


def test_retype_fixes_every_mistyped_picture_once(library, fake_api):
    # The fixture's pictures are typed; one `.webp` beside them stored the
    # way a MIME table without `.webp` stored it, and one clip typed right.
    folder = next(n for n in fake_api.nodes.values() if n.get("kind") == "folder"
                  and n.get("parent_id"))
    wrong = fake_api.put_file(folder["id"], "image.webp", b"webp", "application/octet-stream")
    fake_api.put_file(folder["id"], "take-01.mp4", b"fake clip", "video/mp4")

    first = _run("retype", "--json")
    assert first.exit_code == 0, first.output
    assert json.loads(first.output)["retyped"] == [wrong["id"]]
    assert wrong["content_type"] == "image/webp"

    again = _run("retype")
    assert again.exit_code == 0, again.output
    assert again.output.startswith("0 files retyped")
