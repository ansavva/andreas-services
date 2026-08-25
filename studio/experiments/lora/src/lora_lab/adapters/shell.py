"""ssh/scp/rsync against the pod, and the tunnel the ComfyUI client rides.

Plain subprocess over the system OpenSSH rather than paramiko: the runbook's
manual fallbacks are the same commands, and one mechanism is easier to trust
than two. StrictHostKeyChecking=accept-new because every pod is a fresh host
key by construction.
"""

import contextlib
import pathlib
import re
import shlex
import subprocess
import time

from lora_lab import env_value


class ShellError(Exception):
    pass


# hf_..., and the AWS/RunPod shapes, in case one ever reaches a command line
# again. This is a backstop, not the control: the control is that secrets go
# to the pod as create-pod env vars, which the entrypoint writes to a 0600
# file (/etc/lab.env) — never onto a command line. Added after a live HF
# token was printed into a log by a failed command on 2026-08-24.
_SECRET = re.compile(r"\b(hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|rpa_[A-Za-z0-9]{20,})\b")


def redact(text: str) -> str:
    return _SECRET.sub("<redacted>", text)


def key_path() -> str | None:
    """LORA_LAB_SSH_KEY if set; otherwise let ssh pick its default identity."""
    return env_value("LORA_LAB_SSH_KEY")


def _base(ip: str, port: int) -> list[str]:
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-p", str(port),
    ]
    if key_path():
        cmd += ["-i", key_path()]
    return cmd + [f"root@{ip}"]


def run(ip: str, port: int, remote_cmd: str, *, stream: bool = False, check: bool = True) -> str:
    """Run one command on the pod. stream=True echoes output live (installs).

    `-n` (stdin from /dev/null) is load-bearing: without it ssh inherits and
    drains the caller's stdin, so a `printf 'y' | lora-lab train` lost its
    confirm answer to the OneTrainer install's ssh and aborted at the prompt
    (2026-08-25). Nothing here sends stdin to a remote command; scp, rsync
    and the tunnel manage their own stdio and are untouched.
    """
    cmd = _base(ip, port)
    cmd = cmd[:-1] + ["-n", cmd[-1], remote_cmd]
    if stream:
        proc = subprocess.run(cmd)
        if check and proc.returncode != 0:
            raise ShellError(redact(f"remote command failed ({proc.returncode}): {remote_cmd}"))
        return ""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise ShellError(
            redact(f"remote command failed ({proc.returncode}): {remote_cmd}\n{proc.stderr.strip()}")
        )
    return proc.stdout


def scp_to(ip: str, port: int, local: pathlib.Path, remote: str) -> None:
    cmd = ["scp", "-o", "StrictHostKeyChecking=accept-new", "-P", str(port)]
    if key_path():
        cmd += ["-i", key_path()]
    cmd += ["-r", str(local), f"root@{ip}:{remote}"]
    if subprocess.run(cmd).returncode != 0:
        raise ShellError(f"scp to pod failed: {local} -> {remote}")


def scp_from(ip: str, port: int, remote: str, local: pathlib.Path) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["scp", "-o", "StrictHostKeyChecking=accept-new", "-P", str(port)]
    if key_path():
        cmd += ["-i", key_path()]
    cmd += ["-r", f"root@{ip}:{remote}", str(local)]
    if subprocess.run(cmd).returncode != 0:
        raise ShellError(f"scp from pod failed: {remote} -> {local}")


def rsync_to(ip: str, port: int, local: pathlib.Path, remote: str) -> None:
    ssh_cmd = f"ssh -o StrictHostKeyChecking=accept-new -p {port}"
    if key_path():
        ssh_cmd += f" -i {shlex.quote(key_path())}"
    cmd = ["rsync", "-az", "--delete", "-e", ssh_cmd, f"{local}/", f"root@{ip}:{remote}/"]
    if subprocess.run(cmd).returncode != 0:
        raise ShellError(f"rsync to pod failed: {local} -> {remote}")


def wait_for_ssh(ip: str, port: int, timeout: int = 600) -> None:
    """Poll until sshd answers. A fresh pod takes a minute or three."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            run(ip, port, "true", check=True)
            return
        except ShellError:
            time.sleep(10)
    raise ShellError(f"ssh to {ip}:{port} not answering after {timeout}s")


@contextlib.contextmanager
def tunnel(ip: str, port: int, local_port: int, remote_port: int):
    """ssh -N -L local:127.0.0.1:remote, held open for the with-block.

    Remote services bind 127.0.0.1 only (the image's entrypoint), so this
    tunnel is the single way in — the blueprint's privacy requirement, kept.
    """
    cmd = _base(ip, port)
    cmd = cmd[:-1] + ["-N", "-L", f"{local_port}:127.0.0.1:{remote_port}", cmd[-1]]
    proc = subprocess.Popen(cmd)
    try:
        time.sleep(3)
        if proc.poll() is not None:
            raise ShellError(f"tunnel exited immediately: {' '.join(cmd)}")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=10)
