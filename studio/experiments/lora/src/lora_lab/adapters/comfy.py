"""A minimal ComfyUI API client, spoken through the SSH tunnel.

ComfyUI's HTTP API takes a workflow in "API format" (node-id keyed graph),
returns a prompt_id, and exposes results via /history and /view. The client
assumes the tunnel is already up and everything is 127.0.0.1.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:8188"


class ComfyError(Exception):
    pass


def _get(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{BASE}{path}") as r:
            return json.loads(r.read().decode(), strict=False)
    except urllib.error.URLError as e:
        raise ComfyError(f"GET {path}: {e}")


def alive(timeout: int = 30) -> bool:
    """Is ComfyUI answering through the tunnel?

    Polls rather than asking once. `shell.tunnel` sleeps a flat 3 seconds
    before yielding, which is not always enough for the SSH handshake — a
    single attempt turns a slow forward into "ComfyUI is not answering" and
    aborts a command whose pod was fine. Measured 2026-08-24 on a run where
    `pod status` reported it up a second later.
    """
    deadline = time.time() + timeout
    while True:
        try:
            _get("/system_stats")
            return True
        except ComfyError:
            if time.time() >= deadline:
                return False
            time.sleep(2)


def require_nodes(names: list[str]) -> None:
    """Fail loudly if a custom node pack did not load — the PuLID nodes are
    the most likely casualty of an image rebuild, and a missing node
    otherwise surfaces as an opaque queue-time validation error."""
    info = _get("/object_info")
    missing = [n for n in names if n not in info]
    if missing:
        raise ComfyError(
            f"ComfyUI is up but these nodes are missing: {', '.join(missing)}. "
            "The nodes are baked into the image — check /workspace/comfy.log "
            "for a failed custom-node import."
        )


def queue(graph: dict) -> str:
    body = json.dumps({"prompt": graph, "client_id": uuid.uuid4().hex}).encode()
    req = urllib.request.Request(f"{BASE}/prompt", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            out = json.loads(r.read().decode(), strict=False)
    except urllib.error.HTTPError as e:
        raise ComfyError(f"POST /prompt -> {e.code}: {e.read().decode()[:2000]}")
    if "prompt_id" not in out:
        raise ComfyError(f"queue refused: {out}")
    return out["prompt_id"]


def wait(prompt_id: str, timeout: int = 1800, poll: int = 5) -> dict:
    """Block until the prompt leaves the queue; return its history entry."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        hist = _get(f"/history/{prompt_id}")
        entry = hist.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                messages = status.get("messages", [])
                raise ComfyError(f"prompt {prompt_id} errored: {messages[-1] if messages else status}")
            if entry.get("outputs"):
                return entry
        time.sleep(poll)
    raise ComfyError(f"prompt {prompt_id} not finished after {timeout}s")


def output_images(entry: dict) -> list[dict]:
    """The {filename, subfolder, type} descriptors of every saved image."""
    images = []
    for node_output in entry.get("outputs", {}).values():
        images.extend(node_output.get("images", []))
    return images


def fetch_image(descriptor: dict) -> bytes:
    params = urllib.parse.urlencode(
        {
            "filename": descriptor["filename"],
            "subfolder": descriptor.get("subfolder", ""),
            "type": descriptor.get("type", "output"),
        }
    )
    try:
        with urllib.request.urlopen(f"{BASE}/view?{params}") as r:
            return r.read()
    except urllib.error.URLError as e:
        raise ComfyError(f"GET /view {descriptor}: {e}")


def run_graph(graph: dict, timeout: int = 1800) -> list[bytes]:
    """Queue, wait, fetch every output image."""
    entry = wait(queue(graph), timeout=timeout)
    return [fetch_image(d) for d in output_images(entry)]


def run_graph_files(graph: dict, timeout: int = 1800) -> list[tuple[str, bytes]]:
    """run_graph, keeping each output's remote filename.

    Video saves report under the same `images` key as stills — SaveWEBM
    returns a PreviewVideo, whose as_dict is `{"images": [...]}` — so only the
    extension distinguishes a clip from a frame, and dropping the name would
    lose it.
    """
    entry = wait(queue(graph), timeout=timeout)
    return [(d["filename"], fetch_image(d)) for d in output_images(entry)]
