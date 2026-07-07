# Claude Instructions – `website` service

Personal-brand website for **Andreas Services** at **https://www.andreas.services**
(apex `andreas.services` 301-redirects to `www`). Credibility-first conversion +
content site: it exists to land consulting clients and host the companion blog —
it is supporting infrastructure, kept deliberately lean.

## Architecture (two-tier, like the other services)

Unlike the other services (static SPA on S3+CloudFront), the **frontend renders
server-side** for SEO/OG and fast first paint.

- **`frontend/`** — React Router **v7** (framework mode, Vite) **SSR** app.
  Renders every page server-side, then calls the backend API for dynamic data.
  Deployed as a Docker **Lambda** (`@react-router/architect` handler) behind
  **CloudFront**; hashed client assets are served from **S3** at `/assets/*`.
  Consumes the shared **`@ansavva/design-system`** (Base UI + Tailwind v4).
- **`backend/api/`** — Python API Lambda, **same framework as Scout** (raw
  handler, no web framework; `/api/` path routing; layered
  `handlers/`→`domain/`→`adapters/`→`common/`). Package `website_core`.
  Endpoints: `POST /api/intake`, `POST /api/subscribe`, `GET /api/admin/submissions`.
- **`infra/`** — Terraform `modules/` (data, auth, api_gateway, api_domain,
  compute, hosting) + `envs/prod`, mirroring Scout.

```
Browser ──▶ CloudFront (www + apex)
              ├─ /assets/*  ─▶ S3
              └─ /*         ─▶ SSR frontend Lambda (Function URL, OAC-signed)
                                    │ server-side fetch
                                    ▼
                              website-api.andreas.services (API Gateway)
                                    └─▶ Python API Lambda ─▶ DynamoDB (website-intake)
                                          /api/admin/*  behind Cognito authorizer
```

## Conventions & gotchas

- **Design system is a devDependency**, bundled into the SSR server build via
  `vite.config.ts` `ssr.noExternal` (the whole Base UI subtree). So the runtime
  frontend Lambda image installs only public packages — no GitHub Packages token
  needed at runtime. Local dev/CI installs need `read:packages`:
  `.npmrc` uses `${NODE_AUTH_TOKEN}`; CI uses `secrets.GITHUB_TOKEN`.
- **React 19** (RR7 peer). RR **v8** is intentionally NOT used — it requires
  Node 22; this repo/toolchain is Node 20 (also the Lambda base image).
- **No SES.** Intake submissions are stored in DynamoDB only and reviewed in the
  Cognito-protected `/admin` dashboard. Single admin user, bootstrapped via
  `scripts/create-admin-user.sh`.
- **Server-only code** lives in `frontend/app/lib/*.server.ts` (env, api client,
  Cognito session, markdown loader) so it is stripped from the browser bundle.
- **Companion blog**: markdown files in `frontend/app/content/writing/*.md`
  (frontmatter: `title`, `date`, `description`, `videoUrl`, optional `ogImage`),
  bundled at build via `import.meta.glob`. Adding a post = adding a file.
- Lambdas use `lifecycle { ignore_changes = [image_uri, environment] }`; the
  deploy workflow owns image tags and env vars.

## Local development

```bash
cd frontend
export NODE_AUTH_TOKEN=$(gh auth token)   # needs read:packages
npm ci
npm run dev            # RR SSR dev server (needs WEBSITE_API_URL for forms/admin)

cd ../backend/api
poetry install && poetry run pytest       # backend unit tests (moto)
```

Both images are validated with Docker locally (see `docs/SETUP.md`).

## Third-party services

Newsletter = **Kit (ConvertKit)** (backend `KIT_API_KEY`/`KIT_FORM_ID`).
Analytics = **GA4** (`VITE_GA_MEASUREMENT_ID`, build-time). Booking = **Cal.com**
embed (`VITE_CAL_LINK`). Admin auth = **Cognito**.

## Deferred (Phase 1.5+, architected-for, not built)

Live "Ask me anything" AI chat widget; ungated resources library + OSS lead
magnets; a `/product` marketing section.
