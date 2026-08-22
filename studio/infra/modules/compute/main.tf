locals {
  api_name  = "${var.project}-${var.environment}-api"
  api_image = var.create_ecr ? "${aws_ecr_repository.api[0].repository_url}:latest" : var.api_image_uri
}

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
# READ THIS BEFORE RELYING ON THAT SCOPE. `media_root_prefix` is now empty —
# the pipeline dropped the `media/` wrapper it used to write under, so the
# browsable root is the bucket itself and `${var.media_root_prefix}*` expands to
# `*`. The prefix therefore confines nothing today, and it is a write-capable
# role: what it can read, it can also overwrite and delete. That is a real
# widening of the blast radius over the read-only era, and the only reason it is
# acceptable is that the bucket's entire contents are exactly what studio is for.
# Set the prefix to a real value and both halves narrow again, together.
#
# What still holds the line:
#
#   * `services/keys.py` validates every key and prefix before it reaches boto3,
#     and `assert_inside_root` refuses an operation aimed at the root itself, so
#     "delete everything" is not expressible through the API. With the prefix
#     empty this is the FIRST line of defence, not the second.
#   * There is no multipart grant. **There IS now a path that creates an object
#     out of bytes the caller supplied**, and this paragraph used to say there
#     was not — #294 was the separate decision this note asked for.
#     `POST /api/nodes/<id>/upload-url` signs a PUT, so the bytes go to S3
#     directly and never through this role at all. What bounds it is the
#     signature rather than this policy: one key (`blobs/<node_id>`, never one
#     the caller names), one exact content length, one content type, and a TTL
#     shorter than a read URL's. A signed URL cannot be redirected at another
#     object without invalidating itself.
#     The rest still holds: `PutObject` here writes zero-byte folder markers,
#     overwrites text files that already exist, and lands the destination half
#     of a `CopyObject` — a rename, a move, or a favourite.
#   * `s3:DeleteObjectVersion` is deliberately absent, and the bucket IS
#     versioned (`modules/media`). So a delete through this role writes a
#     tombstone it cannot then reach past: every erasure it can perform is
#     recoverable. That is the single strongest thing holding the line here, and
#     it is why the versioning flag in `modules/media` is not hygiene.
#
# `GetObject` is what signs presigned URLs and what HeadObject checks against;
# both read the same permission. `CopyObject` — which is what a rename, a move
# and a favourite all are — needs `GetObject` on the source and `PutObject` on
# the destination. Favourites need no grant of their own for that reason: the
# source and the destination are both inside the same root everything else here
# is scoped to.
data "aws_iam_policy_document" "media_access" {
  statement {
    sid       = "ListBrowsableRoot"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      # A listing of the root arrives with `s3:prefix` absent or empty, so the
      # bare root is listed alongside the wildcard. `distinct` because an empty
      # root collapses two of the three into the same value.
      values = distinct(["${var.media_root_prefix}*", var.media_root_prefix, ""])
    }
  }

  statement {
    sid       = "ReadMediaObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/${var.media_root_prefix}*"]
  }

  statement {
    sid       = "ManageMediaObjects"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.media_bucket_name}/${var.media_root_prefix}*"]
  }
}

# Renamed from `media_read`, which is no longer what it grants. An inline role
# policy carries no data, so replacing it costs nothing.
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
# it names, not against the base table, so with `<arn>` alone every `by-sk`,
# `by-path` and `by-recent` query fails AccessDenied while a plain folder
# listing — `pk = NODE#<parent>` on the base table — keeps working. That
# asymmetry is exactly the sort that ships: the common path is fine, and the
# reel, the subtree walk and "who is in this library" are what break.
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

# ---------------------------------------------------------------------------
# Lambda — the deploy workflow owns image_uri + environment after creation
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "api" {
  function_name = local.api_name
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = local.api_image
  # 15s was ample while every request was one listing. A folder rename is a
  # CopyObject per key — server-side, so the bytes never move through here, but
  # still one round trip each — and `STUDIO_MAX_FOLDER_OBJECTS` bounds that at
  # 2000. The Lambda refuses anything larger rather than relying on this number,
  # so the timeout is the backstop and the config value is the contract.
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
      STUDIO_MEDIA_ROOT_PREFIX    = var.media_root_prefix
      STUDIO_ALLOWED_ORIGIN       = var.allowed_origin
      STUDIO_CATALOG_TABLE        = var.catalog_table_name
      STUDIO_COGNITO_USER_POOL_ID = var.cognito_user_pool_id
      STUDIO_COGNITO_CLIENT_ID    = var.cognito_client_id
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
