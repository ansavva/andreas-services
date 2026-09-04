locals {
  api_name  = "${var.project}-${var.environment}-api"
  api_image = var.create_ecr ? "${aws_ecr_repository.api[0].repository_url}:latest" : var.api_image_uri

  # Composed from the parameter NAME rather than taken from the resource, so it
  # is known at plan time — see the note above `data.aws_iam_policy_document
  # .provider_token`, which a prod deploy failed on. A parameter name always
  # begins with `/` and the ARN form does not repeat it.
  provider_token_arn = var.replicate_token_parameter == "" ? "" : format(
    "arn:aws:ssm:%s:%s:parameter%s",
    data.aws_region.current.region,
    data.aws_caller_identity.current.account_id,
    var.replicate_token_parameter,
  )
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# ECR
# ---------------------------------------------------------------------------
# A repository name is immutable, so renaming one is a destroy and recreate, and
# DeleteRepository refuses a repository that still holds images. This holds
# nothing but CI build output the next push rebuilds from git, so there is
# nothing for the guard to protect. Note this only helps the rename AFTER the one
# that introduces it: Terraform applies the destroy half of a replacement against
# prior state, so the flag has to already be recorded there. See "Renaming is a
# destroy-and-recreate" in CLAUDE.md.
resource "aws_ecr_repository" "api" {
  count                = var.create_ecr ? 1 : 0
  name                 = local.api_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "api" {
  count      = var.create_ecr ? 1 : 0
  repository = aws_ecr_repository.api[0].name
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
# IAM
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

resource "aws_iam_role" "api" {
  name               = "${local.api_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "logs" {
  name = "${local.api_name}-logs"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# THIS ROLE CAN NOW WRITE, AND THAT IS A DELIBERATE REVERSAL.
#
# For most of studio's life this policy was `ListBucket` + `GetObject` and the
# comment here said so emphatically: the media bucket belonged to a separate
# generation pipeline, studio was a viewer of it, and no bug or compromised
# token could destroy that data because the role simply could not. That was the
# right default and it is worth stating plainly why it changed.
#
# (The ownership half of that argument has since gone too — the pipeline lives
# in `studio/.claude/skills/` and the bucket is declared in `modules/media`. But
# note what did NOT change: that pipeline runs locally under a human's own AWS
# login. This role is still the only thing reachable from the internet, so it is
# still the one worth scoping.)
#
# It changed because tidying the library is a thing you do while looking at it.
# A run that produced nothing worth keeping is recognised in the browser, and
# routing "delete these four frames" back through the pipeline meant it never
# happened. So the role gained `PutObject` and `DeleteObject`, scoped to the same
# root the read grants use.
#
# READ THIS BEFORE RELYING ON THAT SCOPE. The grants cover the whole bucket —
# the browsable root is the bucket itself — and this is a write-capable role:
# what it can read, it can also overwrite and delete. The only reason that is
# acceptable is that the bucket's entire contents are exactly what studio is
# for.
#
# What holds the line:
#
#   * Every key that reaches `PutObject`, `DeleteObject` or `CopyObject` comes
#     off a node record's `blob_key`, never off a request: `services/manage`
#     resolves a name path to a node and passes that node's key, and nothing
#     outside `services/catalog` composes one, so "delete everything" is not
#     expressible through the API. `/api/asset` signs by node id and reads only.
#     See `clients/aws/s3.py`.
#   * There is no multipart grant. The one path that creates an object out of
#     bytes the caller supplied never goes through this role at all:
#     `POST /api/nodes/<id>/upload-url` signs a PUT, so the bytes go to S3
#     directly. What bounds it is the signature rather than this policy: one
#     key (`blobs/<node_id>`, never one the caller names), one exact content
#     length, one content type, and a TTL shorter than a read URL's. A signed
#     URL cannot be redirected at another object without invalidating itself.
#     The `PutObject` this role grants has exactly two callers: `put_text`,
#     which overwrites a text file that already exists, and the destination
#     half of a copy. A folder is one row and no objects, and a rename or a
#     move is a catalog transaction that touches no bytes at all.
#   * `s3:DeleteObjectVersion` is deliberately absent, and the bucket IS
#     versioned (`modules/media`). So a delete through this role writes a
#     tombstone it cannot then reach past: every erasure it can perform is
#     recoverable. That is the single strongest thing holding the line here, and
#     it is why the versioning flag in `modules/media` is not hygiene.
#
# `GetObject` is what signs presigned URLs and what HeadObject checks against;
# both read the same permission. `CopyObject` needs `GetObject` on the source and
# `PutObject` on the destination, so it needs no grant of its own: source and
# destination are both inside the same root everything else here is scoped to.
# `services.manage.copy_objects` is the only caller left. Renames and moves were
# copies too, once — they are catalog transactions now and duplicate nothing, so
# the shape of this grant is carried by one operation rather than four.
data "aws_iam_policy_document" "media_access" {
  statement {
    sid       = "ListBrowsableRoot"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}"]
  }

  statement {
    sid       = "ReadMediaObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/*"]
  }

  statement {
    sid       = "ManageMediaObjects"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/*"]
  }
}

# Inline: a role policy carries no data, so replacing it costs nothing.
resource "aws_iam_role_policy" "media_access" {
  name   = "${local.api_name}-media-access"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.media_access.json
}

# THE CATALOG GRANT, AND WHY IT IS NOT SHAPED LIKE THE MEDIA ONE.
#
# The media grant above is scoped by prefix and leans on versioning to make its
# deletes recoverable. Neither idea carries over. A row has no prefix to scope
# by — `blob_key` is deliberately opaque and membership is a table lookup, so
# IAM cannot express "the caller's libraries" at all — and a row has no version
# history: an overwrite during a move or a transfer, which rewrites `path` or
# `lib` across a whole subtree, leaves nothing behind. The catalog's only
# recovery is the table's PITR, restored out of band by a human into a new
# table. So the boundary is held entirely in the API's own code, which is also
# why the API is the only writer to this table: one consistency boundary, and
# one place where authorization is decided.
#
# What follows is that this policy's job is narrow. Grant the item operations
# the model actually performs, on this table only, and nothing that changes what
# the table IS.
#
# THE INDEX ARNs ARE NOT OPTIONAL. DynamoDB authorizes a Query against the index
# it names, not against the base table, so with `<arn>` alone every `by-path` and
# `by-recent` query fails AccessDenied while a plain folder listing —
# `pk = NODE#<parent>` on the base table — keeps working. That asymmetry is
# exactly the sort that ships: the common path is fine, and the reel and the
# subtree walk are what break.
# `/index/*` rather than three literals because every index is
# `projection_type = ALL` over the same rows, so naming them one by one would
# restrict nothing and would make adding a fourth index a two-module change.
#
# Absences, each of them a decision:
#
#   * No `Scan`. Every access pattern in the model is a Query; a Scan crosses
#     library boundaries by construction, which is the one boundary the API
#     exists to enforce.
#   * No `BatchWriteItem`. A node is two items, so every write is a
#     `TransactWriteItems` — and the one bulk operation, a move rewriting `path`
#     on every descendant, is precisely the one that must not half-apply: a
#     partial batch leaves `path` disagreeing with the authoritative
#     `parent_id`. Chunked transactions are the right shape for it. Add the
#     grant only alongside an argument for why a partial write is acceptable.
#   * No `CreateTable`, `UpdateTable`, `DeleteTable`, and nothing touching
#     backups or PITR. This Lambda writes rows; the table's existence belongs to
#     Terraform and its recovery to a human. Nothing reachable from the internet
#     should be able to delete the library outright, and this policy is the only
#     place that could have handed it that.
data "aws_iam_policy_document" "catalog_access" {
  statement {
    sid    = "ReadWriteCatalogItems"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      # **`BatchGetItem` is not covered by `GetItem`.** Omitting it took the
      # deployed app down: every folder listing is `catalog.children` (a Query
      # for the by-parent items) plus `catalog.records` (one BatchGetItem for
      # their `META` rows), so the listing failed with `Could not read the
      # catalog` while sign-in — which only queries — kept working.
      #
      # The unit suite cannot catch this. moto does not enforce IAM, so every
      # test passes against a policy that grants nothing at all. A grant is only
      # ever proved by a real call.
      "dynamodb:BatchGetItem",
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:TransactWriteItems",
    ]
    resources = [
      var.catalog_table_arn,
      "${var.catalog_table_arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "catalog_access" {
  name   = "${local.api_name}-catalog-access"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.catalog_access.json
}

# THE PROVIDER CREDENTIAL. **STUDIO HELD NONE UNTIL GENERATION MOVED HERE.**
#
# For all of studio's life this role could reach its own bucket and its own
# table and nothing else, so "what does a compromise of this function get you"
# had an answer that stopped at the library. It now also gets you the ability to
# spend money on Replicate. That is a real widening and it is worth stating
# rather than discovering, so: the grant below is the whole of it, and it is
# scoped to ONE parameter name.
#
# **The value is read at call time, not injected as an environment variable.**
# Every other studio setting arrives through `update-lambda`'s `jq` block, and
# doing that here would have been less code — but a Lambda's environment is
# readable by anyone holding `lambda:GetFunctionConfiguration` and is printed in
# the console, so the token would be visible to a strictly larger set of
# principals than this policy names. `clients/aws/ssm.py` caches it per
# container, so this is one read per cold start rather than one per submission.
#
# **`kms:Decrypt` is not optional and is the half that gets forgotten.**
# `GetParameter` with `WithDecryption=true` on a SecureString authorizes against
# KMS as well, so granting only the first fails at runtime with an
# `AccessDeniedException` naming *KMS* — which sends the reader to the wrong
# policy entirely. The key is the account's default SSM key; the condition ties
# the grant to parameter-store use of it rather than to KMS at large.
#
# The parameter is declared in `envs/prod`, not here, because the worker Lambda
# in `modules/callbacks` reads the same one and neither module should own a
# resource the other depends on.
#
# **`count` KEYS OFF THE PARAMETER NAME, NOT ITS ARN, AND THAT IS THE WHOLE OF A
# FAILED PROD DEPLOY.**
#
# It was `var.replicate_token_parameter_arn == "" ? 0 : 1`, with the ARN taken
# from `aws_ssm_parameter.replicate_api_token.arn` in `envs/prod` — a *resource
# attribute*, which does not exist until the parameter has been created. So on
# the apply that creates it, Terraform cannot resolve the count at plan time and
# refuses the whole plan:
#
#     Error: Invalid count argument
#     The "count" value depends on resource attributes that cannot be determined
#     until apply.
#
# **`terraform validate` cannot catch this**, which is why five clean validates
# and a green PR preceded it: validate checks syntax and types and does not
# resolve references between resources. Only a real plan does.
#
# The name is a plain string composed in `envs/prod`'s locals from literals, so
# it is known before anything is created. The ARN is built from it below rather
# than passed in.
#
# What this costs is the dependency edge — the policy does not *reference* the
# parameter, so Terraform will not order them. That is acceptable here and would
# not be everywhere: an IAM grant naming a parameter that does not exist yet is
# inert rather than wrong, and the parameter is created in the same apply.
data "aws_iam_policy_document" "provider_token" {
  count = var.replicate_token_parameter == "" ? 0 : 1

  statement {
    sid       = "ReadTheProviderToken"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [local.provider_token_arn]
  }

  statement {
    sid       = "DecryptTheProviderToken"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "provider_token" {
  count  = var.replicate_token_parameter == "" ? 0 : 1
  name   = "${local.api_name}-provider-token"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.provider_token[0].json
}

data "aws_region" "current" {}

# ---------------------------------------------------------------------------
# Lambda — the deploy workflow owns image_uri + environment after creation
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "api" {
  function_name = local.api_name
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = local.api_image
  # 15s was ample while every request was one listing. A subtree operation is a
  # chunked `TransactWriteItems` — a move rewriting `path` on every descendant, a
  # delete removing two items per node — and `STUDIO_MAX_FOLDER_OBJECTS` bounds
  # that at 2000. The Lambda
  # refuses anything larger rather than relying on this number, so the timeout is
  # the backstop and the config value is the contract.
  #
  # **This did NOT grow when generation moved in, and that is the point of
  # `modules/callbacks`.** Closing a run downloads a model output and puts it in
  # the bucket, which wants minutes and gigabytes; doing it here would have
  # charged every folder listing for the largest video studio can produce. It is
  # a separate function on a queue, sized for that job. What this Lambda gained
  # is `POST /api/runs/<id>/submit`, which creates a prediction and returns —
  # one HTTP round trip to Replicate, comfortably inside 60 seconds.
  timeout     = 60
  memory_size = 512

  # THIS BLOCK APPLIES ONCE, AT CREATION, AND NEVER AGAIN — see the
  # `ignore_changes` below. The values that actually run are set on every deploy
  # by the `jq` block in `update-lambda` in `.github/workflows/studio-prod.yaml`,
  # which reads them back out of SSM. Adding a variable here without adding it
  # there produces the worst kind of wrong: Terraform's plan is clean, the
  # console shows the value on a freshly created function, and the deployed
  # Lambda has never seen it.
  #
  # The two Cognito ids are here because the Lambda validates the JWT itself
  # rather than trusting the gateway. It cannot do otherwise: `WsgiToAsgi`
  # builds the WSGI environ from a fixed key list, so Mangum's `aws.event`
  # scope — where `requestContext.authorizer.claims` lives — never reaches
  # Flask, and an `AWS_PROXY` integration ignores `requestParameters`, so the
  # claim cannot be mapped into a header either. The pool id builds the issuer
  # and the JWKS URL; the client id is checked against `aud`, without which a
  # token minted for any other client of the same pool would be accepted.
  environment {
    variables = {
      STUDIO_MEDIA_BUCKET         = var.media_bucket_name
      STUDIO_ALLOWED_ORIGIN       = var.allowed_origin
      STUDIO_CATALOG_TABLE        = var.catalog_table_name
      STUDIO_COGNITO_USER_POOL_ID = var.cognito_user_pool_id
      STUDIO_COGNITO_CLIENT_ID    = var.cognito_client_id

      # The NAME of the SecureString, never its value. See the policy above.
      STUDIO_REPLICATE_TOKEN_PARAMETER = var.replicate_token_parameter

      # **`STUDIO_WEBHOOK_BASE_URL` is deliberately absent from this block.**
      #
      # It is `modules/callbacks`'s output, and this module is that module's
      # input (it lends the worker its execution role) — so reading it here
      # would be a dependency cycle between the two. It is set by
      # `update-lambda`, which is what actually sets every variable on a running
      # function anyway.
      #
      # What that means on a FIRST apply into an empty account is that the API
      # answers submissions with `callback: "poll"` until the workflow's
      # `update-lambda` step runs. That is a safe degradation rather than a
      # broken deploy: the prediction is created without a webhook and the run
      # is closed by `POST /api/runs/<id>/reconcile`, which is the same code
      # reached by a different trigger.
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [image_uri, environment]
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.api_name}"
  retention_in_days = 14
  tags              = var.tags
}
