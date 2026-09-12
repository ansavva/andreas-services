# The realtime channel (#691): an API Gateway WebSocket API that pushes "something changed for you
# here" to the app, so the anonymous chat feels like a chat rather than a poll.
#
# Nothing else in this deployment can hold a connection — the HTTP API and Lambda both answer and
# hang up — so this is a second API of its own kind, on its own hostname: a custom domain cannot
# carry a WebSocket API and an HTTP API together, and ws.humbugg.com is the one this gets.
#
# Two Lambdas, both the backend's own image with a HUMBUGG_CONSUMER mode, the same way the
# reminder and webhook consumers are. The AUTHORIZER guards $connect: it spends the one-time ticket
# in the query string and hands the user id to the CONNECTIONS handler, which records the socket on
# $connect and forgets it on $disconnect. The API Lambda (the HTTP one) is what pushes: it looks a
# user's sockets up in the table and posts to them through the management endpoint, which is the
# ManageConnections grant below.

resource "aws_lambda_function" "authorizer" {
  function_name = "${var.project}-${var.environment}-realtime-authorizer"
  role          = var.lambda_role_arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = 10
  memory_size   = 256

  environment {
    variables = {
      HUMBUGG_CONSUMER               = "realtime-authorizer"
      HUMBUGG_CHAT_CONNECTIONS_TABLE = var.connections_table_name
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

resource "aws_lambda_function" "connections" {
  function_name = "${var.project}-${var.environment}-realtime-connections"
  role          = var.lambda_role_arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = 10
  memory_size   = 256

  environment {
    variables = {
      HUMBUGG_CONSUMER               = "realtime-connections"
      HUMBUGG_CHAT_CONNECTIONS_TABLE = var.connections_table_name
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

resource "aws_apigatewayv2_api" "realtime" {
  name                       = "${var.project}-${var.environment}-realtime"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"

  tags = var.tags
}

# REQUEST is the only authorizer kind a WebSocket API has, and $connect the only route it guards.
# The identity source is the ticket; a connect without one is refused before the Lambda runs.
resource "aws_apigatewayv2_authorizer" "ticket" {
  api_id           = aws_apigatewayv2_api.realtime.id
  authorizer_type  = "REQUEST"
  authorizer_uri   = aws_lambda_function.authorizer.invoke_arn
  identity_sources = ["route.request.querystring.ticket"]
  name             = "${var.project}-${var.environment}-realtime-ticket"
}

resource "aws_apigatewayv2_integration" "connections" {
  api_id           = aws_apigatewayv2_api.realtime.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.connections.invoke_arn
}

resource "aws_apigatewayv2_route" "connect" {
  api_id             = aws_apigatewayv2_api.realtime.id
  route_key          = "$connect"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.ticket.id
  target             = "integrations/${aws_apigatewayv2_integration.connections.id}"
}

resource "aws_apigatewayv2_route" "disconnect" {
  api_id    = aws_apigatewayv2_api.realtime.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.connections.id}"
}

# Anything a client sends — a keep-alive ping — lands here and is dropped. The channel is one-way.
resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.realtime.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.connections.id}"
}

# WebSocket stages do not auto-deploy the way HTTP API stages do, so a deployment is declared and
# re-created whenever a route or the integration changes. create_before_destroy keeps the stage
# pointed at a live deployment through the swap.
resource "aws_apigatewayv2_deployment" "realtime" {
  api_id = aws_apigatewayv2_api.realtime.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_apigatewayv2_integration.connections,
      aws_apigatewayv2_route.connect,
      aws_apigatewayv2_route.disconnect,
      aws_apigatewayv2_route.default,
      aws_apigatewayv2_authorizer.ticket,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_stage" "realtime" {
  api_id        = aws_apigatewayv2_api.realtime.id
  name          = var.environment
  deployment_id = aws_apigatewayv2_deployment.realtime.id

  default_route_settings {
    throttling_rate_limit  = 100
    throttling_burst_limit = 200
  }

  tags = var.tags
}

resource "aws_lambda_permission" "authorizer" {
  statement_id  = "AllowRealtimeApiAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.realtime.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.ticket.id}"
}

resource "aws_lambda_permission" "connections" {
  statement_id  = "AllowRealtimeApiRoutes"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.connections.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.realtime.execution_arn}/*/*"
}

# The push itself: PostToConnection is an execute-api call against this API's @connections
# resource. Granted to the API Lambda's role, which is also what the two Lambdas above run under.
resource "aws_iam_role_policy" "manage_connections" {
  name = "${var.project}-${var.environment}-realtime-manage-connections"
  role = var.lambda_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["execute-api:ManageConnections"]
      Resource = "${aws_apigatewayv2_api.realtime.execution_arn}/${aws_apigatewayv2_stage.realtime.name}/POST/@connections/*"
    }]
  })
}
