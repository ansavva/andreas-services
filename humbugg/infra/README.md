# Humbugg Infrastructure

Infrastructure scripts/templates for deploying the new Flask backend (`../backend`) and React frontend (`../frontend`) onto AWS Lambda using container images. Everything is designed to run on AWS Linux, so we build Linux/amd64 images even if you are developing on macOS.

## Prerequisites

- AWS CLI v2 configured (`aws configure`)
- Docker with BuildKit/Buildx for cross-platform builds (`docker buildx`)
- An AWS account with permissions for ECR + Lambda + CloudFormation
- MongoDB Atlas or self-hosted Mongo connection string
- AWS Cognito User Pool + App Client

## Cognito Setup

1. In the AWS console create a **Cognito User Pool** (standard or password grant).
2. Create an **App Client** with the password grant enabled (no client secret or with one that you’ll set in env vars).
3. Record region, user pool ID, app client ID (and secret if used).
4. Add any custom attributes (given_name, family_name) so tokens include the data the backend expects.

## Mongo / DocumentDB

For local development the backend defaults to `mongodb://localhost:27017`. In AWS you should provision an AWS DocumentDB cluster. Use the DocumentDB connection string (with TLS parameters) as `MONGO_URI` when deploying:

```
mongodb://username:password@docdb-cluster.cluster-xxxxx.us-east-1.docdb.amazonaws.com:27017/?ssl=true&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false
```

Set the following environment variables (or export them before running the deploy script):

- `MONGO_URI` (DocumentDB connection string in production, standard Mongo URI locally)
- `MONGO_DB_NAME` (default `HumbuggDb`)
- `CORS_ORIGIN`
- `COGNITO_REGION`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`

## Build & Deploy

Use the included deploy script to build a Linux image, push it to ECR, and deploy the CloudFormation stack.

```bash
cd humbugg/infra
export AWS_REGION=us-east-1
export MONGO_URI="mongodb+srv://..."
export CORS_ORIGIN="https://app.example.com"
export COGNITO_REGION="us-east-1"
export COGNITO_USER_POOL_ID="us-east-1_ABC"
export COGNITO_CLIENT_ID="abcd1234"
export FRONTEND_DOMAIN="humbugg.andreas.services"
export HOSTED_ZONE_ID="Z123ABC456DEF"
export ACM_CERT_ARN="arn:aws:acm:us-east-1:123456789012:certificate/abc123"

# Backend
./deploy.sh backend v1

# Frontend
BACKEND_STACK_NAME=humbugg-backend ./deploy.sh frontend v1
```

The script does the following:
1. For the backend, builds the Linux-compatible Docker image, pushes to ECR, and deploys the Lambda + API Gateway stack.
2. For the frontend, builds the React assets, deploys the CloudFront/S3 stack, uploads the files under `/app/`, and invalidates the CloudFront cache.

## Templates

- `backend-lambda.yaml`: Lambda container, IAM role, and API Gateway HTTP API exposing the backend.
- `frontend-cloudfront.yaml`: S3 bucket, CloudFront distribution (with `/app/*` -> S3 and `/api/*` -> API Gateway), CloudFront Function for prefix handling, and Route 53 alias.

The CloudFront distribution routes `/app/*` requests to the S3 bucket (with a viewer function to ensure `index.html` loads correctly) and `/api/*` requests to the API Gateway invoke URL. Update the templates if you need additional IAM permissions, WAF, or alternate routing.
