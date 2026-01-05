# SQS Debugging (Production)

Use these commands to inspect the production image normalization queues.

## Requirements

- AWS CLI configured with access to the prod account.
- Region: `us-east-1`.

## Get the Queue URL

```bash
aws sqs get-queue-url \
  --queue-name storybook-image-normalization-production \
  --region us-east-1
```

## Inspect Queue Attributes

```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/704202188703/storybook-image-normalization-production \
  --attribute-names All \
  --region us-east-1
```

## Peek at a Message (No Delete)

```bash
aws sqs receive-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/704202188703/storybook-image-normalization-production \
  --max-number-of-messages 1 \
  --wait-time-seconds 5 \
  --region us-east-1
```

## Inspect the DLQ

```bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/704202188703/storybook-image-normalization-production-dlq \
  --attribute-names All \
  --region us-east-1
```
