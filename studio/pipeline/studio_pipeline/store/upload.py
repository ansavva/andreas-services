"""Upload local file(s) into the media tree of the
xharness-prod-media-us-east-1 bucket.

  uv run .../s3_upload.py --folder <name>/output output/<name>/clip.mp4
  uv run .../s3_upload.py --folder <name>/reference img/*.webp --presign --json

Each file goes to  s3://<bucket>/<folder>/<basename>  (same-named keys are
overwritten; the bucket is versioned so prior revisions are retained). Prints the
s3:// URI per file; --presign also prints a temporary HTTPS URL.
"""
import json
import mimetypes
import os

from studio_pipeline.store import s3 as s3c  # noqa: E402
from types import SimpleNamespace

import click

# mimetypes doesn't know some media types on every platform; pin the ones we use.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/mp4", ".mp4")


def content_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


@click.command(help=__doc__, epilog="\n\nArguments:\n  FILES  Local file(s) to upload.")
@click.argument("files", nargs=-1, required=True)
@click.option("--expires", type=int, default=3600, help="Presign expiry in seconds (default 3600).")
@click.option("--folder", required=True, help="Destination key prefix (e.g. characters/<name>/seed).")
@click.option("--json", "json_", is_flag=True, help="Emit a JSON list instead of text.")
@click.option("--presign", is_flag=True, help="Also emit a temporary HTTPS URL per file.")
def main(files, expires, folder, json_, presign):
    return _run(SimpleNamespace(files=files, expires=expires, folder=folder, json=json_, presign=presign))


def _run(args):

    s3 = s3c.client()
    folder = args.folder.strip("/")
    results = []
    for path in args.files:
        if not os.path.isfile(path):
            s3c.die(f"not a file: {path}")
        name = os.path.basename(path)
        key = s3c.key(f"{folder}/{name}")
        s3.upload_file(path, s3c.BUCKET, key, ExtraArgs={"ContentType": content_type(path)})
        entry = {"name": name, "key": key, "uri": f"s3://{s3c.BUCKET}/{key}"}
        if args.presign:
            entry["url"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": s3c.BUCKET, "Key": key},
                ExpiresIn=args.expires,
            )
        results.append(entry)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for e in results:
            print(e["uri"])
            if "url" in e:
                print(f"  {e['url']}")


if __name__ == "__main__":
    main()
