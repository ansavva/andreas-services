#!/usr/bin/env bash
# =============================================================================
# deploy.sh – Full deployment script for the NYC Events Aggregator
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

# ─── Defaults ────────────────────────────────────────────────────────────────
STACK_NAME="${STACK_NAME:-nyc-events}"
REGION="${AWS_REGION:-us-east-1}"
SKIP_FRONTEND=false
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --stack-name) STACK_NAME="$2"; shift 2 ;;
    --region)     REGION="$2";     shift 2 ;;
    --skip-frontend) SKIP_FRONTEND=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ─── Load .env if it exists ───────────────────────────────────────────────────
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a; source "${PROJECT_ROOT}/.env"; set +a
fi

# ─── Validate required variables ─────────────────────────────────────────────
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

log() { echo "[$(date '+%H:%M:%S')] $*"; }
section() { echo; echo "═══ $* ═══"; }

# =============================================================================
# 1. Package Lambda functions
# =============================================================================
section "Packaging Lambda functions"

package_lambda() {
  local name="$1"
  local src_dir="${PROJECT_ROOT}/lambda/${name}"
  local zip_file="${PROJECT_ROOT}/lambda/${name}.zip"

  log "Packaging ${name}..."
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  cp -r "${src_dir}/." "${tmp_dir}/"

  # Install Python dependencies if requirements.txt exists
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
# 2. Upload Lambda packages to S3
# =============================================================================
section "Uploading Lambda packages to S3"

aws s3 cp "${PROJECT_ROOT}/lambda/email-processor.zip" \
  "s3://${LAMBDA_CODE_BUCKET}/lambda/email-processor.zip" \
  --region "${REGION}"

aws s3 cp "${PROJECT_ROOT}/lambda/events-api.zip" \
  "s3://${LAMBDA_CODE_BUCKET}/lambda/events-api.zip" \
  --region "${REGION}"

log "Packages uploaded to s3://${LAMBDA_CODE_BUCKET}/lambda/"

# =============================================================================
# 3. Deploy / update CloudFormation stack
# =============================================================================
section "Deploying CloudFormation stack: ${STACK_NAME}"

aws cloudformation deploy \
  --template-file "${PROJECT_ROOT}/cloudformation.yaml" \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName="${STACK_NAME}" \
    LambdaCodeBucket="${LAMBDA_CODE_BUCKET}" \
    OpenAIApiKey="${OPENAI_API_KEY}" \
    GmailClientId="${GMAIL_CLIENT_ID}" \
    GmailClientSecret="${GMAIL_CLIENT_SECRET}" \
    GmailAccessToken="${GMAIL_ACCESS_TOKEN}" \
    GmailRefreshToken="${GMAIL_REFRESH_TOKEN}" \
  --no-fail-on-empty-changeset

log "CloudFormation stack deployed."

# =============================================================================
# 4. Retrieve stack outputs
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
WEBSITE_URL="$(get_output WebsiteURL)"

log "API endpoint : ${API_ENDPOINT}"
log "S3 bucket    : ${S3_BUCKET}"
log "Website URL  : ${WEBSITE_URL}"

# =============================================================================
# 5. Update Lambda function code (picks up any code changes post-CFn deploy)
# =============================================================================
section "Updating Lambda function code"

aws lambda update-function-code \
  --function-name "${STACK_NAME}-email-processor" \
  --s3-bucket "${LAMBDA_CODE_BUCKET}" \
  --s3-key "lambda/email-processor.zip" \
  --region "${REGION}" \
  --output table \
  --query '{FunctionName:FunctionName,CodeSize:CodeSize}'

aws lambda update-function-code \
  --function-name "${STACK_NAME}-events-api" \
  --s3-bucket "${LAMBDA_CODE_BUCKET}" \
  --s3-key "lambda/events-api.zip" \
  --region "${REGION}" \
  --output table \
  --query '{FunctionName:FunctionName,CodeSize:CodeSize}'

# =============================================================================
# 6. Build and deploy React frontend
# =============================================================================
if [[ "${SKIP_FRONTEND}" == "false" ]]; then
  section "Building React frontend"

  cd "${PROJECT_ROOT}/frontend"

  if [[ ! -d node_modules ]]; then
    log "Installing npm dependencies..."
    npm install --silent
  fi

  REACT_APP_API_URL="${API_ENDPOINT}" npm run build

  section "Deploying frontend to S3"

  aws s3 sync build/ "s3://${S3_BUCKET}/" \
    --region "${REGION}" \
    --delete \
    --cache-control "public,max-age=31536000,immutable" \
    --exclude "*.html"

  # HTML files: no-cache so updates are reflected immediately
  aws s3 sync build/ "s3://${S3_BUCKET}/" \
    --region "${REGION}" \
    --cache-control "no-cache,no-store,must-revalidate" \
    --include "*.html"

  log "Frontend deployed to s3://${S3_BUCKET}/"

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
