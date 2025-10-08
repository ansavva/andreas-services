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
   Use the returned ARN as `OPENAI_SECRET_ARN` in `.env` and CDK context parameters.  The Lambda expects the secret JSON to contain an `apiKey` field.

### Gmail OAuth Credentials

1. **Create a Google Cloud project.** Visit [https://console.cloud.google.com/](https://console.cloud.google.com/), click the project selector, and create (or select) a project that will host the Gmail API integration.
2. **Enable the Gmail API.** In the Google Cloud Console, go to **APIs & Services → Library**, search for “Gmail API,” and click **Enable**.
3. **Configure the OAuth consent screen.** Under **APIs & Services → OAuth consent screen**, create either an internal or external consent screen (internal is simplest for Workspace accounts).  Add the Gmail scopes you plan to request—`https://www.googleapis.com/auth/gmail.readonly` works for read-only ingestion.
4. **Create OAuth client credentials.** Navigate to **APIs & Services → Credentials → + Create credentials → OAuth client ID**.  Choose **Desktop app** (for manual token generation) and download the resulting JSON—it will contain a `client_id` and `client_secret`.
5. **Generate refresh tokens.** Run the bundled helper (a direct adaptation of Google’s [Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)) to authorize the Gmail account that receives event emails.  The script reads the OAuth client ID/secret you just created, opens the browser-based consent screen, and writes out the merged token payload you will store in Secrets Manager.

   ```bash
   python backend/scripts/gmail_token_quickstart.py \
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
   Point `GMAIL_SECRET_ARN` to the ARN returned by this command.  The Lambda expects the secret JSON to include the refresh token so it can mint short-lived access tokens automatically.  If Google ever revokes the refresh token (for example, you do not use it for an extended period or you regenerate the OAuth client secret), rerun `gmail_token_quickstart.py` with the updated credentials to produce a fresh JSON payload and update the secret.

Once both secrets exist, reference their ARNs in `.env` (for local runs) and pass them to the CDK stack via context parameters when deploying.

---

## Running the Lambda Locally

The Lambda reaches out to three external systems—AWS Secrets Manager, Gmail, and OpenAI—so a “local” run still requires valid credentials.  There are two common approaches.

### Option A — Invoke against real AWS services

1. **Provision supporting resources (one-time).**
   ```bash
   aws dynamodb create-table \
     --table-name Events \
     --attribute-definitions AttributeName=id,AttributeType=S \
     --key-schema AttributeName=id,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST

   aws dynamodb update-table \
     --table-name Events \
     --attribute-definitions AttributeName=category,AttributeType=S AttributeName=source_name,AttributeType=S AttributeName=start_time,AttributeType=S \
     --global-secondary-index-updates '[{"Create":{"IndexName":"category-index","KeySchema":[{"AttributeName":"category","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}},{"Create":{"IndexName":"source_name-index","KeySchema":[{"AttributeName":"source_name","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}},{"Create":{"IndexName":"start_time-index","KeySchema":[{"AttributeName":"start_time","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}}]'

   aws secretsmanager create-secret --name <openai-secret-name> --secret-string '{"apiKey": "sk-..."}'
   aws secretsmanager create-secret --name <gmail-secret-name> --secret-string @gmail-credentials.json
   ```
   The Gmail credentials JSON must contain the OAuth tokens generated for the `events.andreas.services` Gmail account.

2. **Export environment variables in your shell or rely on `.env`.**
   ```bash
   export OPENAI_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:openai-api
   export GMAIL_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:gmail-credentials
   export TABLE_NAME=Events
   export TIMEZONE=America/New_York
   export AWS_PROFILE=<your-aws-profile>
   export AWS_REGION=us-east-1
   ```

3. **Run an ad-hoc invocation from VS Code’s integrated terminal.**
   ```bash
   python - <<'PY'
   import json
   from backend.lambda.lambda_function import handler

   result = handler({}, None)
   print(json.dumps(result, indent=2, default=str))
   PY
   ```
   The handler will pull real Gmail messages labelled `Events`, process them with OpenAI, and write into DynamoDB.

4. **Inspect CloudWatch Logs** (optional) to review the run: `aws logs tail /aws/lambda/<function-name> --follow`.

### Option B — Emulate AWS with LocalStack

1. **Start LocalStack.**
   ```bash
   docker run --rm -it -p 4566:4566 -p 4510-4559:4510-4559 localstack/localstack
   ```

2. **Point AWS SDKs to LocalStack and bootstrap resources.**
   ```bash
   export AWS_ACCESS_KEY_ID=test
   export AWS_SECRET_ACCESS_KEY=test
   export AWS_DEFAULT_REGION=us-east-1
   export AWS_ENDPOINT_URL=http://localhost:4566
   export SECRETSMANAGER_ENDPOINT_URL=http://localhost:4566
   export DYNAMODB_ENDPOINT_URL=http://localhost:4566

   aws --endpoint-url $AWS_ENDPOINT_URL dynamodb create-table \
     --table-name Events \
     --attribute-definitions AttributeName=id,AttributeType=S \
     --key-schema AttributeName=id,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST

   aws --endpoint-url $AWS_ENDPOINT_URL secretsmanager create-secret \
     --name local/openai \
     --secret-string '{"apiKey": "test-openai"}'
   aws --endpoint-url $AWS_ENDPOINT_URL secretsmanager create-secret \
     --name local/gmail \
     --secret-string @gmail-credentials.json
   ```

3. **Update `.env` to use the LocalStack ARNs and endpoint overrides.**
   ```env
   OPENAI_SECRET_ARN=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/openai
   GMAIL_SECRET_ARN=arn:aws:secretsmanager:us-east-1:000000000000:secret:local/gmail
   TABLE_NAME=Events
   TIMEZONE=America/New_York
   SECRETSMANAGER_ENDPOINT_URL=http://localhost:4566
   DYNAMODB_ENDPOINT_URL=http://localhost:4566
   ```

4. **Invoke the handler** exactly as in Option A.  Gmail and OpenAI calls will still reach their live APIs—mock them by temporarily editing `lambda_function.py` or by setting test credentials.

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
- **Task automation:** Add VS Code tasks that run `python -m compileall backend/lambda` or `cdk synth` for quick verification.

---

## Verification Commands

Run these quick checks before committing changes:

```bash
# Byte-compile the Lambda source to catch syntax errors
python -m compileall backend/lambda

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
