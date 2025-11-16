#!/usr/bin/env bash
set -euo pipefail

STAGE="${1:-}"

if [[ -z "$STAGE" ]]; then
  echo "Usage: deploy-environment.sh <staging|production>" >&2
  exit 1
fi

if [[ "$STAGE" != "staging" && "$STAGE" != "production" ]]; then
  echo "Stage must be 'staging' or 'production'." >&2
  exit 1
fi

if [[ -z "${AWS_REGION:-}" ]]; then
  echo "AWS_REGION is required." >&2
  exit 1
fi

if [[ -z "${API_IMAGE_URI:-}" ]]; then
  echo "API_IMAGE_URI is required (ECR image URI for the Lambda container)." >&2
  exit 1
fi

if [[ -z "${CLOUDFRONT_CERT_ARN:-}" ]]; then
  echo "CLOUDFRONT_CERT_ARN is required (ACM cert in us-east-1)." >&2
  exit 1
fi

if [[ -z "${VPC_ID:-}" || -z "${PRIVATE_SUBNET_IDS:-}" || -z "${DOCDB_SUBNET_IDS:-}" ]]; then
  echo "VPC_ID, PRIVATE_SUBNET_IDS, and DOCDB_SUBNET_IDS must be provided." >&2
  exit 1
fi

if [[ -z "${DOCDB_USERNAME:-}" || -z "${DOCDB_PASSWORD:-}" ]]; then
  echo "DOCDB_USERNAME and DOCDB_PASSWORD must be provided." >&2
  exit 1
fi

BASE_PATH="/xronos"
if [[ "$STAGE" == "staging" ]]; then
  BASE_PATH="/staging/xronos"
fi

STACK_NAME="xronos-${STAGE}"
BUCKET_NAME="${WEB_BUCKET_NAME:-xronos-${STAGE}-web}"

aws cloudformation deploy \
  --template-file infra/cloudformation/xronos-infra.yaml \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$AWS_REGION" \
  --parameter-overrides \
    StageName="$STAGE" \
    BasePath="$BASE_PATH" \
    DomainName="${DOMAIN_NAME:-andreas.services}" \
    CertificateArn="$CLOUDFRONT_CERT_ARN" \
    ApiImageUri="$API_IMAGE_URI" \
    VpcId="$VPC_ID" \
    PrivateSubnetIds="$PRIVATE_SUBNET_IDS" \
    DocDbSubnetIds="$DOCDB_SUBNET_IDS" \
    DocDbUsername="$DOCDB_USERNAME" \
    DocDbPassword="$DOCDB_PASSWORD" \
    WebBucketName="$BUCKET_NAME"

echo "Deployed stack $STACK_NAME with base path $BASE_PATH"
