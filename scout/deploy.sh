#!/usr/bin/env bash
# =============================================================================
# deploy.sh – Full deployment script for Scout
#
# Resolves the shared ACM certificate and Route53 zone from AWS automatically
# (owned by terraform/envs/shared) — no manual ARN configuration required.
#
# Usage:
#   ./deploy.sh [--stack-name NAME] [--region REGION] [--skip-frontend]
#
# Required environment variables (or set in .env):
#   LAMBDA_CODE_BUCKET  - S3 bucket for Lambda zip files (must exist)
#   OPENAI_API_KEY
#   GMAIL_CLIENT_ID
#   GMAIL_CLIENT_SECRET
#   GMAIL_ACCESS_TOKEN
#   GMAIL_REFRESH_TOKEN
# =============================================================================
set -euo pipefail

STACK_NAME="${STACK_NAME:-scout}"
REGION="${AWS_REGION:-us-east-1}"
SKIP_FRONTEND=false
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
  case $1 in
    --stack-name) STACK_NAME="$2"; shift 2 ;;
    --region)     REGION="$2";     shift 2 ;;
    --skip-frontend) SKIP_FRONTEND=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a; source "${PROJECT_ROOT}/.env"; set +a
fi

required_vars=(
  LAMBDA_CODE_BUCKET
  OPENAI_API_KEY
  GMAIL_CLIENT_ID
  GMAIL_CLIENT_SECRET
  GMAIL_ACCESS_TOKEN
  GMAIL_REFRESH_TOKEN
)
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: Required environment variable '$var' is not set."
    exit 1
  fi
done

log()     { echo "[$(date '+%H:%M:%S')] $*"; }
section() { echo; echo "═══ $* ═══"; }

# =============================================================================
# 1. Resolve shared infrastructure values from AWS
#    (ACM cert and Route53 zone are owned by terraform/envs/shared)
# =============================================================================
section "Resolving shared infrastructure"

ACM_CERT_ARN=$(aws acm list-certificates \
  --region us-east-1 \
  --query "CertificateSummaryList[?DomainName=='*.andreas.services'].CertificateArn | [0]" \
  --output text)

if [[ -z "${ACM_CERT_ARN}" || "${ACM_CERT_ARN}" == "None" ]]; then
  echo "ERROR: Could not find *.andreas.services ACM certificate."
  echo "       Ensure terraform/envs/shared has been applied first."
  exit 1
fi

HOSTED_ZONE_ID=$(aws route53 list-hosted-zones \
  --query "HostedZones[?Name=='andreas.services.'].Id | [0]" \
  --output text | sed 's|/hostedzone/||')

if [[ -z "${HOSTED_ZONE_ID}" || "${HOSTED_ZONE_ID}" == "None" ]]; then
  echo "ERROR: Could not find andreas.services Route53 hosted zone."
  echo "       Ensure terraform/envs/shared has been applied first."
  exit 1
fi

log "ACM cert ARN  : ${ACM_CERT_ARN}"
log "Hosted zone ID: ${HOSTED_ZONE_ID}"

# =============================================================================
# 2. Package Lambda functions
# =============================================================================
section "Packaging Lambda functions"

package_lambda() {
  local name="$1"
  local src_dir="${PROJECT_ROOT}/lambda/${name}"
  local zip_file="${PROJECT_ROOT}/lambda/${name}.zip"
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  log "Packaging ${name}..."
  cp -r "${src_dir}/." "${tmp_dir}/"

  if [[ -f "${src_dir}/requirements.txt" ]]; then
    pip install -q -r "${src_dir}/requirements.txt" -t "${tmp_dir}" --upgrade
  fi

  (cd "${tmp_dir}" && zip -q -r "${zip_file}" .)
  rm -rf "${tmp_dir}"
  log "  → ${zip_file}"
}

package_lambda "email-processor"
package_lambda "events-api"

# =============================================================================
# 3. Upload Lambda packages to S3
# =============================================================================
section "Uploading Lambda packages to S3"

aws s3 cp "${PROJECT_ROOT}/lambda/email-processor.zip" \
  "s3://${LAMBDA_CODE_BUCKET}/lambda/email-processor.zip" --region "${REGION}"

aws s3 cp "${PROJECT_ROOT}/lambda/events-api.zip" \
  "s3://${LAMBDA_CODE_BUCKET}/lambda/events-api.zip" --region "${REGION}"

# =============================================================================
# 4. Deploy CloudFormation stack
# =============================================================================
section "Deploying CloudFormation stack: ${STACK_NAME}"

aws cloudformation deploy \
  --template-file "${PROJECT_ROOT}/cloudformation.yaml" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    ProjectName="${STACK_NAME}" \
    LambdaCodeBucket="${LAMBDA_CODE_BUCKET}" \
    AcmCertificateArn="${ACM_CERT_ARN}" \
    Route53HostedZoneId="${HOSTED_ZONE_ID}" \
    OpenAIApiKey="${OPENAI_API_KEY}" \
    GmailClientId="${GMAIL_CLIENT_ID}" \
    GmailClientSecret="${GMAIL_CLIENT_SECRET}" \
    GmailAccessToken="${GMAIL_ACCESS_TOKEN}" \
    GmailRefreshToken="${GMAIL_REFRESH_TOKEN}"

log "CloudFormation stack deployed."

# =============================================================================
# 5. Retrieve stack outputs
# =============================================================================
section "Retrieving stack outputs"

get_output() {
  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='${1}'].OutputValue" \
    --output text
}

API_ENDPOINT="$(get_output ApiEndpoint)"
S3_BUCKET="$(get_output S3BucketName)"
CF_DIST_ID="$(get_output CloudFrontDistributionId)"
WEBSITE_URL="$(get_output WebsiteURL)"

log "API endpoint         : ${API_ENDPOINT}"
log "S3 bucket            : ${S3_BUCKET}"
log "CloudFront dist ID   : ${CF_DIST_ID}"
log "Website URL          : ${WEBSITE_URL}"

# =============================================================================
# 6. Update Lambda function code
# =============================================================================
section "Updating Lambda function code"

aws lambda update-function-code \
  --function-name "${STACK_NAME}-email-processor" \
  --s3-bucket "${LAMBDA_CODE_BUCKET}" \
  --s3-key "lambda/email-processor.zip" \
  --region "${REGION}" --output table \
  --query '{FunctionName:FunctionName,CodeSize:CodeSize}'

aws lambda update-function-code \
  --function-name "${STACK_NAME}-events-api" \
  --s3-bucket "${LAMBDA_CODE_BUCKET}" \
  --s3-key "lambda/events-api.zip" \
  --region "${REGION}" --output table \
  --query '{FunctionName:FunctionName,CodeSize:CodeSize}'

# =============================================================================
# 7. Build and deploy React frontend
# =============================================================================
if [[ "${SKIP_FRONTEND}" == "false" ]]; then
  section "Building React frontend"

  cd "${PROJECT_ROOT}/frontend"
  [[ ! -d node_modules ]] && npm install

  VITE_API_URL="${API_ENDPOINT}" npm run build

  section "Deploying frontend to S3"

  # Hashed assets — long-lived cache
  aws s3 sync dist/ "s3://${S3_BUCKET}/" \
    --region "${REGION}" --delete \
    --cache-control "public,max-age=31536000,immutable" \
    --exclude "*.html"

  # HTML — always revalidate
  aws s3 sync dist/ "s3://${S3_BUCKET}/" \
    --region "${REGION}" \
    --cache-control "no-cache,no-store,must-revalidate" \
    --include "*.html"

  section "Invalidating CloudFront cache"
  aws cloudfront create-invalidation \
    --distribution-id "${CF_DIST_ID}" \
    --paths "/*"

  cd "${PROJECT_ROOT}"
fi

# =============================================================================
# Done
# =============================================================================
section "Deployment complete"
echo
echo "  Website : ${WEBSITE_URL}"
echo "  API     : ${API_ENDPOINT}"
echo
