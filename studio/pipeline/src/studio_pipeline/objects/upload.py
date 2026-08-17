"""Upload local file(s) into the media tree of the
xharness-prod-media-us-east-1 bucket.

  studio upload --folder <name>/output output/<name>/clip.mp4
  studio upload --folder <name>/reference img/*.webp --presign --json

Each file goes to  s3://<bucket>/<folder>/<basename>  (same-named keys are
overwritten; the bucket is versioned so prior revisions are retained). Prints the
s3:// URI per file; --presign also prints a temporary HTTPS URL.
"""
import json
import mimetypes
import os

import click

from studio_pipeline.adapters import s3 as s3c

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
def upload(files, expires, folder, json_, presign):
    s3 = s3c.client()
    folder = folder.strip("/")
    results = []
    for path in files:
        if not os.path.isfile(path):
            s3c.die(f"not a file: {path}")
        name = os.path.basename(path)
        key = s3c.key(f"{folder}/{name}")
        s3.upload_file(path, s3c.BUCKET, key, ExtraArgs={"ContentType": content_type(path)})
        entry = {"name": name, "key": key, "uri": f"s3://{s3c.BUCKET}/{key}"}
        if presign:
            entry["url"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": s3c.BUCKET, "Key": key},
                ExpiresIn=expires,
            )
        results.append(entry)

    if json_:
        print(json.dumps(results, indent=2))
    else:
        for e in results:
            print(e["uri"])
            if "url" in e:
                print(f"  {e['url']}")
