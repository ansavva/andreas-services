"""List or download objects from the media tree, through the studio API.

  studio download --folder char-<uuid>/reference --list
  studio download --folder char-<uuid>/seed --all --dest /tmp/seed --json
  studio download --folder proj-<uuid>/runs/<run_id>/output clip.mp4 --dest .

--folder is a NAME PATH walked from the library root, and an entity's root
folder is named by its ID, not its name: a character's pool is
`char-<uuid>/<pool>`, a project's folder is `proj-<uuid>/<folder>`.
`studio character show <name>` and `studio projects show <project>` print the
ids. `<name>/<pool>` resolves nothing. `studio runs outputs <run>` takes a
run reference and prints (or presigns) its output nodes without any of this.

--list prints the file basenames under <folder>/ (subfolders are left out).
--all downloads them all to --dest; NAME... downloads specific basenames.
--json emits machine output (a list for --list, a {name: local_path} map for
downloads).
"""
import json
import pathlib

import click

from studio_pipeline.adapters import api, store


@click.command(help=__doc__, epilog="\n\nArguments:\n  NAMES  Specific basenames to download (default: see --list/--all).")
@click.argument("names", nargs=-1)
@click.option("--all", "all_", is_flag=True, help="Download every object under the folder.")
@click.option("--dest", default='.', help="Local directory to download into (default: cwd).")
@click.option("--folder", required=True, help="Name path from the library root (e.g. char-<uuid>/reference, proj-<uuid>/input).")
@click.option("--json", "json_", is_flag=True, help="Emit JSON instead of text.")
@click.option("--list", "list_", is_flag=True, help="List basenames under the folder; download nothing.")
def download(names, all_, dest, folder, json_, list_):
    folder = folder.strip("/")
    try:
        entries = store.children(folder)
    except api.NotFound as error:
        raise click.ClickException(f"no such folder: {folder}") from error
    # `_is_file`, not `kind == "file"`: the listing's `kind` says what a file
    # HOLDS (`image`, `video`, …), so the equality matched nothing and `--list`
    # printed an empty line for a folder full of images.
    available = sorted(
        (entry["name"] for entry in entries if store._is_file(entry)),
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
