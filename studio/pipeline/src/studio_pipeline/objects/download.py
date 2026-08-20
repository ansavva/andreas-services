"""List or download objects from the media tree, through the studio API.

  studio download --folder <name>/reference --list
  studio download --folder <name>/reference --all --dest /tmp/refs --json
  studio download --folder <name>/output clip.mp4 --dest .

--list prints the object basenames under <folder>/. --all downloads them
all to --dest; NAME... downloads specific basenames. --json emits machine output
(a list for --list, a {name: local_path} map for downloads).
"""
import json
import pathlib

import click

from studio_pipeline.adapters import api, store


@click.command(help=__doc__, epilog="\n\nArguments:\n  NAMES  Specific basenames to download (default: see --list/--all).")
@click.argument("names", nargs=-1)
@click.option("--all", "all_", is_flag=True, help="Download every object under the folder.")
@click.option("--dest", default='.', help="Local directory to download into (default: cwd).")
@click.option("--folder", required=True, help="Key prefix (e.g. characters/<name>/reference).")
@click.option("--json", "json_", is_flag=True, help="Emit JSON instead of text.")
@click.option("--list", "list_", is_flag=True, help="List basenames under the folder; download nothing.")
def download(names, all_, dest, folder, json_, list_):
    folder = folder.strip("/")
    try:
        entries = store.children(folder)
    except api.NotFound as error:
        raise click.ClickException(f"no such folder: {folder}") from error
    available = sorted(
        (entry["name"] for entry in entries if entry.get("kind") == "file"),
        key=store.natural_key,
    )

    if list_ or (not all_ and not names):
        print(json.dumps(available, indent=2) if json_ else "\n".join(available))
        return

    if all_:
        wanted = available
    else:
        missing = [n for n in names if n not in available]
        if missing:
            raise click.ClickException(f"not found under {folder}/: {', '.join(missing)}")
        wanted = list(names)

    destination = pathlib.Path(dest)
    destination.mkdir(parents=True, exist_ok=True)
    out = {}
    for name in wanted:
        local = store.download(f"{folder}/{name}", destination / name)
        out[name] = str(local.resolve())

    if json_:
        print(json.dumps(out, indent=2))
    else:
        for name, local in out.items():
            print(f"{name}  ->  {local}")
