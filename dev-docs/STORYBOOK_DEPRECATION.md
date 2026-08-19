# Deprecating storybook into studio

Plan, not a decision. Three open questions at the bottom.

## Bottom line

**Storybook holds no production data.** This is a teardown, not a migration.

| Store | Contents |
|---|---|
| 11 `storybook-prod-*` DynamoDB tables | 0 rows each (`scan --select COUNT`, not the cached `ItemCount`) |
| `storybook-prod-files-us-east-1` | 0 objects |
| `storybook-dev-files-us-east-1` | 0 objects |
| `storybook-prod-web-us-east-1` | 9 objects — the SPA bundle |
| `storybook-prod` Cognito pool | 0 users |
| `storybook-dev` Cognito pool | 0 users |

Nothing to export, nothing to back up, no cutover window.

The portrait half of the concept **already exists in studio**, and in a better form. The
story/book half **does not exist anywhere in studio** and is the only part worth building.

## What storybook actually is

Two products sharing one Flask app.

| Half | Flow |
|---|---|
| **Model project** | upload photos → SQS worker normalises → Replicate **fine-tune** → inference against the tuned model |
| **Story project** | child profile → character bible → chat-authored story → compiled pages → per-page illustration → PDF |

State machine on the story half: `DRAFT_SETUP → CHARACTER_PREVIEW → CHAT → COMPILED →
ILLUSTRATING → READY → EXPORTED`.

## Concept mapping

| Storybook | Studio | Verdict |
|---|---|---|
| model project | `projects/<project>/` | **exists** |
| subject photos | `characters/<name>/seed/` | **exists** |
| character asset / bible | `characters/<name>/profile.yaml` + `reference/` | **exists**, richer — described index, `default_set`, curate |
| image normalisation worker (SQS Lambda) | `objects/convert.py` + upload | **exists**, synchronous, no queue |
| Replicate fine-tune + training run | — | **drop** — see below |
| generation history | the run store | **exists**, richer — request/prompt/result, runrefs, `find --character` |
| model chat / story chat | Claude, in session | **exists** — the skills *are* the chat |
| child profile | — | **drop** — PII of minors, and studio is single-operator |
| story project + pages + PDF export | — | **build** |
| public sign-up, multi-user | — | **drop** — studio is admin-create-only, one account |

### Why fine-tuning is dropped, not ported

Storybook trains a per-subject Replicate model and generates against it. Studio holds identity
with **reference images** instead — Nano Banana takes ≤14, Seedance 9, Kling 7, all selected
deliberately from a described index rather than by folder listing. That is the whole design of
`characters/`, and the current model generation is good at it.

Porting training back in means adding a lifecycle studio has never had: a training run record, a
poll loop over the Replicate trainings API, a per-subject model to store and version, and a
cold-start on every first generation. It buys identity fidelity studio already gets for free.

Reversing this later is possible — `add-model` treats models as data — but it should be argued
for on its own, not carried in on the back of a deprecation.

## The one architectural collision

`docs/WEB_APP.md` states the boundary plainly: **studio's app reads and tidies the library, it
does not produce it.** Generation runs locally, under a human's own AWS login, through the CLI.
Storybook's entire UX is the opposite — a generation wizard in the browser.

Two ways out:

**A — the book becomes a pipeline tier.** `studio book` plus a `studio-media-book` skill. One
approval gate per illustration, same as every other run. Studio's app browses the result. The
boundary is untouched, no new AWS surface. **Recommended.**

**B — studio's API generates.** Breaks the documented rule and needs the machinery that rule
avoids: async job state (API Gateway + Lambda cannot hold a 60-second illustration, which is
exactly why storybook needed an SQS worker), a second Lambda, and a database for job status —
reintroducing the DynamoDB that studio deliberately has none of.

Take B only if someone other than you needs to use this. Otherwise A.

## Phase 1 — Build the book tier (option A)

Only if the story half survives Q1 below. Nothing here depends on storybook still running.

**The tier.** `run ⊂ page ⊂ book`, parallel to the existing `run ⊂ shot ⊂ scene ⊂ movie`.

```
projects/<project>/books/<slug>/
    book.json     the plan AND the record — pages in order, text + illustration runref per page
    pages/        each illustration copied in, numbered in page order
    output/       <slug>.pdf
```

Mirrors `scenes/` deliberately: keyed by slug, created before anything renders, derived and never
a source of truth, sources copied in server-side with the originating runref recorded beside the
copied key.

**Work:**

- `domain/books.py` — the book store: manifest, page CRUD, `assemble`, the read-only CLI half.
- A PDF step. `reportlab` layout logic lifts cleanly from storybook's `pdf_export_service.py` —
  recover it from git history rather than rewriting it.
- Wire into `cli.py` and a `_Grouped.SECTIONS` list; a command in neither never appears in
  `studio --help`.
- Tests in `pipeline/tests/` — wiring and execution, not just `--help`.
- Regenerate `cli_surface_reference.json` deliberately. Never edit it to make a test pass.
- `.claude/skills/studio-media-book/SKILL.md` — **media family**, so it names no module, path or
  function. `lint_skills.py` fails the build otherwise.
- Document in `docs/PIPELINE.md` (tiers section + module table) and `studio/CLAUDE.md` (skill
  table).

**Hard rules apply unchanged:** full-payload approval per illustration, S3 as the only origin, no
character name anywhere in the repo.

**Do not port:** the seven-state machine (a `book.json` with pages *is* the state), the chat
services, `stability_service` / `openai_service` (models come from the registry), any DynamoDB.

## Phase 2 — Teardown

Order matters. Two steps fail if done in the wrong order.

1. **Set `force_destroy = true` on both buckets in `storybook/infra/modules/storage`, apply, and
   only then destroy.** `storybook-prod-web-us-east-1` holds 9 objects and is versioned, so a
   destroy without it fails `BucketNotEmpty`. The flag has to be *in state* before the destroy
   plan reads it — the same lesson the root `CLAUDE.md` records from August 2026. The ECR repos
   already carry `force_delete = true` and the CloudFront function and OAC already carry
   `create_before_destroy`; those are fine as they stand.
2. `terraform destroy` on `storybook/infra/envs/prod` — 53 resources. CloudFront disable + delete
   dominates the wall clock (~15–20 min). The `storybook.andreas.services` A record goes with it.
3. `terraform destroy` on `storybook/infra/envs/dev` — 11 resources (Cognito pool, SQS pair, one
   empty bucket). Same `force_destroy` step, one apply.
4. Delete `s3://andreas-services-terraform-state/storybook/{prod,dev}/terraform.tfstate`.
5. Delete the 13 `/storybook/prod/*` SSM parameters — the deploy workflow writes them, Terraform
   does not own them, so a destroy leaves them behind.
6. Verify: no storybook Lambda, table, bucket, pool or distribution; NXDOMAIN on
   `storybook.andreas.services`.

Then the repo:

7. `rm -r storybook/` and `.github/workflows/storybook-{pr.yml,prod.yaml}`. Git history keeps
   every line — it is also where Phase 1 recovers the PDF code from.
8. Reference cleanup, file by file:

| File | Change |
|---|---|
| `infra/envs/shared/main.tf:336` | drop `parameter/storybook/*` from the SSM statement. Lines 161/245/252 only *mention* storybook in comments — those ECR/Cognito/SQS statements are wildcard and serve studio, scout and humbugg. Reword, do not remove. |
| `CLAUDE.md` | services table row; the "Flask services — e.g. storybook" heading; "following the storybook pattern"; "Storybook uses strict mode" |
| `AGENTS.md` | same four — it mirrors `CLAUDE.md` |
| `README.md:5` | drop the bullet |
| `website/CLAUDE.md:20` | reword to humbugg/studio |
| `dev-docs/TERRAFORM_ARCHITECTURE.md` | drop storybook |
| `.pre-commit-config.yaml:26,32` | drop storybook from both file globs |
| `.claude/hooks/session-start.sh:79` + the `.codex/` mirror | drop `storybook/backend` from the poetry loop |
| `.vscode/launch.json`, `.gitignore` | drop storybook entries |
| `mailer/tests/*`, `humbugg/…/MailerIntegrationTests.cs` | check first — likely fixture strings, likely fine |

The shared apply is its own workflow and can run any time after the storybook CI role no longer
needs the SSM grant.

## Cost, and what teardown actually buys

AWS cost is ≈ zero today: pay-per-request DynamoDB at 0 rows, an idle Lambda, an idle CloudFront.
Cost is not the argument.

What goes away: 217 files, ~4.3k lines of backend, two workflows, 64 Terraform resources, and a
second Flask + React + HeroUI dependency set to keep patched.

**And one live exposure.** `storybook-prod`'s Cognito pool has `AllowAdminCreateUserOnly = false`
— public sign-up is open at `storybook.andreas.services`, against a Lambda holding
`REPLICATE_API_TOKEN`, `OPENAI_API_KEY` and `STABILITY_API_KEY`. Nobody has registered. It is the
reason to run Phase 2 **before** Phase 1 rather than after.

## Recommended sequence

Teardown first (hours), then build if wanted. Nothing in the book tier depends on storybook
running, git history keeps the code, and the open sign-up is the tiebreaker.

## Open decisions

1. **Does the story/book half survive at all?** If no, Phase 1 disappears and this is a one-day
   teardown. If yes, it is the only real engineering in the plan.
2. **Will anyone but you ever use this?** If yes, none of studio's design holds — single
   operator, local-against-prod, admin-create-only — and this becomes a rewrite, not a merge.
3. **Keep fine-tuning?** Recommend no, for the reasons above. Worth being explicit, because it is
   the one capability that genuinely disappears.
