#!/bin/bash
set -e

# Script to manually deploy frontend to S3 and CloudFront
# Usage: ./deploy-frontend.sh

echo "Deploying Storybook frontend..."

# Get Terraform outputs
cd ../infra
S3_BUCKET=$(terraform output -raw s3_frontend_bucket)
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)

echo "S3 Bucket: $S3_BUCKET"
echo "CloudFront Distribution: $DISTRIBUTION_ID"

# Navigate to frontend directory
cd ../frontend/storybook-ui

# Install dependencies
echo "Installing dependencies..."
npm ci

# Build frontend
echo "Building frontend..."
npm run build

# Deploy to S3
echo "Uploading to S3..."
aws s3 sync dist/ s3://$S3_BUCKET --delete

# Invalidate CloudFront cache
echo "Invalidating CloudFront cache..."
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*" \
  --query 'Invalidation.Id' \
  --output text)

echo "CloudFront invalidation created: $INVALIDATION_ID"
echo "Frontend deployment complete!"
echo "URL: https://storybook.andreas.services/app"
echo ""
echo "Note: CloudFront invalidation may take a few minutes to propagate"
