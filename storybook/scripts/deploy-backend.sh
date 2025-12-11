#!/bin/bash
set -e

# Script to manually deploy backend to Lambda
# Usage: ./deploy-backend.sh

echo "Deploying Storybook backend to Lambda..."

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
REPOSITORY_NAME="storybook-backend-production"
FUNCTION_NAME="storybook-backend-production"
IMAGE_TAG=$(git rev-parse --short HEAD)

echo "AWS Account: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Image Tag: $IMAGE_TAG"

# Navigate to backend directory
cd ../backend

# Login to ECR
echo "Logging into ECR..."
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Build Docker image for linux/amd64 (Lambda requirement)
echo "Building Docker image..."
docker buildx build --platform linux/amd64 \
  -t $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME:$IMAGE_TAG \
  -t $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME:latest \
  .

# Push to ECR
echo "Pushing image to ECR..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME:$IMAGE_TAG
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME:latest

# Update Lambda function
echo "Updating Lambda function..."
aws lambda update-function-code \
  --function-name $FUNCTION_NAME \
  --image-uri $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPOSITORY_NAME:$IMAGE_TAG \
  --region $REGION

# Wait for update to complete
echo "Waiting for Lambda update to complete..."
aws lambda wait function-updated --function-name $FUNCTION_NAME --region $REGION

echo "Backend deployment complete!"
echo "API URL: https://api.storybook.andreas.services"
