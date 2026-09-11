# THE CALLBACK PATH: RECEIVE, QUEUE, CONSUME.
#
# Generation moved into the API, and a prediction is closed by Replicate calling
# back rather than by the process that started it. This module is everything
# between "Replicate has finished" and "the run row says so".
#
#     Replicate ──► HTTP API ──► receiver (zip) ──► SQS ──┬─► worker  (prod)
#                                                          └─► a laptop (dev)
#
# ## Why receiving and processing are two things
#
# The obvious build is one Lambda that verifies the callback, downloads the
# output and closes the run. It was the first build. Splitting it pays four
# times over, and the first is the one that decided it:
#
#   * **A developer can run the consumer.** Replicate cannot reach
#     `http://localhost:8000`, so with an inline close the webhook path could not
#     execute on a developer's machine at all — local development polled instead,
#     and the code that closes a run in production was code nobody had ever run.
#     A queue can be drained from a laptop. `dev-up.sh` does.
#   * **The callback is acknowledged in milliseconds.** Pulling a 200 MB clip
#     inside the webhook request holds an HTTP connection open for the length of
#     the transfer, against a sender with its own timeout.
#   * **A failed upload retries.** An exception while storing an output used to
#     lose a file somebody had already paid for. It is a redrive now, and then a
#     dead-letter queue a person can read.
#   * **The three functions size independently.** The receiver is 256 MB and
#     seconds; the worker is 2 GB with a real disk because it moves video; the
#     API Lambda is untouched at 512 MB and 60 seconds. One function sized for
#     the worst case would have charged every folder listing for the largest
#     video studio can produce.
#
# ## Why this has its own gateway rather than a route on the API's
#
# `modules/api_gateway` puts a Cognito authorizer on `ANY /api/{proxy+}` and
# carves out exactly one unauthenticated exception, `GET /api/health`, which
# returns a literal. A callback cannot hold a token, so it would have been the
# second exception — and the first one that WRITES.
#
# A separate HTTP API means there is no authorizer to carve an exception out of.
# This gateway has one route, it is unauthenticated by construction, and it
# reaches a function that can do nothing but put a message on a queue. Nothing
# about the studio API's authorization surface changes.
#
# It is also an **HTTP API rather than a REST API**: no authorizer, no gateway
# responses, no CORS contract, no stage deployment resource to remember to
# trigger. The list of things `modules/api_gateway` has to get right is exactly
# the list of things this does not have.
#
# ## What authenticates a callback
#
# The signature, and nothing else — `webhook-id` / `webhook-timestamp` /
# `webhook-signature`, HMAC-SHA256 over the raw body under Replicate's
# per-account secret, inside a bounded timestamp window. It is verified by the
# CONSUMER, not here: see `handlers/aws/hook/hook_handler.py` for why the
# receiver deliberately holds no credential and no HTTP client.
#
# What that costs is an endpoint anyone can push a message into. It is bounded
# rather than ignored: the stage below throttles, the handler caps the body, and
# a forged message costs one consumer invocation that refuses it and deletes it.

locals {
  name     = "${var.name_prefix}-callbacks"
  receiver = "${var.name_prefix}-callback-receiver"
  worker   = "${var.name_prefix}-callback-worker"
  # **An explicit flag, because a `count` may not depend on a resource
  # attribute.** This read `var.worker_image_uri != ""`, and prod passes
  # `"${module.compute.ecr_repository_url}:latest"` — an attribute of a
  # repository that, on a fresh account, does not exist at plan time. It worked
  # only because prod's ECR was already in state. `modules/compute` had the same
  # shape against the SSM parameter and it failed a real deploy with
  # `Invalid count argument`; this is the same bug, one module over, waiting for
  # a first apply into an empty account.
  create_worker = var.create_worker
}

# ---------------------------------------------------------------------------
# The queue, and the one behind it
# ---------------------------------------------------------------------------

# THE DEAD-LETTER QUEUE PRESERVES THE REPORT, NOT THE BYTES.
#
# A message here is a generation that was paid for and whose output was never
# stored — but the DLQ is NOT how that output is eventually recovered. Replicate
# serves outputs on time-limited URLs and **deletes the files themselves after
# about an hour**, so a message that reaches this queue very often names bytes
# that are already unreachable.
#
# What the DLQ actually preserves is the *report* — which prediction, for which
# run, and the provider's own account of it — and that is worth keeping. What
# preserves the bytes is being fast, so the retry budget below is set against
# that hour rather than against a general idea of resilience.
#
# `services/generate.py` closes the loop from the other side: an output that has
# genuinely expired closes the run `failed` saying exactly that, rather than
# redriving against a URL that will never work again.
resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = 1209600 # 14 days, the maximum
  tags                      = var.tags
}

resource "aws_sqs_queue" "main" {
  name = local.name

  # **At least six times the consumer's timeout is the tuning advice; this is
  # the consumer's timeout plus a minute, and the difference is deliberate.** A
  # long visibility timeout is free in prod, where the consumer is a Lambda that
  # either succeeds or reports failure immediately. It is not free in dev, where
  # the consumer is a laptop that gets killed with `Ctrl-C` — a message in flight
  # when `dev-up.sh` stops has to come back quickly enough that restarting is the
  # obvious fix rather than a thirty-minute wait nobody connects to the cause.
  visibility_timeout_seconds = var.worker_timeout + 60

  # Long enough that a weekend of failures is still there on Monday. These are
  # paid artifacts; the default four days would quietly discard them.
  message_retention_seconds = 1209600

  # THREE ATTEMPTS, AND THE NUMBER IS ARITHMETIC RATHER THAN TASTE.
  #
  # A redrive waits out the visibility timeout, so the ladder is
  # `maxReceiveCount × visibility_timeout` of wall clock before a message lands
  # in the DLQ — and it is spending a budget it does not own: Replicate deletes
  # an output file about an hour after the prediction completes.
  #
  #     3 × (300 + 60) = 18 minutes, against a ~60 minute budget.
  #
  # It was five, which is 30 minutes and leaves half the window gone before
  # anybody is told. Three rides out a transient AWS failure and leaves ~40
  # minutes in which somebody can act on the DLQ alarm below.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })

  tags = var.tags
}

# ANYTHING IN THE DLQ IS TIME-CRITICAL, SO IT IS ALARMED RATHER THAN LEFT TO BE
# NOTICED.
#
# A message here is a completed generation whose output has not been stored, and
# the file behind it dies about an hour after the prediction did. The gap between
# "this failed" and "somebody looked" is therefore the whole of whether a paid
# artifact survives — not a thing to leave to whoever next opens the console.
#
# **An alarm with no action notifies nobody, and that is the state this ships
# in.** studio has no SNS topic and no notification convention, and inventing one
# here — a topic, a subscription, an email confirmation somebody has to click —
# would be a second feature riding along with this change. So the alarm exists,
# fires, and is visible; `alarm_topic_arn` wires it to a real destination the day
# there is one. Stated plainly rather than left for a reader to discover by not
# being paged.
resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name        = "${local.name}-dlq-not-empty"
  alarm_description = "A model output was paid for and not stored. Replicate deletes output files about an hour after the prediction completes, so this is time-critical."

  namespace   = "AWS/SQS"
  metric_name = "ApproximateNumberOfMessagesVisible"
  dimensions  = { QueueName = aws_sqs_queue.dlq.name }

  # One minute, one datapoint, greater than zero. No averaging and no tolerance:
  # a single message here is the condition, and a threshold waiting for a second
  # would spend the window this alarm exists to protect.
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0

  # An empty queue reports no datapoints rather than a zero, so without this the
  # alarm sticks in ALARM forever after the first message and stops meaning
  # anything.
  treat_missing_data = "notBreaching"

  alarm_actions = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
  ok_actions    = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]

  tags = var.tags
}

# ---------------------------------------------------------------------------
# The receiver — a zip, from source, with no ECR and no build
# ---------------------------------------------------------------------------
#
# **Packaged straight out of the repo, and that is what makes the per-machine
# dev environment affordable.** `envs/dev` declares no ECR repository and no
# container Lambda on purpose — a per-machine image build would cost minutes per
# apply to prove nothing. This function imports nothing from `studio_core`, needs
# nothing but `boto3` (which the runtime provides), and is one file, so Terraform
# can package it directly. Prod runs the identical artifact.
data "archive_file" "receiver" {
  type        = "zip"
  source_file = "${path.module}/../../../backend/studio_core/handlers/aws/hook/hook_handler.py"
  output_path = "${path.module}/.terraform-build/hook_handler.zip"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "receiver" {
  name               = "${local.receiver}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

# THE WHOLE OF WHAT THE PUBLIC ENDPOINT CAN DO.
#
# Write to one queue, and write logs. It cannot read the queue back, cannot
# reach the media bucket, cannot reach the catalog, and holds no provider
# credential — which is the point of it being a separate function rather than a
# route on something that can do all four. A compromise of the one internet-
# facing unauthenticated component in studio yields the ability to enqueue a
# message that the consumer will refuse for want of a signature.
resource "aws_iam_role_policy" "receiver" {
  name = "${local.receiver}-enqueue"
  role = aws_iam_role.receiver.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.main.arn
      },
    ]
  })
}

resource "aws_lambda_function" "receiver" {
  function_name    = local.receiver
  role             = aws_iam_role.receiver.arn
  runtime          = "python3.12"
  handler          = "hook_handler.handler"
  filename         = data.archive_file.receiver.output_path
  source_code_hash = data.archive_file.receiver.output_base64sha256

  # Seconds and a small heap: it base64s a body it has already been handed and
  # calls `SendMessage`. The timeout is a backstop against a hung SQS call, not
  # a budget for work.
  timeout     = 10
  memory_size = 256

  environment {
    variables = {
      STUDIO_CALLBACK_QUEUE_URL = aws_sqs_queue.main.id
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "receiver" {
  name              = "/aws/lambda/${local.receiver}"
  retention_in_days = 14
  tags              = var.tags
}

# ---------------------------------------------------------------------------
# The public endpoint
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "main" {
  name          = local.name
  protocol_type = "HTTP"

  # No CORS block, deliberately. Nothing in a browser calls this; the only
  # caller is Replicate's server. A CORS configuration here would be a
  # permission granted to a client that does not exist.

  tags = var.tags
}

resource "aws_apigatewayv2_integration" "receiver" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.receiver.invoke_arn
  payload_format_version = "2.0"
}

# One route. `{run_id}` reaches the handler as `pathParameters.run_id`, which it
# checks looks like a run id before queueing anything — a path that is not one
# cannot be acted on downstream and is refused here rather than filling the
# queue with messages the consumer will drop.
resource "aws_apigatewayv2_route" "receiver" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /api/hooks/replicate/{run_id}"
  target    = "integrations/${aws_apigatewayv2_integration.receiver.id}"
}

resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  # **The bound on an unauthenticated public endpoint.** Callbacks arrive at the
  # rate studio submits generations, which is a handful an hour by a person at a
  # terminal — so this is three orders of magnitude above any legitimate load and
  # still low enough that a flood costs cents rather than a bill.
  default_route_settings {
    throttling_rate_limit  = var.throttle_rate
    throttling_burst_limit = var.throttle_burst
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId = "$context.requestId"
      path      = "$context.path"
      status    = "$context.status"
      latency   = "$context.responseLatency"
      # Deliberately no request body and no headers: the body is a provider
      # payload and the headers carry a signature, and neither belongs copied
      # into a log group that is read casually.
    })
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_permission" "gateway" {
  statement_id  = "AllowCallbackGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.receiver.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
# The worker — prod only. In dev the consumer is a process on the laptop.
# ---------------------------------------------------------------------------
#
# **It runs the API's own image and, deliberately, the API's own role.** The
# work it does is the work the API does — read and write the media bucket, read
# and write the catalog, read the provider token — so a second role would be a
# second copy of ~100 lines of carefully argued policy, kept in step by hand,
# with the failure mode that the copy drifts and a callback starts failing on a
# grant the API has. What it needs *extra* is the queue, which is granted below
# as one more inline policy on that same role.
resource "aws_iam_role_policy" "worker_queue" {
  count = local.create_worker ? 1 : 0
  name  = "${local.worker}-drain"
  role  = var.worker_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
      ]
      Resource = aws_sqs_queue.main.arn
    }]
  })
}

resource "aws_lambda_function" "worker" {
  count         = local.create_worker ? 1 : 0
  function_name = local.worker
  role          = var.worker_role_arn
  package_type  = "Image"
  image_uri     = var.worker_image_uri

  image_config {
    # The same image as the API, entered at a different handler. One artifact,
    # so the code that closes a run is the code that was built and tested with
    # everything else.
    command = ["studio_core.handlers.aws.worker.worker_handler.handler"]
  }

  # SIZED FOR A VIDEO, WHICH IS WHY THIS IS NOT A SECOND EVENT SOURCE ON THE API.
  #
  # It streams a model output to `/tmp` and puts it in the bucket as a single
  # PutObject — single so the ETag stays the MD5 of the bytes and the node keeps
  # a real checksum. Memory stays flat because the download never enters the
  # heap, but the disk has to hold the whole file, and the wall clock has to
  # cover a transfer of it.
  timeout     = var.worker_timeout
  memory_size = var.worker_memory
  ephemeral_storage { size = var.worker_ephemeral_storage }

  environment {
    variables = {
      STUDIO_MEDIA_BUCKET              = var.media_bucket_name
      STUDIO_CATALOG_TABLE             = var.catalog_table_name
      STUDIO_REPLICATE_TOKEN_PARAMETER = var.replicate_token_parameter
    }
  }

  tags = var.tags

  # Same reasoning as the API Lambda's: the deploy workflow owns the image and
  # the environment after creation, so this block applies once.
  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  count             = local.create_worker ? 1 : 0
  name              = "/aws/lambda/${local.worker}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_event_source_mapping" "worker" {
  count            = local.create_worker ? 1 : 0
  event_source_arn = aws_sqs_queue.main.arn
  function_name    = aws_lambda_function.worker[0].arn

  # Ten at a time, and **partial failures reported per message**. Without
  # `ReportBatchItemFailures` one bad callback redrives the whole batch, so nine
  # runs that closed correctly are closed again — harmless, because closing is
  # idempotent, and wasteful, because each retry wakes 2 GB of Lambda.
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}
