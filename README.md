# events.andreas.services — Gmail Event Ingestion

This repository packages the Gmail ingestion Lambda for the `events.andreas.services` project and the tooling required to deploy it with **plain AWS CLI commands**. The Lambda polls Gmail for messages labelled **Events**, extracts structured event metadata via the OpenAI API, deduplicates records in DynamoDB, and logs summary metrics.

A helper shell script (`backend/scripts/deploy_infrastructure.sh`) provisions or updates every AWS resource with the CLI—no CDK or CloudFormation stacks are required. The same script works against both AWS and LocalStack so your local setup mirrors production.

---

## Repository Layout

```
backend/
├── lambda/
│   ├── lambda_function.py    # Gmail → OpenAI → DynamoDB ingestion logic
│   └── requirements.txt      # Lambda runtime dependencies (inherits ../requirements.txt)
├── requirements.txt          # Shared backend dependencies
└── scripts/
    ├── deploy_infrastructure.sh  # AWS CLI based infrastructure bootstrapper
    └── gmail_token_quickstart.py # OAuth helper for generating Gmail refresh tokens
```

`.env.example` documents the environment variables consumed by the Lambda and local tooling.

---

## Prerequisites

Install the following before working with the project:

| Tool | Purpose | Notes |
| --- | --- | --- |
| [Python 3.11](https://www.python.org/downloads/) | Lambda runtime & scripts | Configure as the default interpreter in VS Code. |
| [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) | Provision AWS/LocalStack resources | Configure with `aws configure --profile <name>` for cloud deployments. |
| [`zip`](https://infozip.sourceforge.net/Zip.html) | Package Lambda artifacts | macOS and Linux include it by default; Windows users can install via `choco install zip`. |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (optional) | Run LocalStack locally | Required only if you emulate AWS services instead of touching the cloud. |
| [`awscli-local`](https://github.com/localstack/awscli-local) (optional) | Convenience wrapper for LocalStack | Provides the `awslocal` command used throughout this guide. |

If you are using VS Code, install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) for virtualenv support and linting.

---

## Initial Project Setup

1. **Clone and open the repository.**
   ```bash
   git clone <your-fork-url>
   cd andreas-services
   code .
   ```

2. **Create and activate a Python virtual environment.**
   ```bash
   python3.11 -m venv .venv
   # macOS/Linux
   source .venv/bin/activate
   # Windows PowerShell
   # .venv\Scripts\Activate.ps1
   ```
   In VS Code, run `Python: Select Interpreter` and choose `.venv`.

3. **Install backend dependencies.**
   ```bash
   pip install --upgrade pip
   pip install -r backend/requirements.txt
   ```

4. **Copy the environment template.**
   ```bash
   cp .env.example .env
   ```
   Populate the ARN placeholders once you create the OpenAI and Gmail secrets. VS Code automatically loads `.env` files when the Python extension is enabled (or set `"python.envFile": "${workspaceFolder}/.env"` in `.vscode/settings.json`).

---

## Generating the OpenAI and Gmail Secrets

The Lambda expects two Secrets Manager entries: one with your OpenAI API key and another with Gmail OAuth credentials (client ID, client secret, refresh token, etc.). The examples below show both AWS and LocalStack workflows.

### OpenAI API Key

1. **Create or sign in to an OpenAI account.** Visit [https://platform.openai.com/](https://platform.openai.com/) and sign in with the account that will own billing for the ingestion workload.
2. **Generate a personal API key.** Navigate to **Dashboard → API keys → + Create new secret key**. Copy the generated key (`sk-...`) immediately—OpenAI only shows it once.
3. **Store the key in Secrets Manager.**
   ```bash
   # AWS
   aws secretsmanager create-secret \
     --name prod/openai \
     --secret-string '{"apiKey": "sk-your-key"}'

   # LocalStack (using awslocal)
   awslocal secretsmanager create-secret \
     --name local/openai \
     --secret-string '{"apiKey": "sk-your-key"}'
   ```
   Save the returned ARN—you will supply it to the deployment script and `.env` as `OPENAI_SECRET_ARN`.

### Gmail OAuth Credentials

1. **Create a Google Cloud project** (or reuse an existing one) via [https://console.cloud.google.com/](https://console.cloud.google.com/).
2. **Enable the Gmail API** under **APIs & Services → Library**.
3. **Configure the OAuth consent screen** under **APIs & Services → OAuth consent screen**. Add the Gmail scopes you plan to request; `https://www.googleapis.com/auth/gmail.readonly` works for read-only ingestion.
4. **Create OAuth client credentials** via **APIs & Services → Credentials → + Create credentials → OAuth client ID**. Choose **Desktop app** and download the JSON—it contains the `client_id` and `client_secret` used in the next step.
5. **Generate tokens with the bundled helper.** Run the Gmail quickstart adaptation to authorize the mailbox that receives event emails and emit the merged JSON the Lambda expects.
   ```bash
   python3 backend/scripts/gmail_token_quickstart.py \
     --client-id "<CLIENT_ID>.apps.googleusercontent.com" \
     --client-secret "<CLIENT_SECRET>" \
     --output gmail-credentials.json
   ```
   Add `--no-browser` in headless environments to finish the OAuth flow entirely within the terminal.
6. **Store the Gmail secret.**
   ```bash
   # AWS
   aws secretsmanager create-secret \
     --name prod/gmail \
     --secret-string file://gmail-credentials.json

   # LocalStack
   awslocal secretsmanager create-secret \
     --name local/gmail \
     --secret-string file://gmail-credentials.json
   ```
   Keep the ARN handy—it becomes `GMAIL_SECRET_ARN` in `.env` and when you run the deployment script. Re-run the helper whenever you revoke credentials or Google rotates the refresh token.

---

## Provisioning Infrastructure with the AWS CLI

The `deploy_infrastructure.sh` script packages the Lambda, ensures the DynamoDB table and IAM role exist, and wires the EventBridge rule. It works in both cloud and LocalStack environments by switching between `aws` and `awslocal` commands.

### Common Parameters

| Flag | Description |
| --- | --- |
| `--openai-secret-arn` | ARN of the OpenAI secret (required). |
| `--gmail-secret-arn` | ARN of the Gmail secret (required). |
| `--region` | AWS region (default `us-east-1`). |
| `--profile` | AWS CLI profile to use (cloud mode only). |
| `--local` | Use `awslocal` to target LocalStack. |
| `--table-name` | DynamoDB table name (default `Events`). |
| `--lambda-name` | Lambda function name (default `events-gmail-ingest`). |
| `--timezone` | EventBridge schedule time zone (default `America/New_York`). |
| `--openai-model` | Optional override for the `OPENAI_MODEL` environment variable. |

The script writes build artifacts to `build/` (safe to delete) and is idempotent—rerunning it updates existing resources.

### Deploying to LocalStack

1. **Start LocalStack.**
   ```bash
   docker run --rm -it \
     -p 4566:4566 \
     -p 4510-4559:4510-4559 \
     -e SERVICES="dynamodb,secretsmanager,events,iam,lambda" \
     localstack/localstack
   ```

2. **Export throwaway AWS credentials.** LocalStack still requires them for signature calculations.
   ```bash
   export AWS_ACCESS_KEY_ID=test
   export AWS_SECRET_ACCESS_KEY=test
   export AWS_SESSION_TOKEN=test
   export AWS_DEFAULT_REGION=us-east-1
   ```

3. **Create or update the secrets** using `awslocal` (see the previous section) and note their ARNs.

4. **Run the deployment script.**
   ```bash
   backend/scripts/deploy_infrastructure.sh \
     --local \
     --openai-secret-arn arn:aws:secretsmanager:us-east-1:000000000000:secret:local/openai \
     --gmail-secret-arn arn:aws:secretsmanager:us-east-1:000000000000:secret:local/gmail
   ```

5. **Invoke the Lambda locally** using `awslocal` once you upload test emails to your LocalStack secrets/DynamoDB:
   ```bash
   awslocal lambda invoke \
     --function-name events-gmail-ingest \
     --payload '{}' \
     output.json
   cat output.json
   ```

### Deploying to AWS

1. **Ensure the AWS CLI is configured** with an account and region (`aws configure --profile <name>`).
2. **Create the Secrets Manager entries** (OpenAI + Gmail) in the target region and record their ARNs.
3. **Run the deployment script with your profile.**
   ```bash
   backend/scripts/deploy_infrastructure.sh \
     --profile prod \
     --region us-east-1 \
     --openai-secret-arn arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/openai \
     --gmail-secret-arn arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/gmail
   ```

The script creates/updates the following AWS resources:

- DynamoDB table `Events` (with `category`, `source_name`, and `start_time` GSIs + streams).
- IAM role and inline policies for the Lambda.
- Lambda function `events-gmail-ingest` with necessary environment variables.
- EventBridge rule scheduled every Monday at 5:00 PM America/New_York.

Subsequent deployments reuse the same role/table and simply update code, configuration, and scheduling.

---

## Running the Lambda Handler for Debugging

The Lambda is designed to run inside AWS, but you can execute it locally once the required environment variables and AWS endpoints are available (LocalStack or AWS).

```bash
export OPENAI_SECRET_ARN=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/openai
export GMAIL_SECRET_ARN=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/gmail
export TABLE_NAME=Events
export TIMEZONE=America/New_York
export SECRETSMANAGER_ENDPOINT_URL=http://localhost:4566   # LocalStack example
export DYNAMODB_ENDPOINT_URL=http://localhost:4566         # LocalStack example
python3 - <<'PY'
from backend.lambda import lambda_function
print(lambda_function.handler({}, None))
PY
```

Make sure the AWS CLI credentials in your shell point to the correct environment (LocalStack or the cloud) before running the snippet.

---

## Updating Secrets or Redeploying

- **Rotate secrets:** Update the value with `aws secretsmanager put-secret-value` (or `awslocal ...`). The Lambda picks up new credentials on the next invocation.
- **Redeploy code/config:** Re-run `backend/scripts/deploy_infrastructure.sh` with the same parameters. The script rebuilds the package and updates the Lambda in place.
- **Clean up LocalStack artifacts:** Stop the LocalStack container and delete the `build/` directory to remove cached dependencies.

---

## Troubleshooting

| Issue | Resolution |
| --- | --- |
| `AuthenticationError` from `awslocal` or `aws` | Ensure `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` are set (even for LocalStack). |
| `zip: command not found` | Install `zip` (via `apt-get install zip`, `brew install zip`, or `choco install zip`). |
| Gmail OAuth refresh token revoked | Re-run `gmail_token_quickstart.py` with the same client ID/secret and update the stored secret. |
| Lambda cannot reach OpenAI/Gmail | Verify that the Secrets Manager ARNs reference secrets containing the required fields and that outbound internet access is available (or stub responses for testing). |

For more verbose deployment output, run the script with `bash -x backend/scripts/deploy_infrastructure.sh ...`.
