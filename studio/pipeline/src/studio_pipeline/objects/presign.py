"""Generate temporary HTTPS URLs for objects in the media tree.

This is how S3-hosted images/videos reach Replicate/Seedance: a short-lived
presigned GET URL that Replicate fetches during the job. The bucket stays
private; no credentials are exposed.

  # every reference image, in <name>_1..<name>_N order -> [Image1]..[ImageN]
  studio presign --folder <name>/reference --json

  # specific objects under a folder
  studio presign --folder <name>/reference <name>_1.webp <name>_2.webp

  # one exact key
  studio presign --key <name>/output/clip.mp4
"""
import json

import click

from studio_pipeline.adapters import api, store


@click.command(help=__doc__, epilog="\n\nArguments:\n  NAMES  With --folder: specific basenames (default: all in the folder).")
@click.argument("names", nargs=-1)
@click.option("--folder", help="Key prefix (e.g. characters/<name>/reference).")
@click.option("--json", "json_", is_flag=True, help="Emit JSON [{key,url}] instead of one URL per line.")
@click.option("--key", help="An exact key (e.g. projects/<p>/runs/<id>/output/clip.mp4).")
def presign(names, folder, json_, key):
    if not folder and not key:
        raise click.ClickException("pass --folder <path> or --key <path>.")

    if key:
        paths = [key.strip("/")]
    else:
        folder = folder.strip("/")
        # Natural order, not the API's — `store.files` owns that decision and
        # why it matters. This is the call site it matters most at: these URLs
        # become `[Image1]..[ImageN]` positionally.
        available = [entry["name"] for entry in store.files(folder)]
        if names:
            missing = [n for n in names if n not in available]
            if missing:
                raise click.ClickException(f"not found under {folder}/: {', '.join(missing)}")
            chosen = list(names)
        else:
            chosen = available
        if not chosen:
            raise click.ClickException(f"no objects under {folder}/")
        paths = [f"{folder}/{name}" for name in chosen]

    try:
        results = [{"key": path, "url": store.presign(path)} for path in paths]
    except api.NotFound as error:
        raise click.ClickException(str(error)) from error

    if json_:
        print(json.dumps(results, indent=2))
    else:
        for entry in results:
            print(entry["url"])
