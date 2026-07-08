import os

os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("DYNAMODB_ENDPOINT_URL", "http://localhost:8001")

from scout_core.repositories import store
from scout_core.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    store.ensure_local_tables_exist()
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
