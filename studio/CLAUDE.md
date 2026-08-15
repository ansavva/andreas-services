# Claude Instructions – studio

## What this service does

Studio is a private media browser for the **x-harness** AI generation pipeline,
served from two hostnames:

| Surface | URL | What it is |
|---|---|---|
| App | `studio.andreas.services` | Vite + React SPA on S3 + CloudFront. Dark-only. |
| API | `studio-api.andreas.services` | Flask Lambda behind an API Gateway custom domain. |

The x-harness pipeline writes every image and video it produces into
`s3://xharness-prod-media-us-east-1/media/`. Studio makes that browsable:
folders keep their structure, images and video are the focus, and every item can
be opened fullscreen or flipped through as a vertical reel.

**Studio is a reader and only a reader.** It does not generate, edit, upload or
delete anything.

## Stack

| Layer | Choice |
|---|---|
| Backend | Flask (Python 3.11) + Mangum, Docker container Lambda behind API Gateway REST |
| Frontend | Vite + React 19 + Tailwind v4 + the design system's **web** leaves, static build to S3 + CloudFront |
| Auth | AWS Cognito (admin-create-only user pool); SRP via Amplify Auth on the SPA, Cognito authorizer on every `/api` route |
| Data | **None.** No DynamoDB, no cache. Listings come straight from S3 on each request. |
| Media | Presigned S3 GET URLs, direct from the browser to S3 |
| Infra | Terraform in `studio/infra/` (`modules/` + `envs/prod`) |

## Directory Structure

```
studio/
├── backend/                  # Flask + Dockerfile, shipped as a container Lambda
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── studio_core/          # routes → services → clients
│   └── tests/                # pytest + moto over a miniature of the real bucket
├── frontend/                 # Vite + React SPA (studio.andreas.services)
│   ├── index.html            # pins data-theme="dark"
│   └── src/                  # apis, components, pages, hooks, context, utils, types
├── infra/
│   ├── modules/              # auth, compute, api_gateway, api_domain, hosting
│   └── envs/prod/
├── scripts/                  # create-user.sh, dev-up.sh
└── CLAUDE.md                 # ← this file
```

## The media bucket is not ours

`xharness-prod-media-us-east-1` belongs to the x-harness pipeline. Studio's
Terraform **references it by name and nothing more** — there is deliberately no
`aws_s3_bucket` resource and no `aws_s3_bucket` data source for it in
`studio/infra`. A data source would be harmless today but would put the bucket
one careless refactor away from being managed by this state.

The Lambda role's policy (`modules/compute`) grants exactly two actions:
`s3:ListBucket` (conditioned on the `media/` prefix) and `s3:GetObject` on
`media/*`. **Do not add a write action to it.** If a future feature seems to
need one, that feature belongs in x-harness, not here.

There is an older mirror of the same content at `xharness-assets`. Point
`media_bucket_name` at it if you ever need to; nothing else changes.

## What the bucket looks like

```
media/
├── <subject>/                 # fred, mr-p
│   ├── profile.md
│   ├── originals/             # source photos (.webp, .jpg, .jpeg, .JPG)
│   ├── input/                 # prepped inputs (.png, .jpg)
│   ├── reference/             # reference images + .txt captions
│   └── runs/<ts>_<slug>/      # request.json, result.json, sometimes prompt.json
│       └── output/            # the generated .jpeg / .webp / .mp4
└── misc/runs/<ts>_<slug>/     # unattributed runs, mostly seedance/kling video
```

Two things about this shape drive the UI: run folders sort chronologically
because their names start with a timestamp, and a run's output lives one level
down in `output/`, so a run folder itself usually shows only JSON.

**The run JSON is deliberately not parsed.** x-harness owns its shape and
changes it freely, so studio serves those files as text and the frontend shows
them read-only. Do not start decoding `request.json` into typed UI — the moment
the pipeline adds a field, a parser becomes a liar.

## Conventions & gotchas

- **The API takes the ID token, never the access token.** A REST
  `COGNITO_USER_POOLS` authorizer only reads the incoming token as an *access*
  token when the method declares `authorization_scopes`. This one declares none
  — and cannot usefully, since the pool has no resource server and Amplify's SRP
  flow mints only `aws.cognito.signin.user.admin` — so it validates an
  *identity* token. Send `session.tokens.idToken` (`apis/client.ts`). The
  failure mode is the confusing one: sign-in succeeds, the app renders, and
  every `/api` call 401s.
- **An authorizer rejection carries no CORS headers unless you add them.** It is
  generated before the integration runs, so Flask's `CORS(...)` never sees it
  and the MOCK preflight only covers the OPTIONS. `modules/api_gateway` sets
  `aws_api_gateway_gateway_response` for `UNAUTHORIZED` and `ACCESS_DENIED`;
  without them a 401 surfaces in the SPA as an opaque CORS failure with no
  status to act on. Both are in the deployment trigger — a gateway response
  needs a redeploy to take effect.
- **Presigned URLs die with the Lambda's credentials, not with `ExpiresIn`.** A
  URL signed by temporary credentials stops working when those rotate, whatever
  expiry was requested. `STUDIO_PRESIGN_TTL_SECONDS` defaults to 900 and the
  frontend re-signs through `/api/asset` from a media element's `onError`
  (`useSignedSrc`), capped at one retry per key.
- **A cross-origin `<a download>` is ignored by browsers.** Downloads work only
  because `/api/asset?disposition=attachment` signs
  `response-content-disposition` into the URL itself.
- **Text is served through `/api/text`, not fetched from the presigned URL.** A
  cross-origin `fetch` to S3 would need a CORS configuration on a bucket studio
  does not own and must not modify.
- **`services/keys.py` is the only thing between a query string and
  `GetObject`.** Every prefix and key is normalised and confined to
  `media/`. Test changes to it directly — `posixpath.normpath` strips a trailing
  slash, which is why the folder check happens on the raw value.
- **Dark-only, and the palette is declared twice.** `src/styles/app.css` sets it
  in `@theme` *and* under `[data-theme='dark']`; `index.html` pins the attribute
  and nothing toggles it. The duplication stops a component that reads a role
  outside the selector from flashing the design system's light default over a
  photograph. Never hard-code a colour at a call site.
- **The design system's leaf resolution is load-bearing and fails silently.**
  `vite.config.ts` puts the `.web.*` forms first in `resolve.extensions` **and**
  in `optimizeDeps.rollupOptions.resolve.extensions`; `tsconfig.json` mirrors it
  as `moduleSuffixes`. `studio-pr.yml` audits the built source map in both
  directions, because picking the wrong leaf compiles cleanly.
- **`@ansavva/design-system` is pinned exactly (0.14.1).** `0.x` caret ranges do
  not pick up minors. Read the package's `CHANGELOG.md` before bumping.
- **React 19**, matching `website/frontend` and `humbugg/marketing`. The design
  system's source uses React 19 DOM props (`inert`, `onScrollEnd`), so React 18
  types fail `tsc` inside `node_modules`.
- **Reel mode mounts a window, not the world.** Only panes within ±2 of the
  snapped index render a media element; the rest keep their height so scroll
  position stays honest. A hundred live `<video>` elements exhausts the decoder.
- Lambda uses `lifecycle { ignore_changes = [image_uri, environment] }`; the
  deploy workflow owns the image tag and the env vars.

## API

Every route is behind the Cognito authorizer except `GET /api/health`.

| Route | Returns |
|---|---|
| `GET /api/health` | `{"status": "ok"}` — liveness, touches no S3 |
| `GET /api/tree?prefix=` | One delimited listing: `folders`, `files` (each presigned), `breadcrumbs`, `counts` |
| `GET /api/reel?prefix=&cursor=&page_size=` | Images and video beneath a prefix, recursively, paginated |
| `GET /api/asset?key=&disposition=` | A fresh presigned URL for one object |
| `GET /api/text?key=` | A `.json` / `.md` / `.txt` object's contents, capped at 1 MB |

## Local development

```bash
# Both surfaces together (backend :8000, frontend :5173).
aws login
./studio/scripts/dev-up.sh
```

Or separately:

```bash
cd studio/backend
poetry install --no-root
eval "$(aws configure export-credentials --format env)"   # boto3 needs real env creds
poetry run python -m studio_core.handlers.local.api.api_dev_server
poetry run pytest                                          # moto-backed, no AWS needed

cd studio/frontend
export NODE_AUTH_TOKEN=$(gh auth token)                    # needs read:packages
npm ci && npm run dev
```

`aws login` writes a cache only the AWS CLI reads, so `aws sts
get-caller-identity` succeeding tells you nothing about whether boto3 can see
credentials — export them. Same split the root `CLAUDE.md` documents for
Terraform's provider.

Copy `frontend/.env.local.example → .env.local` and fill in the Cognito ids from
the prod outputs, or the app shows "Auth is not configured".

## Creating users

There is no sign-up. Accounts are created out of band:

```bash
STUDIO_EMAIL=you@example.com ./studio/scripts/create-user.sh
```

Cognito emails a temporary password; signing in with it prompts for a new one.
Pass `STUDIO_PASSWORD` to set a permanent one directly instead.

## Deployment

`.github/workflows/studio-prod.yaml` — `detect-changes → bootstrap-ecr →
build-and-push → deploy-infra → update-lambda + deploy-frontend`. The SPA is
built in `deploy-frontend` rather than earlier because Vite inlines every
`VITE_*` value at build time and the Cognito ids come out of the apply.

Terraform state: `s3://andreas-services-terraform-state/studio/prod/terraform.tfstate`.
