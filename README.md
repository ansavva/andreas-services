# events.andreas.services — Gmail Event Ingestion

This repository houses the Gmail ingestion workload for the `events.andreas.services` project. The
Python application fetches Gmail messages labeled **Events**, extracts structured event data with the
OpenAI API, deduplicates items in DynamoDB, and records processing metrics. The service now runs as a
container that you can invoke locally or schedule in AWS via EventBridge + ECS Fargate using the
supplied **CloudFormation** template.

---

## Repository Layout

```
backend/
├── app/                     # Container application entrypoint and helpers
│   ├── __init__.py
│   └── main.py              # Gmail → OpenAI → DynamoDB workflow
├── cloudformation/
│   └── events-stack.yaml    # DynamoDB + ECS task + EventBridge rule
├── scripts/
│   ├── build_container_image.sh  # Convenience wrapper for docker builds
│   └── gmail_token_quickstart.py # Gmail OAuth helper to mint refresh tokens
├── Dockerfile
└── requirements.txt         # Shared backend dependencies
```

`.env.example` documents the environment variables consumed during local runs. Copy it to `.env`
and update the placeholder values.

---

## Prerequisites

Install these tools before working with the project:

| Tool | Purpose | Notes |
| --- | --- | --- |
| [Python 3.11](https://www.python.org/downloads/) | Run the application locally & helper scripts | Select this interpreter in VS Code. |
| [pip](https://pip.pypa.io/en/stable/installation/) | Manage Python dependencies | `python3 -m ensurepip --upgrade` if needed. |
| [Docker](https://docs.docker.com/get-docker/) | Build/run the ingestion container & DynamoDB Local | Required for both local dev and production image builds. |
| [Docker Compose](https://docs.docker.com/compose/) | Orchestrate the app + DynamoDB Local containers | Bundled with Docker Desktop; install separately on Linux if needed. |
| [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) | Deploy CloudFormation stacks and manage Secrets Manager | Configure credentials for the AWS account that hosts the production stack. |

VS Code users should also install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
for virtual environment support.

---

## Initial Project Setup

1. **Clone the repository and open it in VS Code.**
   ```bash
   git clone <your-fork-url>
   cd andreas-services
   code .
   ```

2. **Create and activate a Python virtual environment.**
   ```bash
   python3 -m venv .venv
   # macOS/Linux
   source .venv/bin/activate
   # Windows PowerShell
   # .venv\Scripts\Activate.ps1
   ```
   In VS Code run `Python: Select Interpreter` and choose `.venv`.

3. **Install backend dependencies.**
   ```bash
   pip install --upgrade pip
   pip install -r backend/requirements.txt
   ```

4. **Copy the environment template.**
   ```bash
   cp .env.example .env
   ```
   Update the placeholder API key and file paths after you create the OpenAI and Gmail credentials.
   VS Code can auto-load the `.env` file by setting `"python.envFile": "${workspaceFolder}/.env"` in
   `.vscode/settings.json`.

---

## Generating OpenAI and Gmail Credentials

### OpenAI API Key

1. Sign in to [https://platform.openai.com/](https://platform.openai.com/).
2. Navigate to **Dashboard → API keys → + Create new secret key**.
3. Copy the generated `sk-...` string and paste it into your local `.env` as `OPENAI_API_KEY`.
4. For production, create a Secrets Manager entry so the container can resolve the key at runtime:
   ```bash
   aws secretsmanager create-secret \
     --name prod/openai \
     --secret-string '{"apiKey": "sk-your-key"}'
   ```
   Record the returned ARN for the CloudFormation deployment parameters.

### Gmail OAuth Credentials

1. Create (or reuse) a Google Cloud project at [https://console.cloud.google.com/](https://console.cloud.google.com/).
2. Enable the Gmail API under **APIs & Services → Library**.
3. Configure the OAuth consent screen and add the Gmail scopes you need (at minimum
   `https://www.googleapis.com/auth/gmail.readonly`).
4. Create OAuth client credentials via **APIs & Services → Credentials → + Create credentials → OAuth client ID**.
   Choose **Desktop app** and download the JSON file—it contains the `client_id` and `client_secret`.
5. Authorize the mailbox by running the bundled quickstart helper:
   ```bash
   python3 backend/scripts/gmail_token_quickstart.py \
     --client-id "<CLIENT_ID>.apps.googleusercontent.com" \
     --client-secret "<CLIENT_SECRET>" \
     --output gmail-credentials.json
   ```
   Add `--no-browser` when working on a headless host.
6. Store the resulting JSON path in your `.env` (`GMAIL_CREDENTIALS_FILE=./gmail-credentials.json`).
7. For production, upload the same payload to Secrets Manager:
   ```bash
   aws secretsmanager create-secret \
     --name prod/gmail \
     --secret-string file://gmail-credentials.json
   ```
   Keep the ARN handy for the CloudFormation deployment.

---

## Running DynamoDB Locally

AWS services are no longer emulated with LocalStack. Instead, run
[DynamoDB Local](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.DownloadingAndRunning.html#DynamoDBLocal.DownloadingAndRunning.title)
inside Docker. The repository ships with a ready-to-use Compose service:

```bash
docker compose up dynamodb
```

Compose keeps the container alive in the foreground so you can observe its logs. Press `Ctrl+C` to
stop it, or `docker compose down` to remove the container entirely.

Prefer a one-off container instead? The following command mirrors what the Compose file does:

```bash
docker run -d \
  -p 8000:8000 \
  --name dynamodb-local \
  amazon/dynamodb-local:latest
```

The container persists data in-memory by default. Use the `-v` flag documented by AWS if you prefer
on-disk storage. When DynamoDB Local runs on port 8000, set `DYNAMODB_ENDPOINT_URL=http://localhost:8000`
in your `.env` (already included in `.env.example`).

You must also export (or supply through `.env`) dummy AWS credentials so the AWS SDK can sign
requests even though they target DynamoDB Local:

```bash
export AWS_ACCESS_KEY_ID=fake
export AWS_SECRET_ACCESS_KEY=fake
export AWS_REGION=us-east-1  # matches the default in .env.example
```

---

## Local Execution Options

### 1. Docker Compose (recommended)

Compose can build the ingestion image, start DynamoDB Local, and run the container with a single
command. Rebuild and launch the app service:

```bash
docker compose up --build app
```

The first run installs Python dependencies inside the image. Subsequent invocations reuse the cached
layers and mount your local `backend/app` directory into the container, so code changes are picked up
without a rebuild. Use `Ctrl+C` to stop the run. When you are finished developing, tear everything
down with `docker compose down`.

Want a single execution rather than a long-running container? Use `docker compose run --rm app` (add
`--build` to force a rebuild when dependencies change).

The Compose file overrides `DYNAMODB_ENDPOINT_URL` to point at the companion `dynamodb` service. If
you run DynamoDB elsewhere, set `COMPOSE_DYNAMODB_ENDPOINT_URL` in `.env` before starting Compose.

### 2. Python module (fastest iteration)

With the virtual environment activated and DynamoDB Local running:

```bash
set -a
source .env
set +a
PYTHONPATH=backend python3 -m app.main
```

This command loads environment variables from `.env` and executes the ingestion workflow directly.
Adjust the `GMAIL_QUERY` variable in `.env` to narrow which messages are processed (defaults to
`label:Events`).

### 3. Docker container

Build the image:

```bash
./backend/scripts/build_container_image.sh
```

Run it against DynamoDB Local using your `.env` file:

```bash
docker run --rm \
  --env-file .env \
  -e AWS_ACCESS_KEY_ID=fake \
  -e AWS_SECRET_ACCESS_KEY=fake \
  --network host \
  events-gmail-ingest:latest
```

`--network host` allows the container to reach `localhost:8000`. On macOS or Windows use
`--add-host host.docker.internal:host-gateway` and set `DYNAMODB_ENDPOINT_URL=http://host.docker.internal:8000`.

---

## Building and Publishing the Production Image

1. Create (or reuse) an Amazon ECR repository:
   ```bash
   aws ecr create-repository --repository-name events-gmail-ingest
   ```

2. Authenticate Docker to ECR:
   ```bash
   aws ecr get-login-password | docker login \
     --username AWS \
     --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com
   ```

3. Build and tag the image with the full repository URI:
   ```bash
   IMAGE_URI=<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/events-gmail-ingest:latest
   IMAGE_NAME=events-gmail-ingest IMAGE_TAG=latest ./backend/scripts/build_container_image.sh
   docker tag events-gmail-ingest:latest "$IMAGE_URI"
   ```

4. Push the image:
   ```bash
   docker push "$IMAGE_URI"
   ```

Use the resulting `IMAGE_URI` as the `ContainerImage` parameter when deploying CloudFormation.

---

## Deploying with CloudFormation (AWS)

The provided template provisions the DynamoDB table, ECS cluster, Fargate task definition, IAM
permissions, and an EventBridge schedule. Supply the ECR image URI and the Secrets Manager ARNs you
created earlier.

Common parameters:

| Parameter | Description |
| --- | --- |
| `OpenAISecretArn` | ARN of the OpenAI secret (required). |
| `GmailSecretArn` | ARN of the Gmail secret (required). |
| `ContainerImage` | Full ECR image URI (required). |
| `SubnetIds` | Comma-separated list of subnet IDs for the Fargate task. |
| `SecurityGroupIds` | Comma-separated list of security group IDs. |
| `ScheduleExpression` | Cron expression for the EventBridge rule (defaults to Mondays at 5 PM ET). |
| `ScheduleTimezone` | Time zone for the schedule. |
| `TableName`, `ClusterName`, `TaskFamily`, `ContainerCpu`, `ContainerMemory`, `Timezone`, `OpenAIModel`, `AssignPublicIp` | Optional overrides. |

Example deployment:

```bash
aws cloudformation deploy \
  --template-file backend/cloudformation/events-stack.yaml \
  --stack-name events-ingestion \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      OpenAISecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/openai \
      GmailSecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/gmail \
      ContainerImage=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/events-gmail-ingest:latest \
      SubnetIds=subnet-aaaa1111,subnet-bbbb2222 \
      SecurityGroupIds=sg-abc12345
```

CloudFormation outputs the DynamoDB table name/ARN, ECS cluster name, task definition ARN, and the
EventBridge rule ARN after a successful deployment.

---

## Updating the Schedule or Container

* **Change the schedule:** Update `ScheduleExpression` and run `aws cloudformation deploy` with the
  new value.
* **Ship new code:** Build, tag, and push a new container image, then redeploy the stack pointing to
  the new image URI (or update the task definition image via `aws ecs update-service` if you reuse
  the same tag).

---

## Troubleshooting Tips

* Ensure DynamoDB Local is running before invoking the service locally. The AWS SDK will retry
  failed calls, but the run eventually fails if the endpoint cannot be reached.
* If the container exits immediately in AWS, inspect the CloudWatch Logs group `/ecs/<TaskFamily>`
  for stack traces.
* Gmail refresh tokens can expire when revoked. Re-run the quickstart helper and update the Secrets
  Manager secret or local `.env` file when this happens.
* EventBridge and ECS resources are regional. Deploy the stack to the same region that hosts your
  Secrets Manager entries and ECR repository.

---

## Testing the Codebase

The repository does not yet include automated tests. Run a syntax check before committing changes:

```bash
python3 -m compileall backend/app backend/scripts
```

---

## License

Distributed under the MIT license. See `LICENSE` for details.
