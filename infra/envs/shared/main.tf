# envs/shared/main.tf
# Shared platform infrastructure: Route53 zone (data source) + ACM wildcard certificate.
#
# The VPC, NAT Gateway, subnets, and DocumentDB cluster have been removed.
# All services now use DynamoDB (IAM-controlled, no VPC required).

locals {
  shared_tags = {
    Project     = "platform"
    Environment = "shared"
    ManagedBy   = "terraform"
    Scope       = "shared"
  }
}

# Route53 hosted zone — managed outside Terraform (registered domain)
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# Wildcard ACM certificate for *.andreas.services (must be in us-east-1 for CloudFront)
resource "aws_acm_certificate" "wildcard" {
  provider          = aws.us_east_1
  domain_name       = "*.${var.domain_name}"
  validation_method = "DNS"

  subject_alternative_names = [var.domain_name]

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.shared_tags, {
    Name = "wildcard-${var.domain_name}"
  })
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.wildcard.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

# ─── GitHub Actions OIDC ──────────────────────────────────────────────────────

resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS auto-validates GitHub's TLS cert; thumbprint is ignored but required by the API
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = local.shared_tags
}

data "aws_iam_policy_document" "github_actions_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "github-actions-andreas-services"
  assume_role_policy = data.aws_iam_policy_document.github_actions_trust.json
  tags               = local.shared_tags
}

data "aws_iam_policy_document" "github_actions_permissions" {
  # CloudFormation — scout ephemeral PR stacks + production stack
  statement {
    effect    = "Allow"
    actions   = ["cloudformation:*"]
    resources = ["*"]
  }

  # Lambda — code deploys, env var updates, invocations
  statement {
    effect    = "Allow"
    actions   = ["lambda:*"]
    resources = ["*"]
  }

  # ECR — storybook Docker image pushes
  statement {
    effect    = "Allow"
    actions   = ["ecr:*"]
    resources = ["*"]
  }

  # DynamoDB — created by CloudFormation/Terraform; read during stack ops
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:*"]
    resources = ["*"]
  }

  # S3 — Lambda zip uploads, frontend syncs, Terraform state
  statement {
    effect    = "Allow"
    actions   = ["s3:*"]
    resources = ["*"]
  }

  # API Gateway — scout stack
  statement {
    effect    = "Allow"
    actions   = ["apigateway:*"]
    resources = ["*"]
  }

  # CloudFront — invalidations + stack management
  statement {
    effect    = "Allow"
    actions   = ["cloudfront:*"]
    resources = ["*"]
  }

  # Route53 — DNS records created by stacks
  statement {
    effect    = "Allow"
    actions   = ["route53:*"]
    resources = ["*"]
  }

  # ACM — shared wildcard cert (Terraform)
  statement {
    effect    = "Allow"
    actions   = ["acm:*"]
    resources = ["*"]
  }

  # EventBridge — scout email processor schedule
  statement {
    effect    = "Allow"
    actions   = ["events:*"]
    resources = ["*"]
  }

  # CloudWatch Logs — stack log groups
  statement {
    effect    = "Allow"
    actions   = ["logs:*"]
    resources = ["*"]
  }

  # CloudWatch — Mailer alarms and service health metrics
  statement {
    effect    = "Allow"
    actions   = ["cloudwatch:*"]
    resources = ["*"]
  }

  # SNS — SES feedback topics and subscriptions
  statement {
    effect    = "Allow"
    actions   = ["sns:*"]
    resources = ["*"]
  }

  # GuardDuty — Malware Protection for Mailer attachment storage
  statement {
    effect    = "Allow"
    actions   = ["guardduty:*"]
    resources = ["*"]
  }

  # Cognito — storybook auth (Terraform)
  statement {
    effect    = "Allow"
    actions   = ["cognito-idp:*"]
    resources = ["*"]
  }

  # SQS — storybook image queue (Terraform)
  statement {
    effect    = "Allow"
    actions   = ["sqs:*"]
    resources = ["*"]
  }

  # SES — service email identities, domain authentication, and simulator smoke tests
  statement {
    effect    = "Allow"
    actions   = ["ses:*"]
    resources = ["*"]
  }

  # IAM — creating Lambda execution roles via CloudFormation/Terraform
  statement {
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:PassRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:CreateOpenIDConnectProvider",
      "iam:GetOpenIDConnectProvider",
      "iam:DeleteOpenIDConnectProvider",
      "iam:TagOpenIDConnectProvider",
      "iam:CreatePolicy",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListPolicyVersions",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:DeletePolicy",
      "iam:TagPolicy",
    ]
    resources = ["*"]
  }

  # SSM — infra workflows write outputs; code workflows read them
  statement {
    effect = "Allow"
    actions = [
      "ssm:AddTagsToResource",
      "ssm:DeleteParameter",
      "ssm:GetParameter",
      "ssm:ListTagsForResource",
      "ssm:PutParameter",
      "ssm:RemoveTagsFromResource",
    ]
    resources = [
      "arn:aws:ssm:*:*:parameter/scout/*",
      "arn:aws:ssm:*:*:parameter/storybook/*",
      "arn:aws:ssm:*:*:parameter/humbugg/*",
      "arn:aws:ssm:*:*:parameter/mailer/*",
      "arn:aws:ssm:*:*:parameter/website/*",
    ]
  }
}

resource "aws_iam_policy" "github_actions" {
  name   = "github-actions-andreas-services"
  policy = data.aws_iam_policy_document.github_actions_permissions.json
  tags   = local.shared_tags
}

resource "aws_iam_role_policy_attachment" "github_actions" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_actions.arn
}

# ─── ACM ──────────────────────────────────────────────────────────────────────

resource "aws_acm_certificate_validation" "wildcard" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.wildcard.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# SES reputation is account-wide even though individual applications use
# separate configuration sets. Hard bounces and complaints therefore share one
# suppression policy across every Mailer consumer.
resource "aws_sesv2_account_suppression_attributes" "shared" {
  suppressed_reasons = ["BOUNCE", "COMPLAINT"]
}
