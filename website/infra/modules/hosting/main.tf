locals {
  prefix = "${var.project}-${var.environment}"
}

data "aws_acm_certificate" "wildcard" {
  provider    = aws.us_east_1
  domain      = "*.andreas.services"
  statuses    = ["ISSUED"]
  most_recent = true
}

# Managed policies: no caching for SSR HTML, forward everything except Host to
# the Lambda origin (Function URLs require their own Host); long-cache assets.
data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

# Forward all viewer headers/cookies/query-strings to the SSR Lambda origin
# EXCEPT Host and Authorization. Excluding Authorization is required for OAC:
# if the origin request policy forwards Authorization, CloudFront skips adding
# its SigV4 signature and the Function URL returns 403 Forbidden. The SSR app
# doesn't need the viewer Authorization header (admin auth uses a cookie).
resource "aws_cloudfront_origin_request_policy" "ssr" {
  name    = "${local.prefix}-ssr-origin-request"
  comment = "All viewer data except Host + Authorization (OAC-signed Lambda origin)"

  headers_config {
    header_behavior = "allExcept"
    headers {
      items = ["host", "authorization"]
    }
  }
  cookies_config {
    cookie_behavior = "all"
  }
  query_strings_config {
    query_string_behavior = "all"
  }
}

# ---------------------------------------------------------------------------
# S3 bucket for hashed client assets (served at /assets/*)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "assets" {
  bucket = var.assets_bucket_name

  # Every object in here is a hashed client asset that deploy-frontend-assets
  # re-syncs on each deploy, so a rename has nothing to preserve and should not
  # stop on BucketNotEmpty. As with the ECR repositories, this only takes effect
  # for a rename after the one that records it — the destroy half of a
  # replacement reads prior state, not this configuration.
  force_destroy = true

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket                  = aws_s3_bucket.assets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# Origin Access Control (S3 assets only; the SSR origin is a public HTTP API)
# ---------------------------------------------------------------------------
resource "aws_cloudfront_origin_access_control" "s3" {
  name                              = "${local.prefix}-assets-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ---------------------------------------------------------------------------
# Apex -> www 301 redirect (viewer-request)
# ---------------------------------------------------------------------------
resource "aws_cloudfront_function" "apex_redirect" {
  name    = "${local.prefix}-apex-to-www"
  runtime = "cloudfront-js-2.0"
  comment = "301 redirect andreas.services -> www.andreas.services"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var host = request.headers.host.value;
      if (host === "${var.apex_domain}") {
        return {
          statusCode: 301,
          statusDescription: "Moved Permanently",
          headers: { "location": { "value": "https://${var.www_domain}" + request.uri } }
        };
      }
      return request;
    }
  EOT

  # A function name is immutable, so a rename replaces it — and CloudFront
  # refuses to delete a function while a distribution still references it. With
  # the default destroy-then-create order Terraform deletes the old function
  # before it has updated the distribution off it, which is exactly how the
  # #227 apply failed: "Cannot delete function website-apex-to-www, it is in use
  # by 1 distributions". Creating first reverses that: new function, then the
  # distribution update that detaches the old one, then the delete.
  #
  # Unlike force_destroy this needs no prior state — it changes Terraform's
  # ordering, not an argument the provider reads from the old object — so it
  # takes effect on the very apply that renames the function.
  lifecycle {
    create_before_destroy = true
  }
}

# ---------------------------------------------------------------------------
# CloudFront distribution
# ---------------------------------------------------------------------------
resource "aws_cloudfront_distribution" "main" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "andreas.services website (SSR + assets)"
  price_class     = "PriceClass_100"
  aliases         = [var.www_domain, var.apex_domain]

  # SSR HTTP API (default origin)
  origin {
    domain_name = var.www_api_domain
    origin_id   = "ssr-lambda"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # S3 static assets
  origin {
    domain_name              = aws_s3_bucket.assets.bucket_regional_domain_name
    origin_id                = "s3-assets"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  default_cache_behavior {
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    target_origin_id         = "ssr-lambda"
    viewer_protocol_policy   = "redirect-to-https"
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.ssr.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.apex_redirect.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-assets"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = data.aws_acm_certificate.wildcard.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = var.tags
}

# ---------------------------------------------------------------------------
# Grant: CloudFront -> S3 (read). The SSR origin is a public API Gateway HTTP
# API, so it needs no CloudFront-specific grant.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "assets_bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.assets.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.main.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "assets" {
  bucket = aws_s3_bucket.assets.id
  policy = data.aws_iam_policy_document.assets_bucket.json
}

# ---------------------------------------------------------------------------
# DNS: www + apex -> CloudFront
# ---------------------------------------------------------------------------
resource "aws_route53_record" "www" {
  zone_id = var.route53_zone_id
  name    = var.www_domain
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "apex" {
  zone_id = var.route53_zone_id
  name    = var.apex_domain
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.main.domain_name
    zone_id                = aws_cloudfront_distribution.main.hosted_zone_id
    evaluate_target_health = false
  }
}
