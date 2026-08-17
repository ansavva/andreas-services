"""Generate temporary HTTPS URLs for objects in the media tree.

This is how S3-hosted images/videos reach Replicate/Seedance: a short-lived
presigned GET URL that Replicate fetches during the job. The bucket stays
private; no credentials are exposed.

  # every reference image, in <name>_1..<name>_N order -> [Image1]..[ImageN]
  uv run .../s3_presign.py --folder <name>/reference --json

  # specific objects under a folder
  uv run .../s3_presign.py --folder <name>/reference <name>_1.webp <name>_2.webp

  # one exact key
  uv run .../s3_presign.py --key <name>/output/clip.mp4
"""
import json
import os

from studio_pipeline.store import s3 as s3c  # noqa: E402
from types import SimpleNamespace

import click


@click.command(help=__doc__, epilog="\n\nArguments:\n  NAMES  With --folder: specific basenames (default: all in the folder).")
@click.argument("names", nargs=-1)
@click.option("--expires", type=int, default=3600, help="Expiry in seconds (default 3600).")
@click.option("--folder", help="Key prefix (e.g. characters/<name>/reference).")
@click.option("--json", "json_", is_flag=True, help="Emit JSON [{key,url}] instead of one URL per line.")
@click.option("--key", help="An exact key (e.g. projects/<p>/runs/<id>/output/clip.mp4).")
def main(names, expires, folder, json_, key):
    return _run(SimpleNamespace(names=names, expires=expires, folder=folder, json=json_, key=key))


def _run(args):

    if not args.folder and not args.key:
        s3c.die("pass --folder <path> or --key <path>.")

    s3 = s3c.client()

    if args.key:
        keys = [s3c.key(args.key)]
    else:
        folder = args.folder.strip("/")
        all_keys = s3c.list_keys(s3, folder)
        if args.names:
            by_name = {os.path.basename(k): k for k in all_keys}
            missing = [n for n in args.names if n not in by_name]
            if missing:
                s3c.die(f"not found under {folder}/: {', '.join(missing)}")
            keys = [by_name[n] for n in args.names]
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
                ExpiresIn=args.expires,
            ),
        }
        for k in keys
    ]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(r["url"])


if __name__ == "__main__":
    main()
