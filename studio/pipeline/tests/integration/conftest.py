"""The harness: a clean subprocess environment, and the guards around it.

The single most dangerous thing in this directory is the environment. Read
`studio_env` before adding a test.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent

#: The CLI under test: the one installed in the interpreter running pytest.
#:
#: **Not `studio` off PATH, and this is not pedantry.** A developer with several
#: worktrees has a `.venv` in each and exactly one of them on PATH — so a run
#: from this worktree happily exercised the MAIN checkout's binary, several
#: commits behind, and reported it as a pass. It was noticed only because an
#: assertion failed on an error message that had been reworded here.
#:
#: `sys.prefix` is the venv pytest is running in, which is the venv `uv run
#: --project studio/pipeline` created for THIS tree. Deriving it from the
#: interpreter rather than counting `..` from this file is the same rule
#: `STUDIO_DIR` exists for.
STUDIO_BIN = Path(sys.prefix) / "bin" / "studio"

#: Environment variables the UNIT conftest sets at import time that must not
#: reach a subprocess. Two of them are the whole reason this list exists:
#:
#:     STUDIO_S3_BUCKET     = studio-prod-media-us-east-1
#:     STUDIO_CATALOG_TABLE = studio-prod-catalog
#:
#: They are correct there — the unit suite runs against moto and wants stable
#: names — and inheriting them here would point every command in this file at
#: PRODUCTION. `assert_dev_stack` below is the second line of defence, and it is
#: not a substitute for this one: a command that reads a bucket name for itself
#: would already have done the damage by the time an assertion ran.
POISONED = ("STUDIO_S3_BUCKET", "STUDIO_CATALOG_TABLE")

#: The unit conftest `setdefault`s these to the string "testing". On a machine
#: whose real key lives in `~/.aws/credentials` that is not a no-op — an
#: environment variable BEATS the credentials file (see the root CLAUDE.md), so
#: the sentinel would shadow the real key and every AWS call would fail
#: `InvalidClientTokenId`. Dropped only when they still hold the sentinel, so a
#: machine that genuinely supplies its key by environment keeps it.
SENTINEL = "testing"


def studio_env(**over: str) -> dict:
    """The environment a `studio` subprocess gets. Built, never inherited whole.

    `STUDIO_PROFILE=dev` is set explicitly rather than relied upon: `dev` is the
    CLI's default, but a developer with `STUDIO_PROFILE=prod` exported in the
    shell that started pytest would otherwise hand it straight through.
    """
    env = {key: value for key, value in os.environ.items() if key not in POISONED}
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        if env.get(key) == SENTINEL:
            del env[key]
    env["STUDIO_PROFILE"] = "dev"
    # Nothing here may bill. The unit conftest sets this too; it is repeated
    # rather than inherited because this dict is built from scratch and a
    # default that arrives by accident is not a guarantee.
    env["STUDIO_REPLICATE_MODE"] = "fake"
    env.update(over)
    return env


def pytest_collection_modifyitems(config, items):
    """Skip this tree unless it was asked for, by name.

    **Filtered to this directory, and that is not cosmetic.** pytest hands this
    hook every collected item regardless of which conftest defines it, so an
    unfiltered version skips the whole pipeline suite — a thousand tests
    reported as a thousand skips, exit code 0, CI green having executed nothing.
    That happened to the backend's copy of this hook; this is the fixed shape.
    """
    if os.environ.get("STUDIO_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(
        reason="integration suite: set STUDIO_INTEGRATION=1, provision a dev "
               "stack and start scripts/dev-up.sh"
    )
    for item in items:
        if HERE in Path(str(item.fspath)).resolve().parents:
            item.add_marker(skip)


# ── the parent's autouse fixtures, switched off for this tree ───────────────
#
# Overridden by NAME, which is how a conftest replaces an inherited fixture —
# the same mechanism `backend/tests/integration/conftest.py` uses for
# `signed_in`. Doing it here rather than in each module means a test added later
# inherits the override instead of finding out the hard way.


@pytest.fixture(autouse=True)
def _no_live_dynamodb():
    """moto off. The real table is the point of this tree."""
    yield


@pytest.fixture(autouse=True)
def _no_outbound_sockets(monkeypatch):
    """Loopback-only becomes a provider denylist.

    The parent refuses any socket to anything but loopback, which is right for a
    suite where moto is in-process — and would refuse the AWS calls this tree
    makes to check its work. What must still be impossible is a paid one.
    """
    import socket

    billing = ("api.replicate.com", "replicate.delivery",
               "api.openai.com", "api.anthropic.com")
    real_connect = socket.socket.connect

    def guarded(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and any(host == h or host.endswith("." + h)
                                         for h in billing):
            raise RuntimeError(f"the integration suite tried to reach {host!r}, "
                               "which bills.")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded)


# ── running the CLI ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def studio():
    """Run `studio …` as a subprocess and hand back the CompletedProcess."""
    def run(*args: str, check: bool = True, **over: str):
        result = subprocess.run(  # noqa: S603 — a binary this repo installs
            [str(STUDIO_BIN), *args],
            capture_output=True, text=True, timeout=300,
            env=studio_env(**over),
        )
        if check and result.returncode != 0:
            pytest.fail(f"studio {' '.join(args)} exited {result.returncode}\n"
                        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        return result
    return run


@pytest.fixture(scope="session", autouse=True)
def assert_the_binary_is_this_checkouts():
    """The CLI under test has to come from the tree the tests came from."""
    if not STUDIO_BIN.exists():
        pytest.fail(f"no studio binary at {STUDIO_BIN}. "
                    "Run scripts/dev-setup.sh in this worktree.")


@pytest.fixture(scope="session", autouse=True)
def assert_dev_stack(studio, assert_the_binary_is_this_checkouts):
    """Refuse to run at all unless the CLI resolves to a DEV stack.

    Belt to `POISONED`'s braces. `studio profile show` prints what each value
    resolves to and where it came from, so this asks the CLI itself rather than
    re-deriving the answer — the same reason `dev-aws-seed.sh` refuses a bucket
    or table whose name contains `prod` before it reads anything.
    """
    shown = studio("profile", "show").stdout
    if "prod" in shown:
        pytest.fail("the CLI resolves to something with `prod` in it:\n" + shown)
    if "studio-dev-" not in shown:
        pytest.fail("the CLI does not resolve to a dev stack:\n" + shown)


@pytest.fixture(scope="session", autouse=True)
def api_is_up(studio, assert_dev_stack):
    """A signed-in session against a running local API, or a message saying so."""
    result = studio("whoami", check=False)
    if result.returncode != 0 or "localhost" not in result.stdout:
        pytest.fail(
            "no usable session against the local API.\n"
            "  1. studio/scripts/dev-up.sh          (the backend on :8000)\n"
            "  2. studio login                       (the dev pool account)\n"
            f"whoami said:\n{result.stdout}{result.stderr}")


@pytest.fixture(scope="session")
def seeded(studio):
    """The published fixture, loaded. Several tests read `jason` rather than
    building their own material — it is what a seeded stack is for."""
    tree = studio("dev-seed", "tree").stdout
    if "jason" not in tree:
        pytest.fail("this stack is not seeded. Run scripts/dev-aws-seed.sh.")
    return tree


def library_json(studio, *args: str):
    """A command's `--json` output, parsed."""
    return json.loads(studio(*args, "--json").stdout)
