terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.us_east_1]
    }
  }
}

data "aws_acm_certificate" "wildcard" {
  provider    = aws.us_east_1
  domain      = "*.andreas.services"
  statuses    = ["ISSUED"]
  most_recent = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project}-${var.environment}-web-oac"
  description                       = "OAC for the classroom frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"

  # CloudFront refuses to delete an OAC a live distribution still references.
  # Unlike force_destroy this takes effect on the renaming apply itself, because
  # it changes ordering rather than an argument read off prior state.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudfront_function" "spa_fallback" {
  name    = "${var.project}-${var.environment}-spa-fallback"
  runtime = "cloudfront-js-1.0"
  comment = "SPA fallback routing for classroom"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      // Real files (they carry an extension like .js/.css) are served as-is.
      if (uri.match(/\.[a-zA-Z0-9]+$/)) {
        return request;
      }

      // The SPA is mounted at the root, so every extension-less path is a
      // client-side route — including /p/<slug>, the link students follow.
      request.uri = '/index.html';
      return request;
    }
  EOT

  # CloudFront refuses to delete a function a live distribution references, so
  # the replacement must be created and wired up before the old one goes.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudfront_distribution" "app" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "classroom frontend distribution"
  price_class     = "PriceClass_100"
  aliases         = [var.domain_name]

  origin {
    domain_name              = var.s3_bucket_regional_domain_name
    origin_id                = "S3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    # The deploy sets per-object Cache-Control (immutable for hashed assets,
    # no-store for HTML), so the distribution defers to the origin rather than
    # holding a TTL of its own.
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
    compress    = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_fallback.arn
    }
  }

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

resource "aws_s3_bucket_policy" "frontend" {
  bucket = var.s3_bucket_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowCloudFrontServicePrincipal"
      Effect = "Allow"
      Principal = {
        Service = "cloudfront.amazonaws.com"
      }
      Action   = "s3:GetObject"
      Resource = "${var.s3_bucket_arn}/*"
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
