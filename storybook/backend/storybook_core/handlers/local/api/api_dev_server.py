import os

os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("DYNAMODB_ENDPOINT_URL", "http://localhost:8001")
os.environ.setdefault("STORYBOOK_USER_PROFILES_TABLE", "storybook-user-profiles")
os.environ.setdefault("STORYBOOK_CHILD_PROFILES_TABLE", "storybook-child-profiles")
os.environ.setdefault("STORYBOOK_STORY_PROJECTS_TABLE", "storybook-story-projects")
os.environ.setdefault("STORYBOOK_STORY_PAGES_TABLE", "storybook-story-pages")
os.environ.setdefault("STORYBOOK_CHAT_MESSAGES_TABLE", "storybook-chat-messages")
os.environ.setdefault("STORYBOOK_CHARACTER_ASSETS_TABLE", "storybook-character-assets")
os.environ.setdefault("STORYBOOK_STORY_STATES_TABLE", "storybook-story-states")
os.environ.setdefault("STORYBOOK_IMAGES_TABLE", "storybook-images")
os.environ.setdefault("STORYBOOK_MODEL_PROJECTS_TABLE", "storybook-model-projects")
os.environ.setdefault("STORYBOOK_GENERATION_HISTORY_TABLE", "storybook-generation-history")
os.environ.setdefault("STORYBOOK_TRAINING_RUNS_TABLE", "storybook-training-runs")

from storybook_core.repositories.dynamodb import ensure_local_tables_exist
from storybook_core.app_factory import create_app
from storybook_core.config import AppConfig

app = create_app()

if __name__ == "__main__":
    ensure_local_tables_exist()
    debug_mode = AppConfig.FLASK_ENV == "development"
    app.run(debug=debug_mode, port=AppConfig.PORT, host="0.0.0.0")
