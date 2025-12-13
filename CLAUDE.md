# Claude Instructions

This file contains project-specific instructions and context for Claude Code.

## Project Overview
- Monorepo containing multiple services: humbugg, storybook
- Working on branch: savva-storybook-setup

## AWS Authentication Best Practices

### Never Use Hardcoded Access Keys
- **Production (Lambda)**: Use IAM roles attached to Lambda functions
- **Local Development**: Use AWS CLI credentials (`aws configure`)
- **boto3**: When no credentials are passed, it automatically uses:
  1. Lambda IAM role (in AWS)
  2. AWS CLI credentials from `~/.aws/credentials` (locally)
  3. Environment variables (if set)

### How It Works
```python
# GOOD: No credentials needed
boto3.client('s3', region_name='us-east-1')

# BAD: Never hardcode access keys
boto3.client('s3',
    aws_access_key_id='AKIA...',
    aws_secret_access_key='...')
```

## Instructions
(To be updated as we work together)
