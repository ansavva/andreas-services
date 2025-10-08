# events.andreas.services — Gmail Event Ingestion

This repository contains the Gmail ingestion Lambda for the `events.andreas.services` project together with a reusable
**CloudFormation template**. The function retrieves Gmail messages labeled **Events**, extracts structured event data via the
OpenAI API, deduplicates items in DynamoDB, and logs ingestion metrics.

The CloudFormation workflow keeps local and cloud deployments identical—package the Lambda once, then deploy the same stack to
AWS or LocalStack.

---

## Repository Layout

```
backend/
├── cloudformation/
│   └── events-stack.yaml       # CloudFormation template for DynamoDB, Lambda, EventBridge, IAM
├── lambda/
│   ├── lambda_function.py      # Gmail → OpenAI → DynamoDB ingestion handler
│   └── requirements.txt        # Lambda-specific dependency overrides (extends ../requirements.txt)
├── requirements.txt            # Shared backend dependencies
└── scripts/
    ├── build_lambda_bundle.sh  # Creates the deployment bundle consumed by CloudFormation
    └── gmail_token_quickstart.py # Gmail OAuth helper to mint refresh tokens
```

`.env.example` documents the runtime environment variables that the Lambda consumes during local testing.

---

## Prerequisites

Install the following tools before working with the project:

| Tool | Purpose | Notes |
| --- | --- | --- |
| [Python 3.11](https://www.python.org/downloads/) | Lambda runtime & helper scripts | Set as the default interpreter in VS Code. |
| [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) | Package and deploy CloudFormation stacks | Configure a profile with `aws configure --profile <name>` for real AWS deployments. |
| [`zip`](https://infozip.sourceforge.net/Zip.html) | Bundles Lambda artifacts | Included on macOS/Linux; Windows users can install via `choco install zip`. |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) (optional) | Runs LocalStack locally | Required only when emulating AWS services. |
| [`awscli-local`](https://github.com/localstack/awscli-local) (optional) | Convenience wrapper for LocalStack | Supplies the `awslocal` command used in this guide. |

VS Code users should also install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) for virtual environment support.

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
   Populate the ARN placeholders after you create the OpenAI and Gmail secrets. VS Code automatically loads `.env` files when the Python extension is enabled (or set `"python.envFile": "${workspaceFolder}/.env"` in `.vscode/settings.json`).

---

## Generating the OpenAI and Gmail Secrets

The Lambda expects two Secrets Manager entries: one storing your OpenAI API key and another storing Gmail OAuth credentials
(client ID, client secret, refresh token, etc.). The commands below show both AWS and LocalStack workflows.

### OpenAI API Key

1. **Create or sign in to an OpenAI account.** Visit [https://platform.openai.com/](https://platform.openai.com/) and sign in with the account that will own billing for the ingestion workload.
2. **Generate a personal API key.** Navigate to **Dashboard → API keys → + Create new secret key**. Copy the generated key (`sk-...`) immediately—OpenAI shows it only once.
3. **Store the key in Secrets Manager.**
   ```bash
   # AWS
   aws secretsmanager create-secret \
     --name prod/openai \
     --secret-string '{"apiKey": "sk-your-key"}'

   # LocalStack
   awslocal secretsmanager create-secret \
     --name local/openai \
     --secret-string '{"apiKey": "sk-your-key"}'
   ```
   Save the returned ARN—you will provide it to CloudFormation and to your `.env` file as `OPENAI_SECRET_ARN`.

### Gmail OAuth Credentials

1. **Create a Google Cloud project** (or reuse an existing one) via [https://console.cloud.google.com/](https://console.cloud.google.com/).
2. **Enable the Gmail API** under **APIs & Services → Library**.
3. **Configure the OAuth consent screen** under **APIs & Services → OAuth consent screen**. Add the Gmail scopes you require; `https://www.googleapis.com/auth/gmail.readonly` covers read-only ingestion.
4. **Create OAuth client credentials** via **APIs & Services → Credentials → + Create credentials → OAuth client ID**. Choose **Desktop app** and download the JSON—it contains the `client_id` and `client_secret` for the next step.
5. **Generate tokens with the bundled helper.** Run the quickstart adaptation to authorize the mailbox that receives event emails and produce the merged JSON expected by the Lambda.
   ```bash
   python3 backend/scripts/gmail_token_quickstart.py \
     --client-id "<CLIENT_ID>.apps.googleusercontent.com" \
     --client-secret "<CLIENT_SECRET>" \
     --output gmail-credentials.json
   ```
   Add `--no-browser` in headless environments to complete the OAuth flow entirely within the terminal.
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
   Keep the ARN handy—it becomes `GMAIL_SECRET_ARN` in both `.env` and the CloudFormation parameters. Re-run the helper whenever you revoke credentials or Google rotates the refresh token.

---

## Building the Lambda Bundle

CloudFormation expects a ready-to-zip directory that already contains the Lambda source and its dependencies. Run the helper script from the repository root whenever you update the Lambda code or its requirements:

```bash
./backend/scripts/build_lambda_bundle.sh
```

The script creates `build/lambda/` (ignored by Git) containing the handler and vendored dependencies. Subsequent CloudFormation packaging steps reference this directory.

---

## Deploying with CloudFormation

CloudFormation handles both the AWS and LocalStack environments; only the CLI binary (`aws` vs. `awslocal`) and artifact bucket differ. The examples below assume you run them from the repository root.

### Common Parameters

| Parameter | Description |
| --- | --- |
| `OpenAISecretArn` | ARN of the OpenAI secret (required). |
| `GmailSecretArn` | ARN of the Gmail secret (required). |
| `TableName` | DynamoDB table name (default `Events`). |
| `LambdaFunctionName` | Lambda function name (default `events-gmail-ingest`). |
| `ScheduleExpression` | Cron expression for the EventBridge rule (defaults to Mondays at 5 PM). |
| `ScheduleTimezone` | Time zone for the schedule (default `America/New_York`). |
| `OpenAIModel` | Optional override for the OpenAI model. |
| `SecretsManagerEndpointUrl` / `DynamoDbEndpointUrl` | Set to `http://host.docker.internal:4566` when the Lambda should call LocalStack endpoints. |

### Deploying to AWS

1. **Choose or create an S3 bucket** for packaging artifacts (e.g., `events-artifacts-<account-id>`).
2. **Package the template.**
   ```bash
   aws cloudformation package \
     --template-file backend/cloudformation/events-stack.yaml \
     --s3-bucket <artifact-bucket> \
     --output-template-file build/packaged-template.yaml
   ```
3. **Deploy the stack.**
   ```bash
   aws cloudformation deploy \
     --template-file build/packaged-template.yaml \
     --stack-name events-gmail-stack \
     --capabilities CAPABILITY_NAMED_IAM \
     --parameter-overrides \
       OpenAISecretArn=<openai-secret-arn> \
       GmailSecretArn=<gmail-secret-arn>
   ```
   Add additional `ParameterKey=Value` pairs to override defaults as needed. The command outputs the DynamoDB table and Lambda ARNs on success.

### Deploying to LocalStack

1. **Start LocalStack.**
   ```bash
   docker run --rm -it \
     -p 4566:4566 \
     -p 4510-4559:4510-4559 \
     -e SERVICES="dynamodb,secretsmanager,events,iam,lambda,cloudformation,s3" \
     localstack/localstack
   ```
2. **Export placeholder AWS credentials** (LocalStack still validates that they exist).
   ```bash
   export AWS_ACCESS_KEY_ID=test
   export AWS_SECRET_ACCESS_KEY=test
   export AWS_REGION=us-east-1
   ```
3. **Create an artifact bucket inside LocalStack.**
   ```bash
   awslocal s3 mb s3://local-artifacts
   ```
4. **Package the template.**
   ```bash
   awslocal cloudformation package \
     --template-file backend/cloudformation/events-stack.yaml \
     --s3-bucket local-artifacts \
     --output-template-file build/packaged-template.yaml
   ```
5. **Deploy the stack.**
   ```bash
   awslocal cloudformation deploy \
     --template-file build/packaged-template.yaml \
     --stack-name events-gmail-stack \
     --capabilities CAPABILITY_NAMED_IAM \
     --parameter-overrides \
       OpenAISecretArn=local/openai \
       GmailSecretArn=local/gmail \
       SecretsManagerEndpointUrl=http://host.docker.internal:4566 \
       DynamoDbEndpointUrl=http://host.docker.internal:4566
   ```
   Update the secret ARNs if you chose different names.

---

## Local Testing Tips

* **Invoke the Lambda locally** by exporting the same environment variables defined in `.env` and running `python3 backend/lambda/lambda_function.py` within a harness of your choosing (for example, `lambda_function.handler({}, {})`).
* **Run static checks** with `python3 -m compileall backend/lambda backend/scripts` before packaging to catch syntax errors early.
* **Tail LocalStack logs** for troubleshooting Lambda executions: `docker logs -f <localstack-container-id>`.

---

## Cleanup

To remove the deployed resources, delete the stack with the same CLI used for deployment:

```bash
# AWS
aws cloudformation delete-stack --stack-name events-gmail-stack

# LocalStack
awslocal cloudformation delete-stack --stack-name events-gmail-stack
```

Remember to empty or delete the artifact bucket separately if you no longer need the uploaded Lambda bundles.
