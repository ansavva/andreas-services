FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.2.1 && \
    poetry config virtualenvs.create false

# Copy dependency manifests first for layer caching
COPY pyproject.toml poetry.lock ./

RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY humbugg_core ./humbugg_core

ENV PYTHONPATH="/app"

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["humbugg_core.handlers.aws.api.api_handler.handler"]
