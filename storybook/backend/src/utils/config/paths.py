from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = _BACKEND_DIR / "config"
ASSETS_DIR = _BACKEND_DIR / "assets"

CONFIG_YAML_PATH = CONFIG_DIR / "config.yaml"
if not CONFIG_YAML_PATH.exists():
    raise FileNotFoundError(f"Required config file not found: {CONFIG_YAML_PATH}")

DOCUMENTDB_CA_BUNDLE_PATH = CONFIG_DIR / "global-bundle.pem"
