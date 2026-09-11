# Claude Instructions – classroom

Read the root `CLAUDE.md` first. This file covers what is specific to this
service.

## What it is

One teacher publishes a lesson; a class opens its link. She authors the lesson
in her own tools and uploads the files; classroom stores them and serves them
back untouched. Nothing else.

Resisting scope here is deliberate — a gradebook, a submission inbox or a roster
each drag in student PII, and this service deliberately stores none: no student
ever has an account, and nothing about a student is written down.

**There is no editor, and adding one would be a change of product.** She writes
the lesson in Word, Canva, Google Docs or by hand; this publishes what that
produced.

## The rule that governs every change

**Lessons are served from a different ORIGIN to the app, and that is the whole
security model.**

A lesson runs the teacher's own JavaScript — they are interactive, and that is
the requirement. So neither of the usual defences is available: sanitizing would
destroy her styling, and blocking scripts would break the lesson. What is left
is that her session tokens live in `localStorage` on
`classroom-admin.andreas.services` and a lesson is served from
`classroom.andreas.services`, so a script in a lesson cannot reach them. That is
the browser's same-origin policy, not a header.

Consequences, all of them load-bearing:

- **Never serve lesson content from the app's host.** Not a route, not a proxy
  endpoint, not an iframe with `srcdoc`. Any of those puts uploaded markup back
  on the origin that holds her session.
- **Never render lesson HTML inside the app.** A preview is a link to the real
  lesson URL; cross-origin does the isolating.
- **The API's CORS stays narrow.** It allows the admin origin. Widening it to
  `*` would let lesson scripts call the API.
- **`draft/` must stay unreachable.** A CloudFront function refuses anything
  outside `/lesson/`; without it, an unpublished lesson is live at a guessable
  URL and publishing means nothing.

`infra/modules/lesson_hosting/main.tf` carries the full reasoning and the one
residual risk that was accepted (cross-subdomain cookies).

**The second boundary is path validation on upload.** A path arrives from the
browser and becomes part of an S3 key that a presigned URL grants write access
to, so an unchecked one writes over another teacher's published lesson.
`backend/tests/test_lesson_paths.py` is the specification — add to it in the
same change as any rule you touch. Note it pulls both ways: `pie chart.png` and
`Café/menu.png` must be ACCEPTED, because her HTML references those names and
renaming them for her breaks the lesson.

## Things that will bite

- **The Cognito `sub` is the partition key for every page.** Anything that
  replaces the user pool orphans every page ever written.
  `username_configuration` in `infra/modules/auth/main.tf` is ForceNew, which is
  why it is set at creation and must not be edited after.
- **Publication is files, not a flag.** `published` records an outcome; what
  gates a lesson is whether objects exist under `lesson/<id>/`. Setting the flag
  without moving the files serves nothing, or serves a withdrawn lesson.
- **A re-upload must re-publish.** A published lesson whose draft changes has to
  be copied forward, or her class keeps reading the previous version with no
  sign anything changed. `services/pages.finish_upload` does this.
- **The lesson bucket is versioned, and `s3 rm --recursive` does not empty it.**
  Old versions survive — billed and restorable. `dev-aws-reset.sh` deletes
  versions and delete-markers explicitly.
- **`count` must not depend on a resource attribute.** `modules/lessons` gates
  its bucket policy on a literal `serve_via_cloudfront` bool rather than on
  `cloudfront_distribution_arn != ""`, because adding a `depends_on` made the
  ARN unknown at plan time and failed the whole plan with "Invalid count
  argument" — an error `terraform validate` cannot see.
- **`module.lesson_hosting` depends_on `module.hosting`.** They share no
  reference, but `classroom.andreas.services` moves from one distribution to the
  other, and CloudFront refuses an alias another distribution still holds.
- **The frontend is a design-system consumer.** Read the `design-system-ui`
  skill before touching a screen. The `.web` leaf resolution in `vite.config.ts`
  and `tsconfig.json` is load-bearing and fails silently.
- **`managed-login-settings.json` is generated.** Do not hand-edit it; run
  `npm run brand` in `frontend/`. `npm run brand:check` gates it on every PR.

## Running it

Use the per-machine dev stack; never point local work at prod. Every page is
keyed by a Cognito `sub`, so a local app signed in against the prod pool writes
rows beside a real teacher's.

```bash
./classroom/scripts/dev-aws-setup.sh   # pool + table + lesson bucket
./classroom/scripts/dev-user.sh        # its one teacher account
./classroom/scripts/dev-setup.sh       # ~/.config/andreas-services/classroom/dev.env + both toolchains
./classroom/scripts/dev-up.sh          # app :5174, API and lessons :8001
```

`handlers/local/api/api_dev_server.py` stands in for two deployed things at
once: API Gateway's Cognito authorizer (prod verifies the token and hands Flask
the claims, so `auth.py` verifies no signature itself) and the lesson
CloudFront. Keep both in step with what they imitate — a local server more
permissive than production hides exactly the bugs the split exists to prevent.

## Local commands

```bash
# backend unit tests — moto, no stack needed
cd classroom/backend
CLASSROOM_PAGES_TABLE=classroom-test-pages poetry run pytest tests/ -v

# frontend (needs a GitHub Packages token for the design system)
cd classroom/frontend
eval "$(../../scripts/github-packages-auth.sh --export)"
npm ci && npm run lint && npm run typecheck && npm test && npm run brand:check && npm run build

# infra — both roots, as CI does
for env in prod dev; do
  terraform -chdir=classroom/infra/envs/$env init -backend=false &&
  terraform -chdir=classroom/infra/envs/$env validate
done
```
