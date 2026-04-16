# Claude Instructions – scout

## What this service does

Aggregates NYC event listings from Gmail subscriptions and displays them at `scout.andreas.services`:

1. **EventBridge** triggers `email-processor` Lambda every Monday at 08:00 UTC
2. Lambda fetches emails with the **"Events"** Gmail label, extracts structured event data via Claude (claude-haiku-4-5), stores results in DynamoDB
3. **events-api** Lambda serves a REST API via API Gateway
4. Vite + React + TypeScript SPA (S3 + CloudFront) displays events

## Directory Structure

```
scout/
├── cloudformation.yaml          # AWS infrastructure (DynamoDB, Lambdas, API GW, S3, CloudFront, Route53)
├── deploy.sh                    # Local/manual end-to-end deployment script
├── setup-frontend.sh            # Frontend local dev bootstrap
├── .env.example                 # Required env var template (copy to .env for local use)
├── lambda/
│   ├── email-processor/
│   │   ├── lambda_function.py   # Gmail → OpenAI → DynamoDB
│   │   └── requirements.txt
│   └── events-api/
│       └── lambda_function.py   # GET /events, GET /events/{id}
├── frontend/
│   ├── index.html               # Vite entry point
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── .eslintrc.json
│   ├── .prettierrc
│   └── src/
│       ├── main.tsx             # React entry point
│       ├── App.tsx              # Root component
│       ├── index.css            # CSS custom properties for light/dark theme
│       ├── vite-env.d.ts        # VITE_ env var types
│       ├── components/          # Header, EventCard, EventFilters, SkeletonCard
│       ├── context/             # ThemeContext (light/dark mode)
│       ├── hooks/               # useEvents (API fetching)
│       ├── utils/               # formatters (formatDate, isUpcoming, etc.)
│       └── types/               # Event, SortOrder, Theme interfaces
└── docs/
    └── SETUP.md                 # Full deployment walkthrough
```

## Shared Infrastructure

The CloudFormation stack references (but does not own) two shared resources from `terraform/envs/shared`:

- **ACM wildcard certificate** (`*.andreas.services`) — looked up at deploy time via `aws acm list-certificates`
- **Route53 hosted zone** (`andreas.services`) — looked up at deploy time via `aws route53 list-hosted-zones`

The stack adds a single Route53 A-alias record for `scout.andreas.services` pointing to its CloudFront distribution. It does **not** manage the zone or certificate.

## Environment Variables

All secrets live in the `scout-production` GitHub Actions environment, never in committed files.

| Variable | Where set | Description |
|----------|-----------|-------------|
| `ANTHROPIC_API_KEY` | GitHub secret | Anthropic API key |
| `GMAIL_CLIENT_ID` | GitHub secret | Google OAuth client ID |
| `GMAIL_CLIENT_SECRET` | GitHub secret | Google OAuth client secret |
| `GMAIL_ACCESS_TOKEN` | GitHub secret | OAuth access token (auto-refreshed by Lambda) |
| `GMAIL_REFRESH_TOKEN` | GitHub secret | OAuth refresh token |
| `LAMBDA_CODE_BUCKET` | GitHub var | S3 bucket for Lambda zip uploads |
| `VITE_API_URL` | GitHub var | API Gateway endpoint URL |
| `S3_BUCKET_NAME` | GitHub var | Website S3 bucket name |
| `CLOUDFRONT_DISTRIBUTION_ID` | GitHub var | CloudFront distribution ID |
| `AWS_ROLE_ARN` | GitHub secret | OIDC IAM role for GitHub Actions |

For local use: `cp .env.example .env` and fill in values.

## Lambda Functions

### email-processor

- **Trigger**: EventBridge `cron(0 8 ? * MON *)` — weekly
- **Runtime**: Python 3.11, 256 MB, 300 s timeout
- Authenticates Gmail via OAuth (auto-refreshes token using stored refresh token)
- Skips emails already in DynamoDB (dedup by Gmail `email_id`)
- Converts HTML bodies to plain text via `html2text` before sending to OpenAI
- Claude (claude-haiku-4-5) returns a JSON array — one object per event in the email

### events-api

- **Trigger**: API Gateway
- **Runtime**: Python 3.11, 128 MB, 30 s timeout
- `GET /events` — list all; `?upcoming=true` filters to date ≥ today
- `GET /events/{id}` — fetch single event by `event_id`
- `OPTIONS /*` — CORS preflight

## DynamoDB Schema

Table: `scout-events` · Primary key: `event_id` (UUID string)

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

## Deployment

**Automated (preferred):** Push to `main` — GitHub Actions workflow handles everything.

**Manual (local):**
```bash
cp .env.example .env   # fill in secrets
./deploy.sh            # packages lambdas, deploys CFn, builds + syncs frontend
```

See `docs/SETUP.md` for the full guide including Gmail OAuth setup.

## Local Frontend Development

```bash
./setup-frontend.sh https://your-api-id.execute-api.us-east-1.amazonaws.com/prod
cd frontend && npm run dev
```
