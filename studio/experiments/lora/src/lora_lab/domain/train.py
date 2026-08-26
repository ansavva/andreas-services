"""Session B: push the curated dataset and run the LoRA training.

OneTrainer, headless (`scripts/train.py --config-path …`), inside tmux so the
SSH session can drop without killing the run. The config template ships in
assets/ and this module only fills paths, the trigger token and the step
count — hyperparameters are changed in the template, deliberately, so a
retrain's settings are diffable against the file rather than lost in a shell
history.

The masks OneTrainer trains against come from `lora-lab masks`, which runs
insightface (already on the pod for PuLID) over the dataset and writes one
white-face-on-black mask per image.
"""

import json

import click

from lora_lab import ASSETS_DIR, LOCAL_DIR
from lora_lab.adapters import shell
from lora_lab.domain import generate, pod

# OneTrainer and its ~32GB FLUX.1-dev snapshot are the largest thing the lab
# installs, and Session B is the only thing that opens them. They land on the
# /weights volume — once ever, not once per pod.
TRAIN_ASSETS = {"flux1": ["onetrainer"], "flux2": ["onetrainer", "flux2base"]}
CONFIG_TEMPLATE = {"flux1": "train-config.template.json",
                   "flux2": "train-config-flux2.template.json"}
MASK_ASSETS = ["pulid"]  # masks runs insightface, which ships with the PuLID stack

REMOTE_TRAIN = "/workspace/train"
TMUX_SESSION = "onetrainer"


def _dataset_dir(slug: str):
    d = LOCAL_DIR / slug / "dataset"
    # Case-insensitive: a phone's .JPG files fell out of the count once.
    images = sorted(f for f in d.iterdir()
                    if f.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if len(images) < 10:
        raise click.ClickException(
            f"{d} holds {len(images)} images — the recipe wants 15–20 curated ones "
            "(Gate 1). Copy keepers from candidates/ and caption them first."
        )
    missing = [i.name for i in images if not i.with_suffix(".txt").is_file()]
    if missing:
        raise click.ClickException(
            f"images without captions: {', '.join(missing[:5])}"
            f"{'…' if len(missing) > 5 else ''} — see assets/captions.md"
        )
    return d, images


def scaffold_captions(slug: str) -> None:
    d = LOCAL_DIR / slug / "dataset"
    if not d.is_dir():
        raise click.ClickException(f"{d} does not exist — curate candidates into it first (Gate 1)")
    trigger = f"ohwx_{slug}"
    created = 0
    for img in sorted(f for f in d.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg")):
        txt = img.with_suffix(".txt")
        if not txt.is_file():
            txt.write_text(f"photo of {trigger}, FILL IN: wardrobe, pose, lighting, background\n")
            created += 1
    click.echo(f"scaffolded {created} caption file(s) in {d} — edit each before training")


def masks(slug: str) -> None:
    """Generate face masks on the pod for masked training."""
    pod.ready()
    pod.ensure(MASK_ASSETS, generate.ASSET_GB)
    ip, port = pod.endpoint()
    shell.run(ip, port, f"mkdir -p {REMOTE_TRAIN}/{slug}")
    shell.rsync_to(ip, port, LOCAL_DIR / slug / "dataset", f"{REMOTE_TRAIN}/{slug}/dataset")
    shell.run(
        ip, port,
        f"cd /opt/lab/pod-scripts && python3.12 make_masks.py {REMOTE_TRAIN}/{slug}/dataset",
        stream=True,
    )
    click.echo("masks written next to the dataset on the pod (*-masklabel.png)")


def start(slug: str, steps: int, base: str = "flux1") -> None:
    pod.ready()
    ip, port = pod.endpoint()
    # Install before the confirm, not after: OneTrainer plus the FLUX base is
    # ~40GB and a quarter of an hour, and finding that out *after* saying yes
    # to "start training?" reads as a hang.
    pod.ensure(TRAIN_ASSETS[base], generate.ASSET_GB)
    dataset, images = _dataset_dir(slug)
    trigger = f"ohwx_{slug}"

    click.echo(f"dataset: {len(images)} captioned images; trigger token {trigger}; {steps} steps")
    click.confirm("push dataset and start training on the pod?", abort=True)

    remote = f"{REMOTE_TRAIN}/{slug}"
    shell.run(ip, port, f"mkdir -p {remote}/output")
    shell.rsync_to(ip, port, dataset, f"{remote}/dataset")

    # OneTrainer's current TrainConfig has no step-count field — only epochs.
    # At batch 1, one epoch is one pass over the dataset, so the requested
    # step budget converts directly.
    epochs = max(1, -(-steps // len(images)))

    def fill(name: str) -> str:
        return (
            (ASSETS_DIR / name).read_text()
            .replace("{DATASET_DIR}", f"{remote}/dataset")
            .replace("{OUTPUT_DIR}", f"{remote}/output")
            .replace("{TRIGGER}", trigger)
            .replace("{EPOCHS}", str(epochs))
        )

    for template, remote_name in (
        (CONFIG_TEMPLATE[base], "train-config.json"),
        ("concepts.template.json", "concepts.json"),
        ("train-samples.template.json", "samples.json"),
    ):
        filled = fill(template)
        json.loads(filled)  # fail here, not on the pod
        local = LOCAL_DIR / slug / remote_name
        local.write_text(filled)
        shell.scp_to(ip, port, local, f"{remote}/{remote_name}")

    # GPU is single-tenant for training: ComfyUI keeps ~16GB resident after
    # any render and OneTrainer OOMed beside it. Validation restarts ComfyUI.
    shell.run(ip, port, "tmux kill-session -t comfy 2>/dev/null", check=False)
    shell.run(
        ip, port,
        f"tmux new-session -d -s {TMUX_SESSION} "
        f"'cd /weights/tools/OneTrainer && ./venv/bin/python scripts/train.py "
        f"--config-path {remote}/train-config.json 2>&1 | tee {remote}/train.log'",
    )
    click.echo(f"training started in tmux `{TMUX_SESSION}` — follow with `lora-lab train-status {slug}`")


def status(slug: str) -> None:
    ip, port = pod.endpoint()
    alive = shell.run(ip, port, f"tmux has-session -t {TMUX_SESSION} 2>/dev/null && echo yes || echo no",
                      check=False).strip()
    # Alive means the TRAINER PROCESS exists — the only ground truth. tmux
    # outlives a crashed trainer (TensorBoard holds the session, measured
    # 2026-08-25), and the log contains Tracebacks OneTrainer catches and
    # survives — grepping for those declared a healthy run dead at step ~250
    # and tore it down, also 2026-08-25. Both proxies are for humans only.
    log = f"{REMOTE_TRAIN}/{slug}/train.log"
    proc = shell.run(ip, port, "pgrep -f '[s]cripts/train.py' >/dev/null && echo yes || echo no",
                     check=False).strip()
    click.echo(f"training session alive: {proc or alive}")
    click.echo(shell.run(
        ip, port,
        f"tr '\r' '\n' < {log} 2>/dev/null | "
        "grep -vE 'TensorBoard|TensorFlow installation|load_fast|Serving TensorBoard|pkg_resources|^$' | tail -n 25",
        check=False))


def fetch(slug: str, base: str = "flux1") -> None:
    """Pull every checkpoint down and expose them to ComfyUI for validation."""
    ip, port = pod.endpoint()
    # save_every writes into <workspace_dir>/save/ (GenericTrainer), the
    # final model into output/ — search both, or a capped run fetches nothing.
    remote = f"{REMOTE_TRAIN}/{slug}/output {REMOTE_TRAIN}/{slug}/workspace"
    listing = shell.run(ip, port, f"find {remote} -name '*.safetensors' 2>/dev/null", check=False)
    files = [l.strip() for l in listing.splitlines() if l.strip()]
    if not files:
        raise click.ClickException("no .safetensors in the output dir yet")
    out_dir = LOCAL_DIR / slug / ("checkpoints" if base == "flux1" else f"checkpoints-{base}")
    for f in files:
        shell.scp_from(ip, port, f, out_dir / f.rsplit("/", 1)[1])
        shell.run(ip, port, f"ln -sf {f} /opt/ComfyUI/models/loras/", check=False)
    click.echo(f"{len(files)} checkpoint(s) fetched to {out_dir} and linked for ComfyUI")
