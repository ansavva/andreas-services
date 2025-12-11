#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: deploy.sh <backend|frontend> <image-tag> [stack-name]" >&2
  exit 1
fi

TARGET="$1"
IMAGE_TAG="$2"
STACK_NAME="${3:-humbugg-${TARGET}}"

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT="${AWS_ACCOUNT:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REPO="${ECR_REPO:-${TARGET}-lambda}"

if [[ "$TARGET" == "backend" ]]; then
  TEMPLATE="backend-lambda.yaml"
  docker buildx build --platform linux/amd64 -t "${ECR_REPO}:${IMAGE_TAG}" "../backend"
  aws ecr describe-repositories --repository-names "${ECR_REPO}" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "${ECR_REPO}" >/dev/null
  IMAGE_URI="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"
  aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  docker tag "${ECR_REPO}:${IMAGE_TAG}" "${IMAGE_URI}"
  docker push "${IMAGE_URI}"
  BACKEND_STAGE="${BACKEND_STAGE:-prod}"
  aws cloudformation deploy \
    --template-file "${TEMPLATE}" \
    --stack-name "${STACK_NAME}" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
      FunctionName="${STACK_NAME}" \
      ImageUri="${IMAGE_URI}" \
      StageName="${BACKEND_STAGE}" \
      EnvMongoUri="${MONGO_URI:?set MONGO_URI}" \
      EnvMongoDbName="${MONGO_DB_NAME:-HumbuggDb}" \
      EnvCorsOrigin="${CORS_ORIGIN:?set CORS_ORIGIN}" \
      EnvCognitoRegion="${COGNITO_REGION:?set COGNITO_REGION}" \
      EnvCognitoPoolId="${COGNITO_USER_POOL_ID:?set COGNITO_USER_POOL_ID}" \
      EnvCognitoClientId="${COGNITO_CLIENT_ID:?set COGNITO_CLIENT_ID}"
  echo "Deployed backend stack ${STACK_NAME} using image ${IMAGE_URI}"
else
  BACKEND_STACK="${BACKEND_STACK_NAME:-humbugg-backend}"
  DOMAIN="${FRONTEND_DOMAIN:?set FRONTEND_DOMAIN}"
  HOSTED_ZONE_ID="${HOSTED_ZONE_ID:?set HOSTED_ZONE_ID}"
  CERT_ARN="${ACM_CERT_ARN:?set ACM_CERT_ARN}"

  API_URL=$(aws cloudformation describe-stacks --stack-name "${BACKEND_STACK}" --query "Stacks[0].Outputs[?OutputKey=='ApiInvokeUrl'].OutputValue" --output text)
  if [[ -z "${API_URL}" ]]; then
    echo "Unable to determine API invoke URL from backend stack ${BACKEND_STACK}" >&2
    exit 1
  fi
  API_DOMAIN=$(echo "${API_URL}" | sed -E 's#https?://([^/]+)/.*#\1#')
  API_STAGE=$(echo "${API_URL}" | awk -F/ '{print $NF}')

  pushd ../frontend >/dev/null
  npm install
  npm run build
  popd >/dev/null

  aws cloudformation deploy \
    --template-file frontend-cloudfront.yaml \
    --stack-name "${STACK_NAME}" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
      StackName="${STACK_NAME}" \
      DomainName="${DOMAIN}" \
      HostedZoneId="${HOSTED_ZONE_ID}" \
      CertificateArn="${CERT_ARN}" \
      ApiDomainName="${API_DOMAIN}" \
      ApiStageName="${API_STAGE}"

  BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='SiteBucketName'].OutputValue" --output text)
  DIST_ID=$(aws cloudformation describe-stacks --stack-name "${STACK_NAME}" --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" --output text)

  aws s3 sync ../frontend/dist "s3://${BUCKET_NAME}/app/" --delete
  aws cloudfront create-invalidation --distribution-id "${DIST_ID}" --paths "/app/*"
  echo "Frontend uploaded to s3://${BUCKET_NAME}/app/ and CloudFront invalidated."
fi

echo "Deployment for ${TARGET} complete."
