# NYC Events Aggregator – Setup Guide

## Overview

This project is a serverless NYC events aggregator that:

1. Runs a Lambda weekly to fetch emails labelled **"Events"** from Gmail
2. Uses OpenAI GPT-3.5-turbo to extract structured event data
3. Stores events in DynamoDB
4. Serves them via a REST API (API Gateway + Lambda)
5. Displays them on a static React site hosted on S3 + CloudFront

Monthly AWS cost target: **< $2** (pay-per-request DynamoDB, minimal Lambda invocations, S3 + CloudFront free tier).

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| AWS CLI | v2+ | Configured with `aws configure` |
| Python | 3.11+ | For local Lambda packaging |
| pip | latest | Used inside deploy.sh |
| Node.js | 18+ | For React build |
| npm | 9+ | Bundled with Node.js |

### AWS permissions required

Your AWS IAM user/role needs:

- `cloudformation:*`
- `iam:CreateRole`, `iam:AttachRolePolicy`, `iam:PutRolePolicy`, `iam:PassRole`
- `lambda:*`
- `dynamodb:*`
- `s3:*` (for the deployment bucket and website bucket)
- `cloudfront:*`
- `apigateway:*`
- `events:*` (EventBridge)
- `logs:*` (CloudWatch)

---

## Step 1 – Gmail API Setup

### 1.1 Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (e.g., *nyc-events*)
3. Enable the **Gmail API** under *APIs & Services → Library*

### 1.2 Create OAuth credentials

1. Go to *APIs & Services → Credentials → Create Credentials → OAuth client ID*
2. Application type: **Desktop app**
3. Download the JSON – you'll need `client_id` and `client_secret`

### 1.3 Obtain access and refresh tokens

Run the following Python snippet locally once to get your tokens:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",  # the file you downloaded above
    SCOPES,
)
creds = flow.run_local_server(port=0)

print("Access token :", creds.token)
print("Refresh token:", creds.refresh_token)
```

Copy both tokens into your `.env` file (see `.env.example`).

### 1.4 Create the "Events" Gmail label

In Gmail, create a label named exactly **Events** and apply it to the subscription
emails you want the processor to read.

---

## Step 2 – OpenAI API Key

1. Sign up at [platform.openai.com](https://platform.openai.com)
2. Create an API key under *API Keys*
3. Add it to your `.env` as `OPENAI_API_KEY`

---

## Step 3 – Create the Lambda code S3 bucket

The deployment script needs an existing S3 bucket to upload Lambda zip files.

```bash
aws s3 mb s3://my-deployment-bucket --region us-east-1
```

Set `LAMBDA_CODE_BUCKET=my-deployment-bucket` in your `.env`.

---

## Step 4 – Configure environment

```bash
cp .env.example .env
# Edit .env with your actual values
```

---

## Step 5 – Deploy everything

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:

1. Package both Lambda functions with their dependencies
2. Upload the zip files to S3
3. Deploy (or update) the CloudFormation stack
4. Retrieve API endpoint and S3 bucket from stack outputs
5. Update Lambda function code
6. Build the React app with the correct API endpoint
7. Sync the build to S3

At the end you'll see:

```
  Website : https://xxxxxxxx.cloudfront.net
  API     : https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/prod
```

---

## Step 6 – Verify

### Test the API

```bash
curl https://<api-id>.execute-api.us-east-1.amazonaws.com/prod/events
```

### Manually trigger the email processor

```bash
aws lambda invoke \
  --function-name nyc-events-email-processor \
  --payload '{}' \
  response.json
cat response.json
```

### Check CloudWatch logs

```bash
aws logs tail /aws/lambda/nyc-events-email-processor --follow
aws logs tail /aws/lambda/nyc-events-events-api --follow
```

---

## Local development

### Frontend only (mock API)

```bash
./setup-frontend.sh http://localhost:3001
cd frontend && npm start
```

This starts a dev server at `http://localhost:3000`.

### Backend (Lambda locally with SAM)

```bash
sam local invoke EmailProcessorFunction --no-event
sam local start-api --port 3001
```

---

## Updating credentials

Because Gmail OAuth tokens expire after some time (access tokens last ~1 hour;
refresh tokens are long-lived), the Lambda automatically refreshes the access
token using the stored refresh token.

If the refresh token ever becomes invalid (e.g., after revoking access), repeat
Step 1.3 and update the Lambda environment variables:

```bash
aws lambda update-function-configuration \
  --function-name nyc-events-email-processor \
  --environment "Variables={
    DYNAMODB_TABLE_NAME=nyc-events-events,
    OPENAI_API_KEY=<key>,
    GMAIL_CLIENT_ID=<id>,
    GMAIL_CLIENT_SECRET=<secret>,
    GMAIL_ACCESS_TOKEN=<new-access-token>,
    GMAIL_REFRESH_TOKEN=<new-refresh-token>
  }"
```

---

## Cost breakdown (estimated)

| Service | Usage | Monthly cost |
|---------|-------|-------------|
| Lambda (email-processor) | 4 invocations/month × 300s × 256MB | ~$0.00 (free tier) |
| Lambda (events-api) | ~1 000 requests/month × 128MB | ~$0.00 (free tier) |
| DynamoDB | Pay-per-request, ~100 writes/month | < $0.01 |
| API Gateway | ~1 000 requests/month | < $0.01 |
| S3 | ~5MB static site + lambda zips | < $0.01 |
| CloudFront | ~1GB transfer/month | < $0.10 |
| **Total** | | **< $0.15** |

---

## Troubleshooting

### "Gmail label 'Events' not found"

Ensure the label exists in your Gmail account with the **exact** name `Events`
(capital E, no trailing spaces).

### OpenAI returns non-JSON

This occasionally happens when the model adds markdown fences or a preamble.
The processor strips common fence patterns (```` ```json ... ``` ````), but if
it still fails the email is skipped and logged. Check CloudWatch logs for the
raw response.

### CloudFront serving stale content

Force a cache invalidation after deploying a new frontend build:

```bash
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name nyc-events \
  --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDomain'].OutputValue" \
  --output text)

# Find distribution ID by domain
CF_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?DomainName=='${DIST_ID}'].Id" \
  --output text)

aws cloudfront create-invalidation --distribution-id "${CF_ID}" --paths "/*"
```

### "No space left on device" during Lambda packaging

The Lambda tmp directory `/tmp` has 512MB by default. Increase it under the
Lambda function's *Configuration → General configuration → Ephemeral storage*.

---

## Architecture diagram

```
EventBridge (weekly)
       │
       ▼
┌─────────────────────┐     Gmail API      ┌──────────┐
│  email-processor    │ ──────────────────▶│  Gmail   │
│  Lambda             │                    └──────────┘
│                     │     OpenAI API     ┌──────────┐
│                     │ ──────────────────▶│  OpenAI  │
└─────────┬───────────┘                    └──────────┘
          │ PutItem
          ▼
    ┌───────────┐
    │ DynamoDB  │
    │  (events) │
    └─────┬─────┘
          │ Scan / GetItem
          ▼
┌─────────────────────┐    API Gateway    ┌──────────────┐
│  events-api Lambda  │◀─────────────────│  REST API    │
└─────────────────────┘                   └──────┬───────┘
                                                 │ HTTPS
                                          ┌──────▼───────┐
                                          │  CloudFront  │
                                          │  + S3 (SPA)  │
                                          └──────────────┘
```
