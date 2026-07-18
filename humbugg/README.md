# Humbugg

Humbugg is a public Secret Santa application at `https://humbugg.com`.
`https://www.humbugg.com` and the previous
`https://humbugg.andreas.services` hostname permanently redirect to the apex
while preserving paths and query strings. Organizers create an exchange and share a
private invitation link. Participants manage their own wish list, avoidances,
and optional mailing address. A constrained draw reveals exactly one recipient
to each participant.

## Local development

Local application data always uses DynamoDB Local. Authentication uses the
separate `humbugg-development` Cognito pool.

0. Install the toolchain once with the idempotent setup scripts (from the repo
   root), and expose a `read:packages` token so npm can fetch the private
   `@ansavva/design-system` package:

   ```bash
   ./scripts/dev-setup.sh && ./humbugg/scripts/dev-setup.sh
   export GITHUB_PACKAGES_TOKEN=<pat-with-read:packages>
   eval "$(./scripts/github-packages-auth.sh --export)"   # sets NODE_AUTH_TOKEN
   ```

   See [`../scripts/README.md`](../scripts/README.md) for details.

1. Apply `infra/envs/dev` once, either with the manual **Humbugg · Auth · Dev**
   workflow or Terraform using an authenticated AWS profile.
2. Start the shared local Mailer and Mailpit:

   ```bash
   cd mailer
   docker compose up --build
   ```

3. Copy `frontend/.env.local.example` to `frontend/.env.local` and fill in the
   two Terraform outputs from the development environment.
4. Export those same Cognito values for Docker Compose, then start the .NET API:

   ```bash
   cd humbugg/backend
   docker compose up --build
   ```

5. In another terminal, start the web application:

   ```bash
   cd humbugg/frontend
   npm install
   npm run dev
   ```

The frontend runs at `http://localhost:5173`, the API at
`http://localhost:5001`, DynamoDB Local at `http://localhost:8001`, and the
Mailpit inbox at `http://localhost:8025`. Product messages are captured only by
Mailpit and are never delivered externally. Development Cognito remains on
`COGNITO_DEFAULT`, so signup and recovery codes still go to the real address
entered and do not pass through Mailpit.

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
