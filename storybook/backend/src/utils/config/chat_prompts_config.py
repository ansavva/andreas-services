import yaml

from .paths import ASSETS_DIR, CONFIG_YAML_PATH


class ChatPromptsConfig:
    """Loads chat prompt templates from config.yaml and assets/prompts."""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChatPromptsConfig, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        with open(CONFIG_YAML_PATH, "r") as f:
            self._config = yaml.safe_load(f)

    def reload(self) -> None:
        self._load_config()

    def get_prompt(self, key: str) -> str:
        prompts_cfg = self._config.get("chat_prompts", {})
        if key not in prompts_cfg:
            raise KeyError(f"Missing chat prompt config for '{key}'")
        return self._load_prompt_file(prompts_cfg[key])

    def _load_prompt_file(self, filepath: str) -> str:
        full_path = ASSETS_DIR / filepath
        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")
        with open(full_path, "r") as f:
            return f.read().strip()
