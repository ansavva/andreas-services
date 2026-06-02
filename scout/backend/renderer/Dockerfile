# Headless-browser renderer Lambda.
#
# A full browser + its system libraries are far too heavy for the shared
# scout-events-api image (which backs api/processor/scheduler/sweep), so the
# renderer ships as its own image. We start from the official Playwright image
# (Ubuntu + browser OS deps already installed) and bolt on the AWS Lambda Runtime
# Interface Client so it runs as a container Lambda.
#
# The browser driver is patchright (a drop-in, undetected Playwright fork that
# patches the CDP Runtime.enable leak and headless tells), so the base image tag
# is pinned to match patchright's Playwright version.
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Lambda only mounts /tmp writable; point HOME there so Chrome's caches
    # and profile have somewhere to live.
    HOME=/tmp \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /var/task

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install real Google Chrome for patchright's recommended channel="chrome"
# (less detectable than bundled Chromium). --with-deps pulls any extra apt
# packages Chrome needs; safe here because the base image is Ubuntu jammy.
RUN patchright install --with-deps chrome

COPY handler.py ./

# Run via the Lambda Runtime Interface Client; CMD is the handler entrypoint.
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["handler.lambda_handler"]
