"""Upload local file(s) into the media tree of the
studio-prod-media-us-east-1 bucket.

  studio upload --folder <name>/output output/<name>/clip.mp4
  studio upload --folder <name>/reference img/*.webp --presign --json

Each file goes to  s3://<bucket>/<folder>/<basename>  (same-named keys are
overwritten; the bucket is versioned so prior revisions are retained). Prints the
s3:// URI per file; --presign also prints a temporary HTTPS URL.
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
@click.option("--expires", type=int, default=3600, help="Presign expiry in seconds (default 3600).")
@click.option("--folder", required=True, help="Destination key prefix (e.g. characters/<name>/seed).")
@click.option("--json", "json_", is_flag=True, help="Emit a JSON list instead of text.")
@click.option("--presign", is_flag=True, help="Also emit a temporary HTTPS URL per file.")
def upload(files, expires, folder, json_, presign):
    _warn_ignored_expiry(expires)
    folder = folder.strip("/")
    results = []
    for path in files:
        source = pathlib.Path(path)
        if not source.is_file():
            raise click.ClickException(f"not a file: {path}")
        remote = f"{folder}/{source.name}"
        node = store.upload(remote, source, content_type=content_type(path))
        # `key` rather than `path`, because two SKILL.md pages document that
        # field by name. It holds the same string it always did. #406 renames it
        # when it rewrites those pages; changing it here would make them wrong
        # first and right later.
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


def _warn_ignored_expiry(expires: int) -> None:
    """See the note in `objects/presign.py` — the API owns the URL's lifetime."""
    context = click.get_current_context(silent=True)
    if context is None:
        return
    source = context.get_parameter_source("expires")
    if source is not None and source.name != "DEFAULT":
        click.echo(
            f"warning: --expires {expires} is ignored; the API sets the URL's lifetime.",
            err=True,
        )
