"""`studio faststart` — index every clip in the library for the browser.

A provider writes an MP4 with its index (`moov`) LAST, so a browser cannot
start the clip — hover preview, autoplay, the lightbox — until it has all of
it. Outputs are re-ordered as they land and uploads as they are confirmed;
this is for every clip stored before that, once per library:

    studio --profile prod faststart

The work runs on the render worker, in-region: a clip already in order costs
it a few bytes of ranged reads and a mark, one that is not is rewritten in
place — same bytes, same node, `moov` first. Marked rows are skipped on the
next sweep, so it is cheap to repeat. `runs faststart <project>` is the older
sweep: one project's run outputs, rewritten by the API, synchronously.
"""
import json

import click

from studio_pipeline.adapters import api, entities


@click.command(help=__doc__)
@click.option("--json", "json_", is_flag=True, help="Emit the report as JSON.")
def faststart(json_):
    try:
        report = entities.sweep_faststart()
    except api.ApiError as error:
        raise click.ClickException(str(error)) from error
    if json_:
        print(json.dumps(report, indent=2))
        return
    print(f"{len(report['queued'])} clips queued, {report['skipped']} files already checked")
    if report.get("truncated"):
        print("The walk stopped at the library's cap; run this again once the "
              "worker has caught up to reach the rest.")
