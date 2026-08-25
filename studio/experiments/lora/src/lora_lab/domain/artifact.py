"""Store the winning LoRA in the character's library.

`studio character add-to <slug> corpus <file>` — the corpus pool, because it
is the sanctioned home for files that belong to a character but are not
references; a `models/` folder needs CLI folder support that does not exist
yet (phase 2). The upload rides a 300s presigned PUT, so a slow uplink can
time out — in that case the checkpoint simply stays local, which costs
nothing while nothing in studio can consume a LoRA anyway.
"""

import pathlib
import subprocess

import click

from lora_lab import studio_bin


def store(slug: str, checkpoint: pathlib.Path) -> None:
    if not checkpoint.is_file():
        raise click.ClickException(f"{checkpoint} does not exist")
    size_mb = checkpoint.stat().st_size / 1e6
    click.echo(f"uploading {checkpoint.name} ({size_mb:.0f} MB) into {slug}'s corpus pool…")
    proc = subprocess.run([studio_bin(), "character", "add-to", slug, "corpus", str(checkpoint)])
    if proc.returncode != 0:
        raise click.ClickException(
            "upload failed — a 300s PUT window on a slow uplink is the usual cause. "
            "The checkpoint is still safe locally; keeping it there is fine for the experiment."
        )
    click.echo("stored.")
