# modules/compute/main.tf
# Lambda function, ECR, and API Gateway (production only)

# ECR Repository
resource "aws_ecr_repository" "backend" {
  name                 = "${var.project}-backend-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus     = "any"
        countType     = "imageCountMoreThan"
        countNumber   = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# IAM role for Lambda
resource "aws_iam_role" "lambda" {
  name = "${var.project}-lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = var.image_queue_arn
      }
    ],
    var.vpc_id != null ? [{
      Effect = "Allow"
      Action = [
        "ec2:CreateNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:DeleteNetworkInterface"
      ]
      Resource = "*"
    }] : [])
  })
}

# Security group for Lambda (only if VPC is used)
resource "aws_security_group" "lambda" {
  count       = var.enable_vpc ? 1 : 0
  name        = "${var.project}-lambda-${var.environment}"
  description = "Security group for Lambda function"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project}-lambda-${var.environment}"
  })
}

# Lambda Function
resource "aws_lambda_function" "backend" {
  function_name = "${var.project}-backend-${var.environment}"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:latest"
  timeout       = 30
  memory_size   = 512

  dynamic "vpc_config" {
    for_each = var.enable_vpc ? [1] : []
    content {
      subnet_ids         = var.subnet_ids
      security_group_ids = [aws_security_group.lambda[0].id]
    }
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [
      image_uri,
      environment,
    ]
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.backend.function_name}"
  retention_in_days = 14

  tags = var.tags
}

# API Gateway v2 (HTTP API)
resource "aws_apigatewayv2_api" "backend" {
  name          = "${var.project}-backend-${var.environment}"
  protocol_type = "HTTP"
  description   = "${var.project} Backend API"

  cors_configuration {
    allow_credentials = true
    allow_origins     = var.cors_allowed_origins
    allow_methods     = ["*"]
    allow_headers     = ["*"]
    expose_headers    = ["*"]
    max_age           = 3600
  }

  tags = var.tags
}

resource "aws_apigatewayv2_integration" "backend" {
  api_id           = aws_apigatewayv2_api.backend.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.backend.invoke_arn

  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "backend" {
  api_id    = aws_apigatewayv2_api.backend.id
  route_key = "$default"

  target = "integrations/${aws_apigatewayv2_integration.backend.id}"
}

resource "aws_apigatewayv2_stage" "backend" {
  api_id      = aws_apigatewayv2_api.backend.id
  name        = "$default"
  auto_deploy = true

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${var.project}-backend-${var.environment}"
  retention_in_days = 14

  tags = var.tags
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.backend.execution_arn}/*/*"
}
