# Headless-browser renderer Lambda.
#
# Chromium + all its system libraries are far too heavy for the shared
# scout-events-api image (which backs api/processor/scheduler/sweep), so the
# renderer ships as its own image. We start from the official Playwright image
# (Ubuntu + browsers + their OS deps already installed) and bolt on the AWS
# Lambda Runtime Interface Client so it runs as a container Lambda.
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Lambda only mounts /tmp writable; point HOME there so Chromium's caches
    # and profile have somewhere to live.
    HOME=/tmp \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /var/task

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py ./

# Run via the Lambda Runtime Interface Client; CMD is the handler entrypoint.
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
