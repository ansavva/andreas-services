import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable  # venv python


def run_cli(*args):
    """Run my-tools CLI via subprocess. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["my-tools", *args],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr
