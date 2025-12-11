# ACM Certificate for CloudFront (must be in us-east-1)
resource "aws_acm_certificate" "app" {
  provider          = aws.us_east_1
  domain_name       = var.app_subdomain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "storybook-app-cert"
  }
}

# CloudFront Origin Access Control
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "storybook-frontend-oac"
  description                       = "OAC for Storybook frontend S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "app" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Storybook application distribution"
  price_class         = "PriceClass_100" # Use only North America and Europe
  aliases             = [var.app_subdomain]

  # S3 origin for frontend
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "S3-storybook-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # API Gateway origin for backend
  origin {
    domain_name = replace(aws_apigatewayv2_api.backend.api_endpoint, "https://", "")
    origin_id   = "APIGateway-storybook-backend"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Default behavior - redirect to /app
  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-storybook-frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0

    lambda_function_association {
      event_type   = "viewer-request"
      lambda_arn   = aws_lambda_function.redirect_to_app.qualified_arn
      include_body = false
    }
  }

  # Cache behavior for /app path prefix (frontend)
  ordered_cache_behavior {
    path_pattern     = "${var.frontend_path}/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-storybook-frontend"

    forwarded_values {
      query_string = false
      headers      = ["Origin"]

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }

  # Cache behavior for /api path prefix (backend)
  ordered_cache_behavior {
    path_pattern     = "${var.backend_path}/*"
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "APIGateway-storybook-backend"

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Accept", "Content-Type", "Origin"]

      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = true
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
    acm_certificate_arn      = aws_acm_certificate.app.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Name = "storybook-app-distribution"
  }

  depends_on = [
    aws_acm_certificate_validation.app,
    aws_lambda_function.redirect_to_app
  ]
}

# Lambda@Edge function to redirect root to /app
resource "aws_lambda_function" "redirect_to_app" {
  provider         = aws.us_east_1  # Lambda@Edge must be in us-east-1
  filename         = data.archive_file.redirect_lambda.output_path
  function_name    = "storybook-redirect-to-app"
  role             = aws_iam_role.lambda_edge.arn
  handler          = "index.handler"
  source_code_hash = data.archive_file.redirect_lambda.output_base64sha256
  runtime          = "nodejs18.x"
  publish          = true  # Required for Lambda@Edge

  tags = {
    Name = "storybook-redirect-lambda"
  }
}

# IAM role for Lambda@Edge
resource "aws_iam_role" "lambda_edge" {
  provider = aws.us_east_1
  name     = "storybook-lambda-edge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = [
            "lambda.amazonaws.com",
            "edgelambda.amazonaws.com"
          ]
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_edge_basic" {
  provider   = aws.us_east_1
  role       = aws_iam_role.lambda_edge.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Package the Lambda function
data "archive_file" "redirect_lambda" {
  type        = "zip"
  output_path = "${path.module}/redirect_lambda.zip"

  source {
    content  = <<EOF
exports.handler = async (event) => {
    const request = event.Records[0].cf.request;
    const uri = request.uri;

    // Redirect root to /app
    if (uri === '/' || uri === '') {
        return {
            status: '302',
            statusDescription: 'Found',
            headers: {
                location: [{
                    key: 'Location',
                    value: '/app'
                }]
            }
        };
    }

    return request;
};
EOF
    filename = "index.js"
  }
}

# ACM Certificate Validation
resource "aws_acm_certificate_validation" "app" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for record in aws_route53_record.app_cert_validation : record.fqdn]
}
