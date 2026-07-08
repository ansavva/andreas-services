# Claude Instructions – scout

## What this service does

Scout discovers events from configured **sources**, extracts them with a Claude
model (Anthropic Messages API), lets an admin review/curate them, and publishes
the approved ones at `scout.andreas.services/app`.

1. **Sources** (email or webpage). Webpage sources are configured by hand in the
   admin console; **email sources are auto-discovered** from the Gmail "Events"
   label — one active source per sender domain. A **scheduler** Lambda
   (EventBridge, every 15 min) runs a Gmail discovery pass, then dispatches
   sources whose `next_run_at` is due; admins can also "Scan inbox", trigger a
   run, or preview on demand.
2. The **source-run-processor** Lambda fetches the source content (our code —
   webpage HTTP fetch, or the sender's recent "Events"-labeled mail via the
   Gmail API in `gmail.py`), stores it to S3, then runs a **two-pass Anthropic
   tool-use extraction**: a cheap triage pass finds candidate events (each with
   its own detail URL) plus "listing" URLs — links to pages that list *more*
   events. Listing pages are fetched and re-triaged up to a small depth bound,
   so an email that merely links to a "what's on" page still yields its events.
   We then fetch each candidate's detail page (cleaned to text; cross-domain for
   email, same-domain for webpage; junk-filtered) and a stronger enrich pass
   turns each mention + detail page into a full structured event. All listing +
   detail fetches share one global budget (link-follow cap) with URL de-dup;
   candidates with no usable link fall back to the triage event directly.
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

- **Source** — email (identity = sender domain), webpage (identity = root URL),
  or **ical** (identity = an `.ics` feed URL). Has `status` (active|disabled) and
  an independent `archived` flag (each stops scheduled runs), a `follow_links`
  toggle, per-source agent model/budget overrides, source labels, and a
  `next_run_at` schedule cursor. **All web-page retrieval** — webpage roots,
  followed links, and the links followed out of email digests — goes through the
  headless renderer (`renderer_client.fetch_rendered`), so JS-rendered and
  bot-challenged pages work everywhere. **iCal** sources bypass fetching+LLM
  extraction entirely: the processor parses the feed's `VEVENT`s straight into
  pending events (`clients/ical.py` → `pipeline.execute_ical_run` →
  `events.convert_extraction`). This is the reliable path for events owned by a
  hosted calendar widget (e.g. Tockify/Google Calendar), whose host page renders
  client-side and exposes no events to a fetch or render.
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
│   ├── Dockerfile  pyproject.toml  poetry.lock
│   ├── scout_core/              # the importable package
│   │   ├── handlers/            # thin Lambda entrypoints: api, processor, scheduler, sweep
│   │   ├── routes/              # Flask Blueprints (one per resource): public, sources,
│   │   │                        #   events, locations, labels, settings, notifications, deleted
│   │   ├── services/            # events, sources, runs, labels, locations, deletion,
│   │   │                        #   public, images, pipeline, notifications
│   │   ├── repositories/        # persistence: DynamoDB + S3-backed storage
│   │   ├── clients/             # external APIs/services: Gmail, fetcher, extractor, renderer
│   │   └── utils/               # taxonomy, timeutil (pure, dependency-free)
│   ├── tests/                   # moto-based unit tests (mirror the package)
│   └── renderer/                # browser-render Lambda (own image: patchright + headful Chrome/Xvfb)
│       └── Dockerfile  requirements.txt  handler.py
└── frontend/                    # Vite + React + TS SPA (public site + admin console)
```

Imports are absolute within the package, e.g. `from scout_core.repositories import
store`, `from scout_core.services import events`. HTTP routing is Blueprint-based:
one resource Blueprint per module in `scout_core/routes/`, registered by
`scout_core.app_factory.create_app`. Lambda handlers are referenced as
`scout_core.handlers.aws.api.api_handler.handler` for the Flask + Mangum HTTP API (a
thin Mangum adapter over that app), and
`scout_core.handlers.aws.jobs.<processor|scheduler|sweep>_handler.lambda_handler` for the
event-driven Lambdas.

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
  period, health thresholds, link-follow cap, default triage/agent models + budget.

Soft-delete is uniform: every row carries `deleted_at`; hot indexes (GSI1/GSI3)
are sparse so deleted rows leave public/dedup paths automatically; `cascade_id`
(recorded under a `CASCADE#<id>` partition) drives recursive restore.

`past` can't be indexed, so a stable `effective_end_utc` (location tz + grace
resolved once at write) is indexed instead; the sweep refreshes the boolean.

## Lambda Functions

The first four share IAM role `scout-lambda-role` (DynamoDB on `scout-*` incl.
GSIs, S3 on `scout-artifacts-*`/`scout-images-*`, invoke
`scout-source-run-processor*` and `scout-source-renderer*`) and ship from **one**
`scout-events-api` image with different container commands
(`image_config.command`). The renderer ships from its **own** image
(`scout-renderer`) because Chromium is too heavy for the shared image:

| Function | Entrypoint | Trigger | Notes |
|----------|-----------|---------|-------|
| `scout-events-api` | `scout_core.handlers.aws.api.api_handler.handler` | API Gateway | Flask + Mangum, 128 MB / 30 s |
| `scout-source-run-processor` | `scout_core.handlers.aws.jobs.processor_handler.lambda_handler` | async invoke | 512 MB / 300 s; needs `ANTHROPIC_API_KEY`, `SCOUT_ARTIFACTS_BUCKET`, `SCOUT_IMAGES_BUCKET`, `GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN` (Gmail ingestion + `mode=discover`), `SCOUT_RENDERER_FN` (page rendering) |
| `scout-scheduler` | `scout_core.handlers.aws.jobs.scheduler_handler.lambda_handler` | EventBridge `rate(15 minutes)` | Gmail discovery pass + dispatches due sources |
| `scout-sweep` | `scout_core.handlers.aws.jobs.sweep_handler.lambda_handler` | EventBridge `rate(1 hour)` | orphan recovery + past flags |
| `scout-source-renderer` | `handler.lambda_handler` (own image) | sync invoke (by processor) | 3008 MB / 90 s; patchright (undetected Playwright) + headful Chrome via Xvfb; renders every fetched page (runs JS / passes bot challenges), returns HTML |

EventBridge rules are created only in prod (`create_eventbridge=true`).

The processor injects `renderer_client.fetch_rendered` as the `fetch_fn` for
**all** page retrieval — webpage roots, followed links, and the links followed
out of email digests — which synchronously invokes `scout-source-renderer`;
everything downstream (clean → triage → enrich) is unchanged. Only iCal feeds
(parsed directly) and email bodies (pulled from Gmail) are not page fetches.

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

## Extraction (Anthropic Messages API, two-pass tool-use)

`extractor.py` runs extraction in two passes, each a forced Anthropic tool-use
call (validated structured output, no fragile free-text parsing) behind an
injectable `runner` (default uses the `anthropic` package, imported lazily):

- `triage(pages, …)` → `report_candidates` tool: per page, the distinct
  candidate events (date/venue hints, the event's own detail URL, a best-effort
  `fallback_event`) **and** `listing_urls` — links to pages listing *more*
  events. Default model `default_triage_model` (Haiku).
- `enrich(candidate, page_text, …)` → `record_events` tool: one full event from
  a mention + its fetched detail page. Default model `default_agent_model`
  (Sonnet).

Both prompts carry a system message that anchors relative dates to today +
`system_timezone` (so "this Saturday"/the year resolve correctly), run at
temperature 0, and mark the static system + tool blocks for prompt caching; the
enrich prompt also lists the existing event-label vocabulary (model prefers it,
may add new). `MAX_OUTPUT_TOKENS` is 16k and each logical call retries once on a
parse/empty failure. `pipeline.run_extraction` orchestrates triage → follow
`listing_urls` breadth-first up to `MAX_LISTING_DEPTH` (re-triaging each) →
fetch each candidate's detail page → enrich. All listing + detail fetches go
through `fetcher.fetch_text` (junk-filtered, cleaned) under one shared
`link_follow_cap` budget with URL de-dup. It stores artifacts + the combined
transcript to S3, aggregates token/runtime usage under the per-source budget,
converts the result into pending event records (dedup + fuzzy location match),
and raises in-app notifications on failure. The legacy single-pass `extract()`
is retained for back-compat. (Extraction is
content-only — no WebFetch/WebSearch; our fetcher gathers the pages.)

## Environment Variables

Secrets live in the `scout-production` / `scout-pr` GitHub Actions environments.
Notable additions for the redesign:

| Variable | Where | Purpose |
|----------|-------|---------|
| `ANTHROPIC_API_KEY` | secret → processor env | Anthropic Messages API key |
| `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` / `GMAIL_REFRESH_TOKEN` | secret → processor env | Gmail API (OAuth refresh token) for "Events"-label ingestion |
| `SCOUT_ARTIFACTS_BUCKET` / `SCOUT_IMAGES_BUCKET` | Lambda env | S3 buckets (`scout-artifacts-<env>` / `scout-images-<env>`) |
| `SCOUT_PROCESSOR_FN` | events-api / scheduler env | processor function name for invocations |
| `SCOUT_RENDERER_FN` | processor env | renderer function name (sync-invoked for every page fetch) |
| `SCOUT_TABLE_SUFFIX` | Lambda env | `""` in prod, `-pr-<N>` in previews |
| `VITE_API_URL` / `VITE_COGNITO_*` | GitHub vars | frontend build |

## Deployment

Push to `main` runs `.github/workflows/scout-prod.yaml`:
`detect-changes → build-and-push → deploy-infra → update-lambda + deploy-frontend`.
Image build runs first because the Lambdas reference `:latest` with
`lifecycle { ignore_changes = [image_uri, environment] }`. Two images are built:
the shared `scout-events-api` image and the `scout-renderer` image (Playwright +
Chromium). `update-lambda` sets env vars and pins all five Lambdas to `:${sha}` —
`scout-events-api`, `scout-source-run-processor`, `scout-scheduler`,
`scout-sweep` use the `scout-events-api` image; `scout-source-renderer` uses the
`scout-renderer` image.

PR previews (`.github/workflows/scout-pr.yml`): validate first
(`lint-unit-build`: backend pytest + frontend lint/tsc/build), then
`deploy-preview-infra` (shared stack) → `deploy-preview` (per-PR ephemeral env
under `infra/envs/pr`, tables/functions suffixed `-pr-<N>`). Teardown destroys
the per-PR env on PR close.

## Local development

```bash
# backend tests (events-api)
cd scout/backend && python -m pytest

# local DynamoDB + HTTP API server
cd scout/backend
docker compose up dynamodb
poetry run python -m scout_core.handlers.local.api.api_dev_server

# frontend
cd scout/frontend && npm ci && npm run lint && npm run build && npm run dev
```

## Conventions

- DynamoDB via boto3, no ORM, no VPC. New business logic goes in
  `scout_core/services/` (AWS/HTTP-free), persistence behind
  `scout_core/repositories/`, external APIs behind `scout_core/clients/`, pure
  helpers in `scout_core/utils/`, with moto-based unit tests; the handlers in
  `scout_core/handlers/` stay thin.
  Local app/handler runs use DynamoDB Local on `localhost:8001`; unit tests keep
  using moto. `scout_core.repositories.dynamodb` owns boto3/local table bootstrap;
  `scout_core.repositories.store` owns Scout persistence operations.
- Never hardcode AWS credentials or secrets. Sensitive Terraform vars come via
  `TF_VAR_*` in CI.
- Infra dirs are always named `infra/`; modules under `modules/`, environments
  under `envs/`. Shared ACM cert + Route53 zone are referenced via `data`
  sources, never recreated.
