"""Running the dev scripts' own shell functions from Python.

**Extracted because two suites in two tiers needed it and one was importing the
other.** `contracts/test_dev_scripts.py` owns the shell side of the contract and
`unit/maintenance/test_dev_seed.py` feeds the publisher's output through the
loader's validator — so `test_dev_seed` did `from tests import test_dev_scripts
as loader`, a test module importing a test module for a helper. That works in
one flat directory and stops working the moment the two sit in different tiers,
which is the useful thing about the tiers.
"""
from __future__ import annotations

import json
import subprocess

from studio_pipeline import STUDIO_DIR

SCRIPTS = STUDIO_DIR / "scripts"
SEED = SCRIPTS / "dev-aws-seed.sh"
SHARED = SCRIPTS / "dev-shared-material.sh"


def source_and_run(script, snippet: str) -> str:
    """Source a script and run `snippet` against its functions.

    Safe because both scripts define their functions before doing anything:
    `dev-aws-seed.sh` puts its body in `main` behind a `BASH_SOURCE` guard for
    exactly this, and `dev-shared-material.sh` is sourced-only by design.
    """
    result = subprocess.run(
        ["bash", "-c", f'source "{script}"\n{snippet}'],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def problems(catalog: dict, manifest: dict) -> str:
    """`fixture_problems` from `dev-aws-seed.sh`, run against two documents.

    The loader's OWN validator, not a Python reimplementation of it — which is
    what makes the publisher and the loader one contract rather than two lists
    that drift.
    """
    return source_and_run(SEED, (
        f"fixture_problems {json.dumps(json.dumps(catalog))} "
        f"{json.dumps(json.dumps(manifest))}"
    ))
