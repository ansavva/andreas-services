# The PRODUCT distribution — app.humbugg.com.
#
# The app is an Expo Router single-page export, entirely behind auth, so there is
# nothing to server-render and no SSR origin here. That is the whole difference
# from modules/hosting: this distribution serves static objects and lets the
# client router resolve the path.
#
# The viewer certificate comes from modules/certificates, which owns the single
# us-east-1 certificate covering the apex, www, app and api.

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

resource "aws_cloudfront_origin_access_control" "app_web" {
  name                              = "${var.project}-appweb-oac"
  description                       = "OAC for ${var.project} Expo web export bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_origin_access_control" "avatars" {
  name                              = "${var.project}-avatars-oac"
  description                       = "OAC for ${var.project} avatars S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project} product app distribution"
  price_class         = "PriceClass_100"
  aliases             = ["app.${var.domain_name}"]
  default_root_object = "index.html"

  origin {
    domain_name              = var.app_web_bucket_regional_domain_name
    origin_id                = "S3-appweb"
    origin_access_control_id = aws_cloudfront_origin_access_control.app_web.id
  }

  origin {
    domain_name              = var.avatars_bucket_regional_domain_name
    origin_id                = "S3-avatars"
    origin_access_control_id = aws_cloudfront_origin_access_control.avatars.id
  }

  # index.html must never be cached: a stale one pins returning visitors to a
  # deleted asset bundle. The hashed assets under /_expo/* are immutable and are
  # cached hard by the behaviour below.
  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-appweb"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.disabled.id
  }

  ordered_cache_behavior {
    path_pattern           = "/_expo/*"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-appweb"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-appweb"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  # Profile photos, served read-only straight from the shared application bucket.
  # Moved here from modules/hosting with the migration: only the product app ever
  # renders an avatar, and APP_BASE_URL is what the backend derives avatar URLs
  # from, so they must live on this hostname.
  ordered_cache_behavior {
    path_pattern           = "/avatars/*"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-avatars"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  # Expo Router owns every path below the root, but S3 has an object only at
  # /index.html — so a deep link like /groups/abc or /join/xyz reaches S3 as a
  # miss. S3 answers 403 rather than 404 when the caller cannot list the bucket
  # (which OAC deliberately prevents), so BOTH have to be rewritten or deep links
  # break while the root works. 200, not the original status, or the client
  # router never boots.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = var.tags
}

resource "aws_s3_bucket_policy" "app_web" {
  bucket = var.app_web_bucket_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${var.app_web_bucket_arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.app.arn
          }
        }
      }
    ]
  })
}

resource "aws_s3_bucket_policy" "avatars" {
  bucket = var.avatars_bucket_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipalReadOnly"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action = "s3:GetObject"
        # The bucket is the shared application bucket; CloudFront may read only the avatars/ prefix,
        # never any other application object that may live there.
        Resource = "${var.avatars_bucket_arn}/avatars/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.app.arn
          }
        }
      }
    ]
  })
}

resource "aws_route53_record" "app" {
  for_each = toset(["A", "AAAA"])

  zone_id = var.route53_zone_id
  name    = "app.${var.domain_name}"
  type    = each.value

  alias {
    name                   = aws_cloudfront_distribution.app.domain_name
    zone_id                = aws_cloudfront_distribution.app.hosted_zone_id
    evaluate_target_health = false
  }
}
