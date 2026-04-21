# Humbugg Infrastructure

Infrastructure scripts/templates for deploying the new Flask backend (`../backend`) and React frontend (`../frontend`) onto AWS Lambda using container images. Everything is designed to run on AWS Linux, so we build Linux/amd64 images even if you are developing on macOS.

## Prerequisites

- AWS CLI v2 configured (`aws configure`)
- Docker with BuildKit/Buildx for cross-platform builds (`docker buildx`)
- An AWS account with permissions for ECR + Lambda + CloudFormation
- AWS Cognito User Pool + App Client

## Cognito Setup

1. In the AWS console create a **Cognito User Pool** (standard or password grant).
2. Create an **App Client** with the password grant enabled (no client secret or with one that you’ll set in env vars).
3. Record region, user pool ID, app client ID (and secret if used).
4. Add any custom attributes (given_name, family_name) so tokens include the data the backend expects.

## Templates

- `backend-lambda.yaml`: Lambda container, IAM role, and API Gateway HTTP API exposing the backend.
- `frontend-cloudfront.yaml`: S3 bucket, CloudFront distribution (with `/app/*` -> S3 and `/api/*` -> API Gateway), CloudFront Function for prefix handling, and Route 53 alias.

The CloudFront distribution routes `/app/*` requests to the S3 bucket (with a viewer function to ensure `index.html` loads correctly) and `/api/*` requests to the API Gateway invoke URL. Update the templates if you need additional IAM permissions, WAF, or alternate routing.
