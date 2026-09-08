# THE STUDENT-FACING DISTRIBUTION. A SEPARATE ORIGIN, AND THAT IS THE POINT.
#
# This serves teacher-uploaded lesson files exactly as uploaded — her HTML, her
# CSS, her images, and **her JavaScript**, which runs. Lessons are interactive,
# so none of the usual defences against untrusted markup are available here:
# a sanitizer would destroy her styling, and `script-src 'none'` would break the
# lesson itself.
#
# What protects the teacher instead is that this is a DIFFERENT ORIGIN from the
# app she signs in to. Her session tokens live in `localStorage` on
# `classroom-admin.andreas.services`; `localStorage` is scoped to an origin, so
# a script running on this host cannot read them. That is the browser's
# same-origin policy rather than a header we configured — it cannot be
# weakened by a later edit to a CSP, and it holds even if this content is
# actively hostile.
#
# **Do not merge this back into `modules/hosting`.** The two distributions
# differ in exactly the way that matters: that one serves code we wrote, this
# one serves code we did not. A single distribution with two behaviours would
# put both on one origin and undo the entire control.
#
# Known residual risk, accepted deliberately: a script here can set cookies
# scoped to `.andreas.services`, which sibling services would receive. The full
# fix is a separate registrable domain — what GitHub does with
# `githubusercontent.com` — and is a domain purchase away if that ever matters.

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

resource "aws_cloudfront_origin_access_control" "lessons" {
  name                              = "${var.project}-${var.environment}-lessons-oac"
  description                       = "OAC for the classroom lesson content bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"

  # CloudFront refuses to delete an OAC a live distribution still references.
  lifecycle {
    create_before_destroy = true
  }
}

# `/lesson/<id>/` with no filename means that lesson's index page.
# `default_root_object` only covers the distribution root, not sub-paths, so the
# directory index is done here.
resource "aws_cloudfront_function" "lesson_index" {
  name    = "${var.project}-${var.environment}-lesson-index"
  runtime = "cloudfront-js-1.0"
  comment = "Directory-index rewrite for lesson content"
  publish = true
  code    = <<-EOT
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      // ONLY `/lesson/**` IS PUBLIC, AND THIS IS WHAT ENFORCES IT.
      //
      // The origin is the bucket ROOT, so without this every prefix in the
      // bucket is reachable — including `draft/<id>/`, where a lesson sits
      // before she publishes it and after she withdraws it. Publication would
      // then mean nothing: an unpublished lesson would be live at a guessable
      // URL. Anything outside /lesson/ is refused here, at the edge, before it
      // reaches S3.
      if (!uri.startsWith('/lesson/')) {
        return {
          statusCode: 404,
          statusDescription: 'Not Found',
          headers: { 'content-type': { value: 'text/plain' } },
          body: 'Not found',
        };
      }

      // Anything carrying an extension is a real file she uploaded — an image,
      // a stylesheet, a script, a font — and passes through untouched.
      if (uri.endsWith('/')) {
        request.uri = uri + 'index.html';
      } else if (!uri.match(/\.[a-zA-Z0-9]+$/)) {
        request.uri = uri + '/index.html';
      }
      return request;
    }
  EOT

  lifecycle {
    create_before_destroy = true
  }
}

# Defence in depth, NOT the primary control — the origin split above is that.
#
# Every header here is one a lesson has no legitimate use for, so none of them
# constrain what a teacher can build:
#
#   frame-ancestors  a lesson cannot be framed by anything, so it cannot be
#                    used to dress up a page on another site
#   X-Content-Type-Options  no MIME sniffing, so a mislabelled upload is not
#                    reinterpreted as something executable
#   Referrer-Policy  a student following a link out of a lesson does not leak
#                    the lesson URL
#
# Deliberately absent: any `script-src`. Lessons are interactive and that is the
# requirement, not an oversight.
resource "aws_cloudfront_response_headers_policy" "lesson" {
  name    = "${var.project}-${var.environment}-lesson-headers"
  comment = "Framing and sniffing protections for teacher-uploaded lesson content"

  security_headers_config {
    frame_options {
      frame_option = "DENY"
      override     = true
    }

    content_type_options {
      override = true
    }

    referrer_policy {
      override        = true
      referrer_policy = "no-referrer"
    }
  }
}

resource "aws_cloudfront_distribution" "lessons" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "classroom lesson content (teacher uploads, untrusted)"
  price_class     = "PriceClass_100"
  aliases         = [var.domain_name]

  origin {
    domain_name              = var.lessons_bucket_regional_domain_name
    origin_id                = "S3-lessons"
    origin_access_control_id = aws_cloudfront_origin_access_control.lessons.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-lessons"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # Short, not zero. A lesson is static once uploaded, but a teacher who
    # re-uploads the morning of a class expects the change live in a minute
    # rather than a day, and nothing invalidates this distribution on deploy.
    min_ttl     = 0
    default_ttl = 60
    max_ttl     = 300

    response_headers_policy_id = aws_cloudfront_response_headers_policy.lesson.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.lesson_index.arn
    }
  }

  # **No `custom_error_response` rewriting 404 to an index page.** The app's
  # distribution does that for SPA routing; doing it here would answer a
  # missing image with a lesson's HTML, and would make a withdrawn lesson look
  # like a working one.

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

resource "aws_route53_record" "lessons" {
  for_each = toset(["A", "AAAA"])

  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = each.value

  alias {
    name                   = aws_cloudfront_distribution.lessons.domain_name
    zone_id                = aws_cloudfront_distribution.lessons.hosted_zone_id
    evaluate_target_health = false
  }
}
