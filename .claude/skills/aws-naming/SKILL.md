---
name: aws-naming
description: >-
  Repo rule. Name every AWS resource in andreas-services as
  [project]-[env]-[component]-[identifier] — lowercase kebab, environment always
  second, component named for what it serves. Covers the per-resource-type
  patterns, the global-uniqueness suffix S3 needs, the four required tags, and
  which resources cannot be renamed without destroying data. Use before creating
  or renaming any AWS resource, writing a new Terraform module, or adding a
  service.
---

# Naming AWS resources

## The pattern

```
[project]-[env]-[component]-[identifier]
```

`humbugg-prod-api` · `mailer-prod-ingress` · `scout-prod-events-api`

- **project** — the service directory name: `humbugg`, `mailer`, `scout`, `website`.
- **env** — `prod`, `dev`, or `pr-<number>` for ephemeral previews. Always the
  **second** segment, never the last, never omitted.
- **component** — what the resource *serves*, not which tier it belongs to.
  `api`, `marketing`, `app`, `email-status`. Not `backend`, not `frontend`.
- **identifier** — only when a component needs more than one instance
  (`...-dlq`, `...-role`). Leave it off otherwise.

Lowercase letters, digits and hyphens only. No underscores, no uppercase, no
spaces — several AWS services reject them and others handle them inconsistently.
Keep names short; per-service character limits are real (IAM roles 64, Lambda
64, S3 63, DynamoDB 255).

**If AWS can generate the name and nothing in our workflow needs to predict it,
let AWS generate it.** A name you never look up is a name that can't drift.

## Component names carry meaning — pick the one that's true

The failure this rule exists to prevent is a name that describes the *tier*
rather than the *thing*, because tiers stop being distinguishing the moment a
service has two of them. Humbugg had `humbugg-backend-production` (the API) and
`humbugg-frontend-production` (the marketing renderer) while `humbugg-web-*` was
a bucket of marketing assets and `humbugg-app-*` was a bucket of avatars. Every
one of those names was defensible on its own and the set was unreadable.

Name it after the surface it serves or the job it does:

| Serves | Component |
| --- | --- |
| `api.humbugg.com` | `api` |
| `www.humbugg.com` | `marketing` |
| `app.humbugg.com` | `app` |
| user-uploaded files for the app | `app-files` |
| a queue consumer | the thing it consumes — `email-status` |

## Per-resource-type patterns

Most resources are just `[project]-[env]-[component]`. These need more:

| Resource | Pattern | Example |
| --- | --- | --- |
| **S3 bucket** | `[project]-[env]-[component]-[region]` | `humbugg-prod-marketing-us-east-1` |
| **IAM role** | `[project]-[env]-[component]-role` | `humbugg-prod-api-role` |
| **IAM policy** | `[project]-[env]-[component]-[grant]` | `humbugg-prod-api-dynamodb` |
| **SQS DLQ** | `[project]-[env]-[component]-dlq` | `mailer-prod-feedback-dlq` |
| **CloudFront OAC** | `[project]-[env]-[component]-oac` | `humbugg-prod-app-files-oac` |
| **CloudWatch alarm** | `[project]-[env]-[component]-[condition]` | `mailer-prod-ses-bounce-rate` |
| **Log group** | `/aws/lambda/[function-name]` | derived — never hand-written |
| **SSM parameter** | `/[project]/[env]/[name]` | `/humbugg/prod/api-domain` |

**S3 bucket names are globally unique across all of AWS**, which is why they
alone take a suffix. Use the region code. A short random hash works too, but the
region is deterministic — Terraform can build it from the provider, and a human
reading the console learns something from it.

**IAM is where published guidance disagrees with itself.** The article this
convention came from puts role type first (`admin-myapp-prod`) while every other
type in the same table is project-first. We use **project-first everywhere**: a
console sorted by name should group by service, and one exception costs more in
confusion than it buys in readability.

## Tags do the work names can't

Names are constrained, sometimes immutable, and always one-dimensional. Tags are
none of those. **Every resource that supports tagging gets all four:**

| Tag | Value |
| --- | --- |
| `Project` | `humbugg` / `mailer` / `scout` / `website` |
| `Environment` | `prod` / `dev` / `pr-<number>` |
| `Owner` | the team or person accountable |
| `ManagedBy` | `terraform` |

Put them in `local.common_tags` in the environment's `main.tf` and pass them
into every module — that is the existing pattern in `humbugg/infra/envs/prod`.

**Do not overload the name with what a tag should carry.** Cost centre, owner,
ticket, lifecycle — those are tags. If you're tempted to add a fifth segment,
it's almost certainly a tag.

## Before you rename anything: know what it costs

A rename in Terraform is a **destroy and recreate** for most AWS resources.
Some of those are free; some destroy data irrecoverably. Check which you're
touching before you touch it.

**Free — recreated automatically:**
Lambda functions (the image is in ECR), ECR repositories (CI re-pushes), IAM
roles and policies, API Gateways, CloudFront OACs / functions / cache policies,
log groups, alarms, SSM parameters.

**Destroys data — needs an explicit decision, and usually a migration:**

| Resource | What is lost |
| --- | --- |
| Cognito user pool | every account and password. Users cannot be migrated with passwords intact — they must reset |
| DynamoDB table | every row |
| S3 bucket | every object. Names are also not immediately reusable after deletion |
| SQS queue | in-flight messages |
| SES domain identity | verification, until DNS re-propagates — outbound mail fails in the window |

CloudFront distributions have no name attribute at all: renaming the *Terraform
address* is free, and a `moved` block makes it a state move rather than a
15-minute replacement of a live distribution.

**Renaming a Terraform resource or module is not the same as renaming the AWS
resource.** Use `moved` blocks for the former; they cost nothing. Only a change
to the `name`/`bucket`/`function_name` argument triggers a replacement.

## Adding a service

Pick the project name to match the directory, define `local.common_tags` with
all four tags, and name every resource from the pattern above. If a component
name needs explaining in a comment, it's the wrong component name.
