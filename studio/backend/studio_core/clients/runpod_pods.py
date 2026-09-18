"""The Runpod POD client — the third provider, and the one that is a machine.

`clients/runpod.py` calls hosted models on Runpod's public endpoints. This
module rents a GPU **machine** from the same account and lets it go again:
the training provider. A run whose entry says `provider: runpod-pod` does not
POST a payload to a model; `services/training.py` turns its plan and sends
into a job manifest, this module rents a pod from the official ai-toolkit
image with a URL to that manifest in its environment, the pod trains, uploads
its checkpoints on grants minted at dispatch, calls back, and this module
terminates it.

## What is the same, deliberately

The five names `services/generate.py` reaches a provider through, so the run
lifecycle is untouched: draft, submit, `pending`, `running`, a callback or a
`reconcile`, one closing implementation. `STUDIO_RUNPOD_MODE=fake` governs
this module too — same key, same account, same three guards in the tests.
`rest.runpod.io/v1` rather than `api.runpod.ai/v2`: pods and endpoints are
two APIs under one key.

## What is different, and has to be

**The "prediction" is a pod id and the "output" is a report.** A pod cannot
be asked for its result — it has none; the trainer writes files. So the pod
writes a small `result.json` into the bucket beside its checkpoints and
`training.report` reads that; `get_prediction` here answers only whether the
machine is still alive, for the case where no report ever lands.

**Money runs by the hour, not by the call.** `create_pod` is where billing
starts, `terminate` is where it stops, and the gap between them is the cost.
Everything that closes a training run ends by calling `terminate`, and the
run carries a time cap the pod enforces on itself so a hung trainer calls
back `failed` rather than billing until somebody notices.
"""

import json
import logging
import urllib.error
import urllib.request

from studio_core.clients import runpod
from studio_core.errors import UpstreamError

logger = logging.getLogger(__name__)

UA = "xharness-studio/1.0"
API_ROOT = "https://rest.runpod.io/v1"

#: The official ai-toolkit image, pinned. It carries torch, the trainer and
#: its deps; nothing of studio's is baked in — the job arrives by manifest.
IMAGE = "ostris/aitoolkit:0.13.12"

#: `gpu` in a training plan → Runpod's ids, in preference order. Two 80 GB
#: parts each, so a datacenter out of one still rents the other.
GPU_TYPES = {
    "a100": ["NVIDIA A100 80GB PCIe", "NVIDIA A100-SXM4-80GB"],
    "h100": ["NVIDIA H100 80GB HBM3", "NVIDIA H100 PCIe", "NVIDIA H100 NVL"],
    "4090": ["NVIDIA GeForce RTX 4090"],
}

#: Room for the base model (two 14B experts and a text encoder, ~70 GB), the
#: dataset and every checkpoint. Container disk, gone with the pod.
CONTAINER_DISK_GB = 150

TIMEOUT = 30


class RunpodPodError(UpstreamError):
    """A failed pod call. An `UpstreamError`, so it answers 502."""


class OutputGone(RunpodPodError):
    """Never raised — a pod's outputs are adopted from the bucket, not fetched.
    Named because `services/generate.py` catches `client.OutputGone`."""


class PodGone(RunpodPodError):
    """The pod no longer exists: terminated, or never created."""


def mode() -> str:
    return runpod.mode()


def _request(method: str, url: str, *, body: dict | None = None) -> dict | None:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {runpod.token()}")
    request.add_header("User-Agent", UA)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        if exc.code == 404:
            raise PodGone(f"{method} {url} -> 404: {detail}") from exc
        logger.warning("%s %s -> %s: %s", method, url, exc.code, detail)
        raise RunpodPodError(f"{method} {url} -> {exc.code}: {detail}") from exc
    except OSError as exc:
        logger.warning("%s %s failed: %s", method, url, exc)
        raise RunpodPodError(f"{method} {url} failed: {exc}") from exc
    return json.loads(raw, strict=False) if raw.strip() else None


# ── the fake ────────────────────────────────────────────────────────────────

_FAKE_PODS: dict[str, dict] = {}


def _fake_pod(name: str, gpu: str) -> dict:
    pod = {"id": f"fakepod{abs(hash(name)) % 10**8:08d}", "name": name,
           "desiredStatus": "RUNNING", "costPerHr": 1.59,
           "gpu": {"id": GPU_TYPES.get(gpu, [gpu])[0]}}
    _FAKE_PODS[pod["id"]] = pod
    return pod


# ── pods ────────────────────────────────────────────────────────────────────


def create_pod(*, name: str, gpu: str, cloud: str, env: dict, start_cmd: list[str]) -> dict:
    """Rent one machine. **This is the call that starts billing.**

    On-demand (not interruptible): a spot pod reclaimed mid-run would lose
    hours of training with nothing to resume from. The image's own entrypoint
    is replaced by `start_cmd`, which fetches the manifest and runs the job;
    nothing of the image's SSH or web UI is started.
    """
    if mode() == runpod.FAKE:
        logger.info("[runpod-pod:FAKE] create_pod %s — nothing billed", name)
        return _fake_pod(name, gpu)

    body = {
        "name": name,
        "imageName": IMAGE,
        "cloudType": "COMMUNITY" if cloud == "community" else "SECURE",
        "gpuTypeIds": GPU_TYPES.get(gpu, [gpu]),
        "gpuCount": 1,
        "containerDiskInGb": CONTAINER_DISK_GB,
        "volumeInGb": 0,
        "interruptible": False,
        "supportPublicIp": False,
        "ports": [],
        "env": env,
        "dockerStartCmd": start_cmd,
    }
    pod = _request("POST", f"{API_ROOT}/pods", body=body) or {}
    if not pod.get("id"):
        raise RunpodPodError(f"create pod answered with no id: {json.dumps(pod)[:300]}")
    return pod


def get_pod(pod_id: str) -> dict:
    """The pod's record, or `PodGone`. Reads; never bills."""
    if mode() == runpod.FAKE:
        try:
            return _FAKE_PODS[pod_id]
        except KeyError:
            raise PodGone(pod_id) from None
    return _request("GET", f"{API_ROOT}/pods/{pod_id}") or {}


def terminate(pod_id: str) -> None:
    """Destroy the pod. **This is the call that stops billing.** Idempotent:
    a pod already gone is the outcome wanted, not an error."""
    if mode() == runpod.FAKE:
        logger.info("[runpod-pod:FAKE] terminate %s", pod_id)
        _FAKE_PODS.pop(pod_id, None)
        return
    try:
        _request("DELETE", f"{API_ROOT}/pods/{pod_id}")
    except PodGone:
        return


def is_alive(pod: dict) -> bool:
    status = (pod.get("desiredStatus") or pod.get("status") or "").upper()
    return status in ("RUNNING", "CREATED", "RESTARTING", "PENDING")


# ── the six names `services/generate.py` reaches a provider through ─────────


def create_prediction(model: str, payload: dict, *, webhook: str | None = None) -> dict:
    """Never called: a training run is dispatched by `services/training.py`,
    which owns the manifest. Loud rather than a wrong pod."""
    raise RunpodPodError(
        f"{model} is a training provider; dispatch it through services/training"
    )


def get_prediction(prediction_id: str, *, model: str) -> dict:
    """Whether the machine is still alive, in the vocabulary the closer maps.

    Not the result — that is a report the pod writes and `training.report`
    reads. A pod that has gone away without reporting is a failure; one still
    running is `IN_PROGRESS`.
    """
    try:
        pod = get_pod(prediction_id)
    except PodGone:
        return {"id": prediction_id, "status": "FAILED",
                "error": "the training pod is gone and reported no result"}
    if is_alive(pod):
        return {"id": prediction_id, "status": "IN_PROGRESS"}
    return {"id": prediction_id, "status": "FAILED",
            "error": f"the training pod is {pod.get('desiredStatus')} and reported no result"}


def normalise(prediction: dict) -> dict:
    """The identity: the pod's `result.json` is written in the seam's shape —
    `id`, `status`, `output`, `error` — by the job script itself."""
    return prediction


def output_urls(prediction: dict) -> list[str]:
    """The checkpoint files the pod reported uploading — names, not URLs.

    They are already in the bucket, on the nodes `training.dispatch` made;
    the closer adopts them rather than downloading anything. Names here so the
    generic "succeeded but produced nothing" check still means something.
    """
    output = prediction.get("output")
    if not isinstance(output, dict):
        return []
    return [name for name in (output.get("uploaded") or []) if isinstance(name, str)]


def cost(prediction: dict) -> dict | None:
    """What the machine cost: hourly rate × the hours it existed, computed by
    the pod at the end against the creation time the manifest carried."""
    output = prediction.get("output")
    if not isinstance(output, dict):
        return None
    amount = output.get("cost")
    seconds = output.get("seconds")
    if amount is None and seconds is None:
        return None
    return {"amount": amount, "currency": "USD" if amount is not None else None,
            "predict_time": seconds}


def download(url: str, path: str, *, max_bytes: int) -> int:
    raise RunpodPodError("a training pod's outputs are adopted from the bucket, never downloaded")
