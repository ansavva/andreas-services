# Claude Instructions – nyc-events-aggregator

## What this service does

Aggregates NYC event listings from Gmail subscriptions:
1. **EventBridge** triggers `email-processor` Lambda weekly
2. Lambda fetches emails with the **"Events"** Gmail label, extracts structured event data via OpenAI GPT-3.5-turbo, stores results in DynamoDB
3. **events-api** Lambda serves a REST API via API Gateway
4. React SPA (S3 + CloudFront) displays events at `events.andreas.services`

## Directory Structure

```
nyc-events-aggregator/
├── cloudformation.yaml          # AWS infrastructure (DynamoDB, Lambdas, API GW, S3, CloudFront)
├── deploy.sh                    # End-to-end deployment script
├── setup-frontend.sh            # Frontend local dev bootstrap
├── .env.example                 # Required env var template
├── lambda/
│   ├── email-processor/
│   │   ├── lambda_function.py   # Gmail → OpenAI → DynamoDB
│   │   └── requirements.txt
│   └── events-api/
│       └── lambda_function.py   # GET /events, GET /events/{id}
├── frontend/
│   ├── package.json
│   ├── tailwind.config.js
│   └── src/
│       ├── App.js               # Main SPA (ThemeProvider, EventCard, etc.)
│       ├── index.css            # CSS custom properties for light/dark theme
│       ├── lib/utils.js         # formatDate, isUpcoming, truncate, displayUrl
│       └── components/         # UI component directory
└── docs/
    └── SETUP.md                 # Full deployment walkthrough
```

## Known Tech Debt (to align with repo patterns)

The following should be addressed when time allows — see root `CLAUDE.md` for the patterns to follow:

1. **Frontend build tool**: Currently uses Create React App (`react-scripts`). Should migrate to **Vite** like storybook and humbugg.
2. **TypeScript**: Currently plain JavaScript. Should add TypeScript (`tsconfig.json`) like other services.
3. **ESLint + Prettier**: Not yet configured. Should add `.eslintrc.json` and `.prettierrc`.
4. **GitHub Actions**: Currently uses a manual `deploy.sh` shell script. Should have `.github/workflows/deploy-nyc-events.yml` with path-based filtering and OIDC auth, matching the storybook pattern.
5. **CloudFormation vs Terraform**: This service uses CloudFormation. The shared Route53/ACM resources live in `terraform/`. When the CloudFormation stack creates CloudFront, it should reference the shared wildcard ACM certificate (`*.andreas.services`) and create a Route53 record in the shared zone, rather than managing DNS/TLS independently.
6. **Frontend folder structure**: Currently flat. Should follow `apis/ components/ hooks/ context/ utils/ types/ pages/` layout used by storybook.

## Environment Variables

All secrets live in GitHub Actions environment (`nyc-events-production`), never in committed files.

| Variable | Where set | Description |
|----------|-----------|-------------|
| `OPENAI_API_KEY` | GitHub secret | OpenAI API key |
| `GMAIL_CLIENT_ID` | GitHub secret | Google OAuth client ID |
| `GMAIL_CLIENT_SECRET` | GitHub secret | Google OAuth client secret |
| `GMAIL_ACCESS_TOKEN` | GitHub secret | OAuth access token (auto-refreshed by Lambda) |
| `GMAIL_REFRESH_TOKEN` | GitHub secret | OAuth refresh token |
| `LAMBDA_CODE_BUCKET` | GitHub var | S3 bucket for Lambda zip uploads |
| `AWS_REGION` | GitHub var | Target AWS region (us-east-1) |

For local development, copy `.env.example` to `.env` and fill in values.

## Lambda Functions

### email-processor

- **Trigger**: EventBridge `cron(0 8 ? * MON *)` — every Monday 08:00 UTC
- **Runtime**: Python 3.11, 256MB, 300s timeout
- **What it does**:
  1. Authenticates with Gmail via OAuth (auto-refreshes token)
  2. Lists messages with the `Events` label from the past 7 days
  3. Skips emails already in DynamoDB (idempotency check by `email_id`)
  4. Converts HTML email bodies to plain text via `html2text`
  5. Sends content to GPT-3.5-turbo → parses JSON array of events
  6. Stores each event in DynamoDB with a UUID `event_id`

### events-api

- **Trigger**: API Gateway (`GET /events`, `GET /events/{id}`, `OPTIONS` for CORS)
- **Runtime**: Python 3.11, 128MB, 30s timeout
- **Endpoints**:
  - `GET /events` — list all events; `?upcoming=true` filters to date ≥ today
  - `GET /events/{id}` — fetch single event by primary key
  - `OPTIONS /*` — CORS preflight (returns CORS headers)
- **Serialisation**: Custom `DecimalEncoder` handles DynamoDB `Decimal` → int/float

## DynamoDB Schema

Table: `nyc-events-events` (pay-per-request)
Primary key: `event_id` (string, UUID)

| Field | Type | Notes |
|-------|------|-------|
| `event_id` | String | UUID primary key |
| `email_id` | String | Gmail message ID (used for dedup) |
| `event_name` | String | |
| `date` | String | YYYY-MM-DD or empty |
| `time` | String | e.g. "7:00 PM" or empty |
| `venue` | String | |
| `price` | String | |
| `description` | String | |
| `links` | List[String] | URLs extracted from email |
| `email_subject` | String | |
| `email_sender` | String | |
| `created_at` | String | ISO timestamp |
| `source_email_date` | String | RFC 2822 date from email header |

## AWS Credentials

Follow the repo-wide rule — never hardcode credentials. The Lambda IAM role provides
access to DynamoDB automatically. Locally, use `aws configure`.

## Deployment

```bash
cp .env.example .env   # fill in secrets
./deploy.sh            # packages lambdas, deploys CFn, builds + syncs frontend
```

See `docs/SETUP.md` for the full guide including Gmail OAuth setup.
