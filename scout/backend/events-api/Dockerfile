FROM public.ecr.aws/lambda/python:3.11

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir poetry==2.2.1 && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction --no-ansi

COPY lambda_function.py taxonomy.py store.py labels.py locations.py \
     sources.py runs.py fetcher.py artifacts.py extractor.py pipeline.py ./
CMD ["lambda_function.lambda_handler"]
