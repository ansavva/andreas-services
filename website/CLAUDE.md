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
  Consumes the shared **`@ansavva/design-system`** (React DOM + Tailwind v4)
  from the external [ansavva/design-system](https://github.com/ansavva/design-system)
  repo — see the design-system gotcha below.
- **`backend/`** — Python API Lambda, **Flask + Mangum like storybook/humbugg**
  (`/api/` Blueprint routing in `routes/` → `services`, with persistence in
  `repositories/` and external APIs in `clients/`).
  Package `website_core`.
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

- **`@ansavva/design-system` publishes TypeScript source, not a build.** Its
  `exports` point straight at `src/*.ts`; there is no `dist`. Three consequences,
  all wired up already — do not undo them:
  1. `vite.config.ts` sets `optimizeDeps.include: ['@ansavva/design-system']` so
     Vite transforms the package. Without it the build dies on a type annotation
     or JSX *inside* `node_modules`.
  2. Every component is a `.web.tsx` / `.native.tsx` pair behind one
     extensionless re-export (`export * from './button'`), and the **consumer's**
     bundler picks the leaf. Vite's default `resolve.extensions` stop at `.tsx`,
     so those re-exports resolve to nothing unless the `.web.*` forms come first.
     `vite.config.ts` sets that order on `resolve.extensions` **and** repeats it
     under `optimizeDeps.rollupOptions.resolve.extensions` (the dependency
     optimizer resolves separately); `tsconfig.json` mirrors it as
     `moduleSuffixes: ['.web', '']` for `tsc`.
  3. `app/styles/app.css` `@source`s the **package root**, not `dist`, so
     Tailwind scans the source for the utility classes the components emit.
     Point it anywhere else and every component renders unstyled.
  Import only from the package root — never a `.web`/`.native` path, which
  compiles cleanly and breaks the other platform silently. Base UI and
  `@floating-ui` are gone as of 0.14.0; the only runtime deps are `clsx` and
  `tailwind-merge`.
- **Pin the exact version.** `0.x` caret ranges do not pick up minors, so
  `^0.14.1` would never see 0.15. Read the package's `CHANGELOG.md` before
  bumping.
- **Design system is a devDependency**, bundled into the SSR server build via
  `vite.config.ts` `ssr.noExternal` (the package plus `clsx` and
  `tailwind-merge`). So the runtime frontend Lambda image installs only public
  packages — no GitHub Packages token needed at runtime. Local dev/CI installs
  need `read:packages`: `.npmrc` uses `${NODE_AUTH_TOKEN}`; CI uses
  `secrets.GITHUB_TOKEN`.
- **Brand lives in `app/styles/app.css`, never at a call site.** The `@theme`
  block maps the forest/fern/ivory/linen/brass/clay palette onto the design
  system's semantic roles (`--color-primary`, `--color-accent`, `--color-ink`,
  …), and the `[data-theme='dark']` block does the same for dark mode. Both are
  declared *after* the `theme.css` import, which is what makes them win — no
  `!important` is needed or present. Never hard-code a hex in a component.
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

cd ../backend
poetry install
docker compose up dynamodb                  # local DynamoDB on :8001
poetry run python -m website_core.handlers.local.api.api_dev_server  # :8000
poetry run pytest                         # backend unit tests (moto)
```

Both images are validated with Docker locally (see `docs/SETUP.md`).

## Third-party services

Newsletter = **Kit (ConvertKit)** (backend `KIT_API_KEY`/`KIT_FORM_ID`).
Analytics = **GA4** (`VITE_GA_MEASUREMENT_ID`, build-time). Booking = **Cal.com**
embed (`VITE_CAL_LINK`). Admin auth = **Cognito**.

## Deferred (Phase 1.5+, architected-for, not built)

Live "Ask me anything" AI chat widget; ungated resources library + OSS lead
magnets; a `/product` marketing section.
