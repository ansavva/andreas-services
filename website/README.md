# Andreas Services — website

The personal-brand site for **Andreas Services**, served at
**https://www.andreas.services** (the apex `andreas.services` 301-redirects to
`www`).

A credibility-first conversion + content site: a done-for-you AI-automation
consulting offer sold through a low-friction "scoped quote in 48 hours" intake,
sitewide newsletter capture, and a video→companion-blog engine for SEO.

## Stack

| Part | Tech |
|------|------|
| Frontend | React Router v7 (framework mode, Vite) **SSR**, Tailwind v4, `@ansavva/design-system` |
| Backend | Python 3.11 Flask + Mangum Lambda API, boto3, DynamoDB |
| Hosting | CloudFront → SSR Lambda (Function URL) + S3 (`/assets/*`); backend behind API Gateway at `website-api.andreas.services` |
| Auth | AWS Cognito (admin dashboard) |
| Infra | Terraform (`infra/modules` + `infra/envs/prod`) |
| CI/CD | GitHub Actions (`website-pr.yml`, `website-prod.yaml`) |

## Layout

```
website/
├── frontend/     # React Router SSR app + Dockerfile (Lambda handler)
├── backend/      # Python API Lambda (website_core) + Dockerfile
├── infra/        # Terraform modules + envs/prod
├── scripts/      # create-admin-user.sh, reconcile-prod-rename.sh (one-time)
└── docs/SETUP.md # first-time setup + deploy notes
```

See [`docs/SETUP.md`](docs/SETUP.md) to run and deploy, and [`CLAUDE.md`](CLAUDE.md)
for architecture details.
