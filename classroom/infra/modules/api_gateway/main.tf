# The API has exactly two surfaces and the split is the whole security model:
#
#   /api/public/*  — NO authorizer. The student reader lives here. A student
#                    following a link has no account and never will.
#   /api/pages*    — Cognito authorizer. Everything that reads or writes a
#                    teacher's own pages.
#
# Nothing else is routed, so a new path is a deliberate act rather than
# something that falls through to the Lambda unauthenticated.

resource "aws_api_gateway_rest_api" "main" {
  name = "${var.project}-${var.environment}-api"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = var.tags
}

resource "aws_api_gateway_resource" "api" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "api"
}

# --- the anonymous reader -------------------------------------------------

resource "aws_api_gateway_resource" "public" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.api.id
  path_part   = "public"
}

resource "aws_api_gateway_resource" "public_proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.public.id
  path_part   = "{proxy+}"
}

# Deliberately GET-only. The public surface reads; it must not offer a verb
# that writes, even though the Lambda behind it registers no such route.
resource "aws_api_gateway_method" "public_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.public_proxy.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "public_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.public_proxy.id
  http_method             = aws_api_gateway_method.public_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
}

# --- the teacher's workspace ----------------------------------------------

resource "aws_api_gateway_authorizer" "cognito" {
  count           = var.enable_cognito_authorizer ? 1 : 0
  name            = "${var.project}-${var.environment}-cognito"
  rest_api_id     = aws_api_gateway_rest_api.main.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [var.cognito_user_pool_arn]
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_resource" "pages" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.api.id
  path_part   = "pages"
}

resource "aws_api_gateway_resource" "pages_proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.pages.id
  path_part   = "{proxy+}"
}

# ANY /api/pages — the collection (list, create)
resource "aws_api_gateway_method" "pages_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.pages.id
  http_method   = "ANY"
  authorization = var.enable_cognito_authorizer ? "COGNITO_USER_POOLS" : "NONE"
  authorizer_id = var.enable_cognito_authorizer ? aws_api_gateway_authorizer.cognito[0].id : null
}

resource "aws_api_gateway_integration" "pages_any" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.pages.id
  http_method             = aws_api_gateway_method.pages_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
}

# ANY /api/pages/{proxy+} — one page (get, update, delete)
resource "aws_api_gateway_method" "pages_proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.pages_proxy.id
  http_method   = "ANY"
  authorization = var.enable_cognito_authorizer ? "COGNITO_USER_POOLS" : "NONE"
  authorizer_id = var.enable_cognito_authorizer ? aws_api_gateway_authorizer.cognito[0].id : null
}

resource "aws_api_gateway_integration" "pages_proxy_any" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.pages_proxy.id
  http_method             = aws_api_gateway_method.pages_proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
}

# --- CORS preflight -------------------------------------------------------
#
# OPTIONS must stay unauthenticated on the protected resources: the browser
# sends the preflight without an Authorization header, so an authorizer here
# would fail every cross-origin write before the real request is ever made.

locals {
  cors_resources = {
    pages       = aws_api_gateway_resource.pages.id
    pages_proxy = aws_api_gateway_resource.pages_proxy.id
  }
}

resource "aws_api_gateway_method" "options" {
  for_each = local.cors_resources

  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = each.value
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options" {
  for_each = local.cors_resources

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = each.value
  http_method = aws_api_gateway_method.options[each.key].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = jsonencode({ statusCode = 200 })
  }
}

resource "aws_api_gateway_method_response" "options_200" {
  for_each = local.cors_resources

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = each.value
  http_method = aws_api_gateway_method.options[each.key].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options" {
  for_each = local.cors_resources

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = each.value
  http_method = aws_api_gateway_method.options[each.key].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,DELETE,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_method_response.options_200]
}

# --- deployment -----------------------------------------------------------

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.api.id,
      aws_api_gateway_resource.public.id,
      aws_api_gateway_resource.public_proxy.id,
      aws_api_gateway_resource.pages.id,
      aws_api_gateway_resource.pages_proxy.id,
      aws_api_gateway_method.public_get.id,
      aws_api_gateway_method.pages_any.id,
      aws_api_gateway_method.pages_proxy_any.id,
      values(aws_api_gateway_method.options)[*].id,
      aws_api_gateway_integration.public_get.id,
      aws_api_gateway_integration.pages_any.id,
      aws_api_gateway_integration.pages_proxy_any.id,
      var.cognito_user_pool_arn,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.public_get,
    aws_api_gateway_integration.pages_any,
    aws_api_gateway_integration.pages_proxy_any,
    aws_api_gateway_integration.options,
  ]
}

resource "aws_api_gateway_stage" "main" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = var.stage_name

  tags = var.tags
}

resource "aws_api_gateway_method_settings" "throttle" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.throttle_rate
    throttling_burst_limit = var.throttle_burst
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_api_gateway_base_path_mapping" "main" {
  api_id      = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  domain_name = var.custom_domain_name
  base_path   = var.base_path != "" ? var.base_path : null
}
