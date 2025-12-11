FROM python:3.11-slim AS base

ENV POETRY_VERSION=1.7.1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY commands.sh ./
COPY tests ./tests

ENV PYTHONPATH="/app/src"

EXPOSE 5001

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5001", "src.app:app", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"]
