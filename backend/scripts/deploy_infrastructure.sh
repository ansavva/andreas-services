#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: $0 [options]

Provision or update the Gmail ingestion infrastructure using the AWS CLI.
The script packages the Lambda, creates/updates IAM roles and policies,
ensures the DynamoDB table exists with the required GSIs, and configures
the weekly EventBridge schedule.

Options:
  --region <name>              AWS region (default: us-east-1)
  --profile <name>             AWS CLI profile (cloud mode only)
  --local                      Target LocalStack via the awslocal CLI
  --openai-secret-arn <arn>    ARN of the OpenAI Secrets Manager secret (required)
  --gmail-secret-arn <arn>     ARN of the Gmail Secrets Manager secret (required)
  --table-name <name>          DynamoDB table name (default: Events)
  --lambda-name <name>         Lambda function name (default: events-gmail-ingest)
  --timezone <tz>              EventBridge schedule time zone (default: America/New_York)
  --openai-model <model>       Override OPENAI_MODEL environment variable
  --help                       Show this help text

Examples:
  # Deploy to LocalStack (requires awslocal in PATH)
  backend/scripts/deploy_infrastructure.sh \
    --local \
    --openai-secret-arn arn:aws:secretsmanager:us-east-1:000000000000:secret:local/openai \
    --gmail-secret-arn arn:aws:secretsmanager:us-east-1:000000000000:secret:local/gmail

  # Deploy to AWS us-east-1 using the "dev" profile
  backend/scripts/deploy_infrastructure.sh \
    --profile dev \
    --region us-east-1 \
    --openai-secret-arn arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/openai \
    --gmail-secret-arn arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/gmail
USAGE
}

log() {
  local level="$1"; shift
  printf '[%s] [%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$level" "$*"
}

REGION="us-east-1"
PROFILE=""
MODE="cloud"
OPENAI_SECRET_ARN=""
GMAIL_SECRET_ARN=""
TABLE_NAME="Events"
LAMBDA_NAME="events-gmail-ingest"
TIMEZONE="America/New_York"
OPENAI_MODEL=""
ROLE_NAME="${LAMBDA_NAME}-role"
POLICY_NAME="${LAMBDA_NAME}-inline"
EVENT_RULE_NAME="${LAMBDA_NAME}-weekly"
PERMISSION_SID="${LAMBDA_NAME}-eventbridge"
ARTIFACT_ROOT="build"
PACKAGE_DIR="${ARTIFACT_ROOT}/lambda"
ZIP_PATH="${ARTIFACT_ROOT}/lambda_package.zip"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)
      REGION="$2"; shift 2 ;;
    --profile)
      PROFILE="$2"; shift 2 ;;
    --local)
      MODE="local"; shift ;;
    --openai-secret-arn)
      OPENAI_SECRET_ARN="$2"; shift 2 ;;
    --gmail-secret-arn)
      GMAIL_SECRET_ARN="$2"; shift 2 ;;
    --table-name)
      TABLE_NAME="$2"; shift 2 ;;
    --lambda-name)
      LAMBDA_NAME="$2"; ROLE_NAME="${LAMBDA_NAME}-role"; POLICY_NAME="${LAMBDA_NAME}-inline"; EVENT_RULE_NAME="${LAMBDA_NAME}-weekly"; PERMISSION_SID="${LAMBDA_NAME}-eventbridge"; shift 2 ;;
    --timezone)
      TIMEZONE="$2"; shift 2 ;;
    --openai-model)
      OPENAI_MODEL="$2"; shift 2 ;;
    --help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ -z "$OPENAI_SECRET_ARN" || -z "$GMAIL_SECRET_ARN" ]]; then
  echo "Error: --openai-secret-arn and --gmail-secret-arn are required." >&2
  usage
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "Error: 'zip' command is required." >&2
  exit 1
fi

if [[ "$MODE" == "local" ]]; then
  if ! command -v awslocal >/dev/null 2>&1; then
    echo "Error: awslocal CLI is required for --local deployments." >&2
    exit 1
  fi
  AWS_CLI="awslocal"
  AWS_ARGS=(--region "$REGION")
else
  AWS_CLI="aws"
  AWS_ARGS=(--region "$REGION")
  if [[ -n "$PROFILE" ]]; then
    AWS_ARGS+=(--profile "$PROFILE")
  fi
fi

aws_cmd() {
  "$AWS_CLI" "${AWS_ARGS[@]}" "$@"
}

package_lambda() {
  log INFO "Packaging Lambda dependencies"
  rm -rf "$PACKAGE_DIR" "$ZIP_PATH"
  mkdir -p "$PACKAGE_DIR"
  python3 -m pip install -r backend/lambda/requirements.txt -t "$PACKAGE_DIR"
  cp backend/lambda/*.py "$PACKAGE_DIR"/
  (cd "$PACKAGE_DIR" && zip -r "../$(basename "$ZIP_PATH")" . >/dev/null)
  log INFO "Created deployment package at $ZIP_PATH"
}

ensure_dynamodb_table() {
  if aws_cmd dynamodb describe-table --table-name "$TABLE_NAME" >/dev/null 2>&1; then
    log INFO "DynamoDB table $TABLE_NAME already exists"
    return
  fi

  log INFO "Creating DynamoDB table $TABLE_NAME"
  local table_spec
  table_spec=$(mktemp)
  cat >"$table_spec" <<EOF
{
  "TableName": "$TABLE_NAME",
  "AttributeDefinitions": [
    {"AttributeName": "id", "AttributeType": "S"},
    {"AttributeName": "category", "AttributeType": "S"},
    {"AttributeName": "source_name", "AttributeType": "S"},
    {"AttributeName": "start_time", "AttributeType": "S"}
  ],
  "KeySchema": [
    {"AttributeName": "id", "KeyType": "HASH"}
  ],
  "ProvisionedThroughput": {
    "ReadCapacityUnits": 5,
    "WriteCapacityUnits": 5
  },
  "GlobalSecondaryIndexes": [
    {
      "IndexName": "category-index",
      "KeySchema": [{"AttributeName": "category", "KeyType": "HASH"}],
      "Projection": {"ProjectionType": "ALL"},
      "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
    },
    {
      "IndexName": "source_name-index",
      "KeySchema": [{"AttributeName": "source_name", "KeyType": "HASH"}],
      "Projection": {"ProjectionType": "ALL"},
      "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
    },
    {
      "IndexName": "start_time-index",
      "KeySchema": [{"AttributeName": "start_time", "KeyType": "HASH"}],
      "Projection": {"ProjectionType": "ALL"},
      "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
    }
  ],
  "StreamSpecification": {
    "StreamEnabled": true,
    "StreamViewType": "NEW_AND_OLD_IMAGES"
  }
}
EOF
  aws_cmd dynamodb create-table --cli-input-json file://"$table_spec"
  rm -f "$table_spec"
  aws_cmd dynamodb wait table-exists --table-name "$TABLE_NAME"
  log INFO "Created DynamoDB table $TABLE_NAME"
}

ensure_iam_role() {
  if aws_cmd iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    log INFO "IAM role $ROLE_NAME already exists"
  else
    log INFO "Creating IAM role $ROLE_NAME"
    local trust
    trust=$(mktemp)
    cat >"$trust" <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
    aws_cmd iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document file://"$trust" >/dev/null
    rm -f "$trust"
    log INFO "Created IAM role $ROLE_NAME"
    sleep 5
  fi

  log INFO "Attaching AWSLambdaBasicExecutionRole"
  aws_cmd iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole >/dev/null 2>&1 || true

  local policy_doc
  policy_doc=$(mktemp)
  cat >"$policy_doc" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:GetItem",
        "dynamodb:Query"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/$TABLE_NAME",
        "arn:aws:dynamodb:*:*:table/$TABLE_NAME/index/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": [
        "$OPENAI_SECRET_ARN",
        "$GMAIL_SECRET_ARN"
      ]
    }
  ]
}
EOF
  aws_cmd iam put-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" \
    --policy-document file://"$policy_doc"
  rm -f "$policy_doc"
  ROLE_ARN=$(aws_cmd iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)
  log INFO "IAM role ARN: $ROLE_ARN"
}

ensure_lambda() {
  package_lambda
  ensure_dynamodb_table
  ensure_iam_role

  local env_vars
  env_vars="OPENAI_SECRET_ARN=$OPENAI_SECRET_ARN,GMAIL_SECRET_ARN=$GMAIL_SECRET_ARN,TABLE_NAME=$TABLE_NAME,TIMEZONE=$TIMEZONE"
  if [[ -n "$OPENAI_MODEL" ]]; then
    env_vars="OPENAI_MODEL=$OPENAI_MODEL,$env_vars"
  fi

  if aws_cmd lambda get-function --function-name "$LAMBDA_NAME" >/dev/null 2>&1; then
    log INFO "Updating Lambda function $LAMBDA_NAME"
    aws_cmd lambda update-function-code --function-name "$LAMBDA_NAME" --zip-file fileb://"$ZIP_PATH" >/dev/null
    aws_cmd lambda update-function-configuration \
      --function-name "$LAMBDA_NAME" \
      --runtime python3.11 \
      --handler lambda_function.handler \
      --role "$ROLE_ARN" \
      --timeout 300 \
      --memory-size 512 \
      --environment "Variables={$env_vars}" >/dev/null
  else
    log INFO "Creating Lambda function $LAMBDA_NAME"
    aws_cmd lambda create-function \
      --function-name "$LAMBDA_NAME" \
      --runtime python3.11 \
      --handler lambda_function.handler \
      --role "$ROLE_ARN" \
      --timeout 300 \
      --memory-size 512 \
      --zip-file fileb://"$ZIP_PATH" \
      --environment "Variables={$env_vars}" >/dev/null
  fi
  FUNCTION_ARN=$(aws_cmd lambda get-function --function-name "$LAMBDA_NAME" --query 'Configuration.FunctionArn' --output text)
  log INFO "Lambda ARN: $FUNCTION_ARN"
}

ensure_schedule() {
  ensure_lambda
  local rule_arn
  log INFO "Configuring EventBridge rule $EVENT_RULE_NAME"

  set +e
  rule_arn=$(aws_cmd events put-rule \
    --name "$EVENT_RULE_NAME" \
    --schedule-expression 'cron(0 22 ? * MON *)' \
    --schedule-expression-timezone "$TIMEZONE" \
    --state ENABLED \
    --query 'RuleArn' \
    --output text 2>/tmp/rule_error)
  local status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    log INFO "Falling back to schedule without timezone (see /tmp/rule_error)"
    rule_arn=$(aws_cmd events put-rule \
      --name "$EVENT_RULE_NAME" \
      --schedule-expression 'cron(0 22 ? * MON *)' \
      --state ENABLED \
      --query 'RuleArn' \
      --output text)
  fi
  rm -f /tmp/rule_error 2>/dev/null || true

  aws_cmd lambda remove-permission --function-name "$LAMBDA_NAME" --statement-id "$PERMISSION_SID" >/dev/null 2>&1 || true
  aws_cmd lambda add-permission \
    --function-name "$LAMBDA_NAME" \
    --statement-id "$PERMISSION_SID" \
    --action 'lambda:InvokeFunction' \
    --principal events.amazonaws.com \
    --source-arn "$rule_arn" >/dev/null

  log INFO "Linking Lambda to EventBridge rule"
  aws_cmd events put-targets \
    --rule "$EVENT_RULE_NAME" \
    --targets Id="1",Arn="$FUNCTION_ARN"

  log INFO "Infrastructure deployment complete"
}

ensure_schedule
