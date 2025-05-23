# Create the API Gateway HTTP API
resource "aws_apigatewayv2_api" "paypulse_api" {
  name          = "PayPulseSignupAPI"
  protocol_type = "HTTP"
}

# Connect API Gateway to SignupUser lambda function
resource "aws_apigatewayv2_integration" "signup_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"  # this means just forward the whole request body to the lambda function
  integration_uri        = aws_lambda_function.signup_user.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/signup)
resource "aws_apigatewayv2_route" "signup_route" {
  api_id     = aws_apigatewayv2_api.paypulse_api.id
  route_key  = "POST /signup"
  target     = "integrations/${aws_apigatewayv2_integration.signup_integration.id}"
}

# Deploy signup with default stage
resource "aws_apigatewayv2_stage" "signup_stage" {
  api_id      = aws_apigatewayv2_api.paypulse_api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_logs.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      sourceIp                = "$context.identity.sourceIp"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      path                    = "$context.path"
      status                  = "$context.status"
      protocol                = "$context.protocol"
      responseLength          = "$context.responseLength"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = true
    logging_level            = "INFO"
    data_trace_enabled       = true

    # throttling settings
    throttling_burst_limit = 5000   # max concurrent requests in a burst
    throttling_rate_limit  = 1000.0 # average requests per second
  }
}

# Allow API Gateway to invoke the signup lambda function
resource "aws_lambda_permission" "signup_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.signup_user.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}

# create Cloudwatch group for logging
resource "aws_cloudwatch_log_group" "api_gateway_logs" {
  name = "/aws/apigateway/${aws_apigatewayv2_api.paypulse_api.name}"
  retention_in_days = 30
}

# Connect API Gateway to LoginUser lambda function
resource "aws_apigatewayv2_integration" "login_integration" {
  api_id                 = aws_apigatewayv2_api.paypulse_api.id
  integration_type       = "AWS_PROXY"  # this means just forward the whole request body to the lambda function
  integration_uri        = aws_lambda_function.login_user.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

# Create a route (URL path/login)
resource "aws_apigatewayv2_route" "login_route" {
  api_id    = aws_apigatewayv2_api.paypulse_api.id
  route_key = "POST /login"
  target    = "integrations/${aws_apigatewayv2_integration.login_integration.id}"
}

/*
# TODO: Not sure if this is needed. Perhaps this sets logging settings on an API level, instead of an endpoint level
# Deploy login with default stage
resource "aws_apigatewayv2_stage" "login_api_stage" {
  api_id      = aws_apigatewayv2_api.paypulse_api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_logs.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      sourceIp                = "$context.identity.sourceIp"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      path                    = "$context.path"
      status                  = "$context.status"
      protocol                = "$context.protocol"
      responseLength          = "$context.responseLength"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    detailed_metrics_enabled = true
    logging_level            = "INFO"
    data_trace_enabled       = true

    # throttling settings
    throttling_burst_limit = 5000   # max concurrent requests in a burst
    throttling_rate_limit  = 1000.0 # average requests per second
  }
}

 */

# Allow API Gateway to invoke the login lambda function
resource "aws_lambda_permission" "login_api_permission" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.login_user.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.paypulse_api.execution_arn}/*/*"
}