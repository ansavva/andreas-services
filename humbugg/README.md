# Humbugg

Humbugg is a public Secret Santa application at `https://humbugg.com`.
`https://www.humbugg.com` and the previous
`https://humbugg.andreas.services` hostname permanently redirect to the apex
while preserving paths and query strings. Organizers create an exchange and share a
private invitation link. Participants manage their own wish list, avoidances,
and optional mailing address. A constrained draw reveals exactly one recipient
to each participant.

## Local development

Local application data and authentication use isolated AWS resources managed by
Terraform. Each OS user on each machine receives a persistent random UUID, so a
developer can safely use multiple machines without sharing tables, buckets,
Cognito users, or Terraform state.

### Development script reference

Run every command from the repository root. All scripts are idempotent where
applicable and accept `--help` for their complete usage.

| Script | Purpose | Common options |
|---|---|---|
| `./scripts/dev-setup.sh` | Installs shared Homebrew tooling, including Terraform, AWS CLI, Node.js, Stripe CLI, jq, and zip | `--check` reports without installing |
| `./humbugg/scripts/dev-setup.sh` | Canonical setup: runs shared tool setup, installs .NET 10, then provisions per-machine AWS resources | `--profile`, `--region`, `--yes`; `--check` is read-only across every layer |
| `./humbugg/scripts/dev-aws-setup.sh` | Lower-level AWS setup used by the canonical setup; remains directly runnable | `--profile`, `--region`, `--yes`, `--check` |
| `./humbugg/scripts/dev-up.sh` | Starts the backend, frontend, and Stripe webhook listener as one supervised session | `--profile`, `--region`, `--forward-to` |
| `./humbugg/scripts/dev-up-backend.sh` | Starts only the Dockerized .NET API with short-lived AWS credentials | `--profile`, `--region`, plus Docker Compose options |
| `./humbugg/scripts/dev-up-frontend.sh` | Starts only the React development server using `frontend/.env.local` | accepts React Router/Vite development options |
| `./humbugg/scripts/dev-up-stripe.sh` | Starts only the Stripe CLI listener with Humbugg's event allowlist | `--forward-to`, plus Stripe listener options |
| `./humbugg/scripts/dev-logs-backend.sh` | Follows the local backend's Docker logs | accepts Docker Compose log options such as `--tail 200` |
| `./humbugg/scripts/dev-aws-reset.sh` | Clears this machine's DynamoDB, S3, and optionally Cognito user data while retaining its infrastructure | `--profile`, `--region`, `--dry-run`, `--skip-cognito`, `--yes` |
| `./humbugg/scripts/dev-aws-destroy.sh` | Destroys this machine's AWS development resources while retaining its machine UUID | `--profile`, `--region`, `--yes` |

`dev-aws-common.sh` is an internal helper sourced by the commands above and
should not be run directly. AWS scripts default to `$AWS_PROFILE` (or
`default`) and `$AWS_REGION`/`$AWS_DEFAULT_REGION` (or `us-east-1`). Passing an
explicit profile is recommended.

0. Run the canonical idempotent setup from the repo root. It invokes shared
   tool setup, installs .NET, provisions this machine's AWS resources, and
   generates the ignored environment files. Then expose a `read:packages` token so npm can fetch the private
   `@ansavva/design-system` package:

   ```bash
   ./humbugg/scripts/dev-setup.sh --profile personal
   export GITHUB_PACKAGES_TOKEN=<pat-with-read:packages>
   eval "$(./scripts/github-packages-auth.sh --export)"   # sets NODE_AUTH_TOKEN
   npm --prefix humbugg/frontend install --legacy-peer-deps
   stripe login
   ```

   See [`../scripts/README.md`](../scripts/README.md) for details.

   For billing tests, configure `HUMBUGG_STRIPE_MODE=test`, the test publishable
   key, and the test secret key in the ignored `humbugg/backend/.env` as
   described in [`docs/stripe-setup.md`](docs/stripe-setup.md). The combined
   launcher refreshes the local webhook signing secret, but it does not create
   or persist Stripe API keys.

1. The canonical setup creates the UUID at
   `~/.config/andreas-services/humbugg/machine-id`, applies Terraform using the
   selected authenticated AWS profile, and writes generated resource names to
   the ignored backend and frontend env files. You can validate the entire
   completed setup later with:

   ```bash
   ./humbugg/scripts/dev-setup.sh --profile personal --check
   ```

   `--check` runs the complete dependency chain without installing tools,
   applying Terraform, writing environment files, or restarting containers.

2. Start the shared local Mailer and Mailpit:

   ```bash
   cd mailer
   docker compose up --build
   ```

3. Start the backend, frontend, and Stripe webhook listener together:

   ```bash
   ./humbugg/scripts/dev-up.sh --profile personal
   ```

   The launcher refreshes the Stripe CLI's local `whsec_...` signing secret and
   AWS credentials before starting the API. It force-recreates the backend so
   an existing container cannot retain expired credentials. Press Ctrl+C once
   to stop all three processes.

### Starting components separately

Start the .NET API first. The launcher exports short-lived credentials from the
selected AWS profile directly into the backend process; credentials are never
written to a file:

```bash
./humbugg/scripts/dev-up-backend.sh --profile personal
```

Restart the launcher when the AWS login session expires so it can inject a
fresh set of short-lived credentials. Re-running `dev-aws-setup.sh` also
recreates an already-running backend with refreshed credentials.

Follow the backend logs from another terminal with:

```bash
./humbugg/scripts/dev-logs-backend.sh
```

Then start the web application in another terminal:

```bash
./humbugg/scripts/dev-up-frontend.sh
```

For local Stripe webhook testing, start the Stripe CLI listener in another
terminal:

```bash
./humbugg/scripts/dev-up-stripe.sh
```

Copy the `whsec_...` signing secret displayed by Stripe into
`HUMBUGG_STRIPE_WEBHOOK_SECRET` in `backend/.env`, then restart the backend.

The frontend runs at `http://localhost:5173`, the API at
`http://localhost:5001`, and the Mailpit inbox at `http://localhost:8025`.
Product messages are captured only by Mailpit. AWS Cognito sends signup and
recovery codes to the address entered during testing. The development S3
bucket remains private; the API returns one-hour presigned avatar read URLs.

To preview a reset without changing anything, then reset all development data
before a clean test run, use:

```bash
./humbugg/scripts/dev-aws-reset.sh --profile personal --dry-run
./humbugg/scripts/dev-aws-reset.sh --profile personal
```

The reset script verifies the machine UUID and resource-name prefix, deletes and
recreates only this machine's DynamoDB tables through Terraform, empties its S3
bucket, and deletes its Cognito users while retaining the pool and client. Pass
`--dry-run` or `--skip-cognito` when needed. The destructive run requires typing
`RESET` unless `--yes` is supplied.

Remove the AWS resources when this development environment is no longer needed:

```bash
./humbugg/scripts/dev-aws-destroy.sh --profile personal
```

The machine UUID is intentionally retained so reprovisioning uses the same
identity and Terraform state path.

The frontend uses React Router server rendering. Marketing HTML, page metadata,
`robots.txt`, and `sitemap.xml` are rendered by the frontend server; browser
assets are emitted separately for CloudFront and S3.

## Checks

```bash
cd humbugg/backend && dotnet test Humbugg.slnx
cd humbugg/frontend && npm ci --legacy-peer-deps && npm run typecheck && npm test && npm run build
terraform fmt -check -recursive humbugg/infra
```

Production deploys remain owned by `.github/workflows/humbugg-prod.yaml`.
Email monitoring and recovery are documented in
[`docs/email-operations.md`](docs/email-operations.md).

## Production domain

Terraform reads the existing public `humbugg.com` and `andreas.services`
Route53 hosted zones. It owns a us-east-1 ACM certificate for `humbugg.com`,
`www.humbugg.com`, and `humbugg.andreas.services`, plus their validation and
alias records. The CloudFront viewer-request function returns a `308` redirect
for non-apex hosts before any route reaches an origin.

The backend `APP_BASE_URL` and `CORS_ORIGIN`, frontend build URL, Cognito
callback/logout URLs, metadata, robots file, sitemap, invite links, deployment
smoke tests, and public documentation all use `https://humbugg.com`.

Transactional product email originates from `no-reply@humbugg.com`. Terraform
owns SES identity verification, Easy DKIM, the `mail.humbugg.com` MAIL FROM
records, and the initial DMARC monitoring policy. Deployment verifies all three
authentication states and exercises SES delivery, bounce, and complaint
feedback with the AWS mailbox simulator.

The backend keeps templates and copy but submits product messages through the
shared Mailer HTTP API. Local development uses the unsigned API and Mailpit;
production uses SigV4 and the backend Lambda role. Unit tests retain an
in-memory capture adapter. A DynamoDB delivery ledger uses stable application
message IDs to suppress duplicates, and a dedicated status Lambda records
normalized Mailer feedback for 90 days.
