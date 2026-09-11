# classroom

A place for a teacher to publish a lesson and hand its link to a class.

**Students open `classroom.andreas.services`. Teachers sign in at
`classroom-admin.andreas.services`.** Those are two different origins on
purpose — see [Two hosts](#two-hosts-and-why) below. The API is
`classroom-api.andreas.services` and sign-in is `classroom-auth.andreas.services`.

## What it does

A teacher builds a lesson in whatever tool she already uses — Word, Canva,
Google Docs, an HTML export from a worksheet generator, or hand-written HTML —
and uploads the result. Classroom stores those files and serves them back
**exactly as uploaded**: her styling, her images, her fonts and her JavaScript,
untouched. Lessons are interactive, so the scripts run.

Publishing yields a link (`/lesson/<id>/`) that students open with no account
and no sign-in. Withdrawing makes the link stop working without deleting
anything she uploaded.

There is no editor. She authors elsewhere; this publishes.

## Shape

| Piece | Stack |
| --- | --- |
| `backend/` | Flask on a container Lambda, DynamoDB + S3 via boto3, Cognito JWT at the gateway |
| `frontend/` | Vite + React 19 + TypeScript, UI from `@ansavva/design-system` |
| `infra/` | Terraform — S3, two CloudFront distributions, Lambda, API Gateway, Cognito, DynamoDB |

## A lesson is a directory

`classroom-prod-lessons-us-east-1` holds every lesson's files under two
prefixes:

```
draft/<page-id>/index.html          what she has uploaded. Never served.
draft/<page-id>/js/quiz.js
lesson/<page-id>/index.html         what students can open. Served, and only this.
lesson/<page-id>/js/quiz.js
```

**Publishing copies the first onto the second; withdrawing deletes the second.**
That is the only honest way to gate static hosting: there is no request for the
application to intercept, so an unpublished lesson must not *exist* at a
servable key. A CloudFront function refuses anything outside `/lesson/`, which
is what keeps `draft/` unreachable even though both live in one bucket.

The key prefix deliberately matches the URL path, so CloudFront maps a request
onto an object with no lookup and no Lambda — which is why her relative paths
(`images/diagrams/pie chart.svg`) resolve exactly as they did on her machine.
Nested folders work to any depth.

`classroom-prod-pages` in DynamoDB holds only what a directory cannot:

```
PK  TEACHER#<cognito-sub>     SK  PAGE#<ulid>
page_id  title  published  file_count  teacher_id  teacher_email
created_at  updated_at  entity_type
```

Keyed by the owning teacher, so her list is one query and one teacher cannot
address another's pages. There is no secondary index and no public read path —
students never reach the API at all.

## Two hosts, and why

Her lessons run their own JavaScript. That rules out both of the usual defences
against untrusted markup: a sanitizer would destroy her styling, and a
`script-src 'none'` policy would break the lesson.

So the protection is that lessons are served from a **different origin** to the
app she signs in to. Her session tokens live in `localStorage` on
`classroom-admin.andreas.services`, `localStorage` is scoped to an origin, and
so a script in a lesson cannot read them. That is the browser's same-origin
policy rather than a header we configured: it cannot be weakened by a later edit
and it holds even if a lesson is actively hostile.

This matters because the realistic risk is not a malicious teacher. It is a
teacher downloading a free worksheet template and uploading it without knowing
what is inside.

**Known residual risk, accepted deliberately:** a script on the lesson host can
set cookies scoped to `.andreas.services`, which sibling services would receive.
The complete fix is a separate registrable domain — what GitHub does with
`githubusercontent.com` — and is a domain purchase away if it ever matters.

`infra/modules/lesson_hosting` carries this reasoning next to the code.

## Uploads go straight to S3

The API signs a PUT per file and the browser sends the bytes directly to S3. A
zipped worksheet with its images runs to tens of megabytes and API Gateway stops
at 10MB, so routing content through the Lambda would fail on exactly the lessons
that matter most.

The browser turns all three upload shapes into one list of `(path, blob)` before
anything is signed: a single `.html` becomes `index.html`, a `.zip` is unpacked
client-side, and a chosen folder keeps its structure. It also strips the wrapper
directory that zips and folder pickers almost always add, which would otherwise
bury `index.html` one level too deep.

**Path validation is the security boundary of that API.** A path arrives from
the browser and becomes part of an S3 key that a presigned URL grants write
access to. `backend/tests/test_lesson_paths.py` is the specification: traversal,
absolute paths and empty segments are refused, while `pie chart.png`,
`Worksheet (final).html` and `Café/menu.png` are accepted — a teacher's HTML
references those names, so refusing or renaming them would break her lesson.

## Accounts

The Cognito pool is admin-create-only; there is no public sign-up. Add a teacher
with:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id "$(terraform -chdir=infra/envs/prod output -raw cognito_user_pool_id)" \
  --username teacher@example.com \
  --user-attributes Name=email,Value=teacher@example.com Name=email_verified,Value=true
```

Sign-in, password reset and MFA enrolment are Cognito's Managed Login pages,
styled from this app's own stylesheet — see [Branding](#branding).

## Local development

Classroom has a **per-machine dev stack** — its own Cognito pool, pages table and
lesson bucket, named `classroom-dev-<short12>-*` — keyed by a UUID in
`~/.config/andreas-services/classroom/machine-id`. Four commands from a fresh
clone:

```bash
./classroom/scripts/dev-aws-setup.sh   # pool + table + lesson bucket, ~60s
./classroom/scripts/dev-user.sh        # its one teacher account
./classroom/scripts/dev-setup.sh       # dev.env, poetry, node_modules
./classroom/scripts/dev-up.sh          # app on :5174, API and lessons on :8001
```

**Every local value lives in one file, `~/.config/andreas-services/classroom/dev.env`**
— the frontend's `VITE_*` values and the dev account — documented key by key in
[`dev.env.sample`](dev.env.sample). There is no `frontend/.env.local` any more;
`dev-setup.sh` imports and deletes one it finds. It sits outside the repo
because ignored files vanish on `git clean` and never exist in a fresh worktree,
while this one is per machine and shared by every checkout on it.
`CLASSROOM_DEV_ENV_FILE` overrides the location.

`dev-user.sh` reads the account's address from that file. Put a
`CLASSROOM_DEV_USER_EMAIL=` line in it (a `.test` address, so Cognito can never
mail a stranger on a typo) and pass `--generate-password` on the first run.

There is no CloudFront in the dev stack — a per-machine distribution would cost
twenty minutes an apply to prove nothing — so the local API serves
`/lesson/<id>/…` from S3 instead. The origin split still holds locally: the app
is `localhost:5174` and lessons are `localhost:8001`, and an origin includes its
port.

| Script | What it does |
| --- | --- |
| `dev-aws-setup.sh` | Applies this machine's Terraform stack. `--check` confirms it without applying. |
| `dev-user.sh` | Creates or converges the pool's one teacher account. `--check` is read-only. |
| `dev-setup.sh` | Writes `dev.env` from the stack; installs both toolchains. |
| `dev-up.sh` | Runs the app, the API and the lesson server together; exports `VITE_*` from `dev.env` first. |
| `dev-token.sh` | Prints an ID token, so `curl` can reach the local API. |
| `dev-aws-reset.sh` | Empties the table, the lesson bucket (every version) and the pool. |
| `dev-aws-destroy.sh` | Destroys the stack; keeps the machine id, so setup rebuilds the same names. |

```bash
curl -H "Authorization: Bearer $(./classroom/scripts/dev-token.sh)" \
     http://localhost:8001/api/pages
```

## Branding

The Cognito hosted pages are styled from a JSON document **generated** from the
design system's `theme.css` plus `frontend/src/styles/app.css`:

```bash
cd classroom/frontend && npm run brand        # regenerate
cd classroom/frontend && npm run brand:check  # CI gate
```

Nothing at runtime notices when the two drift — the sign-in page just quietly
stops matching the app — so `brand:check` runs on every PR.

## Tests

Unit tests need no stack; they run on moto.

```bash
cd classroom/backend && poetry run pytest tests/ -v
cd classroom/frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## Deployment

`classroom-pr.yml` validates every PR and never writes to AWS.
`classroom-prod.yaml` deploys from `main`:
`detect-changes → build-and-push → deploy-infra → update-lambda + deploy-frontend`.
