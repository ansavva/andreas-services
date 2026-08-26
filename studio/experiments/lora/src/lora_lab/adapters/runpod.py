"""The RunPod REST client. Modeled on studio_pipeline/adapters/replicate.py.

One deliberate difference from that adapter: every HTTP failure carries the
FULL response body. The REST API's field names — create-pod once, and now the
network-volume endpoints — are the part of this lab most likely to be wrong on
first contact, and the error body is what makes that a one-line fix instead of
an investigation.

Secure Cloud only. Community Cloud is peer-to-peer hardware and the privacy
posture of this experiment rules it out; nothing here can ask for it.
"""

import json
import urllib.error
import urllib.request

from lora_lab import LAB_DIR, env_value

UA = "xharness-studio-lora-lab/1.0"
API_ROOT = "https://rest.runpod.io/v1"

# Ordered by preference. 4090 is the target; the A-series are the documented
# substitutes when Secure Cloud has no 4090 to rent. The network volume pins
# every pod to ITS datacenter, so the fallbacks matter more than they used to.
GPU_TYPES = {
    "4090": "NVIDIA GeForce RTX 4090",
    # 80GB tier — FLUX.2-dev training does not fit 24GB even NF4-quantized.
    "a100": "NVIDIA A100 80GB PCIe",
    "a5000": "NVIDIA RTX A5000",
    "a6000": "NVIDIA RTX A6000",
}

# The lab's own image, built by docker/build.sh and pushed to ECR, where a
# repository policy lets RunPod's account pull it. ComfyUI (pinned commit),
# the PuLID custom nodes and their pip stack, the pod-side scripts and an
# entrypoint that starts sshd + ComfyUI are all baked in — there is no
# bootstrap step. build.sh records the pushed URI in docker/IMAGE; the
# fallback constant exists only so the error for a missing file is not a
# silent pull of something stale.
IMAGE_FILE = LAB_DIR / "docker" / "IMAGE"


def default_image() -> str:
    if IMAGE_FILE.is_file():
        return IMAGE_FILE.read_text().strip()
    raise RunPodError(
        f"{IMAGE_FILE} not found — run docker/build.sh once to build and push "
        "the pod image (and register ECR in the RunPod console, first time)."
    )


# Subject data, checkpoints and renders only — every weight lives on the
# network volume now, so this no longer has to hold ~60GB of models.
CONTAINER_DISK_GB = 150

# The network volume: every engine, OneTrainer and the HF cache coexist
# (~$0.07/GB/mo — a standing cost, deleted deliberately when the experiment
# concludes).
VOLUME_SIZE_GB = 250
VOLUME_MOUNT = "/weights"


class RunPodError(Exception):
    """A failed RunPod call, or a missing key."""


def load_token() -> str:
    tok = env_value("RUNPOD_API_KEY")
    if tok:
        return tok
    raise RunPodError(
        "RUNPOD_API_KEY not set. Put it in "
        "~/.config/andreas-services/studio/dev.env (preferred), export it, or "
        "add it to studio/.env."
    )


def api(method: str, path: str, token: str, body: dict | None = None) -> dict | list | None:
    url = f"{API_ROOT}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", UA)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return json.loads(raw, strict=False) if raw.strip() else None
    except urllib.error.HTTPError as e:
        raise RunPodError(f"{method} {url} -> {e.code}: {e.read().decode()[:2000]}")


# ---------------------------------------------------------------- volumes


def create_volume(token: str, *, name: str, size_gb: int, data_center_id: str) -> dict:
    """Create a Secure Cloud network volume in one datacenter.

    The datacenter choice is load-bearing: every pod that mounts this volume
    must be rented there, so it should be one that stocks 4090s. The console's
    Storage page is where that is visible; the REST API does not expose it.
    """
    body = {"name": name, "size": size_gb, "dataCenterId": data_center_id}
    return api("POST", "/networkvolumes", token, body)


def list_volumes(token: str) -> list:
    out = api("GET", "/networkvolumes", token)
    if isinstance(out, dict):
        return out.get("networkVolumes") or out.get("data") or []
    return out or []


def get_volume(token: str, volume_id: str) -> dict:
    return api("GET", f"/networkvolumes/{volume_id}", token)


def delete_volume(token: str, volume_id: str) -> None:
    api("DELETE", f"/networkvolumes/{volume_id}", token)


# ---------------------------------------------------------------- pods


def create_pod(
    token: str,
    *,
    name: str,
    public_key: str,
    hf_token: str,
    volume_id: str,
    data_center_id: str,
    gpu: str = "4090",
    image: str | None = None,
    disk_gb: int = CONTAINER_DISK_GB,
) -> dict:
    """Create a Secure Cloud on-demand pod with SSH over public TCP.

    The env vars are the whole configuration channel: PUBLIC_KEY is what the
    entrypoint's sshd trusts, HF_TOKEN lands in /etc/lab.env for the on-volume
    downloads. The network volume mounts at /weights; /workspace stays the
    disposable container disk, so Terminate still destroys every byte of
    subject data.
    """
    body = {
        "name": name,
        "imageName": image or default_image(),
        "cloudType": "SECURE",
        "gpuTypeIds": [GPU_TYPES.get(gpu, gpu)],
        "gpuCount": 1,
        "containerDiskInGb": disk_gb,
        "networkVolumeId": volume_id,
        "volumeMountPath": VOLUME_MOUNT,
        "dataCenterIds": [data_center_id],
        # The image's torch is cu129; a 12.8 host refuses it at container
        # start ("Current machine CUDA version is 12.8, but the required
        # version for this image is 12.9", 2026-08-25). Filter the schedule
        # to hosts that can actually run it.
        "allowedCudaVersions": ["12.9", "13.0"],
        "ports": ["22/tcp"],
        "supportPublicIp": True,
        "env": {"PUBLIC_KEY": public_key, "HF_TOKEN": hf_token},
    }
    return api("POST", "/pods", token, body)


def get_pod(token: str, pod_id: str) -> dict:
    return api("GET", f"/pods/{pod_id}", token)


def list_pods(token: str) -> list:
    out = api("GET", "/pods", token)
    # The list endpoint has been seen both bare and wrapped.
    if isinstance(out, dict):
        return out.get("pods") or out.get("data") or []
    return out or []


def terminate(token: str, pod_id: str) -> None:
    api("DELETE", f"/pods/{pod_id}", token)


def is_running(pod: dict) -> bool:
    status = (pod.get("desiredStatus") or pod.get("status") or "").upper()
    return status == "RUNNING"


def ssh_endpoint(pod: dict) -> tuple[str, int] | None:
    """(ip, port) for direct SSH, or None while networking is still coming up.

    Handles the two shapes the API has used for port mappings: a dict of
    {"22": external} and a list of {privatePort, publicPort, ip} objects.
    """
    ip = pod.get("publicIp") or pod.get("public_ip")
    mappings = pod.get("portMappings") or pod.get("ports")
    if isinstance(mappings, dict):
        port = mappings.get("22") or mappings.get(22)
        if ip and port:
            return ip, int(port)
        return None
    if isinstance(mappings, list):
        for m in mappings:
            if not isinstance(m, dict):
                continue
            private = m.get("privatePort") or m.get("private_port")
            if int(private or 0) == 22:
                port = m.get("publicPort") or m.get("public_port")
                mapped_ip = m.get("ip") or ip
                if mapped_ip and port:
                    return mapped_ip, int(port)
    return None
