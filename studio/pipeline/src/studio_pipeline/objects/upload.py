"""Upload local file(s) into the media tree.

  studio upload --folder <name>/output output/<name>/clip.mp4
  studio upload --folder <name>/reference img/*.webp --presign --json

**This names no bucket, deliberately.** It used to say
`studio-prod-media-us-east-1` in this docstring, which was two things at once: a
bucket name in prose that would rot, and an instruction pointing local work at
production. It goes through `adapters/store` and the API now — which mints the
catalog row and the presigned PUT together — so the bucket is whatever the API
is configured with, prod or this machine's dev stack.

Each file lands at `<folder>/<basename>` (same-named keys are overwritten; the
prod bucket is versioned so prior revisions are retained). The folder is created
if it does not exist, missing ancestors included. Prints the path per file;
--presign also prints a temporary HTTPS URL.
"""
import json
import mimetypes
import pathlib

import click

from studio_pipeline.adapters import store

# mimetypes doesn't know some media types on every platform; pin the ones we use.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/mp4", ".mp4")


def content_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


@click.command(help=__doc__, epilog="\n\nArguments:\n  FILES  Local file(s) to upload.")
@click.argument("files", nargs=-1, required=True)
@click.option("--folder", required=True, help="Destination key prefix (e.g. characters/<name>/seed).")
@click.option("--json", "json_", is_flag=True, help="Emit a JSON list instead of text.")
@click.option("--presign", is_flag=True, help="Also emit a temporary HTTPS URL per file.")
def upload(files, folder, json_, presign):
    folder = folder.strip("/")
    # **Ensure the destination, as `convert --dest-key` already does.** Folders
    # were free in S3 — a key with slashes in it produced the appearance of one
    # — and are catalog rows now, so a write into a folder nothing has created
    # yet failed on a missing parent with `no such object: <folder>`. Two
    # commands write into the same tree and only one of them ensured, which made
    # organising a pool into subfolders a dead end: there was no command that
    # created one, and the documented workaround was a dry-run `curate dedupe
    # --group <name>` run purely for the folder it makes on the way past.
    store.folder(folder)
    results = []
    for path in files:
        source = pathlib.Path(path)
        if not source.is_file():
            raise click.ClickException(f"not a file: {path}")
        remote = f"{folder}/{source.name}"
        node = store.upload(remote, source, content_type=content_type(path))
        # `key` rather than `path`, because two SKILL.md pages document that
        # field by name — `studio-media-character` and `studio-media-seedance`
        # both print `{"key": …, "url": …}`. It holds the same string it always
        # did, which is a name path. Renaming it is its own change and has to
        # edit those two pages in the same commit.
        entry = {"name": source.name, "key": remote, "id": node.get("id", "")}
        if presign:
            entry["url"] = store.presign(remote)
        results.append(entry)

    if json_:
        print(json.dumps(results, indent=2))
    else:
        for entry in results:
            # The `s3://bucket/key` line is gone: the CLI no longer knows a
            # bucket, and printing one it had guessed would be worse than
            # printing the path it actually wrote.
            print(entry["key"])
            if "url" in entry:
                print(f"  {entry['url']}")
