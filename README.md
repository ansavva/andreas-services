# events.andreas.services — Gmail Event Ingestion

This repository contains the scheduled Gmail ingestion Lambda and the AWS CDK infrastructure that supports the `events.andreas.services` project.  The Lambda polls Gmail for messages labelled **Events**, extracts structured event metadata via the OpenAI API, and stores the results in DynamoDB.  The CDK stack provisions the Lambda, its schedule, the DynamoDB table, and the required IAM permissions.

The guide below walks you through setting up a local development environment in Visual Studio Code (VS Code), running ad-hoc Lambda executions, and deploying the infrastructure with the AWS Cloud Development Kit (CDK).

---

## Repository Layout

```
backend/
├── cdk/
│   ├── lambda_stack.py       # DynamoDB, Lambda, EventBridge rule, IAM
│   └── ...                   # (Secrets stack lives alongside this file)
├── lambda/
│   ├── lambda_function.py    # Gmail → OpenAI → DynamoDB ingestion logic
│   └── requirements.txt      # Lambda runtime dependencies (inherits ../requirements.txt)
├── models/                   # Placeholder for shared Pydantic models
└── requirements.txt          # Shared backend dependencies
```

An `.env.example` file at the repository root documents the environment variables consumed by the Lambda and local tooling.

---

## Prerequisites

Install the following tools before working with the project locally:

| Tool | Purpose | Notes |
| --- | --- | --- |
| [Python 3.11](https://www.python.org/downloads/) | Lambda runtime & unit tooling | Ensure it is available in VS Code. |
| [Node.js 18+](https://nodejs.org/en/download/) | Required by the AWS CDK CLI | `nvm` is handy for managing versions. |
| [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) | Manage AWS resources & LocalStack | Configure with `aws configure --profile <name>`. |
| [AWS CDK CLI](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html) | Synthesize/deploy infrastructure | Install globally with `npm install -g aws-cdk`. |
| [VS Code](https://code.visualstudio.com/) with the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) and [AWS Toolkit](https://marketplace.visualstudio.com/items?itemName=AmazonWebServices.aws-toolkit-vscode) | Editing, linting, local lambda invocations | The AWS Toolkit streamlines invoking and debugging Lambdas locally. |
| (Optional) [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Local emulation via LocalStack | Required only if you plan to emulate AWS services locally. |
| (Optional) [`aws-cdk-local`](https://github.com/localstack/aws-cdk-local) | Deploy the CDK app against LocalStack | Install with `npm install -g aws-cdk-local`. |

---

## Initial Setup in VS Code

1. **Clone & open the repository.**
   ```bash
   git clone <your-fork-url>
   cd savva-events
   code .
   ```

2. **Create and select a Python virtual environment.**
   ```bash
   python3.11 -m venv .venv
   # macOS/Linux
   source .venv/bin/activate
   # Windows (PowerShell)
   # .venv\Scripts\Activate.ps1
   ```
   In VS Code, use `Ctrl/Cmd + Shift + P` → “Python: Select Interpreter” and choose `.venv`.

3. **Install dependencies.**
   ```bash
   pip install --upgrade pip
   pip install -r backend/requirements.txt
   ```
   The Lambda directory inherits these dependencies via `backend/lambda/requirements.txt`.

4. **Copy the environment template.**
   ```bash
   cp .env.example .env
   ```
   Update the ARN placeholders with the Secrets Manager resources that hold your OpenAI API key and Gmail OAuth credentials.  VS Code automatically loads `.env` files when the Python extension is active (or configure `"python.envFile": "${workspaceFolder}/.env"` in `.vscode/settings.json`).

5. **(Optional) Install CDK dependencies in a separate virtualenv.**
   ```bash
   cd backend/cdk
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r ../requirements.txt
   pip install aws-cdk-lib aws-cdk.aws-lambda-python-alpha
   ```
   When you are done, return to the repository root.

---

## Obtaining the OpenAI & Gmail Secrets

The Lambda expects **two** secrets in AWS Secrets Manager: one that contains an OpenAI API key and another that contains Gmail OAuth credentials (including refresh tokens).  The steps below outline how to create each secret from scratch.

### OpenAI API Key

1. **Create or sign in to an OpenAI account.** Visit [https://platform.openai.com/](https://platform.openai.com/) and sign in with the account that will own billing for the ingestion workload.
2. **Generate a personal API key.** Navigate to **Dashboard → API keys → + Create new secret key**.  Copy the generated key (`sk-...`) immediately—OpenAI will only show it once.
3. **Store the key in Secrets Manager.**
   ```bash
   aws secretsmanager create-secret \
     --name prod/openai \
     --secret-string '{"apiKey": "sk-your-key"}'
   ```
   For LocalStack development, add `--endpoint-url http://localhost:4566` and choose a local secret name (for example, `local/openai`).
   Use the returned ARN as `OPENAI_SECRET_ARN` in `.env` and CDK context parameters.  The Lambda expects the secret JSON to contain an `apiKey` field.

### Gmail OAuth Credentials

1. **Create a Google Cloud project.** Visit [https://console.cloud.google.com/](https://console.cloud.google.com/), click the project selector, and create (or select) a project that will host the Gmail API integration.
2. **Enable the Gmail API.** In the Google Cloud Console, go to **APIs & Services → Library**, search for “Gmail API,” and click **Enable**.
3. **Configure the OAuth consent screen.** Under **APIs & Services → OAuth consent screen**, create either an internal or external consent screen (internal is simplest for Workspace accounts).  Add the Gmail scopes you plan to request—`https://www.googleapis.com/auth/gmail.readonly` works for read-only ingestion.
4. **Create OAuth client credentials.** Navigate to **APIs & Services → Credentials → + Create credentials → OAuth client ID**.  Choose **Desktop app** (for manual token generation) and download the resulting JSON—it will contain a `client_id` and `client_secret`.
5. **Generate refresh tokens.** Run the bundled helper (a direct adaptation of Google’s [Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)) to authorize the Gmail account that receives event emails.  The script reads the OAuth client ID/secret you just created, opens the browser-based consent screen, and writes out the merged token payload you will store in Secrets Manager.

   ```bash
   python3 backend/scripts/gmail_token_quickstart.py \
     --client-id "<CLIENT_ID>.apps.googleusercontent.com" \
     --client-secret "<CLIENT_SECRET>" \
     --output gmail-credentials.json
   ```

   If you are working on a headless machine, add `--no-browser` to complete the flow entirely in the terminal.  The command produces `gmail-credentials.json`, which contains the access token, refresh token, and metadata in the exact structure the Lambda expects.

6. **Combine the client and token JSON.** (Already handled if you ran the helper above.)  Ensure the final secret JSON resembles:
   ```json
   {
     "client_id": "...apps.googleusercontent.com",
     "client_secret": "...",
     "refresh_token": "1//...",
     "token": "ya29...",
     "token_uri": "https://oauth2.googleapis.com/token",
     "scopes": [
       "https://www.googleapis.com/auth/gmail.readonly"
     ]
   }
   ```
7. **Store the Gmail credentials in Secrets Manager.**
   ```bash
   aws secretsmanager create-secret \
     --name prod/gmail \
     --secret-string file://gmail-credentials.json
   ```
   For LocalStack development, repeat the command with `--endpoint-url http://localhost:4566` and a local secret name such as `local/gmail`.
   Point `GMAIL_SECRET_ARN` to the ARN returned by this command.  The Lambda expects the secret JSON to include the refresh token so it can mint short-lived access tokens automatically.  If Google ever revokes the refresh token (for example, you do not use it for an extended period or you regenerate the OAuth client secret), rerun `gmail_token_quickstart.py` with the updated credentials to produce a fresh JSON payload and update the secret.

Once both secrets exist, reference their ARNs in `.env` (for local runs) and pass them to the CDK stack via context parameters when deploying.

When you are working entirely within LocalStack, you can use the same AWS CLI commands shown above by swapping in the LocalStack endpoint (or using the `awslocal` wrapper from the `awscli-local` package).  This keeps parity between your local workflow and your real AWS environments.

---

## Running the Lambda Locally

The Lambda reaches out to three external systems—AWS Secrets Manager, Gmail, and OpenAI—so a “local” run still requires valid credentials.  To avoid touching live AWS resources, you can emulate Secrets Manager and DynamoDB with **LocalStack**.

### Step 1 — Install LocalStack

LocalStack can run either as a Docker container (recommended) or directly via `pip` inside a Python virtual environment.

```bash
# Using Docker (preferred)
docker pull localstack/localstack

# Or install the CLI locally
pip install "localstack[full]"
```

If you use the LocalStack CLI, start it with `localstack start`.  When running in Docker, follow the next step.

### Step 2 — Launch LocalStack

```bash
docker run --rm -it \
  -p 4566:4566 \
  -p 4510-4559:4510-4559 \
  -e SERVICES="dynamodb,secretsmanager" \
  localstack/localstack
```

Leave this container running in a separate terminal.  The default edge endpoint (`http://localhost:4566`) will now proxy DynamoDB and Secrets Manager calls.

### Step 3 — Create the LocalStack secrets

Provision the OpenAI and Gmail credentials exactly as you would in AWS Secrets Manager, but point the AWS CLI at the LocalStack endpoint.  The examples below assume you have installed [`awscli-local`](https://github.com/localstack/awscli-local) (`pip install awscli-local`) so that the `awslocal` wrapper automatically injects the correct endpoint URL.

```bash
# OpenAI API key
awslocal secretsmanager create-secret \
  --name local/openai \
  --secret-string '{"apiKey": "sk-your-key"}'

# Gmail OAuth bundle
awslocal secretsmanager create-secret \
  --name local/gmail \
  --secret-string file://gmail-credentials.json
```

Take note of the returned ARNs; you will pass them to the CDK stack in the next step.

### Step 4 — Deploy the CDK stack with `aws-cdk-local`

Deploying with [`cdklocal`](https://github.com/localstack/aws-cdk-local) exercises the same CDK application that you use for real AWS regions, ensuring environment parity.  Install the CLI (`npm install -g aws-cdk-local`) and then bootstrap and deploy against LocalStack.  Because `cdklocal` still looks for AWS credentials, export throwaway values (or run `aws configure` against a dedicated profile) before bootstrapping:

```bash
cd backend/cdk
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_REGION=us-east-1
cdklocal bootstrap aws://000000000000/us-east-1
cdklocal deploy LambdaStack \
  --context openaiSecretArn=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/openai \
  --context gmailSecretArn=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/gmail
cd ..
```

This command sequence creates the DynamoDB table, Lambda function, EventBridge rule, and IAM permissions inside LocalStack exactly as `cdk deploy` would do in AWS.  When you iterate locally, re-run `cdklocal deploy` after making infrastructure changes.

### Step 5 — Configure environment variables

Update `.env` (or export variables in the terminal) so the Lambda uses the LocalStack resources you just deployed.

```env
OPENAI_SECRET_ARN=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/openai
GMAIL_SECRET_ARN=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/gmail
TABLE_NAME=Events
TIMEZONE=America/New_York
SECRETSMANAGER_ENDPOINT_URL=http://localhost:4566
DYNAMODB_ENDPOINT_URL=http://localhost:4566
```

### Step 6 — Invoke the handler from VS Code

With LocalStack running and environment variables set, execute the Lambda handler directly:

```bash
python3 - <<'PY'
import json
from backend.lambda.lambda_function import handler

result = handler({}, None)
print(json.dumps(result, indent=2, default=str))
PY
```

The handler will communicate with LocalStack for DynamoDB and Secrets Manager while still reaching Gmail and OpenAI over the public internet.  To fully isolate tests, patch `lambda_function.py` to stub those external calls or inject mock clients in your test harness.

---

## Working with the AWS CDK

1. **Bootstrap your AWS environment** (only once per account/region).
   ```bash
   cdk bootstrap aws://<account-id>/<region>
   ```

2. **Synthesize the CloudFormation template.**
   ```bash
   cd backend/cdk
   cdk synth
   ```

3. **Deploy the stack.**
   ```bash
   cdk deploy LambdaStack \
     --context openaiSecretArn=arn:aws:... \
     --context gmailSecretArn=arn:aws:...
   ```
   The stack outputs the DynamoDB table name and the Lambda ARN.

---

## Helpful VS Code Tips

- **Python linting & formatting:** Enable `ruff` or `flake8` if you prefer static analysis.  Configure `"python.formatting.provider": "black"` for consistent formatting.
- **AWS Toolkit invocations:** Right-click `backend/lambda/lambda_function.py` → “Run Locally” to launch the handler with custom payloads.  Provide environment variables in the dialog or via `.env`.
- **Debugging:** Create `.vscode/launch.json` with a `python` configuration whose `module` is `backend.lambda.lambda_function` and add `"envFile": "${workspaceFolder}/.env"`.
- **Task automation:** Add VS Code tasks that run `python3 -m compileall backend/lambda` or `cdk synth` for quick verification.

---

## Verification Commands

Run these quick checks before committing changes:

```bash
# Byte-compile the Lambda source to catch syntax errors
python3 -m compileall backend/lambda

# Optional: run CDK synthesis in CI mode
cd backend/cdk && cdk synth && cd ../..
```

---

## Troubleshooting

- **Gmail API quota or auth errors:** Ensure the OAuth token in Secrets Manager is fresh; re-run the Gmail OAuth flow if you see `invalid_grant` errors.
- **OpenAI `401 Unauthorized`:** Double-check that the OpenAI secret JSON uses the key `apiKey` or `api_key`.
- **DynamoDB throughput throttling:** The table defaults to on-demand mode, but LocalStack sometimes needs a restart if you encounter throttling errors locally.
- **Missing Python packages:** Confirm you are using the project’s virtual environment and that `pip install -r backend/requirements.txt` completed successfully.

With these steps you can iterate quickly in VS Code, run the Lambda against live or emulated services, and deploy the infrastructure via CDK when you are ready.
