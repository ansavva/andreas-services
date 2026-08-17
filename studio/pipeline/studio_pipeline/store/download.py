"""List or download objects from the media tree of the
xharness-prod-media-us-east-1 bucket.

  uv run .../s3_download.py --folder <name>/reference --list
  uv run .../s3_download.py --folder <name>/reference --all --dest /tmp/refs --json
  uv run .../s3_download.py --folder <name>/output clip.mp4 --dest .

--list prints the object basenames under <folder>/. --all downloads them
all to --dest; NAME... downloads specific basenames. --json emits machine output
(a list for --list, a {name: local_path} map for downloads).
"""
import argparse
import json
import os

from studio_pipeline.store import s3 as s3c  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--folder", required=True, help="Key prefix (e.g. characters/<name>/reference).")
    ap.add_argument("names", nargs="*", help="Specific basenames to download (default: see --list/--all).")
    ap.add_argument("--list", action="store_true", help="List basenames under the folder; download nothing.")
    ap.add_argument("--all", action="store_true", help="Download every object under the folder.")
    ap.add_argument("--dest", default=".", help="Local directory to download into (default: cwd).")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = ap.parse_args()

    s3 = s3c.client()
    folder = args.folder.strip("/")
    keys = s3c.list_keys(s3, folder)
    by_name = {os.path.basename(k): k for k in keys}

    if args.list or (not args.all and not args.names):
        names = sorted(by_name, key=s3c.natural_key)
        print(json.dumps(names, indent=2) if args.json else "\n".join(names))
        return

    if args.all:
        wanted = sorted(by_name, key=s3c.natural_key)
    else:
        wanted = args.names
        missing = [n for n in wanted if n not in by_name]
        if missing:
            s3c.die(f"not found under {folder}/: {', '.join(missing)}")

    os.makedirs(args.dest, exist_ok=True)
    out = {}
    for name in wanted:
        local = os.path.join(args.dest, name)
        s3.download_file(s3c.BUCKET, by_name[name], local)
        out[name] = os.path.abspath(local)

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for name, local in out.items():
            print(f"{name}  ->  {local}")


if __name__ == "__main__":
    main()
