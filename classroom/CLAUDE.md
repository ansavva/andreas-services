# Claude Instructions – classroom

Read the root `CLAUDE.md` first. This file covers what is specific to this
service.

## What it is

One teacher writes a page; a class opens its link. Nothing else. Resisting
scope here is deliberate — a gradebook, a submission inbox or a roster each drag
in student PII, and this service deliberately stores none: no student ever has
an account, and nothing about a student is written down.

## The rule that governs every change

**Teacher-authored HTML reaches students from our own origin.** Treat it as a
stored-XSS sink at all times. Two layers, and a change must not weaken either:

1. `backend/classroom_core/utils/html.py` sanitizes on write.
2. `backend/classroom_core/routes/public.py` serves under `script-src 'none'`.

If you add a tag or attribute to the allowlist, add a test to
`backend/tests/test_sanitizer.py` in the same change proving what it still
rejects. Never render an unsanitized draft with `dangerouslySetInnerHTML` — the
editor shows escaped source for exactly this reason.

## Things that will bite

- **The Cognito `sub` is the partition key for every page.** Anything that
  replaces the user pool orphans every page ever written. `username_configuration`
  in `infra/modules/auth/main.tf` is ForceNew, which is why it is set at
  creation and must not be edited after.
- **Slugs are stable across edits.** Reissuing one silently breaks every link a
  teacher has already handed out. `services/pages.py` documents this.
- **GSI1 attributes are the publish flag.** Publishing writes them, withdrawing
  removes them. There is no `published` filter on the public read path, so a
  bug that writes GSI1 unconditionally publishes every draft.
- **`nh3` panics if `rel` is allowlisted on `<a>`** while `link_rel` is also
  set — ammonia asserts they cannot both define it. The allowlist comments say
  so; the failure is a `PanicException`, not a type error.
- **The frontend is a design-system consumer.** Read the `design-system-ui`
  skill before touching a screen. The `.web` leaf resolution in
  `vite.config.ts` and `tsconfig.json` is load-bearing and fails silently.

## Local commands

```bash
# backend
cd classroom/backend
CLASSROOM_PAGES_TABLE=classroom-test-pages poetry run pytest tests/ -v

# frontend (needs a GitHub Packages token for the design system)
cd classroom/frontend
eval "$(../../scripts/github-packages-auth.sh --export)"
npm ci && npm run lint && npm run typecheck && npm test && npm run build

# infra
terraform -chdir=classroom/infra/envs/prod init -backend=false && \
terraform -chdir=classroom/infra/envs/prod validate
```
