# classroom

A place for a teacher to write a page and hand its link to a class.

**Live at `classroom.andreas.services`.** The API is `classroom-api.andreas.services`
and sign-in is `classroom-auth.andreas.services`.

## What it does

A teacher signs in, writes or pastes HTML — a warm-up, a worksheet, a study
guide — and publishes it. Publishing yields a short link (`/p/<slug>`) that
students open with no account and no sign-in. Withdrawing a page makes the link
stop working without deleting the page.

The slug never changes once issued, because by the time anyone edits a page its
link is already on a whiteboard or in a class message.

## Shape

| Piece | Stack |
| --- | --- |
| `backend/` | Flask on a container Lambda, DynamoDB via boto3, Cognito JWT at the gateway |
| `frontend/` | Vite + React 19 + TypeScript, UI from `@ansavva/design-system` |
| `infra/` | Terraform — DynamoDB, Lambda, API Gateway, Cognito, S3 + CloudFront |

One DynamoDB table, `classroom-prod-pages`. Pages are keyed by the owning
teacher (`TEACHER#<sub>` / `PAGE#<id>`), and GSI1 indexes the public slug. The
GSI1 attributes exist only while a page is published, so a withdrawn page falls
out of the public lookup with no filter expression.

## Teacher-authored HTML is the security boundary

Students load this HTML from our own domain, which makes anything stored here a
stored-XSS sink. Two independent layers, because either alone is a single point
of failure:

1. **Sanitized on write** — `backend/classroom_core/utils/html.py` reduces the
   markup to an allowlist shaped for teaching material. No `<script>`,
   `<iframe>`, `<form>`, no event handlers, no `javascript:` or `data:` URLs.
2. **Served under a restrictive CSP** — the public reader sets
   `script-src 'none'` and `sandbox`, so anything that slipped past the
   sanitizer still cannot run.

The editor's own preview shows *escaped source* rather than rendering the
draft, because a draft has not been through layer 1 yet.

## Accounts

The Cognito pool is admin-create-only; there is no public sign-up. Add a
teacher with:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id "$(terraform -chdir=infra/envs/prod output -raw cognito_user_pool_id)" \
  --username teacher@example.com \
  --user-attributes Name=email,Value=teacher@example.com Name=email_verified,Value=true
```

## Local development

```bash
cd frontend
cp .env.local.example .env.local     # point at a dev stack
eval "$(../../scripts/github-packages-auth.sh --export)"   # design system needs a token
npm ci && npm run dev                # http://localhost:5174

cd ../backend
poetry install --with dev
CLASSROOM_PAGES_TABLE=classroom-dev-pages poetry run pytest tests/ -v
```

## Deployment

`classroom-pr.yml` validates every PR and never writes to AWS.
`classroom-prod.yaml` deploys from `main`:
`detect-changes → build-and-push → deploy-infra → update-lambda + deploy-frontend`.
