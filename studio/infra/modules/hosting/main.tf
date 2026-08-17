terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

locals {
  prefix = "${var.project}-${var.environment}"
}

data "aws_acm_certificate" "wildcard" {
  provider    = aws.us_east_1
  domain      = "*.andreas.services"
  statuses    = ["ISSUED"]
  most_recent = true
}

# ---------------------------------------------------------------------------
# S3 — the built SPA. Regenerable from git on every deploy, so `force_destroy`
# is set at creation: a bucket rename is a destroy-and-recreate and
# DeleteBucket refuses a bucket holding objects. Adding the flag later does not
# help the rename that adds it (Terraform applies the destroy half against
# prior state) — see "Renaming is a destroy-and-recreate" in CLAUDE.md.
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "app" {
  bucket        = var.app_bucket_name
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_public_access_block" "app" {
  bucket                  = aws_s3_bucket.app.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app" {
  bucket = aws_s3_bucket.app.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ---------------------------------------------------------------------------
# CloudFront
# ---------------------------------------------------------------------------
resource "aws_cloudfront_origin_access_control" "app" {
  name                              = "${local.prefix}-app-oac"
  description                       = "OAC for the studio SPA bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"

  # A distribution that still references this cannot be detached and reattached
  # in one apply, so ordering — not an argument — is the fix. Unlike
  # force_destroy this works on the very apply that introduces it.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudfront_function" "spa_fallback" {
  name    = "${local.prefix}-spa-fallback"
  runtime = "cloudfront-js-1.0"
  comment = "SPA fallback routing for studio"
  publish = true
  # Routes by WHERE the build puts things, not by whether the path looks like a
  # file — which is the distinction studio's share links turn on.
  #
  # A studio URL is the object's S3 key: `/media/fred/runs/…/output/clip.mp4`.
  # The obvious rule ("has an extension, so serve it") sends that straight to the
  # origin, which does not have it; the distribution's 403/404 fallbacks then
  # rescue it into index.html, so the link *works* — after a round trip to S3 and
  # an error page, on every share link anyone opens. Worse, it is accidental:
  # remove those custom_error_response blocks and every shared clip 404s.
  #
  # Vite emits exactly two things — hashed files under /assets/ and index.html —
  # so passing those through and rewriting everything else is both complete and
  # unambiguous. `public/` is empty; anything added there needs a line here.
  #
  # ES5.1 runtime: `indexOf(x) === 0`, not `startsWith`.
  code = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      // The build's own output, served as-is.
      if (uri.indexOf('/assets/') === 0 || uri === '/index.html') {
        return request;
      }

      // Everything else is a client-side route — including one that ends in
      // `.mp4`, because that is what an object's share link looks like.
      request.uri = '/index.html';
      return request;
    }
  EOT

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "studio frontend distribution"
  price_class         = "PriceClass_100"
  aliases             = [var.domain_name]
  default_root_object = "index.html"

  origin {
    domain_name              = aws_s3_bucket.app.bucket_regional_domain_name
    origin_id                = "S3-app"
    origin_access_control_id = aws_cloudfront_origin_access_control.app.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-app"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # The deploy sets Cache-Control per object (hashed assets immutable, HTML
    # no-store) and CloudFront honours it, so the distribution itself imposes
    # no TTL of its own.
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 31536000

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_fallback.arn
    }
  }

  # With OAC and a private bucket a missing key comes back as 403, not 404, so
  # both have to fall through to the SPA shell.
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
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

resource "aws_s3_bucket_policy" "app" {
  bucket = aws_s3_bucket.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudFrontServicePrincipal"
      Effect = "Allow"
      Principal = {
        Service = "cloudfront.amazonaws.com"
      }
      Action   = "s3:GetObject"
      Resource = "${aws_s3_bucket.app.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.app.arn
        }
      }
    }]
  })
}

resource "aws_route53_record" "app" {
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.app.domain_name
    zone_id                = aws_cloudfront_distribution.app.hosted_zone_id
    evaluate_target_health = false
  }
}
