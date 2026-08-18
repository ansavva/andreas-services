locals {
  prefix = "${var.project}-${var.environment}"

  # The browser-facing CORS contract, stated once. Three places below serve it —
  # the MOCK preflight and the two authorizer gateway responses — and they used
  # to carry three hand-written copies of the same string.
  #
  # The fourth copy, `CORS(methods=...)` in `backend/studio_core/app_factory.py`,
  # cannot be derived from here and still has to be kept in step by hand.
  cors_methods = "GET,POST,PATCH,DELETE,OPTIONS"
  cors_headers = "Content-Type,Authorization"
}

# REST API fronting the single Python Lambda.
#
# Unlike the website's API, which has public routes, EVERY studio route is behind
# the Cognito authorizer — the app exists to expose a private bucket, so there is
# nothing here that an anonymous caller should reach. `/api/health` is the single
# exception, carved out as its own resource because API Gateway prefers an exact
# path over `{proxy+}`; it returns a literal `{"status":"ok"}` and touches no S3.
resource "aws_api_gateway_rest_api" "main" {
  name = "${local.prefix}-api"

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

# ---------------------------------------------------------------------------
# Protected: ANY /api/{proxy+}
# ---------------------------------------------------------------------------
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.api.id
  path_part   = "{proxy+}"
}

# Authorizes against the **ID token**. A REST `COGNITO_USER_POOLS` authorizer
# only treats the incoming token as an access token when the method declares
# `authorization_scopes`; with none declared — and there are none to declare,
# because the pool has no resource server and Amplify's SRP flow only ever mints
# `aws.cognito.signin.user.admin` — it validates an identity token. An access
# token here is a silent 401 on every call, with sign-in still working.
resource "aws_api_gateway_authorizer" "cognito" {
  rest_api_id     = aws_api_gateway_rest_api.main.id
  name            = "${local.prefix}-app"
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [var.cognito_user_pool_arn]
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "proxy_any" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
}

# ---------------------------------------------------------------------------
# Public: GET /api/health — liveness only, so deploys and alarms can check the
# Lambda is answering without holding a Cognito session.
# ---------------------------------------------------------------------------
resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.api.id
  path_part   = "health"
}

resource "aws_api_gateway_method" "health_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.health.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.health_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
}

# ---------------------------------------------------------------------------
# CORS preflight (MOCK) — must stay unauthenticated, because the browser sends
# the OPTIONS with no Authorization header and the authorizer would 401 it
# before the real request ever happens.
#
# The method list is what the *browser* is told, and it is answered here rather
# than by Flask — so a verb the app implements but this omits is a CORS failure
# no amount of Flask configuration can rescue. This copy and the two gateway
# responses further down now all read `local.cors_methods`, so the only copy left
# to keep in step by hand is `CORS(methods=...)` in `app_factory.py`. A preflight
# is also sent for any request carrying a JSON body, which every write route
# does — so a missing verb here takes the whole write half of the app down.
#
# Widening the list is only half the job: it reaches a browser solely through a
# new stage deployment, which is why the `triggers` hash below has to include
# these values and not just resource ids.
# ---------------------------------------------------------------------------
resource "aws_api_gateway_method" "options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options" {
  rest_api_id       = aws_api_gateway_rest_api.main.id
  resource_id       = aws_api_gateway_resource.proxy.id
  http_method       = aws_api_gateway_method.options.http_method
  type              = "MOCK"
  request_templates = { "application/json" = jsonencode({ statusCode = 200 }) }
}

resource "aws_api_gateway_method_response" "options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'${local.cors_headers}'"
    "method.response.header.Access-Control-Allow-Methods" = "'${local.cors_methods}'"
    "method.response.header.Access-Control-Allow-Origin"  = "'${var.allowed_origin}'"
  }
  depends_on = [aws_api_gateway_method_response.options]
}

# ---------------------------------------------------------------------------
# CORS on the authorizer's own rejections.
#
# An authorizer rejection is generated by API Gateway before the integration
# runs, so it does NOT pick up the Flask app's CORS headers — and the MOCK
# preflight above only covers the OPTIONS, not the GET that follows it. Without
# these two responses a 401 reaches the browser with no
# `Access-Control-Allow-Origin`, the fetch rejects as a CORS error, and the SPA
# sees an opaque network failure instead of the status it needs to act on.
# ---------------------------------------------------------------------------
resource "aws_api_gateway_gateway_response" "unauthorized" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  response_type = "UNAUTHORIZED"
  status_code   = "401"

  # Declared rather than left to API Gateway's default because the SPA reads it:
  # `apis/client.ts` falls back to `body.message` when a response is not the
  # API's own `{"error": ...}` shape, which an authorizer rejection never is.
  # Leaving it undeclared makes every apply strip it, and a 401 then reaches the
  # UI as a bare status with nothing to show the user.
  response_templates = {
    "application/json" = "{\"message\":$context.error.messageString}"
  }

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'${var.allowed_origin}'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'${local.cors_headers}'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'${local.cors_methods}'"
  }
}

resource "aws_api_gateway_gateway_response" "access_denied" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  response_type = "ACCESS_DENIED"
  status_code   = "403"

  # Declared rather than left to API Gateway's default because the SPA reads it:
  # `apis/client.ts` falls back to `body.message` when a response is not the
  # API's own `{"error": ...}` shape, which an authorizer rejection never is.
  # Leaving it undeclared makes every apply strip it, and a 401 then reaches the
  # UI as a bare status with nothing to show the user.
  response_templates = {
    "application/json" = "{\"message\":$context.error.messageString}"
  }

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'${var.allowed_origin}'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'${local.cors_headers}'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'${local.cors_methods}'"
  }
}

# ---------------------------------------------------------------------------
# Deployment + stage
# ---------------------------------------------------------------------------
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.api.id,
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_resource.health.id,
      aws_api_gateway_method.proxy_any.id,
      aws_api_gateway_method.health_get.id,
      aws_api_gateway_integration.proxy_any.id,
      aws_api_gateway_integration.health_get.id,
      # The CORS header *values*, not just the ids of the resources carrying
      # them. An integration response's id is `agir-<api>-<resource>-OPTIONS-200`
      # and a gateway response's is `aggr-<api>-<type>`; neither encodes
      # `response_parameters`, so listing only ids meant a change to the allowed
      # method list produced no new deployment and the stage went on serving the
      # preflight it was born with.
      #
      # That is not hypothetical. When studio gained its write routes the method
      # list was widened to `GET,POST,PATCH,DELETE,OPTIONS` here and applied
      # cleanly, while the deployed stage kept answering `GET,OPTIONS` — so every
      # write from the browser died at the preflight as an opaque CORS error with
      # no status, for months, with `terraform plan` clean the whole time. The
      # deployment is the only thing between this config and what a browser sees;
      # anything a browser can observe has to be in this hash by value.
      aws_api_gateway_integration_response.options.response_parameters,
      aws_api_gateway_gateway_response.unauthorized.response_parameters,
      aws_api_gateway_gateway_response.access_denied.response_parameters,
      aws_api_gateway_gateway_response.unauthorized.response_templates,
      aws_api_gateway_gateway_response.access_denied.response_templates,
      var.cognito_user_pool_arn,
      var.allowed_origin,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.proxy_any,
    aws_api_gateway_integration.health_get,
    aws_api_gateway_integration.options,
    aws_api_gateway_gateway_response.unauthorized,
    aws_api_gateway_gateway_response.access_denied,
  ]
}

resource "aws_api_gateway_stage" "main" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = var.stage_name
  tags          = var.tags
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
