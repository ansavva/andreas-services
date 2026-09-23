"""Upload local file(s) into the media tree.

  studio upload --folder proj-<uuid>/input frame.png
  studio upload --folder char-<uuid>/reference/face img/*.webp --presign --json

**This names no bucket, deliberately.** It used to say
`studio-prod-media-us-east-1` in this docstring, which was two things at once: a
bucket name in prose that would rot, and an instruction pointing local work at
production. It goes through `adapters/store` and the API now — which mints the
catalog row and the presigned PUT together — so the bucket is whatever the API
is configured with, prod or this machine's dev stack.

Each file lands at `<folder>/<basename>` (same-named keys are overwritten; the
prod bucket is versioned so prior revisions are retained). The folder is created
if it does not exist, missing ancestors included — but never an entity: a leading
`char-<uuid>`, `loc-<uuid>` or `proj-<uuid>` resolves to that record's root, and one
naming no entity is an error. Prints the path per file; --presign also prints a
temporary HTTPS URL.
"""
import json
import mimetypes
import pathlib

import click

from studio_pipeline.adapters import store

# mimetypes doesn't know some media types on every platform; pin the ones we use.
# The same pins the API keeps, and for the same two reasons: a type the platform
# has never heard of is stored `application/octet-stream`, and two of the audio
# ones a Mac DOES know it knows by their pre-standard names — `audio/x-wav`,
# `audio/mp4a-latm` — the second of which Safari will not play. A voice sample
# uploaded from here and the same file uploaded through the app have to land
# under one type, or a character's take plays in the browser and its twin does
# not.
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/aac", ".aac")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".ogg")


def content_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


@click.command(help=__doc__, epilog="\n\nArguments:\n  FILES  Local file(s) to upload.")
@click.argument("files", nargs=-1, required=True)
@click.option("--folder", required=True, help="Destination name path from the library root (e.g. char-<uuid>/seed, proj-<uuid>/input).")
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
