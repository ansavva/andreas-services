"""`studio posters` — queue a poster for every image and video in the library
that has none. The backfill.

A tile draws a file's poster, a small still the render worker makes — off a
clip's first frame, or a still scaled down to 640 across — and without one it
draws the file itself: a 0.4 MB JPEG per output at best, a phone photo or a
multi-megabyte PNG at worst, ten of them a run. New files get a poster as they
land; this is for everything stored before the service did that, and for a
stack whose queue was down when it did. Idempotent — a file already covered is
passed over — so it is safe to run as often as wanted, once per library:

    studio --profile prod posters

Queued, not awaited: the worker makes them in the background and the tiles
pick them up on the next listing. `runs posters <project>` is the older,
narrower sweep — the clips one project's runs produced — and this covers it.
"""
import json

import click

from studio_pipeline.adapters import api, entities


@click.command(help=__doc__)
@click.option("--json", "json_", is_flag=True, help="Emit the report as JSON.")
def posters(json_):
    try:
        report = entities.sweep_posters()
    except api.ApiError as error:
        raise click.ClickException(str(error)) from error
    if json_:
        print(json.dumps(report, indent=2))
        return
    print(f"{len(report['queued'])} posters queued, {report['skipped']} files already covered")
    if report.get("truncated"):
        print("The walk stopped at the library's cap; run this again once the "
              "worker has caught up to reach the rest.")
