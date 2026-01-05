# CloudWatch Log Tailing

Use these commands to tail Lambda logs in production.

## Requirements

- AWS CLI configured with access to the prod account.
- Region: `us-east-1`.

## Tail the API Lambda

```bash
aws logs tail /aws/lambda/storybook-backend-production --follow --region us-east-1
```

## Tail the Image Normalization Worker

```bash
aws logs tail /aws/lambda/storybook-image-normalization-production --follow --region us-east-1
```

## Last N Minutes (example)

```bash
aws logs tail /aws/lambda/storybook-image-normalization-production --since 10m --follow --region us-east-1
```

## Only New Logs (from now)

```bash
aws logs tail /aws/lambda/storybook-image-normalization-production --since 0s --follow --region us-east-1
```
