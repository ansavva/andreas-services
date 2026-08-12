#!/usr/bin/env bash
#
# ONE-TIME MIGRATION SCRIPT — delete this file once prod is rebuilt.
#
# Tears down every humbugg AWS resource carrying a pre-convention name, so the
# deploy workflow can recreate everything under [project]-[env]-[component].
# See the `aws-naming` skill for the convention and for which resources cannot
# be renamed without destroying data.
#
# This exists because most AWS resources cannot be renamed in place: a name
# change is a destroy and recreate, and Terraform cannot do that for a bucket
# whose name another resource is about to take.
#
# This DESTROYS DATA: DynamoDB tables, the Cognito user pool (every account and
# password), SQS queues. That is the intent — nothing here is in production use.
#
#   ./teardown-humbugg.sh --dry-run    # print what would be deleted, touch nothing
#   ./teardown-humbugg.sh              # do it (asks once)
#
# Order matters in exactly one place: the old avatars bucket holds the name
# humbugg-app-production, which nothing new wants — but the old SPA bucket name
# humbugg-appweb-production and the new humbugg-prod-app-* are different names,
# so there is no reuse collision here. Buckets still go first out of habit: an
# S3 name is not always immediately available after deletion.
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

say()  { printf '\033[1;34m[teardown]\033[0m %s\n' "$*"; }
did()  { printf '\033[1;32m[ gone ]\033[0m %s\n' "$*"; }
skip() { printf '\033[1;36m[ skip ]\033[0m %s\n' "$*"; }
run()  { if [[ $DRY -eq 1 ]]; then printf '\033[1;33m[would]\033[0m %s\n' "$*"; else eval "$@" >/dev/null 2>&1; fi; }

command -v jq >/dev/null || { echo "jq is required"; exit 1; }
aws sts get-caller-identity >/dev/null 2>&1 || { echo "not authenticated — run 'aws login'"; exit 1; }

if [[ $DRY -eq 0 ]]; then
  cat <<'WARN'
This permanently deletes humbugg's DynamoDB tables, Cognito user pool (all
accounts and passwords), SQS queues, S3 buckets, Lambdas and ECR repositories.
WARN
  read -r -p "Type 'destroy humbugg' to continue: " ans
  [[ "$ans" == "destroy humbugg" ]] || { echo "aborted"; exit 1; }
fi

# ── S3 ───────────────────────────────────────────────────────────────────────
# Every bucket is versioned, so `aws s3 rm --recursive` and `aws s3 rb --force`
# both leave versions and delete markers behind and the bucket stays undeletable.
for b in humbugg-web-production humbugg-app-production humbugg-appweb-production; do
  if ! aws s3api head-bucket --bucket "$b" >/dev/null 2>&1; then skip "bucket $b (absent)"; continue; fi
  say "emptying bucket $b"
  if [[ $DRY -eq 0 ]]; then
    while :; do
      payload=$(aws s3api list-object-versions --bucket "$b" --max-keys 500 --output json \
        --query '{Objects: [Versions, DeleteMarkers][][].{Key:Key,VersionId:VersionId}}')
      n=$(jq '(.Objects // []) | length' <<<"$payload")
      [[ "$n" -eq 0 ]] && break
      jq '{Objects: (.Objects // []), Quiet: true}' <<<"$payload" > /tmp/s3-del.json
      aws s3api delete-objects --bucket "$b" --delete file:///tmp/s3-del.json >/dev/null
    done
  fi
  run "aws s3api delete-bucket --bucket '$b'"
  did "bucket $b"
done

# ── Lambda ───────────────────────────────────────────────────────────────────
for f in humbugg-backend-production humbugg-frontend-production humbugg-email-status-production; do
  if aws lambda get-function --function-name "$f" >/dev/null 2>&1; then
    run "aws lambda delete-function --function-name '$f'"; did "lambda $f"
  else skip "lambda $f (absent)"; fi
done

# ── ECR ──────────────────────────────────────────────────────────────────────
# --force is required: a repository holding images will not delete without it.
for r in humbugg-backend-production humbugg-frontend-production; do
  if aws ecr describe-repositories --repository-names "$r" >/dev/null 2>&1; then
    run "aws ecr delete-repository --repository-name '$r' --force"; did "ecr $r"
  else skip "ecr $r (absent)"; fi
done

# ── DynamoDB ─────────────────────────────────────────────────────────────────
# These never had an environment segment, which is part of what this fixes.
for t in humbugg-profiles humbugg-groups humbugg-groupmembers humbugg-draws \
         humbugg-audit-events humbugg-analytics-events humbugg-billing \
         humbugg-email-messages humbugg-email-status-table-production; do
  if aws dynamodb describe-table --table-name "$t" >/dev/null 2>&1; then
    run "aws dynamodb delete-table --table-name '$t'"; did "table $t"
  else skip "table $t (absent)"; fi
done

# ── SQS ──────────────────────────────────────────────────────────────────────
url=$(aws sqs get-queue-url --queue-name humbugg-email-status-queue-production --query QueueUrl --output text 2>/dev/null)
if [[ -n "${url:-}" && "$url" != "None" ]]; then
  run "aws sqs delete-queue --queue-url '$url'"; did "queue humbugg-email-status-queue-production"
else skip "queue humbugg-email-status-queue-production (absent)"; fi

# ── Cognito ──────────────────────────────────────────────────────────────────
# Deleting the pool destroys every account. A pool with a custom domain would
# need that removed first; humbugg has none.
pool=$(aws cognito-idp list-user-pools --max-results 60 \
  --query "UserPools[?Name=='humbugg-production'].Id | [0]" --output text 2>/dev/null)
if [[ -n "${pool:-}" && "$pool" != "None" ]]; then
  run "aws cognito-idp delete-user-pool --user-pool-id '$pool'"; did "cognito pool humbugg-production ($pool)"
else skip "cognito pool humbugg-production (absent)"; fi

# ── SSM ──────────────────────────────────────────────────────────────────────
# The deploy workflow rewrites these; stale values would point the app at
# resources that no longer exist.
for p in api-url lambda-name ecr-url frontend-lambda-name frontend-ecr-url \
         cognito-user-pool-id cognito-client-id s3-bucket cf-dist-id \
         app-s3-bucket app-cf-dist-id api-domain email-from-address; do
  if aws ssm get-parameter --name "/humbugg/prod/$p" >/dev/null 2>&1; then
    run "aws ssm delete-parameter --name '/humbugg/prod/$p'"; did "ssm /humbugg/prod/$p"
  fi
done

say "done."
cat <<'NEXT'

NEXT: clear Terraform state, then let the deploy workflow apply.

  cd humbugg/infra/envs/prod
  terraform init
  terraform state list | grep -vE 'module\.(email|billing)' \
    | while IFS= read -r addr; do terraform state rm "$addr"; done

  Two traps in that command, both learned the hard way:

  * Use the read loop, NOT `xargs`. Addresses from for_each carry index
    brackets like canonical["A"]; xargs strips the quotes and Terraform
    rejects `canonical[A]` with "Index value required".

  * Preserve module.email and module.billing ONLY. An earlier version of this
    also preserved module.certificates — which does not exist in state. The
    certificate lives at module.hosting.aws_acm_certificate.app until the moved
    block is applied, so preserving the wrong address removed the real one and
    orphaned the certificate, the CloudFront distribution and the Route53
    aliases. That is what --orphans exists to clean up.

  Then:
  terraform plan

  Expect creates only. If it proposes destroying the three
  module.billing.aws_ssm_parameter.* entries, that is not a real change: each is
  count = var.stripe_* != "" ? 1 : 0, and the count collapses to 0 when the
  TF_VAR_stripe_* values are absent. CI supplies them from the humbugg-production
  environment. Do NOT apply locally without them or you will delete the Stripe
  credentials from SSM.

NEXT

# ── Orphans ──────────────────────────────────────────────────────────────────
# Resources that survived the rename but left Terraform state. The important one
# is the CloudFront distribution: it still holds the aliases humbugg.com,
# www.humbugg.com and humbugg.andreas.services, and CloudFront refuses to let a
# second distribution claim an alias already in use — so an apply fails with
# CNAMEAlreadyExists until this is gone.
#
# Run with --orphans after the main teardown. Deleting a distribution takes
# 10-20 minutes: it must be disabled, fully propagate to "Deployed", and only
# then can it be deleted.
if [[ "${1:-}" == "--orphans" || "${2:-}" == "--orphans" ]]; then
  say "cleaning up orphaned resources"

  dist=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?contains(Comment,'humbugg')].Id | [0]" --output text 2>/dev/null)
  if [[ -n "${dist:-}" && "$dist" != "None" ]]; then
    etag=$(aws cloudfront get-distribution-config --id "$dist" --query ETag --output text)
    enabled=$(aws cloudfront get-distribution-config --id "$dist" --query 'DistributionConfig.Enabled' --output text)
    if [[ "$enabled" == "True" ]]; then
      say "disabling distribution $dist (this is the slow part)"
      if [[ $DRY -eq 0 ]]; then
        aws cloudfront get-distribution-config --id "$dist" --query DistributionConfig > /tmp/cf.json
        jq '.Enabled = false' /tmp/cf.json > /tmp/cf-off.json
        aws cloudfront update-distribution --id "$dist" --distribution-config file:///tmp/cf-off.json --if-match "$etag" >/dev/null
        say "waiting for $dist to finish deploying ..."
        aws cloudfront wait distribution-deployed --id "$dist"
      else
        printf '\033[1;33m[would]\033[0m disable + wait for %s\n' "$dist"
      fi
    fi
    etag=$(aws cloudfront get-distribution-config --id "$dist" --query ETag --output text 2>/dev/null)
    run "aws cloudfront delete-distribution --id '$dist' --if-match '$etag'"
    did "cloudfront $dist"
  else
    skip "cloudfront distribution (absent)"
  fi

  # Alias records pointing at the distribution. Terraform creates these without
  # allow_overwrite, so a leftover record set fails the apply.
  zone=$(aws route53 list-hosted-zones-by-name --dns-name humbugg.com \
    --query "HostedZones[?Name=='humbugg.com.'].Id | [0]" --output text 2>/dev/null | sed 's|/hostedzone/||')
  if [[ -n "${zone:-}" && "$zone" != "None" ]]; then
    for rec in humbugg.com www.humbugg.com; do
      for type in A AAAA; do
        set=$(aws route53 list-resource-record-sets --hosted-zone-id "$zone" \
          --query "ResourceRecordSets[?Name=='${rec}.' && Type=='${type}']" --output json 2>/dev/null)
        [[ $(jq 'length' <<<"$set") -eq 0 ]] && { skip "route53 $type $rec (absent)"; continue; }
        if [[ $DRY -eq 0 ]]; then
          jq -n --argjson r "$(jq '.[0]' <<<"$set")" \
            '{Changes:[{Action:"DELETE",ResourceRecordSet:$r}]}' > /tmp/r53.json
          aws route53 change-resource-record-sets --hosted-zone-id "$zone" \
            --change-batch file:///tmp/r53.json >/dev/null 2>&1
        else
          printf '\033[1;33m[would]\033[0m delete route53 %s %s\n' "$type" "$rec"
        fi
        did "route53 $type $rec"
      done
    done
  fi

  # The certificate is replaced anyway: its SAN list gains app. and api., which
  # ACM cannot do in place. Deleting only works once nothing references it.
  cert=$(aws acm list-certificates --region us-east-1 \
    --query "CertificateSummaryList[?DomainName=='humbugg.com'].CertificateArn | [0]" --output text 2>/dev/null)
  if [[ -n "${cert:-}" && "$cert" != "None" ]]; then
    run "aws acm delete-certificate --region us-east-1 --certificate-arn '$cert'"
    did "acm $cert"
  else
    skip "acm certificate (absent)"
  fi

  say "orphan cleanup done"
fi
