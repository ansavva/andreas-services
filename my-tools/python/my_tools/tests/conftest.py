import subprocess
import sys
from pathlib import Path

import pytest

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


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Provide a temporary DB path and monkeypatch cache.DB_PATH."""
    db_path = tmp_path / "test_photos.db"
    import my_tools.photos.cache as cache_mod
    monkeypatch.setattr(cache_mod, "DB_PATH", db_path)
    return db_path
