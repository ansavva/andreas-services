# Use AWS Lambda Python base image
FROM public.ecr.aws/lambda/python:3.12

RUN pip install --no-cache-dir poetry==2.2.1 && \
    poetry config virtualenvs.create false

# Copy dependency manifests first for layer caching
COPY pyproject.toml poetry.lock ${LAMBDA_TASK_ROOT}/

RUN cd ${LAMBDA_TASK_ROOT} && poetry install --only main --no-root --no-interaction --no-ansi

# Copy application code
COPY . ${LAMBDA_TASK_ROOT}/

# Set the Lambda handler
CMD ["src.handlers.lambda.api.api_handler.handler"]
