# Humbugg.Api.IntegrationTests — the integration tier

This assembly is the tier boundary: everything in it talks to **real AWS** — the
per-machine dev stack that `humbugg/scripts/dev-aws-setup.sh` provisions. Nothing
in it may run on a PR (PR workflows never write to AWS), so every test is gated by
`[IntegrationFact]`, which skips unless `HUMBUGG_INTEGRATION=1`.

Run it with the one sanctioned entry point, which exports the flag and preflights
credentials and the env file:

```bash
humbugg/scripts/dev-test-integration.sh
```

## What lives here

- `Data/` — the DynamoDB repository classes, exercised against real tables: item
  marshalling round trips (`DynamoValues`), key construction, GSI queries,
  conditional writes, transactions, and absent-attribute defaults. These 12
  classes are the one layer the unit tier cannot see, because unit tests fake at
  the `I*Repository` interfaces above them.
- `Http/` — in-process HTTP tests via `WebApplicationFactory<Program>`: the JWT
  pipeline, CORS, the error-envelope contract, and full-stack flows. (Phase 2.)

## Where does my test go?

- Exercises a service, the matching engine, email composition, or anything a
  hand-written fake can stand in for → `Humbugg.Api.Tests` (unit, runs on PR).
- Exercises a repository's actual DynamoDB expressions, or the HTTP pipeline
  end to end → here.
- Exercises the deployed system (IAM, CloudFront, SES feedback) → the post-deploy
  smoke jobs in `.github/workflows/humbugg-prod.yaml`.

## Rules

- **Every id a test writes starts with `itest-`** (use `Uid("...")`), and every
  written item registers cleanup (`CleanupItem`/`Cleanup`). The tables are shared
  with your local dev app; `dev-aws-reset.sh` is the blunt fallback, not the plan.
- **Reads through a GSI go through `Eventually(...)`** — GSIs are eventually
  consistent, and a bare read-after-write assertion is a flake, not a test.
- **Never point at prod.** Configuration comes only from `humbugg/backend/.env`,
  which `dev-aws-setup.sh` writes from the machine-scoped Terraform outputs.
  `AWS_PROFILE` in that file is deliberately ignored; credentials come from the
  ambient default chain, same as the AWS CLI.
