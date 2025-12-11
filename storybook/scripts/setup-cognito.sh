#!/bin/bash
set -e

# Script to set up Cognito user pool and initial admin user
# Usage: ./setup-cognito.sh

echo "Setting up Cognito User Pool..."

# Get Cognito details from Terraform outputs
cd ../infra
USER_POOL_ID=$(terraform output -raw cognito_user_pool_id)
APP_CLIENT_ID=$(terraform output -raw cognito_user_pool_client_id)
COGNITO_DOMAIN=$(terraform output -raw cognito_domain)

echo "User Pool ID: $USER_POOL_ID"
echo "App Client ID: $APP_CLIENT_ID"
echo "Cognito Domain: $COGNITO_DOMAIN"

# Prompt for admin email
read -p "Enter admin email address: " ADMIN_EMAIL

# Prompt for temporary password
read -sp "Enter temporary password (min 8 chars, must include uppercase, lowercase, number, and symbol): " TEMP_PASSWORD
echo ""

# Create admin user
echo "Creating admin user..."
aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$ADMIN_EMAIL" \
  --user-attributes \
    Name=email,Value="$ADMIN_EMAIL" \
    Name=email_verified,Value=true \
  --temporary-password "$TEMP_PASSWORD" \
  --message-action SUPPRESS

echo "Admin user created successfully!"
echo ""
echo "Next steps:"
echo "1. Visit https://storybook.andreas.services/app"
echo "2. Click 'Login'"
echo "3. Use email: $ADMIN_EMAIL"
echo "4. Use password: $TEMP_PASSWORD"
echo "5. You will be prompted to change your password on first login"
echo ""
echo "Cognito Configuration:"
echo "- User Pool ID: $USER_POOL_ID"
echo "- App Client ID: $APP_CLIENT_ID"
echo "- Cognito Domain: $COGNITO_DOMAIN"
