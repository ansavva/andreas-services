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
import os

import click

from studio_pipeline.adapters import s3 as s3c


@click.command(help=__doc__, epilog="\n\nArguments:\n  NAMES  With --folder: specific basenames (default: all in the folder).")
@click.argument("names", nargs=-1)
@click.option("--expires", type=int, default=3600, help="Expiry in seconds (default 3600).")
@click.option("--folder", help="Key prefix (e.g. characters/<name>/reference).")
@click.option("--json", "json_", is_flag=True, help="Emit JSON [{key,url}] instead of one URL per line.")
@click.option("--key", help="An exact key (e.g. projects/<p>/runs/<id>/output/clip.mp4).")
def presign(names, expires, folder, json_, key):
    if not folder and not key:
        s3c.die("pass --folder <path> or --key <path>.")

    s3 = s3c.client()

    if key:
        keys = [s3c.key(key)]
    else:
        folder = folder.strip("/")
        all_keys = s3c.list_keys(s3, folder)
        if names:
            by_name = {os.path.basename(k): k for k in all_keys}
            missing = [n for n in names if n not in by_name]
            if missing:
                s3c.die(f"not found under {folder}/: {', '.join(missing)}")
            keys = [by_name[n] for n in names]
        else:
            keys = all_keys
        if not keys:
            s3c.die(f"no objects under {folder}/")

    results = [
        {
            "key": k,
            "url": s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": s3c.BUCKET, "Key": k},
                ExpiresIn=expires,
            ),
        }
        for k in keys
    ]

    if json_:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(r["url"])
