"""The network volume: create, inspect, delete.

One volume, created once, mounted at /weights by every pod — the persistent
half of the RunPod deployment split (image = code, volume = weights, env =
config). It holds PUBLIC model weights and tools only; subject data never
touches it, which is what makes its survival across Terminate compatible with
the lab's privacy posture. `lora-lab pod verify` audits that.

State is `local/volume.json` — the volume id and its datacenter. The
datacenter is load-bearing: every pod must be rented where the volume lives,
so it is recorded rather than re-asked.

Money gates: creating starts a standing ~$0.07/GB/mo charge and deleting
destroys every cached weight, so both confirm interactively. Deleting is the
experiment-over action.
"""

import json

import click

from lora_lab import LOCAL_DIR
from lora_lab.adapters import runpod

STATE_FILE = LOCAL_DIR / "volume.json"
VOLUME_NAME = "lora-lab-weights"


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_state() -> dict | None:
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text())
    return None


def require() -> dict:
    """The saved volume, refusing to guess — pods cannot be created without
    one, because a pod without the volume silently re-downloads everything."""
    state = load_state()
    if state and "id" in state:
        return state
    # Fall back to asking RunPod before failing: the state file is per-machine
    # and the volume is not.
    token = runpod.load_token()
    named = [v for v in runpod.list_volumes(token) if v.get("name") == VOLUME_NAME]
    if named:
        v = named[0]
        state = {"id": v["id"], "dc": v.get("dataCenterId"), "size": v.get("size")}
        save_state(state)
        click.echo(f"recovered volume {v['id']} from RunPod (re-saved to {STATE_FILE})")
        return state
    raise click.ClickException(
        "no network volume on record — run `lora-lab volume up --dc <id>` first"
    )


def up(dc: str, size_gb: int) -> None:
    token = runpod.load_token()
    if load_state():
        raise click.ClickException(
            f"{STATE_FILE} already records a volume — `lora-lab volume status`"
        )
    named = [v for v in runpod.list_volumes(token) if v.get("name") == VOLUME_NAME]
    if named:
        v = named[0]
        save_state({"id": v["id"], "dc": v.get("dataCenterId"), "size": v.get("size")})
        click.echo(f"volume {v['id']} already exists in {v.get('dataCenterId')} — recorded, not recreated")
        return

    monthly = size_gb * 0.07
    click.echo(
        f"about to create: {size_gb}GB Secure Cloud network volume in {dc} — "
        f"~${monthly:.2f}/month, billed until `lora-lab volume down`.\n"
        f"Every future pod must be rented in {dc}; check the console's Storage "
        "page that it stocks 4090s before committing."
    )
    click.confirm("create the volume?", abort=True)
    v = runpod.create_volume(token, name=VOLUME_NAME, size_gb=size_gb, data_center_id=dc)
    vol_id = v.get("id")
    if not vol_id:
        raise click.ClickException(f"create returned no volume id: {v}")
    save_state({"id": vol_id, "dc": dc, "size": size_gb})
    click.echo(f"volume {vol_id} created in {dc}. Next: `lora-lab pod up`")


def status() -> None:
    state = load_state()
    if not state:
        click.echo("no volume on record")
        return
    token = runpod.load_token()
    v = runpod.get_volume(token, state["id"])
    click.echo(f"volume   {state['id']} ({VOLUME_NAME})")
    click.echo(f"dc       {state.get('dc') or v.get('dataCenterId')}")
    click.echo(f"size     {v.get('size') or state.get('size')}GB (~${(v.get('size') or state.get('size') or 0) * 0.07:.2f}/mo)")


def down() -> None:
    state = load_state()
    token = runpod.load_token()
    vol_id = state["id"] if state else None
    if not vol_id:
        named = [v for v in runpod.list_volumes(token) if v.get("name") == VOLUME_NAME]
        if not named:
            click.echo(f"no volume on record and none named {VOLUME_NAME} — nothing to do")
            return
        vol_id = named[0]["id"]

    click.echo(
        f"DELETE volume {vol_id} — every cached weight and the OneTrainer venv "
        "are destroyed, and the next pod re-downloads from scratch. This is "
        "the experiment-over action."
    )
    click.confirm("delete the volume?", abort=True)
    runpod.delete_volume(token, vol_id)
    click.echo("volume gone. Verify in the RunPod console: no pod, no volume.")
    if STATE_FILE.is_file():
        STATE_FILE.unlink()
