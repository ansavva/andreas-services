# THE RENDER PATH: ENQUEUE, STITCH, RECORD.
#
# Stitching needs `ffmpeg`, which the API's image does not carry. This module
# is the image that does, and the queue that feeds it.
#
#     API ──► SQS ──┬─► studio-prod-render  (prod, a second container image)
#                   └─► a laptop            (dev, `dev-up.sh`)
#
# ## Why a second image rather than ffmpeg in the API's
#
# Two reasons, and both are about what every *other* request would pay:
#
#   * **Size.** `imageio-ffmpeg` is ~80 MB. The API image is pulled on every cold
#     start of a function that answers folder listings in milliseconds, and a
#     listing should not carry a video toolchain it will never call.
#   * **Time.** A `-c copy` concat of a few clips finishes in seconds, so a
#     synchronous route looks tempting — until a job needs a re-encode, or the
#     movie is long. API Gateway's integration timeout is 30 seconds and a
#     re-encode is minutes. There is no version of "sometimes synchronous" that
#     is not a trap.
#
# So: a second ECR repository, a second image, and a queue between them. The
# images differ by one Poetry group (`Dockerfile.render`), which is what stops
# them drifting in anything else.
#
# ## Why a role of its own, when `modules/callbacks` shares the API's
#
# The callback worker does exactly what the API does — the bucket, the catalog,
# the provider token — so sharing the role avoids a hand-kept copy of a hundred
# lines of policy. The render worker breaks the premise: it never calls
# Replicate. It joins files that are already in the library. Giving it the API's
# role would give it `ssm:GetParameter` and `kms:Decrypt` on the provider token —
# the ability to spend money — for a function with no code path that spends any.
#
# So it gets its own role, built from `modules/compute`'s two exported policy
# *documents*. One definition of what access to the library means; two roles
# scoped to two jobs; and no copy to keep in step.
#
# ## Why the queue's DLQ is alarmed differently from the callback queue's
#
# A callback in the dead-letter queue is time-critical: Replicate deletes the
# output file about an hour after the prediction completes, so the gap between
# "this failed" and "somebody looked" decides whether a paid artifact survives.
# Nothing here is perishable — every input to a render is already in the bucket
# and will still be there next week — so the alarm below is about a job somebody
# is waiting on rather than about bytes about to vanish. It fires on the same
# terms because a person waiting is reason enough; the retry ladder is longer.

locals {
  name = "${var.name_prefix}-render"

  # **An explicit flag, because a `count` may not depend on a resource
  # attribute.** `modules/compute` failed a prod deploy on exactly this
  # (`Invalid count argument`, from an SSM parameter's ARN) and
  # `modules/callbacks` carried the latent version of it against an ECR URL.
  # Both variables below are literals passed down from `envs/prod`.
  create_worker = var.create_worker
  create_ecr    = var.create_ecr

  # THE IMAGE URI IS COMPOSED FROM LITERALS, NOT READ OFF THE REPOSITORY.
  #
  # The obvious spelling — `"${aws_ecr_repository.render[0].repository_url}:latest"`
  # — cannot be used here because this module declares the repository *and* the
  # function, so `envs/prod` cannot pass `module.render.ecr_repository_url` back
  # into `module.render`: that is a cycle. Indexing `[0]` inside the module works
  # only while `create_ecr` is true and fails the plan when it is not.
  #
  # A registry URL is `<account>.dkr.ecr.<region>.amazonaws.com/<name>`, and every
  # part of it is known before anything is created. So it is built here, and the
  # ordering that the reference would have implied is stated explicitly with
  # `depends_on` on the function. Same shape as `modules/compute`'s
  # `provider_token_arn`, and the same lesson: a plan-time value beats a
  # resource attribute wherever one will do.
  image_uri = var.worker_image_uri != "" ? var.worker_image_uri : format(
    "%s.dkr.ecr.%s.amazonaws.com/%s:latest",
    data.aws_caller_identity.current.account_id,
    data.aws_region.current.region,
    local.name,
  )
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

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

  # The consumer's timeout plus a minute. Long enough that a message cannot come
  # back while the worker still holds it, short enough that a `Ctrl-C` on a
  # laptop consumer is not a twenty-minute wait before the job can be retried —
  # the same trade `modules/callbacks` makes, at a longer timeout.
  visibility_timeout_seconds = var.worker_timeout + 60

  # A fortnight, so a weekend of failures is still there on Monday.
  message_retention_seconds = 1209600

  # FIVE ATTEMPTS, WHERE THE CALLBACK QUEUE TAKES THREE, AND THE DIFFERENCE IS
  # WHAT IS BEING SPENT.
  #
  # The callback queue's ladder is bounded by an hour it does not own: Replicate
  # deletes an output file about an hour after the prediction completes, so every
  # redrive is spending somebody else's window and three is what leaves time to
  # act on the alarm.
  #
  # Nothing a render reads is perishable. Every input is already in the media
  # bucket. So the ladder is set against transience instead — five attempts at
  # `visibility_timeout` apart rides out a genuinely unlucky afternoon, and a job
  # that fails permanently never gets here at all: `services/render.run` closes
  # the row `failed` and the message is deleted.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })

  tags = var.tags
}

# A MESSAGE HERE IS SOMEBODY WAITING ON A ROW THAT WILL NEVER MOVE.
#
# `services/render.run` sets a job `running` and leaves it there when the failure
# is transient, so the queue can bring it back. A message that exhausts its
# redrives therefore leaves a `RENDER#` row stuck at `running` for ever, and the
# caller polling it — `studio scenes assemble`, waiting — gets nothing but a
# timeout with no cause in it.
#
# **The alarm still notifies nobody, and that is the state this ships in**, for
# the reason `modules/callbacks` gives: studio has no SNS topic and no
# notification convention, and inventing one here would be a second feature
# riding along with this change. `alarm_topic_arn` wires it up the day there is
# one. Said plainly rather than left for a reader to discover by not being paged.
resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name        = "${local.name}-dlq-not-empty"
  alarm_description = "A render job ran out of retries. Its RENDER# row is stuck at `running` and whoever submitted it is still polling."

  namespace   = "AWS/SQS"
  metric_name = "ApproximateNumberOfMessagesVisible"
  dimensions  = { QueueName = aws_sqs_queue.dlq.name }

  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0

  # An empty queue reports no datapoints rather than a zero, so without this the
  # alarm sticks in ALARM for ever after the first message and stops meaning
  # anything.
  treat_missing_data = "notBreaching"

  alarm_actions = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
  ok_actions    = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]

  tags = var.tags
}

# ---------------------------------------------------------------------------
# The API's grant to enqueue
# ---------------------------------------------------------------------------
#
# One statement on the API's own role, attached from here because the queue is
# declared here — the same arrangement `modules/callbacks` uses for the worker's
# drain grant, and for the same reason: neither module should own a resource the
# other depends on.
#
# `SendMessage` and nothing else. The API cannot read this queue back, cannot
# delete from it and cannot change its policy: a compromise of the request-facing
# function yields the ability to ask for a render, which it can already do.
#
# **`count` keys off an explicit flag, not off `var.api_role_name != ""`.** That
# spelling would put a resource attribute — `module.compute.api_role_name`, which
# is `aws_iam_role.api.name` — inside a `count`, and `modules/compute` failed a
# prod deploy on exactly that shape with `Invalid count argument`. It happens to
# be knowable here, because the role's name is composed from literals, and
# "happens to be knowable" is precisely the property that stopped holding the
# last two times. A literal cannot stop being one.
resource "aws_iam_role_policy" "api_enqueue" {
  count = var.create_api_grant ? 1 : 0
  name  = "${local.name}-enqueue"
  role  = var.api_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = aws_sqs_queue.main.arn
    }]
  })
}

# ---------------------------------------------------------------------------
# The image
# ---------------------------------------------------------------------------
#
# `force_delete` IS SET ON THE APPLY THAT CREATES THIS, WHICH IS THE ONLY APPLY
# ON WHICH SETTING IT WORKS.
#
# The root `CLAUDE.md` records what this cost in August 2026: Terraform applies
# the destroy half of a replacement against *prior state*, so a `force_delete`
# added during a rename is read off the old object and never seen. A repository
# holding images then refuses `DeleteRepository` and the deploy fails, with the
# recovery being out-of-band state surgery. It holds nothing but CI build output
# the next push rebuilds from git, so there is nothing for the guard to protect —
# and now nothing to retrofit.
resource "aws_ecr_repository" "render" {
  count                = local.create_ecr ? 1 : 0
  name                 = local.name
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "render" {
  count      = local.create_ecr ? 1 : 0
  repository = aws_ecr_repository.render[0].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 10 }
      action       = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  count              = local.create_worker ? 1 : 0
  name               = "${local.name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "logs" {
  count = local.create_worker ? 1 : 0
  name  = "${local.name}-logs"
  role  = aws_iam_role.worker[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# The API's own documents, attached to a different role. See the note at the top
# of this file and the outputs in `modules/compute`: one definition of what
# access to the library means, and no provider token here.
resource "aws_iam_role_policy" "media_access" {
  count  = local.create_worker ? 1 : 0
  name   = "${local.name}-media-access"
  role   = aws_iam_role.worker[0].id
  policy = var.media_access_policy
}

resource "aws_iam_role_policy" "catalog_access" {
  count  = local.create_worker ? 1 : 0
  name   = "${local.name}-catalog-access"
  role   = aws_iam_role.worker[0].id
  policy = var.catalog_access_policy
}

resource "aws_iam_role_policy" "drain" {
  count = local.create_worker ? 1 : 0
  name  = "${local.name}-drain"
  role  = aws_iam_role.worker[0].id
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
  function_name = local.name
  role          = aws_iam_role.worker[0].arn
  package_type  = "Image"
  image_uri     = local.image_uri

  # The ordering the composed URI above cannot imply. Without it Terraform is
  # free to create the function before the repository, and Lambda refuses an
  # image it cannot pull.
  depends_on = [aws_ecr_repository.render]

  # No `image_config.command`: this image's own `CMD` is the render handler,
  # unlike the callback worker, which is the API's image entered somewhere else.
  # Overriding it here would be a second place the entrypoint is stated.

  timeout     = var.worker_timeout
  memory_size = var.worker_memory
  ephemeral_storage { size = var.worker_ephemeral_storage }

  environment {
    variables = {
      STUDIO_MEDIA_BUCKET  = var.media_bucket_name
      STUDIO_CATALOG_TABLE = var.catalog_table_name
      # Deliberately no `STUDIO_REPLICATE_TOKEN_PARAMETER` and no Cognito ids.
      # This function answers no request and calls no provider; a variable it
      # never reads is a variable somebody later assumes it does.
    }
  }

  tags = var.tags

  # Same reasoning as every other Lambda here: the deploy workflow owns the image
  # and the environment after creation, so this block applies once.
  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "worker" {
  count             = local.create_worker ? 1 : 0
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_lambda_event_source_mapping" "worker" {
  count            = local.create_worker ? 1 : 0
  event_source_arn = aws_sqs_queue.main.arn
  function_name    = aws_lambda_function.worker[0].arn

  # ONE AT A TIME, WHERE THE CALLBACK WORKER TAKES TEN.
  #
  # A callback is a download and a PutObject — seconds, and ten of them fit
  # comfortably inside one timeout. A render is a stitch, which is minutes, so a
  # batch of ten would serialise nine unrelated callers behind the first under a
  # single visibility timeout and a single 10-minute budget. Lambda scales out on
  # queue depth instead, which is the behaviour actually wanted: two people
  # cutting scenes at once get two containers.
  #
  # `ReportBatchItemFailures` is kept even at a batch of one. A batch size is a
  # tuning value somebody will raise; losing partial-failure reporting to it
  # would be a correctness change hiding inside one.
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}
