# THE STRIPE WEBHOOK PATH: RECEIVE, QUEUE, CONSUME — THE SAME IN EVERY ENVIRONMENT.
#
#     Stripe ──► HTTP API ──► receiver (zip) ──► SQS ──┬─► consumer Lambda ──► api.humbugg.com  (prod)
#                                                       └─► a laptop        ──► localhost:5001   (dev)
#
# This is studio's `modules/callbacks`, which solved the same problem for
# Replicate. Stripe cannot reach `localhost:5001`, so for as long as a dev
# stack had no public endpoint the only way a purchase could complete locally
# was the Stripe CLI's relay (`stripe listen`) — a live process that has to be
# running at the moment Stripe emits the event, and that drops the event when
# it is not. A seeder found that in September 2026: Stripe took the payment,
# nothing was listening, and the exchange stayed Free with a `pending` row.
#
# Prod's webhook used to be Stripe posting straight at the API Lambda's route.
# It works, and it is not what dev runs, and the decision was that the two do
# not get to differ: the path a developer watches close a purchase is the path
# that closes one in production. So prod takes the same gateway, receiver and
# queue, and a consumer Lambda where dev has a laptop. The API's webhook route
# is unchanged — it is what the consumer forwards to in both environments.
#
# ## Why receiving and processing are two things
#
# Because in dev the processor is the developer's working tree. The receiver is
# one dependency-free file, packaged as a zip straight from the repo — no ECR,
# no image build — and all it does is put the request on a queue. `dev-up.sh`
# runs a consumer beside the backend that drains the queue into
# `localhost:5001`. So a real, Stripe-signed event reaches the code being
# edited, an event that arrives while the laptop is shut waits in the queue (up
# to 14 days) instead of being lost, and an apply is seconds. Prod inherits the
# same durability for free: an event behind a failed deploy or a 409 ordering
# race waits in the queue rather than in Stripe's retry schedule.
#
# ## The consumer is the backend
#
# As studio's worker is its backend: the consumer runs the API's own container
# image, entered through `ConsumerHost` (`HUMBUGG_CONSUMER=stripe-webhooks`)
# like the email-status and reminder consumers, and calls the same
# `ProcessQueuedWebhookAsync` the HTTP route's `ProcessWebhookAsync` is a thin
# wrapper around. No HTTP hop, no second implementation. In dev the same image
# runs as a second Compose service (`backend/docker-compose.yml`) that
# long-polls this machine's queue; `RunAsync` picks the host by whether the
# Lambda runtime is present.
#
# ## What authenticates a webhook
#
# The `Stripe-Signature` header — HMAC-SHA256 over `<timestamp>.<raw body>`
# under the endpoint's own `whsec_` — and nothing else. It is verified by the
# CONSUMER, not here: the receiver holds no secret, so a compromise of the one
# internet-facing unauthenticated component yields the ability to enqueue a
# message the consumer refuses. The header is carried through verbatim and the
# body as base64, because an HMAC notices whitespace. The consumer verifies with
# the queue's retention as the timestamp window rather than Stripe's five
# minutes — a queued event may be a day old — and nothing else differs.
#
# The Stripe side — a webhook endpoint pointing at this module's URL — is not
# Terraform's. In dev `dev-aws-setup.sh` registers it after the apply and
# `dev-aws-destroy.sh` deletes it; in prod it is registered by hand
# (`docs/stripe-setup.md`), as it always was. The Stripe provider would be a
# second provider and a second credential for one resource, and the secret it
# returns has to land in dev.env or a GitHub secret regardless.

locals {
  name     = "${var.name_prefix}-stripe-webhooks"
  receiver = "${var.name_prefix}-stripe-webhook-receiver"
  consumer = "${var.name_prefix}-stripe-webhook-consumer"
}

# ---------------------------------------------------------------------------
# The queue, and the one behind it
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = 1209600 # 14 days, the maximum
  tags                      = var.tags
}

resource "aws_sqs_queue" "main" {
  name = local.name

  # Short, because the consumer is a laptop process that gets killed with
  # Ctrl-C: a message in flight when dev-up.sh stops has to come back quickly
  # enough that restarting is the obvious fix. Forwarding one webhook to
  # localhost takes milliseconds; a minute is generous.
  visibility_timeout_seconds = 60

  # A fortnight, the maximum. The whole point of the queue over the CLI relay
  # is that an event emitted while nothing was listening is still there when
  # something is.
  message_retention_seconds = 1209600

  # Ten attempts, ten minutes at the visibility timeout above. The dev consumer
  # does not receive while the backend is down — it checks /health first — so
  # a receive that fails is a genuine surprise; in prod an attempt fails on a
  # 5xx or the 409 ordering race, both of which clear in seconds. Ten is enough
  # to say the message itself is the problem.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 10
  })

  tags = var.tags
}

# A message in the DLQ is a paid Stripe event the backend never accepted — in
# prod, a customer who paid for Plus and does not have it. Alarmed when there is
# a topic to alarm to (prod passes `modules/alerting`'s); dev passes none, and
# an alarm that pages nobody about a laptop would be noise.
resource "aws_cloudwatch_metric_alarm" "dlq" {
  count             = var.alarm_topic_arn == "" ? 0 : 1
  alarm_name        = "${local.name}-dlq-not-empty"
  alarm_description = "A Stripe webhook was refused ten times and is in the dead-letter queue. If it is a checkout.session.completed, somebody paid for Plus and does not have it."

  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }

  alarm_actions = [var.alarm_topic_arn]
  ok_actions    = [var.alarm_topic_arn]
  tags          = var.tags
}

# ---------------------------------------------------------------------------
# The receiver — a zip, from source, with no ECR and no build
# ---------------------------------------------------------------------------
#
# Node rather than the backend's C#: a .NET Lambda is a build, and the whole
# reason this is affordable per machine is that there is none. The file sits
# beside the consumer in `scripts/webhook-relay/` so the two halves of the
# message format are one directory apart. It imports only the SQS client the
# Node runtime ships.
data "archive_file" "receiver" {
  type        = "zip"
  source_file = "${path.module}/../../../scripts/webhook-relay/receiver.mjs"
  output_path = "${path.module}/.terraform-build/receiver.zip"
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

# THE WHOLE OF WHAT THE PUBLIC ENDPOINT CAN DO: write to one queue, write logs.
# It cannot read the queue back, cannot reach a table, and holds no Stripe
# credential.
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
  runtime          = "nodejs22.x"
  handler          = "receiver.handler"
  filename         = data.archive_file.receiver.output_path
  source_code_hash = data.archive_file.receiver.output_base64sha256

  # Seconds and a small heap: it base64s a body it has already been handed and
  # calls SendMessage. The timeout is a backstop against a hung SQS call.
  timeout     = 10
  memory_size = 256

  environment {
    variables = {
      HUMBUGG_WEBHOOK_QUEUE_URL = aws_sqs_queue.main.id
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
#
# An HTTP API rather than a REST API, with one unauthenticated route: there is
# no authorizer to carve an exception out of, no CORS block (nothing in a
# browser calls this), no stage deployment to remember to trigger. An
# `execute-api` hostname rather than anything under humbugg.com: it is handed
# to Stripe once by a script, never typed, so a certificate and a DNS record
# would buy nothing and cost a minute per apply.
resource "aws_apigatewayv2_api" "main" {
  name          = local.name
  protocol_type = "HTTP"
  tags          = var.tags
}

resource "aws_apigatewayv2_integration" "receiver" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.receiver.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "receiver" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /stripe/webhook"
  target    = "integrations/${aws_apigatewayv2_integration.receiver.id}"
}

resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  # The bound on an unauthenticated public endpoint. Stripe emits a handful of
  # events per purchase and a developer makes a handful of purchases an hour,
  # so this is orders of magnitude above legitimate load and still low enough
  # that a flood costs cents.
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
      # No body and no headers: the body names a customer and the header is a
      # signature, and neither belongs in a log group read casually.
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
  statement_id  = "AllowWebhookGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.receiver.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
# The consumer — prod only. In dev the consumer is a Compose service.
# ---------------------------------------------------------------------------
#
# **It runs the API's own image and, deliberately, the API's own role.** The work
# it does is work the API does — verify a Stripe signature, write the billing
# and groups tables — so a second role would be a second copy of the API's
# policy, kept in step by hand, with the failure mode that the copy drifts and a
# webhook starts failing on a grant the API has. What it needs *extra* is the
# queue, granted below as one more inline policy on that same role.
#
# `lifecycle { ignore_changes = [image_uri, environment] }` as on every Lambda:
# the deploy workflow owns both — `update-function-code` pins `:sha`,
# `update-function-configuration` sets the consumer's environment. Terraform
# sets the initial values on first creation only.
resource "aws_iam_role_policy" "consumer_queue" {
  count = var.create_consumer ? 1 : 0
  name  = "${local.consumer}-drain"
  role  = var.consumer_role_name
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

resource "aws_lambda_function" "consumer" {
  count         = var.create_consumer ? 1 : 0
  function_name = local.consumer
  role          = var.consumer_role_arn
  package_type  = "Image"
  image_uri     = var.consumer_image_uri

  # One signature check and two DynamoDB writes; the API Lambda's own sizing is
  # more than enough. Under the queue's 60 s visibility timeout with room to
  # spare, so a retry never overlaps a still-running attempt.
  timeout     = 30
  memory_size = 512

  environment {
    variables = {
      HUMBUGG_CONSUMER = "stripe-webhooks"
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [
      image_uri,
      environment,
    ]
  }
}

resource "aws_cloudwatch_log_group" "consumer" {
  count             = var.create_consumer ? 1 : 0
  name              = "/aws/lambda/${local.consumer}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_event_source_mapping" "consumer" {
  count                   = var.create_consumer ? 1 : 0
  event_source_arn        = aws_sqs_queue.main.arn
  function_name           = aws_lambda_function.consumer[0].arn
  function_response_types = ["ReportBatchItemFailures"]
  # Stripe emits a handful of events per purchase. Small batches keep the 409
  # ordering race — a charge before its session — a one-message retry rather
  # than a whole batch's.
  batch_size                         = 5
  maximum_batching_window_in_seconds = 1

  depends_on = [aws_iam_role_policy.consumer_queue]
}
