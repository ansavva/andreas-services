"""Pod lifecycle: create, verify, status, terminate.

There is no bootstrap step anymore. The image (docker/) carries ComfyUI, the
PuLID nodes and the pod-side scripts; the network volume carries every weight;
the create-pod env vars carry the config. By the time SSH answers, the
entrypoint has already started ComfyUI — `pod verify` is the health check that
replaced `pod bootstrap`.

State is one JSON file, `local/pod.json` — the pod id and its SSH endpoint.
Losing it does not strand anything (`lora-lab pod down` falls back to listing
pods by name prefix), but every command reads it rather than asking RunPod
again.

Money gates: creating a pod and terminating one both confirm interactively.
Creation because it starts billing; termination because it destroys the only
copy of any subject data not yet fetched — and deliberately NOT the weights,
which live on the volume.
"""

import json
import pathlib
import shlex
import time

import click

from lora_lab import LOCAL_DIR, env_value
from lora_lab.adapters import runpod, shell
from lora_lab.domain import volume as _volume

STATE_FILE = LOCAL_DIR / "pod.json"
POD_NAME = "lora-lab"

# On the volume, so "present" survives pods — the whole point of the volume.
ASSET_MARKER = "/weights/.asset-{component}-done"

# Fixed by the image. The env file is written by the entrypoint from the
# create-pod env vars (SSH sessions do not inherit PID 1's environment).
POD_ASSETS = "/opt/lab/pod-assets.sh"
LAB_ENV = "/etc/lab.env"

# What `pod verify` allows at the top level of /weights. Anything else is a
# subject-data leak onto storage that survives Terminate, and the audit's job
# is to make that loud.
WEIGHTS_ALLOWED = {"models", "tools", "hf-cache", "lost+found"}


def _public_key() -> str:
    """The SSH public key the entrypoint's sshd trusts. LORA_LAB_SSH_PUBKEY
    wins; otherwise the first ~/.ssh/id_*.pub found."""
    explicit = env_value("LORA_LAB_SSH_PUBKEY")
    if explicit:
        p = pathlib.Path(explicit).expanduser()
        return p.read_text().strip() if p.is_file() else explicit
    ssh_dir = pathlib.Path.home() / ".ssh"
    for name in ("id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"):
        candidate = ssh_dir / name
        if candidate.is_file():
            return candidate.read_text().strip()
    raise click.ClickException(
        "no SSH public key found — set LORA_LAB_SSH_PUBKEY or create ~/.ssh/id_ed25519.pub"
    )


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_state() -> dict | None:
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text())
    return None


def endpoint() -> tuple[str, int]:
    """The saved SSH endpoint, refusing to guess if there is none."""
    state = load_state()
    if not state or "ip" not in state:
        raise click.ClickException("no pod on record — run `lora-lab pod up` first")
    return state["ip"], state["port"]


def up(gpu: str) -> None:
    token = runpod.load_token()
    image = runpod.default_image()  # fail before any money question if unbuilt
    vol = _volume.require()
    hf_token = env_value("HF_TOKEN") or ""
    if not hf_token:
        click.echo("WARNING: HF_TOKEN not set — it rides in as a pod env var, so gated "
                   "downloads on THIS pod will fail. Set it and re-create the pod.")
    if load_state():
        raise click.ClickException(
            f"{STATE_FILE} already records a pod — `lora-lab pod status`, or `pod down` first"
        )

    gpu_name = runpod.GPU_TYPES.get(gpu, gpu)
    click.echo(f"about to rent: 1x {gpu_name}, Secure Cloud, on-demand, "
               f"{runpod.CONTAINER_DISK_GB}GB disk, volume {vol['id']} at /weights "
               f"(dc {vol.get('dc')}) — billing starts immediately")
    click.confirm("create the pod?", abort=True)

    pod = runpod.create_pod(
        token, name=POD_NAME, public_key=_public_key(), hf_token=hf_token,
        volume_id=vol["id"], data_center_id=vol.get("dc"), gpu=gpu, image=image,
    )
    pod_id = pod.get("id")
    if not pod_id:
        raise click.ClickException(f"create returned no pod id: {pod}")
    click.echo(f"pod {pod_id} created; waiting for RUNNING + ssh mapping…")

    # 30 minutes, not 10: the first boot on a host pulls the ~20GB image from
    # ECR before the container starts, and 10 minutes terminated a pod that
    # was merely mid-pull on 2026-08-24. Status is echoed on change so a real
    # failure (a crash-looping entrypoint, a stuck schedule) is diagnosable
    # from the log rather than a silent countdown.
    deadline = time.time() + 1800
    ep = None
    last_status = ""
    while time.time() < deadline:
        pod = runpod.get_pod(token, pod_id)
        status = str(pod.get("desiredStatus") or pod.get("status"))
        if status != last_status:
            click.echo(f"  status: {status}")
            last_status = status
        ep = runpod.ssh_endpoint(pod)
        if runpod.is_running(pod) and ep:
            break
        time.sleep(10)
    if not ep:
        raise click.ClickException(
            f"pod {pod_id} has no ssh endpoint after 30 minutes (last status: "
            f"{last_status}) — `lora-lab pod status` to keep watching, `pod down` to abandon"
        )

    ip, port = ep
    save_state({"id": pod_id, "ip": ip, "port": port, "gpu": gpu_name})
    click.echo(f"ssh endpoint {ip}:{port}; waiting for sshd…")
    shell.wait_for_ssh(ip, port)
    click.echo("pod is up — the entrypoint is starting ComfyUI. Next: `lora-lab pod verify`")


def install(component: str) -> None:
    """Fetch one component onto the volume. See assets/pod-assets.sh.

    The script ships inside the image; nothing is scp'd. HF_TOKEN comes from
    /etc/lab.env, which the entrypoint wrote from the create-pod env — never
    from a command line. Each component lands once EVER: the volume, not the
    pod, is what remembers.
    """
    ip, port = endpoint()
    shell.run(
        ip, port,
        f"set -a; . {LAB_ENV}; set +a; bash {POD_ASSETS} {component}",
        stream=True,
    )


def has(component: str) -> bool:
    ip, port = endpoint()
    marker = ASSET_MARKER.format(component=component)
    return "ok" in shell.run(ip, port, f"test -f {marker} && echo ok", check=False)


def ensure(components, sizes: dict) -> None:
    """Install every component not already on the volume, checking space first.

    Space is checked against the total still missing rather than per
    component, because the failure this guards is a download dying half way
    and leaving a truncated checkpoint that looks present to everything
    except the loader.
    """
    missing = [c for c in components if not has(c)]
    if not missing:
        return
    need = sum(sizes.get(c, 0) for c in missing)
    free = free_volume_gb()
    if free < need + 5:
        raise click.ClickException(
            f"{', '.join(missing)} need ~{need}GB and the volume has {free}GB free. "
            "Grow it in the RunPod console (Storage — size can only increase), or "
            "delete an engine you are done with under /weights/models/."
        )
    for component in missing:
        click.echo(f"installing {component} (~{sizes.get(component, '?')}GB)…")
        install(component)


def free_volume_gb() -> int:
    """Free space on the network volume, in GB."""
    ip, port = endpoint()
    out = shell.run(ip, port, "df -BG --output=avail /weights | tail -1", check=False)
    return int(out.strip().rstrip("G") or 0)


# The image fixes both paths, so no discovery — but the entrypoint still
# writes /workspace/.comfydir and .pybin, and reading them here keeps this
# honest against an image override.
COMFY_START = (
    "cd $(cat /workspace/.comfydir 2>/dev/null || echo /opt/ComfyUI) && "
    "$(cat /workspace/.pybin 2>/dev/null || echo python3.12) "
    "main.py --listen 127.0.0.1 --port 8188 "
    "--extra-model-paths-config /opt/lab/pod-scripts/extra-paths.yaml "
    "--output-directory /workspace/comfy-out "
    "2>&1 | tee -a /workspace/comfy.log"
)


def comfy_up() -> bool:
    ip, port = endpoint()
    code = shell.run(
        ip, port,
        "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8188/system_stats",
        check=False,
    ).strip()
    return code == "200"


def ensure_comfy(wait_s: int = 300) -> None:
    """Start ComfyUI if it is not answering, and wait for it.

    The entrypoint starts it once, in a tmux session, and that is not treated
    as permanent: the process has gone away before (a killed tmux server, a
    dead-on-arrival dependency), and both times the next command failed with
    "ComfyUI is not answering" and a hand-typed restart. Re-asserting it is
    cheap; the curl is one ssh round trip when it is already up.
    """
    if comfy_up():
        return
    ip, port = endpoint()
    click.echo("ComfyUI is not answering — starting it…")
    shell.run(
        ip, port,
        f"tmux kill-session -t comfy 2>/dev/null; tmux new-session -d -s comfy {shlex.quote(COMFY_START)}",
        check=False,
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if comfy_up():
            click.echo("ComfyUI is up.")
            return
        time.sleep(10)
    raise click.ClickException(
        f"ComfyUI did not answer within {wait_s}s — `ssh root@{ip} -p {port} "
        "'tail -40 /workspace/comfy.log'`"
    )


def weights_mounted() -> bool:
    """Is /weights actually the network volume, not a plain container dir?

    A pod created without the volume still runs — the entrypoint mkdirs
    /weights — but every download lands on the container disk and dies with
    the pod. Silent, expensive, and exactly what this check makes loud.
    """
    ip, port = endpoint()
    out = shell.run(ip, port, "mountpoint -q /weights && echo ok", check=False)
    return "ok" in out


def ready() -> None:
    """Refuse to spend GPU time on a pod that is not actually ready."""
    if not weights_mounted():
        raise click.ClickException(
            "/weights is not a mounted volume on this pod — it was created "
            "without the network volume. Terminate and `lora-lab pod up` again."
        )
    ensure_comfy()


def verify() -> None:
    """The health check that replaced `pod bootstrap`, plus the privacy audit.

    The audit is the redrawn teardown invariant: /weights survives Terminate,
    so nothing subject-derived may be on it. Top-level names outside the
    allowed set are reported, not deleted — deciding is human work.
    """
    ip, port = endpoint()
    click.echo(f"ssh       root@{ip} -p {port} — answering")
    mounted = weights_mounted()
    click.echo(f"volume    /weights {'mounted' if mounted else 'NOT MOUNTED — pod has no volume'}")
    ensure_comfy()
    click.echo("comfyui   up")
    if mounted:
        listing = shell.run(ip, port, "ls -A /weights", check=False).split()
        stray = [n for n in listing
                 if n not in WEIGHTS_ALLOWED and not n.startswith(".asset-")]
        if stray:
            click.echo(f"AUDIT FAIL: unexpected on the volume: {', '.join(stray)} — "
                       "/weights survives Terminate, so nothing subject-derived may "
                       "live there. Move it under /workspace and investigate how it "
                       "got there.")
        else:
            click.echo("audit     /weights holds only weights, tools and markers")


def status() -> None:
    state = load_state()
    if not state:
        click.echo("no pod on record")
        return
    token = runpod.load_token()
    pod = runpod.get_pod(token, state["id"])
    click.echo(f"pod      {state['id']} ({state.get('gpu')})")
    click.echo(f"status   {pod.get('desiredStatus') or pod.get('status')}")
    click.echo(f"ssh      root@{state['ip']} -p {state['port']}")
    mounted = shell.run(state["ip"], state["port"],
                        "mountpoint -q /weights && echo yes || echo no", check=False).strip()
    click.echo(f"volume        {mounted or 'unreachable'}")
    comfy = shell.run(state["ip"], state["port"],
                      "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8188/system_stats",
                      check=False).strip()
    click.echo(f"comfyui       {'up' if comfy == '200' else 'down'}")


def down(*, shred_first: bool = False) -> None:
    state = load_state()
    token = runpod.load_token()
    pod_id = state["id"] if state else None
    if not pod_id:
        pods = [p for p in runpod.list_pods(token) if p.get("name") == POD_NAME]
        if not pods:
            click.echo("no pod on record and none named lora-lab — nothing to do")
            return
        pod_id = pods[0]["id"]

    if shred_first and state:
        click.echo("shredding /workspace/dataset, /workspace/train and /workspace/comfy-out on the pod…")
        shell.run(
            state["ip"], state["port"],
            "find /workspace/dataset /workspace/train /workspace/comfy-out -type f 2>/dev/null "
            "-exec shred -zu {} + ; rm -rf /workspace/dataset /workspace/train /workspace/comfy-out",
            check=False,
        )

    click.echo(f"TERMINATE pod {pod_id} — the container disk (all subject data) is destroyed. "
               "The /weights volume survives, holding public weights only.")
    click.confirm("terminate?", abort=True)
    runpod.terminate(token, pod_id)

    # Verify it is actually gone rather than merely asked to go.
    time.sleep(5)
    try:
        pod = runpod.get_pod(token, pod_id)
        click.echo(f"WARNING: pod still answers ({pod.get('desiredStatus')}) — "
                   "check the RunPod console before walking away")
    except runpod.RunPodError:
        click.echo("pod gone.")
    if STATE_FILE.is_file():
        STATE_FILE.unlink()
