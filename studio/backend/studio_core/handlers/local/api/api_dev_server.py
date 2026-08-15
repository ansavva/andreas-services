"""Local dev server.

Unlike the other services there is no local emulator to point at: the whole
point of this API is reading a real S3 bucket, so local dev uses real read-only
AWS credentials. Export them first — `aws login` alone is not enough for boto3:

    eval "$(aws configure export-credentials --format env)"
"""

import os

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("STUDIO_ALLOWED_ORIGIN", "http://localhost:5173")

from studio_core.app_factory import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
