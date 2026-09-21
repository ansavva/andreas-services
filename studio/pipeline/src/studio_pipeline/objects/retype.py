"""`studio retype` — give every image and clip in the library the content
type its extension says, where its row says something else. The backfill.

A file's `content_type` is what the app decides by — the run feed offers
*Copy into a character or location…* only on an `image/*` — and it was
written at ingest off the filename through a MIME table that, on the
Lambda, had no `.webp`. Every `.webp` output landed `application/octet-stream`
and lost the button. Outputs are typed by what the provider served now; this
is for everything stored before that, once per library:

    studio --profile prod retype

Done by the time it answers, not queued: a retype is one server-side copy
onto the same key and one row write, and only rows that need it are touched.
Same bytes, same node, same checksum. Safe to repeat — a row already typed
is passed over.
"""
import json

import click

from studio_pipeline.adapters import api, entities


@click.command(help=__doc__)
@click.option("--json", "json_", is_flag=True, help="Emit the report as JSON.")
def retype(json_):
    try:
        report = entities.sweep_content_types()
    except api.ApiError as error:
        raise click.ClickException(str(error)) from error
    if json_:
        print(json.dumps(report, indent=2))
        return
    print(f"{len(report['retyped'])} files retyped, {report['skipped']} already right")
    if report.get("truncated"):
        print("The walk stopped at the library's cap; run this again to reach the rest.")
