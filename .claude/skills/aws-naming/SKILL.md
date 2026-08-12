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
- **env** — `prod` or `dev`. Always the **second** segment, never the last,
  never omitted. There are no ephemeral preview environments; PR workflows
  validate and never write to AWS.
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
| `Environment` | `prod` / `dev` |
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

## Executing a rename without breaking things

Every failure below happened while renaming humbugg. None was caught by
`terraform validate` — the configuration was valid each time, and wrong.

### Renaming A→B and B→C in one pass crosses the wires

humbugg needed `app` (avatars) to become `app_files` so that `app_web` (the SPA)
could become `app`. Do those as text substitutions in the wrong order and the
second rename lands on what the first just created. It happened twice in one
change, and both times the result was valid HCL: the `app_files_*` outputs
resolved to the SPA bucket, so avatars would have been served from the wrong
bucket and the SPA's policy applied to the other one.

Rename the *vacating* resource first, and afterwards **read the resulting
values, not the diff you intended**:

```bash
grep -n "value" modules/storage/outputs.tf   # does each output point where its NAME says?
```

A rename that swaps two identifiers is the one case worth checking by hand every
time.

### A `moved` block's `from` is the address in state *today*

```hcl
moved {
  from = module.hosting.aws_cloudfront_distribution.app          # today's state
  to   = module.hosting_marketing.aws_cloudfront_distribution.app # the new config
}
```

Rewrite `from` to the new path — easy to do with a careless global
search-and-replace over the file — and the block becomes a silent no-op.
Terraform then destroys and recreates instead of moving. For a CloudFront
distribution that is a ~15 minute outage in exchange for nothing.

`terraform plan` is the only check that catches this. **Every `moved` block must
appear in the plan as a move.** If a resource you wrote a `moved` block for shows
up under "will be destroyed", the `from` address is wrong.

### The module you are moving *to* is not in state yet

This one orphaned a live certificate and a live CloudFront distribution.

Clearing state before a rebuild, the instinct is to preserve the modules holding
resources you did not tear down:

```bash
# WRONG — module.certificates has never been applied, so it is not in state.
terraform state list | grep -vE 'module\.(certificates|email|billing)' | ...
```

The certificate was still at `module.hosting.aws_acm_certificate.app` and only
moves to `module.certificates` when the `moved` block is **applied**. Preserving
the destination address preserved nothing and removed the real entry — leaving
the certificate, the distribution and the Route53 aliases alive in AWS and
untracked. The next apply then fails with `CNAMEAlreadyExists`, because a
CloudFront alias cannot be claimed by a second distribution.

**Preserve addresses you have read out of `terraform state list`, never
addresses you have read out of the configuration.**

### Two mechanical traps in state surgery

`xargs` performs its own quote processing, so `for_each` addresses lose their
brackets' quotes and Terraform rejects `canonical[A]` with "Index value
required". Non-indexed resources succeed, which makes it look like a partial
failure rather than a systematic one:

```bash
terraform state list | grep -vE '...' | while IFS= read -r addr; do
  terraform state rm "$addr"
done
```

And a plan run without the `TF_VAR_*` values CI supplies will propose destroying
anything guarded by `count = var.x != "" ? 1 : 0`. In this repo that is the three
Stripe SSM parameters. They are not really changing — but applying locally
without those variables really does delete them.

## Adding a service

Pick the project name to match the directory, define `local.common_tags` with
all four tags, and name every resource from the pattern above. If a component
name needs explaining in a comment, it's the wrong component name.
