# Claude Instructions – scout

## What this service does

Scout discovers events from configured **sources**, extracts them with a Claude
Agent SDK agent, lets an admin review/curate them, and publishes the approved
ones at `scout.andreas.services/app`.

1. **Sources** (email or webpage). Webpage sources are configured by hand in the
   admin console; **email sources are auto-discovered** from the Gmail "Events"
   label — one active source per sender domain. A **scheduler** Lambda
   (EventBridge, every 15 min) runs a Gmail discovery pass, then dispatches
   sources whose `next_run_at` is due; admins can also "Scan inbox", trigger a
   run, or preview on demand.
2. The **source-run-processor** Lambda fetches the source content (our code —
   webpage HTTP fetch, or the sender's recent "Events"-labeled mail via the
   Gmail API in `gmail.py`), optionally follows one level of same-domain links,
   stores everything to S3, then invokes the **Claude Agent SDK** (Read +
   WebFetch + WebSearch) to extract structured events.
3. Extracted events become **pending** records (dedup + fuzzy location match
   applied). An admin reviews (approve/reject), publishes, cancels, edits, and
   manages locations, labels, images, and settings.
4. A **sweep** Lambda (EventBridge, hourly) reconciles runs orphaned by a
   restart and refreshes the materialized `past` flag (incl. parent auto-past).
5. The **events-api** Lambda serves the public read endpoints (consumed by the
   UI) and the admin console API. A Vite + React + TypeScript SPA (S3 +
   CloudFront) renders both.

> The Gmail "Events"-label ingestion now lives inside the source-run-processor
> (`gmail.py` + the processor's `mode=discover`). The standalone legacy
> Gmail→Claude `email-processor` Lambda and the old
> `scout-events/emails/senders/regions/categories` tables have been removed.

### Core domain concepts

- **Source** — email (identity = sender domain) or webpage (identity = root
  URL). Has `status` (active|disabled) and an independent `archived` flag (each
  stops scheduled runs), a `follow_links` toggle, per-source agent model/budget
  overrides, source labels, and a `next_run_at` schedule cursor.
- **Source run** — one record per scheduled/manual execution (previews are
  dry-runs and persist nothing): status (in_progress|success|error, with the
  distinct `budget_exceeded` / `orphaned-by-restart` reasons), S3 refs (root
  body/html, linked pages, agent transcript), per-link outcomes, tool-use
  summary.
- **Event / Sub-event** — first-class sub-events. **Independent status fields**:
  `review_status` (pending|approved|rejected), `publish_status`
  (published|unpublished), admin-set `lifecycle_cancelled`, and a materialized
  `past`. Sub-events inherit location + event-labels (and transitively
  location-labels) from the parent unless they override; a sub can't be
  published while its parent is unpublished; cancelling a parent cascades.
- **Location** — name, address, IANA timezone (drives past computation). Fuzzy
  matched on extraction; admin merge tool reassigns references.
- **Labels** — three independent taxonomies (source / event / location), each a
  separate keyspace. Many-to-many; deleting a label removes references without
  deleting entities.
- **Soft delete** everywhere with cascade (admin opt-out) and recursive restore
  via a shared `cascade_id`; deleted-filter views per entity.
- **Public visibility** (single source of truth in `public.py`): published AND
  not cancelled AND within the grace period; AND-only filtering by location /
  event-labels / inherited location-labels; source attribution never exposed.

## Directory Structure

```
scout/
├── infra/                       # Terraform (CloudFormation is NOT used)
│   ├── modules/                 # auth, api_domain, api_gateway, compute, hosting, storage, data
│   └── envs/                    # prod, pr (per-PR ephemeral), pr-preview (shared)
├── backend/
│   ├── events-api/              # scout-core service (one image, 4 Lambda commands)
│   │   ├── Dockerfile  pyproject.toml  poetry.lock
│   │   ├── scout_core/          # the importable package
│   │   │   ├── handlers/        # thin Lambda entrypoints: api, processor, scheduler, sweep
│   │   │   ├── domain/          # events, sources, runs, labels, locations, deletion,
│   │   │   │                    #   public, images, pipeline, notifications
│   │   │   ├── adapters/        # store (DynamoDB), artifacts (S3), gmail, fetcher, extractor
│   │   │   └── common/          # taxonomy, timeutil (pure, dependency-free)
│   │   └── tests/               # moto-based unit tests (mirror the package)
└── frontend/                    # Vite + React + TS SPA (public site + admin console)
```

Imports are absolute within the package, e.g. `from scout_core.adapters import
store`, `from scout_core.domain import events`. Lambda handlers are referenced as
`scout_core.handlers.<api|processor|scheduler|sweep>.lambda_handler`.

## Data model (DynamoDB)

Two tables (`scout-<name>`, suffixed `-pr-<N>` for previews, all
`PAY_PER_REQUEST` + SSE), defined by the `data` Terraform module:

- **`scout-core`** — single table for the whole entity graph (sources, runs,
  events, sub-events, locations, the three label taxonomies, M2M junctions),
  generic `PK`/`SK` + five GSIs:
  - **GSI1** — admin status queues (`LBL#…`, `LOC#ALL`, `SRC#LISTED/ARCHIVED`,
    `RUN#INPROGRESS`) and public visibility (`PUBVIS`, sparse, keyed by
    `effective_end_utc` for the grace range query).
  - **GSI2** — entity→labels reverse index (display + query-time inheritance).
  - **GSI3** — dedup (`DUP#<key>`), sparse over live events.
  - **GSI4** — source health/schedule (`SRCHEALTH` by `next_run_at`) and the
    event review queue (`REVIEW#<status>`).
  - **GSI5** — deleted-filter view + cascade restore (`DELETED#<type>`).
- **`scout-settings`** — singleton (`setting_id="system"`): timezones, grace
  period, health thresholds, link-follow cap, default agent model/budget.

Soft-delete is uniform: every row carries `deleted_at`; hot indexes (GSI1/GSI3)
are sparse so deleted rows leave public/dedup paths automatically; `cascade_id`
(recorded under a `CASCADE#<id>` partition) drives recursive restore.

`past` can't be indexed, so a stable `effective_end_utc` (location tz + grace
resolved once at write) is indexed instead; the sweep refreshes the boolean.

## Lambda Functions

All four share IAM role `scout-lambda-role` (DynamoDB on `scout-*` incl. GSIs,
S3 on `scout-artifacts-*`/`scout-images-*`, invoke `scout-source-run-processor*`)
and ship from **one** `scout-events-api` image with different container commands
(`image_config.command`):

| Function | Entrypoint | Trigger | Notes |
|----------|-----------|---------|-------|
| `scout-events-api` | `scout_core.handlers.api.lambda_handler` | API Gateway | 128 MB / 30 s |
| `scout-source-run-processor` | `scout_core.handlers.processor.lambda_handler` | async invoke | 512 MB / 300 s; needs `ANTHROPIC_API_KEY`, `SCOUT_ARTIFACTS_BUCKET`, `SCOUT_IMAGES_BUCKET`, `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN` (Gmail ingestion + `mode=discover`) |
| `scout-scheduler` | `scout_core.handlers.scheduler.lambda_handler` | EventBridge `rate(15 minutes)` | Gmail discovery pass + dispatches due sources |
| `scout-sweep` | `scout_core.handlers.sweep.lambda_handler` | EventBridge `rate(1 hour)` | orphan recovery + past flags |

EventBridge rules are created only in prod (`create_eventbridge=true`).

### API surface (events-api)

Routing anchors on the `/api/` path segment (works for prod, the `{proxy+}`
catch-all, and PR base paths).

- **Public** (no auth, under the `/api/{proxy+}` catch-all):
  `GET /api/public/events` (filters: `location_id`, `event_labels`,
  `location_labels` (all AND), `q`, `sort`, `cursor`), `GET /api/public/events/{id}`,
  `GET /api/public/facets`.
- **Admin** (`/api/admin/*`, Cognito authorizer): sources (incl.
  `sources/scan-inbox` → Gmail discovery), events/sub-events, locations,
  labels/{source|event|location}, settings, notifications, `deleted/{type}`,
  `restore`.

## Extraction (Claude Agent SDK)

`extractor.py` runs the agent behind an injectable `runner` (default uses the
`claude-agent-sdk` package, imported lazily). It enforces a token + runtime
budget, records the transcript and per-tool usage summary, and maps outcomes to
completed / `budget_exceeded` / error. `pipeline.py` stores artifacts +
transcript to S3, converts a completed extraction into pending event records
(dedup + fuzzy location match), and raises in-app notifications on failure.

## Environment Variables

Secrets live in the `scout-production` / `scout-pr` GitHub Actions environments.
Notable additions for the redesign:

| Variable | Where | Purpose |
|----------|-------|---------|
| `ANTHROPIC_API_KEY` | secret → processor env | Agent SDK key |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` | secret → processor env | Gmail API (OAuth refresh token) for "Events"-label ingestion |
| `SCOUT_ARTIFACTS_BUCKET` / `SCOUT_IMAGES_BUCKET` | Lambda env | S3 buckets (`scout-artifacts-<env>` / `scout-images-<env>`) |
| `SCOUT_PROCESSOR_FN` | events-api / scheduler env | processor function name for invocations |
| `SCOUT_TABLE_SUFFIX` | Lambda env | `""` in prod, `-pr-<N>` in previews |
| `VITE_API_URL` / `VITE_COGNITO_*` | GitHub vars | frontend build |

## Deployment

Push to `main` runs `.github/workflows/scout-prod.yaml`:
`detect-changes → build-and-push → deploy-infra → update-lambda + deploy-frontend`.
Image build runs first because the Lambdas reference `:latest` with
`lifecycle { ignore_changes = [image_uri, environment] }`. `update-lambda` sets
env vars and pins **all four** Lambdas to `:${sha}` — `scout-events-api`,
`scout-source-run-processor`, `scout-scheduler`, `scout-sweep` all use the one
`scout-events-api` image.

PR previews (`.github/workflows/scout-pr.yml`): validate first
(`lint-unit-build`: backend pytest + frontend lint/tsc/build), then
`deploy-preview-infra` (shared stack) → `deploy-preview` (per-PR ephemeral env
under `infra/envs/pr`, tables/functions suffixed `-pr-<N>`). Teardown destroys
the per-PR env on PR close.

## Local development

```bash
# backend tests (events-api)
cd scout/backend/events-api && python -m pytest

# frontend
cd scout/frontend && npm ci && npm run lint && npm run build && npm run dev
```

## Conventions

- DynamoDB via boto3, no ORM, no VPC. New business logic goes in
  `scout_core/domain/` (AWS/HTTP-free), I/O behind `scout_core/adapters/`, pure
  helpers in `scout_core/common/`, with moto-based unit tests; the handlers in
  `scout_core/handlers/` stay thin.
- Never hardcode AWS credentials or secrets. Sensitive Terraform vars come via
  `TF_VAR_*` in CI.
- Infra dirs are always named `infra/`; modules under `modules/`, environments
  under `envs/`. Shared ACM cert + Route53 zone are referenced via `data`
  sources, never recreated.
