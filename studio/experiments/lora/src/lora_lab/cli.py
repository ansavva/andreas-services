"""`lora-lab` — the character-LoRA experiment, one command per runbook phase.

Wiring only, like studio_pipeline/cli.py: every command body lives in the
domain module that owns it. RUNBOOK.md is the protocol; this is its tooling.
"""

import pathlib

import click

from lora_lab.domain import artifact as _artifact
from lora_lab.domain import generate as _generate
from lora_lab.domain import pod as _pod
from lora_lab.domain import refs as _refs
from lora_lab.domain import train as _train
from lora_lab.domain import volume as _volume


@click.group()
def cli() -> None:
    """Character-LoRA experiment lab. Read RUNBOOK.md first."""


def main() -> None:
    """Entry point: adapter failures print as one line, not a traceback."""
    from lora_lab.adapters.comfy import ComfyError
    from lora_lab.adapters.runpod import RunPodError
    from lora_lab.adapters.shell import ShellError

    try:
        cli()
    except (RunPodError, ShellError, ComfyError) as error:
        raise SystemExit(f"error: {error}")


@cli.group()
def pod() -> None:
    """RunPod lifecycle: up, verify, status, down."""


@pod.command("up")
@click.option("--gpu", default="4090", show_default=True,
              help="4090 | a5000 | a6000, or a raw RunPod gpuTypeId.")
def pod_up(gpu: str) -> None:
    """Rent a Secure Cloud pod (confirms before billing starts)."""
    _pod.up(gpu)


@pod.command("verify")
def pod_verify() -> None:
    """Health check + privacy audit: ssh, volume mount, ComfyUI, /weights contents."""
    _pod.verify()


@pod.command("status")
def pod_status() -> None:
    """Pod state, volume mount, ComfyUI health."""
    _pod.status()


@pod.command("down")
def pod_down() -> None:
    """TERMINATE the pod (confirms; the disk is destroyed — the volume survives)."""
    _pod.down()


@cli.group()
def volume() -> None:
    """The persistent /weights network volume: up, status, down."""


@volume.command("up")
@click.option("--dc", required=True,
              help="RunPod datacenter id (e.g. US-KS-2). Every future pod is rented "
                   "here — pick one the console's Storage page shows with 4090 stock.")
@click.option("--size", default=250, show_default=True, help="Size in GB. Can only grow later.")
def volume_up(dc: str, size: int) -> None:
    """Create the weights volume (confirms; ~$0.07/GB/mo until deleted)."""
    _volume.up(dc, size)


@volume.command("status")
def volume_status() -> None:
    """Volume id, datacenter, size, monthly cost."""
    _volume.status()


@volume.command("down")
def volume_down() -> None:
    """DELETE the volume and every cached weight (confirms; experiment-over)."""
    _volume.down()


@cli.command()
@click.argument("slug")
def refs(slug: str) -> None:
    """Mint presigned URLs for SLUG's references and pull them onto the pod."""
    _refs.push_refs(slug)


@cli.command()
def smoke() -> None:
    """Milestone 0: one plain FLUX render on the pod — proves the whole stack."""
    _generate.smoke()


@cli.command()
@click.option("--engine", required=True,
              help="Which model: flux1dev or sd35 (image); ltx098 / ltx23 / ltx25 / wan / wan14b (video).")
@click.option("--prompt", required=True, help="Your prompt.")
@click.option("--negative", default=None, help="Negative prompt. Video engines only.")
@click.option("--seed", type=int, default=None, help="Fixed seed. Default: random, and printed.")
@click.option("--width", type=int, default=None, help="Override the graph's width.")
@click.option("--height", type=int, default=None, help="Override the graph's height.")
@click.option("--length", type=int, default=None, help="Frames. Video engines only.")
@click.option("--steps", type=int, default=None, help="Sampling steps, where the engine has one.")
@click.option("--out", default=None, help="Where to write. Default: local/gen/.")
def gen(engine: str, prompt: str, negative: str | None, seed: int | None, width: int | None,
        height: int | None, length: int | None, steps: int | None, out: str | None) -> None:
    """Generate from your own prompt on any registered engine, image or video."""
    _generate.gen(engine, prompt, negative=negative, seed=seed, width=width,
                  height=height, length=length, steps=steps, out=out)


@cli.command("smoke-video")
@click.option("--engine", type=click.Choice(["ltx098", "ltx23", "ltx25", "wan", "wan14b"]), required=True,
              help="Which local video model to prove.")
def smoke_video(engine: str) -> None:
    """Milestone 0b: one short clip on a local video engine — fetches its weights once."""
    _generate.smoke_video(engine)


@cli.command()
@click.argument("slug")
@click.option("--ref-index", default=0, show_default=True,
              help="Which pulled reference conditions PuLID.")
def expand(slug: str, ref_index: int) -> None:
    """Session A: render 40–60 identity-conditioned candidates for curation."""
    _generate.expand(slug, ref_index)


@cli.command()
@click.argument("slug")
def captions(slug: str) -> None:
    """Scaffold caption .txt files for the curated dataset (then edit each)."""
    _train.scaffold_captions(slug)


@cli.command()
@click.argument("slug")
def masks(slug: str) -> None:
    """Generate face masks on the pod for masked training."""
    _train.masks(slug)


@cli.command()
@click.argument("slug")
@click.option("--steps", default=2000, show_default=True)
@click.option("--base", default="flux1", show_default=True, type=click.Choice(["flux1", "flux2"]),
              help="Base model. flux2 = FLUX.2-dev; needs an 80GB pod (--gpu a100).")
def train(slug: str, steps: int, base: str) -> None:
    """Session B: push the curated dataset and start OneTrainer in tmux."""
    _train.start(slug, steps, base)


@cli.command("train-status")
@click.argument("slug")
def train_status(slug: str) -> None:
    """Is training alive, and the last 25 log lines."""
    _train.status(slug)


@cli.command("fetch-checkpoints")
@click.argument("slug")
@click.option("--base", default="flux1", show_default=True, type=click.Choice(["flux1", "flux2"]))
def fetch_checkpoints(slug: str, base: str) -> None:
    """Pull checkpoints down and link them into ComfyUI for validation."""
    _train.fetch(slug, base)


@cli.command()
@click.argument("slug")
@click.option("--strength", default=0.8, show_default=True)
@click.option("--base", default="flux1", show_default=True, type=click.Choice(["flux1", "flux2"]))
def validate(slug: str, strength: float, base: str) -> None:
    """Render the fixed validation grid with every fetched checkpoint."""
    _generate.validate(slug, strength, base)


@cli.command()
@click.argument("slug")
@click.argument("checkpoint", type=click.Path(exists=True, path_type=pathlib.Path))
def store(slug: str, checkpoint: pathlib.Path) -> None:
    """Upload the winning checkpoint into SLUG's corpus pool in studio."""
    _artifact.store(slug, checkpoint)


@cli.command()
def teardown() -> None:
    """Shred subject data on the pod, then TERMINATE it (confirms)."""
    _pod.down(shred_first=True)


if __name__ == "__main__":
    main()
