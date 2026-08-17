"""List or download objects from the media tree of the
xharness-prod-media-us-east-1 bucket.

  studio download --folder <name>/reference --list
  studio download --folder <name>/reference --all --dest /tmp/refs --json
  studio download --folder <name>/output clip.mp4 --dest .

--list prints the object basenames under <folder>/. --all downloads them
all to --dest; NAME... downloads specific basenames. --json emits machine output
(a list for --list, a {name: local_path} map for downloads).
"""
import json
import os

import click

from studio_pipeline.adapters import s3 as s3c


@click.command(help=__doc__, epilog="\n\nArguments:\n  NAMES  Specific basenames to download (default: see --list/--all).")
@click.argument("names", nargs=-1)
@click.option("--all", "all_", is_flag=True, help="Download every object under the folder.")
@click.option("--dest", default='.', help="Local directory to download into (default: cwd).")
@click.option("--folder", required=True, help="Key prefix (e.g. characters/<name>/reference).")
@click.option("--json", "json_", is_flag=True, help="Emit JSON instead of text.")
@click.option("--list", "list_", is_flag=True, help="List basenames under the folder; download nothing.")
def download(names, all_, dest, folder, json_, list_):
    s3 = s3c.client()
    folder = folder.strip("/")
    keys = s3c.list_keys(s3, folder)
    by_name = {os.path.basename(k): k for k in keys}

    if list_ or (not all_ and not names):
        names = sorted(by_name, key=s3c.natural_key)
        print(json.dumps(names, indent=2) if json_ else "\n".join(names))
        return

    if all_:
        wanted = sorted(by_name, key=s3c.natural_key)
    else:
        wanted = names
        missing = [n for n in wanted if n not in by_name]
        if missing:
            s3c.die(f"not found under {folder}/: {', '.join(missing)}")

    os.makedirs(dest, exist_ok=True)
    out = {}
    for name in wanted:
        local = os.path.join(dest, name)
        s3.download_file(s3c.BUCKET, by_name[name], local)
        out[name] = os.path.abspath(local)

    if json_:
        print(json.dumps(out, indent=2))
    else:
        for name, local in out.items():
            print(f"{name}  ->  {local}")
