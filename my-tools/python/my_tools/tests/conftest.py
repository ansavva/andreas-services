import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable  # venv python
# Resolve my-tools binary from the same bin directory as the venv Python
MY_TOOLS = str(Path(sys.executable).parent / "my-tools")


def run_cli(*args):
    """Run my-tools CLI via subprocess. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        [MY_TOOLS, *args],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr
